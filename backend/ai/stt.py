"""Распознавание речи.

Два движка:
  * vosk    — офлайн, работает без интернета и ключей (по умолчанию);
  * whisper — через любой OpenAI-совместимый API, заметно точнее на длинных фразах.

Ключевая идея: распознаём не «поток вообще», а готовые высказывания, которые
нарезал VAD (см. ai/voice.py). Для одной фразы создаётся свежий распознаватель —
так он не тащит контекст предыдущей реплики и не выдаёт слипшийся текст.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

logger = logging.getLogger("ai.stt")

from core import paths

# Штатная модель едет в поставке, но пользователь может положить свою
# в каталог данных — тогда возьмётся она.
MODEL_DIR = paths.model_dir("vosk-model-small-ru-0.22")

SAMPLE_RATE = 16000

_model = None           # общая модель Vosk (грузится один раз, ~40 МБ)
_stream_recognizer = None  # распознаватель для промежуточных результатов


def _load_model():
    global _model
    if _model is not None:
        return _model

    try:
        from vosk import Model, SetLogLevel

        if not os.path.exists(MODEL_DIR):
            logger.warning(
                f"Модель Vosk не найдена: {MODEL_DIR}. "
                "Запустите backend/scripts/download_vosk_model.py"
            )
            return None

        SetLogLevel(-1)  # без простыни логов Kaldi в консоли
        logger.info("Загружаю модель Vosk…")
        _model = Model(MODEL_DIR)
        logger.info("Модель Vosk готова")
    except Exception as e:
        logger.error(f"Не удалось загрузить Vosk: {e}")
        _model = None
    return _model


def is_ready() -> bool:
    return _load_model() is not None


def _new_recognizer():
    from vosk import KaldiRecognizer

    model = _load_model()
    if model is None:
        return None
    recognizer = KaldiRecognizer(model, SAMPLE_RATE)
    recognizer.SetWords(False)
    return recognizer


# ── Промежуточный текст (пока человек говорит) ─────────────────────────────
def reset_partial() -> None:
    """Сбрасываем распознаватель между фразами."""
    global _stream_recognizer
    _stream_recognizer = None


def _partial_sync(chunk: bytes) -> str:
    global _stream_recognizer
    if _stream_recognizer is None:
        _stream_recognizer = _new_recognizer()
    if _stream_recognizer is None:
        return ""

    try:
        if _stream_recognizer.AcceptWaveform(chunk):
            return json.loads(_stream_recognizer.Result()).get("text", "")
        return json.loads(_stream_recognizer.PartialResult()).get("partial", "")
    except Exception as e:
        logger.debug(f"Ошибка промежуточного распознавания: {e}")
        return ""


async def transcribe_partial(chunk: bytes) -> str:
    if not chunk:
        return ""
    return await asyncio.to_thread(_partial_sync, chunk)


# ── Финальный текст (целое высказывание) ───────────────────────────────────
def _vosk_final_sync(pcm: bytes) -> str:
    recognizer = _new_recognizer()
    if recognizer is None:
        return ""

    try:
        # Скармливаем фразу целиком: так модель видит весь контекст,
        # а не обрывки по 512 байт, и ошибается заметно реже.
        step = SAMPLE_RATE * 2  # по секунде
        for i in range(0, len(pcm), step):
            recognizer.AcceptWaveform(pcm[i : i + step])
        result = json.loads(recognizer.FinalResult())
        return (result.get("text") or "").strip()
    except Exception as e:
        logger.error(f"Ошибка распознавания Vosk: {e}")
        return ""


async def _whisper_final(pcm: bytes) -> str:
    """Распознавание через OpenAI-совместимый /audio/transcriptions."""
    from core.settings import settings_store

    settings = settings_store.current
    api_key = settings.stt_api_key or settings.api_key
    base_url = (settings.stt_base_url or "https://api.openai.com/v1").rstrip("/")
    if not api_key:
        logger.warning("Для whisper нужен ключ — откатываюсь на Vosk")
        return await asyncio.to_thread(_vosk_final_sync, pcm)

    from ai.tts import pcm_to_wav

    try:
        import httpx

        files = {"file": ("speech.wav", pcm_to_wav(pcm), "audio/wav")}
        data = {"model": settings.stt_model or "whisper-1", "language": "ru"}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files=files,
                data=data,
            )
            response.raise_for_status()
            return (response.json().get("text") or "").strip()
    except Exception as e:
        logger.error(f"Whisper недоступен ({e}), использую Vosk")
        return await asyncio.to_thread(_vosk_final_sync, pcm)


async def transcribe_utterance(pcm: bytes) -> str:
    """Распознаёт целую фразу, нарезанную детектором речи."""
    if len(pcm) < SAMPLE_RATE // 4:  # короче 0.25 с — это не речь
        return ""

    from core.settings import settings_store

    engine = settings_store.get("stt_engine", "vosk")
    if engine == "whisper":
        text = await _whisper_final(pcm)
    else:
        text = await asyncio.to_thread(_vosk_final_sync, pcm)

    if text:
        logger.info(f"Распознано ({engine}): {text}")
    return text


# ── Совместимость со старым потоковым интерфейсом ──────────────────────────
async def transcribe_audio_stream(audio_data: bytes) -> tuple[bool, str]:
    """Старый API (chunk -> (готово, текст)). Оставлен для тестов и отладки."""
    text = await transcribe_partial(audio_data)
    return False, text
