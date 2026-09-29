"""Подключение к модели: облако и локальные серверы.

Локальный сервер (LM Studio, он же Bionic, Ollama, llama.cpp, Jan) говорит на том
же OpenAI-совместимом протоколе, что и облако, но отличается в трёх мелочах,
из-за которых подключение обычно и не получается с первого раза:

    ключа нет            — а клиент OpenAI требует непустую строку;
    адрес нужно угадать  — порт свой у каждой программы, и легко забыть «/v1»;
    модель грузится      — первый ответ может идти минуту, пока веса едут в память.

Здесь всё это собрано в одном месте: нормализация адреса, ключ-заглушка,
увеличенный таймаут, список моделей сервера и поиск уже запущенного сервера
по типовым портам. Агент и web-панель ходят к модели только через этот модуль.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

logger = logging.getLogger("ai.llm")

# Хосты, которые считаем «своей машиной»: ключ здесь не нужен и не имеет смысла
LOCAL_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "[::1]",
    "host.docker.internal",
}

# Клиент OpenAI не принимает пустой ключ, а локальный сервер его не проверяет
LOCAL_KEY_PLACEHOLDER = "local"

DEFAULT_MODEL = "gpt-4o-mini"

# Облачная модель отвечает быстро; локальная сначала грузит веса в память,
# и на большой модели первый ответ спокойно занимает несколько минут.
CLOUD_TIMEOUT_SEC = 90
LOCAL_TIMEOUT_SEC = 300

# Где обычно слушает локальный сервер. Порядок — по распространённости.
LOCAL_CANDIDATES: list[tuple[str, int]] = [
    ("LM Studio / Bionic", 1234),
    ("Ollama", 11434),
    ("llama.cpp / LocalAI", 8080),
    ("Jan", 1337),
    ("text-generation-webui", 5000),
    ("KoboldCpp", 5001),
]

# Схема-пустышка: на ней проверяем, умеет ли модель вызывать инструменты.
# Без этого умения питомец сможет только разговаривать, но не действовать.
PROBE_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "ping",
        "description": "Проверка поддержки инструментов. Вызови с text='ok'.",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "Любая строка"}},
            "required": ["text"],
        },
    },
}


def is_local(base_url: str | None) -> bool:
    """True, если адрес указывает на сервер, запущенный на этом же компьютере."""
    if not base_url:
        return False
    host = urlparse(_with_scheme(base_url)).hostname or ""
    return host.lower() in LOCAL_HOSTS


def normalize_base_url(base_url: str | None) -> str:
    """Приводит адрес к рабочему виду.

    Пользователь копирует адрес из окна LM Studio как «127.0.0.1:1234» —
    без схемы и без «/v1». И то и другое дописываем сами: ошибиться здесь
    легко, а диагностируется она невнятной ошибкой соединения.
    """
    if not base_url or not base_url.strip():
        return ""

    parsed = urlparse(_with_scheme(base_url.strip().rstrip("/")))
    path = parsed.path.rstrip("/")
    if not path and is_local(base_url):
        path = "/v1"
    return urlunparse(parsed._replace(path=path, params="", query="", fragment=""))


def api_root(base_url: str) -> str:
    """Origin адреса: «http://127.0.0.1:1234» из «http://127.0.0.1:1234/v1».

    Нужен для фирменного REST LM Studio — он живёт вне «/v1».
    """
    parsed = urlparse(_with_scheme(base_url))
    return f"{parsed.scheme}://{parsed.netloc}"


def effective_key(api_key: str | None, base_url: str | None) -> str:
    """Ключ, который уйдёт серверу.

    Для локального сервера ключ не требуется, поэтому подставляем заглушку —
    и заодно не отправляем облачный ключ пользователя постороннему процессу.
    """
    if is_local(base_url):
        return LOCAL_KEY_PLACEHOLDER
    return (api_key or "").strip()


def needs_api_key(api_key: str | None, base_url: str | None) -> bool:
    """True, если работать не с чем: облако выбрано, а ключа нет."""
    return not is_local(base_url) and not (api_key or "").strip()


def build_chat_model(
    *,
    api_key: str | None,
    base_url: str | None,
    model: str | None,
    temperature: float | None = None,
    timeout: float | None = None,
    max_retries: int | None = None,
):
    """Собирает клиент модели. Единая точка для агента, теста связи и панели."""
    from langchain_openai import ChatOpenAI

    url = normalize_base_url(base_url)
    local = is_local(url)

    headers: dict[str, str] = {}
    if url and "openrouter.ai" in url.lower():
        headers = {"HTTP-Referer": "http://localhost:8000", "X-Title": "Atom-Terminal-Pet"}

    kwargs: dict[str, Any] = {
        "api_key": effective_key(api_key, url),
        "base_url": url or None,
        "model": (model or "").strip() or DEFAULT_MODEL,
        "timeout": timeout if timeout is not None else (LOCAL_TIMEOUT_SEC if local else CLOUD_TIMEOUT_SEC),
        # Локальный сервер обслуживает запросы по одному: повтор не ускорит
        # ответ, а поставит в очередь ещё одну генерацию.
        "max_retries": max_retries if max_retries is not None else (0 if local else 2),
        "default_headers": headers,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature

    return ChatOpenAI(**kwargs)


async def fetch_models(base_url: str | None, api_key: str | None = "") -> list[dict[str, Any]]:
    """Список моделей сервера.

    Сначала спрашиваем фирменный REST LM Studio/Bionic: он говорит, что модель
    умеет (llm или embeddings) и загружена ли она сейчас. Если такого API нет —
    берём обычный OpenAI-совместимый «/models», где известен только id.
    """
    url = normalize_base_url(base_url)
    if not url:
        url = "https://api.openai.com/v1"

    headers = {}
    key = effective_key(api_key, url)
    if key:
        headers["Authorization"] = f"Bearer {key}"

    async with httpx.AsyncClient(timeout=10) as client:
        if is_local(url):
            models = await _lmstudio_models(client, url, headers)
            if models:
                return models

        response = await client.get(f"{url.rstrip('/')}/models", headers=headers)
        response.raise_for_status()
        payload = response.json()

    return [_model_entry(item) for item in payload.get("data", []) if isinstance(item, dict)]


async def discover_local(timeout: float = 1.0) -> list[dict[str, Any]]:
    """Обходит типовые порты и возвращает найденные локальные серверы."""

    async def probe(name: str, port: int) -> dict[str, Any] | None:
        url = f"http://127.0.0.1:{port}/v1"
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(f"{url}/models")
                if response.status_code >= 400:
                    return None
                data = response.json()
                if not isinstance(data, dict) or "data" not in data:
                    return None
                models = await _lmstudio_models(client, url, {}) or [
                    _model_entry(item) for item in data.get("data", []) if isinstance(item, dict)
                ]
        except Exception:  # noqa: BLE001 — порт закрыт или отвечает не тот сервис
            return None
        return {"name": name, "base_url": url, "models": models}

    results = await asyncio.gather(*(probe(name, port) for name, port in LOCAL_CANDIDATES))
    return [item for item in results if item]


def chat_models(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Отсеивает эмбеддинги: разговаривать с ними нельзя, а в списке они мешают."""
    return [m for m in models if m.get("type") != "embeddings"]


# ── внутреннее ─────────────────────────────────────────────────────────────
def _with_scheme(url: str) -> str:
    return url if "://" in url else f"http://{url}"


async def _lmstudio_models(
    client: httpx.AsyncClient, base_url: str, headers: dict[str, str]
) -> list[dict[str, Any]]:
    """Фирменный REST LM Studio/Bionic: тип модели, состояние, длина контекста."""
    try:
        response = await client.get(f"{api_root(base_url)}/api/v0/models", headers=headers)
        if response.status_code >= 400:
            return []
        payload = response.json()
    except Exception as e:  # noqa: BLE001 — обычный сервер такого API не знает
        logger.debug(f"LM Studio REST недоступен на {base_url}: {e}")
        return []

    return [_model_entry(item) for item in payload.get("data", []) if isinstance(item, dict)]


def _model_entry(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id", ""),
        "type": item.get("type") or _guess_type(item.get("id", "")),
        "state": item.get("state", ""),
        "context": item.get("max_context_length"),
    }


def _guess_type(model_id: str) -> str:
    """Без фирменного REST тип угадываем по имени — иначе он неизвестен."""
    lowered = model_id.lower()
    if "embed" in lowered or lowered.startswith("text-embedding"):
        return "embeddings"
    return "llm"
