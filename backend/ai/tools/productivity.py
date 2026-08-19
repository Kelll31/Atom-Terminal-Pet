"""Инструменты «жизни рядом с программистом»: напоминания, помодоро,
долговременная память и выражение эмоций на экране питомца."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta

from pydantic import BaseModel, Field

from ai.tools.base import ToolError, registry

logger = logging.getLogger("ai.tools.productivity")

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BACKEND_DIR, "data")
NOTES_FILE = os.path.join(DATA_DIR, "notes.json")
REMINDERS_FILE = os.path.join(DATA_DIR, "reminders.json")

EMOTIONS = {
    "idle", "happy", "angry", "sad", "love", "dizzy", "sleepy",
    "working", "listening", "talking", "thinking", "panic", "sweat", "party",
}


def _read_json(path: str, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Не удалось прочитать {path}: {e}")
    return default


def _write_json(path: str, data) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Не удалось записать {path}: {e}")


# ── Напоминания ────────────────────────────────────────────────────────────
_reminder_tasks: dict[str, asyncio.Task] = {}


async def _fire_reminder(reminder: dict) -> None:
    delay = reminder["due_ts"] - time.time()
    if delay > 0:
        await asyncio.sleep(delay)

    from core.events import bus

    await bus.speak(f"Напоминание: {reminder['message']}", emotion="party")

    items = [r for r in _read_json(REMINDERS_FILE, []) if r["id"] != reminder["id"]]
    _write_json(REMINDERS_FILE, items)
    _reminder_tasks.pop(reminder["id"], None)
    await bus.emit("reminders_update", reminders=items)


def schedule_pending_reminders() -> int:
    """Вызывается при старте сервера — восстанавливает напоминания после перезапуска."""
    items = _read_json(REMINDERS_FILE, [])
    alive = []
    for reminder in items:
        if reminder.get("due_ts", 0) <= time.time():
            continue  # просроченное — просто убираем
        alive.append(reminder)
        _reminder_tasks[reminder["id"]] = asyncio.create_task(_fire_reminder(reminder))
    if len(alive) != len(items):
        _write_json(REMINDERS_FILE, alive)
    return len(alive)


class ReminderArgs(BaseModel):
    message: str = Field(..., description="О чём напомнить")
    minutes: int = Field(0, description="Через сколько минут напомнить")
    at_time: str = Field("", description="Либо точное время в формате ЧЧ:ММ (сегодня или завтра)")


@registry.tool(
    name="set_reminder",
    description="Ставит напоминание: через N минут или на конкретное время ЧЧ:ММ. Питомец скажет о нём вслух.",
    args_model=ReminderArgs,
    risk="safe",
    category="productivity",
)
def set_reminder(message: str, minutes: int = 0, at_time: str = "") -> str:
    if not message.strip():
        raise ToolError("Не указан текст напоминания.")

    if at_time:
        try:
            hh, mm = (int(x) for x in at_time.replace(".", ":").split(":")[:2])
            now = datetime.now()
            due = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if due <= now:
                due += timedelta(days=1)
        except Exception:
            raise ToolError(f"Не понял время '{at_time}'. Формат: ЧЧ:ММ.")
    elif minutes > 0:
        due = datetime.now() + timedelta(minutes=minutes)
    else:
        raise ToolError("Укажи minutes или at_time.")

    reminder = {
        "id": uuid.uuid4().hex[:8],
        "message": message.strip(),
        "due_ts": due.timestamp(),
        "due_human": due.strftime("%d.%m %H:%M"),
    }
    items = _read_json(REMINDERS_FILE, [])
    items.append(reminder)
    _write_json(REMINDERS_FILE, items)

    _reminder_tasks[reminder["id"]] = asyncio.create_task(_fire_reminder(reminder))
    return f"Напоминание #{reminder['id']} поставлено на {reminder['due_human']}: {reminder['message']}"


class EmptyArgs(BaseModel):
    pass


@registry.tool(
    name="list_reminders",
    description="Показывает активные напоминания с их идентификаторами и временем.",
    args_model=EmptyArgs,
    risk="safe",
    category="productivity",
)
def list_reminders() -> str:
    items = sorted(_read_json(REMINDERS_FILE, []), key=lambda r: r.get("due_ts", 0))
    if not items:
        return "Активных напоминаний нет."
    return "\n".join(f"#{r['id']} в {r['due_human']} — {r['message']}" for r in items)


class CancelReminderArgs(BaseModel):
    reminder_id: str = Field(..., description="Идентификатор напоминания из list_reminders")


@registry.tool(
    name="cancel_reminder",
    description="Отменяет напоминание по идентификатору.",
    args_model=CancelReminderArgs,
    risk="safe",
    category="productivity",
)
def cancel_reminder(reminder_id: str) -> str:
    items = _read_json(REMINDERS_FILE, [])
    rest = [r for r in items if r["id"] != reminder_id]
    if len(rest) == len(items):
        raise ToolError(f"Напоминание #{reminder_id} не найдено.")
    _write_json(REMINDERS_FILE, rest)
    task = _reminder_tasks.pop(reminder_id, None)
    if task:
        task.cancel()
    return f"Напоминание #{reminder_id} отменено."


# ── Помодоро ───────────────────────────────────────────────────────────────
class PomodoroArgs(BaseModel):
    minutes: int = Field(25, description="Длительность рабочего интервала")
    action: str = Field("start", description="'start' или 'stop'")


@registry.tool(
    name="pomodoro",
    description="Запускает или останавливает таймер помодоро. Во время работы питомец показывает режим фокуса.",
    args_model=PomodoroArgs,
    risk="safe",
    category="productivity",
)
async def pomodoro(minutes: int = 25, action: str = "start") -> str:
    from core.events import bus
    from monitor.pc_monitor import pc_monitor

    if action == "stop":
        pc_monitor.stop_pomodoro()
        await bus.set_emotion("idle", "")
        return "Помодоро остановлен."

    minutes = max(1, min(120, minutes))
    pc_monitor.start_pomodoro(minutes * 60)
    await bus.set_emotion("working", f"Focus {minutes}m")
    return f"Помодоро на {minutes} минут запущен. Не отвлекаемся."


# ── Долговременная память ──────────────────────────────────────────────────
class RememberArgs(BaseModel):
    text: str = Field(..., description="Факт, который нужно запомнить о пользователе или проекте")
    tag: str = Field("общее", description="Короткая метка-категория, например 'проект', 'привычки'")


@registry.tool(
    name="remember",
    description=(
        "Сохраняет факт в долговременную память питомца (предпочтения, пути к проектам, "
        "договорённости). Используй, когда пользователь сообщает что-то, что пригодится потом."
    ),
    args_model=RememberArgs,
    risk="safe",
    category="memory",
)
def remember(text: str, tag: str = "общее") -> str:
    notes = _read_json(NOTES_FILE, [])
    note = {
        "id": uuid.uuid4().hex[:8],
        "text": text.strip(),
        "tag": tag.strip() or "общее",
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    notes.append(note)
    _write_json(NOTES_FILE, notes[-500:])
    return f"Запомнил [{note['tag']}]: {note['text']}"


class RecallArgs(BaseModel):
    query: str = Field("", description="Ключевое слово для поиска. Пусто — вернуть всё.")
    limit: int = Field(20, description="Сколько записей вернуть")


@registry.tool(
    name="recall",
    description="Ищет в долговременной памяти ранее сохранённые факты.",
    args_model=RecallArgs,
    risk="safe",
    category="memory",
)
def recall(query: str = "", limit: int = 20) -> str:
    notes = _read_json(NOTES_FILE, [])
    if query:
        needle = query.lower()
        notes = [n for n in notes if needle in n["text"].lower() or needle in n["tag"].lower()]
    if not notes:
        return "В памяти ничего подходящего нет."
    return "\n".join(f"#{n['id']} [{n['tag']}] {n['text']} ({n['created']})" for n in notes[-limit:])


class ForgetArgs(BaseModel):
    note_id: str = Field(..., description="Идентификатор записи из recall")


@registry.tool(
    name="forget",
    description="Удаляет запись из долговременной памяти.",
    args_model=ForgetArgs,
    risk="safe",
    category="memory",
)
def forget(note_id: str) -> str:
    notes = _read_json(NOTES_FILE, [])
    rest = [n for n in notes if n["id"] != note_id]
    if len(rest) == len(notes):
        raise ToolError(f"Запись #{note_id} не найдена.")
    _write_json(NOTES_FILE, rest)
    return f"Забыл запись #{note_id}."


def load_memory_digest(limit: int = 15) -> str:
    """Короткая выжимка памяти для системного промпта."""
    notes = _read_json(NOTES_FILE, [])[-limit:]
    if not notes:
        return ""
    return "\n".join(f"- [{n['tag']}] {n['text']}" for n in notes)


# ── Эмоции ─────────────────────────────────────────────────────────────────
class EmotionArgs(BaseModel):
    emotion: str = Field(..., description=f"Одно из: {', '.join(sorted(EMOTIONS))}")
    text: str = Field("", description="Короткая подпись на экране (до 20 символов, латиница читается лучше)")


@registry.tool(
    name="express_emotion",
    description=(
        "Меняет мордочку питомца на экране M5 и в web-панели. Используй, чтобы показать "
        "реакцию: happy при успехе, working во время долгой задачи, panic при перегреве ПК."
    ),
    args_model=EmotionArgs,
    risk="safe",
    category="pet",
)
async def express_emotion(emotion: str, text: str = "") -> str:
    emo = emotion.strip().lower()
    if emo not in EMOTIONS:
        raise ToolError(f"Неизвестная эмоция '{emotion}'. Доступно: {', '.join(sorted(EMOTIONS))}")

    from core.events import bus

    await bus.set_emotion(emo, text[:24])
    return f"Показал эмоцию {emo}."


# ── Веб-поиск (запасной вариант, если не подключён MCP-сервер поиска) ───────
class SearchArgs(BaseModel):
    query: str = Field(..., description="Поисковый запрос")


@registry.tool(
    name="web_search",
    description=(
        "Быстрый поиск фактов в интернете через DuckDuckGo. "
        "Для полноценного поиска лучше подключить MCP-сервер поиска в настройках."
    ),
    args_model=SearchArgs,
    risk="safe",
    category="web",
)
async def web_search(query: str) -> str:
    try:
        import httpx
    except ImportError:
        raise ToolError("httpx не установлен — веб-поиск недоступен.")

    url = "https://api.duckduckgo.com/"
    params = {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url, params=params)
            data = response.json()
    except Exception as e:
        raise ToolError(f"поиск не удался: {e}")

    parts: list[str] = []
    if data.get("AbstractText"):
        parts.append(f"{data['AbstractText']} ({data.get('AbstractURL', '')})")
    if data.get("Answer"):
        parts.append(str(data["Answer"]))
    for topic in (data.get("RelatedTopics") or [])[:5]:
        if isinstance(topic, dict) and topic.get("Text"):
            parts.append(f"- {topic['Text']} {topic.get('FirstURL', '')}")

    if not parts:
        return (
            f"По запросу '{query}' мгновенного ответа нет. "
            "Подключи MCP-сервер поиска для полноценной выдачи."
        )
    return "\n".join(parts)
