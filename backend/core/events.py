"""Единая шина событий: web-панель, устройство M5 и озвучка.

Модули не работают с WebSocket/Serial напрямую — они вызывают bus.emit(...),
а шина сама решает, куда доставить сообщение:
  * все JSON-события уходят web-клиентам;
  * подмножество событий (эмоции, метрики, речь) уходит питомцу — по Wi-Fi,
    если он на WebSocket, иначе по USB-Serial;
  * аудио TTS передаётся чанками с паузами под скорость воспроизведения I2S.

Речь произносится по предложениям: первая фраза начинает звучать, пока
синтезируются следующие, а любое из них можно оборвать на полуслове —
именно так работает перебивание питомца.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
from collections.abc import Callable
from typing import Any

from core import stats
from core.serial_manager import serial_manager
from core.ws_manager import manager

logger = logging.getLogger("core.events")

# Что понимает прошивка питомца — остальное ей слать бессмысленно и вредно.
# Вредно потому, что канал до устройства узкий: снимок задач или лог шагов
# агента не влезает в буфер команды и рвёт WebSocket питомца (код 1009).
# Белый список, а не чёрный: новое событие панели по умолчанию до устройства
# не доходит, и это правильное поведение по умолчанию.
DEVICE_ACTIONS = {
    "speak", "set_emotion", "update_pc", "pomodoro", "set_rotation",
    "stop_audio", "agent_status", "listening", "beep", "set_screen",
    "set_brightness", "set_mic", "identify",
    # Громкость динамика самого питомца. Наружу — device_volume, чтобы не
    # путать с инструментом set_volume, который крутит громкость ПК;
    # на провод уходит set_volume (см. _device_message).
    "device_volume",
    "set_autorotate",  # автоповорот экрана по акселерометру
    "restart",         # перезагрузка ESP32
    "status",          # «представься»: питомец в ответ шлёт device_status
    "set_time",        # синхронизация часов на экране
    "audio_start",     # предупреждение о начале потока речи
}

# 4096 байт = 128 мс звука при 16 кГц/16 бит/моно. Пауза 110 мс держит темп
# чуть быстрее воспроизведения, не переполняя DMA-буфер I2S.
AUDIO_CHUNK_SIZE = 4096
AUDIO_CHUNK_DELAY = 0.11

_CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_URL = re.compile(r"https?://\S+")
_MARKDOWN = re.compile(r"[*_`#>|]+")
_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F0FF️]+"
)
_PATH = re.compile(r"[A-Za-z]:[\\/][^\s,;]+")
_SENTENCE = re.compile(r"[^.!?…]+[.!?…]*")

# Транслитерация для экрана: встроенный шрифт M5 не умеет кириллицу
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def sanitize_for_speech(text: str) -> str:
    """Готовит текст для синтезатора: без разметки, ссылок, эмодзи и длинных путей."""
    clean = _CODE_BLOCK.sub(" фрагмент кода, смотри панель, ", text)
    clean = _URL.sub("ссылка", clean)
    clean = _PATH.sub("путь", clean)
    clean = _MARKDOWN.sub("", clean)
    clean = _EMOJI.sub("", clean)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


def to_display_text(text: str, limit: int = 64) -> str:
    """Латиница для экрана питомца — кириллицу встроенный шрифт не рисует."""
    result = []
    for ch in sanitize_for_speech(text):
        lower = ch.lower()
        if lower in _TRANSLIT:
            mapped = _TRANSLIT[lower]
            result.append(mapped.upper() if ch.isupper() else mapped)
        elif ch.isascii():
            result.append(ch)
        else:
            result.append(" ")
    return re.sub(r"\s+", " ", "".join(result)).strip()[:limit]


def split_sentences(text: str, max_len: int = 160) -> list[str]:
    """Режет ответ на фразы для поштучной озвучки."""
    parts: list[str] = []
    for match in _SENTENCE.finditer(text):
        sentence = match.group().strip()
        while len(sentence) > max_len:
            cut = sentence.rfind(" ", 0, max_len)
            cut = cut if cut > 40 else max_len
            parts.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if sentence:
            parts.append(sentence)
    return parts or ([text.strip()] if text.strip() else [])


class EventBus:
    def __init__(self) -> None:
        self._speaking = False
        # Локальные подписчики внутри процесса (трей: иконка и уведомления).
        # Это не WebSocket-клиенты, их нельзя «разослать» — их надо позвать.
        self._listeners: list[Callable[[dict[str, Any]], Any]] = []
        # Номер текущей реплики. Прерывание увеличивает счётчик, и все циклы
        # отправки, начатые для прошлой реплики, сами останавливаются.
        # Со «залипающим» флагом отмены получались две беды сразу: либо она
        # снималась не вовремя и прерванный ответ договаривался, либо оставалась
        # навсегда и питомец замолкал до перезапуска.
        self._speech_id = 0
        # Предложения из потока проговариваются строго по очереди
        self._sentence_lock = asyncio.Lock()

    def begin_speech(self) -> int:
        """Начало новой реплики. Возвращает её номер."""
        self._speech_id += 1
        return self._speech_id

    def _is_current(self, speech_id: int) -> bool:
        return speech_id == self._speech_id

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    # ── подписка изнутри процесса ──────────────────────────────────────────
    def subscribe(self, callback: Callable[[dict[str, Any]], Any]) -> Callable[[], None]:
        """Подписывает локального слушателя на все события шины.

        Нужно трею: он ловит approval_request и agent_status, чтобы менять
        иконку и показывать всплывающие уведомления, не поднимая ради этого
        собственный WebSocket-клиент к самому себе.

        Возвращает функцию отписки — удобно для «подписался и забыл» в тестах
        и в коде с временем жизни короче, чем у шины. Тот же эффект даёт
        явный вызов unsubscribe(callback).
        """
        self._listeners.append(callback)
        return lambda: self.unsubscribe(callback)

    def unsubscribe(self, callback: Callable[[dict[str, Any]], Any]) -> None:
        """Снимает подписку. Повторный вызов безопасен."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify(self, message: dict[str, Any]) -> None:
        """Зовёт слушателей синхронно, но так, чтобы их беды остались их бедами.

        Падение трея не должно ронять emit: событие уже ушло панели и питомцу,
        и откатывать доставку из-за упавшего колбэка бессмысленно.
        """
        for callback in list(self._listeners):
            try:
                result = callback(message)
                if inspect.isawaitable(result):
                    # Асинхронный слушатель допустим, но ждать его прямо здесь
                    # нельзя: медленная корутина затормозила бы всю рассылку.
                    asyncio.create_task(self._await_listener(result))
            except Exception as e:  # noqa: BLE001
                logger.error(
                    f"Слушатель шины упал на событии "
                    f"{message.get('action', 'unknown')}: {e}"
                )

    @staticmethod
    async def _await_listener(awaitable: Any) -> None:
        try:
            await awaitable
        except Exception as e:  # noqa: BLE001
            logger.error(f"Асинхронный слушатель шины упал: {e}")

    # ── базовая отправка ───────────────────────────────────────────────────
    async def emit(self, action: str, **payload: Any) -> None:
        """Событие для web-панели (и для питомца, если он его понимает)."""
        await self._dispatch({"action": action, **payload})

    async def emit_raw(self, message: dict[str, Any]) -> None:
        """То же самое, но событие уже собрано словарём (метрики pc_monitor).

        Раньше здесь словарь разбирался обратно в kwargs и снова собирался в
        emit — лишний круг, который вдобавок ломался на ключах, не являющихся
        идентификаторами Python. Теперь оба входа ведут в один _dispatch,
        то есть маршрутизация у них гарантированно одна и та же.
        """
        payload = dict(message)
        payload.setdefault("action", "unknown")
        await self._dispatch(payload)

    async def _dispatch(self, message: dict[str, Any]) -> None:
        """Единственное место, где решается, кто получит событие.

        Три независимых адресата, и разделение между ними принципиальное:
          1. Панели — всё и как есть: полный UTF-8 текст, любые объёмы.
          2. Питомец — только команды из DEVICE_ACTIONS и только в «узком»
             виде (_device_message). Транспорт: Wi-Fi, если устройство на
             WebSocket, иначе USB. Важно, что переработка сообщения общая для
             обоих транспортов — раньше её проходил только USB, и по Wi-Fi
             питомец получал кириллицу, которую его шрифт рисует мусором.
          3. Локальные подписчики внутри процесса (трей).
        """
        action = str(message.get("action", "unknown"))

        await manager.broadcast_json(message)

        if action in DEVICE_ACTIONS:
            device_message = self._device_message(message)
            # Wi-Fi предпочтительнее: он быстрее и не занимает COM-порт. Но если
            # сокет питомца отвалился ровно между проверкой и отправкой,
            # send_to_device вернёт False — тогда пробуем USB. Кабель часто
            # воткнут одновременно с Wi-Fi, и терять команду только потому, что
            # сеть моргнула, незачем: при закрытом порте send_json — пустышка.
            delivered = False
            if manager.device_on_wifi:
                delivered = await manager.send_to_device(device_message)
            if not delivered:
                serial_manager.send_json(device_message)

        self._notify(message)

    @staticmethod
    def _device_message(message: dict[str, Any]) -> dict[str, Any]:
        """Приводит событие к тому виду, который переварит прошивка.

        Две правки, и обе обязаны применяться на ОБОИХ транспортах:

        * Текст переводим в латиницу и режем до 64 символов. Встроенный шрифт
          M5 кириллицу не рисует, а команда целиком должна влезть в буфер
          прошивки — иначе она молча отбрасывается.
        * Действие device_volume переименовываем в set_volume. Наружу — для
          панели и для инструментов агента — громкость динамика питомца зовётся
          device_volume, чтобы её нельзя было спутать с инструментом set_volume,
          который крутит громкость Windows. На провод же уходит имя, которое
          прошивка знает исторически, — set_volume.
        """
        device = dict(message)
        if device.get("action") == "device_volume":
            device["action"] = "set_volume"
        if device.get("text"):
            device["text"] = to_display_text(str(device["text"]))
        return device

    async def set_emotion(self, emotion: str, text: str = "") -> None:
        await self.emit("set_emotion", emotion=emotion, text=text)

    # ── речь ───────────────────────────────────────────────────────────────
    async def speak(self, text: str, emotion: str = "happy", voice: bool = True) -> None:
        """Показывает реплику везде и (при voice=True) озвучивает её по фразам."""
        await self.emit("speak", emotion=emotion, text=text)
        if not voice or not text:
            return

        from core.settings import settings_store

        settings = settings_store.current
        if not settings.speak_replies:
            return

        spoken = sanitize_for_speech(text)
        if len(spoken) > settings.max_speech_chars:
            spoken = spoken[: settings.max_speech_chars].rsplit(" ", 1)[0] + "..."

        speech_id = self.begin_speech()
        sentences = split_sentences(spoken)

        from ai.tts import generate_speech

        # Синтез следующей фразы идёт параллельно с проговариванием текущей
        pending: asyncio.Task | None = None
        try:
            for index, sentence in enumerate(sentences):
                if not self._is_current(speech_id):
                    break

                audio = await (pending if pending else generate_speech(sentence))
                if index + 1 < len(sentences):
                    pending = asyncio.create_task(generate_speech(sentences[index + 1]))
                else:
                    pending = None

                if audio and self._is_current(speech_id):
                    await self.send_audio(audio, speech_id)
        except Exception as e:
            logger.error(f"Ошибка озвучки: {e}")
        finally:
            if pending:
                pending.cancel()

    async def speak_sentence(self, sentence: str, speech_id: int, emotion: str = "talking") -> None:
        """Озвучивает одно предложение из потока ответа.

        Используется, пока модель ещё договаривает: питомец начинает отвечать
        через секунду после вопроса, а не после полной генерации.
        """
        from core.settings import settings_store

        if not settings_store.get("speak_replies", True):
            return

        text = sanitize_for_speech(sentence)
        if not text or not self._is_current(speech_id):
            return

        async with self._sentence_lock:
            if not self._is_current(speech_id):
                return
            from ai.tts import generate_speech

            await self.emit("set_emotion", emotion=emotion, text=text[:60])
            audio = await generate_speech(text)
            if audio:
                await self.send_audio(audio, speech_id)

    async def cancel_speech(self) -> bool:
        """Оборвать речь: перестать слать чанки и очистить буфер на устройстве."""
        was_speaking = self._speaking
        self._speech_id += 1  # всё, что играло, перестаёт быть текущим
        await self.emit("stop_audio")
        await self._stop_pc_audio()
        if was_speaking:
            logger.info("Речь прервана")
        return was_speaking

    async def send_audio(self, pcm: bytes, speech_id: int | None = None) -> None:
        """Проигрывает речь: на питомце (Wi-Fi/USB), на колонках ПК или везде.

        Три адресата и у каждого своё правило:

        * Панели получают поток всегда — там осциллограф и отладка звука, и
          настройка «куда выводить голос» про динамики, а не про мониторинг.
        * Питомец — только при audio_output = device/both, и это должно
          работать на обоих транспортах. Раньше гейт по настройке стоял лишь
          на USB, а Wi-Fi шёл через broadcast_binary, который тогда включал
          устройство: в режиме «только колонки ПК» питомец всё равно говорил.
          После разделения панелей и устройства в ws_manager получилась
          обратная беда — по Wi-Fi звук питомцу не уходил вовсе.
        * Колонки ПК — при audio_output = pc/both, отдельной задачей.
        """
        if not pcm:
            return

        from core.settings import settings_store

        output = settings_store.get("audio_output", "both")
        to_device = output in ("device", "both")
        to_pc = output in ("pc", "both")

        if speech_id is None:
            speech_id = self._speech_id

        self._speaking = True
        pc_task = None
        try:
            if to_pc:
                from ai.tts import play_on_pc

                pc_task = asyncio.create_task(play_on_pc(pcm))

            for i in range(0, len(pcm), AUDIO_CHUNK_SIZE):
                if not self._is_current(speech_id):
                    break
                chunk = pcm[i : i + AUDIO_CHUNK_SIZE]
                await manager.broadcast_binary(chunk)
                if to_device:
                    # Транспорт выбираем на каждом чанке, а не один раз на
                    # реплику: если Wi-Fi отвалился посреди фразы, остаток
                    # договорим по USB. send_binary_to_device сам возвращает
                    # False, когда устройства на WebSocket нет.
                    sent = await manager.send_binary_to_device(chunk)
                    if not sent and serial_manager.is_connected:
                        # Запись в порт блокирующая: без отдельного потока
                        # event loop замирал на всё время передачи.
                        await asyncio.to_thread(serial_manager.send_binary, chunk)
                stats.track_tts(len(chunk))
                await asyncio.sleep(AUDIO_CHUNK_DELAY)

            if pc_task:
                if not self._is_current(speech_id):
                    pc_task.cancel()
                    await self._stop_pc_audio()
                else:
                    await pc_task
        finally:
            self._speaking = False
            # Даём устройству дослушать буфер, прежде чем снова слушать микрофон
            await asyncio.sleep(0.25)

    @staticmethod
    async def _stop_pc_audio() -> None:
        try:
            import winsound

            await asyncio.to_thread(winsound.PlaySound, None, winsound.SND_PURGE)
        except Exception:
            pass


bus = EventBus()
