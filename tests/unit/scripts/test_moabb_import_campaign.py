"""Import campaign completion and reuse must fail closed."""

import json
import subprocess

import pytest

from scripts.dev import run_moabb_import_conformance as campaign
from scripts.dev.moabb_user_journeys.import_catalog import CATALOG_PATH, load_catalog
from scripts.dev.run_moabb_import_conformance import (
    completion_status,
    require_same_identity,
)


def test_missing_required_case_cannot_be_a_complete_campaign():
    rows = [{"id": "one", "status": "required"}, {"id": "two", "status": "required"}]
    assert completion_status(rows, {"one": {"status": "passed"}}) == "failed"


def test_known_blocker_is_visible_but_not_a_required_case_failure():
    rows = [{"id": "one", "status": "required"}, {"id": "two", "status": "blocked"}]
    assert completion_status(rows, {"one": {"status": "passed"}}) == "passed"


@pytest.mark.parametrize("field", ["source", "environment", "catalog"])
def test_resume_rejects_each_changed_identity(field):
    original = {"source": "a", "environment": "b", "catalog": "c"}
    changed = {**original, field: "different"}
    with pytest.raises(ValueError, match="identity"):
        require_same_identity(original, changed)


def test_identical_resume_is_allowed():
    require_same_identity({"source": "a"}, {"source": "a"})


def test_campaign_rejects_downgrade_of_previously_promoted_case(tmp_path, monkeypatch):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args], timeout=15)  # noqa: S603,S607 - fixed Git fixture commands, no user input.

    git("init", "--quiet")
    path = tmp_path / CATALOG_PATH.relative_to(campaign.REPO_ROOT)
    path.parent.mkdir(parents=True)
    catalog = load_catalog()
    row = next(row for row in catalog["entries"] if row["id"] == "BNCI2015_006")
    row["status"] = "required"
    row["evidence_hashes"] = ["1" * 64]  # This Git-only fixture does not execute EEG.
    path.write_text(json.dumps(catalog), encoding="utf-8")
    git("add", ".")
    git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "accepted",
    )
    git("update-ref", "refs/remotes/origin/main", "HEAD")
    monkeypatch.setattr(campaign, "REPO_ROOT", tmp_path)
    campaign._identity(path)
    row["status"] = "blocked"
    path.write_text(json.dumps(catalog), encoding="utf-8")
    with pytest.raises(ValueError, match=r"regression.*BNCI2015_006"):
        campaign._identity(path)
