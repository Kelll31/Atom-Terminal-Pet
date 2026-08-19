from unittest.mock import AsyncMock

import pytest

from core.ws_manager import ConnectionManager


@pytest.fixture
def manager():
    return ConnectionManager()


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
