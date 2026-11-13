"""Subscribe to telemetry and fold it into the store."""

import json
import logging
import threading
import time

from fleet_monitor.config import Settings
from fleet_monitor.mqtt_loop import IngestStatus, serve
from fleet_monitor.store import Store
from fleet_monitor.telemetry import TelemetryError, parse_telemetry

logger = logging.getLogger(__name__)


def handle_payload(store: Store, payload: bytes, now: float) -> bool:
    """Parse one MQTT payload and apply it. Bad payloads are logged and skipped."""
    try:
        data = json.loads(payload)
        message = parse_telemetry(data)
    except (UnicodeDecodeError, json.JSONDecodeError, TelemetryError) as exc:
        logger.warning("dropped malformed telemetry: %s", exc)
        return False
    applied = store.apply(message, now=now)
    if not applied:
        logger.debug("ignored stale telemetry robot=%s seq=%s", message.robot_id, message.seq)
    return applied


def consume_forever(
    settings: Settings,
    store: Store,
    stop: threading.Event,
    status: IngestStatus | None = None,
) -> None:
    def setup(client):
        client.subscribe(settings.mqtt_topic, qos=0)
        logger.info("subscribed to %s", settings.mqtt_topic)

    def on_message(client, userdata, message):
        try:
            handle_payload(store, message.payload, now=time.time())
        except Exception:
            logger.exception("failed to store telemetry")

    serve(
        settings,
        stop,
        client_id="fleet-ingest",
        setup=setup,
        step=lambda client: None,
        status=status,
        on_message=on_message,
    )
