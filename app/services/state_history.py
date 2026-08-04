from typing import Sequence

from app.models import StateHistory, StateRecord, StateSwitch


def build_state_history(records: Sequence[StateRecord]) -> StateHistory:
    """从时间正序的状态记录序列提取切换事件与当前持续时长。

    - switches：首条记录 + 状态与上一条不同的记录；
    - current_duration_ticks：末尾连续相同状态的记录数（含最后一条）。
    """
    switches: list[StateSwitch] = []
    previous_state: str | None = None
    for record in records:
        if record.state != previous_state:
            switches.append(
                StateSwitch(
                    observed_at=record.generated_at,
                    state=record.state,
                    allocation_min=record.allocation_min,
                    allocation_max=record.allocation_max,
                    dca_multiplier=record.dca_multiplier,
                    reasons=record.reasons,
                )
            )
            previous_state = record.state
    duration = 0
    for record in reversed(records):
        if record.state != previous_state:
            break
        duration += 1
    return StateHistory(switches=switches, current_duration_ticks=duration)
