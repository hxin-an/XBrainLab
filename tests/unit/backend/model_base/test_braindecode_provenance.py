from __future__ import annotations

import csv
import hashlib
from importlib.metadata import distribution
from pathlib import Path

from XBrainLab.backend.model_base.model_catalog import (
    discover_braindecode_model_specs,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_MANIFEST_PATH = (
    _REPO_ROOT / "XBrainLab/backend/model_base/legacy_braindecode/PROVENANCE.tsv"
)
_APPROVED_LEGACY_LICENSES = {"BSD-3-Clause", "MIT", "Apache-2.0"}
_EXCLUDED_SYMBOLS = {
    "BrainModule",
    "EEGMiner",
    "EMG2QwertyNet",
    "MetaNeuromotorHand",
}


def _manifest_rows() -> list[dict[str, str]]:
    lines = [
        line
        for line in _MANIFEST_PATH.read_text(encoding="utf-8").splitlines()
        if not line.startswith("#")
    ]
    return list(csv.DictReader(lines, delimiter="\t"))


def test_model_provenance_covers_every_pinned_contract_once() -> None:
    rows = _manifest_rows()
    manifested_symbols = [
        symbol for row in rows for symbol in row["symbols"].split(",") if symbol
    ]
    catalog_symbols = [spec.aliases[0] for spec in discover_braindecode_model_specs()]

    assert len(rows) == len({row["upstream_path"] for row in rows})
    assert len(manifested_symbols) == len(set(manifested_symbols)) == 61
    assert manifested_symbols == catalog_symbols


def test_model_provenance_matches_exact_installed_sources() -> None:
    package_root = Path(distribution("braindecode").locate_file(""))

    for row in _manifest_rows():
        source_path = package_root / row["upstream_path"]
        assert source_path.is_file(), row["upstream_path"]
        actual_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
        assert actual_hash == row["sha256"], row["upstream_path"]


def test_only_approved_source_licenses_enter_legacy_allowlist() -> None:
    rows = _manifest_rows()
    excluded_symbols = {
        symbol
        for row in rows
        if row["disposition"] == "excluded"
        for symbol in row["symbols"].split(",")
    }

    assert excluded_symbols == _EXCLUDED_SYMBOLS
    for row in rows:
        if row["disposition"] == "vendor":
            assert row["license"] in _APPROVED_LEGACY_LICENSES
        else:
            assert row["disposition"] == "excluded"
            assert row["license"] == "CC-BY-NC-4.0"


def test_catalog_legacy_eligibility_matches_provenance_allowlist() -> None:
    rows_by_symbol = {
        symbol: row for row in _manifest_rows() for symbol in row["symbols"].split(",")
    }

    for spec in discover_braindecode_model_specs():
        row = rows_by_symbol[spec.aliases[0]]
        expected_allowed = row["disposition"] == "vendor"
        assert spec.license_id == row["license"]
        assert spec.legacy_copy_allowed is expected_allowed
        assert bool(spec.legacy_unavailable_reason) is not expected_allowed
