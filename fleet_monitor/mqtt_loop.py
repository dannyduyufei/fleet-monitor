"""MQTT session loop with reconnect.

paho can reconnect on its own inside loop_forever. This loop calls client.loop()
itself so a dropped broker is visible: the session ends, we wait with capped
exponential backoff, then connect and subscribe again.
"""

import logging
import threading
import time
from collections.abc import Callable

import paho.mqtt.client as mqtt

from fleet_monitor.config import Settings

logger = logging.getLogger(__name__)

Setup = Callable[[mqtt.Client], None]
Step = Callable[[mqtt.Client], None]
OnMessage = Callable[[mqtt.Client, object, mqtt.MQTTMessage], None]


class IngestStatus:
    def __init__(self) -> None:
        self.connected = False


class Backoff:
    def __init__(self, minimum: float, maximum: float) -> None:
        if minimum <= 0 or maximum < minimum:
            raise ValueError("backoff bounds must satisfy 0 < min <= max")
        self._minimum = minimum
        self._maximum = maximum
        self._attempt = 0

    def next_delay(self) -> float:
        delay = min(self._maximum, self._minimum * (2**self._attempt))
        self._attempt += 1
        return delay

    def reset(self) -> None:
        self._attempt = 0


def serve(
    settings: Settings,
    stop: threading.Event,
    client_id: str,
    *,
    setup: Setup,
    step: Step,
    status: IngestStatus | None = None,
    on_message: OnMessage | None = None,
) -> None:
    """Hold one MQTT session until it drops, then retry until stop is set."""
    backoff = Backoff(settings.reconnect_min_seconds, settings.reconnect_max_seconds)
    while not stop.is_set():
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv311,
        )
        # up: CONNACK accepted and the socket is still open.
        # ever: CONNACK was accepted on this socket, so a later drop is a disconnect
        # and not "still waiting for the first CONNACK".
        holder = {"up": False, "ever": False}

        def on_connect(client, userdata, flags, reason_code, properties):
            if not _accepted(reason_code):
                logger.warning("mqtt CONNACK rejected: %s", reason_code)
                return
            setup(client)
            holder["ever"] = True
            holder["up"] = True
            if status is not None:
                status.connected = True
            backoff.reset()
            logger.info(
                "mqtt connected to %s:%s", settings.mqtt_host, settings.mqtt_port
            )

        def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
            holder["up"] = False
            if status is not None:
                status.connected = False

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        if on_message is not None:
            client.on_message = on_message

        failure: Exception | None = None
        try:
            client.connect(settings.mqtt_host, settings.mqtt_port, keepalive=30)
            started = time.monotonic()
            while not stop.is_set():
                rc = client.loop(timeout=0.1)
                if rc != mqtt.MQTT_ERR_SUCCESS:
                    raise ConnectionError(f"mqtt loop rc={rc}")
                if holder["up"]:
                    step(client)
                    continue
                if holder["ever"]:
                    raise ConnectionError("mqtt disconnected")
                if time.monotonic() - started > settings.connect_timeout_seconds:
                    raise TimeoutError("timed out waiting for CONNACK")
        except Exception as exc:
            failure = exc
        finally:
            if status is not None:
                status.connected = False
            try:
                client.disconnect()
            except Exception:
                logger.debug("mqtt disconnect failed", exc_info=True)

        if stop.is_set():
            break
        delay = backoff.next_delay()
        if failure is not None:
            logger.warning("mqtt session ended (%s); retrying in %.1fs", failure, delay)
        _sleep(delay, stop)


def _accepted(reason_code: object) -> bool:
    is_failure = getattr(reason_code, "is_failure", None)
    if is_failure is not None:
        return not is_failure
    try:
        return int(reason_code) == 0  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def _sleep(seconds: float, stop: threading.Event) -> None:
    end = time.monotonic() + seconds
    while not stop.is_set():
        remaining = end - time.monotonic()
        if remaining <= 0:
            return
        stop.wait(min(0.05, remaining))
