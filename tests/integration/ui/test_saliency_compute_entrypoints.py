"""Real GUI and Assistant entry-point coverage for manual saliency computation."""

from __future__ import annotations

import time
from pathlib import Path
from threading import Event

import pytest
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication, QDialogButtonBox

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
from XBrainLab.backend.training.evaluator import Evaluator
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyPhase,
    TrainingOutcomeState,
)
from XBrainLab.llm.agent.ui_handoff import (
    WorkflowUiHandoffRequest,
    WorkflowUiHandoffResolutionStatus,
)
from XBrainLab.ui.components.workflow_ui_handoff_host import WorkflowUiHandoffHost
from XBrainLab.ui.dialogs.visualization.saliency_setting_dialog import (
    SaliencySettingDialog,
)
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
        widget = panel.tabs.currentWidget()
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
        view_ready = (
            widget.scene_ready
            if widget is panel.tab_3d
            else canvas is not None
            and canvas.isVisible()
            and bool(axes)
            and image_count > 0
            and (error_label is None or error_label.isHidden())
        )
        return bool(
            isinstance(summary, dict)
            and int(summary.get("finite_count") or 0) > 0
            and int(summary.get("nonfinite_count") or 0) == 0
            and view_ready
            and widget.property("renderStatus") == "completed"
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
@pytest.mark.parametrize("recompute_view", ["tab_map", "tab_topo"])
@pytest.mark.usefixtures("allow_real_modals")
def test_real_gui_and_assistant_saliency_entrypoints_render_finite_results(
    qtbot,
    tmp_path: Path,
    first_entrypoint: str,
    recompute_view: str,
    monkeypatch,
    noise_method: str = "SmoothGrad",
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

        # Reproduce the manual Settings path, retaining the default noise
        # parameters rather than reducing the actual SmoothGrad workload.
        selected_params = []
        panel.tabs.setCurrentWidget(getattr(panel, recompute_view))

        def select_smoothgrad() -> None:
            dialog = QApplication.activeModalWidget()
            assert isinstance(dialog, SaliencySettingDialog)
            for method, checkbox in dialog.method_checks.items():
                checkbox.setChecked(method == noise_method)
            qtbot.mouseClick(
                dialog.button_box.button(QDialogButtonBox.StandardButton.Ok),
                Qt.MouseButton.LeftButton,
            )
            selected_params.append(dialog.get_result())

        QTimer.singleShot(0, select_smoothgrad)
        qtbot.mouseClick(panel.saliency_settings_btn, Qt.MouseButton.LeftButton)
        assert selected_params
        assert selected_params[0][noise_method] == {
            "nt_samples": 5,
            "nt_samples_batch_size": None,
            "stdevs": 1.0,
        }
        qtbot.mouseClick(panel.compute_saliency_btn, Qt.MouseButton.LeftButton)
        _wait_for_visible_finite_saliency(qtbot, panel)
        assert (
            service.get_state().visualization.post_training_saliency.generation
            > first_generation
        )
        panel.method_combo.setCurrentText(noise_method)
        _wait_for_visible_finite_saliency(qtbot, panel)

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

        # Hold only the expensive evaluation seam so a click reliably lands
        # during real owned work. The original evaluator still executes;
        # cancellation must prevent its result from replacing the prior record.
        entered = Event()
        release = Event()
        evaluate = Evaluator.evaluate_with_saliency
        holder = service.study.trainer.get_training_plan_holders()[0]
        previous_record = holder.get_plans()[0].get_eval_record()

        def held_evaluation(*args, **kwargs):
            entered.set()
            assert release.wait(10), "GUI did not release the evaluation test barrier"
            return evaluate(*args, **kwargs)

        heartbeat = []
        timer = QTimer(panel)
        timer.setInterval(10)
        timer.timeout.connect(lambda: heartbeat.append(time.monotonic()))
        timer.start()
        try:
            with monkeypatch.context() as controlled:
                controlled.setattr(Evaluator, "evaluate_with_saliency", held_evaluation)
                qtbot.mouseClick(panel.compute_saliency_btn, Qt.MouseButton.LeftButton)
                qtbot.waitUntil(entered.is_set, timeout=5_000)
                assert panel.cursor().shape() is Qt.CursorShape.ArrowCursor
                qtbot.waitUntil(lambda: len(heartbeat) >= 5, timeout=1_000)
                operation_id = panel._active_saliency_operation_id
                assert operation_id
                window.switch_page(0)
                qtbot.waitUntil(lambda: window.stack.currentIndex() == 0)
                window.switch_page(4)
                qtbot.waitUntil(lambda: panel.cancel_saliency_btn.isVisible())
                assert panel.cancel_saliency_btn.isEnabled()
                qtbot.mouseClick(panel.cancel_saliency_btn, Qt.MouseButton.LeftButton)
                assert service.get_owned_operation(operation_id).cancel_requested
                release.set()
                qtbot.waitUntil(
                    lambda: not panel._saliency_compute_in_progress, timeout=10_000
                )
        finally:
            release.set()
            timer.stop()
        assert (
            service.get_state().visualization.post_training_saliency.phase
            is PostTrainingSaliencyPhase.CANCELLED
        )
        assert holder.get_plans()[0].get_eval_record() is previous_record
        assert panel.compute_saliency_btn.isEnabled()
        qtbot.mouseClick(panel.compute_saliency_btn, Qt.MouseButton.LeftButton)
        _wait_for_visible_finite_saliency(qtbot, panel)

        # Also cancel the native render AFTER the backend has succeeded: this
        # must release Computing, not merely hide Cancel and drop its callback.
        view = getattr(panel, recompute_view)
        panel.tabs.setCurrentWidget(view)
        _wait_for_visible_finite_saliency(qtbot, panel)
        render_owner = type(view)
        render_name = "_render_plot"
        if view is panel.tab_3d:
            from XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view import (
                Saliency3D,
            )

            render_owner = Saliency3D
            render_name = "prepare_engine"
        render = getattr(render_owner, render_name)
        render_entered = Event()
        render_release = Event()

        def held_render(*args, **kwargs):
            render_entered.set()
            assert render_release.wait(10), "GUI did not release native render barrier"
            return render(*args, **kwargs)

        try:
            with monkeypatch.context() as controlled:
                controlled.setattr(render_owner, render_name, staticmethod(held_render))
                qtbot.mouseClick(panel.compute_saliency_btn, Qt.MouseButton.LeftButton)
                qtbot.waitUntil(render_entered.is_set, timeout=5_000)
                assert (
                    service.get_state().visualization.post_training_saliency.phase
                    is PostTrainingSaliencyPhase.SUCCEEDED
                )
                assert panel._saliency_compute_in_progress
                operation_id = panel._saliency_operation_presenter.active_operation_id
                assert operation_id and view in panel._native_render_bindings
                assert panel.cancel_saliency_btn.isVisible()
                assert panel.cancel_saliency_btn.isEnabled()
                qtbot.mouseClick(panel.cancel_saliency_btn, Qt.MouseButton.LeftButton)
                assert not panel._saliency_compute_in_progress
                assert panel.compute_saliency_btn.isEnabled()
                assert (
                    service.get_owned_operation(operation_id).phase.value == "cancelled"
                )
                render_release.set()
                qtbot.waitUntil(panel.native_render_work_idle, timeout=10_000)
                assert view.property("renderStatus") == "cancelled"
        finally:
            render_release.set()
        qtbot.mouseClick(panel.compute_saliency_btn, Qt.MouseButton.LeftButton)
        _wait_for_visible_finite_saliency(qtbot, panel)
    finally:
        window.close()
        deadline = time.monotonic() + (_TIMEOUT_MS / 1_000)
        while window.isVisible() and time.monotonic() < deadline:
            qtbot.wait(50)
