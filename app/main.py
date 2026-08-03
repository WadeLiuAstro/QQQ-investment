from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from app.config import PROJECT_ROOT
from app.db import SnapshotRepository
from app.models import DashboardPayload
from app.scheduler import refresh_once


def create_app(
    repository: SnapshotRepository | None = None,
    export_path: Path | None = None,
    refresh: Callable[[SnapshotRepository, Path], DashboardPayload] = refresh_once,
) -> FastAPI:
    active_repository = repository or SnapshotRepository(PROJECT_ROOT / "data" / "dashboard.sqlite")
    active_export_path = export_path or PROJECT_ROOT / "static" / "data" / "dashboard.json"
    app = FastAPI(title="QQQ 美股投研仪表盘")

    @app.get("/api/dashboard", response_model=DashboardPayload)
    def get_dashboard() -> DashboardPayload:
        payload = active_repository.load_latest_payload()
        if payload is None:
            raise HTTPException(status_code=503, detail="No successful dashboard snapshot exists")
        return payload

    @app.get("/api/health")
    def get_health() -> dict[str, object]:
        payload = active_repository.load_latest_payload()
        return {"sources": payload.sources if payload else {}}

    @app.post("/api/refresh", response_model=DashboardPayload)
    def post_refresh() -> DashboardPayload:
        return refresh(active_repository, active_export_path)

    app.mount("/", StaticFiles(directory=PROJECT_ROOT / "static", html=True), name="static")

    return app


app = create_app()

