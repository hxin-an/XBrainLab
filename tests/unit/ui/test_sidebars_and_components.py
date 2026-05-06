"""Coverage tests for sidebar modules: preprocess, training, dataset, viz control."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QDialog, QMainWindow, QWidget


def _command_result(**diagnostics):
    from types import SimpleNamespace

    return SimpleNamespace(
        ok=True,
        failed=False,
        message="ok",
        diagnostics=diagnostics,
    )


def _make_panel_mock():
    p = MagicMock()
    p.controller = MagicMock()
    p.dataset_controller = MagicMock()
    # main_window must be a real QWidget so AggregateInfoPanel can use it as parent
    p.main_window = QMainWindow()
    p.update_panel = MagicMock()
    p.controller.is_locked.return_value = False
    p.controller.has_data.return_value = True
    p.controller.is_epoched.return_value = False
    return p


# ============ PreprocessSidebar ============


class TestPreprocessSidebar:
    @pytest.fixture
    def sidebar(self, qtbot):
        from XBrainLab.ui.panels.preprocess.sidebar import PreprocessSidebar

        panel = _make_panel_mock()
        panel.controller.get_preprocessed_data_list.return_value = []
        sb = PreprocessSidebar(panel)
        qtbot.addWidget(sb)
        return sb

    def test_creates(self, sidebar):
        assert isinstance(sidebar, QWidget)

    def test_update_sidebar(self, sidebar):
        sidebar.update_sidebar()

    def test_update_sidebar_prefers_backend_capabilities_over_stale_preprocessed_list(
        self,
        sidebar,
    ):
        from XBrainLab.backend.study import Study

        study = Study()
        raw = MagicMock()
        raw.get_filename.return_value = "sub-01_task-mi_raw.fif"
        study.data_manager.loaded_data_list = [raw]
        sidebar.panel.main_window.study = study
        sidebar.panel.controller.get_preprocessed_data_list.side_effect = (
            AssertionError("stale preprocessed list should not be read")
        )

        sidebar.update_sidebar()

        sidebar.panel.controller.get_preprocessed_data_list.assert_not_called()

    def test_check_lock_unlocked(self, sidebar):
        # check_lock returns False when NOT epoched (action is allowed)
        assert sidebar.check_lock() is False

    def test_check_lock_locked(self, sidebar):
        sidebar.panel.controller.is_epoched.return_value = True
        with patch("PyQt6.QtWidgets.QMessageBox.warning"):
            # check_lock returns True when epoched (action is blocked)
            assert sidebar.check_lock() is True

    def test_check_lock_prefers_backend_capability_over_stale_controller(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.study import Study

        study = Study()
        raw = MagicMock()
        raw.get_filename.return_value = "sub-01_task-mi_raw.fif"
        study.data_manager.loaded_data_list = [raw]
        sidebar.panel.main_window.study = study
        sidebar.panel.controller.is_epoched.return_value = True

        with patch.object(QMessageBox, "warning") as mock_warning:
            assert sidebar.check_lock() is False

        mock_warning.assert_not_called()

    def test_check_data_loaded_true(self, sidebar):
        assert sidebar.check_data_loaded() is True

    def test_check_data_loaded_false(self, sidebar):
        sidebar.panel.controller.has_data.return_value = False
        with patch("PyQt6.QtWidgets.QMessageBox.warning"):
            assert sidebar.check_data_loaded() is False

    def test_check_data_loaded_prefers_backend_capability_over_stale_controller(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.study import Study

        study = Study()
        raw = MagicMock()
        raw.get_filename.return_value = "sub-01_task-mi_raw.fif"
        study.data_manager.loaded_data_list = [raw]
        sidebar.panel.main_window.study = study
        sidebar.panel.controller.has_data.return_value = False

        with patch.object(QMessageBox, "warning") as mock_warning:
            assert sidebar.check_data_loaded() is True

        mock_warning.assert_not_called()

    def test_open_filtering_accepted(self, sidebar):
        with (
            patch("XBrainLab.ui.panels.preprocess.sidebar.FilteringDialog") as MockDlg,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = (1.0, 40.0, [50.0])
            sidebar.open_filtering()
            sidebar.panel.controller.apply_filter.assert_called_once()

    def test_open_resample_accepted(self, sidebar):
        with (
            patch("XBrainLab.ui.panels.preprocess.sidebar.ResampleDialog") as MockDlg,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = 256
            sidebar.open_resample()
            sidebar.panel.controller.apply_resample.assert_called_once()

    def test_open_rereference_accepted(self, sidebar):
        with (
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.RereferenceDialog"
            ) as MockDlg,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = ["Cz"]
            sidebar.open_rereference()
            sidebar.panel.controller.apply_rereference.assert_called_once()

    def test_open_rereference_uses_query_data_list_before_stale_controller(
        self,
        sidebar,
    ):
        from XBrainLab.backend.application import (
            PreprocessCommand,
            QueryStateCommand,
        )

        query_data = [MagicMock()]
        sidebar.panel.controller.get_preprocessed_data_list.side_effect = (
            AssertionError("stale preprocessed list should not be read")
        )

        def execute_for(_, command, refresh=True):
            if isinstance(command, QueryStateCommand):
                return _command_result(preprocessed_data_list=query_data)
            if isinstance(command, PreprocessCommand):
                return _command_result()
            raise AssertionError(f"unexpected command: {command!r}")

        with (
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.get_command_capability",
                return_value=SimpleNamespace(enabled=True, reasons=[]),
            ),
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.RereferenceDialog"
            ) as MockDlg,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command",
                side_effect=execute_for,
            ) as mock_execute,
            patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warning,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = ["Cz"]
            sidebar.open_rereference()

        mock_warning.assert_not_called()
        assert isinstance(mock_execute.call_args_list[0].args[1], QueryStateCommand)
        assert isinstance(mock_execute.call_args_list[1].args[1], PreprocessCommand)
        MockDlg.assert_called_once_with(sidebar, query_data)
        sidebar.panel.controller.get_preprocessed_data_list.assert_not_called()
        sidebar.panel.controller.apply_rereference.assert_not_called()

    def test_open_normalize_accepted(self, sidebar):
        with (
            patch("XBrainLab.ui.panels.preprocess.sidebar.NormalizeDialog") as MockDlg,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = "z-score"
            sidebar.open_normalize()
            sidebar.panel.controller.apply_normalization.assert_called_once()

    def test_open_normalize_service_success_uses_coordinator_refresh(self, sidebar):
        from XBrainLab.backend.application import PreprocessCommand

        with (
            patch("XBrainLab.ui.panels.preprocess.sidebar.NormalizeDialog") as MockDlg,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command",
                return_value=_command_result(),
            ) as mock_execute,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = "z-score"
            sidebar.open_normalize()

        assert isinstance(mock_execute.call_args.args[1], PreprocessCommand)
        sidebar.panel.controller.apply_normalization.assert_not_called()
        sidebar.panel.update_panel.assert_not_called()

    def test_open_epoching_accepted(self, sidebar):
        with (
            patch("XBrainLab.ui.panels.preprocess.sidebar.EpochingDialog") as MockDlg,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = (
                (None, 0),
                ["left", "right"],
                -0.5,
                1.0,
            )
            sidebar.panel.controller.apply_epoching.return_value = True
            sidebar.open_epoching()
            sidebar.panel.controller.apply_epoching.assert_called_once()

    def test_open_epoching_legacy_result_refreshes_shared_status(self, sidebar):
        sidebar.panel.main_window.update_info_panel = MagicMock()
        sidebar.panel.main_window.agent_manager = SimpleNamespace(
            refresh_backend_status=MagicMock(),
        )

        with (
            patch("XBrainLab.ui.panels.preprocess.sidebar.EpochingDialog") as MockDlg,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = (
                (None, 0),
                ["left", "right"],
                -0.5,
                1.0,
            )
            sidebar.panel.controller.apply_epoching.return_value = True
            sidebar.open_epoching()

        sidebar.panel.controller.apply_epoching.assert_called_once()
        sidebar.panel.main_window.update_info_panel.assert_called_once()
        (
            sidebar.panel.main_window.agent_manager.refresh_backend_status.assert_called_once()
        )

    def test_open_epoching_uses_epoch_capability_not_preprocess_block(
        self,
        sidebar,
    ):
        from XBrainLab.backend.application import (
            CommandName,
            CreateEpochCommand,
            QueryStateCommand,
        )

        def capability_for(_, command_name):
            if command_name == CommandName.CREATE_EPOCH:
                return SimpleNamespace(enabled=True, reasons=[])
            if command_name == CommandName.PREPROCESS:
                return SimpleNamespace(
                    enabled=False,
                    reasons=["Load raw data before preprocessing."],
                )
            return None

        sidebar.panel.controller.get_preprocessed_data_list.return_value = [MagicMock()]

        def execute_for(_, command, refresh=True):
            if isinstance(command, QueryStateCommand):
                return _command_result(preprocessed_data_list=[MagicMock()])
            return _command_result()

        with (
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.get_command_capability",
                side_effect=capability_for,
            ),
            patch("XBrainLab.ui.panels.preprocess.sidebar.EpochingDialog") as MockDlg,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command",
                side_effect=execute_for,
            ) as mock_execute,
            patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warning,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = (
                (None, 0),
                ["left", "right"],
                -0.5,
                1.0,
            )
            sidebar.open_epoching()

        mock_warning.assert_not_called()
        assert isinstance(mock_execute.call_args.args[1], CreateEpochCommand)
        sidebar.panel.controller.apply_epoching.assert_not_called()

    def test_open_epoching_uses_query_data_list_before_stale_controller(
        self,
        sidebar,
    ):
        from XBrainLab.backend.application import (
            CreateEpochCommand,
            QueryStateCommand,
        )

        query_data = [MagicMock()]
        sidebar.panel.controller.get_preprocessed_data_list.side_effect = (
            AssertionError("stale preprocessed list should not be read")
        )

        def execute_for(_, command, refresh=True):
            if isinstance(command, QueryStateCommand):
                return _command_result(preprocessed_data_list=query_data)
            if isinstance(command, CreateEpochCommand):
                return _command_result()
            raise AssertionError(f"unexpected command: {command!r}")

        with (
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.get_command_capability",
                return_value=SimpleNamespace(enabled=True, reasons=[]),
            ),
            patch("XBrainLab.ui.panels.preprocess.sidebar.EpochingDialog") as MockDlg,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command",
                side_effect=execute_for,
            ) as mock_execute,
            patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warning,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = (
                (None, 0),
                ["left", "right"],
                -0.5,
                1.0,
            )
            sidebar.open_epoching()

        mock_warning.assert_not_called()
        assert isinstance(mock_execute.call_args_list[0].args[1], QueryStateCommand)
        assert isinstance(mock_execute.call_args_list[1].args[1], CreateEpochCommand)
        MockDlg.assert_called_once_with(sidebar, query_data)
        sidebar.panel.controller.get_preprocessed_data_list.assert_not_called()
        sidebar.panel.controller.apply_epoching.assert_not_called()

    def test_open_epoching_refuses_real_study_query_none_controller_fallback(
        self,
        sidebar,
    ):
        from XBrainLab.backend.study import Study

        sidebar.panel.main_window.study = Study()
        sidebar.panel.controller.has_data.return_value = True
        sidebar.panel.controller.is_epoched.return_value = False
        sidebar.panel.controller.get_preprocessed_data_list.side_effect = (
            AssertionError("stale preprocessed list should not be read")
        )

        with (
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.get_command_capability",
                return_value=None,
            ),
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command",
                return_value=None,
            ),
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.EpochingDialog"
            ) as mock_dialog,
            patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warning,
        ):
            sidebar.open_epoching()

        mock_dialog.assert_not_called()
        sidebar.panel.controller.get_preprocessed_data_list.assert_not_called()
        mock_warning.assert_called_once()
        assert "could not safely complete" in mock_warning.call_args.args[2]

    def test_reset_preprocess(self, sidebar):
        from PyQt6.QtWidgets import QMessageBox

        with patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
        ):
            sidebar.reset_preprocess()
            sidebar.panel.controller.reset_preprocess.assert_called()

    def test_reset_preprocess_service_success_does_not_fallback_to_controller(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        with (
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command",
                return_value=_command_result(),
            ),
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            sidebar.reset_preprocess()

        sidebar.panel.controller.reset_preprocess.assert_not_called()
        sidebar.panel.update_panel.assert_not_called()

    def test_reset_preprocess_uses_reset_capability_when_preprocess_locked(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.study import Study

        study = Study()
        raw_data = MagicMock()
        raw_data.is_raw.return_value = True
        study.loaded_data_list = [raw_data]
        study.preprocessed_data_list = [MagicMock()]
        study.epoch_data = MagicMock()
        sidebar.panel.main_window.study = study
        sidebar.panel.controller.has_data.return_value = False

        with (
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ) as mock_question,
            patch.object(QMessageBox, "warning") as mock_warning,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command",
                return_value=_command_result(),
            ) as mock_execute,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            sidebar.reset_preprocess()

        mock_question.assert_called_once()
        mock_warning.assert_not_called()
        from XBrainLab.backend.application import ResetPreprocessCommand

        assert isinstance(mock_execute.call_args.args[1], ResetPreprocessCommand)
        sidebar.panel.controller.reset_preprocess.assert_not_called()
        sidebar.panel.update_panel.assert_not_called()

    def test_reset_preprocess_blocked_by_reset_capability_before_confirm(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.study import Study

        sidebar.panel.main_window.study = Study()
        sidebar.panel.controller.has_data.return_value = True

        with (
            patch.object(QMessageBox, "question") as mock_question,
            patch.object(QMessageBox, "warning") as mock_warning,
        ):
            sidebar.reset_preprocess()

        mock_question.assert_not_called()
        mock_warning.assert_called_once_with(
            sidebar,
            "Reset Blocked",
            "Load raw data before resetting preprocessing.",
        )
        sidebar.panel.controller.reset_preprocess.assert_not_called()

    def test_reset_preprocess_refuses_real_study_controller_fallback(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.study import Study

        study = Study()
        raw_data = MagicMock()
        raw_data.is_raw.return_value = True
        study.loaded_data_list = [raw_data]
        sidebar.panel.main_window.study = study
        sidebar.panel.controller.has_data.return_value = True

        with (
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command",
                return_value=None,
            ),
            patch.object(QMessageBox, "warning") as mock_warning,
            patch.object(QMessageBox, "critical") as mock_critical,
        ):
            sidebar.reset_preprocess()

        sidebar.panel.controller.reset_preprocess.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Reset Blocked"
        mock_critical.assert_not_called()
        visible_message = mock_warning.call_args.args[2]
        assert "could not safely complete" in visible_message
        assert "refusing controller fallback" not in visible_message
        assert "ApplicationService" not in visible_message


# ============ TrainingSidebar ============


class TestTrainingSidebar:
    @pytest.fixture
    def sidebar(self, qtbot):
        from XBrainLab.ui.panels.training.sidebar import TrainingSidebar

        panel = _make_panel_mock()
        panel.controller.has_datasets.return_value = False
        panel.controller.has_model.return_value = False
        panel.controller.has_training_option.return_value = False
        panel.controller.is_training.return_value = False
        sb = TrainingSidebar(panel)
        qtbot.addWidget(sb)
        return sb

    def test_creates(self, sidebar):
        assert isinstance(sidebar, QWidget)

    def test_check_ready_to_train_not_ready(self, sidebar):
        result = sidebar.check_ready_to_train()
        # Without datasets/model/option, not ready
        assert result is False or result is None

    def test_update_info_no_crash(self, sidebar):
        sidebar.update_info()  # smoke test: should not raise

    def test_split_data_accepted(self, sidebar):
        sidebar.panel.controller.has_data = MagicMock(return_value=True)
        sidebar.panel.dataset_controller.has_data.return_value = True
        sidebar.panel.dataset_controller.get_epoch_data.return_value = MagicMock()
        with patch(
            "XBrainLab.ui.panels.training.sidebar.DataSplittingDialog"
        ) as MockDlg:
            MockDlg.return_value.exec.return_value = QDialog.DialogCode.Accepted
            MockDlg.return_value.get_result.return_value = MagicMock()
            sidebar.split_data()

    def test_split_data_service_success_does_not_fallback_to_controller(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.application import (
            ClearDatasetsCommand,
            GenerateDatasetCommand,
            QueryStateCommand,
        )

        generator = MagicMock()
        sidebar.panel.controller.has_data = MagicMock(return_value=True)
        sidebar.panel.dataset_controller.has_data.return_value = True
        sidebar.panel.dataset_controller.get_epoch_data.return_value = MagicMock()
        sidebar.panel.controller.has_datasets.return_value = True
        sidebar.panel.controller.get_trainer.return_value = MagicMock()

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.DataSplittingDialog"
            ) as MockDlg,
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                return_value=_command_result(),
            ) as mock_execute,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = QDialog.DialogCode.Accepted
            MockDlg.return_value.get_result.return_value = generator
            sidebar.split_data()

        commands = [call.args[1] for call in mock_execute.call_args_list]
        assert isinstance(commands[0], QueryStateCommand)
        split_commands = [
            command
            for command in commands
            if not isinstance(command, QueryStateCommand)
        ]
        assert isinstance(split_commands[0], ClearDatasetsCommand)
        assert isinstance(split_commands[1], GenerateDatasetCommand)
        sidebar.panel.controller.clean_datasets.assert_not_called()
        sidebar.panel.controller.apply_data_splitting.assert_not_called()

    def test_split_data_uses_backend_generate_capability_before_dialog(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.study import Study

        sidebar.panel.main_window.study = Study()
        sidebar.panel.controller.get_loaded_data_list.return_value = [MagicMock()]
        sidebar.panel.controller.get_epoch_data.return_value = MagicMock()
        sidebar.panel.controller.is_training.return_value = False

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.DataSplittingDialog"
            ) as mock_dialog,
            patch.object(QMessageBox, "warning") as mock_warning,
        ):
            sidebar.split_data()

        mock_dialog.assert_not_called()
        mock_warning.assert_called_once_with(
            sidebar,
            "Data Splitting Blocked",
            "Create epochs before generating datasets.",
        )

    def test_split_data_allows_backend_replacement_boundary(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.application import (
            ClearDatasetsCommand,
            GenerateDatasetCommand,
            QueryStateCommand,
        )
        from XBrainLab.backend.study import Study

        study = Study()
        raw = MagicMock()
        raw.is_raw.return_value = True
        study.data_manager.loaded_data_list = [raw]
        study.data_manager.preprocessed_data_list = [raw]
        study.data_manager.epoch_data = MagicMock()
        study.data_manager.datasets = [MagicMock()]
        sidebar.panel.main_window.study = study
        sidebar.panel.controller.has_datasets.return_value = True
        sidebar.panel.controller.get_trainer.return_value = None
        generator = MagicMock()

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.DataSplittingDialog"
            ) as mock_dialog,
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                return_value=_command_result(),
            ) as mock_execute,
            patch.object(QMessageBox, "warning") as mock_warning,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            mock_dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            mock_dialog.return_value.get_result.return_value = generator
            sidebar.split_data()

        mock_warning.assert_not_called()
        commands = [call.args[1] for call in mock_execute.call_args_list]
        assert isinstance(commands[0], QueryStateCommand)
        split_commands = [
            command
            for command in commands
            if not isinstance(command, QueryStateCommand)
        ]
        assert isinstance(split_commands[0], ClearDatasetsCommand)
        assert isinstance(split_commands[1], GenerateDatasetCommand)

    def test_split_data_uses_backend_replacement_boundary_when_controller_stale(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.application import (
            ClearDatasetsCommand,
            GenerateDatasetCommand,
            QueryStateCommand,
        )
        from XBrainLab.backend.study import Study

        study = Study()
        raw = MagicMock()
        raw.is_raw.return_value = True
        study.data_manager.loaded_data_list = [raw]
        study.data_manager.preprocessed_data_list = [raw]
        study.data_manager.epoch_data = MagicMock()
        study.data_manager.datasets = [MagicMock()]
        sidebar.panel.main_window.study = study
        sidebar.panel.controller.has_datasets.return_value = False
        sidebar.panel.controller.get_trainer.return_value = None
        generator = MagicMock()

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.DataSplittingDialog"
            ) as mock_dialog,
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ) as mock_question,
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                return_value=_command_result(),
            ) as mock_execute,
            patch.object(QMessageBox, "warning") as mock_warning,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            mock_dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            mock_dialog.return_value.get_result.return_value = generator
            sidebar.split_data()

        mock_warning.assert_not_called()
        mock_question.assert_called_once()
        commands = [call.args[1] for call in mock_execute.call_args_list]
        assert isinstance(commands[0], QueryStateCommand)
        split_commands = [
            command
            for command in commands
            if not isinstance(command, QueryStateCommand)
        ]
        assert isinstance(split_commands[0], ClearDatasetsCommand)
        assert isinstance(split_commands[1], GenerateDatasetCommand)
        sidebar.panel.controller.clean_datasets.assert_not_called()
        sidebar.panel.controller.apply_data_splitting.assert_not_called()

    def test_split_data_passes_service_epoch_context_to_dialog(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.application import (
            GenerateDatasetCommand,
            QueryStateCommand,
        )
        from XBrainLab.backend.study import Study

        study = Study()
        raw = MagicMock()
        raw.is_raw.return_value = True
        study.data_manager.loaded_data_list = [raw]
        study.data_manager.preprocessed_data_list = [raw]
        study.data_manager.epoch_data = MagicMock(name="service_epoch_data")
        study.data_manager.dataset_generator = MagicMock(name="service_generator")
        sidebar.panel.main_window.study = study
        sidebar.panel.controller.get_epoch_data.side_effect = AssertionError(
            "split dialog context should come from QueryStateCommand",
        )
        sidebar.panel.controller.get_dataset_generator.side_effect = AssertionError(
            "split dialog generator should come from QueryStateCommand",
        )
        generator = MagicMock()

        query_result = _command_result(
            payload_type="dataset_generation_context",
            epoch_available=True,
            generator_exists=True,
            epoch_data=study.data_manager.epoch_data,
            dataset_generator=study.data_manager.dataset_generator,
        )

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.DataSplittingDialog"
            ) as mock_dialog,
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                side_effect=[query_result, _command_result()],
            ) as mock_execute,
            patch.object(QMessageBox, "warning") as mock_warning,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            mock_dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            mock_dialog.return_value.get_result.return_value = generator
            sidebar.split_data()

        mock_warning.assert_not_called()
        assert (
            mock_dialog.call_args.kwargs["epoch_data"] is study.data_manager.epoch_data
        )
        assert (
            mock_dialog.call_args.kwargs["dataset_generator"]
            is study.data_manager.dataset_generator
        )
        commands = [call.args[1] for call in mock_execute.call_args_list]
        assert isinstance(commands[0], QueryStateCommand)
        assert commands[0].query == "dataset_generation_context"
        assert commands[0].include_objects is True
        assert isinstance(commands[1], GenerateDatasetCommand)

    def test_select_model_accepted(self, sidebar):
        sidebar.panel.controller.is_training.return_value = False
        mock_holder = MagicMock()
        mock_holder.target_model.__name__ = "EEGNet"
        sidebar.panel.controller.get_model_holder.return_value = mock_holder
        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.ModelSelectionDialog"
            ) as MockDlg,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_result.return_value = mock_holder
            sidebar.select_model()
            sidebar.panel.controller.set_model_holder.assert_called_once()

    def test_select_model_service_success_does_not_read_stale_controller(
        self,
        sidebar,
    ):
        from XBrainLab.backend.application import ConfigureTrainingCommand

        sidebar.panel.controller.is_training.return_value = False
        sidebar.panel.controller.get_model_holder.return_value = None
        mock_holder = MagicMock()
        mock_holder.target_model.__name__ = "EEGNet"
        mock_holder.model_params_map = {"channels": 8}
        mock_holder.pretrained_weight_path = None

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.ModelSelectionDialog"
            ) as mock_dialog,
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                return_value=_command_result(),
            ) as mock_execute,
            patch("PyQt6.QtWidgets.QMessageBox.information") as mock_info,
            patch("PyQt6.QtWidgets.QMessageBox.critical") as mock_critical,
        ):
            mock_dialog.return_value.exec.return_value = True
            mock_dialog.return_value.get_result.return_value = mock_holder
            sidebar.select_model()

        command = mock_execute.call_args.args[1]
        assert isinstance(command, ConfigureTrainingCommand)
        assert command.model_name == "EEGNet"
        sidebar.panel.controller.set_model_holder.assert_not_called()
        sidebar.panel.controller.get_model_holder.assert_not_called()
        mock_critical.assert_not_called()
        mock_info.assert_called_once_with(sidebar, "Success", "Model selected: EEGNet")

    def test_select_model_uses_backend_configure_capability_before_dialog(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.study import Study

        study = Study()
        trainer = MagicMock()
        trainer.is_running.return_value = True
        study.training_manager.trainer = trainer
        sidebar.panel.main_window.study = study
        sidebar.panel.controller.is_training.return_value = False

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.ModelSelectionDialog"
            ) as mock_dialog,
            patch.object(QMessageBox, "warning") as mock_warning,
        ):
            sidebar.select_model()

        mock_dialog.assert_not_called()
        mock_warning.assert_called_once_with(
            sidebar,
            "Training Configuration Blocked",
            "Stop training before changing training configuration.",
        )

    def test_on_training_started_disables_buttons(self, sidebar):
        sidebar.on_training_started()
        # After training starts, stop button or UI state should update
        # Verify the method runs without error
        assert isinstance(sidebar, QWidget)

    def test_on_training_stopped_enables_buttons(self, sidebar):
        sidebar.on_training_stopped()
        # After training stops, UI state should update
        assert isinstance(sidebar, QWidget)

    def test_stop_training(self, sidebar):
        sidebar.panel.controller.is_training.return_value = True
        sidebar.stop_training()
        sidebar.panel.controller.stop_training.assert_called()

    def test_stop_training_uses_backend_capability_when_controller_stale(
        self,
        sidebar,
    ):
        from XBrainLab.backend.application import StopTrainingCommand
        from XBrainLab.backend.study import Study

        study = Study()
        trainer = MagicMock()
        trainer.is_running.return_value = True
        study.training_manager.trainer = trainer
        sidebar.panel.main_window.study = study
        sidebar.panel.controller.is_training.return_value = False

        with patch(
            "XBrainLab.ui.panels.training.sidebar.execute_application_command",
            return_value=_command_result(),
        ) as mock_execute:
            sidebar.stop_training()

        assert isinstance(mock_execute.call_args.args[1], StopTrainingCommand)
        sidebar.panel.controller.stop_training.assert_not_called()
        assert sidebar.btn_stop.isEnabled() is False

    def test_stop_training_refuses_real_study_controller_fallback(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.study import Study

        study = Study()
        trainer = MagicMock()
        trainer.is_running.return_value = True
        study.training_manager.trainer = trainer
        sidebar.panel.main_window.study = study
        sidebar.panel.controller.is_training.return_value = True

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                return_value=None,
            ),
            patch.object(QMessageBox, "warning") as mock_warning,
        ):
            sidebar.stop_training()

        sidebar.panel.controller.stop_training.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Stop Training Blocked"
        assert "could not safely complete" in mock_warning.call_args.args[2]

    def test_stop_training_blocked_by_backend_capability_before_command(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.study import Study

        sidebar.panel.main_window.study = Study()
        sidebar.panel.controller.is_training.return_value = True

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
            ) as mock_execute,
            patch.object(QMessageBox, "warning") as mock_warning,
        ):
            sidebar.stop_training()

        mock_execute.assert_not_called()
        mock_warning.assert_called_once_with(
            sidebar,
            "Stop Training Blocked",
            "No training run is active.",
        )
        sidebar.panel.controller.stop_training.assert_not_called()

    def test_clear_history(self, sidebar):
        from PyQt6.QtWidgets import QMessageBox

        with patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
        ):
            sidebar.clear_history()
            sidebar.panel.controller.clear_history.assert_called()

    def test_clear_history_service_success_does_not_fallback_to_controller(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.application import ClearTrainingHistoryCommand

        with (
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                return_value=_command_result(),
            ) as mock_execute,
        ):
            sidebar.clear_history()

        assert isinstance(mock_execute.call_args.args[1], ClearTrainingHistoryCommand)
        sidebar.panel.controller.clear_history.assert_not_called()

    def test_clear_history_uses_backend_capability_before_confirm(self, sidebar):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.study import Study

        sidebar.panel.main_window.study = Study()
        sidebar.panel.controller.is_training.return_value = False

        with (
            patch.object(QMessageBox, "question") as mock_question,
            patch.object(QMessageBox, "warning") as mock_warning,
        ):
            sidebar.clear_history()

        mock_question.assert_not_called()
        mock_warning.assert_called_once_with(
            sidebar,
            "Clear History Blocked",
            "No training history is available to clear.",
        )
        sidebar.panel.controller.clear_history.assert_not_called()

    def test_clear_history_refuses_real_study_controller_fallback(self, sidebar):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.application.capabilities import CommandCapability
        from XBrainLab.backend.study import Study

        sidebar.panel.main_window.study = Study()
        sidebar.panel.controller.is_training.return_value = False

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_command_capability",
                return_value=CommandCapability(
                    command_name="clear_training_history",
                    enabled=True,
                    destructive=True,
                    confirmation_required=True,
                ),
            ),
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                return_value=None,
            ),
            patch.object(QMessageBox, "warning") as mock_warning,
        ):
            sidebar.clear_history()

        sidebar.panel.controller.clear_history.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Clear History Blocked"
        assert "could not safely complete" in mock_warning.call_args.args[2]

    def test_training_setting_while_training(self, sidebar):
        sidebar.panel.controller.is_training.return_value = True
        with patch("PyQt6.QtWidgets.QMessageBox.warning"):
            sidebar.training_setting()

    def test_training_setting_accepted(self, sidebar):
        sidebar.panel.controller.is_training.return_value = False
        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.TrainingSettingDialog"
            ) as MockDlg,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_result.return_value = MagicMock()
            sidebar.training_setting()
            sidebar.panel.controller.set_training_option.assert_called_once()

    def test_training_setting_uses_state_snapshot_defaults_before_stale_controller(
        self,
        sidebar,
    ):
        from XBrainLab.backend.application import (
            ConfigureTrainingCommand,
            QueryStateCommand,
        )
        from XBrainLab.ui.dialogs.training.training_setting_dialog import (
            TrainingSettingDialog,
        )

        sidebar.panel.controller.is_training.return_value = False
        sidebar.panel.controller.get_training_option.side_effect = AssertionError(
            "stale controller option should not be read",
        )
        query_result = _command_result(
            state={
                "training": {
                    "training_option": {
                        "epoch": 7,
                        "batch_size": 16,
                        "learning_rate": 0.002,
                        "repeat": 3,
                        "device": "cpu",
                        "optimizer": "Adam",
                        "checkpoint_epoch": 2,
                        "output_dir": "./snapshot-output",
                    },
                },
            },
        )
        save_result = _command_result()
        option = SimpleNamespace(
            epoch=7,
            bs=16,
            lr=0.002,
            repeat_num=3,
            use_cpu=True,
            gpu_idx=None,
            optim=None,
            optim_params={},
            checkpoint_epoch=2,
            output_dir="./snapshot-output",
            evaluation_option=SimpleNamespace(value="test_acc"),
        )

        def accept_dialog(dialog):
            assert dialog.epoch_entry.text() == "7"
            assert dialog.bs_entry.text() == "16"
            assert dialog.lr_entry.text() == "0.002"
            assert dialog.repeat_entry.text() == "3"
            assert dialog.output_dir_label.text() == "./snapshot-output"
            return QDialog.DialogCode.Accepted

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                side_effect=[query_result, save_result],
            ) as mock_execute,
            patch.object(
                TrainingSettingDialog,
                "exec",
                new=accept_dialog,
            ),
            patch.object(
                TrainingSettingDialog,
                "get_result",
                return_value=option,
            ),
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            sidebar.training_setting()

        sidebar.panel.controller.get_training_option.assert_not_called()
        commands = [call.args[1] for call in mock_execute.call_args_list]
        assert isinstance(commands[0], QueryStateCommand)
        assert isinstance(commands[1], ConfigureTrainingCommand)
        sidebar.panel.controller.set_training_option.assert_not_called()

    def test_training_setting_uses_backend_configure_capability_before_dialog(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.study import Study

        study = Study()
        trainer = MagicMock()
        trainer.is_running.return_value = True
        study.training_manager.trainer = trainer
        sidebar.panel.main_window.study = study
        sidebar.panel.controller.is_training.return_value = False

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.TrainingSettingDialog"
            ) as mock_dialog,
            patch.object(QMessageBox, "warning") as mock_warning,
        ):
            sidebar.training_setting()

        mock_dialog.assert_not_called()
        mock_warning.assert_called_once_with(
            sidebar,
            "Training Configuration Blocked",
            "Stop training before changing training configuration.",
        )

    def test_start_training_ui_action(self, sidebar):
        sidebar.panel.controller.is_training.return_value = False
        sidebar.start_training_ui_action()
        sidebar.panel.controller.start_training.assert_called_once()

    def test_start_training_requires_confirmation_for_long_running_command(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        capability = SimpleNamespace(
            enabled=True,
            reasons=[],
            requires_confirmation=True,
            confirmation_required=False,
        )

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_command_capability",
                return_value=capability,
            ),
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.No,
            ) as mock_question,
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
            ) as mock_execute,
        ):
            sidebar.start_training_ui_action()

        mock_question.assert_called_once()
        mock_execute.assert_not_called()
        sidebar.panel.controller.start_training.assert_not_called()

    def test_start_training_service_success_does_not_fallback_to_controller(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.application import TrainCommand

        capability = SimpleNamespace(
            enabled=True,
            reasons=[],
            requires_confirmation=True,
            confirmation_required=False,
        )

        sidebar.panel.controller.is_training.return_value = False
        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_command_capability",
                return_value=capability,
            ),
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                return_value=_command_result(),
            ) as mock_execute,
        ):
            sidebar.start_training_ui_action()

        assert isinstance(mock_execute.call_args.args[1], TrainCommand)
        assert mock_execute.call_args.args[1].confirmed is True
        sidebar.panel.controller.start_training.assert_not_called()

    def test_start_training_prefers_backend_capability_over_stale_controller(
        self,
        sidebar,
    ):
        from XBrainLab.backend.application import TrainCommand

        capability = SimpleNamespace(
            enabled=True,
            reasons=[],
            requires_confirmation=False,
            confirmation_required=False,
        )

        sidebar.panel.controller.is_training.return_value = True
        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_command_capability",
                return_value=capability,
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                return_value=_command_result(),
            ) as mock_execute,
            patch("PyQt6.QtWidgets.QMessageBox.critical") as mock_critical,
        ):
            sidebar.start_training_ui_action()

        assert isinstance(mock_execute.call_args.args[1], TrainCommand)
        sidebar.panel.controller.start_training.assert_not_called()
        mock_critical.assert_not_called()

    def test_start_training_service_success_uses_coordinator_for_readiness(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        capability = SimpleNamespace(
            enabled=True,
            reasons=[],
            requires_confirmation=True,
            confirmation_required=False,
        )

        sidebar.panel.controller.is_training.return_value = False
        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_command_capability",
                return_value=capability,
            ),
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                return_value=_command_result(),
            ),
            patch.object(sidebar, "check_ready_to_train") as mock_check_ready,
        ):
            sidebar.start_training_ui_action()

        mock_check_ready.assert_not_called()

    def test_start_training_error(self, sidebar):
        sidebar.panel.controller.is_training.return_value = False
        sidebar.panel.controller.start_training.side_effect = RuntimeError("fail")
        with patch("PyQt6.QtWidgets.QMessageBox.critical"):
            sidebar.start_training_ui_action()

    def test_split_data_no_data(self, sidebar):
        sidebar.panel.controller.get_loaded_data_list.return_value = []
        with patch("PyQt6.QtWidgets.QMessageBox.warning"):
            sidebar.split_data()

    def test_split_data_no_epoch(self, sidebar):
        sidebar.panel.controller.get_loaded_data_list.return_value = [MagicMock()]
        sidebar.panel.controller.get_epoch_data.return_value = None
        with patch("PyQt6.QtWidgets.QMessageBox.warning"):
            sidebar.split_data()

    def test_split_data_while_training(self, sidebar):
        sidebar.panel.controller.get_loaded_data_list.return_value = [MagicMock()]
        sidebar.panel.controller.get_epoch_data.return_value = MagicMock()
        sidebar.panel.controller.is_training.return_value = True
        with patch("PyQt6.QtWidgets.QMessageBox.warning"):
            sidebar.split_data()

    def test_clear_history_while_training(self, sidebar):
        sidebar.panel.controller.is_training.return_value = True
        with patch("PyQt6.QtWidgets.QMessageBox.warning"):
            sidebar.clear_history()


# ============ DatasetSidebar ============


class TestDatasetSidebar:
    @pytest.fixture
    def sidebar(self, qtbot):
        from XBrainLab.ui.panels.dataset.sidebar import DatasetSidebar

        panel = _make_panel_mock()
        panel.action_handler = MagicMock()
        panel.controller.get_loaded_data_list.return_value = []
        sb = DatasetSidebar(panel)
        qtbot.addWidget(sb)
        return sb

    def test_creates(self, sidebar):
        assert isinstance(sidebar, QWidget)

    def test_update_sidebar(self, sidebar):
        sidebar.update_sidebar()

    def test_update_sidebar_uses_backend_import_label_capability(self, qtbot):
        from XBrainLab.backend.study import Study
        from XBrainLab.ui.panels.dataset.sidebar import DatasetSidebar

        panel = _make_panel_mock()
        panel.main_window.study = Study()
        panel.controller.has_data.return_value = True
        panel.controller.is_locked.return_value = False
        sb = DatasetSidebar(panel)
        qtbot.addWidget(sb)

        sb.update_sidebar()

        assert not sb.import_label_btn.isEnabled()
        assert "Load raw data before attaching labels." in (
            sb.import_label_btn.toolTip()
        )

    def test_update_sidebar_uses_backend_smart_parse_capability(self, qtbot):
        from XBrainLab.backend.study import Study
        from XBrainLab.ui.panels.dataset.sidebar import DatasetSidebar

        panel = _make_panel_mock()
        panel.main_window.study = Study()
        panel.controller.is_locked.return_value = False
        sb = DatasetSidebar(panel)
        qtbot.addWidget(sb)

        sb.update_sidebar()

        assert not sb.smart_parse_btn.isEnabled()
        assert "Load raw data before applying smart parse." in (
            sb.smart_parse_btn.toolTip()
        )

    def test_update_sidebar_prefers_backend_capabilities_over_stale_lock(
        self,
        qtbot,
    ):
        from XBrainLab.backend.study import Study
        from XBrainLab.ui.panels.dataset.sidebar import DatasetSidebar

        study = Study()
        raw = MagicMock()
        raw.get_filename.return_value = "sub-01_task-mi_raw.fif"
        study.data_manager.loaded_data_list = [raw]
        panel = _make_panel_mock()
        panel.main_window.study = study
        panel.controller.is_locked.return_value = True
        sb = DatasetSidebar(panel)
        qtbot.addWidget(sb)

        sb.update_sidebar()

        assert sb.import_btn.toolTip() == "Scan, preview, validate, and apply EEG data"
        assert sb.import_folder_btn.toolTip() == (
            "Scan a folder or BIDS root, then preview and confirm it"
        )
        assert sb.reload_recipe_btn.toolTip() == (
            "Review a saved import recipe before applying it"
        )
        assert sb.smart_parse_btn.isEnabled()
        assert sb.smart_parse_btn.toolTip() == (
            "Auto-extract Subject/Session from filenames"
        )
        panel.controller.is_locked.assert_not_called()
        panel.controller.has_data.assert_not_called()

    def test_open_channel_selection_uses_backend_preprocess_capability(self, qtbot):
        from XBrainLab.backend.study import Study
        from XBrainLab.ui.panels.dataset.sidebar import DatasetSidebar

        panel = _make_panel_mock()
        panel.main_window.study = Study()
        panel.controller.has_data.return_value = True
        panel.controller.is_locked.return_value = False
        panel.controller.get_loaded_data_list.return_value = [MagicMock()]
        sb = DatasetSidebar(panel)
        qtbot.addWidget(sb)

        with (
            patch(
                "XBrainLab.ui.panels.dataset.sidebar.ChannelSelectionDialog",
            ) as mock_dialog,
            patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warning,
        ):
            sb.open_channel_selection()

        mock_dialog.assert_not_called()
        mock_warning.assert_called_once()
        assert "Load raw data before preprocessing." in mock_warning.call_args.args[2]

    def test_open_channel_selection_prefers_backend_capability_over_stale_controller(
        self,
        qtbot,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.application import PreprocessCommand
        from XBrainLab.backend.study import Study
        from XBrainLab.ui.panels.dataset.sidebar import DatasetSidebar

        study = Study()
        raw = MagicMock()
        raw.get_filename.return_value = "sub-01_task-mi_raw.fif"
        study.data_manager.loaded_data_list = [raw]
        panel = _make_panel_mock()
        panel.main_window.study = study
        panel.controller.has_data.return_value = False
        panel.controller.is_locked.return_value = True
        panel.controller.get_loaded_data_list.return_value = [raw]
        sb = DatasetSidebar(panel)
        qtbot.addWidget(sb)

        with (
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch(
                "XBrainLab.ui.panels.dataset.sidebar.ChannelSelectionDialog",
            ) as mock_dialog,
            patch(
                "XBrainLab.ui.panels.dataset.sidebar.execute_application_command",
                return_value=_command_result(),
            ) as mock_execute,
            patch.object(QMessageBox, "warning") as mock_warning,
        ):
            mock_dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            mock_dialog.return_value.get_result.return_value = ["Cz", "Pz"]
            sb.open_channel_selection()

        mock_dialog.assert_called_once()
        assert isinstance(mock_execute.call_args.args[1], PreprocessCommand)
        panel.controller.apply_channel_selection.assert_not_called()
        panel.update_panel.assert_not_called()
        mock_warning.assert_not_called()

    def test_open_channel_selection_uses_query_data_before_stale_controller(
        self,
        qtbot,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.application import PreprocessCommand, QueryStateCommand
        from XBrainLab.backend.study import Study
        from XBrainLab.ui.panels.dataset.sidebar import DatasetSidebar

        study = Study()
        raw = MagicMock()
        raw.get_filename.return_value = "sub-01_task-mi_raw.fif"
        study.data_manager.loaded_data_list = [raw]
        panel = _make_panel_mock()
        panel.main_window.study = study
        panel.controller.get_loaded_data_list.side_effect = AssertionError(
            "stale loaded list should not be read",
        )
        sb = DatasetSidebar(panel)
        qtbot.addWidget(sb)

        def execute_for(_, command, refresh=True):
            if isinstance(command, QueryStateCommand):
                assert refresh is False
                return _command_result(loaded_data_list=[raw])
            if isinstance(command, PreprocessCommand):
                return _command_result()
            raise AssertionError(f"unexpected command: {command!r}")

        with (
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch(
                "XBrainLab.ui.panels.dataset.sidebar.get_command_capability",
                return_value=SimpleNamespace(enabled=True, reasons=[]),
            ),
            patch(
                "XBrainLab.ui.panels.dataset.sidebar.ChannelSelectionDialog",
            ) as mock_dialog,
            patch(
                "XBrainLab.ui.panels.dataset.sidebar.execute_application_command",
                side_effect=execute_for,
            ) as mock_execute,
            patch.object(QMessageBox, "warning") as mock_warning,
        ):
            mock_dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            mock_dialog.return_value.get_result.return_value = ["Cz", "Pz"]
            sb.open_channel_selection()

        mock_dialog.assert_called_once_with(sb, [raw])
        assert isinstance(mock_execute.call_args_list[0].args[1], QueryStateCommand)
        assert isinstance(mock_execute.call_args_list[1].args[1], PreprocessCommand)
        panel.controller.get_loaded_data_list.assert_not_called()
        panel.controller.apply_channel_selection.assert_not_called()
        mock_warning.assert_not_called()

    def test_open_channel_selection_refuses_real_study_query_none_controller_fallback(
        self,
        qtbot,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.study import Study
        from XBrainLab.ui.panels.dataset.sidebar import DatasetSidebar

        panel = _make_panel_mock()
        panel.main_window.study = Study()
        panel.controller.has_data.return_value = True
        panel.controller.is_locked.return_value = False
        panel.controller.get_loaded_data_list.side_effect = AssertionError(
            "stale loaded list should not be read",
        )
        sb = DatasetSidebar(panel)
        qtbot.addWidget(sb)

        with (
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch(
                "XBrainLab.ui.panels.dataset.sidebar.get_command_capability",
                return_value=None,
            ),
            patch(
                "XBrainLab.ui.panels.dataset.sidebar.execute_application_command",
                return_value=None,
            ),
            patch(
                "XBrainLab.ui.panels.dataset.sidebar.ChannelSelectionDialog",
            ) as mock_dialog,
            patch.object(QMessageBox, "warning") as mock_warning,
        ):
            sb.open_channel_selection()

        mock_dialog.assert_not_called()
        panel.controller.get_loaded_data_list.assert_not_called()
        mock_warning.assert_called_once()
        assert "could not safely complete" in mock_warning.call_args.args[2]

    def test_open_channel_selection_accepted(self, sidebar):
        sidebar.panel.controller.has_data.return_value = True
        sidebar.panel.controller.is_locked.return_value = False
        sidebar.panel.controller.get_loaded_data_list.return_value = [MagicMock()]
        with patch(
            "XBrainLab.ui.panels.dataset.sidebar.ChannelSelectionDialog"
        ) as MockDlg:
            MockDlg.return_value.exec.return_value = QDialog.DialogCode.Accepted
            MockDlg.return_value.get_result.return_value = ["Fp1", "Fp2"]
            sidebar.open_channel_selection()

    def test_clear_dataset(self, sidebar):
        from PyQt6.QtWidgets import QMessageBox

        with patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
        ):
            sidebar.clear_dataset()
            sidebar.panel.controller.clean_dataset.assert_called()

    def test_clear_dataset_uses_reset_session_capability_before_confirm(
        self,
        qtbot,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.study import Study
        from XBrainLab.ui.panels.dataset.sidebar import DatasetSidebar

        panel = _make_panel_mock()
        panel.main_window.study = Study()
        sb = DatasetSidebar(panel)
        qtbot.addWidget(sb)

        with (
            patch.object(QMessageBox, "question") as mock_question,
            patch.object(QMessageBox, "information") as mock_info,
        ):
            sb.clear_dataset()

        mock_question.assert_not_called()
        mock_info.assert_called_once_with(sb, "Success", "Dataset cleared.")
        panel.controller.clean_dataset.assert_not_called()
        panel.update_panel.assert_not_called()

    def test_clear_dataset_refuses_real_study_controller_fallback(self, sidebar):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.application.capabilities import CommandCapability
        from XBrainLab.backend.study import Study

        sidebar.panel.main_window.study = Study()

        with (
            patch(
                "XBrainLab.ui.panels.dataset.sidebar.get_command_capability",
                return_value=CommandCapability(
                    command_name="reset_session",
                    enabled=True,
                    destructive=True,
                    confirmation_required=True,
                ),
            ),
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch(
                "XBrainLab.ui.panels.dataset.sidebar.execute_application_command",
                return_value=None,
            ),
            patch.object(QMessageBox, "warning") as mock_warning,
            patch.object(QMessageBox, "critical") as mock_critical,
        ):
            sidebar.clear_dataset()

        sidebar.panel.controller.clean_dataset.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Clear Dataset Blocked"
        mock_critical.assert_not_called()
        assert "could not safely complete" in mock_warning.call_args.args[2]


# ============ CardWidget & PlaceholderWidget ============


class TestCardWidget:
    def test_creates_with_title(self, qtbot):
        from XBrainLab.ui.components.card import CardWidget

        card = CardWidget("Test Card")
        qtbot.addWidget(card)
        assert isinstance(card, CardWidget)

    def test_creates_without_title(self, qtbot):
        from XBrainLab.ui.components.card import CardWidget

        card = CardWidget("")
        qtbot.addWidget(card)
        assert isinstance(card, CardWidget)

    def test_add_widget(self, qtbot):
        from PyQt6.QtWidgets import QLabel

        from XBrainLab.ui.components.card import CardWidget

        card = CardWidget("Card")
        qtbot.addWidget(card)
        label = QLabel("hello")
        card.add_widget(label)

    def test_add_layout(self, qtbot):
        from PyQt6.QtWidgets import QHBoxLayout

        from XBrainLab.ui.components.card import CardWidget

        card = CardWidget("Card")
        qtbot.addWidget(card)
        layout = QHBoxLayout()
        card.add_layout(layout)


class TestPlaceholderWidget:
    def test_creates(self, qtbot):
        from XBrainLab.ui.components.placeholder import PlaceholderWidget

        w = PlaceholderWidget("📊", "No data available")
        qtbot.addWidget(w)
        assert isinstance(w, PlaceholderWidget)

    def test_message_displayed(self, qtbot):
        from XBrainLab.ui.components.placeholder import PlaceholderWidget

        w = PlaceholderWidget("⚠", "Please load data first")
        qtbot.addWidget(w)
        assert "load data" in w.msg_label.text().lower()
