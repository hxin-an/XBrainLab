from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
INTEGRATION_BRANCH = "integration/assistant-stable-v2"


@pytest.mark.parametrize(
    "workflow_path",
    (
        ".github/workflows/ci.yml",
        ".github/workflows/docs-pages.yml",
    ),
)
def test_assistant_integration_prs_run_existing_workflows(workflow_path: str) -> None:
    workflow = yaml.safe_load((REPO_ROOT / workflow_path).read_text(encoding="utf-8"))
    triggers = workflow.get("on", workflow.get(True))

    assert triggers["pull_request"]["branches"] == [
        "main",
        INTEGRATION_BRANCH,
    ]
