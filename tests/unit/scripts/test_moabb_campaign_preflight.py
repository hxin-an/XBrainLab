from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path

import pytest

from scripts.dev.moabb_campaign_preflight import (
    EXPECTED_CLASS_NAMES,
    EXPECTED_MOABB_COMMIT,
    EXPECTED_MOABB_VERSION,
    PreflightInputs,
    evaluate_preflight,
    load_campaign_manifest,
    poetry_dependency_blockers,
)


def _write_manifest(tmp_path: Path) -> Path:
    files = []
    output_formats = ("EDF", "BrainVision", "EEGLAB")
    for index, class_name in enumerate(EXPECTED_CLASS_NAMES):
        is_mirror = class_name == "Ma2020"
        source_artifacts = [
            {
                "relative_path": f"{class_name}/source.bin",
                "size_bytes": 128 if is_mirror else 1_000_000,
                "checksum": {
                    "algorithm": "sha256",
                    "value": "a" * 64,
                },
            }
        ]
        bids_artifacts = [
            {
                "relative_path": "dataset_description.json",
                "size_bytes": 1_000_000 if is_mirror else 128,
                "checksum": {
                    "algorithm": "sha256",
                    "value": "b" * 64,
                },
            }
        ]
        row = {
            "moabb_class": class_name,
            "source_mode": ("formal_bids_mirror" if is_mirror else "moabb_convert"),
            "subjects": [1, 2, 3, 4, 5] if index < 5 else [1, 2],
            "output_format": (
                "BDF" if is_mirror else output_formats[index % len(output_formats)]
            ),
            "status": "ready",
            "source_download_bytes": 1_000_000,
            "retained_source_bytes": 128 if is_mirror else 1_000_000,
            "source_checksum_status": "verified",
            "source_artifacts": source_artifacts,
            "source_revision_sha256": _canonical_sha256(source_artifacts),
            "source_root": f"/mnt/d/xbrainlab/moabb/native/{class_name}",
            "source_checksum_manifest": (
                f"/mnt/d/xbrainlab/moabb/checksums/{class_name}.source.sha256"
            ),
            "bids_checksum_status": "verified",
            "bids_artifacts": bids_artifacts,
            "dataset_revision_sha256": _canonical_sha256(bids_artifacts),
            "bids_root": f"/mnt/d/xbrainlab/moabb/bids/{class_name}/MNE-BIDS-x",
            "checksum_manifest": (
                f"/mnt/d/xbrainlab/moabb/checksums/{class_name}.sha256"
            ),
            "license_status": "verified",
            "resource_status": "verified",
        }
        if is_mirror:
            upstream = [
                {
                    **bids_artifacts[0],
                    "source_url": (
                        "https://data.nemar.invalid/v1/dataset_description.json"
                    ),
                    "upstream_checksum": {
                        "algorithm": "git",
                        "value": "c" * 40,
                    },
                }
            ]
            row.update(
                upstream_download_status="verified",
                upstream_download_bytes=1_000_000,
                upstream_download_artifacts=upstream,
                upstream_download_revision_sha256=_canonical_sha256(upstream),
            )
        files.append(row)
    payload = {
        "schema_version": "1.0.0",
        "moabb_release": {
            "version": EXPECTED_MOABB_VERSION,
            "commit": EXPECTED_MOABB_COMMIT,
        },
        "resource_policy": {
            "minimum_headroom_multiplier": 4,
            "minimum_artifact_headroom_bytes": 10_000_000,
        },
        "materialization": {
            "mne_data_root": "/mnt/d/xbrainlab/moabb/native",
            "output_root": "/mnt/d/xbrainlab/moabb/bids",
            "checksum_root": "/mnt/d/xbrainlab/moabb/checksums",
            "environment_identity_sha256": "c" * 64,
            "conversion_identity_sha256": "d" * 64,
            "campaign_product_identity_sha256": "e" * 64,
        },
        "datasets": files,
    }
    path = tmp_path / "campaign.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _inputs(tmp_path: Path, manifest_path: Path) -> PreflightInputs:
    data_root = tmp_path / "mne-data"
    output_root = tmp_path / "bids-output"
    data_root.mkdir()
    output_root.mkdir()
    return PreflightInputs(
        manifest_path=manifest_path,
        mne_data_root=data_root,
        output_root=output_root,
        free_bytes=10**12,
        distribution_version=lambda name: {
            "moabb": EXPECTED_MOABB_VERSION,
            "pyxdf": "1.17.0",
            "mne-bids": "0.19.0",
            "pybv": "0.7.6",
            "edfio": "0.4.8",
            "edflib-python": "1.0.8",
            "eeglabio": "0.1.0",
        }[name],
        moabb_class_names=lambda: EXPECTED_CLASS_NAMES,
        moabb_has_generic_bids_conversion=lambda: True,
        configured_mne_data=None,
        poetry_dependency_blockers=list,
        frozen_integrity_error=lambda _row, _source, _bids, _checksums: None,
    )


def test_preflight_passes_only_complete_pinned_d_drive_campaign(tmp_path: Path) -> None:
    manifest_path = _write_manifest(tmp_path)
    inputs = _inputs(tmp_path, manifest_path)
    inputs = inputs._replace(
        mne_data_root=Path("/mnt/d/xbrainlab/moabb/native"),
        output_root=Path("/mnt/d/xbrainlab/moabb/bids"),
    )

    result = evaluate_preflight(inputs)

    assert result["status"] == "ready"
    assert result["campaign_allowed"] is True
    assert result["dataset_count"] == 15
    assert result["materialization_phase"] == "complete"
    assert result["remaining_source_download_bytes"] == 0
    assert result["retained_materialized_bytes"] == 15_001_920
    assert result["required_headroom_bytes"] == 10_000_000
    assert result["blockers"] == []


def test_preflight_rejects_mirror_upstream_inventory_drift(tmp_path: Path) -> None:
    manifest_path = _write_manifest(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mirror = next(
        row
        for row in manifest["datasets"]
        if row["source_mode"] == "formal_bids_mirror"
    )
    mirror["upstream_download_artifacts"][0]["checksum"]["value"] = "d" * 64
    mirror["upstream_download_revision_sha256"] = _canonical_sha256(
        mirror["upstream_download_artifacts"]
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    inputs = _inputs(tmp_path, manifest_path)._replace(
        mne_data_root=Path("/mnt/d/xbrainlab/moabb/native"),
        output_root=Path("/mnt/d/xbrainlab/moabb/bids"),
    )

    result = evaluate_preflight(inputs)

    assert result["campaign_allowed"] is False
    assert any(
        "upstream download inventory differs from frozen BIDS bytes" in blocker
        for blocker in result["blockers"]
    )


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (
            lambda manifest: manifest["datasets"][0].pop("source_artifacts"),
            "checksum",
        ),
        (
            lambda manifest: manifest["datasets"][1].pop("bids_artifacts"),
            "BIDS checksum",
        ),
        (
            lambda manifest: manifest["datasets"][4].update(
                license_status="LEGAL_REVIEW"
            ),
            "Nakanishi2015",
        ),
        (
            lambda manifest: manifest["datasets"][6].update(
                resource_status="RESOURCE_PREFLIGHT_BLOCKED"
            ),
            "Ma2020",
        ),
    ],
)
def test_manifest_uncertainty_blocks_campaign(
    tmp_path: Path, mutation: object, expected: str
) -> None:
    path = _write_manifest(tmp_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    mutation(manifest)  # type: ignore[operator]
    path.write_text(json.dumps(manifest), encoding="utf-8")

    result = evaluate_preflight(_inputs(tmp_path, path))

    assert result["status"] == "blocked"
    assert result["campaign_allowed"] is False
    assert any(expected in blocker for blocker in result["blockers"])


def test_local_use_only_license_is_admitted_only_with_no_redistribution(
    tmp_path: Path,
) -> None:
    path = _write_manifest(tmp_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    row = manifest["datasets"][4]
    row.update(
        license_status="local-use-only",
        redistribution_allowed=False,
        license_note="Upstream license is unknown; retain only in the local campaign.",
    )
    path.write_text(json.dumps(manifest), encoding="utf-8")

    inputs = _inputs(tmp_path, path)._replace(
        mne_data_root=Path("/mnt/d/xbrainlab/moabb/native"),
        output_root=Path("/mnt/d/xbrainlab/moabb/bids"),
    )
    admitted = evaluate_preflight(inputs)
    assert admitted["campaign_allowed"] is True

    row.pop("redistribution_allowed")
    path.write_text(json.dumps(manifest), encoding="utf-8")
    blocked = evaluate_preflight(inputs)
    assert blocked["campaign_allowed"] is False
    assert any("redistribution" in item for item in blocked["blockers"])


def test_output_format_inventory_is_manifest_declared_and_bounded(
    tmp_path: Path,
) -> None:
    path = _write_manifest(tmp_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["datasets"][0]["output_format"] = "FIF"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    result = evaluate_preflight(_inputs(tmp_path, path))

    assert result["campaign_allowed"] is False
    assert any("output format" in item for item in result["blockers"])


def test_preflight_rejects_weak_or_mismatched_frozen_tree_identity(
    tmp_path: Path,
) -> None:
    path = _write_manifest(tmp_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    source = manifest["datasets"][0]
    source["source_artifacts"][0]["checksum"] = {
        "algorithm": "md5",
        "value": "a" * 32,
    }
    bids = manifest["datasets"][1]
    bids["dataset_revision_sha256"] = "f" * 64
    path.write_text(json.dumps(manifest), encoding="utf-8")

    result = evaluate_preflight(_inputs(tmp_path, path))

    assert result["campaign_allowed"] is False
    assert any("SHA256" in item for item in result["blockers"])
    assert any("BIDS aggregate checksum" in item for item in result["blockers"])


def test_final_preflight_rehashes_actual_source_and_bids_trees(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.dev import moabb_campaign_preflight as preflight_module

    monkeypatch.setattr(preflight_module, "_is_d_drive_mount", lambda _path: True)
    path = _write_manifest(tmp_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    source_owner = tmp_path / "native"
    bids_owner = tmp_path / "bids"
    checksum_owner = tmp_path / "checksums"
    source_owner.mkdir()
    bids_owner.mkdir()
    checksum_owner.mkdir()
    (checksum_owner / "bids-validation").mkdir()
    manifest["materialization"].update(
        mne_data_root=str(source_owner),
        output_root=str(bids_owner),
        checksum_root=str(checksum_owner),
    )
    from scripts.dev.moabb_dataset_materializer import (
        _canonical_sha256 as materializer_sha256,
    )
    from scripts.dev.moabb_dataset_materializer import (
        _hash_tree,
        _sha256_manifest_text,
        frozen_dataset_integrity_error,
    )

    for row in manifest["datasets"]:
        class_name = row["moabb_class"]
        source_root = source_owner / class_name
        conversion_parent = bids_owner / class_name
        bids_root = conversion_parent / "MNE-BIDS-test"
        source_root.mkdir()
        bids_root.mkdir(parents=True)
        (source_root / "source.bin").write_bytes(f"source:{class_name}".encode())
        (bids_root / "dataset_description.json").write_text(
            '{"Name":"test","BIDSVersion":"1.9.0"}',
            encoding="utf-8",
        )
        source_artifacts, source_revision = _hash_tree(source_root)
        bids_artifacts, bids_revision = _hash_tree(bids_root)
        source_manifest = checksum_owner / f"{class_name}.source.sha256"
        bids_manifest = checksum_owner / f"{class_name}.sha256"
        source_manifest.write_text(
            _sha256_manifest_text(source_artifacts), encoding="utf-8"
        )
        bids_manifest.write_text(
            _sha256_manifest_text(bids_artifacts), encoding="utf-8"
        )
        validation = {
            "status": "passed",
            "validator": "bids-validator-deno",
            "required_version": "2.4.1",
            "version": "2.4.1",
            "argv": [
                "bids-validator-deno",
                str(bids_root),
                "--format",
                "json",
                "--max-rows",
                "-1",
            ],
            "exit_code": 0,
            "error_count": 0,
            "warning_count": 1,
            "warning_codes": ["README_FILE_MISSING"],
            "report": {"issues": {"issues": []}},
        }
        validation["report_sha256"] = materializer_sha256(validation["report"])
        validation_path = checksum_owner / "bids-validation" / f"{class_name}.json"
        validation_path.write_text(json.dumps(validation), encoding="utf-8")
        row.update(
            source_root=str(source_root),
            conversion_parent=str(conversion_parent),
            bids_root=str(bids_root),
            source_artifacts=source_artifacts,
            source_revision_sha256=source_revision,
            source_download_bytes=sum(item["size_bytes"] for item in source_artifacts),
            bids_artifacts=bids_artifacts,
            dataset_revision_sha256=bids_revision,
            source_checksum_manifest=str(source_manifest),
            checksum_manifest=str(bids_manifest),
            bids_validation_report=str(validation_path),
            bids_validation=validation,
        )
        if row.get("source_mode") == "formal_bids_mirror":
            upstream = [
                {
                    **artifact,
                    "source_url": (
                        "https://data.nemar.invalid/v1/"
                        + str(artifact["relative_path"])
                    ),
                    "upstream_checksum": {
                        "algorithm": "git",
                        "value": "c" * 40,
                    },
                }
                for artifact in bids_artifacts
            ]
            row.update(
                retained_source_bytes=sum(
                    item["size_bytes"] for item in source_artifacts
                ),
                source_download_bytes=sum(
                    item["size_bytes"] for item in bids_artifacts
                ),
                upstream_download_status="verified",
                upstream_download_bytes=sum(
                    item["size_bytes"] for item in bids_artifacts
                ),
                upstream_download_artifacts=upstream,
                upstream_download_revision_sha256=_canonical_sha256(upstream),
            )
    path.write_text(json.dumps(manifest), encoding="utf-8")
    inputs = _inputs(tmp_path, path)._replace(
        mne_data_root=source_owner,
        output_root=bids_owner,
        frozen_integrity_error=(
            lambda row, source, bids, checksums: frozen_dataset_integrity_error(
                row,
                source_owner=source,
                bids_owner=bids,
                checksum_owner=checksums,
            )
        ),
    )

    clean = evaluate_preflight(inputs)
    assert clean["campaign_allowed"] is True

    first_bids = Path(manifest["datasets"][0]["bids_root"])
    untracked = first_bids / "untracked.json"
    untracked.write_text("{}", encoding="utf-8")
    stale = evaluate_preflight(inputs)
    assert stale["campaign_allowed"] is False
    assert any("BIDS checksum inventory changed" in item for item in stale["blockers"])

    untracked.unlink()
    first_manifest = Path(manifest["datasets"][0]["checksum_manifest"])
    manifest_bytes = first_manifest.read_bytes()
    first_manifest.write_text("0" * 64 + "  dataset_description.json\n", "utf-8")
    tampered_manifest = evaluate_preflight(inputs)
    assert tampered_manifest["campaign_allowed"] is False
    assert any(
        "BIDS checksum manifest changed" in item
        for item in tampered_manifest["blockers"]
    )

    first_manifest.write_bytes(manifest_bytes)
    marker = first_bids / "dataset_description.json"
    marker.unlink()
    missing_marker = evaluate_preflight(inputs)
    assert missing_marker["campaign_allowed"] is False
    assert any(
        "formal BIDS dataset_description.json marker" in item
        for item in missing_marker["blockers"]
    )


def test_environment_identity_and_d_drive_are_fail_closed(tmp_path: Path) -> None:
    manifest_path = _write_manifest(tmp_path)
    inputs = _inputs(tmp_path, manifest_path)._replace(
        distribution_version=lambda name: {
            "moabb": "1.4.3",
        }[name],
        moabb_class_names=lambda: tuple(
            name for name in EXPECTED_CLASS_NAMES if name != "GuttmannFlury2025_SSVEP"
        ),
        moabb_has_generic_bids_conversion=lambda: False,
    )

    result = evaluate_preflight(inputs)

    assert result["campaign_allowed"] is False
    assert any("D-drive" in blocker for blocker in result["blockers"])
    assert any("MOABB 1.5.0" in blocker for blocker in result["blockers"])
    assert any("pyxdf" in blocker for blocker in result["blockers"])
    assert any("GuttmannFlury2025_SSVEP" in blocker for blocker in result["blockers"])
    assert any("convert_to_bids" in blocker for blocker in result["blockers"])


def test_insufficient_conservative_headroom_blocks_before_download(
    tmp_path: Path,
) -> None:
    manifest_path = _write_manifest(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["datasets"][0].update(
        status="pending",
        source_checksum_status="ABSENT",
        source_artifacts=[],
        bids_checksum_status="ABSENT",
        bids_artifacts=[],
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    inputs = _inputs(tmp_path, manifest_path)._replace(
        mne_data_root=Path("/mnt/d/xbrainlab/moabb/native"),
        output_root=Path("/mnt/d/xbrainlab/moabb/bids"),
        free_bytes=13_999_999,
    )

    result = evaluate_preflight(inputs)

    assert result["campaign_allowed"] is False
    assert result["materialization_phase"] == "partial"
    assert result["remaining_source_download_bytes"] == 1_000_000
    assert result["required_headroom_bytes"] == 14_000_000
    assert any("free space" in blocker for blocker in result["blockers"])


def test_complete_campaign_still_reserves_the_artifact_floor(tmp_path: Path) -> None:
    manifest_path = _write_manifest(tmp_path)
    inputs = _inputs(tmp_path, manifest_path)._replace(
        mne_data_root=Path("/mnt/d/xbrainlab/moabb/native"),
        output_root=Path("/mnt/d/xbrainlab/moabb/bids"),
        free_bytes=9_999_999,
    )

    result = evaluate_preflight(inputs)

    assert result["campaign_allowed"] is False
    assert result["materialization_phase"] == "complete"
    assert result["remaining_source_download_bytes"] == 0
    assert result["required_headroom_bytes"] == 10_000_000
    assert any("free space" in blocker for blocker in result["blockers"])


def test_exact_byte_drift_restores_future_download_headroom(
    tmp_path: Path,
) -> None:
    manifest_path = _write_manifest(tmp_path)
    first_class = EXPECTED_CLASS_NAMES[0]
    inputs = _inputs(tmp_path, manifest_path)._replace(
        mne_data_root=Path("/mnt/d/xbrainlab/moabb/native"),
        output_root=Path("/mnt/d/xbrainlab/moabb/bids"),
        free_bytes=13_999_999,
        frozen_integrity_error=(
            lambda row, _source, _bids, _checksums: (
                "BIDS checksum inventory changed"
                if row["moabb_class"] == first_class
                else None
            )
        ),
    )

    result = evaluate_preflight(inputs)

    assert result["campaign_allowed"] is False
    assert result["materialization_phase"] == "partial"
    assert result["remaining_source_download_bytes"] == 1_000_000
    assert result["required_headroom_bytes"] == 14_000_000
    assert any("final byte verification failed" in item for item in result["blockers"])
    assert any("free space" in item for item in result["blockers"])


def test_tracked_manifest_preserves_known_gates_and_mirror_identity() -> None:
    manifest = load_campaign_manifest()
    by_class = {item["moabb_class"]: item for item in manifest["datasets"]}

    assert tuple(by_class) == EXPECTED_CLASS_NAMES
    assert by_class["Nakanishi2015"]["license_status"] == "local-use-only"
    assert by_class["Nakanishi2015"]["redistribution_allowed"] is False
    assert "unknown" in by_class["Nakanishi2015"]["license_note"].casefold()
    mirror = by_class["Ma2020"]
    assert mirror["source_mode"] == "formal_bids_mirror"
    assert mirror["output_format"] == "BDF"
    assert mirror["resource_status"] == "FORMAL_BIDS_MIRROR_REQUIRED"
    assert mirror["formal_bids_mirror"]["native_format"] == "BDF"
    assert mirror["formal_bids_mirror"]["selected_projection"] == {
        "entry_count": 339,
        "total_bytes": 1_886_960_128,
        "projection_sha256": (
            "9464c4b457cc4f52504dbe68437e778e40782383b856fbb8419a5fd7583628c5"
        ),
    }
    assert {item["output_format"] for item in manifest["datasets"]} == {
        "EDF",
        "BrainVision",
        "EEGLAB",
        "BDF",
    }
    assert all(
        item["source_checksum_status"] != "verified" for item in manifest["datasets"]
    )
    assert all(not item.get("source_artifacts") for item in manifest["datasets"])


def test_current_poetry_environment_still_requires_complete_campaign_manifest() -> None:
    result = evaluate_preflight(
        PreflightInputs.from_environment(
            mne_data_root=Path("/mnt/d/xbrainlab/moabb/native"),
            output_root=Path("/mnt/d/xbrainlab/moabb/bids"),
            distribution_version=importlib.metadata.version,
        )
    )

    assert result["campaign_allowed"] is False
    assert any("checksum" in blocker for blocker in result["blockers"])
    assert any("Nakanishi2015" in blocker for blocker in result["blockers"])
    assert any("Ma2020" in blocker for blocker in result["blockers"])
    assert not any("pyproject.toml" in blocker for blocker in result["blockers"])
    assert not any("poetry.lock" in blocker for blocker in result["blockers"])
    assert not any("installed environment" in blocker for blocker in result["blockers"])


def test_poetry_contract_requires_direct_and_locked_conversion_dependencies(
    tmp_path: Path,
) -> None:
    pyproject_path = tmp_path / "pyproject.toml"
    lock_path = tmp_path / "poetry.lock"
    pyproject_path.write_text(
        """
[tool.poetry.dependencies]
python = ">=3.11,<3.13"
moabb = "1.5.0"
pyxdf = ">=1.16.4"
mne-bids = ">=0.17"
pybv = ">=0.7.3"
edfio = ">=0.4.2"
edflib-python = ">=1.0.6"
eeglabio = ">=0.1.0"
""",
        encoding="utf-8",
    )
    lock_path.write_text(
        """
[[package]]
name = "moabb"
version = "1.5.0"

[[package]]
name = "pyxdf"
version = "1.17.0"

[[package]]
name = "eeglabio"
version = "0.1.0"

[[package]]
name = "mne-bids"
version = "0.19.0"

[[package]]
name = "pybv"
version = "0.8.1"

[[package]]
name = "edfio"
version = "0.4.16"

[[package]]
name = "edflib-python"
version = "1.0.8"
""",
        encoding="utf-8",
    )

    assert poetry_dependency_blockers(pyproject_path, lock_path) == []

    pyproject_path.write_text(
        pyproject_path.read_text(encoding="utf-8").replace(
            'pyxdf = ">=1.16.4"', 'pyxdf = ">=1.16.3"'
        ),
        encoding="utf-8",
    )

    assert "pyproject.toml must declare pyxdf>=1.16.4" in poetry_dependency_blockers(
        pyproject_path, lock_path
    )
