"""Единая шина событий: web-панель, устройство M5 и озвучка.

Модули не работают с WebSocket/Serial напрямую — они вызывают bus.emit(...),
а шина сама решает, куда доставить сообщение:
  * все JSON-события уходят web-клиентам;
  * подмножество событий (эмоции, метрики, речь) уходит питомцу — по Wi-Fi,
    если он на WebSocket, иначе по USB-Serial;
  * аудио TTS передаётся чанками с паузами под скорость воспроизведения I2S.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from core import stats
from core.serial_manager import serial_manager
from core.ws_manager import manager

logger = logging.getLogger("core.events")

# Что понимает прошивка питомца — остальное ей слать бессмысленно.
DEVICE_ACTIONS = {"speak", "set_emotion", "update_pc", "pomodoro", "set_rotation"}

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


def sanitize_for_speech(text: str) -> str:
    """Готовит текст для синтезатора: без разметки, ссылок, эмодзи и длинных путей."""
    clean = _CODE_BLOCK.sub(" фрагмент кода, смотри панель, ", text)
    clean = _URL.sub("ссылка", clean)
    clean = _PATH.sub("путь", clean)
    clean = _MARKDOWN.sub("", clean)
    clean = _EMOJI.sub("", clean)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


class EventBus:
    def __init__(self) -> None:
        self._speaking = False

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    # ── базовая отправка ───────────────────────────────────────────────────
    async def emit(self, action: str, **payload: Any) -> None:
        """Событие для web-панели (и для питомца, если он его понимает)."""
        message = {"action": action, **payload}
        await manager.broadcast_json(message)
        if action in DEVICE_ACTIONS and not manager.device_on_wifi:
            serial_manager.send_json(message)

    async def emit_raw(self, message: dict[str, Any]) -> None:
        await self.emit(message.get("action", "unknown"), **{k: v for k, v in message.items() if k != "action"})

    async def set_emotion(self, emotion: str, text: str = "") -> None:
        await self.emit("set_emotion", emotion=emotion, text=text)

    # ── речь ───────────────────────────────────────────────────────────────
    async def speak(self, text: str, emotion: str = "happy", voice: bool = True) -> None:
        """Показывает реплику везде и (при voice=True) озвучивает её."""
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

        try:
            from ai.tts import generate_speech

            audio = await generate_speech(spoken)
        except Exception as e:
            logger.error(f"TTS недоступен: {e}")
            return

        if audio:
            await self.send_audio(audio)

    async def send_audio(self, pcm: bytes) -> None:
        """Проигрывает речь: на питомце (Wi-Fi/USB), на колонках ПК или везде."""
        if not pcm:
            return

        from core.settings import settings_store

        output = settings_store.get("audio_output", "both")
        to_device = output in ("device", "both")
        to_pc = output in ("pc", "both")
        to_serial = to_device and not manager.device_on_wifi and serial_manager.is_connected

        self._speaking = True
        logger.info(
            f"Речь {len(pcm)} байт → "
            f"{'Wi-Fi' if to_device and manager.device_on_wifi else 'USB' if to_serial else 'питомец недоступен'}"
            f"{' + колонки ПК' if to_pc else ''}"
        )

        pc_task = None
        try:
            if to_pc:
                from ai.tts import play_on_pc

                # Колонки ПК играют параллельно с передачей на устройство
                pc_task = asyncio.create_task(play_on_pc(pcm))

            for i in range(0, len(pcm), AUDIO_CHUNK_SIZE):
                chunk = pcm[i : i + AUDIO_CHUNK_SIZE]
                await manager.broadcast_binary(chunk)
                if to_serial:
                    # Запись в порт блокирующая: без отдельного потока
                    # event loop замирал на всё время передачи.
                    await asyncio.to_thread(serial_manager.send_binary, chunk)
                stats.track_tts(len(chunk))
                await asyncio.sleep(AUDIO_CHUNK_DELAY)

            if pc_task:
                await pc_task
        finally:
            self._speaking = False
            # Даём устройству дослушать буфер, прежде чем снова слушать микрофон
            await asyncio.sleep(0.4)


bus = EventBus()
