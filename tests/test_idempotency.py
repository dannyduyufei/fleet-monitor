from fleet_monitor.alerts import LOW_BATTERY, OFFLINE, evaluate
from fleet_monitor.config import Settings
from fleet_monitor.ingest import handle_payload
from fleet_monitor.store import Store

from conftest import message, payload


def test_first_snapshot_is_stored(tmp_path):
    store = Store(tmp_path / "fleet.db")
    assert store.apply(message(seq=0, battery=91), now=10) is True
    robot = store.get_robot("robot-1")
    assert robot is not None
    assert robot.seq == 0
    assert robot.battery == 91
    assert robot.last_seen == 10


def test_newer_seq_replaces_state(tmp_path):
    store = Store(tmp_path / "fleet.db")
    store.apply(message(seq=1, battery=80, x=1), now=10)
    assert store.apply(message(seq=2, battery=70, x=4), now=11) is True
    robot = store.get_robot("robot-1")
    assert robot.seq == 2
    assert robot.battery == 70
    assert robot.x == 4
    assert robot.last_seen == 11


def test_duplicate_seq_is_ignored(tmp_path):
    store = Store(tmp_path / "fleet.db")
    store.apply(message(seq=3, battery=40), now=10)
    assert store.apply(message(seq=3, battery=99), now=50) is False
    robot = store.get_robot("robot-1")
    assert robot.battery == 40
    assert robot.last_seen == 10


def test_older_seq_does_not_overwrite_or_refresh_liveness(tmp_path):
    store = Store(tmp_path / "fleet.db")
    store.apply(message(seq=5, battery=11), now=50)
    assert store.apply(message(seq=4, battery=90), now=80) is False
    robot = store.get_robot("robot-1")
    assert robot.seq == 5
    assert robot.battery == 11
    assert robot.last_seen == 50
    alerts = evaluate(robot, now=50 + 8.1, settings=Settings())
    assert [alert.kind for alert in alerts] == [OFFLINE]


def test_gap_in_seq_is_still_applied(tmp_path):
    store = Store(tmp_path / "fleet.db")
    store.apply(message(seq=1), now=10)
    assert store.apply(message(seq=4, battery=60), now=12) is True
    assert store.get_robot("robot-1").seq == 4


def test_unchanged_task_keeps_progress_timer(tmp_path):
    store = Store(tmp_path / "fleet.db")
    store.apply(message(seq=1, progress=0.2, battery=80), now=10)
    assert store.apply(message(seq=2, progress=0.2, battery=70), now=25) is True
    robot = store.get_robot("robot-1")
    assert robot.progress_since == 10
    assert robot.last_seen == 25
    assert robot.battery == 70


def test_task_change_resets_progress_timer(tmp_path):
    store = Store(tmp_path / "fleet.db")
    store.apply(message(seq=1, progress=0.2), now=10)
    store.apply(message(seq=2, progress=0.4), now=30)
    robot = store.get_robot("robot-1")
    assert robot.progress_since == 30
    assert robot.task_progress == 0.4


def test_stale_message_cannot_clear_a_low_battery_reading(tmp_path):
    store = Store(tmp_path / "fleet.db")
    store.apply(message(seq=2, battery=10), now=100)
    store.apply(message(seq=1, battery=95), now=110)
    robot = store.get_robot("robot-1")
    alerts = evaluate(robot, now=100, settings=Settings())
    assert [alert.kind for alert in alerts] == [LOW_BATTERY]


def test_duplicate_json_payload_is_ignored(tmp_path):
    store = Store(tmp_path / "fleet.db")
    assert handle_payload(store, payload(seq=1, battery=40), now=10) is True
    assert handle_payload(store, payload(seq=1, battery=99), now=20) is False
    robot = store.get_robot("robot-1")
    assert robot.battery == 40
    assert robot.last_seen == 10


def test_malformed_payload_is_dropped(tmp_path):
    store = Store(tmp_path / "fleet.db")
    assert handle_payload(store, b"{", now=1) is False
    assert handle_payload(store, payload(heartbeat=False), now=1) is False
    assert store.list_robots() == []


def test_robots_are_independent(tmp_path):
    store = Store(tmp_path / "fleet.db")
    store.apply(message(robot_id="robot-1", seq=3), now=10)
    store.apply(message(robot_id="robot-2", seq=1, battery=15), now=11)
    assert store.apply(message(robot_id="robot-2", seq=1, battery=90), now=12) is False
    assert store.get_robot("robot-1").seq == 3
    assert store.get_robot("robot-2").battery == 15
    assert [robot.robot_id for robot in store.list_robots()] == ["robot-1", "robot-2"]
