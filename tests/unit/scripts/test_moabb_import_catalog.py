"""The fixed baseline must not disappear when a new release is evaluated."""

from copy import deepcopy
from pathlib import Path

import pytest

from scripts.dev.moabb_user_journeys.import_catalog import (
    load_catalog,
    render_inventory_rows,
    require_no_regressions,
    resolve_case_manifest,
    validate_catalog,
)


def test_human_inventory_matches_executable_catalog():
    path = Path(__file__).resolve().parents[3] / "docs/validation/moabb-inventory.md"
    content = path.read_text(encoding="utf-8")
    table = content[content.index("| Dataset export |") :].split("\n\n", 1)[0]
    assert table + "\n" == render_inventory_rows(load_catalog())


def test_catalog_admission_itself_rejects_a_downgraded_required_case():
    catalog = load_catalog()
    catalog["entries"][0]["status"] = "blocked"
    with pytest.raises(ValueError, match=r"regression.*AlexMI"):
        validate_catalog(catalog)


@pytest.mark.parametrize("hashes", [[], ["d98657f1...8a09f0ea"]])
def test_required_history_needs_complete_evidence_identities(hashes):
    catalog = load_catalog()
    catalog["entries"][0]["evidence_hashes"] = hashes
    with pytest.raises(ValueError, match="evidence identity"):
        validate_catalog(catalog)


def test_fixed_catalog_keeps_required_deferred_and_blocked_distinct() -> None:
    catalog = load_catalog()
    entries = catalog["entries"]
    assert len(entries) == 147
    assert sum(row["status"] == "required" for row in entries) >= 127
    assert {row["id"] for row in entries if row["status"] == "deferred_rights"} == {
        "Shin2017A",
        "Shin2017B",
        "EPFLP300",
        "Lee2024_AC",
        "Lee2024_BS",
        "Lee2024_DL",
        "Lee2024_EL",
        "Lee2024_TV",
        "Liu2020BETA",
    }


def test_release_cannot_hide_failure_by_replacing_a_required_entry() -> None:
    previous = load_catalog()
    current = deepcopy(previous)
    current["entries"][0]["status"] = "blocked"
    current["entries"][2]["status"] = "required"
    current["entries"][2]["evidence_hashes"] = ["1" * 64]  # Catalog-only fixture.
    with pytest.raises(ValueError, match=r"regression.*AlexMI"):
        require_no_regressions(previous, current)


@pytest.mark.parametrize("change", ["remove", "duplicate", "unknown_status", "version"])
def test_catalog_rejects_denominator_and_identity_drift(change: str) -> None:
    catalog = load_catalog()
    if change == "remove":
        catalog["entries"].pop()
    elif change == "duplicate":
        catalog["entries"][-1] = deepcopy(catalog["entries"][0])
    elif change == "unknown_status":
        catalog["entries"][0]["status"] = "skipped"
    else:
        catalog["moabb_release"]["commit"] = "0" * 40
    with pytest.raises(ValueError):
        validate_catalog(catalog)


def test_missing_binding_is_not_an_executed_pass(tmp_path: Path) -> None:
    row = deepcopy(load_catalog()["entries"][0])
    row["case_manifest"] = None
    with pytest.raises(ValueError, match="case manifest"):
        resolve_case_manifest(row, tmp_path)


@pytest.mark.parametrize(
    "path",
    ["../outside.json", "C:/elsewhere/case.json", "/tmp/case.json", "data\\case.json"],
)
def test_manifest_path_cannot_escape_durable_root(tmp_path: Path, path: str) -> None:
    row = {"id": "AlexMI", "case_manifest": {"path": path, "sha256": "0" * 64}}
    with pytest.raises(ValueError, match="relative"):
        resolve_case_manifest(row, tmp_path)


def test_manifest_tampering_is_rejected_before_product_import(tmp_path: Path) -> None:
    path = tmp_path / "case.json"
    path.write_text('{"id":"AlexMI"}', encoding="utf-8")
    row = {"id": "AlexMI", "case_manifest": {"path": "case.json", "sha256": "0" * 64}}
    with pytest.raises(ValueError, match="identity"):
        resolve_case_manifest(row, tmp_path)
