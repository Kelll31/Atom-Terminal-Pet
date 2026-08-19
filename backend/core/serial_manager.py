import asyncio
import json
import logging
import struct
import serial
import serial.tools.list_ports

import time

logger = logging.getLogger("core.serial_manager")

class SerialManager:
    def __init__(self):
        self.ser = None
        self.running = False
        self.paused_until = 0.0
        # Callbacks for incoming data
        self.on_json_message = None
        self.on_binary_message = None

    @property
    def is_connected(self) -> bool:
        return bool(self.ser and self.ser.is_open)

    def find_m5stack_port(self):
        # M5Stack AtomS3 Native USB VID is 0x303A (Espressif)
        ports = serial.tools.list_ports.comports()
        for port in ports:
            if port.vid == 0x303A:
                return port.device
        return None

    def pause_reconnect(self, duration_seconds: float = 60.0):
        self.paused_until = time.time() + duration_seconds
        self.disconnect()
        logger.info(f"Paused auto-reconnect for {duration_seconds}s for WebSerial flashing.")

    def connect(self):
        self.paused_until = 0.0
        port = self.find_m5stack_port()
        if not port:
            logger.warning("No M5Stack AtomS3 found on Serial ports.")
            return False
        
        try:
            self.ser = serial.Serial()
            self.ser.port = port
            self.ser.baudrate = 115200
            self.ser.timeout = 0.1
            # Аудио идёт кусками по 4 КБ: при коротком таймауте записи чанки
            # молча терялись и речь на динамике рвалась.
            self.ser.write_timeout = 2.0
            
            # Windows native USB CDC workarounds
            self.ser.dtr = True
            self.ser.rts = True
            
            self.ser.open()
            self.running = True
            logger.info(f"Connected to AtomS3 via Serial on {port}")
            return True
        except Exception as e:
            logger.error(f"Failed to open Serial port {port}: {e}")
            return False

    def disconnect(self):
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            logger.info("Serial port closed.")

    def stop(self):
        self.running = False
        self.disconnect()

    def send_json(self, message: dict):
        if not self.ser or not self.ser.is_open:
            return
        try:
            data = json.dumps(message).encode('utf-8')
            header = struct.pack('<BBBI', 0xAA, 0xBB, 0x01, len(data))
            self.ser.write(header + data)
        except Exception as e:
            logger.error(f"Error sending JSON over Serial: {e}")
            if "PermissionError" in str(e) or "OSError" in str(e):
                self.ser.close() # Force close so it reconnects

    def send_binary(self, data: bytes) -> bool:
        if not self.ser or not self.ser.is_open:
            return False
        try:
            header = struct.pack('<BBBI', 0xAA, 0xBB, 0x02, len(data))
            self.ser.write(header + data)
            return True
        except serial.SerialTimeoutException:
            # Устройство не успевает забирать данные — чанк пропускаем,
            # но порт не рвём: следующий уйдёт нормально.
            logger.warning("Устройство не успело принять аудио-чанк, пропускаю")
            return False
        except Exception as e:
            logger.error(f"Ошибка отправки аудио в Serial: {e}")
            if "PermissionError" in str(e) or "OSError" in str(e):
                self.ser.close()
            return False

    async def read_loop(self):
        while self.running:
            if not self.ser or not self.ser.is_open:
                if time.time() < self.paused_until:
                    await asyncio.sleep(1)
                    continue
                # Try to reconnect
                if self.connect():
                    await asyncio.sleep(1)
                else:
                    await asyncio.sleep(2)
                continue
                
            try:
                # Read 2 byte header
                if self.ser.in_waiting >= 2:
                    header = self.ser.read(2)
                    if header == b'\xaa\xbb':
                        # Read Type (1 byte) + Length (4 bytes)
                        meta = self.ser.read(5)
                        if len(meta) == 5:
                            msg_type, length = struct.unpack('<BI', meta)
                            payload = self.ser.read(length)
                            if len(payload) == length:
                                if msg_type == 0x01 and self.on_json_message:
                                    try:
                                        json_data = json.loads(payload.decode('utf-8'))
                                        await self.on_json_message(json_data, source="serial")
                                    except Exception as e:
                                        logger.error(f"Failed to parse Serial JSON: {e}")
                                elif msg_type == 0x02 and self.on_binary_message:
                                    await self.on_binary_message(payload, source="serial")
            except Exception as e:
                logger.error(f"Serial read error: {e}")
                if "PermissionError" in str(e) or "OSError" in str(e) or "ClearCommError" in str(e):
                    # Windows USB CDC dropped the connection (e.g., device rebooted)
                    logger.warning("Device disconnected or rebooted. Closing port...")
                    if self.ser:
                        self.ser.close()
                await asyncio.sleep(1)
                
            await asyncio.sleep(0.01)

serial_manager = SerialManager()
