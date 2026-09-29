"""Патрик как приложение Windows: значок в трее, никакой консоли.

Сервер FastAPI поднимается в фоновом потоке того же процесса, а главный поток
занят циклом сообщений трея. Отдельный процесс не нужен: так нечему осиротеть,
если приложение закрыть, и выход гарантированно проходит через штатное
завершение — MCP-серверы и COM-порт освобождаются, а не остаются висеть.

Запуск из исходников для отладки:

    backend/venv/Scripts/pythonw.exe backend/tray_app.py
"""

from __future__ import annotations

import ctypes
import logging
import os
import socket
import sys
import threading
from logging.handlers import RotatingFileHandler

# В сборке без консоли стандартные потоки не существуют, и первый же print()
# внутри любой библиотеки уронил бы приложение.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import paths  # noqa: E402
from panel_window import PANEL_FLAG  # noqa: E402

APP_TITLE = "Патрик"
MUTEX_NAME = "Local\\AtomTerminalPet"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "AtomTerminalPet"

# Слушаем все интерфейсы: питомец подключается к серверу по Wi-Fi, на localhost
# он бы до него не достучался. Панель при этом открываем по петле.
BIND_HOST = "0.0.0.0"
PANEL_HOST = "127.0.0.1"
PORT = int(os.environ.get("ATOM_PORT", "8000"))

logger = logging.getLogger("tray")
_mutex_handle = None


# ── Единственный экземпляр ──────────────────────────────────────────────────
def acquire_single_instance() -> bool:
    """False, если приложение уже запущено."""
    global _mutex_handle
    kernel32 = ctypes.windll.kernel32
    _mutex_handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    ERROR_ALREADY_EXISTS = 183
    return kernel32.GetLastError() != ERROR_ALREADY_EXISTS


# ── Журнал ──────────────────────────────────────────────────────────────────
def log_path() -> str:
    return paths.data("logs", "app.log")


def setup_logging() -> None:
    handler = RotatingFileHandler(log_path(), maxBytes=2 * 1024 * 1024,
                                  backupCount=3, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    # main.py вызывает basicConfig, но тот ничего не делает, если обработчик
    # уже есть, — поэтому вывод не уедет в несуществующий stdout.


# ── Автозапуск ──────────────────────────────────────────────────────────────
def _autostart_command() -> str:
    if paths.is_frozen():
        return f'"{sys.executable}"'
    return f'"{sys.executable}" "{os.path.abspath(__file__)}"'


def autostart_enabled() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, RUN_VALUE)
            return bool(value)
    except OSError:
        return False


def set_autostart(enabled: bool) -> None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, _autostart_command())
            else:
                try:
                    winreg.DeleteValue(key, RUN_VALUE)
                except FileNotFoundError:
                    pass
    except OSError as exc:
        logger.error(f"Не удалось изменить автозапуск: {exc}")


# ── Сервер ──────────────────────────────────────────────────────────────────
class ServerRunner:
    """Uvicorn в фоновом потоке. Сигналы он в неглавном потоке не трогает."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self._server = None
        self._thread: threading.Thread | None = None
        self.error: str | None = None

    @property
    def started(self) -> bool:
        return bool(self._server is not None and getattr(self._server, "started", False))

    @property
    def alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def port_taken(self) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((self.host, self.port))
                return False
            except OSError:
                return True

    def start(self) -> None:
        # Проверяем порт заранее: иначе uvicorn завершает поток через SystemExit,
        # и в трее просто ничего не происходит без объяснения причины.
        if self.port_taken():
            self.error = f"Порт {self.port} занят другой программой"
            logger.error(self.error)
            return

        import uvicorn

        from main import app

        self.error = None
        config = uvicorn.Config(app, host=self.host, port=self.port,
                                log_config=None, access_log=False)
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._run, name="uvicorn", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            self._server.run()
        except BaseException as exc:   # SystemExit от uvicorn тоже сюда
            self.error = str(exc) or exc.__class__.__name__
            logger.exception("Сервер остановился с ошибкой")

    def stop(self, timeout: float = 20.0) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout)
            if self._thread.is_alive():
                logger.warning("Сервер не остановился за отведённое время")
        self._server = None
        self._thread = None


# ── Трей ────────────────────────────────────────────────────────────────────
def main() -> int:
    paths.ensure_dirs()
    setup_logging()

    # Окно панели — дочерний процесс этого же exe. Мьютекс единственного
    # экземпляра он не трогает: сервер и трей остаются в родительском процессе.
    if PANEL_FLAG in sys.argv:
        from panel_window import run_window

        args = [a for a in sys.argv[1:] if a != PANEL_FLAG]
        return run_window(args[0] if args else f"http://{PANEL_HOST}:{PORT}")

    if not acquire_single_instance():
        ctypes.windll.user32.MessageBoxW(
            None, "Патрик уже запущен — значок в трее, рядом с часами.",
            APP_TITLE, 0x40
        )
        return 0

    import pystray

    from tray_icon import build_image

    runner = ServerRunner(BIND_HOST, PORT)
    panel_url = f"http://{PANEL_HOST}:{PORT}"

    def status_text(_item=None) -> str:
        if runner.error:
            return f"Ошибка: {runner.error}"
        if runner.started:
            return f"Работает на {panel_url}"
        if runner.alive:
            return "Запускается…"
        return "Остановлен"

    def on_open(icon, _item=None):
        if not runner.started:
            icon.notify(status_text(), APP_TITLE)
            return

        from core.settings import settings_store

        if not settings_store.get("panel_window", True):
            import webbrowser

            webbrowser.open(panel_url)
            return

        from panel_window import open_panel

        way = open_panel(panel_url)
        if way == "browser":
            icon.notify("Окно панели недоступно — открыл в браузере", APP_TITLE)

    def on_open_data(_icon=None, _item=None):
        os.startfile(paths.DATA_ROOT)

    def on_open_log(icon, _item=None):
        target = log_path()
        if os.path.exists(target):
            os.startfile(target)
        else:
            icon.notify("Журнал ещё пуст", APP_TITLE)

    def on_toggle_autostart(_icon=None, _item=None):
        set_autostart(not autostart_enabled())

    def on_restart(icon, _item=None):
        icon.notify("Перезапускаю сервер…", APP_TITLE)
        runner.stop()
        runner.start()

    def on_quit(icon, _item=None):
        icon.visible = False
        runner.stop()
        icon.stop()

    # ── Обновление ──────────────────────────────────────────────────────────
    from core.updater import updater

    def update_text(_item=None) -> str:
        info = updater.state.available
        if updater.state.downloading:
            return f"Скачиваю обновление… {updater.state.progress}%"
        if info:
            return f"Обновить до {info.version}"
        return f"Проверить обновления (сейчас {updater.state.current})"

    def on_update(icon, _item=None):
        """Первый клик — проверка, второй (когда версия найдена) — установка."""
        import asyncio

        def work():
            try:
                if updater.state.available and updater.state.installable:
                    icon.notify(f"Скачиваю версию {updater.state.available.version}…", APP_TITLE)
                    asyncio.run(updater.install())
                    return

                icon.notify("Проверяю обновления…", APP_TITLE)
                state = asyncio.run(updater.check(force=True))
                if state.last_error:
                    icon.notify(f"Не удалось проверить: {state.last_error}", APP_TITLE)
                elif state.available and state.installable:
                    icon.notify(
                        f"Доступна версия {state.available.version}. "
                        "Нажмите пункт меню ещё раз, чтобы обновиться.",
                        APP_TITLE,
                    )
                elif state.available:
                    icon.notify(
                        f"Вышла версия {state.available.version}, "
                        "но эта копия запущена из исходников — обновитесь через git.",
                        APP_TITLE,
                    )
                else:
                    icon.notify(f"У вас последняя версия ({state.current})", APP_TITLE)
            except Exception as exc:  # noqa: BLE001 — сеть, отказ от UAC
                logger.exception("Обновление не удалось")
                icon.notify(f"Обновление не удалось: {exc}", APP_TITLE)

        threading.Thread(target=work, name="updater", daemon=True).start()

    menu = pystray.Menu(
        pystray.MenuItem("Открыть панель", on_open, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(status_text, None, enabled=False),
        pystray.MenuItem("Папка с данными", on_open_data),
        pystray.MenuItem("Журнал работы", on_open_log),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(update_text, on_update),
        pystray.MenuItem("Запускать вместе с Windows", on_toggle_autostart,
                         checked=lambda _item: autostart_enabled()),
        pystray.MenuItem("Перезапустить сервер", on_restart),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Выход", on_quit),
    )

    icon = pystray.Icon("atom-terminal-pet", build_image(64), APP_TITLE, menu)

    # Перед установкой обновления приложение должно закрыться само: иначе
    # установщик снимет его через taskkill, не дав завершить MCP и COM-порт.
    updater.set_quit_handler(lambda: on_quit(icon))

    def on_ready(icon):
        icon.visible = True
        runner.start()
        if runner.error:
            icon.notify(runner.error, APP_TITLE)
        else:
            icon.notify(f"Панель: {panel_url}", APP_TITLE)

    logger.info(f"Запуск в трее, каталог данных: {paths.DATA_ROOT}")
    icon.run(setup=on_ready)
    logger.info("Выход")
    return 0


if __name__ == "__main__":
    sys.exit(main())
