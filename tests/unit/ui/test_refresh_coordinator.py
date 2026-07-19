"""Tests for command-result-driven UI refresh coordination."""

from __future__ import annotations

from gc import collect
from types import SimpleNamespace
from weakref import ref

from PyQt6 import sip
from PyQt6.QtCore import QObject

from XBrainLab.backend.application import ChangedState, CommandResult
from XBrainLab.ui import refresh_coordinator
from XBrainLab.ui.refresh_coordinator import (
    begin_command_refresh_suppression,
    complete_command_refresh_suppression,
    refresh_after_command,
    refresh_after_navigation,
    refresh_after_observer,
    refresh_after_serialized_command,
    refresh_panel,
    suppress_observer_refresh_during_command,
)


class _PanelSpy:
    def __init__(self) -> None:
        self.update_calls = 0

    def update_panel(self) -> None:
        self.update_calls += 1


class _TrainingPanelSpy(_PanelSpy):
    def __init__(self) -> None:
        super().__init__()
        self.terminal_refresh_calls = 0

    def refresh_terminal_publication(self) -> None:
        self.terminal_refresh_calls += 1


class _QtPanelSpy(QObject):
    def __init__(self, callback_calls: list[str]) -> None:
        super().__init__()
        self._callback_calls = callback_calls
        self.main_window: object | None = None

    def update_panel(self) -> None:
        self._callback_calls.append("update")


class _InfoSpy:
    def __init__(self) -> None:
        self.update_calls = 0

    def update_info_panel(self) -> None:
        self.update_calls += 1


class _AgentSpy:
    def __init__(self) -> None:
        self.refresh_calls = 0

    def refresh_backend_status(self) -> None:
        self.refresh_calls += 1


def _result(changed_state: ChangedState) -> CommandResult:
    return CommandResult.success_result(
        command_name="test",
        message="ok",
        state=None,
        changed_state=changed_state,
    )


def _main_window() -> SimpleNamespace:
    return SimpleNamespace(
        dataset_panel=_PanelSpy(),
        preprocess_panel=_PanelSpy(),
        training_panel=_TrainingPanelSpy(),
        evaluation_panel=_PanelSpy(),
        visualization_panel=_PanelSpy(),
        agent_manager=_AgentSpy(),
        update_info_calls=0,
        update_info_panel=lambda: None,
    )


def _attach_info_spy(main_window: SimpleNamespace) -> _InfoSpy:
    info = _InfoSpy()
    main_window.update_info_panel = info.update_info_panel
    return info


def test_raw_change_refreshes_workflow_panels_and_assistant_status():
    main_window = _main_window()
    info = _attach_info_spy(main_window)
    context = SimpleNamespace(main_window=main_window)

    refreshed = refresh_after_command(
        context,
        _result(ChangedState(raw_changed=True)),
    )

    assert refreshed is True
    assert main_window.dataset_panel.update_calls == 1
    assert main_window.preprocess_panel.update_calls == 1
    assert main_window.training_panel.update_calls == 1
    assert main_window.training_panel.terminal_refresh_calls == 0
    assert main_window.evaluation_panel.update_calls == 0
    assert main_window.visualization_panel.update_calls == 0
    assert info.update_calls == 1
    assert main_window.agent_manager.refresh_calls == 1


def test_serialized_agent_change_uses_the_same_refresh_routes():
    main_window = _main_window()
    info = _attach_info_spy(main_window)
    context = SimpleNamespace(main_window=main_window)

    refreshed = refresh_after_serialized_command(
        context,
        {"epoch_changed": True},
    )

    assert refreshed is True
    assert main_window.preprocess_panel.update_calls == 1
    assert main_window.training_panel.update_calls == 1
    assert main_window.training_panel.terminal_refresh_calls == 0
    assert main_window.visualization_panel.update_calls == 1
    assert info.update_calls == 1


def test_analysis_changes_refresh_only_analysis_panels_and_shared_status():
    main_window = _main_window()
    info = _attach_info_spy(main_window)
    context = SimpleNamespace(main_window=main_window)

    refreshed = refresh_after_command(
        context,
        _result(
            ChangedState(
                evaluation_changed=True,
                visualization_changed=True,
            )
        ),
    )

    assert refreshed is True
    assert main_window.dataset_panel.update_calls == 0
    assert main_window.preprocess_panel.update_calls == 0
    assert main_window.training_panel.update_calls == 0
    assert main_window.evaluation_panel.update_calls == 1
    assert main_window.visualization_panel.update_calls == 1
    assert info.update_calls == 1
    assert main_window.agent_manager.refresh_calls == 1


def test_training_change_refreshes_downstream_analysis_readiness():
    main_window = _main_window()
    info = _attach_info_spy(main_window)
    context = SimpleNamespace(main_window=main_window)

    refreshed = refresh_after_command(
        context,
        _result(ChangedState(training_changed=True)),
    )

    assert refreshed is True
    assert main_window.dataset_panel.update_calls == 0
    assert main_window.preprocess_panel.update_calls == 0
    assert main_window.training_panel.update_calls == 1
    assert main_window.evaluation_panel.update_calls == 1
    assert main_window.visualization_panel.update_calls == 1
    assert info.update_calls == 1
    assert main_window.agent_manager.refresh_calls == 1


def test_epoch_change_refreshes_visualization_readiness():
    main_window = _main_window()
    info = _attach_info_spy(main_window)
    context = SimpleNamespace(main_window=main_window)

    refreshed = refresh_after_command(
        context,
        _result(ChangedState(epoch_changed=True)),
    )

    assert refreshed is True
    assert main_window.dataset_panel.update_calls == 0
    assert main_window.preprocess_panel.update_calls == 1
    assert main_window.training_panel.update_calls == 1
    assert main_window.evaluation_panel.update_calls == 0
    assert main_window.visualization_panel.update_calls == 1
    assert info.update_calls == 1
    assert main_window.agent_manager.refresh_calls == 1


def test_evaluation_change_refreshes_visualization_readiness():
    main_window = _main_window()
    info = _attach_info_spy(main_window)
    context = SimpleNamespace(main_window=main_window)

    refreshed = refresh_after_command(
        context,
        _result(ChangedState(evaluation_changed=True)),
    )

    assert refreshed is True
    assert main_window.dataset_panel.update_calls == 0
    assert main_window.preprocess_panel.update_calls == 0
    assert main_window.training_panel.update_calls == 0
    assert main_window.evaluation_panel.update_calls == 1
    assert main_window.visualization_panel.update_calls == 1
    assert info.update_calls == 1
    assert main_window.agent_manager.refresh_calls == 1


def test_no_state_change_does_not_refresh_ui():
    main_window = _main_window()
    info = _attach_info_spy(main_window)
    context = SimpleNamespace(main_window=main_window)

    refreshed = refresh_after_command(context, _result(ChangedState()))

    assert refreshed is False
    assert main_window.dataset_panel.update_calls == 0
    assert main_window.preprocess_panel.update_calls == 0
    assert main_window.training_panel.update_calls == 0
    assert main_window.evaluation_panel.update_calls == 0
    assert main_window.visualization_panel.update_calls == 0
    assert info.update_calls == 0
    assert main_window.agent_manager.refresh_calls == 0


def test_unknown_post_command_state_refreshes_every_workflow_panel():
    main_window = _main_window()
    info = _attach_info_spy(main_window)
    context = SimpleNamespace(main_window=main_window)

    refreshed = refresh_after_command(
        context,
        _result(ChangedState(error_changed=True, state_unknown=True)),
    )

    assert refreshed is True
    assert main_window.dataset_panel.update_calls == 1
    assert main_window.preprocess_panel.update_calls == 1
    assert main_window.training_panel.update_calls == 1
    assert main_window.evaluation_panel.update_calls == 1
    assert main_window.visualization_panel.update_calls == 1
    assert info.update_calls == 1
    assert main_window.agent_manager.refresh_calls == 1


def test_refresh_is_not_reentrant_for_same_main_window():
    main_window = _main_window()
    context = SimpleNamespace(main_window=main_window)
    nested_results = []

    class _RecursivePanel:
        update_calls = 0

        def update_panel(self) -> None:
            self.update_calls += 1
            nested_results.append(
                refresh_after_command(context, _result(ChangedState(raw_changed=True))),
            )

    main_window.dataset_panel = _RecursivePanel()

    refreshed = refresh_after_command(context, _result(ChangedState(raw_changed=True)))

    assert refreshed is True
    assert main_window.dataset_panel.update_calls == 1
    assert nested_results == [False]


def test_observer_refresh_is_suppressed_while_command_is_executing():
    main_window = _main_window()
    info = _attach_info_spy(main_window)
    panel = main_window.dataset_panel
    panel.main_window = main_window

    with suppress_observer_refresh_during_command(panel):
        refreshed = refresh_after_observer(panel, event_name="data_changed")

    assert refreshed is False
    assert main_window.dataset_panel.update_calls == 0
    assert main_window.preprocess_panel.update_calls == 0
    assert main_window.training_panel.update_calls == 0
    assert main_window.evaluation_panel.update_calls == 0
    assert main_window.visualization_panel.update_calls == 0
    assert info.update_calls == 0
    assert main_window.agent_manager.refresh_calls == 0


def test_observer_refresh_resumes_after_command_execution_scope():
    main_window = _main_window()
    info = _attach_info_spy(main_window)
    panel = main_window.dataset_panel
    panel.main_window = main_window

    with suppress_observer_refresh_during_command(panel):
        assert refresh_after_observer(panel, event_name="data_changed") is False

    refreshed = refresh_after_observer(panel, event_name="data_changed")

    assert refreshed is True
    assert main_window.dataset_panel.update_calls == 1
    assert main_window.preprocess_panel.update_calls == 1
    assert main_window.training_panel.update_calls == 1
    assert main_window.evaluation_panel.update_calls == 0
    assert main_window.visualization_panel.update_calls == 0
    assert info.update_calls == 1
    assert main_window.agent_manager.refresh_calls == 1


def test_nested_command_execution_scopes_keep_observer_refresh_suppressed():
    main_window = _main_window()
    info = _attach_info_spy(main_window)
    panel = main_window.dataset_panel
    panel.main_window = main_window

    with suppress_observer_refresh_during_command(panel):
        with suppress_observer_refresh_during_command(panel):
            assert refresh_after_observer(panel, event_name="data_changed") is False

        assert refresh_after_observer(panel, event_name="data_changed") is False

    assert main_window.dataset_panel.update_calls == 0
    assert main_window.preprocess_panel.update_calls == 0
    assert main_window.training_panel.update_calls == 0
    assert main_window.evaluation_panel.update_calls == 0
    assert main_window.visualization_panel.update_calls == 0
    assert info.update_calls == 0
    assert main_window.agent_manager.refresh_calls == 0


def test_terminal_training_publication_replays_once_after_outer_command_scope():
    main_window = _main_window()
    info = _attach_info_spy(main_window)
    panel = main_window.training_panel
    panel.main_window = main_window

    with suppress_observer_refresh_during_command(panel):
        with suppress_observer_refresh_during_command(panel):
            assert (
                refresh_after_observer(
                    panel,
                    event_name="training_terminal_published",
                )
                is False
            )
            assert (
                refresh_after_observer(
                    panel,
                    event_name="training_terminal_published",
                )
                is False
            )

        assert main_window.training_panel.update_calls == 0
        assert main_window.evaluation_panel.update_calls == 0
        assert main_window.visualization_panel.update_calls == 0

    assert main_window.training_panel.update_calls == 0
    assert main_window.training_panel.terminal_refresh_calls == 1
    assert main_window.evaluation_panel.update_calls == 1
    assert main_window.visualization_panel.update_calls == 1
    assert info.update_calls == 1
    assert main_window.agent_manager.refresh_calls == 1


def test_command_completion_coalesces_terminal_observer_and_changed_state():
    main_window = _main_window()
    info = _attach_info_spy(main_window)
    panel = main_window.training_panel
    panel.main_window = main_window

    assert begin_command_refresh_suppression(panel) is True
    assert (
        refresh_after_observer(
            panel,
            event_name="training_terminal_published",
        )
        is False
    )
    assert (
        refresh_after_observer(
            panel,
            event_name="training_terminal_published",
        )
        is False
    )

    refreshed = complete_command_refresh_suppression(
        panel,
        ChangedState(
            training_changed=True,
            evaluation_changed=True,
            visualization_changed=True,
        ).to_dict(),
    )

    assert refreshed is True
    assert main_window.training_panel.update_calls == 0
    assert main_window.training_panel.terminal_refresh_calls == 1
    assert main_window.evaluation_panel.update_calls == 1
    assert main_window.visualization_panel.update_calls == 1
    assert info.update_calls == 1
    assert main_window.agent_manager.refresh_calls == 1


def test_standalone_training_panel_uses_terminal_renderer_without_shell_slot():
    panel = _TrainingPanelSpy()
    panel.main_window = SimpleNamespace(
        agent_manager=None,
        update_info_panel=lambda: None,
    )

    refreshed = refresh_after_observer(
        panel,
        event_name="training_terminal_published",
    )

    assert refreshed is True
    assert panel.update_calls == 0
    assert panel.terminal_refresh_calls == 1


def test_deleted_saliency_owner_is_not_retained_or_replayed(qtbot):
    main_window = _main_window()
    lease_context = SimpleNamespace(main_window=main_window)
    callback_calls: list[str] = []
    panel = _QtPanelSpy(callback_calls)
    panel.main_window = main_window
    main_window.visualization_panel = panel
    panel_ref = ref(panel)
    main_window_id = id(main_window)

    def owner_deleted() -> bool:
        owner = panel_ref()
        return owner is not None and sip.isdeleted(owner)

    with suppress_observer_refresh_during_command(lease_context):
        assert refresh_after_observer(panel, event_name="saliency_changed") is False
        assert refresh_after_observer(panel, event_name="saliency_changed") is False
        pending = refresh_coordinator._DEFERRED_TERMINAL_REFRESHES[main_window_id]
        assert len(pending) == 1

        panel.deleteLater()
        qtbot.waitUntil(owner_deleted, timeout=1_000)
        main_window.visualization_panel = None
        del panel
        collect()
        assert panel_ref() is None

    assert callback_calls == []
    assert main_window_id not in refresh_coordinator._DEFERRED_TERMINAL_REFRESHES


def test_navigation_refreshes_selected_panel_and_shared_status():
    main_window = _main_window()
    info = _attach_info_spy(main_window)

    refreshed = refresh_after_navigation(main_window, 2)

    assert refreshed is True
    assert main_window.dataset_panel.update_calls == 0
    assert main_window.preprocess_panel.update_calls == 0
    assert main_window.training_panel.update_calls == 1
    assert main_window.evaluation_panel.update_calls == 0
    assert main_window.visualization_panel.update_calls == 0
    assert info.update_calls == 1
    assert main_window.agent_manager.refresh_calls == 1


def test_navigation_does_not_run_object_queries_during_active_ui_command():
    main_window = _main_window()
    info = _attach_info_spy(main_window)
    context = SimpleNamespace(main_window=main_window)

    with suppress_observer_refresh_during_command(context):
        refreshed = refresh_after_navigation(main_window, 2)

    assert refreshed is False
    assert main_window.training_panel.update_calls == 0
    assert info.update_calls == 0
    assert main_window.agent_manager.refresh_calls == 0


def test_navigation_refresh_is_not_reentrant_for_same_main_window():
    main_window = _main_window()
    nested_results = []

    class _RecursivePanel:
        def __init__(self) -> None:
            self.update_calls = 0

        def update_panel(self) -> None:
            self.update_calls += 1
            if self.update_calls == 1:
                nested_results.append(refresh_after_navigation(main_window, 2))

    panel = _RecursivePanel()
    main_window.training_panel = panel

    refreshed = refresh_after_navigation(main_window, 2)

    assert refreshed is True
    assert panel.update_calls == 1
    assert nested_results == [False]


def test_navigation_refresh_ignores_unknown_panel_index():
    main_window = _main_window()
    info = _attach_info_spy(main_window)

    refreshed = refresh_after_navigation(main_window, 99)

    assert refreshed is False
    assert main_window.dataset_panel.update_calls == 0
    assert main_window.preprocess_panel.update_calls == 0
    assert main_window.training_panel.update_calls == 0
    assert main_window.evaluation_panel.update_calls == 0
    assert main_window.visualization_panel.update_calls == 0
    assert info.update_calls == 0
    assert main_window.agent_manager.refresh_calls == 0


def test_observer_refreshes_source_panel_and_shared_status():
    main_window = _main_window()
    info = _attach_info_spy(main_window)
    panel = main_window.dataset_panel
    panel.main_window = main_window

    refreshed = refresh_after_observer(panel)

    assert refreshed is True
    assert main_window.dataset_panel.update_calls == 1
    assert main_window.preprocess_panel.update_calls == 0
    assert main_window.training_panel.update_calls == 0
    assert main_window.evaluation_panel.update_calls == 0
    assert main_window.visualization_panel.update_calls == 0
    assert info.update_calls == 1
    assert main_window.agent_manager.refresh_calls == 1


def test_data_changed_observer_uses_central_refresh_scope():
    main_window = _main_window()
    info = _attach_info_spy(main_window)
    panel = main_window.dataset_panel
    panel.main_window = main_window

    refreshed = refresh_after_observer(panel, event_name="data_changed")

    assert refreshed is True
    assert main_window.dataset_panel.update_calls == 1
    assert main_window.preprocess_panel.update_calls == 1
    assert main_window.training_panel.update_calls == 1
    assert main_window.evaluation_panel.update_calls == 0
    assert main_window.visualization_panel.update_calls == 0
    assert info.update_calls == 1
    assert main_window.agent_manager.refresh_calls == 1


def test_secondary_data_changed_observer_does_not_duplicate_central_scope():
    main_window = _main_window()
    info = _attach_info_spy(main_window)
    panel = main_window.preprocess_panel
    panel.main_window = main_window

    refreshed = refresh_after_observer(panel, event_name="data_changed")

    assert refreshed is False
    assert main_window.dataset_panel.update_calls == 0
    assert main_window.preprocess_panel.update_calls == 0
    assert main_window.training_panel.update_calls == 0
    assert main_window.evaluation_panel.update_calls == 0
    assert main_window.visualization_panel.update_calls == 0
    assert info.update_calls == 0
    assert main_window.agent_manager.refresh_calls == 0


def test_preprocess_changed_observer_uses_central_refresh_scope():
    main_window = _main_window()
    info = _attach_info_spy(main_window)
    panel = main_window.preprocess_panel
    panel.main_window = main_window

    refreshed = refresh_after_observer(panel, event_name="preprocess_changed")

    assert refreshed is True
    assert main_window.dataset_panel.update_calls == 0
    assert main_window.preprocess_panel.update_calls == 1
    assert main_window.training_panel.update_calls == 1
    assert main_window.evaluation_panel.update_calls == 0
    assert main_window.visualization_panel.update_calls == 1
    assert info.update_calls == 1
    assert main_window.agent_manager.refresh_calls == 1


def test_secondary_preprocess_changed_observer_does_not_duplicate_central_scope():
    main_window = _main_window()
    info = _attach_info_spy(main_window)
    panel = main_window.training_panel
    panel.main_window = main_window

    refreshed = refresh_after_observer(panel, event_name="preprocess_changed")

    assert refreshed is False
    assert main_window.dataset_panel.update_calls == 0
    assert main_window.preprocess_panel.update_calls == 0
    assert main_window.training_panel.update_calls == 0
    assert main_window.evaluation_panel.update_calls == 0
    assert main_window.visualization_panel.update_calls == 0
    assert info.update_calls == 0
    assert main_window.agent_manager.refresh_calls == 0


def test_training_lifecycle_observer_uses_training_owner_scope():
    main_window = _main_window()
    info = _attach_info_spy(main_window)
    panel = main_window.training_panel
    panel.main_window = main_window

    refreshed = refresh_after_observer(panel, event_name="training_stopped")

    assert refreshed is True
    assert main_window.dataset_panel.update_calls == 0
    assert main_window.preprocess_panel.update_calls == 0
    assert main_window.training_panel.update_calls == 1
    assert main_window.evaluation_panel.update_calls == 1
    assert main_window.visualization_panel.update_calls == 1
    assert info.update_calls == 1
    assert main_window.agent_manager.refresh_calls == 1


def test_training_updated_observer_does_not_fan_out_live_tick():
    main_window = _main_window()
    info = _attach_info_spy(main_window)
    panel = main_window.training_panel
    panel.main_window = main_window

    refreshed = refresh_after_observer(panel, event_name="training_updated")

    assert refreshed is False
    assert main_window.dataset_panel.update_calls == 0
    assert main_window.preprocess_panel.update_calls == 0
    assert main_window.training_panel.update_calls == 0
    assert main_window.evaluation_panel.update_calls == 0
    assert main_window.visualization_panel.update_calls == 0
    assert info.update_calls == 0
    assert main_window.agent_manager.refresh_calls == 0


def test_secondary_training_lifecycle_observer_does_not_duplicate_central_scope():
    main_window = _main_window()
    info = _attach_info_spy(main_window)
    panel = main_window.evaluation_panel
    panel.main_window = main_window

    refreshed = refresh_after_observer(panel, event_name="training_stopped")

    assert refreshed is False
    assert main_window.dataset_panel.update_calls == 0
    assert main_window.preprocess_panel.update_calls == 0
    assert main_window.training_panel.update_calls == 0
    assert main_window.evaluation_panel.update_calls == 0
    assert main_window.visualization_panel.update_calls == 0
    assert info.update_calls == 0
    assert main_window.agent_manager.refresh_calls == 0


def test_visualization_observer_uses_visualization_scope_from_helper_context():
    main_window = _main_window()
    info = _attach_info_spy(main_window)
    context = SimpleNamespace(
        main_window=main_window,
        panel=main_window.visualization_panel,
    )

    refreshed = refresh_after_observer(context, event_name="saliency_changed")

    assert refreshed is True
    assert main_window.dataset_panel.update_calls == 0
    assert main_window.preprocess_panel.update_calls == 0
    assert main_window.training_panel.update_calls == 0
    assert main_window.evaluation_panel.update_calls == 0
    assert main_window.visualization_panel.update_calls == 1
    assert info.update_calls == 1
    assert main_window.agent_manager.refresh_calls == 1


def test_terminal_analysis_publication_does_not_repeat_workflow_refreshes():
    main_window = _main_window()
    info = _attach_info_spy(main_window)
    panel = main_window.training_panel
    panel.main_window = main_window

    refreshed = refresh_after_observer(
        panel,
        event_name="training_analysis_published",
    )

    assert refreshed is True
    assert main_window.dataset_panel.update_calls == 0
    assert main_window.preprocess_panel.update_calls == 0
    assert main_window.training_panel.update_calls == 0
    assert main_window.evaluation_panel.update_calls == 0
    assert main_window.visualization_panel.update_calls == 0
    assert info.update_calls == 1
    assert main_window.agent_manager.refresh_calls == 1


def test_terminal_analysis_event_pair_refreshes_each_panel_once():
    main_window = _main_window()
    _attach_info_spy(main_window)
    training = main_window.training_panel
    training.main_window = main_window
    visualization = main_window.visualization_panel
    visualization.main_window = main_window

    assert (
        refresh_after_observer(
            training,
            event_name="training_analysis_published",
        )
        is True
    )
    assert (
        refresh_after_observer(
            visualization,
            event_name="saliency_changed",
        )
        is True
    )

    assert main_window.training_panel.update_calls == 0
    assert main_window.evaluation_panel.update_calls == 0
    assert main_window.visualization_panel.update_calls == 1


def test_secondary_visualization_observer_does_not_duplicate_central_scope():
    main_window = _main_window()
    info = _attach_info_spy(main_window)
    panel = main_window.evaluation_panel
    panel.main_window = main_window

    refreshed = refresh_after_observer(panel, event_name="montage_changed")

    assert refreshed is False
    assert main_window.dataset_panel.update_calls == 0
    assert main_window.preprocess_panel.update_calls == 0
    assert main_window.training_panel.update_calls == 0
    assert main_window.evaluation_panel.update_calls == 0
    assert main_window.visualization_panel.update_calls == 0
    assert info.update_calls == 0
    assert main_window.agent_manager.refresh_calls == 0


def test_unknown_observer_event_keeps_source_panel_scope():
    main_window = _main_window()
    info = _attach_info_spy(main_window)
    panel = main_window.dataset_panel
    panel.main_window = main_window

    refreshed = refresh_after_observer(panel, event_name="custom_event")

    assert refreshed is True
    assert main_window.dataset_panel.update_calls == 1
    assert main_window.preprocess_panel.update_calls == 0
    assert main_window.training_panel.update_calls == 0
    assert main_window.evaluation_panel.update_calls == 0
    assert main_window.visualization_panel.update_calls == 0
    assert info.update_calls == 1
    assert main_window.agent_manager.refresh_calls == 1


def test_refresh_panel_uses_safe_noarg_update_call():
    panel = _PanelSpy()

    refreshed = refresh_panel(panel)

    assert refreshed is True
    assert panel.update_calls == 1
