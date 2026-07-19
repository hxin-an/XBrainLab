from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from PyQt6.QtWidgets import QLabel

from XBrainLab.backend.application.results import (
    ChangedState,
    CommandResult,
    ErrorType,
)
from XBrainLab.ui.panels.evaluation.confusion_matrix import ConfusionMatrixWidget
from XBrainLab.ui.panels.evaluation.panel import EvaluationPanel


class _FinishedRecord:
    eval_record = None

    @staticmethod
    def is_finished() -> bool:
        return True


class _Plan:
    def __init__(self) -> None:
        self.record = _FinishedRecord()

    @staticmethod
    def get_name() -> str:
        return "EEGNet"

    def get_plans(self) -> list[_FinishedRecord]:
        return [self.record]


def _base_evaluation_result(plan: _Plan) -> CommandResult:
    return CommandResult.success_result(
        command_name="evaluate",
        message="Evaluation summary ready.",
        state={},
        changed_state=ChangedState(),
        diagnostics={
            "payload_type": "evaluation_summary",
            "available": True,
            "plan_objects": [plan],
        },
    )


@pytest.mark.parametrize(
    "terminal_kind",
    ["failed_result", "worker_error", "invalid_result"],
)
def test_model_summary_async_failure_replaces_loading_with_actionable_terminal_state(
    qtbot,
    monkeypatch,
    caplog,
    terminal_kind: str,
) -> None:
    plan = _Plan()
    baseline = _base_evaluation_result(plan)
    callbacks: dict[str, Callable[..., Any]] = {}

    def capture_async(_panel, _command, *, on_result, on_error, **_kwargs):
        callbacks["result"] = on_result
        callbacks["error"] = on_error
        return True

    monkeypatch.setattr(
        "XBrainLab.ui.panels.evaluation.panel.execute_application_command_async",
        capture_async,
    )
    panel = EvaluationPanel(controller=None)
    qtbot.addWidget(panel)
    panel.last_application_query = baseline
    panel.model_combo.blockSignals(True)
    panel.model_combo.addItem("Fold 1: EEGNet", plan)
    panel.model_combo.blockSignals(False)

    panel.update_model_summary(plan, record=plan.record)

    assert panel.summary_text.toPlainText() == "Loading model details..."

    with caplog.at_level(
        logging.ERROR,
        logger="XBrainLab.ui.panels.evaluation.panel",
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
    assert panel.last_application_query is baseline
    assert (
        "KeyError: 0 from raw backend result" in caplog.text
        or "private worker traceback detail" in caplog.text
        or "invalid result" in caplog.text
    )


def test_confusion_matrix_exception_uses_product_copy_and_logs_diagnostic(
    qtbot,
    caplog,
) -> None:
    class _BrokenRecord:
        @staticmethod
        def get_confusion_figure(*, show_percentage: bool = False):
            del show_percentage
            raise RuntimeError("private confusion matrix tuple")

    widget = ConfusionMatrixWidget()
    qtbot.addWidget(widget)

    with caplog.at_level(logging.ERROR, logger="XBrainLab"):
        widget.update_plot(_BrokenRecord())

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
