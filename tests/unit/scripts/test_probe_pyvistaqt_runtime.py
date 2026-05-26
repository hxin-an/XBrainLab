from __future__ import annotations

import subprocess

from scripts.dev.probe_pyvistaqt_runtime import (
    render_markdown,
    run_probe,
    summarize_probe_result,
)


def test_summarize_probe_result_marks_badwindow_as_blocked() -> None:
    payload = summarize_probe_result(
        returncode=1,
        stdout="",
        stderr="X Error of failed request:  BadWindow (invalid Window parameter)",
        image_exists=False,
        timeout_seconds=60,
        environment={"DISPLAY": ":0"},
    )

    assert payload["status"] == "blocked"
    assert payload["checks"]["bad_window_error"] is True
    assert payload["claim_boundary"].startswith("Interactive PyVistaQt")


def test_render_markdown_keeps_claim_boundary() -> None:
    payload = summarize_probe_result(
        returncode=0,
        stdout="plotter_created=True\nimage_exists=True\n",
        stderr="",
        image_exists=True,
        timeout_seconds=60,
        environment={"DISPLAY": ":0"},
    )

    rendered = render_markdown(payload)

    assert "# PyVistaQt Runtime Probe" in rendered
    assert "Interactive PyVistaQt runtime probe" in rendered
    assert "not a full XBrainLab 3D saliency render" in rendered


def test_run_probe_applies_wslg_xcb_default(monkeypatch, tmp_path) -> None:
    captured_env = {}

    screenshot_path = tmp_path / "probe.png"

    def fake_run(*_args, **kwargs):
        captured_env.update(kwargs["env"])
        screenshot_path.write_bytes(b"fake image")
        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="plotter_created=True\nimage_exists=True\n",
            stderr="",
        )

    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu-24.04")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.setattr("scripts.dev.probe_pyvistaqt_runtime.subprocess.run", fake_run)

    payload = run_probe(screenshot_path, timeout_seconds=10)

    assert captured_env["QT_QPA_PLATFORM"] == "xcb"
    assert payload["status"] == "passed"
