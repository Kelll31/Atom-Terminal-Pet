import os
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import List

from config import load_config, save_config, SystemSettings
from agent import AICompanionAgent

app = FastAPI(title="AI Companion Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize settings and agent
settings = load_config()
agent = AICompanionAgent(settings)

# Active log websockets for the UI
log_connections: List[WebSocket] = []

async def broadcast_log(message: str):
    for connection in log_connections:
        try:
            await connection.send_text(message)
        except:
            pass

# Define the absolute path for the web folder
WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
FIRMWARE_DIR = os.path.join(WEB_DIR, "firmware")

# Mount static files for ESP Web Tools (manifest and bins)
if os.path.exists(FIRMWARE_DIR):
    app.mount("/firmware", StaticFiles(directory=FIRMWARE_DIR), name="firmware")


@app.get("/")
async def get_index():
    index_path = os.path.join(WEB_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>Web UI not found. Please create web/index.html</h1>")

def autodetect_wifi_and_ip():
    import subprocess
    import re
    import socket

    wifi_ssid = ""
    wifi_pass = ""
    server_ip = ""

    # 1. Detect Wi-Fi SSID & Password
    try:
        out = subprocess.check_output("netsh wlan show interfaces", shell=True, text=True, errors="ignore")
        for line in out.splitlines():
            line_str = line.strip()
            if line_str.startswith("SSID") and not "BSSID" in line_str:
                parts = line_str.split(":", 1)
                if len(parts) > 1:
                    wifi_ssid = parts[1].strip()
                    break

        if wifi_ssid:
            cmd = f'netsh wlan show profile name="{wifi_ssid}" key=clear'
            prof_out = subprocess.check_output(cmd, shell=True, text=True, errors="ignore")
            for line in prof_out.splitlines():
                if "Key Content" in line or "Содержимое ключа" in line:
                    parts = line.split(":", 1)
                    if len(parts) > 1:
                        wifi_pass = parts[1].strip()
                        break
    except Exception as e:
        print(f"Wi-Fi autodetect error: {e}")

    # 2. Detect physical Wi-Fi / LAN IP (ignoring VPN / TUN / TAP / Radmin / 169.254)
    for iface in ["Беспроводная сеть", "Wi-Fi", "WLAN"]:
        try:
            ip_out = subprocess.check_output(f'netsh interface ipv4 show addresses "{iface}"', shell=True, text=True, errors="ignore")
            match = re.search(r"(?:IP-адрес|IP Address|IP)\s*:\s*([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", ip_out)
            if match:
                found_ip = match.group(1).strip()
                if not found_ip.startswith("169.254"):
                    server_ip = found_ip
                    break
        except Exception:
            pass

    if not server_ip:
        try:
            all_ips = socket.gethostbyname_ex(socket.gethostname())[2]
            for ip in all_ips:
                if (ip.startswith("192.168.") or ip.startswith("10.")) and not ip.startswith("169.254"):
                    server_ip = ip
                    break
        except Exception:
            pass

    if not server_ip:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            server_ip = s.getsockname()[0]
            s.close()
        except Exception:
            server_ip = "192.168.1.100"

    return {
        "ssid": wifi_ssid,
        "pass": wifi_pass,
        "server_ip": server_ip
    }


@app.get("/api/autodetect")
async def get_autodetect():
    return autodetect_wifi_and_ip()

@app.post("/api/compile_firmware")
async def compile_firmware(data: dict):
    ssid = data.get("ssid", "")
    wifi_pass = data.get("pass", "")
    server_ip = data.get("server_ip", "192.168.1.100")

    await broadcast_log(f"Начата компиляция прошивки под Wi-Fi '{ssid}' и IP '{server_ip}'...")

    env = os.environ.copy()
    env["PLATFORMIO_BUILD_FLAGS"] = f'-DDEFAULT_WIFI_SSID=\\"{ssid}\\" -DDEFAULT_WIFI_PASS=\\"{wifi_pass}\\" -DDEFAULT_SERVER_IP=\\"{server_ip}\\"'

    cmd = [os.path.join(os.path.dirname(__file__), "venv", "Scripts", "python.exe"), "-m", "platformio", "run"]
    firmware_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "firmware")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=firmware_dir,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode == 0:
            await broadcast_log("Прошивка успешно скомпилирована с указанными настройками Wi-Fi!")
            return {"status": "success", "message": "Прошивка успешно собрана с вашими настройками Wi-Fi!"}
        else:
            err_msg = stderr.decode(errors="ignore") or stdout.decode(errors="ignore")
            await broadcast_log(f"Ошибка компиляции: {err_msg[:200]}")
            return {"status": "error", "message": f"Ошибка компиляции: {err_msg[:200]}"}
    except Exception as e:
        await broadcast_log(f"Исключение при сборке: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/settings", response_model=SystemSettings)
async def get_settings():
    return settings

@app.post("/api/settings")
async def update_settings(new_settings: SystemSettings):
    global settings
    settings = new_settings
    save_config(settings)
    agent.update_settings(settings)
    await broadcast_log("Настройки обновлены.")
    return {"status": "success"}


@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()
    log_connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        log_connections.remove(websocket)

# Active M5Stack websocket connections
esp_connections: List[WebSocket] = []

async def broadcast_esp_emotion(emotion: str):
    for ws in esp_connections:
        try:
            await ws.send_text(f"EMOTION:{emotion}")
        except:
            pass

@app.post("/api/pc_audio")
async def pc_audio_endpoint(file: Request):
    """
    Endpoint for PC microphone audio / text chat.
    Processes audio or JSON text, plays reply through PC Speakers, and updates M5Stack emotion!
    """
    import urllib.parse
    content_type = file.headers.get("content-type", "")

    if "application/json" in content_type:
        body = await file.json()
        user_text = body.get("text", "")
        await broadcast_log(f"ПК Чат [Текст]: {user_text}")
        audio_file_path, text_reply, emotion = await agent.process_text(user_text)
    else:
        audio_bytes = await file.body()
        await broadcast_log(f"ПК Чат [Микрофон]: {len(audio_bytes)} байт. Обработка...")
        audio_file_path, text_reply, emotion = await agent.process_audio(audio_bytes)

    await broadcast_log(f"Ответ Компаньона ({emotion}): {text_reply}")
    await broadcast_esp_emotion(emotion)

    if audio_file_path and os.path.exists(audio_file_path):
        encoded_reply = urllib.parse.quote(text_reply or "")
        return FileResponse(
            audio_file_path,
            media_type="audio/mpeg",
            headers={
                "X-Reply-Text": encoded_reply,
                "X-Emotion": emotion,
                "Access-Control-Expose-Headers": "X-Reply-Text, X-Emotion"
            }
        )
    return {"status": "error", "message": "Failed to generate audio"}

def convert_mp3_to_pcm16k(mp3_path: str) -> bytes:
    import miniaudio
    try:
        with open(mp3_path, "rb") as f:
            mp3_bytes = f.read()
        decoded = miniaudio.decode(mp3_bytes, sample_rate=16000, nchannels=1)
        return decoded.samples.tobytes()
    except Exception as e:
        print(f"Error converting MP3 to 16kHz PCM: {e}")
        return b""

@app.websocket("/ws/audio")
async def websocket_audio(websocket: WebSocket):
    """
    WebSocket for the ESP32 (M5Stack) to connect.
    Sends raw 16kHz 16-bit PCM audio and emotion text commands.
    """
    await websocket.accept()
    esp_connections.append(websocket)
    await broadcast_log("ESP32 Устройство подключено по WebSocket.")
    
    try:
        while True:
            message = await websocket.receive()
            if "bytes" in message and message["bytes"]:
                audio_data = message["bytes"]
                await broadcast_log(f"Получено аудио с M5Stack: {len(audio_data)} байт. Обработка...")
                await websocket.send_text("EMOTION:thinking")

                audio_file_path, text_reply, emotion = await agent.process_audio(audio_data)
                await broadcast_log(f"Ответ агента [{emotion}]: {text_reply}")
                await websocket.send_text(f"EMOTION:{emotion}")

                if audio_file_path and os.path.exists(audio_file_path):
                    pcm_bytes = convert_mp3_to_pcm16k(audio_file_path)
                    if pcm_bytes:
                        await websocket.send_bytes(pcm_bytes)
                        await broadcast_log(f"PCM аудиоответ (16kHz, {len(pcm_bytes)} байт) отправлен на динамик M5Stack.")
                    os.remove(audio_file_path)

            elif "text" in message and message["text"]:
                text_cmd = message["text"].strip()
                if text_cmd == "PET_ACTION:pat":
                    await broadcast_log("🐾 Пользователь погладил Атома по экрану M5Stack!")
                    await websocket.send_text("EMOTION:love")

                    audio_file_path, text_reply, emotion = await agent.process_text("Пользователь ласково погладил тебя по экрану! Порадуйся и скажи что-нибудь милое.")
                    await broadcast_log(f"Атом обрадовался: {text_reply}")
                    await websocket.send_text("EMOTION:love")

                    if audio_file_path and os.path.exists(audio_file_path):
                        pcm_bytes = convert_mp3_to_pcm16k(audio_file_path)
                        if pcm_bytes:
                            await websocket.send_bytes(pcm_bytes)
                        os.remove(audio_file_path)
    except WebSocketDisconnect:
        if websocket in esp_connections:
            esp_connections.remove(websocket)
        await broadcast_log("ESP32 Устройство отключено.")
    except Exception as e:
        if websocket in esp_connections:
            esp_connections.remove(websocket)
        await broadcast_log(f"Ошибка в WebSocket /ws/audio: {e}")




if __name__ == "__main__":
    import uvicorn
    # Make sure we run on 0.0.0.0 to allow ESP32 to connect from local network
    # Disable ping interval/timeout to prevent 1011 ConnectionClosedError when ESP is busy processing audio
    uvicorn.run(app, host="0.0.0.0", port=8000, ws_ping_interval=None, ws_ping_timeout=None)
