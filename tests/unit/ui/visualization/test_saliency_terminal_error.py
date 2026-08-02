from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import numpy as np

from XBrainLab.backend.application.results import (
    ChangedState,
    CommandResult,
    ErrorType,
)
from XBrainLab.backend.application.saliency_render import (
    SaliencyPlanIdentity,
    SaliencyRenderData,
    SaliencyRenderPublication,
    SaliencyRenderRequest,
    SaliencyRunIdentity,
)
from XBrainLab.backend.application.state import (
    SaliencyClassCoverageSnapshot,
    SaliencyMethodCoverageSnapshot,
)
from XBrainLab.ui.interaction_outcome import InteractionStatus
from XBrainLab.ui.panels.visualization.panel import VisualizationPanel
from XBrainLab.ui.panels.visualization.saliency_views.base_saliency_view import (
    BaseSaliencyView,
)
from XBrainLab.ui.panels.visualization.saliency_views.map_view import SaliencyMapWidget


def _render_publication() -> SaliencyRenderPublication:
    request = SaliencyRenderRequest(
        publication_generation=3,
        run=SaliencyRunIdentity(
            plan=SaliencyPlanIdentity(plan_index=0),
            run_index=0,
        ),
        method="Gradient",
    )
    return SaliencyRenderPublication(
        request=request,
        generation=3,
        training_generation=1,
        data=SaliencyRenderData(
            method="Gradient",
            saliency_by_class={0: np.ones((1, 1, 3))},
            class_map=((0, "left"),),
            event_ids={"left": 0},
            channel_names=("C3",),
            channel_positions=((0.0, 0.0, 0.1),),
            sfreq=128.0,
            tmin=0.0,
        ),
    )


def test_render_exception_is_sanitized_for_user_and_product_log(
    qtbot,
    caplog,
    capture_product_logs,
) -> None:
    view = BaseSaliencyView()
    qtbot.addWidget(view)

    with capture_product_logs(
        logging.ERROR,
        logger_name=(
            "XBrainLab.ui.panels.visualization.saliency_views.base_saliency_view"
        ),
    ):
        view._render_figure_async(
            lambda: (_ for _ in ()).throw(
                RuntimeError("KeyError: 0 / private render tuple"),
            ),
            error_context="saliency map",
        )
        qtbot.waitUntil(
            lambda: "Rendering saliency" not in view.error_label.text(),
            timeout=3_000,
        )

    visible = view.error_label.text()
    assert visible == (
        "Error: Saliency could not be rendered. "
        "Try again or choose another saliency view."
    )
    assert "KeyError" not in visible
    assert "private render tuple" not in visible
    assert "KeyError: 0" in caplog.text
    assert "private render tuple" not in caplog.text
    assert "[REDACTED_PATH]" in caplog.text


def test_preparation_exception_is_sanitized_before_render_dispatch(
    qtbot,
    caplog,
    capture_product_logs,
) -> None:
    view = SaliencyMapWidget()
    qtbot.addWidget(view)
    view.set_saliency_coverage(
        SaliencyMethodCoverageSnapshot(
            method="Gradient",
            classes=[
                SaliencyClassCoverageSnapshot(
                    class_index=0,
                    display_name="left",
                    available=True,
                ),
            ],
        ),
    )

    with (
        patch.object(
            view,
            "require_complete_saliency_coverage",
            side_effect=RuntimeError("private preparation traceback"),
        ),
        capture_product_logs(logging.ERROR),
    ):
        view.update_plot(_render_publication(), False)

    visible = view.error_label.text()
    assert visible == (
        "Error: This saliency view could not be prepared. "
        "Recompute saliency or choose another view."
    )
    assert "private preparation traceback" not in visible
    assert "private preparation traceback" in caplog.text


def test_visualization_query_failure_message_sanitizes_internal_backend_detail(
    qtbot,
    caplog,
    capture_product_logs,
) -> None:
    panel = VisualizationPanel()
    qtbot.addWidget(panel)
    panel.last_application_query = CommandResult.failure_result(
        command_name="visualize",
        message="KeyError: private visualization state tuple",
        state={},
        changed_state=ChangedState(),
        error_type=ErrorType.INTERNAL,
        recoverable=True,
    )

    with capture_product_logs(logging.ERROR):
        visible = panel._application_query_message()

    assert visible == (
        "Visualization could not be loaded. Refresh Visualization and try again."
    )
    assert "KeyError" not in visible
    assert "private visualization state tuple" in caplog.text


def test_compute_failed_result_uses_retryable_product_copy_without_backend_message(
    qtbot,
    caplog,
    capture_product_logs,
) -> None:
    panel = VisualizationPanel()
    qtbot.addWidget(panel)
    current_widget = panel.tabs.currentWidget()
    assert isinstance(current_widget, BaseSaliencyView)
    attempt_key = ("manual", "Fold 1", "Run 1", "Gradient", ())
    panel._saliency_compute_attempted.add(attempt_key)
    panel._saliency_compute_in_progress = True
    result = CommandResult.failure_result(
        command_name="saliency",
        message="RuntimeError: CUDA kernel tuple ('private', 0)",
        state={},
        changed_state=ChangedState(),
        error_type=ErrorType.VISUALIZATION,
        recoverable=True,
    )

    with capture_product_logs(logging.ERROR):
        outcome = panel._on_lazy_saliency_configured(
            result,
            attempt_key=attempt_key,
            current_widget=current_widget,
        )

    expected = "Saliency could not be computed. Adjust the settings and try again."
    assert outcome.status is InteractionStatus.FAILED
    assert outcome.message == expected
    assert current_widget.error_label.text() == f"Error: {expected}"
    assert panel.saliency_action_detail.text() == expected
    assert "RuntimeError" not in current_widget.error_label.text()
    assert "private" not in current_widget.error_label.text()
    assert "RuntimeError: CUDA kernel tuple ('private', 0)" in caplog.text


def test_compute_worker_error_tuple_is_sanitized_and_logged(
    qtbot,
    caplog,
    capture_product_logs,
) -> None:
    panel = VisualizationPanel()
    qtbot.addWidget(panel)
    current_widget = panel.tabs.currentWidget()
    assert isinstance(current_widget, BaseSaliencyView)
    attempt_key = ("manual", "Fold 1", "Run 1", "Gradient", ())
    panel._saliency_compute_attempted.add(attempt_key)
    panel._saliency_compute_in_progress = True
    error = RuntimeError("private async tuple")

    with capture_product_logs(logging.ERROR):
        panel._on_lazy_saliency_error(
            (RuntimeError, error, "Traceback: private async tuple"),
            attempt_key=attempt_key,
            current_widget=current_widget,
        )

    expected = "Saliency could not be computed. Adjust the settings and try again."
    assert current_widget.error_label.text() == f"Error: {expected}"
    assert panel.saliency_action_detail.text() == expected
    assert "private async tuple" not in current_widget.error_label.text()
    assert "private async tuple" in caplog.text


def test_saliency_product_code_has_no_raw_terminal_error_ui_sinks() -> None:
    panel_path = Path(
        "XBrainLab/ui/panels/visualization/panel.py",
    )
    views_path = Path(
        "XBrainLab/ui/panels/visualization/saliency_views",
    )
    source = panel_path.read_text(encoding="utf-8")
    source += "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(views_path.glob("*.py"))
    )

    forbidden = (
        "self._display_error(str(value))",
        "self.show_error(str(e))",
        "self.show_error(str(message))",
        'f"Saliency failed: {result.message}"',
        'f"Saliency failed: {message}"',
        'f"Error during plotting: {e}"',
    )
    assert all(fragment not in source for fragment in forbidden)
