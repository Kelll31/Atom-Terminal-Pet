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

        # 18 = 16kHz 16Bit Mono PCM (SAFT16kHz16BitMono)
        strm.Format.Type = 18
        spk.AudioOutputStream = strm

        spk.Speak(text)

        # Extract data
        data = strm.GetData()

        if isinstance(data, memoryview):
            raw_bytes = data.tobytes()
        else:
            raw_bytes = bytes(data)
            
        # Properly parse RIFF/WAV to find the 'data' chunk — header size varies (44–46+ bytes)
        if len(raw_bytes) > 12 and raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WAVE":
            offset = 12
            while offset + 8 <= len(raw_bytes):
                chunk_id = raw_bytes[offset:offset + 4]
                chunk_size = int.from_bytes(raw_bytes[offset + 4:offset + 8], "little")
                if chunk_id == b"data":
                    raw_bytes = raw_bytes[offset + 8:]
                    break
                offset += 8 + chunk_size

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
