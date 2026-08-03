from pathlib import Path

from app.models import RuleConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULES_PATH = PROJECT_ROOT / "config" / "default_rules.json"


def load_rule_config(path: Path | None = None) -> RuleConfig:
    rules_path = path or DEFAULT_RULES_PATH
    return RuleConfig.model_validate_json(rules_path.read_text(encoding="utf-8"))
