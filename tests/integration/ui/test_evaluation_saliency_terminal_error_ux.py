from __future__ import annotations

from collections.abc import Callable
from typing import Any

from XBrainLab.backend.application import (
    EvaluationPlanIdentity,
    EvaluationRunIdentity,
    EvaluationSummaryIdentity,
)
from XBrainLab.ui.panels.evaluation.panel import EvaluationPanel
from XBrainLab.ui.panels.visualization.saliency_views.base_saliency_view import (
    BaseSaliencyView,
)


def test_evaluation_async_worker_error_reaches_visible_terminal_state(
    qtbot,
    monkeypatch,
) -> None:
    callbacks: dict[str, Callable[..., Any]] = {}

    def capture_async(_panel, _command, *, on_result, on_error, **_kwargs):
        callbacks["result"] = on_result
        callbacks["error"] = on_error
        return True

    monkeypatch.setattr(
        "XBrainLab.ui.panels.evaluation.panel.execute_application_command_async",
        capture_async,
    )
    panel = EvaluationPanel()
    qtbot.addWidget(panel)
    panel.resize(900, 650)
    panel._application_generation = 4
    run_identity = EvaluationRunIdentity(
        plan=EvaluationPlanIdentity(plan_index=0),
        run_index=0,
    )
    summary_identity = EvaluationSummaryIdentity(
        plan=run_identity.plan,
        run=run_identity,
    )
    panel.bottom_tabs.setCurrentWidget(panel.summary_tab)
    panel.show()

    panel.update_model_summary(summary_identity)
    assert panel.summary_text.toPlainText() == "Loading model details..."

    callbacks["error"](
        (
            RuntimeError,
            RuntimeError("private evaluation worker detail"),
            "Traceback: private evaluation worker detail",
        ),
    )
    qtbot.waitUntil(
        lambda: "could not be loaded" in panel.summary_text.toPlainText(),
        timeout=2_000,
    )

    visible = panel.summary_text.toPlainText()
    assert "reopen Evaluation to try again" in visible
    assert "private evaluation worker detail" not in visible
    image = panel.grab().toImage()
    assert not image.isNull()
    assert image.width() >= 900
    assert image.height() >= 650


def test_saliency_background_render_error_reaches_visible_sanitized_state(
    qtbot,
) -> None:
    view = BaseSaliencyView()
    qtbot.addWidget(view)
    view.resize(720, 480)
    view.show()

    def fail_render():
        raise RuntimeError("private saliency backend tuple")

    view._render_figure_async(fail_render, error_context="integration saliency")
    qtbot.waitUntil(
        lambda: "could not be rendered" in view.error_label.text(),
        timeout=3_000,
    )

    visible = view.error_label.text()
    assert visible == (
        "Error: Saliency could not be rendered. "
        "Try again or choose another saliency view."
    )
    assert "private saliency backend tuple" not in visible
    image = view.grab().toImage()
    assert not image.isNull()
    assert image.width() >= 720
    assert image.height() >= 480
