import asyncio
import logging
import shutil
import subprocess
import time

import psutil

from core.ws_manager import manager

logger = logging.getLogger("monitor.pc_monitor")

try:
    import GPUtil

    HAS_GPUTIL = True
except Exception:  # GPUtil ломается на Python 3.13+ (нет distutils)
    GPUtil = None
    HAS_GPUTIL = False

try:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    )

    HAS_WINSDK = True
except ImportError:
    HAS_WINSDK = False
    logger.warning("winrt не найден — информация о плеере недоступна")


class PCMonitor:
    def __init__(self, interval_sec=2.0):
        self.interval_sec = interval_sec
        self.is_running = False

        # Последние измеренные метрики — их читает агент и правила,
        # чтобы не опрашивать железо на каждый запрос.
        self._latest: dict = {
            "cpu": 0,
            "ram": 0,
            "gpu": 0,
            "temp": 0,
            "spotify": "",
            "ts": 0.0,
        }

        # Кэш опроса видеокарты
        self._gpu_cache: tuple[int, int] = (0, 0)
        self._gpu_cache_ts: float = 0.0

        # Помодоро
        self.pomodoro_active = False
        self.pomodoro_time_left = 0

    def latest_metrics(self) -> dict:
        return dict(self._latest)

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

    def _read_nvidia_smi(self) -> tuple[int, int]:
        """(загрузка %, температура °C) с кэшем — чтобы не дёргать процесс каждые 2 с."""
        now = time.time()
        if now - self._gpu_cache_ts < 5.0:
            return self._gpu_cache

        self._gpu_cache_ts = now
        exe = shutil.which("nvidia-smi")
        if not exe:
            self._gpu_cache = (0, 0)
            return self._gpu_cache

        try:
            output = subprocess.run(
                [exe, "--query-gpu=utilization.gpu,temperature.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=4,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).stdout.strip().splitlines()
            if output:
                load, temp = (int(float(v)) for v in output[0].split(",")[:2])
                self._gpu_cache = (load, temp)
        except Exception as e:
            logger.debug(f"nvidia-smi недоступен: {e}")
            self._gpu_cache = (0, 0)
        return self._gpu_cache

    def get_gpu_usage(self):
        if HAS_GPUTIL:
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    return int(gpus[0].load * 100)
            except Exception:
                pass
        return self._read_nvidia_smi()[0]

    def get_gpu_temp(self):
        if HAS_GPUTIL:
            try:
                gpus = GPUtil.getGPUs()
                if gpus and gpus[0].temperature:
                    return int(gpus[0].temperature)
            except Exception:
                pass
        return self._read_nvidia_smi()[1]

    def get_cpu_temp(self):
        """На Windows psutil обычно не отдаёт температуру CPU без WMI/OHM,
        поэтому используем температуру GPU как индикатор нагрева корпуса."""
        if hasattr(psutil, "sensors_temperatures"):
            try:
                temps = psutil.sensors_temperatures() or {}
                for key in ("coretemp", "k10temp", "acpitz"):
                    if temps.get(key):
                        return int(temps[key][0].current)
            except Exception:
                pass
        return self.get_gpu_temp()

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
            "temp": temp,
        }

        media = await self.get_media_info()
        if media:
            payload["spotify"] = media

        if self.pomodoro_active:
            payload["time_left"] = self.pomodoro_time_left
            self.pomodoro_time_left = max(
                0, self.pomodoro_time_left - int(self.interval_sec)
            )
            if self.pomodoro_time_left == 0:
                self.pomodoro_active = False

        self._latest = {
            "cpu": cpu,
            "ram": ram,
            "gpu": gpu,
            "temp": temp,
            "spotify": media or "",
            "ts": time.time(),
        }
        return payload

    async def monitor_loop(self):
        from core.events import bus

        self.is_running = True
        logger.info("Мониторинг ПК запущен.")
        psutil.cpu_percent()  # первый вызов задаёт точку отсчёта

        while self.is_running:
            try:
                metrics = await self.collect_metrics()
                if manager.active_connections or manager.device_on_wifi:
                    await bus.emit_raw(metrics)
                await asyncio.sleep(self.interval_sec)
            except asyncio.CancelledError:
                self.is_running = False
                logger.info("Мониторинг ПК остановлен.")
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле мониторинга: {e}")
                await asyncio.sleep(self.interval_sec)

    def start_pomodoro(self, duration_sec=1500):
        self.pomodoro_active = True
        self.pomodoro_time_left = duration_sec

    def stop_pomodoro(self):
        self.pomodoro_active = False
        self.pomodoro_time_left = 0


pc_monitor = PCMonitor()
