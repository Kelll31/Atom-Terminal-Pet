import os
import subprocess
import pyautogui
import psutil
import asyncio
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from langchain_core.tools import tool

@tool
def set_volume(level: int) -> str:
    """Устанавливает громкость системы Windows (0 до 100)."""
    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        
        level = max(0, min(100, level))
        volume.SetMasterVolumeLevelScalar(level / 100.0, None)
        return f"Громкость установлена на {level}%."
    except Exception as e:
        return f"Ошибка при установке громкости: {e}"

@tool
def open_program(program_name: str) -> str:
    """Открывает базовые программы в Windows."""
    try:
        subprocess.Popen(program_name, shell=True)
        return f"Программа {program_name} запущена."
    except Exception as e:
        return f"Ошибка при запуске программы {program_name}: {e}"

@tool
def kill_process(process_name: str) -> str:
    """Убивает процесс по его имени (например, 'chrome.exe')."""
    killed = 0
    try:
        for proc in psutil.process_iter(['name']):
            if process_name.lower() in proc.info['name'].lower():
                proc.kill()
                killed += 1
        return f"Убито процессов: {killed}" if killed > 0 else f"Процесс {process_name} не найден."
    except Exception as e:
        return f"Ошибка при завершении процесса: {e}"

@tool
def web_search(query: str) -> str:
    """Выполняет поиск в веб и возвращает результат."""
    # Dummy implementation for now, in real app use DuckDuckGoSearchRun from langchain
    return f"Результаты поиска для '{query}': (Требуется настройка ключа API / duckduckgo)"

@tool
async def set_reminder(minutes: int, message: str) -> str:
    """Устанавливает таймер/напоминание на заданное количество минут."""
    async def reminder_task():
        await asyncio.sleep(minutes * 60)
        # Here we would send this to the rule engine or ws_manager
        print(f"НАПОМИНАНИЕ: {message}")
        
    asyncio.create_task(reminder_task())
    return f"Напоминание '{message}' установлено на {minutes} минут."

def get_active_tools():
    return [set_volume, open_program, kill_process, web_search, set_reminder]
