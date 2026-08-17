import logging
import asyncio

logger = logging.getLogger("ai.stt")

# In a real scenario, you'd use something like Faster-Whisper, OpenAI API, etc.
# For fully async behavior with heavy local models, use asyncio.to_thread()

async def transcribe_audio(audio_data: bytes) -> str:
    """
    Mock function to transcribe binary audio data into text.
    In reality, this would save the bytes to a temp file or memory buffer 
    and pass to a Whisper model.
    """
    logger.info(f"Transcribing {len(audio_data)} bytes of audio...")
    
    # Simulate network/processing delay
    await asyncio.sleep(0.5)
    
    # Mock result
    logger.info("STT Mock Result: 'Что у меня с загрузкой процессора?'")
    return "Что у меня с загрузкой процессора?"
