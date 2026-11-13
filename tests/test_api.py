import time

from fastapi.testclient import TestClient

from fleet_monitor.api import create_app
from fleet_monitor.config import Settings
from fleet_monitor.store import Store

from conftest import message


def _client(tmp_path, store: Store | None = None):
    store = store or Store(tmp_path / "fleet.db")
    app = create_app(settings=Settings(), store=store, start_ingest=False)
    return TestClient(app), store


def test_openapi_includes_the_four_routes(tmp_path):
    client, _store = _client(tmp_path)
    with client:
        spec = client.get("/openapi.json")
        docs = client.get("/docs")
    assert spec.status_code == 200
    assert {
        "/health",
        "/robots",
        "/robots/{robot_id}",
        "/alerts",
    } <= set(spec.json()["paths"])
    assert docs.status_code == 200
    assert "swagger" in docs.text.lower()


def test_health_is_ok_when_ingest_is_not_running(tmp_path):
    client, _store = _client(tmp_path)
    with client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "mqtt_connected": False}


def test_robots_empty(tmp_path):
    client, _store = _client(tmp_path)
    with client:
        assert client.get("/robots").json() == []


def test_robot_round_trip_and_unknown_id(tmp_path):
    client, store = _client(tmp_path)
    store.apply(message(seq=6, battery=64, progress=0.4, x=1.5, y=-2, theta=0.25), now=123.5)
    with client:
        listing = client.get("/robots")
        one = client.get("/robots/robot-1")
        missing = client.get("/robots/nope")
    assert listing.status_code == 200
    body = one.json()
    assert body["robot_id"] == "robot-1"
    assert body["seq"] == 6
    assert body["battery"] == 64
    assert body["last_seen"] == 123.5
    assert body["pose"] == {"x": 1.5, "y": -2, "theta": 0.25}
    assert body["task"] == {"id": "robot-1-patrol", "state": "in_progress", "progress": 0.4}
    assert listing.json() == [body]
    assert missing.status_code == 404


def test_alerts_endpoint_uses_live_rules(tmp_path):
    client, store = _client(tmp_path)
    now = time.time()
    store.apply(message(robot_id="robot-1", battery=5, progress=0.3), now=now)
    store.apply(
        message(robot_id="robot-2", seq=2, battery=90),
        now=now - 30,
    )
    with client:
        alerts = client.get("/alerts").json()
    kinds = {(alert["robot_id"], alert["kind"]) for alert in alerts}
    assert ("robot-1", "low_battery") in kinds
    assert ("robot-1", "stuck_task") not in kinds
    assert ("robot-2", "offline") in kinds
    assert ("robot-2", "low_battery") not in kinds
