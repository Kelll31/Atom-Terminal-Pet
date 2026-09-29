"""Панель Патрика в собственном окне, а не во вкладке браузера.

Окно рисует pywebview поверх системного WebView2 (тот же движок, что у Edge,
в Windows 11 он предустановлен). Это настоящее окно приложения: своя иконка,
своя кнопка на панели задач, никакой адресной строки и чужих вкладок.

Почему отдельным процессом. И pystray, и pywebview требуют главного потока с
собственным циклом сообщений, а главный поток у нас занят треем. Поэтому окно
запускается как дочерний процесс: `AtomPet.exe --panel` в сборке или
`python tray_app.py --panel` из исходников.

Если pywebview или WebView2 в системе нет, окно открывает Edge в режиме
приложения (`--app=`) — внешне то же самое окно без вкладок и адресной строки.
Совсем в крайнем случае остаётся обычный браузер.
"""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys
import webbrowser

logger = logging.getLogger("panel.window")

WINDOW_TITLE = "Патрик"
WINDOW_SIZE = (1180, 800)
MIN_SIZE = (900, 600)

# Ярлык, которым дочерний процесс отличает «покажи окно» от обычного запуска
PANEL_FLAG = "--panel"

SW_RESTORE = 9


def open_panel(url: str) -> str:
    """Показывает панель. Возвращает способ, которым это удалось сделать."""
    if focus_existing():
        return "focus"

    if _spawn_window_process(url):
        return "window"

    if _open_app_mode(url):
        return "app"

    webbrowser.open(url)
    return "browser"


def focus_existing() -> bool:
    """Поднимает уже открытое окно панели, если оно есть."""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, WINDOW_TITLE)
        if not hwnd:
            return False
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception as e:  # noqa: BLE001 — не Windows или окно исчезло
        logger.debug(f"Не удалось найти окно панели: {e}")
        return False


def run_window(url: str) -> int:
    """Главный поток дочернего процесса: создаёт окно и не выходит из него."""
    try:
        import webview
    except ImportError:
        logger.warning("pywebview не установлен — открываю окно Edge")
        return 0 if _open_app_mode(url) else 1

    webview.create_window(
        WINDOW_TITLE,
        url,
        width=WINDOW_SIZE[0],
        height=WINDOW_SIZE[1],
        min_size=MIN_SIZE,
        background_color="#0B1120",   # тот же фон, что у панели: без белой вспышки
        text_select=True,
    )
    try:
        webview.start()
    except Exception as e:  # noqa: BLE001 — нет WebView2 Runtime и т.п.
        logger.error(f"Окно не открылось ({e}), показываю панель в режиме приложения")
        return 0 if _open_app_mode(url) else 1
    return 0


# ── внутреннее ─────────────────────────────────────────────────────────────
def _spawn_window_process(url: str) -> bool:
    """Запускает дочерний процесс с окном."""
    if not _webview_available():
        return False

    if getattr(sys, "frozen", False):
        command = [sys.executable, PANEL_FLAG, url]
    else:
        entry = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tray_app.py")
        command = [sys.executable, entry, PANEL_FLAG, url]

    try:
        subprocess.Popen(command, close_fds=True)
        return True
    except Exception as e:  # noqa: BLE001
        logger.error(f"Не удалось запустить окно панели: {e}")
        return False


def _webview_available() -> bool:
    from importlib.util import find_spec

    try:
        return find_spec("webview") is not None
    except Exception:  # noqa: BLE001
        return False


def _open_app_mode(url: str) -> bool:
    """Окно браузера без вкладок и адресной строки — запасной вариант."""
    width, height = WINDOW_SIZE
    profile = os.path.join(os.environ.get("LOCALAPPDATA", ""), "AtomTerminalPet", "panel-profile")

    for browser in _app_mode_browsers():
        try:
            subprocess.Popen(
                [
                    browser,
                    f"--app={url}",
                    f"--window-size={width},{height}",
                    f"--user-data-dir={profile}",
                    "--no-first-run",
                ],
                close_fds=True,
            )
            return True
        except Exception as e:  # noqa: BLE001 — этого браузера нет, пробуем следующий
            logger.debug(f"{browser}: {e}")
    return False


def _app_mode_browsers() -> list[str]:
    candidates = []
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if not base:
            continue
        candidates.append(os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"))
        candidates.append(os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"))
    return [path for path in candidates if os.path.exists(path)]
