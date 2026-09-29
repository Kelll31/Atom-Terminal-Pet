"""Сбор метрик компьютера и их рассылка питомцу и панели.

Весь опрос железа синхронный и местами медленный (psutil, а главное — запуск
процесса `nvidia-smi`), поэтому он вынесен в отдельный поток: пока метрики
собираются, event loop продолжает гнать аудио на устройство и принимать кадры
микрофона. Раньше сбор шёл прямо в цикле, и при подвисшем видеодрайвере
питомец замолкал на все 4 секунды таймаута подпроцесса.
"""

import asyncio
import logging
import shutil
import subprocess
import sys
import threading
import time

import psutil

from core.serial_manager import serial_manager
from core.ws_manager import manager

logger = logging.getLogger("monitor.pc_monitor")

# GPUtil сознательно не используем: под капотом он запускает тот же nvidia-smi,
# но без кэша и по два раза за цикл (отдельно загрузка, отдельно температура).
# На Python 3.13+ он к тому же не импортируется — там больше нет distutils.

try:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    )

    HAS_WINSDK = True
except ImportError:
    HAS_WINSDK = False
    logger.warning("winrt не найден — информация о плеере недоступна")

# Окно консоли от nvidia-smi моргало поверх всех окон при запуске из трея,
# где у процесса нет своей консоли. Флаг есть только в Windows-сборке Python.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


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
        # Сбор метрик может идти сразу из двух мест (цикл мониторинга и
        # инструмент get_pc_status), а второй одновременный nvidia-smi — это
        # лишний процесс и порванный кэш. Замок дешевле, чем дубль запуска.
        self._gpu_lock = threading.Lock()
        # Путь к nvidia-smi ищем один раз: which() обходит весь PATH.
        self._nvidia_smi: str | None = None
        self._nvidia_smi_checked = False

        # Помодоро. Храним момент окончания, а не «сколько осталось»:
        # раньше остаток уменьшался внутри collect_metrics, и каждый вызов
        # инструмента get_pc_status незаметно подкручивал таймер вперёд.
        self.pomodoro_active = False
        self._pomodoro_deadline = 0.0  # time.monotonic()
        self._pomodoro_total = 0

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
        """(загрузка %, температура °C) с кэшем — чтобы не дёргать процесс каждые 2 с.

        Блокирующая функция: вызывать только из рабочего потока.
        """
        with self._gpu_lock:
            now = time.time()
            if now - self._gpu_cache_ts < 5.0:
                return self._gpu_cache

            self._gpu_cache_ts = now
            if not self._nvidia_smi_checked:
                self._nvidia_smi = shutil.which("nvidia-smi")
                self._nvidia_smi_checked = True
                if not self._nvidia_smi:
                    logger.info("nvidia-smi не найден — метрики GPU будут нулевыми")
            if not self._nvidia_smi:
                self._gpu_cache = (0, 0)
                return self._gpu_cache

            try:
                output = subprocess.run(
                    [self._nvidia_smi, "--query-gpu=utilization.gpu,temperature.gpu",
                     "--format=csv,noheader,nounits"],
                    capture_output=True,
                    text=True,
                    timeout=4,
                    # Без явного DEVNULL дочерний процесс наследует stdin
                    # родителя: из-под трея это закрытый дескриптор, и запуск
                    # иногда падал ещё до вывода.
                    stdin=subprocess.DEVNULL,
                    creationflags=_NO_WINDOW,
                ).stdout.strip().splitlines()
                if output:
                    load, temp = (int(float(v)) for v in output[0].split(",")[:2])
                    self._gpu_cache = (load, temp)
            except Exception as e:
                logger.debug(f"nvidia-smi недоступен: {e}")
                self._gpu_cache = (0, 0)
            return self._gpu_cache

    def get_gpu_usage(self):
        return self._read_nvidia_smi()[0]

    def get_gpu_temp(self):
        return self._read_nvidia_smi()[1]

    @staticmethod
    def _sensors_temp() -> int | None:
        """Температура CPU по датчикам psutil или None, если их нет."""
        if hasattr(psutil, "sensors_temperatures"):
            try:
                temps = psutil.sensors_temperatures() or {}
                for key in ("coretemp", "k10temp", "acpitz"):
                    if temps.get(key):
                        return int(temps[key][0].current)
            except Exception:
                pass
        return None

    def get_cpu_temp(self):
        """На Windows psutil обычно не отдаёт температуру CPU без WMI/OHM,
        поэтому используем температуру GPU как индикатор нагрева корпуса."""
        temp = self._sensors_temp()
        return temp if temp is not None else self.get_gpu_temp()

    def _collect_sync(self) -> dict[str, int]:
        """Весь блокирующий опрос железа в одном месте — его гоняем в потоке.

        Первый замер стоит около 90 мс, а с зависшим драйвером видеокарты —
        до 4 секунд таймаута nvidia-smi. В event loop этому места нет.
        """
        cpu = int(psutil.cpu_percent(interval=None))
        ram = int(psutil.virtual_memory().percent)
        # Оба значения берём из одного вызова nvidia-smi: кэш общий,
        # так что второй заход всё равно вернул бы те же цифры.
        gpu, gpu_temp = self._read_nvidia_smi()
        temp = self.get_cpu_temp()
        return {"cpu": cpu, "ram": ram, "gpu": gpu, "temp": temp or gpu_temp}

    async def collect_metrics(self):
        metrics = await asyncio.to_thread(self._collect_sync)
        cpu, ram = metrics["cpu"], metrics["ram"]
        gpu, temp = metrics["gpu"], metrics["temp"]

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
            # Остаток считается от дедлайна, поэтому лишний вызов
            # collect_metrics больше не «съедает» минуты таймера.
            time_left = self.pomodoro_time_left
            payload["time_left"] = time_left
            if time_left == 0:
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
        from core.serial_manager import serial_manager

        self.is_running = True
        logger.info("Мониторинг ПК запущен.")
        psutil.cpu_percent()  # первый вызов задаёт точку отсчёта

        while self.is_running:
            try:
                metrics = await self.collect_metrics()
                # Питомец по USB — основной сценарий: трей запущен, панель
                # закрыта. Без проверки serial_manager метрики в этом режиме
                # не уходили вовсе, и график нагрузки на экране был пустым.
                if (
                    manager.active_connections
                    or manager.device_on_wifi
                    or serial_manager.is_connected
                ):
                    await bus.emit_raw(metrics)
                await asyncio.sleep(self.interval_sec)
            except asyncio.CancelledError:
                self.is_running = False
                logger.info("Мониторинг ПК остановлен.")
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле мониторинга: {e}")
                await asyncio.sleep(self.interval_sec)

    # ── Помодоро ───────────────────────────────────────────────────────────
    @property
    def pomodoro_time_left(self) -> int:
        """Остаток текущего помодоро в секундах (0, если таймер не идёт).

        Только для чтения: источник правды — дедлайн, а не счётчик, который
        кто-то мог бы забыть уменьшить или уменьшить дважды.
        """
        if not self.pomodoro_active:
            return 0
        return max(0, int(round(self._pomodoro_deadline - time.monotonic())))

    @property
    def pomodoro_minutes_left(self) -> int:
        """Остаток в минутах, округлённый вверх — для пункта меню в трее.

        Округление вверх, чтобы последние 40 секунд показывались как «1 мин»,
        а не как «0 мин» при живом таймере.
        """
        return -(-self.pomodoro_time_left // 60)

    def pomodoro_status(self) -> dict:
        """Снимок состояния таймера для UI (трей, панель): без лишних свойств."""
        seconds = self.pomodoro_time_left
        return {
            "active": self.pomodoro_active and seconds > 0,
            "seconds_left": seconds,
            "minutes_left": -(-seconds // 60),
            "total_sec": self._pomodoro_total,
        }

    def start_pomodoro(self, duration_sec=1500):
        self.pomodoro_active = True
        self._pomodoro_total = int(duration_sec)
        self._pomodoro_deadline = time.monotonic() + duration_sec

    def stop_pomodoro(self):
        self.pomodoro_active = False
        self._pomodoro_deadline = 0.0
        self._pomodoro_total = 0


pc_monitor = PCMonitor()
