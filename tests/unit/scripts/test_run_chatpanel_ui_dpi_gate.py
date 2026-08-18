from __future__ import annotations

import copy
import hashlib
import inspect
import subprocess
from pathlib import Path

from PIL import Image

import scripts.dev.run_chatpanel_ui_dpi_gate as dpi_gate
from scripts.dev.chatpanel_guided_boundary import artifact_integrity
from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    source_identity_digest,
)
from scripts.dev.run_chatpanel_ui_dpi_gate import (
    DPI_CONTENT_SCREENSHOTS,
    FULL_WINDOW_DOCK_SCREENSHOTS,
    NARROW_CROP_SCREENSHOTS,
    REQUIRED_QT_SCALE_FACTORS,
    SELECTED_SCREENSHOTS,
    validate_cross_scale_records,
    validate_dpi_manifest,
    validate_scale_payload,
)


def _payload(*, configured: str = "1.25", observed: float = 1.25) -> dict:
    def physical(logical: list[int]) -> list[int]:
        return [int(value * observed + 0.5) for value in logical]

    content_screens = []
    for index, (width, filename) in enumerate(
        zip((320, 420, 760), DPI_CONTENT_SCREENSHOTS, strict=True)
    ):
        logical_size = [width, 720]
        content_screens.append(
            {
                "name": f"dpi_{width}_message_error_confirmation",
                "file": filename,
                "logical_size": logical_size,
                "pixel_size": physical(logical_size),
                "capture_method": "widget_grab",
                "capture_device_pixel_ratio": observed,
                "image_sha256": f"{index + 1:064x}",
                "message_kinds": ["user", "error"],
                "visible_messages": [
                    {"sender": "You", "text": "Review this setting."},
                    {"sender": "XBrainLab", "text": "A warning needs review."},
                ],
                "confirmation": {
                    "visible": True,
                    "title": "Start training",
                    "values": "",
                    "impact": "Starts a potentially long GPU or CPU job.",
                },
                "render_content": {
                    "regions": {
                        "message_content": {"passed": True},
                        "warning_or_error": {"passed": True},
                        "confirmation_card": {"passed": True},
                    }
                },
                "checks": {"visible_text_fits": True},
                "failures": [],
            }
        )
    return {
        "status": "passed",
        "configured_qt_scale_factor": configured,
        "observed_screen_device_pixel_ratio": observed,
        "source_fingerprint": "current-source",
        "capture_source": {"stable": True},
        "first_paint_320_contract": {
            "real_dock": {
                "file": "first-paint-320-real-dock.png",
                "surface": "real_dock",
                "real_main_window": True,
                "real_qdockwidget": True,
                "dock_visible": True,
                "dock_floating": False,
                "pixel_size": [1024, 760],
                "passed": True,
            }
        },
        "screens": [
            {
                "name": "main_window_dock_420_response_visible",
                "file": "main-window-dock-420-response-visible.png",
                "logical_size": [1180, 760],
                "pixel_size": physical([1180, 760]),
                "checks": {
                    "real_main_window_visible": True,
                    "real_qdockwidget_visible": True,
                    "dock_is_not_floating": True,
                    "render_content_ready": True,
                },
                "failures": [],
            },
            {
                "name": "responsive_320_idle",
                "file": "responsive-320-idle.png",
                "logical_size": [320, 720],
                "pixel_size": physical([320, 720]),
                "checks": {"visible_text_fits": True},
                "failures": [],
            },
            {
                "name": "narrow_message_content_boundaries",
                "file": "narrow-message-content-boundaries.png",
                "logical_size": [320, 760],
                "pixel_size": physical([320, 760]),
                "checks": {"visible_text_fits": True},
                "failures": [],
            },
            {
                "name": "narrow_setting_change_confirmation_max_content",
                "file": "narrow-setting-change-confirmation-max-content.png",
                "logical_size": [320, 780],
                "pixel_size": physical([320, 780]),
                "checks": {"visible_text_fits": True},
                "failures": [],
            },
            *content_screens,
        ],
        "failures": [],
    }


def _source_identity() -> dict:
    identity = {
        "version": 3,
        "repo_root": str(dpi_gate.ROOT.resolve()),
        "branch": "test",
        "commit_sha": "a" * 40,
        "head_tree_sha": "b" * 40,
        "dirty": True,
        "dirty_digest": "c" * 64,
        "source_content_digest": "d" * 64,
        "untracked_source_count": 0,
        "excluded_generated_prefixes": ["artifacts/", "build/"],
        "excluded_local_paths": ["settings.json"],
        "included_file_policy": "test-source-policy",
        "error": "",
    }
    identity["source_digest"] = source_identity_digest(identity)
    return identity


def test_default_dpi_evidence_uses_dev_artifact_namespace() -> None:
    assert (
        dpi_gate.ROOT / "build" / "dev-artifacts" / "chatpanel-dpi"
    ) == dpi_gate.DEFAULT_OUTPUT_DIR


def test_dpi_gate_covers_required_full_window_and_narrow_evidence() -> None:
    assert REQUIRED_QT_SCALE_FACTORS == (1.0, 1.25, 1.5)
    assert FULL_WINDOW_DOCK_SCREENSHOTS == (
        "first-paint-320-real-dock.png",
        "main-window-dock-420-response-visible.png",
    )
    assert NARROW_CROP_SCREENSHOTS == (
        "responsive-320-idle.png",
        "narrow-message-content-boundaries.png",
        "narrow-setting-change-confirmation-max-content.png",
    )
    assert (
        *FULL_WINDOW_DOCK_SCREENSHOTS,
        *NARROW_CROP_SCREENSHOTS,
        *DPI_CONTENT_SCREENSHOTS,
    ) == SELECTED_SCREENSHOTS


def test_scale_payload_requires_matching_configured_and_observed_scale() -> None:
    assert validate_scale_payload(_payload(), expected_scale=1.25) == []

    failures = validate_scale_payload(
        _payload(configured="1.0", observed=1.0),
        expected_scale=1.25,
    )

    assert "configured QT scale factor does not match 1.25" in failures
    assert "observed Qt device pixel ratio does not match 1.25" in failures


def test_scale_payload_requires_full_window_dock_and_narrow_records() -> None:
    payload = _payload()
    payload["screens"] = payload["screens"][:1]
    payload["first_paint_320_contract"] = {}

    failures = validate_scale_payload(payload, expected_scale=1.25)

    assert "full-window dock evidence is missing: first-paint-320-real-dock.png" in (
        failures
    )
    assert "narrow crop evidence is missing: responsive-320-idle.png" in failures
    assert (
        "narrow crop evidence is missing: narrow-message-content-boundaries.png"
        in failures
    )
    assert (
        "narrow crop evidence is missing: "
        "narrow-setting-change-confirmation-max-content.png"
    ) in failures


def test_scale_payload_rejects_capture_size_that_ignores_observed_dpr() -> None:
    payload = _payload(observed=1.25)
    screen = next(
        item
        for item in payload["screens"]
        if item["file"] == DPI_CONTENT_SCREENSHOTS[0]
    )
    screen["pixel_size"] = screen["logical_size"]
    screen["capture_device_pixel_ratio"] = 1.0

    failures = validate_scale_payload(payload, expected_scale=1.25)

    assert any("physical capture size" in failure for failure in failures)
    assert any("capture DPR" in failure for failure in failures)


def test_scale_payload_requires_message_error_and_confirmation_at_every_width() -> None:
    payload = _payload()
    screen = next(
        item
        for item in payload["screens"]
        if item["file"] == DPI_CONTENT_SCREENSHOTS[1]
    )
    screen["message_kinds"] = ["user"]
    screen["confirmation"]["visible"] = False

    failures = validate_scale_payload(payload, expected_scale=1.25)

    assert any(
        "420px" in failure and "warning/error" in failure for failure in failures
    )
    assert any(
        "420px" in failure and "confirmation card" in failure for failure in failures
    )


def test_cross_scale_gate_rejects_identical_capture_fingerprints() -> None:
    records = []
    for scale in REQUIRED_QT_SCALE_FACTORS:
        payload = _payload(configured=f"{scale:g}", observed=scale)
        content = [
            copy.deepcopy(screen)
            for screen in payload["screens"]
            if screen["file"] in DPI_CONTENT_SCREENSHOTS
        ]
        records.append({"scale": scale, "dpi_content": content})
    for record in records:
        for screen in record["dpi_content"]:
            screen["image_sha256"] = f"{screen['logical_size'][0]:064x}"

    failures = validate_cross_scale_records(records)

    assert any("fingerprint" in failure for failure in failures)


def test_dpi_gate_has_no_dead_strip_or_outer_fill_assumption() -> None:
    source = inspect.getsource(dpi_gate)

    assert "dead_strip" not in source
    assert "outer_dock_fill" not in source
    assert "panel_fills_dock_width" not in source


def test_dpi_manifest_binds_source_environment_roles_and_hashes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def fake_capture(*, scale: float, output_dir: Path):
        payload = _payload(configured=f"{scale:g}", observed=scale)
        output_dir.mkdir(parents=True)
        for index, filename in enumerate(SELECTED_SCREENSHOTS):
            screen = next(
                (item for item in payload["screens"] if item.get("file") == filename),
                None,
            )
            size = (
                tuple(screen["pixel_size"])
                if screen is not None
                else (round(1024 * scale), round(760 * scale))
            )
            color = (35 + round(scale * 20), 70 + index, 105)
            path = output_dir / filename
            Image.new("RGB", size, color).save(path)
            if screen is not None:
                screen["image_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        return subprocess.CompletedProcess([], 0, "", ""), payload

    monkeypatch.setattr(dpi_gate, "_run_scale_capture", fake_capture)
    source_identity = _source_identity()
    monkeypatch.setattr(
        dpi_gate,
        "collect_source_identity",
        lambda *_args, **_kwargs: dict(source_identity),
    )
    monkeypatch.setattr(
        artifact_integrity,
        "collect_source_identity",
        lambda *_args, **_kwargs: dict(source_identity),
    )
    output_dir = tmp_path / "dpi"

    result = dpi_gate.run_dpi_gate(output_dir)

    assert result["status"] == "passed"
    assert result["generator"] == "scripts/dev/run_chatpanel_ui_dpi_gate.py"
    assert result["source_identity"]["commit_sha"]
    assert result["source_identity"]["head_tree_sha"]
    assert result["source_identity"]["source_digest"]
    assert isinstance(result["source_identity"]["dirty"], bool)
    assert result["capture_environment"]["required_scales"] == [1.0, 1.25, 1.5]
    assert result["claims"]
    assert result["limitations"]
    assert set(result["screenshots"]) == {
        f"scale-{round(scale * 100):03d}-{filename}"
        for scale in REQUIRED_QT_SCALE_FACTORS
        for filename in SELECTED_SCREENSHOTS
    }
    assert all(item["sha256"] for item in result["screenshots"].values())
    assert {
        record["scale"] for record in result["records"] if record["status"] == "passed"
    } == set(REQUIRED_QT_SCALE_FACTORS)
    assert all(record["full_window_dock"] for record in result["records"])
    assert all(record["narrow_crops"] for record in result["records"])

    ok, reason = validate_dpi_manifest(
        result,
        output_dir=output_dir,
        refresh_source_identity=False,
        current_source_identity=result["source_identity"],
    )
    assert ok is True, reason

    first = output_dir / next(iter(result["screenshots"]))
    first.write_bytes(b"tampered")
    ok, reason = validate_dpi_manifest(
        result,
        output_dir=output_dir,
        refresh_source_identity=False,
        current_source_identity=result["source_identity"],
    )
    assert ok is False
    assert "metadata/hash mismatch" in reason
