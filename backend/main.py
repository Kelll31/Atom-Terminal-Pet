import asyncio
import logging
import json
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from core.ws_manager import manager

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
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
FIRMWARE_DIR = os.path.join(WEB_DIR, "firmware")
if os.path.exists(FIRMWARE_DIR):
    app.mount("/firmware", StaticFiles(directory=FIRMWARE_DIR), name="firmware")

from monitor.pc_monitor import pc_monitor
from rules.rule_engine import rule_engine
import asyncio

@app.on_event("startup")
async def startup_event():
    logger.info("Starting up Atom-Terminal-Pet backend...")
    # Start PC monitor worker
    app.state.monitor_task = asyncio.create_task(pc_monitor.monitor_loop())
    # Start rule engine worker
    app.state.rule_engine_task = asyncio.create_task(rule_engine.engine_loop())

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down... Cleaning up connections.")
    
    # Stop workers
    if hasattr(app.state, "monitor_task"):
        app.state.monitor_task.cancel()
    if hasattr(app.state, "rule_engine_task"):
        app.state.rule_engine_task.cancel()
        
    for ws in list(manager.active_connections):
        await ws.close()

@app.get("/")
async def get_index():
    index_path = os.path.join(WEB_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>Web UI not found. Please create web/index.html</h1>")

from ai.agent import process_user_input
from ai.stt import transcribe_audio
from ai.tts import generate_speech

@app.websocket("/ws/pet")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            message = await websocket.receive()
            
            if "bytes" in message:
                audio_data = message["bytes"]
                logger.debug(f"Received audio payload: {len(audio_data)} bytes")
                
                # STT Pipeline
                transcribed_text = await transcribe_audio(audio_data)
                
                # Pass to Agent
                ai_response_text = await process_user_input(transcribed_text)
                
                # TTS Pipeline
                audio_response = await generate_speech(ai_response_text)
                
                # Send back to ESP32
                await manager.send_binary(audio_response, websocket)
                
            elif "text" in message:
                text_data = message["text"]
                try:
                    payload = json.loads(text_data)
                    logger.info(f"Received JSON: {payload}")
                    # TODO: Pass event to Rule Engine / AI Agent
                except json.JSONDecodeError:
                    logger.warning("Received invalid JSON")
                    
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    # uvicorn run for development
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
