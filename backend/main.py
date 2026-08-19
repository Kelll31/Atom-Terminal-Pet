import asyncio
import json
import logging
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from core.ws_manager import manager

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("main")

app = FastAPI(title="Atom-Terminal-Pet Brain")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Optional Web UI serving (from older version logic)
WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
FIRMWARE_DIR = os.path.join(WEB_DIR, "dist", "firmware")
if not os.path.exists(FIRMWARE_DIR):
    FIRMWARE_DIR = os.path.join(WEB_DIR, "public", "firmware")

if os.path.exists(FIRMWARE_DIR):
    app.mount("/firmware", StaticFiles(directory=FIRMWARE_DIR), name="firmware")

from monitor.pc_monitor import pc_monitor
from rules.rule_engine import rule_engine
from core.mcp_client import mcp_manager
from core.serial_manager import serial_manager

@app.on_event("startup")
async def startup_event():
    logger.info("Starting up Atom-Terminal-Pet backend...")
    # Start PC monitor worker
    app.state.monitor_task = asyncio.create_task(pc_monitor.monitor_loop())
    # Start rule engine worker
    app.state.rule_engine_task = asyncio.create_task(rule_engine.engine_loop())
    # Start MCP clients
    await mcp_manager.initialize()
    
    # Start Serial Manager
    if serial_manager.connect():
        app.state.serial_task = asyncio.create_task(serial_manager.read_loop())
        serial_manager.on_json_message = handle_json_message
        serial_manager.on_binary_message = handle_audio_stream


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down... Cleaning up connections.")

    # Stop workers
    if hasattr(app.state, "monitor_task"):
        app.state.monitor_task.cancel()
    if hasattr(app.state, "rule_engine_task"):
        app.state.rule_engine_task.cancel()
    if hasattr(app.state, "serial_task"):
        app.state.serial_task.cancel()
        
    # Stop MCP clients
    await mcp_manager.cleanup()
    
    # Stop Serial
    serial_manager.stop()

    for ws in list(manager.active_connections):
        await ws.close()


from ai.agent import process_user_input
from ai.stt import transcribe_audio_stream
from ai.tts import generate_speech

from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

class AISettings(BaseModel):
    api_key: str = ""
    base_url: str = ""
    model_name: str = ""

@app.get("/api/settings")
def get_settings():
    settings_file = os.path.join(os.path.dirname(__file__), "settings.json")
    if os.path.exists(settings_file):
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return AISettings().dict()

@app.post("/api/settings")
def save_settings(settings: AISettings):
    settings_file = os.path.join(os.path.dirname(__file__), "settings.json")
    with open(settings_file, "w", encoding="utf-8") as f:
        json.dump(settings.dict(), f)
    return {"status": "success"}

@app.post("/api/serial/disconnect")
def disconnect_serial():
    serial_manager.pause_reconnect(60.0)
    return {"status": "success", "message": "Serial port disconnected for 60 seconds"}

@app.post("/api/serial/connect")
def connect_serial():
    if serial_manager.connect():
        app.state.serial_task = asyncio.create_task(serial_manager.read_loop())
        serial_manager.on_json_message = handle_json_message
        serial_manager.on_binary_message = handle_audio_stream
        return {"status": "success", "message": "Serial port connected"}
    return {"status": "error", "message": "Failed to connect to Serial port"}

@app.post("/api/settings/test")
async def test_settings(settings: AISettings):
    try:
        if not settings.api_key:
            return {"status": "error", "message": "API Key is required."}
        headers = {}
        if settings.base_url and "openrouter.ai" in settings.base_url.lower():
            headers = {
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "Atom-Terminal-Pet"
            }
            
        llm = ChatOpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url or None,
            model=settings.model_name or "gpt-3.5-turbo",
            max_retries=1,
            timeout=15,
            default_headers=headers
        )
        res = await llm.ainvoke([HumanMessage(content="Hello! Please reply exactly with 'Test OK'.")])
        return {"status": "success", "message": res.content}
    except Exception as e:
        return {"status": "error", "message": str(e)}




async def handle_audio_stream(audio_data: bytes, exclude_ws: WebSocket = None, source: str = None):
    # Broadcast to other clients (Web UI)
    if exclude_ws:
        await manager.broadcast_binary_exclude(audio_data, exclude_ws)
    else:
        await manager.broadcast_binary(audio_data)

    # STT Pipeline
    is_complete, transcribed_text = await transcribe_audio_stream(audio_data)

    if transcribed_text:
        if not is_complete:
            await manager.broadcast_json({"action": "user_speech_partial", "text": transcribed_text})
        else:
            await manager.broadcast_json({"action": "user_speech", "text": transcribed_text})

    if is_complete and transcribed_text:
        # Pass to Agent
        ai_response_text = await process_user_input(transcribed_text)

        if ai_response_text:
            # Show thinking state
            await manager.broadcast_json({"action": "agent_thinking"})
            
            # Broadcast AI response text and happy emotion to screen
            await manager.broadcast_json(
                {"action": "speak", "emotion": "happy", "text": ai_response_text}
            )

            # TTS Pipeline
            audio_response = await generate_speech(ai_response_text)

            # Send audio to all clients in 4096-byte chunks
            if audio_response:
                chunk_size = 4096
                for i in range(0, len(audio_response), chunk_size):
                    chunk = audio_response[i:i+chunk_size]
                    await manager.broadcast_binary(chunk)
                    serial_manager.send_binary(chunk)
                    await asyncio.sleep(0.01)

async def handle_json_message(payload: dict, websocket: WebSocket = None):
    logger.info(f"Received JSON: {payload}")
    action = payload.get("action")
    if action == "device_status":
        manager.update_device_info(
            ip=payload.get("ip"),
            ssid=payload.get("ssid"),
            rssi=payload.get("rssi"),
            device=payload.get("device"),
        )
        await manager.broadcast_json(
            {"action": "device_status_update", "device_info": manager.device_info}
        )
    elif action == "shake":
        count = payload.get("count", 1)
        if count >= 5:
            reply_text = "🎉 Ого! Супер-встряска! Пати режим!"
            emotion = "party"
        elif count >= 3:
            reply_text = "Ой-ой! Голова кружится от потряхиваний!"
            emotion = "dizzy"
        else:
            reply_text = "Ой! Зачем меня трясешь?"
            emotion = "happy"

        msg = {"action": "speak", "emotion": emotion, "text": reply_text}
        await manager.broadcast_json(msg)
        serial_manager.send_json(msg)
    elif action == "user_text" and payload.get("text"):
        user_text = payload["text"]
        ai_response_text = await process_user_input(user_text)
        
        msg = {"action": "speak", "emotion": "happy", "text": ai_response_text}
        await manager.broadcast_json(msg)
        serial_manager.send_json(msg)

        # Generate TTS and send binary in chunks
        audio_response = await generate_speech(ai_response_text)
        if audio_response:
            chunk_size = 4096
            for i in range(0, len(audio_response), chunk_size):
                chunk = audio_response[i:i+chunk_size]
                await manager.broadcast_binary(chunk)
                serial_manager.send_binary(chunk)
                await asyncio.sleep(0.01)
    elif action == "set_rotation":
        await manager.broadcast_json(payload)
        serial_manager.send_json(payload)
    else:
        # Broadcast generic events
        await manager.broadcast_json(payload)
        serial_manager.send_json(payload)


@app.websocket("/ws/pet")
@app.websocket("/ws/audio")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send current device status to newly connected client
        await manager.send_json(
            {"action": "device_status_update", "device_info": manager.device_info},
            websocket,
        )

        while True:
            message = await websocket.receive()

            if "bytes" in message and message.get("bytes") is not None:
                audio_data = message["bytes"]
                await handle_audio_stream(audio_data, exclude_ws=websocket)
            elif "text" in message:
                text_data = message["text"]
                try:
                    payload = json.loads(text_data)
                    await handle_json_message(payload, websocket)
                except json.JSONDecodeError:
                    logger.warning("Received invalid JSON")

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await asyncio.sleep(1)  # Keep connection alive
    except WebSocketDisconnect:
        pass


@app.get("/api/autodetect")
async def api_autodetect():
    return {"status": "ok", "port": "COM_DUMMY"}


@app.get("/api/status")
async def api_status():
    return {
        "status": "ok",
        "active_connections": len(manager.active_connections),
        "device_info": manager.device_info,
    }


SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "settings.json")


def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading settings: {e}")
    return {"pet_name": "Атом"}


def save_settings(data):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving settings: {e}")


@app.get("/api/settings")
async def api_settings():
    settings = load_settings()
    return {
        "wifi_ssid": manager.device_info.get("ssid", ""),
        "server_ip": "192.168.1.100",
        "device_info": manager.device_info,
        "pet_name": settings.get("pet_name", "Атом"),
    }


from pydantic import BaseModel


class SettingsUpdate(BaseModel):
    pet_name: str


@app.post("/api/settings")
async def update_settings(config: SettingsUpdate):
    settings = load_settings()
    if config.pet_name:
        settings["pet_name"] = config.pet_name
    save_settings(settings)
    return {"status": "success", "pet_name": settings["pet_name"]}


import os

import yaml
from pydantic import BaseModel


class RuleCondition(BaseModel):
    metric: str
    operator: str
    value: float
    duration_seconds: int


class RuleAction(BaseModel):
    type: str
    emotion: str
    text: str


class Rule(BaseModel):
    id: str
    description: str
    condition: RuleCondition
    action: RuleAction


class RulesConfig(BaseModel):
    rules: list[Rule]


@app.get("/api/rules")
async def get_rules():
    from rules.rule_engine import rule_engine

    full_path = os.path.join(os.path.dirname(__file__), rule_engine.config_path)
    if os.path.exists(full_path):
        with open(full_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data
    return {"rules": []}


@app.post("/api/rules")
async def update_rules(config: RulesConfig):
    from rules.rule_engine import rule_engine

    full_path = os.path.join(os.path.dirname(__file__), rule_engine.config_path)

    # Convert Pydantic to dict
    data_dict = config.dict()

    with open(full_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data_dict, f, allow_unicode=True, sort_keys=False)

    # Hot reload
    rule_engine.load_rules()
    return {"status": "success"}


@app.get("/")
@app.get("/{full_path:path}")
async def serve_spa(full_path: str = ""):
    # Avoid matching API or WS routes
    if full_path.startswith("api/") or full_path.startswith("ws/"):
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Not Found")

    dist_dir = os.path.join(WEB_DIR, "dist")
    file_path = os.path.join(dist_dir, full_path)

    # If file exists, serve it (e.g. assets/index.js)
    if full_path and os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)

    # Otherwise, fallback to index.html (SPA routing)
    index_path = os.path.join(dist_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)

    return HTMLResponse(
        "<h1>Web UI not found. Please run 'npm run build' in the web/ directory.</h1>"
    )


if __name__ == "__main__":
    import uvicorn

    # uvicorn run for development
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
