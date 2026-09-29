"""Инструменты управления ПК (Windows): процессы, громкость, окна, клавиши.

Уровни риска здесь местами зависят от аргументов, а не от инструмента:
open_program без аргументов открывает файл, а с аргументами запускает
произвольный процесс; clipboard на чтение безобиден, а на запись становится
первым звеном цепочки «положить в буфер → win+r → вставить → enter».
Такие случаи описаны функцией risk_for у соответствующего инструмента.
"""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
import time
from typing import Any

import psutil
from pydantic import BaseModel, Field

from ai.tools.base import ToolError, no_window_flags, registry

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


# Процессы, завершение которых роняет Windows в синий экран или выкидывает
# пользователя из сеанса. Проверять список надо для КАЖДОГО кандидата, а не
# только для строки запроса: поиск идёт по подстроке, поэтому цель «csrss»
# сама по себе в списке не значится, но находит csrss.exe.
PROTECTED_PROCESSES = {
    "system",
    "system idle process",
    "registry",
    "memory compression",
    "smss.exe",
    "csrss.exe",
    "wininit.exe",
    "winlogon.exe",
    "services.exe",
    "lsass.exe",
    "lsaiso.exe",
    "svchost.exe",
    "fontdrvhost.exe",
    "dwm.exe",
}


def _is_protected(name: str | None) -> bool:
    return (name or "").strip().lower() in PROTECTED_PROCESSES


@registry.tool(
    name="kill_process",
    description="Завершает зависший процесс по имени или PID. Необратимо — несохранённые данные будут потеряны.",
    args_model=KillProcessArgs,
    risk="danger",
    category="system",
)
def kill_process(target: str, all_matching: bool = False) -> str:
    target = str(target).strip()
    if not target:
        raise ToolError("Не указано, какой процесс завершать.")
    if _is_protected(target):
        raise ToolError(f"Процесс {target} системный, трогать его нельзя.")

    killed: list[str] = []
    if target.isdigit():
        try:
            p = psutil.Process(int(target))
            name = p.name()
            if _is_protected(name):
                raise ToolError(
                    f"PID {target} — это системный процесс {name}, его завершение уронит Windows."
                )
            p.terminate()
            killed.append(f"{name} (PID {target})")
        except psutil.NoSuchProcess:
            raise ToolError(f"Процесса с PID {target} нет.")
        except psutil.AccessDenied:
            raise ToolError(f"Нет прав завершить PID {target}. Нужен запуск от администратора.")
    else:
        needle = target.lower()
        exact: list[Any] = []
        partial: list[Any] = []
        blocked: set[str] = set()

        for p in psutil.process_iter(["pid", "name"]):
            try:
                name = (p.info["name"] or "")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            lowered = name.lower()
            if needle not in lowered:
                continue
            # Защищённые отсеиваем ДО завершения и по имени кандидата:
            # запрос «csrss» иначе нашёл бы csrss.exe и убил систему.
            if _is_protected(name):
                blocked.add(name)
                continue
            # Точное совпадение сильнее подстрочного: «code» должен убить
            # code.exe, а не vscode-helper.exe, если первый существует.
            (exact if lowered in (needle, f"{needle}.exe") else partial).append(p)

        for p in exact or partial:
            try:
                info = p.info
                p.terminate()
                killed.append(f"{info['name']} (PID {info['pid']})")
                if not all_matching:
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if not killed and blocked:
            raise ToolError(
                f"Под '{target}' подходят только системные процессы "
                f"({', '.join(sorted(blocked))}) — завершать их нельзя."
            )

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


# Клавиши, которые превращают «нажать сочетание» в «запустить что угодно»
# или «закрыть чужое окно без сохранения»:
#   win           — открывает меню «Пуск» и win+r («Выполнить»),
#   enter/return  — подтверждает то, что уже набрано в чужом окне,
#   alt+f4        — закрывает активное приложение.
_KEYS_ESCALATING = {"win", "winleft", "winright", "super", "command", "enter", "return"}


def _keys_combo(keys: str) -> list[str]:
    return [k.strip().lower() for k in str(keys).replace(" ", "").split("+") if k.strip()]


def _press_keys_risk(args: dict[str, Any]) -> str:
    combo = set(_keys_combo(args.get("keys", "")))
    if combo & _KEYS_ESCALATING:
        return "danger"
    if "alt" in combo and "f4" in combo:
        return "danger"
    return "caution"


@registry.tool(
    name="press_keys",
    description=(
        "Нажимает сочетание клавиш в активном окне (ctrl+s, alt+tab, ctrl+shift+t). "
        "Сочетания с win, enter и alt+f4 требуют подтверждения: ими можно запустить "
        "произвольную программу или закрыть окно без сохранения."
    ),
    args_model=PressKeysArgs,
    risk="caution",
    risk_for=_press_keys_risk,
    category="system",
)
def press_keys(keys: str) -> str:
    try:
        import pyautogui

        combo = _keys_combo(keys)
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


def _open_program_risk(args: dict[str, Any]) -> str:
    """С аргументами командной строки это уже не «открыть», а «выполнить».

    'code' и 'D:/проект/отчёт.docx' — бытовые действия. А вот
    'powershell' + '-enc <base64>' или 'cmd' + '/c ...' — это произвольный код,
    и такое должно спрашивать подтверждение в любом режиме, кроме full.
    """
    return "danger" if str(args.get("args") or "").strip() else "caution"


@registry.tool(
    name="open_program",
    description=(
        "Запускает программу, открывает файл, папку или URL в приложении по умолчанию. "
        "Примеры target: 'code', 'notepad', 'https://github.com', 'D:/projects/app'. "
        "Запуск с аргументами командной строки требует подтверждения."
    ),
    args_model=OpenProgramArgs,
    risk="caution",
    risk_for=_open_program_risk,
    category="system",
)
def open_program(target: str, args: str = "") -> str:
    target = target.strip()
    args = (args or "").strip()
    if not target:
        raise ToolError("Не указано, что открывать.")

    try:
        # Ссылки — только http/https и только в браузер. Схемы вроде file://,
        # javascript: или ms-settings: сюда не пускаем: через них открывается
        # локальный файл или системная панель в обход всех проверок.
        if target.lower().startswith(("http://", "https://")):
            import webbrowser

            webbrowser.open(target)
            return f"Открыл в браузере: {target}"
        if "://" in target.split(" ", 1)[0]:
            raise ToolError(
                f"Схема в '{target}' не поддерживается — разрешены только http:// и https://."
            )

        expanded = os.path.expandvars(os.path.expanduser(target))

        # Файл или папка без аргументов — отдаём проводнику через os.startfile.
        # Это ShellExecute с ОДНИМ параметром-путём: разбора командной строки
        # там нет вовсе, поэтому кавычки и амперсанды в имени файла безопасны.
        if not args and os.path.exists(expanded):
            os.startfile(expanded)  # noqa: S606 — путь идёт отдельным параметром
            return f"Открыл: {expanded}"

        # Иначе это запуск программы. Собираем СПИСОК аргументов и запускаем
        # без оболочки: posix=False у shlex обязателен, иначе на Windows
        # обратные слэши пути съедаются как escape-последовательности.
        executable = expanded if os.path.exists(expanded) else (shutil.which(target) or "")
        if not executable:
            raise ToolError(
                f"'{target}' не найден ни как файл, ни как программа в PATH."
            )

        argv = [executable]
        if args:
            argv += shlex.split(args, posix=False)

        subprocess.Popen(  # noqa: S603 — shell=False, аргументы списком
            argv,
            shell=False,
            stdin=subprocess.DEVNULL,
            creationflags=no_window_flags(),
        )
        return f"Запустил: {' '.join(argv)}"
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"не удалось запустить '{target}': {e}")


class ClipboardArgs(BaseModel):
    text: str = Field("", description="Текст для записи в буфер обмена. Пусто — только прочитать.")


def _clipboard_risk(args: dict[str, Any]) -> str:
    """Запись в буфер — danger, чтение — caution.

    Запись опасна не сама по себе, а в связке: «положить команду в буфер» +
    press_keys win+r + ctrl+v + enter выполняет что угодно, причём каждый шаг
    по отдельности выглядел безобидно. Чтение — caution, потому что в буфере
    бывает пароль из менеджера паролей, а содержимое уходит в облачную модель.
    """
    return "danger" if str(args.get("text") or "") else "caution"


@registry.tool(
    name="clipboard",
    description=(
        "Читает буфер обмена, а если передан text — записывает его туда. "
        "В буфере может лежать пароль, поэтому чтение подтверждается; запись — "
        "тем более, ею можно подготовить команду для вставки в чужое окно."
    ),
    args_model=ClipboardArgs,
    risk="caution",
    risk_for=_clipboard_risk,
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
