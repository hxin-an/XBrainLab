"""Real GUI and Assistant entry-point coverage for manual saliency computation."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt

from scripts.dev.chatpanel_training_fixture import write_training_ready_raw_fif
from scripts.dev.training_evidence_fixture import prepare_training_dataset_ready_state
from XBrainLab.backend.application import (
    ApplyMontageCommand,
    CommandName,
    ConfigureTrainingCommand,
    TrainCommand,
    get_application_service,
)
from XBrainLab.backend.study import Study
from XBrainLab.backend.training_state_contract import TrainingOutcomeState
from XBrainLab.llm.agent.ui_handoff import (
    WorkflowUiHandoffRequest,
    WorkflowUiHandoffResolutionStatus,
)
from XBrainLab.ui.components.workflow_ui_handoff_host import WorkflowUiHandoffHost
from XBrainLab.ui.main_window import MainWindow

_TIMEOUT_MS = 120_000


def _wait_for_finished_training(qtbot, service) -> None:
    qtbot.waitUntil(
        lambda: (
            not service.get_state().training.is_running
            and service.get_state().training.terminal_outcome.is_terminal
        ),
        timeout=_TIMEOUT_MS,
    )
    training = service.get_state().training
    assert training.terminal_outcome.state is TrainingOutcomeState.COMPLETED, (
        training.terminal_outcome
    )
    assert training.finished_run_count >= 1


def _wait_for_visible_finite_saliency(qtbot, panel) -> None:
    def rendered() -> bool:
        widget = panel.tab_map
        summary = widget.property("saliencyNumericSummary")
        canvas = getattr(widget, "canvas", None)
        figure = getattr(widget, "fig", None)
        axes = list(getattr(figure, "axes", ()) or ())
        image_count = sum(
            len(getattr(axis, "images", ()) or ())
            + len(getattr(axis, "collections", ()) or ())
            for axis in axes
        )
        error_label = getattr(widget, "error_label", None)
        return bool(
            isinstance(summary, dict)
            and int(summary.get("finite_count") or 0) > 0
            and int(summary.get("nonfinite_count") or 0) == 0
            and canvas is not None
            and canvas.isVisible()
            and axes
            and image_count > 0
            and (error_label is None or error_label.isHidden())
            and not panel._saliency_compute_in_progress
        )

    qtbot.waitUntil(rendered, timeout=_TIMEOUT_MS)


def _open_visualization_panel(qtbot, window):
    window.switch_page(4)
    qtbot.waitUntil(
        lambda: (
            4 in window._loaded_panel_indices
            and window.stack.currentIndex() == 4
            and window.visualization_panel is not None
        ),
        timeout=_TIMEOUT_MS,
    )
    panel = window.visualization_panel
    panel.tabs.setCurrentWidget(panel.tab_map)
    qtbot.waitUntil(
        lambda: panel.compute_saliency_btn.isVisible()
        and panel.compute_saliency_btn.isEnabled(),
        timeout=_TIMEOUT_MS,
    )
    return panel


@pytest.mark.parametrize("first_entrypoint", ["gui", "assistant"])
def test_real_gui_and_assistant_saliency_entrypoints_render_finite_results(
    qtbot,
    tmp_path: Path,
    first_entrypoint: str,
) -> None:
    """Both approved entry points schedule real work and render a visible result."""
    study = Study()
    service = get_application_service(study)
    source_path = write_training_ready_raw_fif(tmp_path / "training_ready_raw.fif")
    window = MainWindow(study)
    qtbot.addWidget(window)
    window.resize(1200, 800)
    window.show()

    try:
        prepared = prepare_training_dataset_ready_state(
            study,
            source_path,
            tmp_path / "training-output",
        )
        assert prepared["ok"], prepared["commands"]
        for command in (
            ConfigureTrainingCommand(model_name="braindecode.eegnet"),
            ApplyMontageCommand(
                channels=["C3", "C4", "Cz", "Pz"],
                positions=[
                    (-0.06, 0.0, 0.04),
                    (0.06, 0.0, 0.04),
                    (0.0, 0.04, 0.08),
                    (0.0, -0.08, 0.02),
                ],
                montage_name="synthetic-4ch",
            ),
            TrainCommand(confirmed=True, interactive=True),
        ):
            result = service.execute(command)
            assert result.ok, result.message

        _wait_for_finished_training(qtbot, service)
        assert not service.get_state().visualization.saliency_available

        host = WorkflowUiHandoffHost(window)
        request = WorkflowUiHandoffRequest.for_action(
            CommandName.SALIENCY,
            tool_name="compute_saliency",
        )
        if first_entrypoint == "gui":
            panel = _open_visualization_panel(qtbot, window)
            qtbot.mouseClick(
                panel.compute_saliency_btn,
                Qt.MouseButton.LeftButton,
                pos=panel.compute_saliency_btn.rect().center(),
            )
        else:
            terminal_resolutions = []
            initial = host.open(
                request,
                on_terminal=lambda resolution: terminal_resolutions.append(resolution)
                or True,
            )
            assert initial.status is WorkflowUiHandoffResolutionStatus.COMMAND_PENDING
            qtbot.waitUntil(lambda: bool(terminal_resolutions), timeout=_TIMEOUT_MS)
            assert (
                terminal_resolutions[-1].status
                is WorkflowUiHandoffResolutionStatus.COMPLETED
            ), terminal_resolutions[-1]
            panel = window.visualization_panel
            panel.tabs.setCurrentWidget(panel.tab_map)
        _wait_for_visible_finite_saliency(qtbot, panel)
        first_generation = (
            service.get_state().visualization.post_training_saliency.generation
        )

        panel.method_combo.setCurrentText("Gradient * Input")
        panel.tabs.setCurrentWidget(panel.tab_spectro)
        qtbot.waitUntil(
            lambda: panel.tab_spectro.isVisible()
            and panel.method_combo.currentText() == "Gradient * Input",
            timeout=_TIMEOUT_MS,
        )

        terminal_resolutions = []
        initial = host.open(
            request,
            on_terminal=lambda resolution: terminal_resolutions.append(resolution)
            or True,
        )
        assert initial.status is WorkflowUiHandoffResolutionStatus.COMMAND_PENDING
        qtbot.waitUntil(lambda: bool(terminal_resolutions), timeout=_TIMEOUT_MS)
        assert (
            terminal_resolutions[-1].status
            is WorkflowUiHandoffResolutionStatus.COMPLETED
        )
        assert (
            service.get_state().visualization.post_training_saliency.generation
            > first_generation
        )

        panel.tabs.setCurrentWidget(panel.tab_map)
        _wait_for_visible_finite_saliency(qtbot, panel)
    finally:
        window.close()
        deadline = time.monotonic() + (_TIMEOUT_MS / 1_000)
        while window.isVisible() and time.monotonic() < deadline:
            qtbot.wait(50)
