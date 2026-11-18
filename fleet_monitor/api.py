"""HTTP API for the latest fleet state and the alerts derived from it."""

import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from fleet_monitor import __version__
from fleet_monitor.alerts import evaluate_fleet
from fleet_monitor.config import Settings, load_settings
from fleet_monitor.ingest import consume_forever
from fleet_monitor.mqtt_loop import IngestStatus
from fleet_monitor.store import Robot, Store

logger = logging.getLogger(__name__)


class HealthOut(BaseModel):
    status: str
    mqtt_connected: bool


class PoseOut(BaseModel):
    x: float
    y: float
    theta: float


class TaskOut(BaseModel):
    id: str
    state: str
    progress: float


class RobotOut(BaseModel):
    robot_id: str
    seq: int
    last_seen: float = Field(description="Unix seconds when this snapshot was accepted")
    battery: float
    pose: PoseOut
    task: TaskOut


class AlertOut(BaseModel):
    robot_id: str
    kind: str = Field(description="offline, low_battery, or stuck_task")
    detail: str


def create_app(
    settings: Settings | None = None,
    store: Store | None = None,
    start_ingest: bool = True,
) -> FastAPI:
    settings = settings or load_settings()
    store = store or Store(settings.database_path)
    status = IngestStatus()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        stop = threading.Event()
        thread: threading.Thread | None = None
        if start_ingest:
            thread = threading.Thread(
                target=consume_forever,
                args=(settings, store, stop, status),
                name="mqtt-ingest",
                daemon=True,
            )
            thread.start()
        yield
        stop.set()
        if thread is not None:
            thread.join(timeout=2)

    app = FastAPI(
        title="fleet-monitor",
        version=__version__,
        summary="Fleet state and alerts for simulated robots.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.store = store
    app.state.ingest_status = status

    @app.get("/health", response_model=HealthOut)
    def health() -> HealthOut:
        return HealthOut(status="ok", mqtt_connected=status.connected)

    @app.get("/robots", response_model=list[RobotOut])
    def list_robots() -> list[RobotOut]:
        return [_robot_out(robot) for robot in store.list_robots()]

    @app.get("/robots/{robot_id}", response_model=RobotOut)
    def get_robot(robot_id: str) -> RobotOut:
        robot = store.get_robot(robot_id)
        if robot is None:
            raise HTTPException(status_code=404, detail="robot not found")
        return _robot_out(robot)

    @app.get("/alerts", response_model=list[AlertOut])
    def list_alerts() -> list[AlertOut]:
        found = evaluate_fleet(store.list_robots(), time.time(), settings)
        return [
            AlertOut(robot_id=alert.robot_id, kind=alert.kind, detail=alert.detail)
            for alert in found
        ]

    return app


def _robot_out(robot: Robot) -> RobotOut:
    return RobotOut(
        robot_id=robot.robot_id,
        seq=robot.seq,
        last_seen=robot.last_seen,
        battery=robot.battery,
        pose=PoseOut(x=robot.x, y=robot.y, theta=robot.theta),
        task=TaskOut(
            id=robot.task_id,
            state=robot.task_state,
            progress=robot.task_progress,
        ),
    )


app = create_app()
