from fleet_monitor.alerts import LOW_BATTERY, OFFLINE, STUCK_TASK, evaluate
from fleet_monitor.config import Settings

from conftest import robot

NOW = 1_000.0


def _kinds(alerts):
    return [alert.kind for alert in alerts]


def test_healthy_robot_has_no_alerts():
    assert evaluate(robot(), NOW, Settings()) == []


def test_offline_when_silence_exceeds_limit():
    alerts = evaluate(robot(last_seen=NOW - 8.1), NOW, Settings())
    assert _kinds(alerts) == [OFFLINE]
    assert "limit 8s" in alerts[0].detail


def test_exactly_at_offline_limit_is_still_online():
    assert evaluate(robot(last_seen=NOW - 8), NOW, Settings()) == []


def test_low_battery_when_below_threshold():
    alerts = evaluate(robot(battery=19.9), NOW, Settings())
    assert _kinds(alerts) == [LOW_BATTERY]
    assert "19.9%" in alerts[0].detail


def test_battery_at_threshold_is_not_low():
    assert evaluate(robot(battery=20), NOW, Settings()) == []


def test_stuck_when_progress_has_not_moved():
    alerts = evaluate(robot(progress_since=NOW - 10.1), NOW, Settings())
    assert _kinds(alerts) == [STUCK_TASK]
    assert "robot-1-patrol" in alerts[0].detail


def test_exactly_at_stuck_limit_is_not_stuck():
    assert evaluate(robot(progress_since=NOW - 10), NOW, Settings()) == []


def test_completed_task_is_not_stuck():
    assert (
        evaluate(
            robot(task_state="completed", progress_since=NOW - 100),
            NOW,
            Settings(),
        )
        == []
    )


def test_idle_task_is_not_stuck():
    assert evaluate(robot(task_state="idle", progress_since=NOW - 100), NOW, Settings()) == []


def test_offline_suppresses_stale_battery_and_task_alerts():
    alerts = evaluate(
        robot(last_seen=NOW - 30, battery=1, progress_since=NOW - 30),
        NOW,
        Settings(),
    )
    assert _kinds(alerts) == [OFFLINE]


def test_low_battery_and_stuck_can_both_be_open():
    alerts = evaluate(
        robot(battery=5, progress_since=NOW - 30),
        NOW,
        Settings(),
    )
    assert _kinds(alerts) == [LOW_BATTERY, STUCK_TASK]


def test_thresholds_come_from_settings():
    settings = Settings(
        offline_after_seconds=2,
        low_battery_percent=50,
        stuck_after_seconds=3,
    )
    alerts = evaluate(robot(last_seen=NOW - 2.5, battery=40), NOW, settings)
    assert _kinds(alerts) == [OFFLINE]
    alerts = evaluate(robot(battery=40, progress_since=NOW - 3.5), NOW, settings)
    assert _kinds(alerts) == [LOW_BATTERY, STUCK_TASK]
