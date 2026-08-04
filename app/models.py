from datetime import datetime

from pydantic import BaseModel, Field


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


class ThresholdDistanceRow(BaseModel):
    rule: str
    label: str
    current: float | None = None
    condition: str
    distance: float | None = None
    unit: str
    direction: str | None = None
    available: bool = True
    note: str | None = None


class WatchCondition(BaseModel):
    label: str
    condition: str
    met: bool = False
    note: str | None = None


class ActionCard(BaseModel):
    extra_top_up_ready: bool
    extra_top_up_reason: str
    watch_conditions: list[WatchCondition]
    data_completeness: dict[str, object]


class DashboardPayload(BaseModel):
    generated_at: datetime
    sources: dict[str, SourceStatus]
    decision: Decision | None = None
    market: dict[str, dict[str, object]] = Field(default_factory=dict)
    events: list[MacroEvent] = Field(default_factory=list)
    backtest: dict[str, object] | None = None
    action_card: dict[str, object] | None = None

