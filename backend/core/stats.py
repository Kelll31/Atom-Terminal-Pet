"""Счётчики аудиопотока — чтобы «нет звука» диагностировалось за секунды,
а не гаданием: видно, идёт ли звук с микрофона и уходит ли речь на устройство."""

from __future__ import annotations

import struct
import time

audio_stats: dict[str, float | int | None] = {
    "mic_bytes": 0,
    "mic_chunks": 0,
    "mic_last_ts": 0.0,
    "mic_peak": 0,
    "tts_bytes": 0,
    "tts_chunks": 0,
    "tts_last_ts": 0.0,
}


def track_mic(audio_data: bytes) -> None:
    audio_stats["mic_bytes"] += len(audio_data)
    audio_stats["mic_chunks"] += 1
    audio_stats["mic_last_ts"] = time.time()

    samples = len(audio_data) // 2
    if not samples:
        return
    step = max(1, samples // 64)
    peak = 0
    for i in range(0, samples, step):
        value = abs(struct.unpack_from("<h", audio_data, i * 2)[0])
        if value > peak:
            peak = value
    audio_stats["mic_peak"] = peak


def track_tts(chunk_size: int) -> None:
    audio_stats["tts_bytes"] += chunk_size
    audio_stats["tts_chunks"] += 1
    audio_stats["tts_last_ts"] = time.time()


def snapshot() -> dict:
    now = time.time()
    mic_ts = audio_stats["mic_last_ts"] or 0
    tts_ts = audio_stats["tts_last_ts"] or 0
    return {
        **audio_stats,
        "mic_age_sec": round(now - mic_ts, 1) if mic_ts else None,
        "tts_age_sec": round(now - tts_ts, 1) if tts_ts else None,
    }
