"""Синтез речи (Windows SAPI5, офлайн) и воспроизведение.

Речь генерируется один раз в виде PCM 16 кГц / 16 бит / моно — в таком виде
её понимает и ESP32 (I2S), и звуковая карта ПК (через WAV-обёртку).
"""

import asyncio
import io
import logging
import struct
import wave

logger = logging.getLogger("ai.tts")


def _extract_pcm(raw_bytes: bytes) -> bytes:
    """SAPI отдаёт RIFF/WAV — вырезаем чанк data (заголовок бывает разной длины)."""
    if len(raw_bytes) > 12 and raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WAVE":
        offset = 12
        while offset + 8 <= len(raw_bytes):
            chunk_id = raw_bytes[offset : offset + 4]
            chunk_size = int.from_bytes(raw_bytes[offset + 4 : offset + 8], "little")
            if chunk_id == b"data":
                return raw_bytes[offset + 8 : offset + 8 + chunk_size] or raw_bytes[offset + 8 :]
            offset += 8 + chunk_size
    return raw_bytes


def process_tts_sync(text: str) -> bytes:
    try:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            stream = win32com.client.Dispatch("SAPI.SpMemoryStream")
            stream.Format.Type = 18  # SAFT16kHz16BitMono
            speaker.AudioOutputStream = stream
            speaker.Speak(text)

            data = stream.GetData()
            raw_bytes = data.tobytes() if isinstance(data, memoryview) else bytes(data)
            return _extract_pcm(raw_bytes)
        finally:
            pythoncom.CoUninitialize()
    except Exception as e:
        logger.error(f"Ошибка синтеза речи SAPI: {e}")
        return b""


async def generate_speech(text: str) -> bytes:
    """Возвращает PCM 16 кГц / 16 бит / моно для ESP32 и колонок ПК."""
    if not text:
        return b""

    logger.info(f"Синтезирую речь: {text[:80]}")
    pcm_bytes = await asyncio.to_thread(process_tts_sync, text)
    logger.info(f"Готово: {len(pcm_bytes)} байт PCM")
    return pcm_bytes


def pcm_to_wav(pcm: bytes, sample_rate: int = 16000) -> bytes:
    """Оборачивает сырой PCM в WAV — так его принимает звуковая подсистема Windows."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


def _play_on_pc_sync(pcm: bytes) -> bool:
    try:
        import winsound

        winsound.PlaySound(pcm_to_wav(pcm), winsound.SND_MEMORY)
        return True
    except Exception as e:
        logger.error(f"Не удалось воспроизвести звук на ПК: {e}")
        return False


async def play_on_pc(pcm: bytes) -> bool:
    """Проигрывает речь на колонках компьютера (без внешних зависимостей)."""
    if not pcm:
        return False
    return await asyncio.to_thread(_play_on_pc_sync, pcm)


def peak_level(pcm: bytes) -> int:
    """Пиковая амплитуда — для индикаторов в панели."""
    samples = len(pcm) // 2
    if not samples:
        return 0
    step = max(1, samples // 128)
    return max(
        abs(struct.unpack_from("<h", pcm, i * 2)[0]) for i in range(0, samples, step)
    )
