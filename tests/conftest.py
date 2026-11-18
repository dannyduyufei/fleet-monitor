import json

from fleet_monitor.store import Robot
from fleet_monitor.telemetry import Telemetry, parse_telemetry


def robot(**overrides) -> Robot:
    values = dict(
        robot_id="robot-1",
        seq=1,
        last_seen=1_000.0,
        battery=80.0,
        x=0.0,
        y=0.0,
        theta=0.0,
        task_id="robot-1-patrol",
        task_state="in_progress",
        task_progress=0.2,
        progress_since=1_000.0,
    )
    values.update(overrides)
    return Robot(**values)


def message(
    *,
    robot_id: str = "robot-1",
    seq: int = 1,
    battery: float = 80,
    progress: float = 0.2,
    task_state: str = "in_progress",
    task_id: str | None = None,
    x: float = 1.0,
    y: float = 2.0,
    theta: float = 0.5,
) -> Telemetry:
    return parse_telemetry(
        {
            "robot_id": robot_id,
            "seq": seq,
            "heartbeat": True,
            "battery": battery,
            "pose": {"x": x, "y": y, "theta": theta},
            "task": {
                "id": task_id or f"{robot_id}-patrol",
                "state": task_state,
                "progress": progress,
            },
        }
    )


def payload(**overrides) -> bytes:
    body = {
        "robot_id": "robot-1",
        "seq": 1,
        "heartbeat": True,
        "battery": 80,
        "pose": {"x": 1, "y": 2, "theta": 0.5},
        "task": {"id": "robot-1-patrol", "state": "in_progress", "progress": 0.2},
    }
    for key, value in overrides.items():
        if key in body and isinstance(body[key], dict) and isinstance(value, dict):
            body[key] = {**body[key], **value}
        else:
            body[key] = value
    return json.dumps(body).encode()
