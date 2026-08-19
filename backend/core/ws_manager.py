import logging
import time

from fastapi import WebSocket

logger = logging.getLogger("core.ws_manager")


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        # Сокет самого питомца (M5), если он подключён по Wi-Fi.
        # Нужен, чтобы не дублировать аудио в Serial, когда устройство уже на WebSocket.
        self.device_ws: WebSocket | None = None
        self.device_info: dict = {
            "connected": False,
            "ip": "Not Connected",
            "ssid": "Not Connected",
            "rssi": 0,
            "device": "M5Stack AtomS3R",
            "last_seen": None,
            "transport": "none",  # none | wifi | usb
        }

    def update_device_info(
        self,
        ip: str = None,
        ssid: str = None,
        rssi: int = None,
        device: str = None,
        transport: str = None,
    ):
        self.device_info["connected"] = True
        if ip:
            self.device_info["ip"] = ip
        if ssid:
            self.device_info["ssid"] = ssid
        if rssi is not None:
            self.device_info["rssi"] = rssi
        if device:
            self.device_info["device"] = device
        if transport:
            self.device_info["transport"] = transport
        self.device_info["last_seen"] = time.strftime("%H:%M:%S")

    def set_device_ws(self, websocket: WebSocket) -> None:
        """Помечает соединение как соединение самого питомца."""
        self.device_ws = websocket
        self.device_info["transport"] = "wifi"

    @property
    def device_on_wifi(self) -> bool:
        return self.device_ws is not None and self.device_ws in self.active_connections

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("Client disconnected.")
        if websocket is self.device_ws:
            self.device_ws = None
            self.device_info["connected"] = False
            self.device_info["transport"] = "none"

    async def send_json(self, message: dict, websocket: WebSocket):
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending JSON: {e}")
            self.disconnect(websocket)

    async def send_binary(self, data: bytes, websocket: WebSocket):
        try:
            await websocket.send_bytes(data)
        except Exception as e:
            logger.error(f"Error sending binary: {e}")
            self.disconnect(websocket)

    async def broadcast_json(self, message: dict):
        for connection in list(self.active_connections):
            await self.send_json(message, connection)

    async def broadcast_binary(self, data: bytes):
        for connection in list(self.active_connections):
            await self.send_binary(data, connection)

    async def broadcast_binary_exclude(self, data: bytes, exclude_ws: WebSocket):
        for connection in list(self.active_connections):
            if connection != exclude_ws:
                await self.send_binary(data, connection)


manager = ConnectionManager()
