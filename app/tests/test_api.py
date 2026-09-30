from fastapi.testclient import TestClient

from autoseguro.api import create_app


def test_health_and_message_flow(make_agent):
    agent, _ = make_agent()
    client = TestClient(create_app(agent))
    assert client.get("/health").json() == {"status": "ok"}
    body = {
        "conversation_id": "w1", "message_id": "m1",
        "text": "Tenho 35 anos, carro 2022, CEP 01310-100, começo em 15/07/2026, plano completo",
    }  # fmt: skip
    data = client.post("/messages", json=body).json()
    assert data["stage"] == "quoted" and data["price"] == 1234.5 and data["message_id"] == "m1"


def test_rejects_invalid_payload(make_agent):
    agent, _ = make_agent()
    client = TestClient(create_app(agent))
    assert client.post("/messages", json={"conversation_id": "x", "text": ""}).status_code == 422


def test_json_declares_utf8_charset_for_windows_clients(make_agent):
    agent, _ = make_agent()
    client = TestClient(create_app(agent))
    resp = client.post("/messages", json={"conversation_id": "w1", "text": "Olá, cotação"})
    assert resp.headers["content-type"] == "application/json; charset=utf-8"
    assert "Olá" in resp.content.decode("utf-8")
