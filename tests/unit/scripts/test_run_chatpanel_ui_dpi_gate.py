from __future__ import annotations

from scripts.dev.run_chatpanel_ui_dpi_gate import (
    REQUIRED_QT_SCALE_FACTORS,
    SELECTED_SCREENSHOTS,
    validate_scale_payload,
)


def _payload(*, configured: str = "1.25", observed: float = 1.25) -> dict:
    return {
        "status": "passed",
        "configured_qt_scale_factor": configured,
        "observed_screen_device_pixel_ratio": observed,
        "source_fingerprint": "current-source",
        "capture_source": {"stable": True},
        "failures": [],
    }


def test_dpi_gate_covers_required_independent_qt_scales() -> None:
    assert REQUIRED_QT_SCALE_FACTORS == (1.0, 1.25, 1.5)
    assert "first-paint-320-real-dock.png" in SELECTED_SCREENSHOTS
    assert "narrow-setting-change-confirmation-max-content.png" in (
        SELECTED_SCREENSHOTS
    )


def test_scale_payload_requires_matching_configured_and_observed_scale() -> None:
    assert validate_scale_payload(_payload(), expected_scale=1.25) == []

    failures = validate_scale_payload(
        _payload(configured="1.0", observed=1.0),
        expected_scale=1.25,
    )

    assert "configured QT scale factor does not match 1.25" in failures
    assert "observed Qt device pixel ratio does not match 1.25" in failures


def test_scale_payload_rejects_failed_or_stale_capture() -> None:
    payload = _payload()
    payload["status"] = "failed"
    payload["capture_source"] = {"stable": False}
    payload["source_fingerprint"] = ""

    failures = validate_scale_payload(payload, expected_scale=1.25)

    assert "focused ChatPanel capture failed" in failures
    assert "capture source changed during the DPI subprocess" in failures
    assert "capture source fingerprint is missing" in failures
