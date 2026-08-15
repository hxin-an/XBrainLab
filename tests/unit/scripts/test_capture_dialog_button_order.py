from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import pytest
from PIL import Image

from scripts.dev import capture_dialog_button_order as capture_script


def _identity(*, source_digest: str = "e" * 64) -> dict[str, object]:
    return {
        "version": 3,
        "repo_root": str(capture_script.ROOT),
        "branch": "test-branch",
        "commit_sha": "a" * 40,
        "head_tree_sha": "b" * 40,
        "dirty": True,
        "dirty_digest": "c" * 64,
        "source_content_digest": "d" * 64,
        "source_digest": source_digest,
        "untracked_source_count": 1,
        "excluded_generated_prefixes": ["build/"],
        "excluded_local_paths": ["settings.json"],
        "included_file_policy": "all-non-generated-tracked-and-untracked-files",
        "error": "",
    }


def _successful_capture(variant: str) -> tuple[Image.Image, list[dict[str, object]]]:
    observations = []
    for title, _factory in capture_script._dialog_factories():
        observations.append(
            {
                "dialog": title,
                "variant": variant,
                "layout_direction": "LeftToRight",
                "order": "cancel-primary",
            }
        )
    return Image.new("RGB", (16, 12), "white"), observations


def test_dialog_order_capture_records_complete_fail_closed_evidence(
    qapp,
    tmp_path,
    monkeypatch,
) -> None:
    identity = _identity()
    captured_variants: list[str] = []

    def capture(_app, *, variant: str):
        captured_variants.append(variant)
        return _successful_capture(variant)

    monkeypatch.setattr(capture_script, "_capture_variant", capture)
    monkeypatch.setattr(
        capture_script,
        "collect_source_identity",
        lambda *_args, **_kwargs: deepcopy(identity),
    )

    assert capture_script.main(["--output-dir", str(tmp_path)]) == 0

    payload = json.loads(
        (tmp_path / capture_script.EVIDENCE_FILENAME).read_text(encoding="utf-8")
    )
    titles = {title for title, _factory in capture_script._dialog_factories()}
    assert captured_variants == ["standard", "narrow"]
    assert {(row["dialog"], row["variant"]) for row in payload["observations"]} == {
        (title, variant) for title in titles for variant in captured_variants
    }
    assert payload["passed"] is True
    assert payload["failures"] == []
    assert payload["capture_environment"] == {
        "qt_platform": qapp.platformName(),
        "qt_style": "Fusion",
    }
    assert payload["source_capture"] == {
        "branch_at_start": "test-branch",
        "branch_at_end": "test-branch",
        "commit_sha_at_start": "a" * 40,
        "commit_sha_at_end": "a" * 40,
        "head_tree_sha_at_start": "b" * 40,
        "head_tree_sha_at_end": "b" * 40,
        "dirty_at_start": True,
        "dirty_at_end": True,
        "dirty_digest_at_start": "c" * 64,
        "dirty_digest_at_end": "c" * 64,
        "source_content_digest_at_start": "d" * 64,
        "source_content_digest_at_end": "d" * 64,
        "source_digest_at_start": "e" * 64,
        "source_digest_at_end": "e" * 64,
        "untracked_source_count_at_start": 1,
        "untracked_source_count_at_end": 1,
    }
    assert set(payload["screenshots"]) == {"standard", "narrow"}
    for screenshot in payload["screenshots"].values():
        path = tmp_path / screenshot["path"]
        assert screenshot["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert screenshot["readable"] is True


def test_dialog_order_capture_rejects_order_failure(
    qapp,
    tmp_path,
    monkeypatch,
) -> None:
    identity = _identity()
    monkeypatch.setattr(
        capture_script,
        "collect_source_identity",
        lambda *_args, **_kwargs: deepcopy(identity),
    )

    def capture(_app, *, variant: str):
        image, observations = _successful_capture(variant)
        observations[0]["order"] = "primary-cancel"
        return image, observations

    monkeypatch.setattr(capture_script, "_capture_variant", capture)

    with pytest.raises(RuntimeError, match="Dialog order evidence failed"):
        capture_script.main(["--output-dir", str(tmp_path)])

    payload = json.loads(
        (tmp_path / capture_script.EVIDENCE_FILENAME).read_text(encoding="utf-8")
    )
    assert payload["passed"] is False
    assert payload["failures"]


def test_dialog_order_capture_rejects_source_identity_drift(
    qapp,
    tmp_path,
    monkeypatch,
) -> None:
    evidence_path = tmp_path / capture_script.EVIDENCE_FILENAME
    evidence_path.write_text('{"passed": true}\n', encoding="utf-8")
    identities = [_identity(), _identity(source_digest="f" * 64)]
    monkeypatch.setattr(
        capture_script,
        "collect_source_identity",
        lambda *_args, **_kwargs: identities.pop(0),
    )
    monkeypatch.setattr(
        capture_script,
        "_capture_variant",
        lambda _app, *, variant: _successful_capture(variant),
    )

    with pytest.raises(RuntimeError, match="source changed during dialog capture"):
        capture_script.main(["--output-dir", str(tmp_path)])

    assert not evidence_path.exists()
