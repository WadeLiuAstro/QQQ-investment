from pydantic import BaseModel


class StateRule(BaseModel):
    name: str
    allocation_min: int
    allocation_max: int
    dca_multiplier: float


class RuleConfig(BaseModel):
    states: list[StateRule]
    thresholds: dict[str, float]
