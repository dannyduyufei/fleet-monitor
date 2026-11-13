"""Latest robot state in SQLite.

Messages are applied only when their sequence number is newer than the one
already stored for that robot. A replay or a late packet leaves the row as it
was, including last_seen, so it cannot postpone an offline alert.
"""

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

from fleet_monitor.telemetry import Telemetry


@dataclass(frozen=True)
class Robot:
    robot_id: str
    seq: int
    last_seen: float
    battery: float
    x: float
    y: float
    theta: float
    task_id: str
    task_state: str
    task_progress: float
    progress_since: float


class Store:
    def __init__(self, path: str) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS robots (
                robot_id TEXT PRIMARY KEY,
                seq INTEGER NOT NULL,
                last_seen REAL NOT NULL,
                battery REAL NOT NULL,
                x REAL NOT NULL,
                y REAL NOT NULL,
                theta REAL NOT NULL,
                task_id TEXT NOT NULL,
                task_state TEXT NOT NULL,
                task_progress REAL NOT NULL,
                progress_since REAL NOT NULL
            )
            """
        )
        self._conn.commit()

    def apply(self, msg: Telemetry, now: float) -> bool:
        """Store msg if it is the newest snapshot for that robot.

        Returns True when the row changes. now is the ingest clock, recorded
        as last_seen only for snapshots that are actually applied.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT seq, task_id, task_state, task_progress, progress_since "
                "FROM robots WHERE robot_id = ?",
                (msg.robot_id,),
            ).fetchone()
            if row is not None and msg.seq <= row["seq"]:
                return False
            same_task = (
                row is not None
                and row["task_id"] == msg.task_id
                and row["task_state"] == msg.task_state
                and row["task_progress"] == msg.task_progress
            )
            progress_since = float(row["progress_since"]) if same_task else now
            self._conn.execute(
                """
                INSERT INTO robots (
                    robot_id, seq, last_seen, battery, x, y, theta,
                    task_id, task_state, task_progress, progress_since
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(robot_id) DO UPDATE SET
                    seq = excluded.seq,
                    last_seen = excluded.last_seen,
                    battery = excluded.battery,
                    x = excluded.x,
                    y = excluded.y,
                    theta = excluded.theta,
                    task_id = excluded.task_id,
                    task_state = excluded.task_state,
                    task_progress = excluded.task_progress,
                    progress_since = excluded.progress_since
                """,
                (
                    msg.robot_id,
                    msg.seq,
                    now,
                    msg.battery,
                    msg.x,
                    msg.y,
                    msg.theta,
                    msg.task_id,
                    msg.task_state,
                    msg.task_progress,
                    progress_since,
                ),
            )
            self._conn.commit()
            return True

    def get_robot(self, robot_id: str) -> Robot | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM robots WHERE robot_id = ?",
                (robot_id,),
            ).fetchone()
        return _robot(row) if row is not None else None

    def list_robots(self) -> list[Robot]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM robots ORDER BY robot_id"
            ).fetchall()
        return [_robot(row) for row in rows]

    def close(self) -> None:
        self._conn.close()


def _robot(row: sqlite3.Row) -> Robot:
    return Robot(
        robot_id=row["robot_id"],
        seq=row["seq"],
        last_seen=row["last_seen"],
        battery=row["battery"],
        x=row["x"],
        y=row["y"],
        theta=row["theta"],
        task_id=row["task_id"],
        task_state=row["task_state"],
        task_progress=row["task_progress"],
        progress_since=row["progress_since"],
    )
