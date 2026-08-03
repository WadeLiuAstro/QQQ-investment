from app.config import load_rule_config


def test_default_rules_define_all_five_states() -> None:
    rules = load_rule_config()

    assert [state.name for state in rules.states] == [
        "defensive",
        "cautious",
        "neutral",
        "constructive",
        "opportunity",
    ]
    assert rules.states[0].allocation_min == 20
    assert rules.states[-1].dca_multiplier == 2.0
