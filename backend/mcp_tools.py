import os
import subprocess
import pyautogui
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from langchain.tools import tool
from config import MCPSettings

@tool
def set_volume(level: int) -> str:
    """
    Устанавливает громкость системы Windows (0 до 100).
    """
    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        
        # level is 0-100, set scalar volume expects 0.0 to 1.0
        level = max(0, min(100, level))
        volume.SetMasterVolumeLevelScalar(level / 100.0, None)
        return f"Громкость установлена на {level}%."
    except Exception as e:
        return f"Ошибка при установке громкости: {e}"

@tool
def press_keys(keys: str) -> str:
    """
    Эмулирует нажатие комбинации клавиш (например: 'win+d', 'ctrl+c', 'enter').
    Клавиши разделяются знаком '+'.
    """
    try:
        key_list = keys.lower().split('+')
        pyautogui.hotkey(*key_list)
        return f"Нажаты клавиши: {keys}"
    except Exception as e:
        return f"Ошибка при нажатии клавиш: {e}"

@tool
def open_program(program_name: str) -> str:
    """
    Открывает базовые программы в Windows.
    Например: 'notepad', 'calc', 'explorer', или путь к исполняемому файлу.
    """
    try:
        # Для безопасности ограничиваем запуск или просто используем subprocess
        subprocess.Popen(program_name, shell=True)
        return f"Программа {program_name} запущена."
    except Exception as e:
        return f"Ошибка при запуске программы {program_name}: {e}"

def get_active_tools(settings: MCPSettings):
    """
    Возвращает список активных инструментов на основе конфигурации.
    """
    active_tools = []
    if settings.volume_control:
        active_tools.append(set_volume)
    if settings.keyboard_control:
        active_tools.append(press_keys)
    if settings.app_launcher:
        active_tools.append(open_program)
    return active_tools
