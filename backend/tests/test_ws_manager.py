"""Тесты реестра соединений.

Главное здесь — питомец не панель. Все broadcast_* обязаны означать «всем
панелям»: снимок задач на десятки килобайт рвёт WebSocket прошивки кодом 1009,
а браузерный микрофон из тестера в общей бинарной рассылке уходил прямо
в динамик питомца. До устройства данные доходят только адресно, через
send_to_device / send_binary_to_device.
"""

from unittest.mock import AsyncMock

import pytest

from core.ws_manager import ConnectionManager


@pytest.fixture
def manager():
    return ConnectionManager()


async def connect_device(manager: ConnectionManager) -> AsyncMock:
    """Подключает клиента и помечает его питомцем — как это делает main.py."""
    device = AsyncMock()
    await manager.connect(device)
    manager.set_device_ws(device)
    return device


@pytest.mark.asyncio
async def test_connect_disconnect(manager):
    mock_ws = AsyncMock()
    await manager.connect(mock_ws)
    assert len(manager.active_connections) == 1
    mock_ws.accept.assert_awaited_once()

    manager.disconnect(mock_ws)
    assert len(manager.active_connections) == 0


def test_update_device_info(manager):
    manager.update_device_info(
        ip="192.168.1.100", ssid="MyWiFi", rssi=-50, device="TestDevice"
    )
    assert manager.device_info["connected"] is True
    assert manager.device_info["ip"] == "192.168.1.100"
    assert manager.device_info["ssid"] == "MyWiFi"
    assert manager.device_info["rssi"] == -50
    assert manager.device_info["device"] == "TestDevice"


@pytest.mark.asyncio
async def test_broadcast_json(manager):
    ws1 = AsyncMock()
    ws2 = AsyncMock()
    await manager.connect(ws1)
    await manager.connect(ws2)

    await manager.broadcast_json({"test": "data"})
    ws1.send_json.assert_awaited_once_with({"test": "data"})
    ws2.send_json.assert_awaited_once_with({"test": "data"})


# ── Разделение панелей и устройства ────────────────────────────────────────
@pytest.mark.asyncio
async def test_panel_connections_exclude_device(manager):
    panel = AsyncMock()
    await manager.connect(panel)
    device = await connect_device(manager)

    assert manager.panel_connections() == [panel]
    assert device not in manager.panel_connections()
    assert manager.device_on_wifi is True


@pytest.mark.asyncio
async def test_broadcast_json_reaches_panel_but_not_device(manager):
    """Снимок задач и прочий поток панели до прошивки доходить не должен."""
    panel = AsyncMock()
    await manager.connect(panel)
    device = await connect_device(manager)

    await manager.broadcast_json({"action": "tasks_snapshot", "tasks": []})

    panel.send_json.assert_awaited_once()
    device.send_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_broadcast_binary_reaches_panel_but_not_device(manager):
    panel = AsyncMock()
    await manager.connect(panel)
    device = await connect_device(manager)

    await manager.broadcast_binary(b"\x01\x02")

    panel.send_bytes.assert_awaited_once_with(b"\x01\x02")
    device.send_bytes.assert_not_awaited()


@pytest.mark.asyncio
async def test_broadcast_binary_exclude_skips_sender_and_device(manager):
    """Микрофон из панели не возвращается эхом отправителю и не попадает в питомца.

    Это тот самый случай, ради которого метод и появился: main.py гонит через
    него поток с браузерного микрофона, и физически не должно быть пути,
    по которому этот поток окажется в динамике устройства.
    """
    sender = AsyncMock()
    listener = AsyncMock()
    await manager.connect(sender)
    await manager.connect(listener)
    device = await connect_device(manager)

    await manager.broadcast_binary_exclude(b"mic", sender)

    listener.send_bytes.assert_awaited_once_with(b"mic")
    sender.send_bytes.assert_not_awaited()
    device.send_bytes.assert_not_awaited()


# ── Адресная отправка питомцу ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_send_to_device_targets_only_the_device(manager):
    panel = AsyncMock()
    await manager.connect(panel)
    device = await connect_device(manager)

    assert await manager.send_to_device({"action": "beep"}) is True
    device.send_json.assert_awaited_once_with({"action": "beep"})
    panel.send_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_to_device_reports_absent_device(manager):
    """Без Wi-Fi-питомца метод честно отвечает False — шина уйдёт на USB."""
    panel = AsyncMock()
    await manager.connect(panel)

    assert await manager.send_to_device({"action": "beep"}) is False
    assert await manager.send_binary_to_device(b"\x00") is False
    panel.send_json.assert_not_awaited()
    panel.send_bytes.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_to_device_drops_broken_socket(manager):
    """Мёртвый сокет надо не только заметить, но и вычистить из реестра."""
    device = await connect_device(manager)
    device.send_json.side_effect = RuntimeError("сокет закрыт")

    assert await manager.send_to_device({"action": "beep"}) is False
    assert manager.device_ws is None
    assert device not in manager.active_connections
    assert manager.device_on_wifi is False


@pytest.mark.asyncio
async def test_send_binary_to_device_targets_only_the_device(manager):
    panel = AsyncMock()
    await manager.connect(panel)
    device = await connect_device(manager)

    assert await manager.send_binary_to_device(b"pcm") is True
    device.send_bytes.assert_awaited_once_with(b"pcm")
    panel.send_bytes.assert_not_awaited()


@pytest.mark.asyncio
async def test_disconnected_device_stops_being_on_wifi(manager):
    device = await connect_device(manager)
    manager.disconnect(device)

    assert manager.device_on_wifi is False
    assert manager.device_info["connected"] is False
    assert manager.device_info["transport"] == "none"
    assert await manager.send_to_device({"action": "beep"}) is False


def test_mark_device_seen_reports_only_real_changes(manager):
    """Панель дёргаем событием только когда состояние правда изменилось."""
    assert manager.mark_device_seen("usb") is True
    assert manager.mark_device_seen("usb") is False
    assert manager.device_info["ip"] == "USB"

    assert manager.mark_device_seen("wifi") is True   # сменился транспорт
    assert manager.mark_device_gone() is True
    assert manager.mark_device_gone() is False
