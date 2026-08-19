"""Инструменты управления ПК (Windows): процессы, громкость, окна, клавиши."""

from __future__ import annotations

import logging
import os
import subprocess
import time

import psutil
from pydantic import BaseModel, Field

from ai.tools.base import ToolError, registry

logger = logging.getLogger("ai.tools.system")


# ── Состояние ПК ───────────────────────────────────────────────────────────
class EmptyArgs(BaseModel):
    pass


@registry.tool(
    name="get_pc_status",
    description=(
        "Текущее состояние компьютера: загрузка CPU/RAM/GPU, температура, аптайм, "
        "заряд батареи, свободное место на дисках и что играет в плеере."
    ),
    args_model=EmptyArgs,
    risk="safe",
    category="system",
)
async def get_pc_status() -> str:
    from monitor.pc_monitor import pc_monitor

    m = await pc_monitor.collect_metrics()
    uptime_h = (time.time() - psutil.boot_time()) / 3600

    disks = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append(f"{part.device.rstrip(os.sep)} {usage.percent}% занято "
                         f"(свободно {usage.free / 1024 ** 3:.0f} ГБ)")
        except Exception:
            continue

    lines = [
        f"CPU: {m['cpu']}%",
        f"RAM: {m['ram']}%",
        f"GPU: {m['gpu']}%",
        f"Температура CPU: {m['temp']}°C",
        f"Аптайм: {uptime_h:.1f} ч",
        f"Диски: {'; '.join(disks) or 'нет данных'}",
    ]
    battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    if battery:
        lines.append(
            f"Батарея: {battery.percent}%" + (" (от сети)" if battery.power_plugged else "")
        )
    if m.get("spotify"):
        lines.append(f"Сейчас играет: {m['spotify']}")
    return "\n".join(lines)


class ListProcessesArgs(BaseModel):
    sort_by: str = Field("cpu", description="Сортировка: 'cpu' или 'memory'")
    limit: int = Field(10, description="Сколько процессов вернуть (1-30)")
    name_filter: str = Field("", description="Показать только процессы, содержащие эту подстроку в имени")


@registry.tool(
    name="list_processes",
    description="Список самых тяжёлых процессов с PID, именем, %CPU и памятью в МБ.",
    args_model=ListProcessesArgs,
    risk="safe",
    category="system",
)
def list_processes(sort_by: str = "cpu", limit: int = 10, name_filter: str = "") -> str:
    limit = max(1, min(30, limit))
    procs = []
    for p in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            info = p.info
            if name_filter and name_filter.lower() not in (info["name"] or "").lower():
                continue
            procs.append(
                {
                    "pid": info["pid"],
                    "name": info["name"] or "?",
                    "cpu": p.cpu_percent(None),
                    "mem_mb": round((info["memory_info"].rss if info["memory_info"] else 0) / 1024 ** 2),
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    key = "mem_mb" if sort_by.startswith("m") else "cpu"
    procs.sort(key=lambda x: x[key], reverse=True)
    top = procs[:limit]
    if not top:
        return "Подходящих процессов не найдено."
    return "\n".join(
        f"{p['pid']:>6}  {p['name'][:32]:<32} CPU {p['cpu']:>5.1f}%  RAM {p['mem_mb']:>6} МБ"
        for p in top
    )


class KillProcessArgs(BaseModel):
    target: str = Field(..., description="Имя процесса (chrome.exe) или PID")
    all_matching: bool = Field(False, description="Завершить все процессы с таким именем")


@registry.tool(
    name="kill_process",
    description="Завершает зависший процесс по имени или PID. Необратимо — несохранённые данные будут потеряны.",
    args_model=KillProcessArgs,
    risk="danger",
    category="system",
)
def kill_process(target: str, all_matching: bool = False) -> str:
    target = str(target).strip()
    protected = {"system", "csrss.exe", "wininit.exe", "winlogon.exe", "services.exe", "smss.exe"}
    if target.lower() in protected:
        raise ToolError(f"Процесс {target} системный, трогать его нельзя.")

    killed: list[str] = []
    if target.isdigit():
        try:
            p = psutil.Process(int(target))
            name = p.name()
            p.terminate()
            killed.append(f"{name} (PID {target})")
        except psutil.NoSuchProcess:
            raise ToolError(f"Процесса с PID {target} нет.")
        except psutil.AccessDenied:
            raise ToolError(f"Нет прав завершить PID {target}. Нужен запуск от администратора.")
    else:
        for p in psutil.process_iter(["pid", "name"]):
            try:
                if target.lower() in (p.info["name"] or "").lower():
                    p.terminate()
                    killed.append(f"{p.info['name']} (PID {p.info['pid']})")
                    if not all_matching:
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    if not killed:
        raise ToolError(f"Процесс '{target}' не найден.")
    return "Завершено: " + ", ".join(killed)


# ── Звук ───────────────────────────────────────────────────────────────────
class VolumeArgs(BaseModel):
    level: int = Field(..., description="Громкость 0-100")


@registry.tool(
    name="set_volume",
    description="Устанавливает громкость системы Windows (0-100).",
    args_model=VolumeArgs,
    risk="caution",
    category="system",
)
def set_volume(level: int) -> str:
    try:
        from ctypes import POINTER, cast

        from comtypes import CLSCTX_ALL, CoInitialize
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        CoInitialize()
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        level = max(0, min(100, int(level)))
        volume.SetMasterVolumeLevelScalar(level / 100.0, None)
        return f"Громкость: {level}%."
    except ImportError:
        raise ToolError("pycaw не установлен — управление громкостью недоступно.")
    except Exception as e:
        raise ToolError(f"не удалось изменить громкость: {e}")


class MediaArgs(BaseModel):
    command: str = Field(..., description="Одно из: play_pause, next, prev, mute, volume_up, volume_down")


_MEDIA_KEYS = {
    "play_pause": "playpause",
    "play": "playpause",
    "pause": "playpause",
    "next": "nexttrack",
    "prev": "prevtrack",
    "previous": "prevtrack",
    "mute": "volumemute",
    "volume_up": "volumeup",
    "volume_down": "volumedown",
}


@registry.tool(
    name="media_control",
    description="Управление плеером: play_pause, next, prev, mute, volume_up, volume_down.",
    args_model=MediaArgs,
    risk="caution",
    category="system",
)
def media_control(command: str) -> str:
    key = _MEDIA_KEYS.get(command.strip().lower())
    if not key:
        raise ToolError(f"Неизвестная команда '{command}'. Доступно: {', '.join(_MEDIA_KEYS)}")
    try:
        import pyautogui

        pyautogui.press(key)
        return f"Отправлено: {command}."
    except ImportError:
        raise ToolError("pyautogui не установлен.")


class PressKeysArgs(BaseModel):
    keys: str = Field(..., description="Сочетание клавиш через '+', например 'ctrl+shift+t' или 'win+d'")


@registry.tool(
    name="press_keys",
    description="Нажимает сочетание клавиш в активном окне (ctrl+s, alt+tab, win+d и т.п.).",
    args_model=PressKeysArgs,
    risk="caution",
    category="system",
)
def press_keys(keys: str) -> str:
    try:
        import pyautogui

        combo = [k.strip().lower() for k in keys.replace(" ", "").split("+") if k.strip()]
        if not combo:
            raise ToolError("Пустое сочетание клавиш.")
        pyautogui.hotkey(*combo)
        return f"Нажато: {'+'.join(combo)}."
    except ImportError:
        raise ToolError("pyautogui не установлен.")


# ── Запуск приложений ──────────────────────────────────────────────────────
class OpenProgramArgs(BaseModel):
    target: str = Field(..., description="Имя программы (code, notepad, chrome), путь к файлу или URL")
    args: str = Field("", description="Дополнительные аргументы командной строки")


@registry.tool(
    name="open_program",
    description=(
        "Запускает программу, открывает файл, папку или URL в приложении по умолчанию. "
        "Примеры target: 'code', 'notepad', 'https://github.com', 'D:/projects/app'."
    ),
    args_model=OpenProgramArgs,
    risk="caution",
    category="system",
)
def open_program(target: str, args: str = "") -> str:
    target = target.strip()
    if not target:
        raise ToolError("Не указано, что открывать.")
    try:
        if target.lower().startswith(("http://", "https://")):
            import webbrowser

            webbrowser.open(target)
            return f"Открыл в браузере: {target}"

        cmd = f'start "" "{target}" {args}'.strip()
        subprocess.Popen(cmd, shell=True)
        return f"Запустил: {target} {args}".strip()
    except Exception as e:
        raise ToolError(f"не удалось запустить '{target}': {e}")


class ClipboardArgs(BaseModel):
    text: str = Field("", description="Текст для записи в буфер обмена. Пусто — только прочитать.")


@registry.tool(
    name="clipboard",
    description="Читает буфер обмена, а если передан text — записывает его туда.",
    args_model=ClipboardArgs,
    risk="safe",
    category="system",
)
def clipboard(text: str = "") -> str:
    try:
        import pyperclip as clip
    except ImportError:
        raise ToolError("Буфер обмена недоступен: установите pyperclip.")

    if text:
        clip.copy(text)
        return f"В буфер обмена записано {len(text)} символов."
    content = clip.paste() or ""
    if not content:
        return "Буфер обмена пуст."
    return content[:4000]


class ActiveWindowArgs(BaseModel):
    pass


@registry.tool(
    name="get_active_window",
    description="Возвращает заголовок активного окна — полезно, чтобы понять, чем сейчас занят пользователь.",
    args_model=ActiveWindowArgs,
    risk="safe",
    category="system",
)
def get_active_window() -> str:
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value or "(без заголовка)"

        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            proc = psutil.Process(pid.value).name()
        except Exception:
            proc = "?"
        return f"{title} [{proc}]"
    except Exception as e:
        raise ToolError(f"не удалось получить активное окно: {e}")


__all__ = ["get_pc_status", "list_processes", "kill_process", "set_volume"]
