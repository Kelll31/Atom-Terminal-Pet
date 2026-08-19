import logging

from fastapi import WebSocket

logger = logging.getLogger("core.ws_manager")


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.device_info: dict = {
            "connected": False,
            "ip": "Not Connected",
            "ssid": "Not Connected",
            "rssi": 0,
            "device": "M5Stack AtomS3",
            "last_seen": None,
        }

    def update_device_info(
        self, ip: str = None, ssid: str = None, rssi: int = None, device: str = None
    ):
        import time

        self.device_info["connected"] = True
        if ip:
            self.device_info["ip"] = ip
        if ssid:
            self.device_info["ssid"] = ssid
        if rssi is not None:
            self.device_info["rssi"] = rssi
        if device:
            self.device_info["device"] = device
        self.device_info["last_seen"] = time.strftime("%H:%M:%S")

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("Client disconnected.")
            if len(self.active_connections) == 0:
                self.device_info["connected"] = False

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
        count = 0
        for connection in list(self.active_connections):
            if connection != exclude_ws:
                await self.send_binary(data, connection)
                count += 1
        if count > 0 and len(data) > 0:
            # We log every 100th message to avoid spam? Actually we can't easily track state here.
            # Let's just log it if we really need to, or not at all.
            pass


manager = ConnectionManager()
