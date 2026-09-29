"""Голосовой конвейер «живого» режима.

Что здесь происходит с каждым куском звука с микрофона:

    чанк → уровень громкости → детектор речи (VAD) → накопление фразы
         → промежуточный текст в панель → пауза → распознавание фразы целиком
         → решение: это обращение к питомцу? продолжение диалога? команда «стоп»?

Отличия от прошлой версии, из-за которых голос работал плохо:
  * речь резалась по кускам 512 байт и распознавалась «на лету» — теперь фраза
    собирается целиком и распознаётся одним куском (точность заметно выше);
  * тишина и шум тоже уходили в распознаватель — теперь их отсекает VAD
    с адаптивным порогом под конкретную комнату;
  * после ответа снова требовалось звать по имени — теперь есть окно живого
    диалога, внутри которого можно говорить свободно;
  * питомца нельзя было перебить — теперь есть barge-in по голосу, стоп-словам,
    кнопке на устройстве и кнопке в панели.
"""

from __future__ import annotations

import asyncio
import logging
import math
import struct
import time
from collections import deque
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from core.settings import settings_store

logger = logging.getLogger("ai.voice")

SAMPLE_RATE = 16000
BYTES_PER_SEC = SAMPLE_RATE * 2

# Стоп-слова: произносятся, когда питомца хотят прервать
STOP_WORDS = {
    "стоп", "хватит", "замолчи", "молчи", "отмена", "отменить",
    "стой", "тихо", "прекрати", "заткнись",
}


def rms_level(pcm: bytes) -> float:
    """Средняя громкость куска, 0..1."""
    samples = len(pcm) // 2
    if samples == 0:
        return 0.0
    step = max(1, samples // 256)
    total = 0.0
    count = 0
    for i in range(0, samples, step):
        value = struct.unpack_from("<h", pcm, i * 2)[0]
        total += value * value
        count += 1
    if count == 0:
        return 0.0
    return min(1.0, math.sqrt(total / count) / 32768.0)


def normalize(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text.lower()).strip()


def matches_wake_word(text: str, wake_words: list[str], threshold: float = 0.72) -> bool:
    """Нечёткое сравнение: ловит «а том», «атам», «адом» и прочие оговорки Vosk."""
    words = normalize(text).split()
    if not words:
        return False

    candidates = list(words)
    candidates += [f"{a}{b}" for a, b in zip(words, words[1:])]  # склеенные пары

    for wake in wake_words:
        wake = wake.strip().lower().replace(" ", "")
        if not wake:
            continue
        for candidate in candidates:
            if candidate == wake or wake in candidate:
                return True
            if SequenceMatcher(None, candidate, wake).ratio() >= threshold:
                return True
    return False


def contains_stop_word(text: str) -> bool:
    words = set(normalize(text).split())
    return bool(words & STOP_WORDS)


@dataclass
class VoiceState:
    speaking: bool = False              # человек сейчас говорит
    level: float = 0.0                  # текущая громкость 0..1
    noise_floor: float = 0.004          # оценка фонового шума
    conversation_until: float = 0.0     # до какого момента открыт живой диалог
    last_partial: str = ""
    utterances: int = 0

    def dict(self) -> dict:
        remaining = max(0.0, self.conversation_until - time.time())
        return {
            "speaking": self.speaking,
            "level": round(self.level, 4),
            "noise_floor": round(self.noise_floor, 4),
            "conversation_open": remaining > 0,
            "conversation_left": round(remaining, 1),
            "utterances": self.utterances,
        }


class VoicePipeline:
    """Собирает фразы из потока и решает, что с ними делать."""

    def __init__(self) -> None:
        self.state = VoiceState()
        self._buffer = bytearray()                  # накопленная фраза
        self._preroll: deque[bytes] = deque(maxlen=8)  # ~0.25 с до начала речи

        # Время считаем по количеству обработанного звука, а не по часам:
        # устройство отдаёт аудио пачками, и на настенных часах пауза между
        # словами выглядела нулевой — фраза никогда не заканчивалась.
        self._clock = 0.0
        self._speech_started = 0.0
        self._last_voice_at = 0.0
        self._loud_since = 0.0                      # для перебивания во время речи
        self._lock = asyncio.Lock()

    # ── настройки ──────────────────────────────────────────────────────────
    @property
    def cfg(self):
        return settings_store.current

    def open_conversation(self, seconds: float | None = None) -> None:
        """Открыть окно живого диалога — после ответа питомца или вручную."""
        window = seconds if seconds is not None else self.cfg.conversation_window_sec
        self.state.conversation_until = time.time() + window

    def close_conversation(self) -> None:
        self.state.conversation_until = 0.0

    @property
    def conversation_open(self) -> bool:
        return time.time() < self.state.conversation_until

    def reset(self) -> None:
        self._buffer.clear()
        self._preroll.clear()
        self.state.speaking = False
        self._speech_started = 0.0
        self._loud_since = 0.0

    # ── основной вход ──────────────────────────────────────────────────────
    async def feed(self, pcm: bytes) -> None:
        if not pcm:
            return

        from core.events import bus

        cfg = self.cfg
        if not cfg.voice_enabled:
            return

        level = rms_level(pcm)
        self.state.level = level
        self._clock += len(pcm) / BYTES_PER_SEC
        now = self._clock

        # Пока питомец говорит — слушаем только на предмет «меня перебивают»
        if bus.is_speaking:
            await self._maybe_barge_in(level, now)
            return

        # Адаптивный порог: тихие куски обновляют оценку шума комнаты
        threshold = max(cfg.vad_min_level, self.state.noise_floor * cfg.vad_sensitivity)
        is_voice = level > threshold

        if not is_voice:
            self.state.noise_floor = self.state.noise_floor * 0.97 + level * 0.03

        if not self.state.speaking:
            self._preroll.append(pcm)
            if is_voice:
                # Начало фразы: берём предзапись, чтобы не срезать первый слог
                self.state.speaking = True
                self._speech_started = now
                self._last_voice_at = now
                self._buffer = bytearray(b"".join(self._preroll))
                self._preroll.clear()
                await bus.emit("voice_state", **self.state.dict(), event="speech_start")
            return

        # Идёт фраза
        self._buffer.extend(pcm)
        if is_voice:
            self._last_voice_at = now

        # Промежуточный текст — чтобы в панели было видно, что услышано
        if len(self._buffer) % (BYTES_PER_SEC // 4) < len(pcm):
            from ai.stt import transcribe_partial

            partial = await transcribe_partial(bytes(pcm))
            if partial and partial != self.state.last_partial:
                self.state.last_partial = partial
                await bus.emit("user_speech_partial", text=partial)

        silence = now - self._last_voice_at
        duration = now - self._speech_started
        too_long = duration > cfg.max_utterance_sec

        if silence >= cfg.endpoint_silence_sec or too_long:
            utterance = bytes(self._buffer)
            self.reset()
            await bus.emit("voice_state", **self.state.dict(), event="speech_end")
            asyncio.create_task(self._finish_utterance(utterance, duration))

    async def _maybe_barge_in(self, level: float, now: float) -> None:
        """Пытаемся понять, что человек заговорил поверх речи питомца."""
        cfg = self.cfg
        if not cfg.barge_in:
            return

        # Когда голос идёт в динамик самого питомца, микрофон слышит прежде всего
        # его самого — по звуку перебить нельзя, для этого есть кнопка и панель.
        from core.ws_manager import manager

        if cfg.audio_output in ("device", "both") and manager.device_info.get("connected"):
            return

        loud = level > max(cfg.barge_in_level, self.state.noise_floor * 6)
        if not loud:
            self._loud_since = 0.0
            return

        if self._loud_since == 0.0:
            self._loud_since = now
        elif now - self._loud_since >= cfg.barge_in_hold_sec:
            self._loud_since = 0.0
            await self.interrupt("voice")

    async def interrupt(self, reason: str = "user") -> bool:
        """Прервать питомца: замолчать и вернуться в режим слушания."""
        from core.events import bus
        from tasks.task_manager import task_manager

        stopped = await bus.cancel_speech()
        cancelled = await task_manager.cancel_current()
        self.open_conversation()
        self.reset()

        await bus.emit("voice_interrupted", reason=reason, stopped=stopped, cancelled=cancelled)
        logger.info(f"Питомца перебили ({reason})")
        return stopped or cancelled

    # ── обработка готовой фразы ────────────────────────────────────────────
    async def _finish_utterance(self, pcm: bytes, duration: float) -> None:
        from ai.stt import reset_partial, transcribe_utterance
        from core.events import bus
        from tasks.task_manager import task_manager

        async with self._lock:
            reset_partial()
            cfg = self.cfg

            if duration < cfg.min_utterance_sec:
                return  # хлопок двери, кашель, щелчок мыши

            text = await transcribe_utterance(pcm)
            if not text or len(text) < 2:
                return

            self.state.utterances += 1
            self.state.last_partial = ""
            await bus.emit("user_speech", text=text)

            # «Стоп» в любой момент — просто замолчать
            if contains_stop_word(text) and len(normalize(text).split()) <= 3:
                await self.interrupt("stop_word")
                return

            named = matches_wake_word(text, cfg.wake_words + [cfg.pet_name])
            live = cfg.live_mode and self.conversation_open

            if not (named or live or not cfg.require_wake_word):
                logger.info(f"Пропускаю (не ко мне): {text}")
                await bus.emit("voice_ignored", text=text)
                return

            # Убираем обращение из начала фразы: «Патрик, открой проект» → «открой проект»
            cleaned = self._strip_wake_word(text, cfg.wake_words + [cfg.pet_name]) if named else text
            if len(cleaned.split()) == 0:
                # Позвали по имени и всё — отзовёмся и откроем диалог
                self.open_conversation()
                await bus.speak("На связи. Слушаю.", emotion="happy")
                return

            self.open_conversation()
            await bus.emit("beep")  # короткий отклик: «услышал, работаю»
            await task_manager.submit(cleaned, source="voice")

    @staticmethod
    def _strip_wake_word(text: str, wake_words: list[str]) -> str:
        """Убирает обращение из начала фразы.

        Распознаватель часто разбивает имя на два слова («а том», «а там»),
        поэтому пробуем снять и одно слово, и склеенную пару.
        """
        cleaned_words = [w.lower().replace(" ", "") for w in wake_words if w.strip()]

        def is_name(token: str) -> bool:
            token = normalize(token).replace(" ", "")
            if not token:
                return False
            # Длина должна быть сопоставима с именем, иначе «Патрикоткрой»
            # тоже сойдёт за обращение и съест первое слово команды.
            return any(
                abs(len(token) - len(wake)) <= 2
                and SequenceMatcher(None, token, wake).ratio() >= 0.75
                for wake in cleaned_words
            )

        words = text.split()
        changed = True
        while changed and words:
            changed = False
            if len(words) >= 2 and is_name(words[0] + words[1]):
                words = words[2:]
                changed = True
            elif is_name(words[0]):
                words = words[1:]
                changed = True

        cleaned = " ".join(words).lstrip(" ,.!?—-").strip()
        return cleaned or text


voice_pipeline = VoicePipeline()
