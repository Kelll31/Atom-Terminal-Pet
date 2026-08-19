import asyncio
import logging

import pythoncom
import win32com.client

logger = logging.getLogger("ai.tts")


def process_tts_sync(text: str) -> bytes:
    try:
        # COM objects must be initialized per-thread
        pythoncom.CoInitialize()

        spk = win32com.client.Dispatch("SAPI.SpVoice")
        strm = win32com.client.Dispatch("SAPI.SpMemoryStream")

        # 30 = 16kHz 16Bit Mono PCM
        strm.Format.Type = 30
        spk.AudioOutputStream = strm

        spk.Speak(text)

        # Extract data
        data = strm.GetData()

        if isinstance(data, memoryview):
            raw_bytes = data.tobytes()
        else:
            raw_bytes = bytes(data)
            
        # Strip the 44-byte RIFF WAV header if present so it's pure PCM
        if len(raw_bytes) > 44 and raw_bytes[:4] == b"RIFF":
            raw_bytes = raw_bytes[44:]

        pythoncom.CoUninitialize()
        return raw_bytes
    except Exception as e:
        logger.error(f"Error in SAPI TTS: {e}")
        return b""


async def generate_speech(text: str) -> bytes:
    """
    Generate speech from text using Windows offline TTS (SAPI5).
    Returns 16kHz 16-bit Mono PCM raw bytes for the ESP32.
    """
    logger.info(f"Generating speech for text: {text}")

    if not text:
        return b""

    pcm_bytes = await asyncio.to_thread(process_tts_sync, text)

    logger.info(f"Successfully generated {len(pcm_bytes)} bytes of PCM audio data.")
    return pcm_bytes
