import logging
import os
import urllib.request
import zipfile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vosk_downloader")

MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")
MODEL_PATH = os.path.join(MODEL_DIR, "vosk-model-small-ru-0.22")


def download_and_extract_model():
    if not os.path.exists(MODEL_DIR):
        os.makedirs(MODEL_DIR)

    if os.path.exists(MODEL_PATH):
        logger.info(f"Model already exists at {MODEL_PATH}")
        return True

    zip_path = os.path.join(MODEL_DIR, "vosk_model.zip")

    logger.info(f"Downloading Vosk model from {MODEL_URL}...")
    try:
        urllib.request.urlretrieve(MODEL_URL, zip_path)

        logger.info("Extracting model...")
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(MODEL_DIR)

        logger.info("Cleaning up...")
        os.remove(zip_path)
        logger.info("Model downloaded and extracted successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed to download or extract model: {e}")
        if os.path.exists(zip_path):
            os.remove(zip_path)
        return False


if __name__ == "__main__":
    download_and_extract_model()
