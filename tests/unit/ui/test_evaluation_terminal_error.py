from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest
from PyQt6.QtWidgets import QLabel

from XBrainLab.backend.application import (
    EvaluationPlanIdentity,
    EvaluationRenderData,
    EvaluationRunIdentity,
    EvaluationSummaryIdentity,
)
from XBrainLab.backend.application.results import (
    ChangedState,
    CommandResult,
    ErrorType,
)
from XBrainLab.ui.panels.evaluation.confusion_matrix import ConfusionMatrixWidget
from XBrainLab.ui.panels.evaluation.panel import EvaluationPanel


@pytest.mark.parametrize(
    "terminal_kind",
    ["failed_result", "worker_error", "invalid_result"],
)
def test_model_summary_async_failure_replaces_loading_with_actionable_terminal_state(
    qtbot,
    monkeypatch,
    caplog,
    capture_product_logs,
    terminal_kind: str,
) -> None:
    callbacks: dict[str, Callable[..., Any]] = {}
    requested_commands = []

    def capture_async(_panel, command, *, on_result, on_error, **_kwargs):
        requested_commands.append(command)
        callbacks["result"] = on_result
        callbacks["error"] = on_error
        return True

    monkeypatch.setattr(
        "XBrainLab.ui.panels.evaluation.panel.execute_application_command_async",
        capture_async,
    )
    panel = EvaluationPanel()
    qtbot.addWidget(panel)
    panel._application_generation = 4
    run_identity = EvaluationRunIdentity(
        plan=EvaluationPlanIdentity(plan_index=0),
        run_index=0,
    )
    summary_identity = EvaluationSummaryIdentity(
        plan=run_identity.plan,
        run=run_identity,
    )

    panel.update_model_summary(summary_identity)

    assert panel.summary_text.toPlainText() == "Loading model details..."
    assert requested_commands[0].summary_identity == summary_identity

    with capture_product_logs(
        logging.ERROR,
        logger_name="XBrainLab.ui.panels.evaluation.panel",
    ):
        if terminal_kind == "failed_result":
            failed = CommandResult.failure_result(
                command_name="evaluate",
                message="KeyError: 0 from raw backend result",
                state={},
                changed_state=ChangedState(),
                error_type=ErrorType.EVALUATION,
                recoverable=True,
            )
            callbacks["result"](failed)
        elif terminal_kind == "worker_error":
            error = RuntimeError("private worker traceback detail")
            callbacks["error"](
                (RuntimeError, error, "Traceback: private worker traceback detail"),
            )
        else:
            callbacks["result"](object())

    visible = panel.summary_text.toPlainText()
    assert visible == (
        "Model details could not be loaded. Select another completed run or "
        "reopen Evaluation to try again."
    )
    assert "Loading model details" not in visible
    assert "KeyError" not in visible
    assert "private worker" not in visible
    assert panel._model_summary_identity is None
    assert (
        "KeyError: 0 from raw backend result" in caplog.text
        or "private worker traceback detail" in caplog.text
        or "invalid result" in caplog.text
    )


def test_confusion_matrix_exception_uses_product_copy_and_logs_diagnostic(
    qtbot,
    monkeypatch,
    caplog,
    capture_product_logs,
) -> None:
    widget = ConfusionMatrixWidget()
    qtbot.addWidget(widget)
    identity = EvaluationPlanIdentity(plan_index=0)
    data = EvaluationRenderData(
        labels=np.array([0]),
        outputs=np.array([[1.0, 0.0]]),
        metrics={},
        class_labels={0: "Left", 1: "Right"},
        summary_identity=EvaluationSummaryIdentity(plan=identity),
        evaluation_split="test",
    )
    monkeypatch.setattr(
        widget,
        "_build_figure",
        MagicMock(side_effect=RuntimeError("private confusion matrix tuple")),
    )

    with capture_product_logs(logging.ERROR):
        widget.update_plot(data)

    visible = [label.text() for label in widget.findChildren(QLabel) if label.text()]
    assert visible == [
        "Confusion matrix could not be displayed. "
        "Select another completed run or refresh Evaluation."
    ]
    assert all("private confusion matrix tuple" not in text for text in visible)
    assert "private confusion matrix tuple" in caplog.text


def test_evaluation_product_code_has_no_raw_terminal_error_ui_sinks() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(Path("XBrainLab/ui/panels/evaluation").glob("*.py"))
    )

    assert 'self._show_message(f"Error: {e}"' not in source
    assert "self.summary_text.setText(str(error" not in source
    assert "self.no_data_label.setText(str(error" not in source
