"""Реестр WebSocket-клиентов и маршрутизация по ним.

Ключевая идея: питомец — НЕ ещё одна панель. У прошивки в разы более узкое
горло (буфер команды в пару килобайт, экран 128x128 без кириллицы, скромный
heap), поэтому «разослать всем» для неё смертельно: снимок задач на 15+ КБ
рвёт соединение кодом 1009, а браузерный микрофон из тестера превращается
в шум из динамика. Поэтому все broadcast_* здесь означают «всем панелям»,
а для устройства есть отдельные адресные send_to_device / send_binary_to_device.
"""

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

    def mark_device_seen(self, transport: str) -> bool:
        """Питомец только что прислал данные. Возвращает True, если состояние изменилось.

        Нужно потому, что по USB старые прошивки не представляются пакетом
        device_status — раньше панель в упор не видела подключённого питомца,
        хотя звук с его микрофона исправно шёл.
        """
        changed = (
            not self.device_info["connected"] or self.device_info["transport"] != transport
        )
        self.device_info["connected"] = True
        self.device_info["transport"] = transport
        self.device_info["last_seen"] = time.strftime("%H:%M:%S")
        if transport == "usb" and self.device_info["ip"] in ("Not Connected", "Оффлайн"):
            self.device_info["ip"] = "USB"
            self.device_info["ssid"] = "—"
        return changed

    def mark_device_gone(self) -> bool:
        if not self.device_info["connected"]:
            return False
        self.device_info["connected"] = False
        self.device_info["transport"] = "none"
        return True

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

    # ── рассылка по панелям ────────────────────────────────────────────────
    def panel_connections(self) -> list[WebSocket]:
        """Все клиенты, кроме самого питомца.

        Отдельный список нужен потому, что панель и устройство хотят разного:
        панели — весь поток событий целиком, устройству — только то, что оно
        понимает, и только в укороченном виде (см. EventBus._device_message).
        """
        return [ws for ws in self.active_connections if ws is not self.device_ws]

    async def broadcast_json(self, message: dict):
        """JSON всем панелям. Устройство сюда НЕ попадает намеренно."""
        for connection in self.panel_connections():
            await self.send_json(message, connection)

    async def broadcast_binary(self, data: bytes):
        """Бинарный кадр всем панелям (осциллограф, запись, отладка звука)."""
        for connection in self.panel_connections():
            await self.send_binary(data, connection)

    async def broadcast_binary_exclude(self, data: bytes, exclude_ws: WebSocket):
        """То же, но без отправителя — чтобы микрофон не возвращался ему эхом.

        Устройство исключено и здесь: иначе браузерный микрофон из тестера
        PCMicTester уходил бы прямиком в динамик питомца.
        """
        for connection in self.panel_connections():
            if connection is not exclude_ws:
                await self.send_binary(data, connection)

    # ── адресная отправка питомцу ──────────────────────────────────────────
    async def send_to_device(self, message: dict) -> bool:
        """Команда лично питомцу по Wi-Fi.

        Возвращает False, если устройства по Wi-Fi нет или отправка не удалась,
        — вызывающий код (шина событий) по этому признаку решает, не переслать
        ли команду по USB.
        """
        websocket = self.device_ws
        if websocket is None or websocket not in self.active_connections:
            return False
        try:
            await websocket.send_json(message)
            return True
        except Exception as e:
            logger.error(f"Не удалось отправить команду питомцу: {e}")
            self.disconnect(websocket)
            return False

    async def send_binary_to_device(self, data: bytes) -> bool:
        """Аудио-чанк лично питомцу по Wi-Fi. Возвращает False, если не дошло."""
        websocket = self.device_ws
        if websocket is None or websocket not in self.active_connections:
            return False
        try:
            await websocket.send_bytes(data)
            return True
        except Exception as e:
            logger.error(f"Не удалось отправить аудио питомцу: {e}")
            self.disconnect(websocket)
            return False


manager = ConnectionManager()
