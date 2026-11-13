"""Process settings, all overridable from the environment."""

import os
from dataclasses import dataclass


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return float(raw)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class Settings:
    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = 1883
    mqtt_topic: str = "fleet/telemetry"
    database_path: str = "data/fleet.db"
    offline_after_seconds: float = 8.0
    low_battery_percent: float = 20.0
    stuck_after_seconds: float = 10.0
    reconnect_min_seconds: float = 0.5
    reconnect_max_seconds: float = 5.0
    connect_timeout_seconds: float = 5.0
    sim_scenario: str = "healthy"
    sim_robots: tuple[str, ...] = ("robot-1", "robot-2", "robot-3")
    sim_interval: float = 1.0


def load_settings() -> Settings:
    robots = os.environ.get("SIM_ROBOTS", "robot-1,robot-2,robot-3")
    parsed = tuple(part.strip() for part in robots.split(",") if part.strip())
    if not parsed:
        raise ValueError("SIM_ROBOTS must name at least one robot")
    return Settings(
        mqtt_host=os.environ.get("MQTT_HOST", "127.0.0.1"),
        mqtt_port=_env_int("MQTT_PORT", 1883),
        mqtt_topic=os.environ.get("MQTT_TOPIC", "fleet/telemetry"),
        database_path=os.environ.get("DATABASE_PATH", "data/fleet.db"),
        offline_after_seconds=_env_float("OFFLINE_AFTER_SECONDS", 8.0),
        low_battery_percent=_env_float("LOW_BATTERY_PERCENT", 20.0),
        stuck_after_seconds=_env_float("STUCK_AFTER_SECONDS", 10.0),
        reconnect_min_seconds=_env_float("RECONNECT_MIN_SECONDS", 0.5),
        reconnect_max_seconds=_env_float("RECONNECT_MAX_SECONDS", 5.0),
        connect_timeout_seconds=_env_float("CONNECT_TIMEOUT_SECONDS", 5.0),
        sim_scenario=os.environ.get("SIM_SCENARIO", "healthy"),
        sim_robots=parsed,
        sim_interval=_env_float("SIM_INTERVAL", 1.0),
    )
