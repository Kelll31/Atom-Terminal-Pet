"""Единое хранилище настроек Патрика.

Все модули (агент, инструменты, TTS, MCP) читают конфигурацию отсюда,
а не из разрозненных json-файлов. Файл лежит в каталоге данных (см. core.paths):
при запуске из исходников это backend/settings.json, в собранном приложении —
%LOCALAPPDATA%\\AtomTerminalPet\\settings.json. Секреты можно задать через
переменные окружения (они имеют приоритет только если в файле пусто).
"""

import json
import logging
import os
import threading
from typing import Any, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger("core.settings")

from core import paths

BACKEND_DIR = paths.DATA_ROOT
SETTINGS_FILE = paths.data("settings.json")

# Уровень автономии агента:
#   ask       — спрашивать подтверждение перед любым действием, меняющим систему
#   auto_safe — безопасные инструменты выполняются сразу, опасные требуют подтверждения
#   full      — выполнять всё без подтверждений (только для доверенной среды)
AutonomyLevel = Literal["ask", "auto_safe", "full"]


def _default_roots() -> list[str]:
    home = os.path.expanduser("~")
    roots = [os.path.join(home, "Documents"), os.path.join(home, "Desktop")]
    return [p for p in roots if os.path.isdir(p)]


class Settings(BaseModel):
    # ── LLM ────────────────────────────────────────────────────────────────
    api_key: str = ""
    base_url: str = ""
    model_name: str = "gpt-4o-mini"
    temperature: float = 0.4
    max_steps: int = 12  # максимум итераций "модель ↔ инструменты" на одну задачу

    # ── Личность питомца ───────────────────────────────────────────────────
    pet_name: str = "Патрик"
    # Варианты, которыми распознаватель обычно слышит кличку. Само имя из
    # pet_name добавляется к списку автоматически, а сравнение нечёткое,
    # так что «потрик» и «пат рик» тоже сработают.
    wake_words: list[str] = Field(
        default_factory=lambda: ["патрик", "patrick", "потрик", "пат рик", "патрык"]
    )
    require_wake_word: bool = True  # только для голоса; в чате не требуется
    speak_replies: bool = True  # озвучивать ответы через TTS
    # Куда выводить голос: динамик питомца, колонки ПК или туда и туда
    audio_output: Literal["device", "pc", "both"] = "both"
    max_speech_chars: int = 400  # длинные ответы не читаем целиком вслух

    # ── Голосовой режим ────────────────────────────────────────────────────
    voice_enabled: bool = True
    # Живой диалог: после ответа можно говорить дальше без обращения по имени
    live_mode: bool = True
    conversation_window_sec: int = 45

    # Детектор речи
    vad_min_level: float = 0.012      # абсолютный порог громкости (0..1)
    vad_sensitivity: float = 2.6      # во сколько раз речь громче фонового шума
    endpoint_silence_sec: float = 0.8  # пауза, после которой фраза считается законченной
    min_utterance_sec: float = 0.35    # короче — это не речь, а шум
    max_utterance_sec: float = 20.0

    # Перебивание
    barge_in: bool = True
    barge_in_level: float = 0.06
    barge_in_hold_sec: float = 0.25

    # Распознавание
    stt_engine: Literal["vosk", "whisper"] = "vosk"
    stt_model: str = "whisper-1"
    stt_base_url: str = ""
    stt_api_key: str = ""

    # ── Автономия и безопасность ───────────────────────────────────────────
    autonomy: AutonomyLevel = "auto_safe"
    approval_timeout_sec: int = 180
    allowed_roots: list[str] = Field(default_factory=_default_roots)
    disabled_tools: list[str] = Field(default_factory=list)
    blocked_commands: list[str] = Field(
        default_factory=lambda: [
            "format",
            "diskpart",
            "vssadmin",
            "bcdedit",
            "cipher /w",
            "rd /s /q c:\\",
            "rmdir /s /q c:\\",
            "del /f /s /q c:\\",
            "shutdown",
        ]
    )
    command_timeout_sec: int = 120

    # ── MCP ────────────────────────────────────────────────────────────────
    mcp_enabled: bool = True

    # ── Обновления ─────────────────────────────────────────────────────────
    auto_check_updates: bool = True
    # Пусто — релизы на GitHub. Иначе адрес latest.json со своей сборкой.
    update_url: str = ""
    # Открывать панель в собственном окне, а не во вкладке браузера
    panel_window: bool = True

    def public_dict(self) -> dict[str, Any]:
        """Настройки для web-панели: ключи маскируются."""
        data = self.model_dump()
        data["api_key_set"] = bool(self.api_key)
        if self.api_key:
            data["api_key"] = f"{self.api_key[:4]}...{self.api_key[-4:]}"
        data["stt_api_key_set"] = bool(self.stt_api_key)
        if self.stt_api_key:
            data["stt_api_key"] = f"{self.stt_api_key[:4]}...{self.stt_api_key[-4:]}"
        return data


class SettingsStore:
    def __init__(self, path: str = SETTINGS_FILE):
        self.path = path
        self._lock = threading.Lock()
        self._settings = self._load()

    # ── чтение/запись ──────────────────────────────────────────────────────
    def _load(self) -> Settings:
        data: dict[str, Any] = {}
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
            except Exception as e:
                logger.error(f"Не удалось прочитать {self.path}: {e}")
                data = {}

        # Секреты из окружения, если в файле пусто
        if not data.get("api_key"):
            env_key = os.getenv("ATOM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
            if env_key:
                data["api_key"] = env_key
        if not data.get("base_url") and os.getenv("ATOM_BASE_URL"):
            data["base_url"] = os.getenv("ATOM_BASE_URL", "")

        try:
            return Settings(**data)
        except Exception as e:
            logger.error(f"Некорректные настройки, применяю значения по умолчанию: {e}")
            return Settings()

    def save(self) -> None:
        with self._lock:
            tmp = f"{self.path}.tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(
                        self._settings.model_dump(), f, ensure_ascii=False, indent=2
                    )
                os.replace(tmp, self.path)
            except Exception as e:
                logger.error(f"Не удалось сохранить настройки: {e}")

    # ── API ────────────────────────────────────────────────────────────────
    @property
    def current(self) -> Settings:
        return self._settings

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self._settings, key, default)

    def update(self, patch: dict[str, Any]) -> Settings:
        """Частичное обновление. Пустые строки для api_key игнорируются,
        чтобы UI мог отправлять форму с замаскированным ключом."""
        clean = {k: v for k, v in patch.items() if v is not None}
        for secret in ("api_key", "stt_api_key"):
            value = clean.get(secret)
            if value in ("", None) or (isinstance(value, str) and "..." in value):
                clean.pop(secret, None)

        merged = self._settings.model_dump()
        merged.update(clean)
        self._settings = Settings(**merged)
        self.save()
        logger.info(f"Настройки обновлены: {sorted(clean.keys())}")
        return self._settings

    def reload(self) -> Settings:
        self._settings = self._load()
        return self._settings


settings_store = SettingsStore()
