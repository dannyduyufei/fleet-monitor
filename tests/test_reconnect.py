import json
import socket
import threading
import time

from fleet_monitor.config import Settings
from fleet_monitor.ingest import consume_forever
from fleet_monitor.mqtt_loop import Backoff, IngestStatus
from fleet_monitor.store import Store

from mqtt_stub import ScriptedBroker


def test_backoff_grows_caps_and_resets():
    backoff = Backoff(0.5, 3)
    assert backoff.next_delay() == 0.5
    assert backoff.next_delay() == 1
    assert backoff.next_delay() == 2
    assert backoff.next_delay() == 3
    assert backoff.next_delay() == 3
    backoff.reset()
    assert backoff.next_delay() == 0.5


def test_retries_after_broker_drops_and_ingests_the_next_session(tmp_path):
    body = {
        "robot_id": "robot-9",
        "seq": 1,
        "heartbeat": True,
        "battery": 10,
        "pose": {"x": 1, "y": 2, "theta": 0},
        "task": {"id": "robot-9-patrol", "state": "in_progress", "progress": 0.1},
    }
    broker = ScriptedBroker(json.dumps(body).encode(), drop_first=True)
    broker.start()
    assert broker.ready.wait(2)

    store = Store(tmp_path / "fleet.db")
    stop = threading.Event()
    status = IngestStatus()
    settings = _fast_settings(broker.port)
    thread = threading.Thread(
        target=consume_forever,
        args=(settings, store, stop, status),
        daemon=True,
    )
    thread.start()
    try:
        deadline = time.time() + 5
        while time.time() < deadline and store.get_robot("robot-9") is None:
            if broker.error:
                raise AssertionError(broker.error)
            time.sleep(0.02)
        robot = store.get_robot("robot-9")
        assert robot is not None, "telemetry was not ingested after reconnect"
        assert robot.seq == 1
        assert robot.battery == 10
        assert broker.accepted >= 2
    finally:
        stop.set()
        thread.join(timeout=2)


def test_retries_until_the_broker_starts_listening(tmp_path):
    body = {
        "robot_id": "robot-8",
        "seq": 4,
        "heartbeat": True,
        "battery": 55,
        "pose": {"x": 0, "y": 0, "theta": 0},
        "task": {"id": "robot-8-patrol", "state": "idle", "progress": 0},
    }
    port = _free_port()
    store = Store(tmp_path / "fleet.db")
    stop = threading.Event()
    thread = threading.Thread(
        target=consume_forever,
        args=(_fast_settings(port), store, stop, IngestStatus()),
        daemon=True,
    )
    thread.start()
    time.sleep(0.3)
    broker = ScriptedBroker(json.dumps(body).encode(), port=port, drop_first=False)
    broker.start()
    assert broker.ready.wait(2)
    try:
        deadline = time.time() + 5
        while time.time() < deadline and store.get_robot("robot-8") is None:
            if broker.error:
                raise AssertionError(broker.error)
            time.sleep(0.02)
        robot = store.get_robot("robot-8")
        assert robot is not None, "ingest did not recover when the broker came up"
        assert robot.seq == 4
        assert robot.task_state == "idle"
    finally:
        stop.set()
        thread.join(timeout=2)


def _fast_settings(port: int) -> Settings:
    return Settings(
        mqtt_host="127.0.0.1",
        mqtt_port=port,
        reconnect_min_seconds=0.05,
        reconnect_max_seconds=0.2,
        connect_timeout_seconds=1,
    )


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port
