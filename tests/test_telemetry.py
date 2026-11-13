import math

import pytest

from fleet_monitor.telemetry import TelemetryError, parse_telemetry

from conftest import payload


def _parse(raw: bytes):
    import json

    return parse_telemetry(json.loads(raw))


def test_parses_a_snapshot():
    message = _parse(payload())
    assert message.robot_id == "robot-1"
    assert message.seq == 1
    assert message.battery == 80
    assert message.task_state == "in_progress"


def test_rejects_non_object():
    with pytest.raises(TelemetryError):
        parse_telemetry([])


def test_rejects_bad_robot_id():
    with pytest.raises(TelemetryError):
        _parse(payload(robot_id="robot 1"))


def test_rejects_bool_seq_and_negative_seq():
    with pytest.raises(TelemetryError):
        _parse(payload(seq=True))
    with pytest.raises(TelemetryError):
        _parse(payload(seq=-1))


def test_rejects_missing_heartbeat():
    import json

    body = json.loads(payload())
    del body["heartbeat"]
    with pytest.raises(TelemetryError):
        parse_telemetry(body)


def test_rejects_battery_out_of_range_and_non_finite():
    with pytest.raises(TelemetryError):
        _parse(payload(battery=101))
    with pytest.raises(TelemetryError):
        _parse(payload(battery=float("nan")))


def test_rejects_bad_task_state_and_progress():
    with pytest.raises(TelemetryError):
        _parse(payload(task={"state": "running"}))
    with pytest.raises(TelemetryError):
        _parse(payload(task={"progress": 1.2}))


def test_rejects_non_finite_pose():
    with pytest.raises(TelemetryError):
        _parse(payload(pose={"x": math.inf}))
