"""Atom-Terminal-Pet — мозг питомца.

FastAPI-сервер: принимает голос с M5Stack AtomS3R, распознаёт речь, отдаёт задачу
агенту (который реально управляет ПК через инструменты и MCP), озвучивает ответ
и транслирует всё происходящее в web-панель.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ai.agent import agent, is_wake_word_present, tools_snapshot
from ai.stt import transcribe_audio_stream
from ai.tools import registry
from core.events import bus
from core.mcp_client import mcp_manager
from core.serial_manager import serial_manager
from core.settings import settings_store
from core.ws_manager import manager
from core import stats
from monitor.pc_monitor import pc_monitor
from rules.rule_engine import rule_engine
from tasks.task_manager import task_manager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("main")

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(os.path.dirname(BACKEND_DIR), "web")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Атом просыпается…")

    app.state.monitor_task = asyncio.create_task(pc_monitor.monitor_loop())
    app.state.rule_engine_task = asyncio.create_task(rule_engine.engine_loop())
    task_manager.start()

    from ai.tools.productivity import schedule_pending_reminders

    restored = schedule_pending_reminders()
    if restored:
        logger.info(f"Восстановлено напоминаний: {restored}")

    # MCP-серверы поднимаем в фоне: медленный сервер не должен блокировать старт
    app.state.mcp_task = asyncio.create_task(mcp_manager.initialize())

    if serial_manager.connect():
        ensure_serial_reader()
        manager.update_device_info(transport="usb")

    logger.info(f"Инструментов доступно: {len(registry.all())}")
    yield

    logger.info("Останавливаюсь…")
    for attr in ("monitor_task", "rule_engine_task", "serial_task", "mcp_task"):
        task = getattr(app.state, attr, None)
        if task:
            task.cancel()
    await task_manager.stop()
    await mcp_manager.cleanup()
    serial_manager.stop()
    for ws in list(manager.active_connections):
        try:
            await ws.close()
        except Exception:
            pass


app = FastAPI(title="Atom-Terminal-Pet Brain", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FIRMWARE_DIR = os.path.join(WEB_DIR, "dist", "firmware")
if not os.path.exists(FIRMWARE_DIR):
    FIRMWARE_DIR = os.path.join(WEB_DIR, "public", "firmware")
if os.path.exists(FIRMWARE_DIR):
    app.mount("/firmware", StaticFiles(directory=FIRMWARE_DIR), name="firmware")


# ── Обработка входящих данных (WebSocket + Serial) ─────────────────────────
async def handle_audio_stream(
    audio_data: bytes, exclude_ws: WebSocket | None = None, source: str | None = None
):
    """Аудио с микрофона питомца: ретрансляция в панель + распознавание речи."""
    stats.track_mic(audio_data)

    if exclude_ws is not None:
        await manager.broadcast_binary_exclude(audio_data, exclude_ws)
    else:
        await manager.broadcast_binary(audio_data)

    # Пока питомец говорит, микрофон слышит его самого — не распознаём эхо.
    if bus.is_speaking:
        return

    is_complete, text = await transcribe_audio_stream(audio_data)
    if not text:
        return

    if not is_complete:
        await bus.emit("user_speech_partial", text=text)
        return

    await bus.emit("user_speech", text=text)

    if not is_wake_word_present(text):
        logger.info(f"Реплика без обращения по имени, игнорирую: {text}")
        return

    await task_manager.submit(text, source="voice")


async def handle_json_message(
    payload: dict, websocket: WebSocket | None = None, source: str | None = None
):
    action = payload.get("action")

    if action == "device_status":
        if websocket is not None:
            manager.set_device_ws(websocket)
        manager.update_device_info(
            ip=payload.get("ip"),
            ssid=payload.get("ssid"),
            rssi=payload.get("rssi"),
            device=payload.get("device"),
            transport="wifi" if websocket is not None else "usb",
        )
        await bus.emit("device_status_update", device_info=manager.device_info)
        return

    if action == "user_text" and payload.get("text"):
        await task_manager.submit(payload["text"], source=payload.get("source", "chat"))
        return

    if action == "approve":
        await task_manager.resolve_approval(
            payload.get("id", ""), payload.get("decision", "deny")
        )
        return

    if action == "cancel_task":
        await task_manager.cancel(payload.get("task_id", ""))
        return

    if action == "reset_chat":
        agent.reset()
        await bus.emit("chat_reset")
        return

    if action == "shake":
        count = int(payload.get("count", 1))
        if count >= 5:
            await bus.speak("Ого! Супер-встряска! Врубаю пати-режим!", emotion="party")
        elif count >= 3:
            await bus.speak("Ой-ой, голова кружится!", emotion="dizzy")
        else:
            await bus.speak("Эй! Зачем трясёшь?", emotion="happy")
        return

    if action in ("set_emotion", "speak"):
        await bus.emit(action, emotion=payload.get("emotion", "idle"), text=payload.get("text", ""))
        return

    if action == "set_rotation":
        await bus.emit("set_rotation", rotation=payload.get("rotation", 0))
        return

    if action == "ping":
        if websocket is not None:
            await manager.send_json({"action": "pong"}, websocket)
        return

    logger.debug(f"Неизвестное сообщение: {payload}")


# ── WebSocket ──────────────────────────────────────────────────────────────
@app.websocket("/ws/pet")
@app.websocket("/ws/audio")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        await manager.send_json(
            {"action": "device_status_update", "device_info": manager.device_info}, websocket
        )
        await manager.send_json({"action": "tasks_snapshot", "tasks": task_manager.list()}, websocket)

        while True:
            message = await websocket.receive()

            if message.get("bytes") is not None:
                await handle_audio_stream(message["bytes"], exclude_ws=websocket)
            elif "text" in message:
                try:
                    payload = json.loads(message["text"])
                except json.JSONDecodeError:
                    logger.warning("Получен некорректный JSON по WebSocket")
                    continue
                await handle_json_message(payload, websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Ошибка WebSocket: {e}")
        manager.disconnect(websocket)


# ── Настройки ──────────────────────────────────────────────────────────────
class SettingsPayload(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model_name: str | None = None
    temperature: float | None = None
    max_steps: int | None = None
    pet_name: str | None = None
    wake_words: list[str] | None = None
    require_wake_word: bool | None = None
    speak_replies: bool | None = None
    audio_output: str | None = None
    autonomy: str | None = None
    allowed_roots: list[str] | None = None
    disabled_tools: list[str] | None = None
    mcp_enabled: bool | None = None


class AISettings(BaseModel):
    api_key: str = ""
    base_url: str = ""
    model_name: str = ""


@app.get("/api/health")
async def api_health():
    return {
        "status": "ok",
        "clients": len(manager.active_connections),
        "device": manager.device_info,
        "serial_connected": serial_manager.is_connected,
        "tools": len(registry.all()),
        "mcp": mcp_manager.status(),
        "model": settings_store.get("model_name"),
        "has_key": bool(settings_store.get("api_key")),
        "audio": stats.snapshot(),
        "speaking": bus.is_speaking,
    }


class SayPayload(BaseModel):
    text: str = "Проверка связи. Меня слышно?"
    emotion: str = "happy"
    voice: bool = True


@app.post("/api/say")
async def api_say(payload: SayPayload):
    """Проверка динамика и экрана: фраза уходит на устройство и в панель."""
    before = stats.audio_stats["tts_bytes"]
    await bus.speak(payload.text, emotion=payload.emotion, voice=payload.voice)

    output = settings_store.get("audio_output", "both")
    device_route = "Wi-Fi" if manager.device_on_wifi else ("USB" if serial_manager.is_connected else "устройство не подключено")
    routes = []
    if output in ("device", "both"):
        routes.append(f"питомец ({device_route})")
    if output in ("pc", "both"):
        routes.append("колонки ПК")

    return {
        "status": "success",
        "bytes_sent": stats.audio_stats["tts_bytes"] - before,
        "route": " + ".join(routes) or "звук выключен",
    }


@app.get("/api/settings")
def get_settings():
    return settings_store.current.public_dict()


@app.post("/api/settings")
def update_settings(payload: SettingsPayload):
    updated = settings_store.update(payload.model_dump(exclude_unset=True, exclude_none=True))
    return {"status": "success", **updated.public_dict()}


@app.post("/api/settings/test")
async def test_settings(payload: AISettings):
    """Проверка связи с LLM без сохранения настроек."""
    from langchain_core.messages import HumanMessage
    from langchain_openai import ChatOpenAI

    api_key = payload.api_key or settings_store.get("api_key")
    if not api_key:
        return {"status": "error", "message": "Не указан API-ключ."}

    headers = {}
    base_url = payload.base_url or settings_store.get("base_url")
    if base_url and "openrouter.ai" in base_url.lower():
        headers = {"HTTP-Referer": "http://localhost:8000", "X-Title": "Atom-Terminal-Pet"}

    try:
        llm = ChatOpenAI(
            api_key=api_key,
            base_url=base_url or None,
            model=payload.model_name or settings_store.get("model_name") or "gpt-4o-mini",
            max_retries=1,
            timeout=20,
            default_headers=headers,
        )
        result = await llm.ainvoke([HumanMessage(content="Ответь ровно: Test OK")])
        return {"status": "success", "message": result.content}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── Инструменты ────────────────────────────────────────────────────────────
@app.get("/api/tools")
async def api_tools():
    return {"tools": tools_snapshot()}


@app.post("/api/tools/{name}/toggle")
async def api_toggle_tool(name: str, enabled: bool = True):
    if registry.get(name) is None:
        raise HTTPException(status_code=404, detail="Инструмент не найден")

    disabled = set(settings_store.get("disabled_tools") or [])
    disabled.discard(name) if enabled else disabled.add(name)
    settings_store.update({"disabled_tools": sorted(disabled)})
    return {"status": "success", "name": name, "enabled": enabled}


class ToolRunPayload(BaseModel):
    args: dict[str, Any] = {}


@app.post("/api/tools/{name}/run")
async def api_run_tool(name: str, payload: ToolRunPayload):
    """Ручной запуск инструмента из панели — подтверждением считается сам клик."""
    if registry.get(name) is None:
        raise HTTPException(status_code=404, detail="Инструмент не найден")
    ok, result = await registry.execute(name, payload.args, ctx=None, autonomy="full")
    return {"status": "success" if ok else "error", "result": result}


@app.get("/api/audit")
async def api_audit(limit: int = 100):
    from ai.tools.base import AUDIT_LOG

    if not os.path.exists(AUDIT_LOG):
        return {"entries": []}
    with open(AUDIT_LOG, "r", encoding="utf-8") as f:
        lines = f.readlines()[-max(1, min(500, limit)):]
    entries = []
    for line in lines:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return {"entries": entries[::-1]}


# ── MCP ────────────────────────────────────────────────────────────────────
class MCPServerPayload(BaseModel):
    name: str
    command: str
    args: list[str] = []
    env: dict[str, str] = {}
    cwd: str | None = None
    description: str = ""
    enabled: bool = True


@app.get("/api/mcp/servers")
async def api_mcp_servers():
    return {"servers": mcp_manager.status()}


@app.post("/api/mcp/servers")
async def api_mcp_upsert(payload: MCPServerPayload):
    config = payload.model_dump(exclude={"name"})
    info = await mcp_manager.upsert_server(payload.name, config)
    return {"status": "success", "server": info}


@app.delete("/api/mcp/servers/{name}")
async def api_mcp_delete(name: str):
    if not await mcp_manager.remove_server(name):
        raise HTTPException(status_code=404, detail="Сервер не найден")
    return {"status": "success"}


@app.post("/api/mcp/servers/{name}/toggle")
async def api_mcp_toggle(name: str, enabled: bool = True):
    if not await mcp_manager.set_enabled(name, enabled):
        raise HTTPException(status_code=404, detail="Сервер не найден или не запустился")
    return {"status": "success", "servers": mcp_manager.status()}


@app.post("/api/mcp/servers/{name}/restart")
async def api_mcp_restart(name: str):
    ok = await mcp_manager.restart_server(name)
    return {"status": "success" if ok else "error", "servers": mcp_manager.status()}


# ── Задачи ─────────────────────────────────────────────────────────────────
class TaskPayload(BaseModel):
    text: str
    source: str = "api"


class ApprovalPayload(BaseModel):
    decision: str = "deny"  # allow | allow_always | deny


@app.get("/api/tasks")
async def api_tasks():
    return {"tasks": task_manager.list(), "pending_approvals": list(task_manager.pending_approvals.values())}


@app.post("/api/tasks")
async def api_create_task(payload: TaskPayload):
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Пустая задача")
    task = await task_manager.submit(payload.text, source=payload.source)
    return {"status": "success", "task": task.dict()}


@app.post("/api/tasks/{task_id}/cancel")
async def api_cancel_task(task_id: str):
    if not await task_manager.cancel(task_id):
        raise HTTPException(status_code=404, detail="Задача не найдена или уже завершена")
    return {"status": "success"}


@app.post("/api/approvals/{approval_id}")
async def api_resolve_approval(approval_id: str, payload: ApprovalPayload):
    if not await task_manager.resolve_approval(approval_id, payload.decision):
        raise HTTPException(status_code=404, detail="Запрос подтверждения не найден")
    return {"status": "success"}


# ── Правила ────────────────────────────────────────────────────────────────
class RuleCondition(BaseModel):
    metric: str
    operator: str
    value: float
    duration_seconds: int = 0


class RuleAction(BaseModel):
    type: str = "set_emotion"
    emotion: str = "idle"
    text: str = ""
    task: str = ""


class Rule(BaseModel):
    id: str
    description: str = ""
    condition: RuleCondition
    action: RuleAction
    cooldown_seconds: int = 300


class RulesConfig(BaseModel):
    rules: list[Rule]


@app.get("/api/rules")
async def get_rules():
    if os.path.exists(rule_engine.full_path):
        with open(rule_engine.full_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {"rules": []}
    return {"rules": []}


@app.post("/api/rules")
async def update_rules(config: RulesConfig):
    with open(rule_engine.full_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config.model_dump(), f, allow_unicode=True, sort_keys=False)
    rule_engine.load_rules()
    return {"status": "success", "count": len(rule_engine.rules)}


# ── Устройство ─────────────────────────────────────────────────────────────
@app.post("/api/serial/disconnect")
def disconnect_serial():
    serial_manager.pause_reconnect(60.0)
    return {"status": "success", "message": "Serial освобождён на 60 секунд (для прошивки)"}


def ensure_serial_reader() -> None:
    """Держим ровно один цикл чтения порта: два параллельных ломают кадры."""
    serial_manager.on_json_message = handle_json_message
    serial_manager.on_binary_message = handle_audio_stream

    task = getattr(app.state, "serial_task", None)
    if task is None or task.done():
        app.state.serial_task = asyncio.create_task(serial_manager.read_loop())


@app.post("/api/serial/connect")
def connect_serial():
    if serial_manager.connect():
        ensure_serial_reader()
        return {"status": "success", "message": "Устройство подключено по USB"}
    return {"status": "error", "message": "AtomS3R не найден на COM-портах"}


@app.get("/api/status")
async def api_status():
    return {
        "status": "ok",
        "active_connections": len(manager.active_connections),
        "device_info": manager.device_info,
    }


# ── Отдача web-панели (SPA) ────────────────────────────────────────────────
@app.get("/")
@app.get("/{full_path:path}")
async def serve_spa(full_path: str = ""):
    if full_path.startswith(("api/", "ws/", "firmware/")):
        raise HTTPException(status_code=404, detail="Not Found")

    dist_dir = os.path.join(WEB_DIR, "dist")
    file_path = os.path.join(dist_dir, full_path)
    if full_path and os.path.isfile(file_path):
        return FileResponse(file_path)

    index_path = os.path.join(dist_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)

    return HTMLResponse(
        "<h1>Web-панель не собрана</h1><p>Выполните <code>npm install &amp;&amp; npm run build</code> "
        "в каталоге <code>web/</code>, либо запустите <code>npm run dev</code> на порту 5173.</p>"
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
