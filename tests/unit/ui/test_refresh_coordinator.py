"""Tests for command-result-driven UI refresh coordination."""

from __future__ import annotations

from types import SimpleNamespace

from XBrainLab.backend.application import ChangedState, CommandResult
from XBrainLab.ui.refresh_coordinator import refresh_after_command


class _PanelSpy:
    def __init__(self) -> None:
        self.update_calls = 0

    def update_panel(self) -> None:
        self.update_calls += 1


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
        training_panel=_PanelSpy(),
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
    assert main_window.evaluation_panel.update_calls == 0
    assert main_window.visualization_panel.update_calls == 0
    assert info.update_calls == 1
    assert main_window.agent_manager.refresh_calls == 1


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
