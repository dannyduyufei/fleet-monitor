"""Alert rules over the latest stored snapshot.

Alerts are derived when someone asks for them. The robot row is the only
stored state, so a duplicate message cannot open a second copy of an alert.
"""

from dataclasses import dataclass

from fleet_monitor.config import Settings
from fleet_monitor.store import Robot

OFFLINE = "offline"
LOW_BATTERY = "low_battery"
STUCK_TASK = "stuck_task"


@dataclass(frozen=True)
class Alert:
    robot_id: str
    kind: str
    detail: str


def evaluate(robot: Robot, now: float, settings: Settings) -> list[Alert]:
    silent_for = now - robot.last_seen
    if silent_for > settings.offline_after_seconds:
        return [
            Alert(
                robot_id=robot.robot_id,
                kind=OFFLINE,
                detail=(
                    f"no telemetry for {silent_for:.1f}s "
                    f"(limit {settings.offline_after_seconds:.0f}s)"
                ),
            )
        ]

    alerts: list[Alert] = []
    if robot.battery < settings.low_battery_percent:
        alerts.append(
            Alert(
                robot_id=robot.robot_id,
                kind=LOW_BATTERY,
                detail=(
                    f"battery {robot.battery:.1f}% is below "
                    f"{settings.low_battery_percent:.0f}%"
                ),
            )
        )
    stuck_for = now - robot.progress_since
    if robot.task_state == "in_progress" and stuck_for > settings.stuck_after_seconds:
        alerts.append(
            Alert(
                robot_id=robot.robot_id,
                kind=STUCK_TASK,
                detail=(
                    f"task {robot.task_id} progress {robot.task_progress:.2f} "
                    f"unchanged for {stuck_for:.1f}s"
                ),
            )
        )
    return alerts


def evaluate_fleet(robots: list[Robot], now: float, settings: Settings) -> list[Alert]:
    alerts: list[Alert] = []
    for robot in robots:
        alerts.extend(evaluate(robot, now, settings))
    return alerts
