from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
DOCS_WORKFLOW = ROOT / ".github" / "workflows" / "docs-pages.yml"

ACTION_PINS = {
    # Public GitHub Action commit pins, not credentials.
    "actions/checkout": "11d5960a326750d5838078e36cf38b85af677262",  # pragma: allowlist secret
    "actions/setup-python": "a26af69be951a213d495a4c3e4e4022e16d87065",  # pragma: allowlist secret
    "actions/cache": "0057852bfaa89a56745cba8c7296529d2fc39830",  # pragma: allowlist secret
    "actions/upload-artifact": "ea165f8d65b6e75b540449e92b4886f43607fa02",  # pragma: allowlist secret
    "actions/download-artifact": "d3f86a106a0bac45b974a628896c90dbdf5c8093",  # pragma: allowlist secret
    "actions/configure-pages": "983d7736d9b0ae728b81ab479565c72886d7745b",  # pragma: allowlist secret
    "actions/upload-pages-artifact": "56afc609e74202658d3ffba0e8f6dda462b719fa",  # pragma: allowlist secret
    "actions/deploy-pages": "d6db90164ac5ed86f2b6aed7e0febac5b3c0c03e",  # pragma: allowlist secret
}


def _workflow(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _steps(workflow: dict) -> list[dict]:
    return [step for job in workflow["jobs"].values() for step in job.get("steps", ())]


def test_all_official_actions_are_pinned_to_reviewed_immutable_shas() -> None:
    observed: set[str] = set()
    for path in (CI_WORKFLOW, DOCS_WORKFLOW):
        for step in _steps(_workflow(path)):
            reference = step.get("uses")
            if not isinstance(reference, str) or not reference.startswith("actions/"):
                continue
            owner, sha = reference.split("@", 1)
            assert sha == ACTION_PINS[owner]
            observed.add(owner)

    assert observed == set(ACTION_PINS)


def test_ci_poetry_bootstrap_and_venv_cache_are_lock_exact() -> None:
    workflow = _workflow(CI_WORKFLOW)
    assert workflow["env"] == {
        "POETRY_VERSION": "2.3.4",
        "CI_PYTHON_VERSION": "3.11",
    }
    steps = _steps(workflow)
    poetry_installers = [step for step in steps if step.get("name") == "Install Poetry"]
    dependency_installers = [
        step
        for step in steps
        if step.get("name") == "Install dependencies"
        and str(step.get("run", "")).startswith("poetry ")
    ]
    assert len(poetry_installers) == 6
    assert all(
        'python -m pip install "poetry==${POETRY_VERSION}"' in step["run"]
        for step in poetry_installers
    )
    assert len(dependency_installers) == 6
    assert all(
        step["run"] == "poetry sync --no-interaction" for step in dependency_installers
    )

    venv_cache_steps = [
        step for step in steps if str(step.get("with", {}).get("path", "")) == ".venv"
    ]
    assert len(venv_cache_steps) == 6
    for step in venv_cache_steps:
        cache = step["with"]
        assert "restore-keys" not in cache
        key = cache["key"]
        assert "${{ runner.os }}-${{ runner.arch }}" in key
        assert "py${{ env.CI_PYTHON_VERSION }}" in key
        assert "poetry-${{ env.POETRY_VERSION }}" in key
        assert "${{ hashFiles('poetry.lock') }}" in key


def test_public_fixture_cache_does_not_restore_a_stale_manifest() -> None:
    steps = _steps(_workflow(CI_WORKFLOW))
    fixture_cache = next(
        step for step in steps if step.get("name") == "Cache pinned public EEG fixtures"
    )
    assert "restore-keys" not in fixture_cache["with"]
