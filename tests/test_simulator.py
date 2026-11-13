import pytest

from fleet_monitor.simulator import build_publication


def _pub(robot_id, tick, scenario, seq=1):
    return build_publication(robot_id, tick, scenario, seq)


def test_unknown_scenario_is_rejected():
    with pytest.raises(ValueError):
        _pub("robot-1", 0, "chaos")


def test_healthy_keeps_publishing_a_moving_task():
    first = _pub("robot-1", 0, "healthy")
    second = _pub("robot-1", 1, "healthy")
    assert first is not None and second is not None
    assert first["battery"] == 90
    assert second["battery"] > 20
    assert first["task"]["progress"] != second["task"]["progress"]
    assert first["heartbeat"] is True
    assert first["pose"].keys() == {"x", "y", "theta"}


def test_offline_scenario_silences_robot_1_after_three_ticks():
    assert _pub("robot-1", 2, "offline") is not None
    assert _pub("robot-1", 3, "offline") is None
    assert _pub("robot-2", 3, "offline") is not None


def test_low_battery_scenario_drains_robot_2():
    assert _pub("robot-2", 0, "low_battery")["battery"] == 30
    assert _pub("robot-2", 2, "low_battery")["battery"] == 20
    assert _pub("robot-2", 3, "low_battery")["battery"] == 15
    assert _pub("robot-1", 3, "low_battery")["battery"] > 20


def test_stuck_scenario_freezes_robot_3_progress():
    moving = _pub("robot-3", 1, "stuck")
    frozen = _pub("robot-3", 2, "stuck")
    later = _pub("robot-3", 6, "stuck")
    assert moving["task"]["progress"] != frozen["task"]["progress"]
    assert frozen["task"]["progress"] == 0.5
    assert later["task"]["progress"] == 0.5
    assert later["task"]["state"] == "in_progress"
    assert later["battery"] > 20


def test_all_scenario_assigns_one_fault_per_robot():
    assert _pub("robot-1", 3, "all") is None
    assert _pub("robot-2", 3, "all")["battery"] == 15
    assert _pub("robot-3", 4, "all")["task"]["progress"] == 0.5
    assert _pub("robot-3", 4, "all", seq=9)["seq"] == 9
