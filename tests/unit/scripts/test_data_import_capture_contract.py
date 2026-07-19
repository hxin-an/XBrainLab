from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

import pytest
from PIL import Image

import scripts.dev.capture_data_import_wizard_steps as capture_script
from scripts.dev.app_polish_capture_contract import collect_source_identity
from scripts.dev.data_import_capture_contract import (
    MANIFEST_NAME,
    build_data_import_capture_manifest,
    load_data_import_capture_manifest,
    validate_data_import_capture_manifest,
    write_data_import_capture_manifest,
)


def _payload(tmp_path):
    filenames = ("01-choose-eeg-data.png", "05-review-and-import.png")
    for index, filename in enumerate(filenames):
        Image.new("RGB", (80 + index, 60), (35, 70, 105)).save(tmp_path / filename)
    identity = collect_source_identity()
    payload = build_data_import_capture_manifest(
        tmp_path,
        expected_surfaces=filenames,
        selected_surfaces=filenames,
        source_identity=identity,
        source_identity_at_start=identity,
        capture_started_at=datetime(2026, 7, 18, 4, 0, tzinfo=UTC),
        generated_at=datetime(2026, 7, 18, 4, 1, tzinfo=UTC),
        qt_platform="xcb",
        session_id="test-session",
    )
    return payload, identity, filenames


def test_data_import_manifest_binds_complete_capture_to_source_and_environment(
    tmp_path,
) -> None:
    payload, identity, filenames = _payload(tmp_path)

    ok, reason = validate_data_import_capture_manifest(
        payload,
        output_dir=tmp_path,
        expected_surfaces=filenames,
        now=datetime(2026, 7, 18, 4, 1, tzinfo=UTC),
        refresh_source_identity=False,
        current_source_identity=identity,
    )

    assert ok is True, reason
    assert payload["schema_version"] == 4
    assert payload["source_identity"]["branch"]
    assert payload["source_identity"]["commit_sha"]
    assert payload["source_identity"]["dirty_digest"]
    assert payload["capture_environment"]["qt_platform"] == "xcb"
    assert payload["capture_scope"]["complete"] is True
    assert payload["capture_session"]["session_id"] == "test-session"


def test_data_import_manifest_uses_content_freshness_and_rejects_tampered_completion(
    tmp_path,
) -> None:
    payload, identity, filenames = _payload(tmp_path)
    same_content = deepcopy(identity)
    same_content["branch"] = f"{identity['branch']}-different"
    same_content["commit_sha"] = "a" * 40
    same_content["head_tree_sha"] = "b" * 40
    same_content["dirty"] = not bool(identity["dirty"])
    same_content["dirty_digest"] = "c" * 64
    same_content["source_digest"] = "d" * 64

    ok, reason = validate_data_import_capture_manifest(
        payload,
        output_dir=tmp_path,
        expected_surfaces=filenames,
        now=datetime(2026, 7, 18, 4, 1, tzinfo=UTC),
        refresh_source_identity=False,
        current_source_identity=same_content,
    )
    assert ok is True, reason

    stale_content = deepcopy(identity)
    stale_content["source_content_digest"] = "0" * 64
    ok, reason = validate_data_import_capture_manifest(
        payload,
        output_dir=tmp_path,
        expected_surfaces=filenames,
        now=datetime(2026, 7, 18, 4, 1, tzinfo=UTC),
        refresh_source_identity=False,
        current_source_identity=stale_content,
    )
    assert ok is False
    assert "stale (source_content_digest)" in reason.lower()

    payload["capture_session"]["source_digest_at_completion"] = "0" * 64
    ok, reason = validate_data_import_capture_manifest(
        payload,
        output_dir=tmp_path,
        expected_surfaces=filenames,
        now=datetime(2026, 7, 18, 4, 1, tzinfo=UTC),
        refresh_source_identity=False,
        current_source_identity=identity,
    )
    assert ok is False
    assert "capture completion" in reason.lower()


def test_data_import_manifest_writer_publishes_manifest_atomically(tmp_path) -> None:
    payload, _identity, _filenames = _payload(tmp_path)

    destination = write_data_import_capture_manifest(tmp_path, payload)

    assert destination == tmp_path / MANIFEST_NAME
    assert not (tmp_path / f".{MANIFEST_NAME}.tmp").exists()
    assert load_data_import_capture_manifest(tmp_path) == payload


def test_data_import_manifest_rejects_source_mutation_during_capture(tmp_path) -> None:
    _payload_value, identity, filenames = _payload(tmp_path)
    changed_at_start = deepcopy(identity)
    changed_at_start["source_digest"] = "0" * 64

    with pytest.raises(RuntimeError, match="source changed"):
        build_data_import_capture_manifest(
            tmp_path,
            expected_surfaces=filenames,
            selected_surfaces=filenames,
            source_identity=identity,
            source_identity_at_start=changed_at_start,
            capture_started_at=datetime(2026, 7, 18, 4, 0, tzinfo=UTC),
            generated_at=datetime(2026, 7, 18, 4, 1, tzinfo=UTC),
            qt_platform="xcb",
            session_id="changed-source",
        )


def test_data_import_publication_replaces_manifest_after_every_png(
    monkeypatch,
    tmp_path,
) -> None:
    staging_dir = tmp_path / "staging"
    output_dir = tmp_path / "canonical"
    staging_dir.mkdir()
    filenames = ["01-choose-eeg-data.png", "05-review-and-import.png"]
    for filename in filenames:
        Image.new("RGB", (20, 12), (40, 80, 120)).save(staging_dir / filename)
    (staging_dir / MANIFEST_NAME).write_text("{}\n", encoding="utf-8")
    replaced: list[str] = []
    original_replace = type(staging_dir).replace

    def tracking_replace(source, target):
        if source.name == MANIFEST_NAME:
            assert all((output_dir / filename).is_file() for filename in filenames)
        replaced.append(source.name)
        return original_replace(source, target)

    monkeypatch.setattr(type(staging_dir), "replace", tracking_replace)

    capture_script._publish_capture(
        staging_dir,
        output_dir,
        selected_surfaces=filenames,
    )

    assert replaced == [*filenames, MANIFEST_NAME]
    assert (output_dir / MANIFEST_NAME).is_file()


def test_validate_only_returns_nonzero_for_stale_source_evidence(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        capture_script,
        "load_data_import_capture_manifest",
        lambda _output_dir: {"schema_version": 4},
    )
    monkeypatch.setattr(
        capture_script,
        "validate_data_import_capture_manifest",
        lambda *_args, **_kwargs: (
            False,
            "Data Import capture source identity is stale (branch).",
        ),
    )

    result = capture_script.main(["--output-dir", str(tmp_path), "--validate-only"])

    assert result == 1
