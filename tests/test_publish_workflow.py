from pathlib import Path


def test_publish_workflow_deploys_after_push_to_main() -> None:
    workflow = Path(".github/workflows/publish-dashboard.yml").read_text(encoding="utf-8")

    assert "push:" in workflow
    assert "branches: [main]" in workflow
    assert "workflow_dispatch:" in workflow
    assert 'cron: "*/15 * * * 1-5"' in workflow