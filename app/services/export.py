from pathlib import Path

from app.models import DashboardPayload


def write_dashboard_json(payload: DashboardPayload, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(payload.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(destination)
