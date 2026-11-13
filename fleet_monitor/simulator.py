"""Publish telemetry for a few simulated robots.

Scenarios are a pure function of (robot, tick), so the conditions that raise
each alert can be tested without a broker. The process only adds MQTT and a clock.
"""

import json
import logging
import math
import threading
import time

import paho.mqtt.client as mqtt

from fleet_monitor.config import Settings, load_settings
from fleet_monitor.mqtt_loop import serve

logger = logging.getLogger(__name__)

SCENARIOS = frozenset({"healthy", "offline", "low_battery", "stuck", "all"})

# robot-1 goes quiet after this many published ticks (0-based).
_OFFLINE_FROM_TICK = 3
# robot-3 freezes on this tick and after.
_STUCK_FROM_TICK = 2


def build_publication(robot_id: str, tick: int, scenario: str, seq: int) -> dict | None:
    """Return the next telemetry object, or None when this robot should be silent."""
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}")

    battery = max(0.0, 90.0 - tick * 0.2)
    progress = round((tick % 5) * 0.2, 4)
    silent = False

    if scenario in {"offline", "all"} and robot_id == "robot-1" and tick >= _OFFLINE_FROM_TICK:
        silent = True
    if scenario in {"low_battery", "all"} and robot_id == "robot-2":
        battery = max(0.0, 30.0 - tick * 5.0)
    if scenario in {"stuck", "all"} and robot_id == "robot-3" and tick >= _STUCK_FROM_TICK:
        progress = 0.5

    if silent:
        return None

    phase = {"robot-1": 0.0, "robot-2": 2.1, "robot-3": 4.2}.get(robot_id, 0.0)
    angle = phase + tick * 0.4
    return {
        "robot_id": robot_id,
        "seq": seq,
        "heartbeat": True,
        "battery": round(battery, 2),
        "pose": {
            "x": round(math.cos(angle), 3),
            "y": round(math.sin(angle), 3),
            "theta": round(angle, 3),
        },
        "task": {
            "id": f"{robot_id}-patrol",
            "state": "in_progress",
            "progress": progress,
        },
    }


def run_simulator(settings: Settings, stop: threading.Event) -> None:
    if settings.sim_scenario not in SCENARIOS:
        raise ValueError(
            f"SIM_SCENARIO must be one of {', '.join(sorted(SCENARIOS))}"
        )

    seq = {robot_id: 0 for robot_id in settings.sim_robots}
    silenced: set[str] = set()
    next_publish = time.monotonic()
    tick = 0
    logger.info(
        "simulator scenario=%s robots=%s interval=%ss",
        settings.sim_scenario,
        ",".join(settings.sim_robots),
        settings.sim_interval,
    )

    def step(client: mqtt.Client) -> None:
        nonlocal tick, next_publish
        now = time.monotonic()
        if now < next_publish:
            return
        for robot_id in settings.sim_robots:
            sample = build_publication(
                robot_id, tick, settings.sim_scenario, seq[robot_id] + 1
            )
            if sample is None:
                if robot_id not in silenced:
                    logger.info(
                        "robot %s stopped publishing (scenario=%s)",
                        robot_id,
                        settings.sim_scenario,
                    )
                    silenced.add(robot_id)
                continue
            result = client.publish(
                settings.mqtt_topic, json.dumps(sample), qos=0
            )
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                raise ConnectionError(f"publish failed rc={result.rc}")
            seq[robot_id] = sample["seq"]
        tick += 1
        next_publish = time.monotonic() + settings.sim_interval

    serve(
        settings,
        stop,
        client_id="fleet-simulator",
        setup=lambda client: None,
        step=step,
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings()
    stop = threading.Event()
    try:
        run_simulator(settings, stop)
    except KeyboardInterrupt:
        stop.set()


if __name__ == "__main__":
    main()
