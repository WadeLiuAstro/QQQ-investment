from datetime import datetime

from pydantic import BaseModel


class StateRule(BaseModel):
    name: str
    allocation_min: int
    allocation_max: int
    dca_multiplier: float


class RuleConfig(BaseModel):
    states: list[StateRule]
    thresholds: dict[str, float]


class SourceStatus(BaseModel):
    source: str
    available: bool
    checked_at: datetime
    stale: bool = False
    message: str | None = None


class MacroEvent(BaseModel):
    kind: str
    title: str
    event_at: datetime
    source: str

class Decision(BaseModel):
    state: str
    allocation_min: int
    allocation_max: int
    target_allocation: float
    dca_multiplier: float
    reasons: list[str]
    non_triggers: list[str]
    actionability: str


class DashboardPayload(BaseModel):
    generated_at: datetime
    sources: dict[str, SourceStatus]
    decision: Decision | None = None
