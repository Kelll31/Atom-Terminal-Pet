"""Тесты шины событий: подготовка текста к озвучке и маршрутизация к устройству."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.events import DEVICE_ACTIONS, EventBus, sanitize_for_speech


def test_sanitize_removes_markdown_and_links():
    text = "**Готово!** Смотри https://example.com/very/long/path и файл D:/projects/app/main.py"
    clean = sanitize_for_speech(text)

    assert "**" not in clean
    assert "https" not in clean
    assert "ссылка" in clean
    assert "путь" in clean


def test_sanitize_replaces_code_block():
    clean = sanitize_for_speech("Вот код:\n```python\nprint(1)\n```\nвсё")
    assert "print" not in clean
    assert "фрагмент кода" in clean


def test_sanitize_collapses_whitespace_and_emoji():
    assert sanitize_for_speech("Привет   🚀\n\nмир") == "Привет мир"


def test_device_actions_are_limited_to_firmware_commands():
    assert DEVICE_ACTIONS == {"speak", "set_emotion", "update_pc", "pomodoro", "set_rotation"}


@pytest.mark.asyncio
async def test_emit_sends_to_serial_only_when_device_is_not_on_wifi(monkeypatch):
    manager = MagicMock()
    manager.broadcast_json = AsyncMock()
    manager.device_on_wifi = False
    serial = MagicMock()

    monkeypatch.setattr("core.events.manager", manager)
    monkeypatch.setattr("core.events.serial_manager", serial)

    bus = EventBus()
    await bus.emit("set_emotion", emotion="happy")
    serial.send_json.assert_called_once()

    serial.reset_mock()
    manager.device_on_wifi = True
    await bus.emit("set_emotion", emotion="happy")
    serial.send_json.assert_not_called()

    # Служебные события агента на устройство не уходят вовсе
    serial.reset_mock()
    manager.device_on_wifi = False
    await bus.emit("agent_step", step={})
    serial.send_json.assert_not_called()
