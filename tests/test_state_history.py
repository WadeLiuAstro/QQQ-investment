from datetime import UTC, datetime

from app.models import StateRecord
from app.services.state_history import build_state_history


def record(index: int, state: str) -> StateRecord:
    return StateRecord(
        generated_at=datetime(2026, 8, 3, 10, 0, tzinfo=UTC).replace(
            minute=15 * index
        ),
        state=state,
        allocation_min=20,
        allocation_max=60,
        dca_multiplier=1.0,
        reasons=[f"原因-{state}"],
    )


def test_first_record_is_a_switch() -> None:
    history = build_state_history([record(0, "neutral"), record(1, "neutral")])

    assert len(history.switches) == 1
    assert history.switches[0].state == "neutral"


def test_state_change_is_a_switch() -> None:
    history = build_state_history(
        [record(0, "neutral"), record(1, "neutral"), record(2, "constructive")]
    )

    assert len(history.switches) == 2
    assert history.switches[1].state == "constructive"
    assert history.switches[1].observed_at == record(2, "constructive").generated_at
    assert history.switches[1].reasons == ["原因-constructive"]
    assert history.switches[1].allocation_min == 20


def test_same_state_sequence_is_not_multiple_switches() -> None:
    history = build_state_history(
        [record(0, "neutral"), record(1, "neutral"), record(2, "neutral")]
    )

    assert len(history.switches) == 1


def test_current_duration_counts_trailing_same_states() -> None:
    history = build_state_history(
        [
            record(0, "neutral"),
            record(1, "cautious"),
            record(2, "cautious"),
            record(3, "cautious"),
        ]
    )

    assert history.current_duration_ticks == 3


def test_current_duration_is_one_for_single_record() -> None:
    history = build_state_history([record(0, "neutral")])

    assert history.current_duration_ticks == 1


def test_empty_records_produce_empty_history() -> None:
    history = build_state_history([])

    assert history.switches == []
    assert history.current_duration_ticks == 0
