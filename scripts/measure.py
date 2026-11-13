"""Measure ingest throughput and alert latency against a running stack.

The broker and API must already be up:

    docker compose up --build -d
    python scripts/measure.py

Definitions printed by the script:

- Ingest rate: wall time from just before the first publish of MEASURE_MESSAGES
  snapshots for one robot until GET /robots/{id} reports that sequence.
  The gap includes the publisher, the broker, SQLite, and up to one poll.
- Low-battery latency: wall time from publishing a fresh robot at 5% battery
  until GET /alerts lists low_battery for it. /alerts is polled on a fixed
  interval, so each sample includes up to one poll of wait.
- Offline latency: wall time from one heartbeat until GET /alerts lists
  offline for that robot. This includes the server's offline threshold.

The simulator may be publishing in the background. That traffic is part of
the running stack this command measures.
"""

import json
import os
import statistics
import time
import urllib.error
import urllib.request

import paho.mqtt.client as mqtt

API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
MQTT_HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
TOPIC = os.environ.get("MQTT_TOPIC", "fleet/telemetry")
MESSAGE_COUNT = int(os.environ.get("MEASURE_MESSAGES", "300"))
POLL_SECONDS = float(os.environ.get("MEASURE_POLL_SECONDS", "0.02"))
ALERT_SAMPLES = int(os.environ.get("MEASURE_ALERT_SAMPLES", "5"))


def main() -> None:
    _wait_for_health()
    ingest_seconds = _measure_ingest()
    rate = MESSAGE_COUNT / ingest_seconds
    battery_ms = [_measure_low_battery(index) * 1000 for index in range(ALERT_SAMPLES)]
    offline_seconds = _measure_offline()
    print(
        f"Ingested {MESSAGE_COUNT} messages in {ingest_seconds:.3f}s "
        f"({rate:.1f} messages/s), from the first publish until "
        f"GET /robots/measure-load reported seq {MESSAGE_COUNT}."
    )
    print(
        f"Low-battery alert latency over {ALERT_SAMPLES} samples, "
        f"publish until GET /alerts, polled every {POLL_SECONDS * 1000:.0f} ms: "
        f"min {min(battery_ms):.1f} ms, median {statistics.median(battery_ms):.1f} ms, "
        f"max {max(battery_ms):.1f} ms."
    )
    print("low_battery_samples_ms=" + ",".join(f"{sample:.1f}" for sample in battery_ms))
    print(
        f"Offline alert observed {offline_seconds:.2f}s after the heartbeat publish "
        f"(includes the server offline threshold; default in compose is 8s)."
    )


def _measure_ingest() -> float:
    robot_id = "measure-load"
    client = _connected_client("measure-load")
    started = time.perf_counter()
    try:
        for seq in range(1, MESSAGE_COUNT + 1):
            _publish(client, _snapshot(robot_id, seq, battery=80, progress=(seq % 5) * 0.2))
        _wait_for(lambda: _robot_seq(robot_id) >= MESSAGE_COUNT, timeout=20)
        return time.perf_counter() - started
    finally:
        _close_client(client)


def _measure_low_battery(index: int) -> float:
    robot_id = f"measure-bat-{index}"
    client = _connected_client(f"measure-bat-{index}")
    started = time.perf_counter()
    try:
        _publish(client, _snapshot(robot_id, seq=1, battery=5, progress=0.2))
        _wait_for(lambda: _has_alert(robot_id, "low_battery"), timeout=10)
        return time.perf_counter() - started
    finally:
        _close_client(client)


def _measure_offline() -> float:
    robot_id = "measure-offline"
    client = _connected_client("measure-offline")
    started = time.perf_counter()
    try:
        _publish(client, _snapshot(robot_id, seq=1, battery=80, progress=0.2))
        _wait_for(lambda: _has_alert(robot_id, "offline"), timeout=30)
        return time.perf_counter() - started
    finally:
        _close_client(client)


def _snapshot(robot_id: str, seq: int, battery: float, progress: float) -> dict:
    return {
        "robot_id": robot_id,
        "seq": seq,
        "heartbeat": True,
        "battery": battery,
        "pose": {"x": 0, "y": 0, "theta": 0},
        "task": {"id": f"{robot_id}-task", "state": "in_progress", "progress": progress},
    }


def _connected_client(client_id: str) -> mqtt.Client:
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id,
        protocol=mqtt.MQTTv311,
    )
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_start()
    deadline = time.time() + 5
    while not client.is_connected() and time.time() < deadline:
        time.sleep(0.01)
    if not client.is_connected():
        raise SystemExit(f"could not connect to mqtt at {MQTT_HOST}:{MQTT_PORT}")
    return client


def _close_client(client: mqtt.Client) -> None:
    client.disconnect()
    client.loop_stop()


def _publish(client: mqtt.Client, body: dict) -> None:
    result = client.publish(TOPIC, json.dumps(body), qos=0)
    result.wait_for_publish(timeout=5)
    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        raise SystemExit(f"publish failed rc={result.rc}")


def _wait_for_health() -> None:
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            payload = _get("/health")
        except urllib.error.URLError:
            time.sleep(0.2)
            continue
        if payload.get("status") == "ok":
            return
        time.sleep(0.2)
    raise SystemExit(f"API at {API_URL} did not become healthy")


def _robot_seq(robot_id: str) -> int:
    try:
        payload = _get(f"/robots/{robot_id}")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return 0
        raise
    return int(payload["seq"])


def _has_alert(robot_id: str, kind: str) -> bool:
    alerts = _get("/alerts")
    return any(alert["robot_id"] == robot_id and alert["kind"] == kind for alert in alerts)


def _wait_for(predicate, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(POLL_SECONDS)
    raise SystemExit("timed out waiting for the API to catch up")


def _get(path: str):
    with urllib.request.urlopen(API_URL + path, timeout=2) as response:
        return json.load(response)


if __name__ == "__main__":
    main()
