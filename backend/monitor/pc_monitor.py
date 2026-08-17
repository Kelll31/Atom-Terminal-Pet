import asyncio
import psutil
import logging
import json
from core.ws_manager import manager

logger = logging.getLogger("monitor.pc_monitor")

try:
    import GPUtil
    HAS_GPUTIL = True
except ImportError:
    HAS_GPUTIL = False
    logger.warning("GPUtil not found. GPU monitoring will be disabled. Install with: pip install gputil")

try:
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as MediaManager
    HAS_WINSDK = True
except ImportError:
    HAS_WINSDK = False
    logger.warning("winrt not found. Spotify/Media monitoring disabled. Install with: pip install winrt-Windows.Media.Control")

class PCMonitor:
    def __init__(self, interval_sec=2.0):
        self.interval_sec = interval_sec
        self.is_running = False
        
        # Simple Pomodoro state
        self.pomodoro_active = False
        self.pomodoro_time_left = 0

    async def get_media_info(self):
        if not HAS_WINSDK:
            return None
        try:
            sessions = await MediaManager.request_async()
            current_session = sessions.get_current_session()
            if current_session:
                info = await current_session.try_get_media_properties_async()
                title = info.title
                artist = info.artist
                if title:
                    return f"{artist} - {title}" if artist else title
        except Exception as e:
            logger.debug(f"Media info error: {e}")
        return None

    def get_gpu_usage(self):
        if not HAS_GPUTIL:
            return 0
        try:
            gpus = GPUtil.getGPUs()
            if gpus:
                return int(gpus[0].load * 100)
        except Exception:
            pass
        return 0
        
    def get_cpu_temp(self):
        # psutil temperatures are tricky on Windows, usually requires WMI or OpenHardwareMonitor.
        # We will return a mock or try a fallback if it exists.
        if hasattr(psutil, "sensors_temperatures"):
            temps = psutil.sensors_temperatures()
            if temps and 'coretemp' in temps:
                return int(temps['coretemp'][0].current)
        return 40 # Mock default

    async def collect_metrics(self):
        cpu = int(psutil.cpu_percent(interval=None))
        ram = int(psutil.virtual_memory().percent)
        gpu = self.get_gpu_usage()
        temp = self.get_cpu_temp()
        
        payload = {
            "action": "update_pc",
            "cpu": cpu,
            "ram": ram,
            "gpu": gpu,
            "temp": temp
        }
        
        media = await self.get_media_info()
        if media:
            payload["spotify"] = media
            
        if self.pomodoro_active:
            payload["time_left"] = self.pomodoro_time_left
            self.pomodoro_time_left = max(0, self.pomodoro_time_left - int(self.interval_sec))
            
        return payload

    async def monitor_loop(self):
        self.is_running = True
        logger.info("PC Monitor started.")
        # Prime the CPU percent call
        psutil.cpu_percent()
        
        while self.is_running:
            try:
                if len(manager.active_connections) > 0:
                    metrics = await self.collect_metrics()
                    await manager.broadcast_json(metrics)
                    logger.debug(f"Broadcasted metrics: {metrics}")
                await asyncio.sleep(self.interval_sec)
            except asyncio.CancelledError:
                self.is_running = False
                logger.info("PC Monitor stopped.")
                break
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                await asyncio.sleep(self.interval_sec)

    def start_pomodoro(self, duration_sec=1500):
        self.pomodoro_active = True
        self.pomodoro_time_left = duration_sec

    def stop_pomodoro(self):
        self.pomodoro_active = False
        self.pomodoro_time_left = 0

pc_monitor = PCMonitor()
