import asyncio
import json
import logging
import os

logger = logging.getLogger("ai.stt")

recognizer = None


def init_vosk():
    global recognizer
    if recognizer is not None:
        return

    try:
        from vosk import KaldiRecognizer, Model

        # Adjust path to model dir
        model_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "models",
            "vosk-model-small-ru-0.22",
        )

        if not os.path.exists(model_dir):
            logger.warning(
                f"Vosk model not found at {model_dir}. Please run download_vosk_model.py"
            )
            return

        logger.info(f"Loading Vosk model from {model_dir}...")
        model = Model(model_dir)
        # ESP32 usually sends 16kHz audio
        recognizer = KaldiRecognizer(model, 16000)
        logger.info("Vosk model loaded successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Vosk: {e}")


def process_audio_sync(audio_data: bytes) -> tuple[bool, str]:
    global recognizer
    if recognizer is None:
        init_vosk()

    if recognizer is None:
        return False, ""

    # We receive chunks of audio buffer from ESP32.
    if recognizer.AcceptWaveform(audio_data):
        res = json.loads(recognizer.Result())
        text = res.get("text", "")
        return True, text
    else:
        # Utterance not finished yet, get partial
        partial_res = json.loads(recognizer.PartialResult())
        text = partial_res.get("partial", "")
        return False, text


async def transcribe_audio_stream(audio_data: bytes) -> tuple[bool, str]:
    """
    Transcribe streaming binary audio data.
    Returns (is_complete, text).
    """
    if len(audio_data) == 0:
        return False, ""

    # Run CPU-bound STT task in a thread
    is_complete, text = await asyncio.to_thread(process_audio_sync, audio_data)

    if is_complete and text:
        logger.info(f"STT Result: '{text}'")

    return is_complete, text
