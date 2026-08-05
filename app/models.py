from datetime import date, datetime
from typing import Literal

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


class StateRecord(BaseModel):
    generated_at: datetime
    state: str
    allocation_min: int
    allocation_max: int
    dca_multiplier: float
    reasons: list[str]


class StateSwitch(BaseModel):
    observed_at: datetime
    state: str
    allocation_min: int
    allocation_max: int
    dca_multiplier: float
    reasons: list[str]


class StateHistory(BaseModel):
    switches: list[StateSwitch]
    current_duration_ticks: int


class Alert(BaseModel):
    key: str
    kind: str
    title: str
    detail: str


class Breadth(BaseModel):
    qqqe_price: float | None = None
    relative_strength_5d: float | None = None
    relative_strength_20d: float | None = None
    qqq_return_20d: float | None = None
    label: str | None = None
    available: bool = True
    note: str | None = None


class AttributionRequest(BaseModel):
    classification: Literal["liquidity_panic", "structural", "watch"]
    reason: str = Field(min_length=1, max_length=500)


MonitoringTone = Literal["positive", "negative", "warning", "neutral", "unavailable"]
MonitoringDataStatus = Literal["available", "partial", "unavailable"]


class MonitoringPoint(BaseModel):
    observed_at: datetime
    value: float


class MonitoringFactor(BaseModel):
    key: str
    label: str
    score: float
    rating: str | None = None
    change: float | None = None
    tone: MonitoringTone = "neutral"


class MonitoringDetails(BaseModel):
    comparisons: dict[str, float | None] = Field(default_factory=dict)
    history: list[MonitoringPoint] = Field(default_factory=list)
    factors: list[MonitoringFactor] = Field(default_factory=list)
    term_ratio: float | None = None
    term_status: str | None = None
    events: list[MacroEvent] = Field(default_factory=list)


class MonitoringMetric(BaseModel):
    key: str
    label: str
    current: float | None = None
    unit: str | None = None
    change_1d: float | None = None
    change_unit: str | None = None
    direction_5d: str | None = None
    momentum_20d: float | None = None
    momentum_unit: str | None = None
    as_of: date | None = None
    tone: MonitoringTone = "neutral"
    display_status: str = "数据正常"
    data_status: MonitoringDataStatus = "available"
    available: bool = True
    stale: bool = False
    note: str | None = None


class MonitoringSummary(BaseModel):
    key: str
    label: str
    display_value: str
    status: str
    tone: MonitoringTone
    data_status: MonitoringDataStatus = "available"
    available: bool = True
    stale: bool = False
    as_of: date | None = None


class MonitoringGroup(BaseModel):
    key: str
    label: str
    status: str
    data_status: MonitoringDataStatus = "available"
    available: bool = True
    stale: bool = False
    metrics: list[MonitoringMetric] = Field(default_factory=list)
    details: MonitoringDetails = Field(default_factory=MonitoringDetails)


class MonitoringPayload(BaseModel):
    generated_at: datetime
    summary: list[MonitoringSummary]
    groups: dict[str, MonitoringGroup]


class DashboardPayload(BaseModel):
    generated_at: datetime
    sources: dict[str, SourceStatus]
    decision: Decision | None = None
    market: dict[str, dict[str, object]] = Field(default_factory=dict)
    events: list[MacroEvent] = Field(default_factory=list)
    backtest: dict[str, object] | None = None
    action_card: dict[str, object] | None = None
    state_history: dict[str, object] | None = None
    alerts: list[dict[str, object]] | None = None
    monitoring: MonitoringPayload | None = None

