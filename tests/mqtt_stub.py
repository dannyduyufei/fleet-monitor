"""A tiny MQTT 3.1.1 peer for reconnect tests.

It accepts CONNECT, answers with CONNACK, and can drop the socket or deliver
one PUBLISH after SUBSCRIBE. It is not a broker.
"""

import socket
import threading
import traceback


class ScriptedBroker(threading.Thread):
    def __init__(
        self,
        payload: bytes,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        topic: str = "fleet/telemetry",
        drop_first: bool = False,
    ) -> None:
        super().__init__(daemon=True)
        self.payload = payload
        self.host = host
        self.port = port
        self.topic = topic
        self.drop_first = drop_first
        self.ready = threading.Event()
        self.delivered = threading.Event()
        self.accepted = 0
        self.error: str | None = None

    def run(self) -> None:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind((self.host, self.port))
            self.port = server.getsockname()[1]
            server.listen(5)
            server.settimeout(5)
            self.ready.set()
            sessions = 2 if self.drop_first else 1
            for index in range(sessions):
                deliver = not (self.drop_first and index == 0)
                self._session(server, deliver=deliver)
        except Exception:
            self.error = traceback.format_exc()
        finally:
            self.ready.set()
            server.close()

    def _session(self, server: socket.socket, deliver: bool) -> None:
        conn, _ = server.accept()
        self.accepted += 1
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        conn.settimeout(3)
        try:
            read_packet(conn)
            conn.sendall(b"\x20\x02\x00\x00")
            if not deliver:
                return
            deadline_reads = 0
            while deadline_reads < 10:
                deadline_reads += 1
                kind, body = read_packet(conn)
                if kind >> 4 != 8:
                    continue
                conn.sendall(_suback(body))
                conn.sendall(_publish(self.topic, self.payload))
                self.delivered.set()
                conn.settimeout(3)
                while True:
                    read_packet(conn)
        except (ConnectionError, TimeoutError, OSError):
            return
        finally:
            conn.close()


def read_exact(sock: socket.socket, size: int) -> bytes:
    buf = bytearray()
    while len(buf) < size:
        chunk = sock.recv(size - len(buf))
        if not chunk:
            raise ConnectionError("socket closed")
        buf += chunk
    return bytes(buf)


def read_packet(sock: socket.socket) -> tuple[int, bytes]:
    first = read_exact(sock, 1)[0]
    remaining = _remaining_length(sock)
    body = read_exact(sock, remaining) if remaining else b""
    return first, body


def _remaining_length(sock: socket.socket) -> int:
    multiplier = 1
    value = 0
    for _ in range(4):
        digit = read_exact(sock, 1)[0]
        value += (digit & 0x7F) * multiplier
        if digit & 0x80 == 0:
            return value
        multiplier *= 128
    raise ConnectionError("bad remaining length")


def _encode_remaining(length: int) -> bytes:
    out = bytearray()
    while True:
        digit = length % 128
        length //= 128
        if length:
            digit |= 0x80
        out.append(digit)
        if not length:
            return bytes(out)


def _suback(subscribe_body: bytes) -> bytes:
    variable = subscribe_body[:2] + bytes([0x00])
    return bytes([0x90]) + _encode_remaining(len(variable)) + variable


def _publish(topic: str, payload: bytes) -> bytes:
    topic_bytes = topic.encode()
    variable = len(topic_bytes).to_bytes(2, "big") + topic_bytes + payload
    return bytes([0x30]) + _encode_remaining(len(variable)) + variable
