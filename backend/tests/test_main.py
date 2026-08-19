"""Тесты HTTP-API. TestClient создаётся без контекстного менеджера,
поэтому lifespan (мониторинг, MCP, Serial) не запускается."""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["tools"] > 10


def test_tools_endpoint_lists_registry():
    response = client.get("/api/tools")
    assert response.status_code == 200
    names = {tool["name"] for tool in response.json()["tools"]}
    assert "get_pc_status" in names
    assert "run_command" in names


def test_settings_masks_api_key():
    response = client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert "api_key_set" in data
    if data["api_key_set"]:
        assert "..." in data["api_key"]


def test_settings_update_roundtrip():
    original = client.get("/api/settings").json()["pet_name"]
    try:
        response = client.post("/api/settings", json={"pet_name": "Патрик"})
        assert response.status_code == 200
        assert client.get("/api/settings").json()["pet_name"] == "Патрик"
    finally:
        client.post("/api/settings", json={"pet_name": original})


def test_masked_api_key_is_not_saved():
    """UI отправляет замаскированный ключ обратно — он не должен затирать настоящий."""
    before = client.get("/api/settings").json()
    client.post("/api/settings", json={"api_key": "sk-1...cdef"})
    after = client.get("/api/settings").json()
    assert after["api_key_set"] == before["api_key_set"]


def test_tasks_endpoint_returns_list():
    response = client.get("/api/tasks")
    assert response.status_code == 200
    assert "tasks" in response.json()


def test_rules_endpoint():
    response = client.get("/api/rules")
    assert response.status_code == 200
    assert "rules" in response.json()


def test_websocket_sends_initial_state():
    with client.websocket_connect("/ws/pet") as websocket:
        first = websocket.receive_json()
        assert first["action"] == "device_status_update"
        second = websocket.receive_json()
        assert second["action"] == "tasks_snapshot"


def test_unknown_api_route_is_404():
    assert client.get("/api/does-not-exist").status_code == 404
