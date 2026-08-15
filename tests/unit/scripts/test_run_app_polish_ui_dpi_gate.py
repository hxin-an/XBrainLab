from __future__ import annotations

from types import SimpleNamespace

from scripts.dev.run_app_polish_ui_dpi_gate import (
    DPI_APP_POLISH_SURFACES,
    REQUIRED_SCALE_FACTORS,
    _capture_scale,
    build_dpi_gate_manifest,
    validate_dpi_gate_manifest,
)


def _capture(scale: float) -> dict[str, object]:
    return {
        "requested_scale_factor": scale,
        "observed_device_pixel_ratio": scale,
        "platform_system": "Windows",
        "qt_platform": "windows",
        "evidence_path": (f"scale-{round(scale * 100):03d}/app-polish-evidence.json"),
        "evidence_valid": True,
        "selected_surfaces": list(DPI_APP_POLISH_SURFACES),
    }


def test_dpi_gate_requires_exact_windows_100_125_150_matrix():
    assert REQUIRED_SCALE_FACTORS == (1.0, 1.25, 1.5)
    payload = build_dpi_gate_manifest(
        captures=[_capture(scale) for scale in REQUIRED_SCALE_FACTORS],
        source_identity={"source_digest": "a" * 64},
    )

    ok, reason = validate_dpi_gate_manifest(
        payload,
        expected_source_digest="a" * 64,
    )

    assert ok, reason


def test_dpi_gate_rejects_missing_scale_and_non_windows_capture():
    captures = [_capture(1.0), _capture(1.25)]
    captures[0]["platform_system"] = "Linux"
    payload = build_dpi_gate_manifest(
        captures=captures,
        source_identity={"source_digest": "a" * 64},
    )

    ok, reason = validate_dpi_gate_manifest(
        payload,
        expected_source_digest="a" * 64,
    )

    assert not ok
    assert "Windows" in reason or "scale" in reason


def test_capture_scale_forces_native_windows_qt_and_exact_scale(monkeypatch, tmp_path):
    observed = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["env"] = kwargs["env"]
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        "scripts.dev.run_app_polish_ui_dpi_gate.subprocess.run",
        fake_run,
    )
    monkeypatch.setattr(
        "scripts.dev.run_app_polish_ui_dpi_gate.load_app_polish_evidence",
        lambda _path: {
            "capture_environment": {
                "requested_scale_factor": 1.25,
                "observed_device_pixel_ratio": 1.25,
                "platform_system": "Windows",
                "qt_platform": "windows",
            }
        },
    )
    monkeypatch.setattr(
        "scripts.dev.run_app_polish_ui_dpi_gate.validate_app_polish_evidence",
        lambda *_args, **_kwargs: (True, ""),
    )

    record = _capture_scale(
        scale=1.25,
        output_dir=tmp_path,
        source_identity={"source_digest": "a" * 64},
        timeout_seconds=30.0,
    )

    assert observed["env"]["QT_QPA_PLATFORM"] == "windows"
    assert observed["env"]["QT_SCALE_FACTOR"] == "1.25"
    assert observed["command"].count("--only") == len(DPI_APP_POLISH_SURFACES)
    assert record["qt_platform"] == "windows"
    assert record["evidence_valid"] is True
