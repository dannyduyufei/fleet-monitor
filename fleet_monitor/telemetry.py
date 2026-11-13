"""Telemetry payload parsing.

One JSON message is one snapshot: heartbeat, battery, pose, and task together,
with a per-robot sequence number the ingest worker uses for ordering.
"""

import math
import re
from dataclasses import dataclass

_ROBOT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_TASK_STATES = frozenset({"idle", "in_progress", "completed", "failed"})


class TelemetryError(ValueError):
    """The payload is not a snapshot we can store."""


@dataclass(frozen=True)
class Telemetry:
    robot_id: str
    seq: int
    battery: float
    x: float
    y: float
    theta: float
    task_id: str
    task_state: str
    task_progress: float


def parse_telemetry(data: object) -> Telemetry:
    if not isinstance(data, dict):
        raise TelemetryError("payload must be a JSON object")

    robot_id = data.get("robot_id")
    if not isinstance(robot_id, str) or _ROBOT_ID.fullmatch(robot_id) is None:
        raise TelemetryError("invalid robot_id")

    seq = data.get("seq")
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
        raise TelemetryError("seq must be an integer >= 0")

    if data.get("heartbeat") is not True:
        raise TelemetryError("heartbeat must be true")

    battery = round(_number(data.get("battery"), "battery"), 2)
    if not 0 <= battery <= 100:
        raise TelemetryError("battery must be between 0 and 100")

    pose = data.get("pose")
    if not isinstance(pose, dict):
        raise TelemetryError("pose must be an object")

    task = data.get("task")
    if not isinstance(task, dict):
        raise TelemetryError("task must be an object")
    task_id = task.get("id")
    if not isinstance(task_id, str) or not 1 <= len(task_id) <= 64:
        raise TelemetryError("invalid task id")
    task_state = task.get("state")
    if task_state not in _TASK_STATES:
        raise TelemetryError("invalid task state")
    progress = round(_number(task.get("progress"), "task.progress"), 4)
    if not 0 <= progress <= 1:
        raise TelemetryError("task progress must be between 0 and 1")

    return Telemetry(
        robot_id=robot_id,
        seq=seq,
        battery=battery,
        x=_number(pose.get("x"), "pose.x"),
        y=_number(pose.get("y"), "pose.y"),
        theta=_number(pose.get("theta"), "pose.theta"),
        task_id=task_id,
        task_state=task_state,
        task_progress=progress,
    )


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TelemetryError(f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise TelemetryError(f"{name} must be finite")
    return number
