from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_read_main():
    # Since we only mount /firmware conditionally, there is no generic GET / route defined
    # We can check a 404 or add a health check test if it existed.
    response = client.get("/")
    assert response.status_code == 200


def test_websocket_connect():
    with client.websocket_connect("/ws/pet") as websocket:
        # Expected first message is device_status_update
        data = websocket.receive_json()
        assert data["action"] == "device_status_update"
        assert "device_info" in data
