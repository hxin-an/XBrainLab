from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QWidget

from XBrainLab.ui.main_window import MainWindow


@pytest.fixture
def mock_study():
    return MagicMock()


@pytest.fixture
def main_window(mock_study, qtbot):
    # Patch init_panels and init_agent to avoid creating real widgets
    with (
        patch("XBrainLab.ui.main_window.MainWindow.init_panels"),
        patch("XBrainLab.ui.main_window.MainWindow.init_agent"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
    ):
        window = MainWindow(mock_study)

        # Manually attach mock panels
        window.dataset_panel = MagicMock(spec=QWidget)
        window.dataset_panel.update_panel = MagicMock()

        window.preprocess_panel = MagicMock(spec=QWidget)
        window.preprocess_panel.update_panel = MagicMock()

        window.training_panel = MagicMock(spec=QWidget)
        window.training_panel.update_panel = MagicMock()

        window.evaluation_panel = MagicMock(spec=QWidget)
        window.evaluation_panel.update_panel = MagicMock()

        window.visualization_panel = MagicMock(spec=QWidget)
        window.visualization_panel.update_panel = MagicMock()

        qtbot.addWidget(window)
        return window


def test_switch_page_updates_dataset_panel(main_window):
    """Test switching to Dataset panel (Index 0) calls update_panel."""
    main_window.switch_page(0)
    main_window.dataset_panel.update_panel.assert_called_once()


def test_switch_page_updates_preprocess_panel(main_window):
    """Test switching to Preprocess panel (Index 1) calls update_panel."""
    main_window.switch_page(1)
    main_window.preprocess_panel.update_panel.assert_called_once()


def test_switch_page_updates_training_panel(main_window):
    """Test switching to Training panel (Index 2) calls update_panel."""
    main_window.switch_page(2)
    main_window.training_panel.update_panel.assert_called_once()


def test_switch_page_updates_evaluation_panel(main_window):
    """Test switching to Evaluation panel (Index 3) calls update_panel."""
    main_window.switch_page(3)
    main_window.evaluation_panel.update_panel.assert_called_once()


def test_switch_page_updates_visualization_panel(main_window):
    """Test switching to Visualization panel (Index 4) calls update_panel."""
    main_window.switch_page(4)
    main_window.visualization_panel.update_panel.assert_called_once()


def test_switch_page_checks_only_active_nav_button(main_window):
    """Switching pages should keep nav button checked state in sync."""
    main_window.switch_page(3)

    checked_states = [btn.isChecked() for btn in main_window.nav_btns]

    assert checked_states == [False, False, False, True, False]


def test_switch_page_only_updates_target_panel(main_window):
    """Only the selected panel should be refreshed for a page switch."""
    panels = [
        main_window.dataset_panel,
        main_window.preprocess_panel,
        main_window.training_panel,
        main_window.evaluation_panel,
        main_window.visualization_panel,
    ]

    main_window.switch_page(2)

    main_window.training_panel.update_panel.assert_called_once()
    for panel in (p for p in panels if p is not main_window.training_panel):
        panel.update_panel.assert_not_called()


def test_switch_page_delegates_navigation_refresh(main_window):
    """Panel refresh scope should live in the refresh coordinator."""
    with patch("XBrainLab.ui.main_window.refresh_after_navigation") as refresh:
        main_window.switch_page(4)

    refresh.assert_called_once_with(main_window, 4)


def test_switch_page_status_uses_backend_state_when_agent_absent(main_window):
    """Main status bar should not claim no data after backend state has data."""
    result = SimpleNamespace(
        failed=False,
        diagnostics={
            "state": {
                "active_training": {"is_running": False},
                "evaluation": {"finished_runs": 0},
                "active_dataset": {
                    "has_datasets": False,
                    "has_epoch_data": False,
                    "has_preprocessed_data": False,
                    "has_raw_data": True,
                },
            },
        },
    )

    with patch(
        "XBrainLab.ui.main_window.execute_application_command",
        return_value=result,
    ) as execute:
        main_window.switch_page(0)

    execute.assert_called_once()
    assert main_window.statusBar().currentMessage() == (
        "EEG data loaded · Preprocess data"
    )


def test_update_info_panel_uses_info_service(main_window):
    """Shared refresh should update registered AggregateInfoPanel instances."""
    main_window.info_service = MagicMock()

    main_window.update_info_panel()

    main_window.info_service.notify_all.assert_called_once()


def test_main_window_delegates_info_refresh_to_coordinator(mock_study, qtbot):
    """Product MainWindow should not double-subscribe aggregate info refresh."""
    with (
        patch("XBrainLab.ui.main_window.MainWindow.init_panels"),
        patch("XBrainLab.ui.main_window.MainWindow.init_agent"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
    ):
        window = MainWindow(mock_study)

    qtbot.addWidget(window)
    assert window.info_service.study is mock_study
    assert window.info_service._observes_controller_events is False


def test_init_panels_uses_legacy_bootstrap_helper(mock_study, qtbot):
    """MainWindow should lazy-create workflow panels from the bootstrap bundle."""
    controllers = SimpleNamespace(
        dataset=object(),
        preprocess=object(),
        training=object(),
        evaluation=object(),
        visualization=object(),
    )
    loaded_classes = []

    with (
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
        patch("XBrainLab.ui.main_window.InfoPanelService"),
        patch(
            "XBrainLab.ui.main_window.get_legacy_workflow_controllers_for_panel_bootstrap",
            return_value=controllers,
        ) as bootstrap,
        patch(
            "XBrainLab.ui.main_window._load_panel_class",
            side_effect=lambda _module, class_name: (
                loaded_classes.append(class_name) or (lambda *args: QWidget())
            ),
        ) as load_panel_class,
    ):
        window = MainWindow(mock_study)
        assert loaded_classes == []
        window.switch_page(0)
        window.switch_page(2)

    qtbot.addWidget(window)
    bootstrap.assert_called_once_with(mock_study)
    mock_study.get_controller.assert_not_called()
    assert loaded_classes == ["DatasetPanel", "TrainingPanel"]
    assert window.stack.count() == 5
    assert load_panel_class.call_count == 2


def test_initial_panel_lazy_load_preserves_current_page(mock_study, qtbot):
    """Replacing the visible placeholder must not jump to the next panel."""
    controllers = SimpleNamespace(
        dataset=object(),
        preprocess=object(),
        training=object(),
        evaluation=object(),
        visualization=object(),
    )

    with (
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
        patch(
            "XBrainLab.ui.main_window.get_legacy_workflow_controllers_for_panel_bootstrap",
            return_value=controllers,
        ),
        patch(
            "XBrainLab.ui.main_window._load_panel_class",
            return_value=lambda *args: QWidget(),
        ),
    ):
        window = MainWindow(mock_study)
        assert window.stack.currentIndex() == 0
        window._load_initial_panel_if_alive()

    qtbot.addWidget(window)
    assert window.stack.currentIndex() == 0
    assert window.nav_btns[0].isChecked()


def test_default_startup_materializes_dataset_before_main_window_is_shown(
    mock_study,
    qtbot,
):
    """The splash phase should prepare Dataset before the main window appears."""
    controllers = SimpleNamespace(
        dataset=object(),
        preprocess=object(),
        training=object(),
        evaluation=object(),
        visualization=object(),
    )
    loaded_classes = []

    with (
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
        patch(
            "XBrainLab.ui.main_window.get_legacy_workflow_controllers_for_panel_bootstrap",
            return_value=controllers,
        ),
        patch(
            "XBrainLab.ui.main_window._load_panel_class",
            side_effect=lambda _module, class_name: (
                loaded_classes.append(class_name) or (lambda *args: QWidget())
            ),
        ),
    ):
        window = MainWindow(mock_study)

    qtbot.addWidget(window)

    assert loaded_classes == ["DatasetPanel"]
    assert window._loaded_panel_indices == {0}
    assert window.dataset_panel.__class__.__name__ != "_LazyPanelPlaceholder"
    assert window.stack.currentIndex() == 0
    assert window.nav_btns[0].isChecked()


def test_startup_prewarm_result_does_not_reload_dataset(mock_study, qtbot):
    """Background prewarm completion should not re-materialize Dataset."""
    controllers = SimpleNamespace(
        dataset=object(),
        preprocess=object(),
        training=object(),
        evaluation=object(),
        visualization=object(),
    )
    loaded_classes = []

    with (
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
        patch(
            "XBrainLab.ui.main_window.get_legacy_workflow_controllers_for_panel_bootstrap",
            return_value=controllers,
        ),
        patch(
            "XBrainLab.ui.main_window._load_panel_class",
            side_effect=lambda _module, class_name: (
                loaded_classes.append(class_name) or (lambda *args: QWidget())
            ),
        ),
    ):
        window = MainWindow(mock_study)

    qtbot.addWidget(window)
    window._on_startup_prewarm_result({"loaded": [], "failed": []})

    assert loaded_classes == ["DatasetPanel"]
    assert window._loaded_panel_indices == {0}


def test_agent_manager_is_lazy_until_ai_toggle(mock_study, qtbot):
    """The AI assistant stack should not import/init during MainWindow startup."""

    class _Signal:
        def connect(self, _callback):
            return None

    class _AgentManager:
        status_message_received = _Signal()

        def __init__(self, *args):
            self.chat_panel = None
            self.toggled = False
            self.closed = False

        def init_ui(self):
            return None

        def toggle(self):
            self.toggled = True

        def close(self):
            self.closed = True

    with (
        patch("XBrainLab.ui.main_window.MainWindow.init_panels"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
        patch(
            "XBrainLab.ui.main_window._load_agent_manager_class",
            return_value=_AgentManager,
        ) as load_agent_manager,
    ):
        window = MainWindow(mock_study)
        assert window.agent_manager is None
        load_agent_manager.assert_not_called()
        window.toggle_ai_dock()

    qtbot.addWidget(window)
    load_agent_manager.assert_called_once()
    assert window.agent_manager is not None
    assert window.agent_manager.toggled is True


def test_update_info_panel_keeps_legacy_direct_panel_fallback(main_window):
    """Older injected contexts without InfoPanelService can still update directly."""
    delattr(main_window, "info_service")
    main_window.info_panel = MagicMock()

    main_window.update_info_panel()

    main_window.info_panel.update_info.assert_called_once()


def test_switch_page_skips_panel_without_update_panel(mock_study, qtbot):
    """Panels without update_panel should not break navigation refresh."""
    with (
        patch("XBrainLab.ui.main_window.MainWindow.init_panels"),
        patch("XBrainLab.ui.main_window.MainWindow.init_agent"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
    ):
        window = MainWindow(mock_study)
        cast(Any, window).dataset_panel = QWidget()
        window.preprocess_panel = MagicMock(spec=QWidget)
        window.preprocess_panel.update_panel = MagicMock()
        window.training_panel = MagicMock(spec=QWidget)
        window.training_panel.update_panel = MagicMock()
        window.evaluation_panel = MagicMock(spec=QWidget)
        window.evaluation_panel.update_panel = MagicMock()
        window.visualization_panel = MagicMock(spec=QWidget)
        window.visualization_panel.update_panel = MagicMock()

        qtbot.addWidget(window)

        window.switch_page(0)

        assert window.nav_btns[0].isChecked()
