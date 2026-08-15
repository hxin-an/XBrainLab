from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

import scripts.dev.consolidate_dataset_storage as consolidation
from scripts.dev.consolidate_dataset_storage import (
    build_migration_plan,
    copy_verified_active_source_cache,
    copy_verified_formal_bids_dataset,
    copy_verified_public_fixture_profile,
    finalize_verified_cleanup_receipt,
    main,
)
from scripts.dev.fetch_public_eeg_fixtures import FixtureFile, FixtureGroup


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def test_plan_keeps_frozen_sources_and_excludes_build_quarantine(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    data_root = tmp_path / "central"
    dataset_container = repo_root / "build/moabb-gui-campaign-v2/data/PhysionetMI"
    dataset = dataset_container / "MNE-BIDS-physionet-motor-imagery"
    checksum_dir = repo_root / "build/moabb-gui-campaign-v2/checksums"
    dataset.mkdir(parents=True)
    checksum_dir.mkdir(parents=True)
    payload = b"formal-bids"
    (dataset / "dataset_description.json").write_bytes(payload)
    (checksum_dir / "PhysionetMI.sha256").write_text(
        f"{_sha256(payload)}  dataset_description.json\n",
        encoding="utf-8",
    )
    (checksum_dir / "PhysionetMI.freeze.json").write_text(
        '{"bids_root":"/old/repo/PhysionetMI/MNE-BIDS-physionet-motor-imagery"}\n',
        encoding="utf-8",
    )
    (repo_root / "build/moabb-gui-campaign-v2/data/.quarantine").mkdir()

    plan = build_migration_plan(repo_root=repo_root, data_root=data_root)

    entry = next(
        item for item in plan["entries"] if item["dataset_id"] == "PhysionetMI"
    )
    assert entry["role"] == "formal-bids"
    assert entry["copy_status"] == "manifest_present_unverified"
    assert entry["root_error"] == ""
    assert entry["source_path"] == str(dataset)
    assert entry["target_path"] == str(data_root / "datasets/bids/moabb-15/PhysionetMI")
    assert entry["old_source_retained"] is True
    assert entry["deletion_authorized"] is False
    assert not any(".quarantine" in item["target_path"] for item in plan["entries"])


def test_plan_includes_one_active_source_cache_and_excludes_quarantine(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    data_root = tmp_path / "central"
    active_source = repo_root / "build/moabb-gui-campaign-v2/mne-data"
    (active_source / "PhysionetMI").mkdir(parents=True)
    (active_source / "PhysionetMI/raw.edf").write_bytes(b"active")
    (active_source / ".quarantine/orphan").mkdir(parents=True)
    (active_source / ".quarantine/orphan/raw.edf").write_bytes(b"discard")

    plan = build_migration_plan(repo_root=repo_root, data_root=data_root)

    entry = next(
        item for item in plan["entries"] if item["dataset_id"] == "moabb-15-source"
    )
    assert entry["role"] == "source-cache"
    assert entry["authority"] == "accepted-active-source"
    assert entry["expected_file_count"] == 1
    assert entry["expected_bytes"] == len(b"active")
    assert entry["target_path"] == str(data_root / "datasets/source/moabb-15")
    assert entry["excluded_top_level"] == [".quarantine", ".staging"]


def test_active_source_copy_is_exact_and_excludes_quarantine(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "central" / "source" / "moabb-15"
    (source / "PhysionetMI").mkdir(parents=True)
    (source / "PhysionetMI/raw.edf").write_bytes(b"active-source")
    (source / ".quarantine/orphan").mkdir(parents=True)
    (source / ".quarantine/orphan/raw.edf").write_bytes(b"discard")

    result = copy_verified_active_source_cache(source=source, target=target)

    assert result == {
        "status": "copied_and_verified",
        "file_count": 1,
        "size_bytes": len(b"active-source"),
    }
    assert (target / "PhysionetMI/raw.edf").read_bytes() == b"active-source"
    assert not (target / ".quarantine").exists()
    assert (target / ".xbrainlab-source.sha256").is_file()


def test_active_source_existing_target_rejects_unmanaged_file(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    target = tmp_path / "central" / "source" / "moabb-15"
    (source / "PhysionetMI").mkdir(parents=True)
    (source / "PhysionetMI/raw.edf").write_bytes(b"active-source")
    copy_verified_active_source_cache(source=source, target=target)
    (target / "unmanaged.bin").write_bytes(b"unexpected")

    with pytest.raises(ValueError, match="inventory mismatch"):
        copy_verified_active_source_cache(source=source, target=target)


def test_finalize_cleanup_requires_verified_targets_and_absent_sources(
    tmp_path: Path,
) -> None:
    source = tmp_path / "old-source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    plan = {
        "copy_state": "complete",
        "entries": [
            {
                "dataset_id": "Demo",
                "source_path": str(source),
                "target_path": str(target),
                "copy_status": "copied_and_verified",
                "cutover_status": "copied_not_cut_over",
                "old_source_retained": True,
                "deletion_authorized": False,
            }
        ],
    }

    with pytest.raises(ValueError, match="still exists"):
        finalize_verified_cleanup_receipt(plan)


def test_finalize_cleanup_records_completed_source_removal(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    plan = {
        "copy_state": "complete",
        "entries": [
            {
                "dataset_id": "Demo",
                "source_path": str(tmp_path / "removed-source"),
                "target_path": str(target),
                "copy_status": "copied_and_verified",
                "cutover_status": "copied_not_cut_over",
                "old_source_retained": True,
                "deletion_authorized": False,
            }
        ],
    }

    finalized = finalize_verified_cleanup_receipt(plan)

    assert finalized["cleanup_state"] == "complete"
    assert finalized["entries"][0]["cutover_status"] == "cut_over"
    assert finalized["entries"][0]["old_source_retained"] is False
    assert finalized["entries"][0]["deletion_authorized"] is True


def test_verified_copy_is_atomic_and_never_deletes_the_source(tmp_path: Path) -> None:
    source = tmp_path / "source" / "PhysionetMI"
    target = tmp_path / "target" / "PhysionetMI"
    checksum_manifest = tmp_path / "PhysionetMI.sha256"
    source.mkdir(parents=True)
    payload = b"formal-bids"
    (source / "dataset_description.json").write_bytes(payload)
    checksum_manifest.write_text(
        f"{_sha256(payload)}  dataset_description.json\n",
        encoding="utf-8",
    )

    result = copy_verified_formal_bids_dataset(
        source=source,
        target=target,
        checksum_manifest=checksum_manifest,
    )

    assert result["status"] == "copied_and_verified"
    assert (source / "dataset_description.json").read_bytes() == payload
    assert (target / "dataset_description.json").read_bytes() == payload
    assert not target.with_name("PhysionetMI.copying").exists()


def test_verified_copy_rejects_a_corrupt_source_without_creating_target(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source" / "PhysionetMI"
    target = tmp_path / "target" / "PhysionetMI"
    checksum_manifest = tmp_path / "PhysionetMI.sha256"
    source.mkdir(parents=True)
    (source / "dataset_description.json").write_bytes(b"corrupt")
    checksum_manifest.write_text(
        f"{'0' * 64}  dataset_description.json\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="checksum mismatch"):
        copy_verified_formal_bids_dataset(
            source=source,
            target=target,
            checksum_manifest=checksum_manifest,
        )

    assert not target.exists()
    assert not target.with_name("PhysionetMI.copying").exists()


def test_public_fixture_copy_uses_only_pinned_manifest_files(tmp_path: Path) -> None:
    source = tmp_path / "public-source"
    target = tmp_path / "public-target"
    source.mkdir()
    payload = b"pinned-fixture"
    (source / "fixture.edf").write_bytes(payload)
    (source / "unverified-orphan.eeg").write_bytes(b"do-not-copy")
    fixture_file: FixtureFile = {
        "filename": "fixture.edf",
        "url": "https://example.invalid/fixture.edf",
        "sha256": _sha256(payload),
        "size_bytes": len(payload),
    }
    groups: list[FixtureGroup] = [
        {
            "name": "test",
            "description": "test fixture",
            "source": "unit test",
            "entrypoint": "fixture.edf",
            "files": [fixture_file],
        }
    ]

    result = copy_verified_public_fixture_profile(
        source=source,
        target=target,
        groups=groups,
    )

    assert result == {
        "status": "copied_and_verified",
        "file_count": 1,
        "size_bytes": len(payload),
    }
    assert (target / "fixture.edf").read_bytes() == payload
    assert not (target / "unverified-orphan.eeg").exists()
    assert (source / "unverified-orphan.eeg").exists()


def test_existing_public_target_with_orphan_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    payload = b"pinned"
    fixture_file: FixtureFile = {
        "filename": "fixture.edf",
        "url": "https://example.invalid/fixture.edf",
        "sha256": _sha256(payload),
        "size_bytes": len(payload),
    }
    groups: list[FixtureGroup] = [
        {
            "name": "test",
            "description": "test fixture",
            "source": "unit test",
            "entrypoint": "fixture.edf",
            "files": [fixture_file],
        }
    ]
    (source / "fixture.edf").write_bytes(payload)
    (target / "fixture.edf").write_bytes(payload)
    (target / "orphan.eeg").write_bytes(b"unverified")

    with pytest.raises(ValueError, match="unmanaged files"):
        copy_verified_public_fixture_profile(
            source=source,
            target=target,
            groups=groups,
        )


def test_formal_copy_rejects_target_parent_symlink_alias(tmp_path: Path) -> None:
    source = tmp_path / "source" / "PhysionetMI"
    source.mkdir(parents=True)
    payload = b"formal-bids"
    (source / "dataset_description.json").write_bytes(payload)
    checksum_manifest = tmp_path / "PhysionetMI.sha256"
    checksum_manifest.write_text(
        f"{_sha256(payload)}  dataset_description.json\n",
        encoding="utf-8",
    )
    alias_parent = tmp_path / "alias"
    alias_parent.symlink_to(source.parent, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        copy_verified_formal_bids_dataset(
            source=source,
            target=alias_parent / "copy",
            checksum_manifest=checksum_manifest,
        )

    assert not (source.parent / "copy").exists()


def test_formal_copy_rejects_nested_source_symlink(tmp_path: Path) -> None:
    source = tmp_path / "source" / "PhysionetMI"
    outside = tmp_path / "outside"
    target = tmp_path / "target" / "PhysionetMI"
    source.mkdir(parents=True)
    outside.mkdir()
    (outside / "payload.edf").write_bytes(b"outside")
    (source / "linked").symlink_to(outside, target_is_directory=True)
    checksum_manifest = tmp_path / "PhysionetMI.sha256"
    checksum_manifest.write_text(
        f"{_sha256(b'outside')}  linked/payload.edf\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="symlink"):
        copy_verified_formal_bids_dataset(
            source=source,
            target=target,
            checksum_manifest=checksum_manifest,
        )

    assert not target.exists()


def test_public_fixture_copy_rejects_manifest_path_escape(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    payload = b"outside"
    (tmp_path / "outside.edf").write_bytes(payload)
    fixture_file: FixtureFile = {
        "filename": "../outside.edf",
        "url": "https://example.invalid/outside.edf",
        "sha256": _sha256(payload),
        "size_bytes": len(payload),
    }
    groups: list[FixtureGroup] = [
        {
            "name": "test",
            "description": "test fixture",
            "source": "unit test",
            "entrypoint": "../outside.edf",
            "files": [fixture_file],
        }
    ]

    with pytest.raises(ValueError, match="Unsafe manifest path"):
        copy_verified_public_fixture_profile(
            source=source,
            target=target,
            groups=groups,
        )

    assert not target.exists()


def test_failed_copy_cleans_only_its_unique_staging_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source" / "PhysionetMI"
    target = tmp_path / "target" / "PhysionetMI"
    source.mkdir(parents=True)
    payload = b"formal-bids"
    (source / "dataset_description.json").write_bytes(payload)
    checksum_manifest = tmp_path / "PhysionetMI.sha256"
    checksum_manifest.write_text(
        f"{_sha256(payload)}  dataset_description.json\n",
        encoding="utf-8",
    )

    foreign_staging = target.parent / ".PhysionetMI.copying-foreign"
    foreign_staging.mkdir(parents=True)
    (foreign_staging / "owner.txt").write_text("foreign", encoding="utf-8")

    def fail_copy(**_kwargs: object) -> None:
        raise OSError("copy interrupted")

    monkeypatch.setattr(consolidation, "_copy_manifest_file_no_follow", fail_copy)

    with pytest.raises(OSError, match="copy interrupted"):
        copy_verified_formal_bids_dataset(
            source=source,
            target=target,
            checksum_manifest=checksum_manifest,
        )

    assert not target.exists()
    assert list(target.parent.glob(".PhysionetMI.copying-*")) == [foreign_staging]
    assert not target.with_name(".PhysionetMI.migration.lock").exists()
    assert (foreign_staging / "owner.txt").read_text(encoding="utf-8") == "foreign"
    assert (source / "dataset_description.json").read_bytes() == payload


def test_copy_rejects_lock_contention_without_removing_foreign_lock(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source" / "PhysionetMI"
    target = tmp_path / "target" / "PhysionetMI"
    source.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    payload = b"formal-bids"
    (source / "dataset_description.json").write_bytes(payload)
    checksum_manifest = tmp_path / "PhysionetMI.sha256"
    checksum_manifest.write_text(
        f"{_sha256(payload)}  dataset_description.json\n",
        encoding="utf-8",
    )
    lock = target.with_name(".PhysionetMI.migration.lock")
    lock.write_text("foreign-owner\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Another migration owns"):
        copy_verified_formal_bids_dataset(
            source=source,
            target=target,
            checksum_manifest=checksum_manifest,
        )

    assert lock.read_text(encoding="utf-8") == "foreign-owner\n"
    assert not target.exists()


def test_formal_copy_rejects_source_changed_to_symlink_after_precheck(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source" / "PhysionetMI"
    outside = tmp_path / "outside.edf"
    target = tmp_path / "target" / "PhysionetMI"
    source.mkdir(parents=True)
    payload = b"formal-bids"
    source_file = source / "dataset_description.json"
    source_file.write_bytes(payload)
    outside.write_bytes(payload)
    checksum_manifest = tmp_path / "PhysionetMI.sha256"
    checksum_manifest.write_text(
        f"{_sha256(payload)}  dataset_description.json\n",
        encoding="utf-8",
    )
    real_verify = consolidation.verify_formal_bids_dataset
    calls = 0

    def verify_then_swap(**kwargs: object) -> dict[str, int]:
        nonlocal calls
        result = real_verify(**kwargs)
        calls += 1
        if calls == 1:
            source_file.unlink()
            source_file.symlink_to(outside)
        return result

    monkeypatch.setattr(consolidation, "verify_formal_bids_dataset", verify_then_swap)

    with pytest.raises(ValueError, match="changed or became unsafe"):
        copy_verified_formal_bids_dataset(
            source=source,
            target=target,
            checksum_manifest=checksum_manifest,
        )

    assert not target.exists()


def test_formal_copy_never_clobbers_target_that_appears_before_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source" / "PhysionetMI"
    target = tmp_path / "target" / "PhysionetMI"
    source.mkdir(parents=True)
    payload = b"formal-bids"
    (source / "dataset_description.json").write_bytes(payload)
    checksum_manifest = tmp_path / "PhysionetMI.sha256"
    checksum_manifest.write_text(
        f"{_sha256(payload)}  dataset_description.json\n",
        encoding="utf-8",
    )
    real_verify = consolidation.verify_formal_bids_dataset
    calls = 0

    def verify_then_create_target(**kwargs: object) -> dict[str, int]:
        nonlocal calls
        result = real_verify(**kwargs)
        calls += 1
        if calls == 2:
            target.mkdir()
            (target / "foreign.txt").write_text("foreign", encoding="utf-8")
        return result

    monkeypatch.setattr(
        consolidation,
        "verify_formal_bids_dataset",
        verify_then_create_target,
    )

    with pytest.raises(ValueError, match="appeared before publish"):
        copy_verified_formal_bids_dataset(
            source=source,
            target=target,
            checksum_manifest=checksum_manifest,
        )

    assert (target / "foreign.txt").read_text(encoding="utf-8") == "foreign"
    assert not target.with_name(".PhysionetMI.migration.lock").exists()
    assert list(target.parent.glob(".PhysionetMI.copying-*")) == []


def test_plan_blocks_ambiguous_formal_bids_container(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    data_root = tmp_path / "central"
    container = repo_root / "build/moabb-gui-campaign-v2/data/Ambiguous"
    checksum_dir = repo_root / "build/moabb-gui-campaign-v2/checksums"
    for child in ("first", "second"):
        dataset = container / child
        dataset.mkdir(parents=True)
        (dataset / "dataset_description.json").write_text("{}", encoding="utf-8")
    checksum_dir.mkdir(parents=True)
    (checksum_dir / "Ambiguous.sha256").write_text(
        f"{_sha256(b'{}')}  dataset_description.json\n",
        encoding="utf-8",
    )

    plan = build_migration_plan(repo_root=repo_root, data_root=data_root)

    entry = next(item for item in plan["entries"] if item["dataset_id"] == "Ambiguous")
    assert entry["copy_status"] == "blocked_invalid_bids_root"
    assert "exactly one dataset root" in entry["root_error"]


def test_cli_writes_copy_only_plan_without_mutating_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo_root = tmp_path / "repo"
    data_root = tmp_path / "central"
    plan_path = tmp_path / "plans" / "migration.json"
    repo_root.mkdir()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "consolidate_dataset_storage.py",
            "--repo-root",
            str(repo_root),
            "--data-root",
            str(data_root),
            "--write-plan",
            str(plan_path),
        ],
    )

    assert main() == 0

    written = json.loads(plan_path.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert written == printed
    assert written["canonical_root"] == str(data_root / "datasets")
    assert written["rollback"]["policy"].startswith("copy-only")
    assert written["copy_results"] == {}
    assert written["copy_state"] == "not_started"


def test_cli_records_verified_copy_without_authorizing_cutover_or_deletion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo_root = tmp_path / "repo"
    data_root = tmp_path / "central"
    dataset = repo_root / "build/moabb-gui-campaign-v2/data/Demo"
    checksum_dir = repo_root / "build/moabb-gui-campaign-v2/checksums"
    plan_path = tmp_path / "plans" / "migration.json"
    dataset.mkdir(parents=True)
    checksum_dir.mkdir(parents=True)
    payload = b"formal-bids"
    (dataset / "dataset_description.json").write_bytes(payload)
    (checksum_dir / "Demo.sha256").write_text(
        f"{_sha256(payload)}  dataset_description.json\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "consolidate_dataset_storage.py",
            "--repo-root",
            str(repo_root),
            "--data-root",
            str(data_root),
            "--copy-formal-bids",
            "Demo",
            "--write-plan",
            str(plan_path),
        ],
    )

    assert main() == 0

    written = json.loads(plan_path.read_text(encoding="utf-8"))
    capsys.readouterr()
    entry = next(item for item in written["entries"] if item["dataset_id"] == "Demo")
    assert written["copy_results"]["Demo"]["status"] == "copied_and_verified"
    assert written["copy_state"] == "complete"
    assert entry["copy_status"] == "copied_and_verified"
    assert entry["cutover_status"] == "copied_not_cut_over"
    assert entry["old_source_retained"] is True
    assert entry["deletion_authorized"] is False
    assert (
        data_root / "datasets/bids/moabb-15/Demo/dataset_description.json"
    ).read_bytes() == payload


def test_cli_checkpoints_success_before_a_later_copy_action_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    data_root = tmp_path / "central"
    checksum_dir = repo_root / "build/moabb-gui-campaign-v2/checksums"
    plan_path = tmp_path / "plan.json"
    checksum_dir.mkdir(parents=True)
    for dataset_id, payload, digest in (
        ("First", b"valid", _sha256(b"valid")),
        ("Second", b"corrupt", "0" * 64),
    ):
        dataset = repo_root / f"build/moabb-gui-campaign-v2/data/{dataset_id}"
        dataset.mkdir(parents=True)
        (dataset / "dataset_description.json").write_bytes(payload)
        (checksum_dir / f"{dataset_id}.sha256").write_text(
            f"{digest}  dataset_description.json\n",
            encoding="utf-8",
        )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "consolidate_dataset_storage.py",
            "--repo-root",
            str(repo_root),
            "--data-root",
            str(data_root),
            "--copy-formal-bids",
            "First",
            "--copy-formal-bids",
            "Second",
            "--write-plan",
            str(plan_path),
        ],
    )

    with pytest.raises(ValueError, match="checksum mismatch"):
        main()

    written = json.loads(plan_path.read_text(encoding="utf-8"))
    first_entry = next(
        item for item in written["entries"] if item["dataset_id"] == "First"
    )
    assert written["copy_state"] == "failed"
    assert written["copy_results"]["First"]["status"] == "copied_and_verified"
    assert first_entry["copy_status"] == "copied_and_verified"
    assert first_entry["cutover_status"] == "copied_not_cut_over"
    assert (
        data_root / "datasets/bids/moabb-15/First/dataset_description.json"
    ).read_bytes() == b"valid"
    assert not (data_root / "datasets/bids/moabb-15/Second").exists()


def test_cli_persists_failed_receipt_when_verified_copy_cannot_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    data_root = tmp_path / "central"
    dataset = repo_root / "build/moabb-gui-campaign-v2/data/Demo"
    checksum_dir = repo_root / "build/moabb-gui-campaign-v2/checksums"
    plan_path = tmp_path / "plans" / "migration.json"
    dataset.mkdir(parents=True)
    checksum_dir.mkdir(parents=True)
    (dataset / "dataset_description.json").write_bytes(b"corrupt")
    (checksum_dir / "Demo.sha256").write_text(
        f"{'0' * 64}  dataset_description.json\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "consolidate_dataset_storage.py",
            "--repo-root",
            str(repo_root),
            "--data-root",
            str(data_root),
            "--copy-formal-bids",
            "Demo",
            "--write-plan",
            str(plan_path),
        ],
    )

    with pytest.raises(ValueError, match="checksum mismatch"):
        main()

    written = json.loads(plan_path.read_text(encoding="utf-8"))
    assert written["copy_state"] == "failed"
    assert written["copy_error"]["type"] == "ValueError"
    assert "checksum mismatch" in written["copy_error"]["message"]
    assert not (data_root / "datasets/bids/moabb-15/Demo").exists()
