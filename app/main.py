from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from app.config import PROJECT_ROOT
from app.db import SnapshotRepository
from app.models import AttributionRequest, DashboardPayload
from app.scheduler import create_refresh_scheduler, refresh_once
from app.services.export import write_dashboard_json


def create_app(
    repository: SnapshotRepository | None = None,
    export_path: Path | None = None,
    refresh: Callable[[SnapshotRepository, Path], DashboardPayload] = refresh_once,
) -> FastAPI:
    active_repository = repository or SnapshotRepository(PROJECT_ROOT / "data" / "dashboard.sqlite")
    active_export_path = export_path or PROJECT_ROOT / "static" / "data" / "dashboard.json"
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler = create_refresh_scheduler(active_repository, active_export_path)
        app.state.refresh_scheduler = scheduler
        try:
            yield
        finally:
            scheduler.shutdown(wait=False)

    app = FastAPI(title="QQQ 美股投研仪表盘", lifespan=lifespan)

    @app.get("/api/dashboard", response_model=DashboardPayload)
    def get_dashboard() -> DashboardPayload:
        payload = active_repository.load_latest_payload()
        if payload is None and active_export_path.exists():
            payload = DashboardPayload.model_validate_json(
                active_export_path.read_text(encoding="utf-8")
            )
            active_repository.save_payload(payload)
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

    @app.get("/api/attribution")
    def get_attribution() -> dict[str, object]:
        payload = active_repository.load_latest_payload()
        attribution = _payload_attribution(payload)
        if attribution is None:
            return {"available": False, "gate": None, "decision": None, "evidence": None}
        # 动态组装 gate，保证决策变更后 GET 结果即时一致
        from app.scheduler import attach_attribution_gate

        refreshed = attach_attribution_gate(payload, active_repository)
        attribution = _payload_attribution(refreshed) or {}
        return {
            "available": True,
            "gate": attribution.get("gate"),
            "decision": attribution.get("decision"),
            "evidence": attribution.get("evidence"),
        }

    @app.post("/api/attribution")
    def post_attribution(body: AttributionRequest) -> dict[str, object]:
        payload = active_repository.load_latest_payload()
        attribution = _payload_attribution(payload)
        evidence = attribution.get("evidence") if attribution else None
        if not isinstance(evidence, dict):
            raise HTTPException(status_code=400, detail="无大跌证据集，无法拍板")
        incident_key = str(evidence.get("day") or "unknown")
        decided_at = datetime.now(UTC)
        expires_at = (
            decided_at + timedelta(hours=48) if body.classification == "watch" else None
        )
        active_repository.save_attribution_decision(
            incident_key=incident_key,
            classification=body.classification,
            reason=body.reason,
            decided_at=decided_at,
            expires_at=expires_at,
        )
        active_repository.append_decision_log(
            category="attribution",
            incident_key=incident_key,
            content={
                "classification": body.classification,
                "reason": body.reason,
            },
        )
        from app.scheduler import attach_attribution_gate

        updated = attach_attribution_gate(payload, active_repository)
        active_repository.save_payload(updated)
        write_dashboard_json(updated, active_export_path)
        updated_attribution = _payload_attribution(updated) or {}
        return {"ok": True, "gate": updated_attribution.get("gate")}

    @app.get("/api/decision-log")
    def get_decision_log() -> dict[str, object]:
        return {"entries": active_repository.load_decision_log(limit=50)}

    app.mount("/", StaticFiles(directory=PROJECT_ROOT / "static", html=True), name="static")

    return app


def _payload_attribution(payload: DashboardPayload | None) -> dict[str, object] | None:
    if payload is None or payload.market is None:
        return None
    qqq = payload.market.get("qqq")
    attribution = qqq.get("attribution") if qqq else None
    return attribution if isinstance(attribution, dict) else None


app = create_app()

