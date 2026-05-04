from __future__ import annotations

from scripts.dev.probe_pyvistaqt_runtime import (
    render_markdown,
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
