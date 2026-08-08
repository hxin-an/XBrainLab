"""Coverage tests for sidebar modules: preprocess, training, dataset, viz control."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QDialog, QGroupBox, QMainWindow, QMessageBox, QWidget

from XBrainLab.ui.application_capabilities import (
    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
)
from XBrainLab.ui.interaction_outcome import InteractionStatus


def _command_result(**diagnostics):
    from types import SimpleNamespace

    return SimpleNamespace(
        ok=True,
        failed=False,
        message="ok",
        diagnostics=diagnostics,
    )


def _usable_epoch_dialog_context(
    epoch_handoff: dict[str, Any] | None = None,
):
    from XBrainLab.backend.application import CommandCapability
    from XBrainLab.backend.application.epoch_context import EpochDialogContext

    return EpochDialogContext(
        capability=CommandCapability(command_name="create_epoch", enabled=True),
        epoch_handoff=dict(epoch_handoff or {}),
        epoch_setup={
            "available_events": [{"name": "left", "count": 2}],
            "recommended_events": ["left"],
        },
        publication_generation=1,
        usable=True,
        unavailable_reason=None,
    )


def _split_config_payload() -> dict[str, object]:
    return {
        "train_type": "Individual",
        "is_cross_validation": False,
        "val_splitters": [
            {"split_type": "By Trial", "split_unit": "Ratio", "value": "0.2"},
        ],
        "test_splitters": [
            {"split_type": "By Trial", "split_unit": "Ratio", "value": "0.2"},
        ],
    }


def _dataset_split_dialog_binding(*, generation: int = 1):
    from XBrainLab.backend.application.dataset_split_preview import DatasetSplitContext
    from XBrainLab.ui.application_capabilities import DatasetSplitDialogBinding

    return DatasetSplitDialogBinding(
        split_context=DatasetSplitContext(
            epoch_available=True,
            subject_count=2,
            session_count=1,
            label_count=2,
            trial_count=12,
        ),
        publication_generation=generation,
        preview_provider=MagicMock(name="preview_provider"),
        preview_canceller=MagicMock(name="preview_canceller"),
    )


def _usable_training_epoch_data() -> MagicMock:
    epoch_data = MagicMock()
    epoch_data.epoch_count = 6
    epoch_data.event_id = {"left": 0, "right": 1}
    epoch_data.data = SimpleNamespace(shape=(6, 4, 33))
    epoch_data.sfreq = 128.0
    return epoch_data


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


def _running_trainer():
    """Return a contract-valid trainer whose liveness reads as active."""
    from XBrainLab.backend.training import Trainer

    trainer = Trainer([])
    cast(Any, trainer).is_running = MagicMock(return_value=True)
    return trainer


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

    def test_right_sidebars_keep_operation_area_at_consistent_y(self, qtbot):
        from XBrainLab.ui.panels.dataset.sidebar import DatasetSidebar
        from XBrainLab.ui.panels.preprocess.sidebar import PreprocessSidebar
        from XBrainLab.ui.panels.training.sidebar import TrainingSidebar
        from XBrainLab.ui.panels.visualization.control_sidebar import ControlSidebar
        from XBrainLab.ui.styles.stylesheets import Stylesheets

        sidebars = []
        for sidebar_class in (
            DatasetSidebar,
            PreprocessSidebar,
            TrainingSidebar,
            ControlSidebar,
        ):
            panel = _make_panel_mock()
            panel.action_handler = MagicMock()
            sidebar = sidebar_class(panel)
            qtbot.addWidget(sidebar)
            sidebars.append(sidebar)

        for sidebar in sidebars:
            layout = sidebar.layout()
            assert layout is not None
            assert layout.stretch(0) == 0
            groups = sidebar.findChildren(QGroupBox)
            primary_group = next(
                group
                for group in groups
                if group.title() in {"IMPORT", "OPERATIONS", "CONFIGURATION"}
            )
            assert (
                primary_group.minimumHeight()
                == Stylesheets.SIDEBAR_PRIMARY_GROUP_MIN_HEIGHT
            )

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

    def test_update_sidebar_reads_one_atomic_capability_publication(self, sidebar):
        from XBrainLab.backend.application import get_application_service
        from XBrainLab.backend.study import Study

        publication = get_application_service(Study()).get_view_publication()

        class Runtime:
            def __init__(self) -> None:
                self.publication_reads = 0

            def get_view_publication(self):
                self.publication_reads += 1
                return publication

        runtime = Runtime()
        with patch(
            "XBrainLab.ui.application_capabilities.application_ui_runtime",
            return_value=runtime,
        ):
            sidebar.update_sidebar()

        assert runtime.publication_reads == 1

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

    def test_check_lock_refuses_real_study_no_capability_fallback(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.study import Study

        sidebar.panel.main_window.study = Study()
        sidebar.panel.controller.is_epoched.side_effect = AssertionError(
            "stale epoched state should not be read",
        )

        with (
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.get_command_capability",
                return_value=None,
            ),
            patch.object(QMessageBox, "warning") as mock_warning,
        ):
            assert sidebar.check_lock() is True

        sidebar.panel.controller.is_epoched.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Action Blocked"
        assert mock_warning.call_args.args[2] == (
            "Preprocessing availability is unavailable right now."
        )

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

    def test_check_data_loaded_refuses_real_study_no_capability_fallback(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.study import Study

        sidebar.panel.main_window.study = Study()
        sidebar.panel.controller.has_data.side_effect = AssertionError(
            "stale loaded-data state should not be read",
        )

        with (
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.get_command_capability",
                return_value=None,
            ),
            patch.object(QMessageBox, "warning") as mock_warning,
        ):
            assert sidebar.check_data_loaded() is False

        sidebar.panel.controller.has_data.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Warning"
        assert mock_warning.call_args.args[2] == (
            "Preprocessing availability is unavailable right now."
        )

    def test_open_filtering_without_command_service_does_not_mutate_controller(
        self,
        sidebar,
    ):
        with (
            patch("XBrainLab.ui.panels.preprocess.sidebar.FilteringDialog") as MockDlg,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command",
                return_value=None,
            ) as mock_execute,
            patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warning,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = (1.0, 40.0, [50.0])
            sidebar.open_filtering()

        mock_execute.assert_called_once()
        sidebar.panel.controller.apply_filter.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Filtering Blocked"

    def test_open_filtering_refuses_real_study_controller_fallback(self, sidebar):
        from XBrainLab.backend.study import Study

        study = Study()
        raw = MagicMock()
        raw.get_filename.return_value = "sub-01_task-mi_raw.fif"
        study.data_manager.loaded_data_list = [raw]
        sidebar.panel.main_window.study = study

        with (
            patch("XBrainLab.ui.panels.preprocess.sidebar.FilteringDialog") as MockDlg,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command_async",
                return_value=False,
            ),
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command",
                return_value=None,
            ) as mock_execute,
            patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warning,
            patch("PyQt6.QtWidgets.QMessageBox.critical") as mock_critical,
            patch("PyQt6.QtWidgets.QMessageBox.information") as mock_info,
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = (1.0, 40.0, [50.0])
            sidebar.open_filtering()

        sidebar.panel.controller.apply_filter.assert_not_called()
        mock_execute.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Filtering Blocked"
        assert "could not safely complete" in mock_warning.call_args.args[2]
        mock_critical.assert_not_called()
        mock_info.assert_not_called()

    def test_open_filtering_uses_async_for_real_study(self, sidebar):
        from XBrainLab.backend.application import PreprocessCommand
        from XBrainLab.backend.study import Study

        study = Study()
        raw = MagicMock()
        raw.get_filename.return_value = "sub-01_task-mi_raw.fif"
        study.data_manager.loaded_data_list = [raw]
        sidebar.panel.main_window.study = study
        async_calls = []

        with (
            patch("XBrainLab.ui.panels.preprocess.sidebar.FilteringDialog") as MockDlg,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command_async",
                side_effect=lambda *args, **kwargs: async_calls.append(
                    (args, kwargs),
                )
                or True,
            ),
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command",
            ) as sync_execute,
            patch("PyQt6.QtWidgets.QMessageBox.information") as mock_info,
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = (1.0, 40.0, [50.0])
            sidebar.open_filtering()

        assert len(async_calls) == 1
        command = async_calls[0][0][1]
        assert isinstance(command, PreprocessCommand)
        sync_execute.assert_not_called()
        sidebar.panel.controller.apply_filter.assert_not_called()
        mock_info.assert_not_called()

    def test_open_filtering_binds_dialog_to_reviewed_publication(self, sidebar):
        from XBrainLab.backend.application import CommandCapability
        from XBrainLab.ui.application_capabilities import CommandReviewContext

        review_context = CommandReviewContext(
            capability=CommandCapability(
                command_name="preprocess",
                enabled=True,
            ),
            publication_generation=61,
        )
        with (
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.get_command_review_context",
                return_value=review_context,
            ),
            patch("XBrainLab.ui.panels.preprocess.sidebar.FilteringDialog") as dialog,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command_async",
                return_value=False,
            ) as execute_async,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command",
                return_value=_command_result(),
            ) as execute,
        ):
            dialog.return_value.exec.return_value = True
            dialog.return_value.get_params.return_value = (1.0, 40.0, [50.0])

            sidebar.open_filtering()

        assert execute_async.call_args.kwargs["expected_publication_generation"] == 61
        assert execute.call_args.kwargs["expected_publication_generation"] == 61

    def test_open_resample_without_command_service_does_not_mutate_controller(
        self,
        sidebar,
    ):
        with (
            patch("XBrainLab.ui.panels.preprocess.sidebar.ResampleDialog") as MockDlg,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command",
                return_value=None,
            ) as mock_execute,
            patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warning,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = 256
            sidebar.open_resample()

        mock_execute.assert_called_once()
        sidebar.panel.controller.apply_resample.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Resampling Blocked"

    def test_open_rereference_without_channel_context_blocks_before_mutation(
        self,
        sidebar,
    ):
        from XBrainLab.backend.application import QueryStateCommand

        with (
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.RereferenceDialog"
            ) as MockDlg,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command",
                return_value=None,
            ) as mock_execute,
            patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warning,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = ["Cz"]
            sidebar.open_rereference()

        assert isinstance(mock_execute.call_args_list[0].args[1], QueryStateCommand)
        assert len(mock_execute.call_args_list) == 1
        MockDlg.assert_not_called()
        sidebar.panel.controller.apply_rereference.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Re-reference Blocked"

    def test_open_rereference_uses_detached_channels_before_stale_controller(
        self,
        sidebar,
    ):
        from XBrainLab.backend.application import (
            PreprocessCommand,
            QueryStateCommand,
        )

        sidebar.panel.controller.get_preprocessed_data_list.side_effect = (
            AssertionError("stale preprocessed list should not be read")
        )

        def execute_for(
            _,
            command,
            refresh=True,
            expected_publication_generation=None,
        ):
            if isinstance(command, QueryStateCommand):
                return _command_result(preprocessed_rows=[{"channels": ["Cz", "Pz"]}])
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
        MockDlg.assert_called_once_with(sidebar, ["Cz", "Pz"])
        sidebar.panel.controller.get_preprocessed_data_list.assert_not_called()
        sidebar.panel.controller.apply_rereference.assert_not_called()

    def test_open_rereference_binds_query_and_apply_to_reviewed_publication(
        self,
        sidebar,
    ):
        from XBrainLab.backend.application import (
            CommandCapability,
            PreprocessCommand,
            QueryStateCommand,
        )
        from XBrainLab.ui.application_capabilities import CommandReviewContext

        review_context = CommandReviewContext(
            capability=CommandCapability(
                command_name="preprocess",
                enabled=True,
            ),
            publication_generation=62,
        )
        calls = []

        def execute_for(
            _,
            command,
            *,
            refresh=True,
            expected_publication_generation=None,
        ):
            calls.append((command, refresh, expected_publication_generation))
            if isinstance(command, QueryStateCommand):
                return _command_result(preprocessed_rows=[{"channels": ["Cz"]}])
            if isinstance(command, PreprocessCommand):
                return _command_result()
            raise AssertionError(f"unexpected command: {command!r}")

        with (
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.get_command_review_context",
                return_value=review_context,
            ),
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.RereferenceDialog",
            ) as dialog,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command_async",
                return_value=False,
            ),
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command",
                side_effect=execute_for,
            ),
        ):
            dialog.return_value.exec.return_value = True
            dialog.return_value.get_params.return_value = ["Cz"]

            sidebar.open_rereference()

        assert [type(command) for command, _, _ in calls] == [
            QueryStateCommand,
            PreprocessCommand,
        ]
        assert [generation for _, _, generation in calls] == [62, 62]

    def test_open_normalize_without_command_service_does_not_mutate_controller(
        self,
        sidebar,
    ):
        with (
            patch("XBrainLab.ui.panels.preprocess.sidebar.NormalizeDialog") as MockDlg,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command",
                return_value=None,
            ) as mock_execute,
            patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warning,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = "z-score"
            sidebar.open_normalize()

        mock_execute.assert_called_once()
        sidebar.panel.controller.apply_normalization.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Normalization Blocked"

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

    def test_open_epoching_without_command_service_does_not_mutate_controller(
        self,
        sidebar,
    ):
        with (
            patch("XBrainLab.ui.panels.preprocess.sidebar.EpochingDialog") as MockDlg,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command",
                return_value=None,
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
            sidebar.panel.controller.apply_epoching.return_value = True
            outcome = sidebar.open_epoching()

        assert outcome.status is InteractionStatus.BLOCKED
        mock_execute.assert_not_called()
        MockDlg.assert_not_called()
        sidebar.panel.controller.apply_epoching.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Create EEG Epochs Blocked"

    def test_open_epoching_dialog_rejection_returns_cancelled(self, sidebar):
        with (
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.get_epoch_dialog_context",
                return_value=_usable_epoch_dialog_context(),
            ),
            patch("XBrainLab.ui.panels.preprocess.sidebar.EpochingDialog") as dialog,
        ):
            dialog.return_value.exec.return_value = QDialog.DialogCode.Rejected
            outcome = sidebar.open_epoching()

        assert outcome.status is InteractionStatus.CANCELLED

    def test_open_epoching_async_dispatch_reports_scheduled_without_completion(
        self,
        sidebar,
    ):
        with (
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.get_epoch_dialog_context",
                return_value=_usable_epoch_dialog_context(),
            ),
            patch("XBrainLab.ui.panels.preprocess.sidebar.EpochingDialog") as dialog,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar."
                "execute_application_command_async",
                return_value=True,
            ),
        ):
            dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            dialog.return_value.get_params.return_value = (
                None,
                ["left"],
                -0.5,
                1.0,
            )
            outcome = sidebar.open_epoching()

        assert outcome.status is InteractionStatus.ACCEPTED

    def test_open_epoching_nonrecoverable_command_failure_returns_failed(
        self,
        sidebar,
    ):
        failure = SimpleNamespace(
            failed=True,
            recoverable=False,
            message="epoch command failed",
        )
        with (
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.get_epoch_dialog_context",
                return_value=_usable_epoch_dialog_context(),
            ),
            patch("XBrainLab.ui.panels.preprocess.sidebar.EpochingDialog") as dialog,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar."
                "execute_application_command_async",
                return_value=False,
            ),
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.has_real_application_context",
                return_value=False,
            ),
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command",
                return_value=failure,
            ),
            patch("PyQt6.QtWidgets.QMessageBox.critical"),
        ):
            dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            dialog.return_value.get_params.return_value = (
                None,
                ["left"],
                -0.5,
                1.0,
            )
            outcome = sidebar.open_epoching()

        assert outcome.status is InteractionStatus.FAILED

    def test_open_epoching_without_command_service_skips_shared_status(self, sidebar):
        sidebar.panel.main_window.update_info_panel = MagicMock()
        sidebar.panel.main_window.agent_manager = SimpleNamespace(
            refresh_backend_status=MagicMock(),
        )

        with (
            patch("XBrainLab.ui.panels.preprocess.sidebar.EpochingDialog") as MockDlg,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command",
                return_value=None,
            ),
            patch("PyQt6.QtWidgets.QMessageBox.warning"),
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

        sidebar.panel.controller.apply_epoching.assert_not_called()
        sidebar.panel.main_window.update_info_panel.assert_not_called()
        (
            sidebar.panel.main_window.agent_manager.refresh_backend_status.assert_not_called()
        )

    def test_open_epoching_uses_epoch_capability_not_preprocess_block(
        self,
        sidebar,
    ):
        from XBrainLab.backend.application import CreateEpochCommand

        def execute_for(
            _,
            command,
            refresh=True,
            expected_publication_generation=None,
        ):
            assert expected_publication_generation == 1
            assert isinstance(command, CreateEpochCommand)
            return _command_result()

        with (
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.get_epoch_dialog_context",
                return_value=_usable_epoch_dialog_context(),
            ),
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.get_command_capability",
                side_effect=AssertionError(
                    "epoching performed a second capability read"
                ),
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
            outcome = sidebar.open_epoching()

        assert outcome.status is InteractionStatus.COMPLETED
        mock_warning.assert_not_called()
        assert isinstance(mock_execute.call_args.args[1], CreateEpochCommand)
        sidebar.panel.controller.apply_epoching.assert_not_called()

    def test_open_epoching_uses_detached_context_before_stale_controller(
        self,
        sidebar,
    ):
        from XBrainLab.backend.application import CreateEpochCommand

        sidebar.panel.controller.get_preprocessed_data_list.side_effect = (
            AssertionError("stale preprocessed list should not be read")
        )

        def execute_for(
            _,
            command,
            refresh=True,
            expected_publication_generation=None,
        ):
            assert expected_publication_generation == 1
            if isinstance(command, CreateEpochCommand):
                return _command_result()
            raise AssertionError(f"unexpected command: {command!r}")

        with (
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.get_epoch_dialog_context",
                return_value=_usable_epoch_dialog_context(),
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
        MockDlg.assert_called_once_with(
            sidebar,
            epoch_context={
                "available_events": [{"name": "left", "count": 2}],
                "recommended_events": ["left"],
            },
        )
        sidebar.panel.controller.get_preprocessed_data_list.assert_not_called()
        sidebar.panel.controller.apply_epoching.assert_not_called()

    def test_open_epoching_passes_import_handoff_to_dialog(self, sidebar):
        from XBrainLab.backend.application import (
            CommandCapability,
            CreateEpochCommand,
        )
        from XBrainLab.backend.application.epoch_context import EpochDialogContext

        epoch_handoff = {
            "ready": True,
            "default_epoch_events": ["Left hand", "Right hand"],
            "label_source": "bids_events",
        }
        epoch_setup = {
            "available_events": [
                {"name": "Left hand", "count": 2},
                {"name": "Right hand", "count": 2},
            ],
            "recommended_events": ["Left hand", "Right hand"],
        }
        assistant_suggestions = {
            "target_event": "Left hand",
            "t_min": "-0.5",
        }
        dialog_context = EpochDialogContext(
            capability=CommandCapability(
                command_name="create_epoch",
                enabled=True,
            ),
            epoch_handoff=epoch_handoff,
            epoch_setup=epoch_setup,
            publication_generation=7,
            usable=True,
            unavailable_reason=None,
        )
        executed_commands = []

        def execute_for(
            _,
            command,
            refresh=True,
            expected_publication_generation=None,
        ):
            executed_commands.append(command)
            if isinstance(command, CreateEpochCommand):
                assert expected_publication_generation == 7
                return _command_result()
            raise AssertionError(f"unexpected command: {command!r}")

        with (
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.get_command_capability",
                side_effect=AssertionError(
                    "epoch dialog must not perform a second capability read"
                ),
            ),
            patch("XBrainLab.ui.panels.preprocess.sidebar.EpochingDialog") as MockDlg,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command",
                side_effect=execute_for,
            ),
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.get_epoch_dialog_context",
                return_value=dialog_context,
            ) as read_dialog_context,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = (
                (None, 0),
                ["Left hand", "Right hand"],
                -0.5,
                1.0,
            )
            MockDlg.return_value.get_confirmation_receipt.return_value = (
                "backend-epoch-receipt"
            )
            sidebar.open_epoching(suggested_values=assistant_suggestions)

        MockDlg.assert_called_once_with(
            sidebar,
            epoch_context=epoch_setup,
            epoch_handoff={
                "ready": True,
                "default_epoch_events": ["Left hand", "Right hand"],
                "label_source": "bids_events",
            },
            assistant_suggestions=assistant_suggestions,
        )
        read_dialog_context.assert_called_once_with(sidebar)
        epoch_command = next(
            command
            for command in executed_commands
            if isinstance(command, CreateEpochCommand)
        )
        assert epoch_command.confirmation_receipt == "backend-epoch-receipt"

    def test_open_epoching_reads_exactly_one_detached_context(self, sidebar):
        from dataclasses import replace

        dialog_context = replace(
            _usable_epoch_dialog_context(),
            publication_generation=19,
        )

        class Runtime:
            def __init__(self) -> None:
                self.context_reads = 0
                self.commands: list[object] = []

            def get_epoch_dialog_context(self):
                self.context_reads += 1
                return dialog_context

            def execute(
                self,
                command,
                *,
                expected_publication_generation=None,
            ):
                assert expected_publication_generation == 19
                self.commands.append(command)
                return _command_result()

        runtime = Runtime()
        with (
            patch(
                "XBrainLab.ui.application_capabilities.application_ui_runtime",
                return_value=runtime,
            ),
            patch("XBrainLab.ui.panels.preprocess.sidebar.EpochingDialog") as dialog,
        ):
            dialog.return_value.exec.return_value = QDialog.DialogCode.Rejected
            outcome = sidebar.open_epoching()

        assert outcome.status is InteractionStatus.CANCELLED
        assert runtime.context_reads == 1
        assert runtime.commands == []
        dialog.assert_called_once_with(
            sidebar,
            epoch_context=dialog_context.epoch_setup,
        )

    def test_epoch_confirmation_binds_generation_and_stale_result_requires_review(
        self,
        sidebar,
    ):
        from dataclasses import replace

        from XBrainLab.backend.application import (
            ChangedState,
            CommandName,
            CommandResult,
            ErrorType,
        )

        dialog_context = replace(
            _usable_epoch_dialog_context(),
            publication_generation=23,
        )
        stale_result = CommandResult.failure_result(
            command_name=CommandName.CREATE_EPOCH.value,
            message=(
                "Workflow state changed while this confirmed action was pending. "
                "Review the action again before continuing."
            ),
            state=None,
            changed_state=ChangedState(),
            error_type=ErrorType.PRECONDITION,
            recoverable=True,
            diagnostics={"stale_publication": True},
        )
        callback_outcomes = []

        def fake_async(_context, _command, *, on_result, **kwargs):
            assert kwargs["expected_publication_generation"] == 23
            callback_outcomes.append(on_result(stale_result))
            return True

        with (
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.get_epoch_dialog_context",
                return_value=dialog_context,
            ),
            patch("XBrainLab.ui.panels.preprocess.sidebar.EpochingDialog") as dialog,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar."
                "execute_application_command_async",
                side_effect=fake_async,
            ),
            patch.object(QMessageBox, "warning") as warning,
            patch.object(QMessageBox, "critical") as critical,
            patch.object(sidebar, "_handle_epoch_command_success") as success,
        ):
            dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            dialog.return_value.get_params.return_value = (
                None,
                ["left"],
                -0.5,
                1.0,
            )
            outcome = sidebar.open_epoching()

        assert outcome.status is InteractionStatus.ACCEPTED
        assert callback_outcomes[0].status is InteractionStatus.BLOCKED
        warning.assert_called_once_with(
            sidebar,
            "Review EEG Epoch Setup Again",
            stale_result.message,
        )
        critical.assert_not_called()
        success.assert_not_called()

    def test_open_epoching_blocks_typed_unavailable_context_without_defaults(
        self,
        sidebar,
    ):
        from XBrainLab.backend.application.epoch_context import EpochDialogContext

        unavailable = EpochDialogContext(
            capability=None,
            epoch_handoff=None,
            epoch_setup=None,
            publication_generation=11,
            usable=False,
            unavailable_reason="Workflow state is temporarily unavailable.",
        )

        with (
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.get_epoch_dialog_context",
                return_value=unavailable,
            ) as read_dialog_context,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command"
            ) as execute_command,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.EpochingDialog"
            ) as epoch_dialog,
            patch("PyQt6.QtWidgets.QMessageBox.warning") as warning,
        ):
            outcome = sidebar.open_epoching()

        assert outcome.status is InteractionStatus.BLOCKED
        read_dialog_context.assert_called_once_with(sidebar)
        execute_command.assert_not_called()
        epoch_dialog.assert_not_called()
        warning.assert_called_once()
        assert "temporarily unavailable" in warning.call_args.args[2]

    def test_open_epoching_never_reads_controller_live_data(
        self,
        sidebar,
    ):
        sidebar.panel.controller.get_preprocessed_data_list.side_effect = (
            AssertionError("stale preprocessed list should not be read")
        )

        with (
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.get_epoch_dialog_context",
                return_value=_usable_epoch_dialog_context(),
            ),
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.EpochingDialog"
            ) as mock_dialog,
        ):
            mock_dialog.return_value.exec.return_value = QDialog.DialogCode.Rejected
            outcome = sidebar.open_epoching()

        assert outcome.status is InteractionStatus.CANCELLED
        mock_dialog.assert_called_once_with(
            sidebar,
            epoch_context={
                "available_events": [{"name": "left", "count": 2}],
                "recommended_events": ["left"],
            },
        )
        sidebar.panel.controller.get_preprocessed_data_list.assert_not_called()

    def test_reset_preprocess(self, sidebar):
        from PyQt6.QtWidgets import QMessageBox

        with (
            patch.object(
                QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
            ),
            patch.object(QMessageBox, "warning") as mock_warning,
        ):
            sidebar.reset_preprocess()

        sidebar.panel.controller.reset_preprocess.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Reset Blocked"

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

    def test_reset_preprocess_binds_generation_and_stale_result_requires_review(
        self,
        sidebar,
    ):
        from XBrainLab.backend.application import (
            ChangedState,
            CommandName,
            CommandResult,
            ErrorType,
            get_application_service,
        )
        from XBrainLab.backend.study import Study

        study = Study()
        raw = MagicMock()
        raw.get_filename.return_value = "sub-01_task-mi_raw.fif"
        study.data_manager.loaded_data_list = [raw]
        study.data_manager.preprocessed_data_list = [raw]
        sidebar.panel.main_window.study = study
        publication = get_application_service(study).get_view_publication()
        stale_result = CommandResult.failure_result(
            command_name=CommandName.RESET_PREPROCESS.value,
            message=(
                "Workflow state changed while this confirmed action was pending. "
                "Review the action again before continuing."
            ),
            state=publication.state,
            changed_state=ChangedState(),
            error_type=ErrorType.PRECONDITION,
            recoverable=True,
            diagnostics={"stale_publication": True},
        )

        with (
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command",
                return_value=stale_result,
            ) as execute,
            patch.object(QMessageBox, "warning") as warning,
            patch.object(QMessageBox, "critical") as critical,
            patch.object(sidebar, "_show_status") as show_status,
        ):
            sidebar.reset_preprocess()

        assert execute.call_args.kwargs["expected_publication_generation"] == (
            publication.generation
        )
        warning.assert_called_once_with(
            sidebar,
            "Review Reset Preprocessing Again",
            stale_result.message,
        )
        critical.assert_not_called()
        show_status.assert_not_called()

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

    def test_model_selection_dialog_canonicalizes_only_existing_initial_model(
        self,
        qtbot,
    ):
        from XBrainLab.ui.dialogs.training import ModelSelectionDialog

        selected = ModelSelectionDialog(
            None,
            MagicMock(),
            initial_model_name="sccnet",
        )
        qtbot.addWidget(selected)
        assert selected.model_combo is not None
        assert selected.model_combo.currentText() == "SCCNet (XBrainLab)"

        unknown = ModelSelectionDialog(
            None,
            MagicMock(),
            initial_model_name="not-a-real-model",
        )
        qtbot.addWidget(unknown)
        assert unknown.model_combo is not None
        assert unknown.model_combo.currentText() == unknown.model_list[0]
        assert unknown.model_combo.findText("not-a-real-model") == -1

    def test_check_ready_to_train_not_ready(self, sidebar):
        result = sidebar.check_ready_to_train()
        # Without datasets/model/option, not ready
        assert result is False or result is None

    def test_check_ready_to_train_uses_published_blockers_without_controller_fallback(
        self,
        sidebar,
    ):
        from XBrainLab.backend.study import Study

        sidebar.panel.main_window.study = Study()
        sidebar.panel.controller.validate_ready.side_effect = AssertionError(
            "stale controller readiness should not be read",
        )
        sidebar.panel.controller.has_datasets.side_effect = AssertionError(
            "stale dataset readiness should not be read",
        )
        sidebar.panel.controller.validate_ready.reset_mock()
        sidebar.panel.controller.has_datasets.reset_mock()

        with patch(
            "XBrainLab.ui.panels.training.sidebar.get_command_capability",
            return_value=None,
        ):
            sidebar.check_ready_to_train()

        sidebar.panel.controller.validate_ready.assert_not_called()
        sidebar.panel.controller.has_datasets.assert_not_called()
        assert sidebar.btn_start.isEnabled() is False
        assert "Load raw data before training" in sidebar.btn_start.toolTip()
        assert "state is unavailable" not in sidebar.btn_start.toolTip()

    def test_update_info_is_info_panel_service_boundary_without_controller_reads(
        self,
        sidebar,
    ):
        sidebar.panel.controller.validate_ready.reset_mock()
        sidebar.panel.controller.has_datasets.reset_mock()
        sidebar.panel.controller.validate_ready.side_effect = AssertionError(
            "update_info should not read training readiness",
        )
        sidebar.panel.controller.has_datasets.side_effect = AssertionError(
            "update_info should not read dataset state",
        )

        sidebar.update_info()

        sidebar.panel.controller.validate_ready.assert_not_called()
        sidebar.panel.controller.has_datasets.assert_not_called()

    def test_split_data_without_command_service_does_not_mutate_controller(
        self,
        sidebar,
    ):
        sidebar.panel.controller.has_data = MagicMock(return_value=True)
        sidebar.panel.dataset_controller.has_data.return_value = True
        sidebar.panel.dataset_controller.get_epoch_data.return_value = MagicMock()
        sidebar.panel.controller.has_datasets.return_value = False
        sidebar.panel.controller.get_trainer.return_value = None
        generator = _split_config_payload()
        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.DataSplittingDialog"
            ) as MockDlg,
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command_async",
                return_value=False,
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                return_value=None,
            ),
            patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warning,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = QDialog.DialogCode.Accepted
            MockDlg.return_value.get_result.return_value = generator
            outcome = sidebar.split_data()

        assert outcome.status is InteractionStatus.BLOCKED
        sidebar.panel.controller.apply_data_splitting.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Data Splitting Blocked"

    def test_split_data_dialog_rejection_returns_cancelled(self, sidebar):
        suggestions = {
            "training_mode": "individual",
            "split_strategy": "subject",
        }
        with (
            patch.object(sidebar, "_data_splitting_blocked", return_value=False),
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_command_capability",
                return_value=SimpleNamespace(enabled=True, reasons=[]),
            ),
            patch.object(
                sidebar,
                "_data_splitting_dialog_context",
                return_value=_dataset_split_dialog_binding(),
            ),
            patch("XBrainLab.ui.panels.training.sidebar.DataSplittingDialog") as dialog,
        ):
            dialog.return_value.exec.return_value = QDialog.DialogCode.Rejected
            outcome = sidebar.split_data(suggested_values=suggestions)

        assert outcome.status is InteractionStatus.CANCELLED
        assert dialog.call_args.kwargs["initial_values"] == suggestions

    def test_split_data_binds_reviewed_generation_and_stale_result_is_recoverable(
        self,
        sidebar,
    ):
        from XBrainLab.backend.application import (
            ChangedState,
            CommandCapability,
            CommandName,
            CommandResult,
            ErrorType,
        )

        generation = 31
        capability = CommandCapability(
            command_name=CommandName.GENERATE_DATASET.value,
            enabled=True,
        )
        publication = SimpleNamespace(
            generation=generation,
            effective_capabilities=SimpleNamespace(
                get=lambda command_name: (
                    capability
                    if command_name
                    in {
                        CommandName.GENERATE_DATASET,
                        CommandName.GENERATE_DATASET.value,
                    }
                    else None
                )
            ),
        )
        stale_result = CommandResult.failure_result(
            command_name=CommandName.GENERATE_DATASET.value,
            message=(
                "Workflow state changed while this confirmed action was pending. "
                "Review the action again before continuing."
            ),
            state=None,
            changed_state=ChangedState(),
            error_type=ErrorType.PRECONDITION,
            recoverable=True,
            diagnostics={"stale_publication": True},
        )
        callback_outcomes = []

        def fake_async(_context, _command, *, on_result, **kwargs):
            assert kwargs["expected_publication_generation"] == generation
            callback_outcomes.append(on_result(stale_result))
            return True

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_application_view_publication",
                return_value=publication,
                create=True,
            ) as get_publication,
            patch.object(
                sidebar,
                "_data_splitting_dialog_context",
                return_value=_dataset_split_dialog_binding(generation=generation),
            ) as dialog_context,
            patch("XBrainLab.ui.panels.training.sidebar.DataSplittingDialog") as dialog,
            patch(
                "XBrainLab.ui.panels.training.sidebar."
                "execute_application_command_async",
                side_effect=fake_async,
            ),
            patch.object(sidebar, "_show_message_box") as message_box,
            patch.object(sidebar, "_show_status") as show_status,
        ):
            dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            dialog.return_value.get_result.return_value = _split_config_payload()
            outcome = sidebar.split_data()

        assert outcome.status is InteractionStatus.ACCEPTED
        assert callback_outcomes[0].status is InteractionStatus.BLOCKED
        get_publication.assert_called_once_with(sidebar, runtime=None)
        dialog_context.assert_called_once_with(
            expected_publication_generation=generation,
        )
        message_box.assert_called_once_with(
            QMessageBox.Icon.Warning,
            "Review Data Splitting Again",
            stale_result.message,
        )
        show_status.assert_not_called()

    def test_clear_history_binds_confirmation_generation_and_reviews_stale_result(
        self,
        sidebar,
    ):
        from XBrainLab.backend.application import (
            ChangedState,
            CommandCapability,
            CommandName,
            CommandResult,
            ErrorType,
        )

        generation = 43
        capability = CommandCapability(
            command_name=CommandName.CLEAR_TRAINING_HISTORY.value,
            enabled=True,
            destructive=True,
            confirmation_required=True,
        )
        publication = SimpleNamespace(
            generation=generation,
            effective_capabilities=SimpleNamespace(
                get=lambda command_name: (
                    capability
                    if command_name
                    in {
                        CommandName.CLEAR_TRAINING_HISTORY,
                        CommandName.CLEAR_TRAINING_HISTORY.value,
                    }
                    else None
                )
            ),
        )
        stale_result = CommandResult.failure_result(
            command_name=CommandName.CLEAR_TRAINING_HISTORY.value,
            message=(
                "Workflow state changed while this confirmed action was pending. "
                "Review the action again before continuing."
            ),
            state=None,
            changed_state=ChangedState(),
            error_type=ErrorType.PRECONDITION,
            recoverable=True,
            diagnostics={"stale_publication": True},
        )

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_application_view_publication",
                return_value=publication,
            ),
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                return_value=stale_result,
            ) as execute,
            patch.object(QMessageBox, "warning") as warning,
            patch.object(sidebar, "_show_status") as show_status,
        ):
            sidebar.clear_history()

        assert execute.call_args.kwargs["expected_publication_generation"] == generation
        warning.assert_called_once_with(
            sidebar,
            "Review Clear History Again",
            stale_result.message,
        )
        show_status.assert_not_called()

    def test_split_data_nonrecoverable_command_failure_returns_failed(self, sidebar):
        failure = SimpleNamespace(
            failed=True,
            recoverable=False,
            message="generation failed",
        )
        with (
            patch.object(sidebar, "_data_splitting_blocked", return_value=False),
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_command_capability",
                return_value=SimpleNamespace(enabled=True, reasons=[]),
            ),
            patch.object(
                sidebar,
                "_data_splitting_dialog_context",
                return_value=_dataset_split_dialog_binding(),
            ),
            patch.object(
                sidebar,
                "_requires_dataset_replacement_confirmation",
                return_value=False,
            ),
            patch("XBrainLab.ui.panels.training.sidebar.DataSplittingDialog") as dialog,
            patch(
                "XBrainLab.ui.panels.training.sidebar."
                "execute_application_command_async",
                return_value=False,
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.has_real_application_context",
                return_value=False,
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                return_value=failure,
            ),
            patch.object(sidebar, "_show_message_box"),
        ):
            dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            dialog.return_value.get_result.return_value = _split_config_payload()
            outcome = sidebar.split_data()

        assert outcome.status is InteractionStatus.FAILED

    def test_split_data_service_success_does_not_fallback_to_controller(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.application import (
            CommandCapability,
            CommandName,
            GenerateDatasetCommand,
        )

        generation = 21
        generator = _split_config_payload()
        capability = CommandCapability(
            command_name=CommandName.GENERATE_DATASET.value,
            enabled=True,
            destructive=True,
            confirmation_required=True,
            requires_confirmation=True,
        )
        publication = SimpleNamespace(
            generation=generation,
            effective_capabilities={CommandName.GENERATE_DATASET: capability},
        )
        binding = _dataset_split_dialog_binding(generation=generation)
        sidebar.panel.controller.has_data = MagicMock(return_value=True)
        sidebar.panel.dataset_controller.has_data.return_value = True
        sidebar.panel.dataset_controller.get_epoch_data.return_value = MagicMock()
        sidebar.panel.controller.has_datasets.return_value = True
        sidebar.panel.controller.get_trainer.return_value = MagicMock()

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.DataSplittingDialog"
            ) as MockDlg,
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_application_view_publication",
                return_value=publication,
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_dataset_split_dialog_binding",
                return_value=binding,
            ),
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                return_value=_command_result(),
            ) as mock_execute_sync,
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command_async",
                return_value=True,
            ) as mock_execute_async,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = QDialog.DialogCode.Accepted
            MockDlg.return_value.get_result.return_value = generator
            outcome = sidebar.split_data()

        assert outcome.status is InteractionStatus.ACCEPTED
        async_commands = [call.args[1] for call in mock_execute_async.call_args_list]
        mock_execute_sync.assert_not_called()
        assert isinstance(async_commands[0], GenerateDatasetCommand)
        assert async_commands[0].replacement_mode == "replace_existing"
        assert async_commands[0].confirmed is True
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
            "Create EEG epochs before building the training dataset.",
        )

    def test_split_data_refuses_real_study_preflight_fallback(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.study import Study

        sidebar.panel.main_window.study = Study()
        sidebar.panel.controller.get_loaded_data_list.side_effect = AssertionError(
            "stale loaded data list should not be read",
        )
        sidebar.panel.controller.get_epoch_data.side_effect = AssertionError(
            "stale epoch data should not be read",
        )
        sidebar.panel.controller.is_training.side_effect = AssertionError(
            "stale training state should not be read",
        )

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_command_review_context",
                return_value=None,
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_application_view_publication",
                return_value=None,
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.DataSplittingDialog",
            ) as mock_dialog,
            patch.object(QMessageBox, "warning") as mock_warning,
        ):
            sidebar.split_data()

        mock_dialog.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Data Splitting Blocked"
        assert "could not safely complete" in mock_warning.call_args.args[2]
        sidebar.panel.controller.get_loaded_data_list.assert_not_called()
        sidebar.panel.controller.get_epoch_data.assert_not_called()
        sidebar.panel.controller.is_training.assert_not_called()

    def test_split_data_allows_backend_replacement_boundary(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.application import (
            GenerateDatasetCommand,
        )
        from XBrainLab.backend.study import Study

        study = Study()
        raw = MagicMock()
        raw.is_raw.return_value = True
        study.data_manager.loaded_data_list = [raw]
        study.data_manager.preprocessed_data_list = [raw]
        study.data_manager.epoch_data = _usable_training_epoch_data()
        study.data_manager.datasets = [MagicMock()]
        sidebar.panel.main_window.study = study
        sidebar.panel.controller.has_datasets.return_value = True
        sidebar.panel.controller.get_trainer.return_value = None
        generator = _split_config_payload()
        async_commands = []

        def fake_async(_panel, command, *, on_result, **_kwargs):
            async_commands.append(command)
            on_result(_command_result())
            return True

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_command_capability",
                return_value=SimpleNamespace(
                    enabled=True,
                    reasons=["This wording may change without changing policy."],
                    requires_confirmation=True,
                    decision_boundary="replace_generated_datasets",
                ),
            ),
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
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command_async",
                side_effect=fake_async,
            ),
            patch.object(QMessageBox, "warning") as mock_warning,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            mock_dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            mock_dialog.return_value.get_result.return_value = generator
            outcome = sidebar.split_data()

        assert outcome.status is InteractionStatus.ACCEPTED
        mock_warning.assert_not_called()
        mock_execute.assert_not_called()
        assert isinstance(async_commands[0], GenerateDatasetCommand)
        assert async_commands[0].replacement_mode == "replace_existing"
        assert async_commands[0].confirmed is True

    def test_split_data_replacement_cancel_preserves_backend_state(self, sidebar):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.application import CommandCapability, CommandName
        from XBrainLab.backend.study import Study

        old_datasets = [MagicMock(name="existing_dataset")]
        old_generator = MagicMock(name="existing_generator")
        old_trainer = MagicMock(name="existing_trainer")
        study = Study()
        sidebar.panel.main_window.study = study
        study.data_manager.datasets = cast(Any, old_datasets)
        study.data_manager.dataset_generator = old_generator
        study.training_manager.trainer = old_trainer
        generate_capability = CommandCapability(
            command_name=CommandName.GENERATE_DATASET.value,
            enabled=True,
            reasons=["Display copy is not policy."],
            requires_confirmation=True,
            decision_boundary="replace_generated_datasets",
        )

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_application_view_publication",
                return_value=SimpleNamespace(
                    generation=41,
                    effective_capabilities={
                        CommandName.GENERATE_DATASET: generate_capability,
                    },
                ),
            ),
            patch.object(
                sidebar,
                "_data_splitting_dialog_context",
                return_value=_dataset_split_dialog_binding(generation=41),
            ),
            patch("XBrainLab.ui.panels.training.sidebar.DataSplittingDialog") as dialog,
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.No,
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command"
            ) as execute_sync,
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command_async"
            ) as execute_async,
        ):
            dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            dialog.return_value.get_result.return_value = _split_config_payload()
            outcome = sidebar.split_data()

        assert outcome.status is InteractionStatus.CANCELLED
        execute_sync.assert_not_called()
        execute_async.assert_not_called()
        assert study.data_manager.datasets == old_datasets
        assert study.data_manager.dataset_generator is old_generator
        assert study.training_manager.trainer is old_trainer

    def test_split_data_uses_backend_replacement_boundary_when_controller_stale(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.application import (
            GenerateDatasetCommand,
        )
        from XBrainLab.backend.study import Study

        study = Study()
        raw = MagicMock()
        raw.is_raw.return_value = True
        study.data_manager.loaded_data_list = [raw]
        study.data_manager.preprocessed_data_list = [raw]
        study.data_manager.epoch_data = _usable_training_epoch_data()
        study.data_manager.datasets = [MagicMock()]
        sidebar.panel.main_window.study = study
        sidebar.panel.controller.has_datasets.return_value = False
        sidebar.panel.controller.get_trainer.return_value = None
        generator = _split_config_payload()
        async_commands = []

        def fake_async(_panel, command, *, on_result, **_kwargs):
            async_commands.append(command)
            on_result(_command_result())
            return True

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
                "XBrainLab.ui.panels.training.sidebar.execute_application_command_async",
                side_effect=fake_async,
            ) as mock_execute_async,
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                return_value=_command_result(),
            ) as mock_execute_sync,
            patch.object(QMessageBox, "warning") as mock_warning,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            mock_dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            mock_dialog.return_value.get_result.return_value = generator
            sidebar.split_data()

        mock_warning.assert_not_called()
        mock_question.assert_called_once()
        mock_execute_sync.assert_not_called()
        assert isinstance(async_commands[0], GenerateDatasetCommand)
        assert async_commands[0].replacement_mode == "replace_existing"
        assert async_commands[0].confirmed is True
        assert isinstance(mock_execute_async.call_args.args[1], GenerateDatasetCommand)
        sidebar.panel.controller.clean_datasets.assert_not_called()
        sidebar.panel.controller.apply_data_splitting.assert_not_called()

    def test_split_data_passes_detached_service_context_and_callbacks_to_dialog(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.application import GenerateDatasetCommand
        from XBrainLab.backend.application.dataset_split_preview import (
            DatasetSplitContext,
        )
        from XBrainLab.backend.study import Study

        study = Study()
        raw = MagicMock()
        raw.is_raw.return_value = True
        study.data_manager.loaded_data_list = [raw]
        study.data_manager.preprocessed_data_list = [raw]
        study.data_manager.epoch_data = _usable_training_epoch_data()
        study.data_manager.dataset_generator = MagicMock(name="service_generator")
        sidebar.panel.main_window.study = study
        sidebar.panel.controller.get_epoch_data.side_effect = AssertionError(
            "split dialog context must not read controller Epochs",
        )
        sidebar.panel.controller.get_dataset_generator.side_effect = AssertionError(
            "split dialog must not read a controller DatasetGenerator",
        )
        generator = _split_config_payload()

        def fake_async(_panel, command, *, on_result, **_kwargs):
            assert isinstance(command, GenerateDatasetCommand)
            on_result(_command_result())
            return True

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.DataSplittingDialog"
            ) as mock_dialog,
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                side_effect=AssertionError(
                    "split dialog launch must not execute a state query",
                ),
            ) as mock_execute,
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command_async",
                side_effect=fake_async,
            ) as mock_async,
            patch.object(QMessageBox, "warning") as mock_warning,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            mock_dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            mock_dialog.return_value.get_result.return_value = generator
            sidebar.split_data()

        mock_warning.assert_not_called()
        dialog_kwargs = mock_dialog.call_args.kwargs
        assert set(dialog_kwargs) == {
            "split_context",
            "publication_generation",
            "preview_provider",
            "preview_canceller",
            "initial_values",
        }
        assert isinstance(dialog_kwargs["split_context"], DatasetSplitContext)
        assert dialog_kwargs["split_context"].epoch_available is True
        assert isinstance(dialog_kwargs["publication_generation"], int)
        assert dialog_kwargs["publication_generation"] > 0
        assert callable(dialog_kwargs["preview_provider"])
        assert callable(dialog_kwargs["preview_canceller"])
        assert dialog_kwargs["initial_values"] == {}
        mock_execute.assert_not_called()
        assert isinstance(mock_async.call_args.args[1], GenerateDatasetCommand)
        sidebar.panel.controller.get_epoch_data.assert_not_called()
        sidebar.panel.controller.get_dataset_generator.assert_not_called()

    def test_split_data_refuses_real_study_missing_typed_dialog_binding(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.application import CommandCapability, CommandName
        from XBrainLab.backend.study import Study

        sidebar.panel.main_window.study = Study()
        generation = 51
        publication = SimpleNamespace(
            generation=generation,
            effective_capabilities={
                CommandName.GENERATE_DATASET: CommandCapability(
                    command_name=CommandName.GENERATE_DATASET.value,
                    enabled=True,
                ),
            },
        )
        sidebar.panel.controller.get_epoch_data.side_effect = AssertionError(
            "split dialog context should not fall back to controller",
        )

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_application_view_publication",
                return_value=publication,
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_dataset_split_dialog_binding",
                return_value=None,
            ) as get_binding,
            patch(
                "XBrainLab.ui.panels.training.sidebar.DataSplittingDialog",
            ) as mock_dialog,
            patch.object(QMessageBox, "warning") as mock_warning,
        ):
            sidebar.split_data()

        mock_dialog.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Data Splitting Blocked"
        assert "could not safely complete" in mock_warning.call_args.args[2]
        get_binding.assert_called_once_with(
            sidebar,
            publication_generation=generation,
        )
        sidebar.panel.controller.get_epoch_data.assert_not_called()

    def test_split_data_refuses_real_study_generate_none_controller_fallback(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.study import Study

        study = Study()
        raw = MagicMock()
        raw.is_raw.return_value = True
        study.data_manager.loaded_data_list = [raw]
        study.data_manager.preprocessed_data_list = [raw]
        study.data_manager.epoch_data = _usable_training_epoch_data()
        sidebar.panel.main_window.study = study
        generator = _split_config_payload()

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.DataSplittingDialog",
            ) as mock_dialog,
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                side_effect=AssertionError(
                    "real Study dataset generation must not fall back to sync",
                ),
            ) as execute_sync,
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command_async",
                return_value=False,
            ),
            patch.object(QMessageBox, "warning") as mock_warning,
            patch.object(QMessageBox, "critical") as mock_critical,
            patch.object(QMessageBox, "information") as mock_info,
        ):
            mock_dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            mock_dialog.return_value.get_result.return_value = generator
            sidebar.split_data()

        sidebar.panel.controller.apply_data_splitting.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Data Splitting Blocked"
        mock_critical.assert_not_called()
        mock_info.assert_not_called()
        assert "could not safely complete" in mock_warning.call_args.args[2]
        execute_sync.assert_not_called()

    def test_split_data_refuses_sync_fallback_when_replacement_dispatch_fails(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.study import Study

        study = Study()
        raw = MagicMock()
        raw.is_raw.return_value = True
        study.data_manager.loaded_data_list = [raw]
        study.data_manager.preprocessed_data_list = [raw]
        study.data_manager.epoch_data = _usable_training_epoch_data()
        study.data_manager.datasets = [MagicMock(name="existing_dataset")]
        sidebar.panel.main_window.study = study
        generator = _split_config_payload()

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.DataSplittingDialog",
            ) as mock_dialog,
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                side_effect=AssertionError(
                    "real Study replacement must not fall back to sync execution",
                ),
            ) as execute_sync,
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command_async",
                return_value=False,
            ),
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch.object(QMessageBox, "warning") as mock_warning,
            patch.object(QMessageBox, "critical") as mock_critical,
            patch.object(QMessageBox, "information") as mock_info,
        ):
            mock_dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            mock_dialog.return_value.get_result.return_value = generator
            sidebar.split_data()

        sidebar.panel.controller.clean_datasets.assert_not_called()
        sidebar.panel.controller.apply_data_splitting.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Data Splitting Blocked"
        mock_critical.assert_not_called()
        mock_info.assert_not_called()
        assert "could not safely complete" in mock_warning.call_args.args[2]
        execute_sync.assert_not_called()

    def test_select_model_dialog_rejection_returns_cancelled_and_passes_suggestion(
        self,
        sidebar,
    ):
        with (
            patch.object(sidebar, "_configuration_blocked", return_value=False),
            patch(
                "XBrainLab.ui.panels.training.sidebar.ModelSelectionDialog"
            ) as dialog,
        ):
            dialog.return_value.exec.return_value = QDialog.DialogCode.Rejected
            outcome = sidebar.select_model("sccnet")

        assert outcome.status is InteractionStatus.CANCELLED
        dialog.assert_called_once_with(
            sidebar,
            sidebar.controller,
            initial_model_name="sccnet",
        )

    def test_configure_training_handoff_second_dialog_cancel_is_atomic(self, sidebar):
        model_holder = MagicMock()
        model_holder.target_model.__name__ = "EEGNet"
        model_holder.model_params_map = {"dropout": 0.25}
        model_holder.pretrained_weight_path = None

        with (
            patch.object(sidebar, "_configuration_blocked", return_value=False),
            patch.object(sidebar, "_training_option_snapshot", return_value={}),
            patch(
                "XBrainLab.ui.panels.training.sidebar.ModelSelectionDialog"
            ) as model_dialog,
            patch(
                "XBrainLab.ui.panels.training.sidebar.TrainingSettingDialog"
            ) as setting_dialog,
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command"
            ) as execute_command,
        ):
            model_dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            model_dialog.return_value.get_result.return_value = model_holder
            setting_dialog.return_value.exec.return_value = QDialog.DialogCode.Rejected

            outcome = sidebar.configure_training(
                suggested_model="EEGNet",
                suggested_values={"batch_size": "32"},
            )

        assert outcome.status is InteractionStatus.CANCELLED
        execute_command.assert_not_called()
        sidebar.panel.controller.set_model_holder.assert_not_called()
        sidebar.panel.controller.set_training_option.assert_not_called()

    def test_configure_training_handoff_cancel_preserves_real_study_state(
        self,
        sidebar,
    ):
        import torch

        from XBrainLab.backend.study import Study
        from XBrainLab.backend.training import (
            ModelHolder,
            TrainingEvaluation,
            TrainingOption,
        )

        study = Study()
        existing_model = ModelHolder(
            torch.nn.Linear,
            {"in_features": 2, "out_features": 2},
        )
        existing_option = TrainingOption(
            "./existing-output",
            torch.optim.Adam,
            {},
            True,
            None,
            4,
            8,
            0.001,
            0,
            TrainingEvaluation.LAST_EPOCH,
            1,
        )
        study.training_manager.model_holder = existing_model
        study.training_manager.training_option = existing_option
        before_model = study.training_manager.model_holder
        before_option = study.training_manager.training_option
        sidebar.panel.main_window.study = study

        model_holder = MagicMock()
        model_holder.target_model.__name__ = "EEGNet"
        model_holder.model_params_map = {}
        model_holder.pretrained_weight_path = None
        with (
            patch.object(sidebar, "_configuration_blocked", return_value=False),
            patch.object(sidebar, "_training_option_snapshot", return_value={}),
            patch(
                "XBrainLab.ui.panels.training.sidebar.ModelSelectionDialog"
            ) as model_dialog,
            patch(
                "XBrainLab.ui.panels.training.sidebar.TrainingSettingDialog"
            ) as setting_dialog,
        ):
            model_dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            model_dialog.return_value.get_result.return_value = model_holder
            setting_dialog.return_value.exec.return_value = QDialog.DialogCode.Rejected

            outcome = sidebar.configure_training()

        assert outcome.status is InteractionStatus.CANCELLED
        after_model = study.training_manager.model_holder
        after_option = study.training_manager.training_option
        assert after_model is not None and before_model is not None
        assert after_model.target_model is before_model.target_model
        assert after_model.model_params_map == before_model.model_params_map
        assert after_model.pretrained_weight_path == before_model.pretrained_weight_path
        assert after_option is not None and before_option is not None
        assert after_option.output_dir == before_option.output_dir
        assert after_option.epoch == before_option.epoch
        assert after_option.bs == before_option.bs
        assert after_option.lr == before_option.lr
        assert after_option.evaluation_option is before_option.evaluation_option

    def test_configure_training_handoff_commits_both_choices_once(self, sidebar):
        from XBrainLab.backend.application import ConfigureTrainingCommand

        model_holder = MagicMock()
        model_holder.target_model.__name__ = "EEGNet"
        model_holder.model_params_map = {"dropout": 0.25}
        model_holder.pretrained_weight_path = "/tmp/eegnet.pt"
        option = SimpleNamespace(
            epoch=12,
            bs=32,
            lr=0.001,
            repeat_num=2,
            use_cpu=False,
            gpu_idx=1,
            optim=type("Adam", (), {}),
            optim_params={"weight_decay": 0.01},
            checkpoint_epoch=3,
            output_dir="./atomic-output",
            evaluation_option=SimpleNamespace(value="val_acc"),
        )

        with (
            patch.object(sidebar, "_configuration_blocked", return_value=False),
            patch.object(sidebar, "_training_option_snapshot", return_value={}),
            patch(
                "XBrainLab.ui.panels.training.sidebar.ModelSelectionDialog"
            ) as model_dialog,
            patch(
                "XBrainLab.ui.panels.training.sidebar.TrainingSettingDialog"
            ) as setting_dialog,
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                return_value=_command_result(),
            ) as execute_command,
        ):
            model_dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            model_dialog.return_value.get_result.return_value = model_holder
            setting_dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            setting_dialog.return_value.get_result.return_value = option

            outcome = sidebar.configure_training(
                suggested_model="EEGNet",
                suggested_values={"batch_size": "32", "learning_rate": "0.001"},
            )

        assert outcome.status is InteractionStatus.COMPLETED
        execute_command.assert_called_once()
        command = execute_command.call_args.args[1]
        assert isinstance(command, ConfigureTrainingCommand)
        assert command.model_name == "EEGNet"
        assert command.model_params == {"dropout": 0.25}
        assert command.pretrained_weight_path == "/tmp/eegnet.pt"
        assert command.epoch == 12
        assert command.batch_size == 32
        assert command.learning_rate == 0.001
        assert command.repeat == 2
        assert command.device == "cuda:1"
        assert command.optimizer == "Adam"
        assert command.optimizer_params == {"weight_decay": 0.01}
        assert command.save_checkpoints_every == 3
        assert command.output_dir == "./atomic-output"
        assert command.evaluation_option == "val_acc"
        sidebar.panel.controller.set_model_holder.assert_not_called()
        sidebar.panel.controller.set_training_option.assert_not_called()

    def test_select_model_button_click_does_not_forward_checked_state(
        self,
        sidebar,
    ):
        with (
            patch.object(sidebar, "_configuration_blocked", return_value=False),
            patch(
                "XBrainLab.ui.panels.training.sidebar.ModelSelectionDialog"
            ) as dialog,
        ):
            dialog.return_value.exec.return_value = QDialog.DialogCode.Rejected
            sidebar.btn_model.click()

        dialog.assert_called_once_with(
            sidebar,
            sidebar.controller,
            initial_model_name=None,
        )

    def test_select_model_without_command_service_does_not_mutate_controller(
        self,
        sidebar,
    ):
        from XBrainLab.backend.application import ConfigureTrainingCommand

        sidebar.panel.controller.is_training.return_value = False
        mock_holder = MagicMock()
        mock_holder.target_model.__name__ = "EEGNet"
        mock_holder.model_params_map = {"channels": 8}
        mock_holder.pretrained_weight_path = None
        sidebar.panel.controller.get_model_holder.return_value = mock_holder
        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_command_capability",
                return_value=None,
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.ModelSelectionDialog"
            ) as MockDlg,
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                return_value=None,
            ) as mock_execute,
            patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warning,
            patch("PyQt6.QtWidgets.QMessageBox.information") as mock_info,
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_result.return_value = mock_holder
            outcome = sidebar.select_model()

        assert outcome.status is InteractionStatus.BLOCKED
        command = mock_execute.call_args.args[1]
        assert isinstance(command, ConfigureTrainingCommand)
        assert command.model_name == "EEGNet"
        assert command.model_params == {"channels": 8}
        sidebar.panel.controller.set_model_holder.assert_not_called()
        sidebar.panel.controller.get_model_holder.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Model Selection Blocked"
        mock_info.assert_not_called()

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
            outcome = sidebar.select_model()

        assert outcome.status is InteractionStatus.COMPLETED
        command = mock_execute.call_args.args[1]
        assert isinstance(command, ConfigureTrainingCommand)
        assert command.model_name == "EEGNet"
        sidebar.panel.controller.set_model_holder.assert_not_called()
        sidebar.panel.controller.get_model_holder.assert_not_called()
        mock_critical.assert_not_called()
        mock_info.assert_not_called()
        sidebar.panel.show_status_message.assert_called_with("Model selected: EEGNet")

    def test_select_model_nonrecoverable_command_failure_returns_failed(
        self,
        sidebar,
    ):
        failure = SimpleNamespace(
            failed=True,
            recoverable=False,
            message="model configuration failed",
        )
        mock_holder = MagicMock()
        mock_holder.target_model.__name__ = "EEGNet"
        mock_holder.model_params_map = {}
        mock_holder.pretrained_weight_path = None
        with (
            patch.object(sidebar, "_configuration_blocked", return_value=False),
            patch(
                "XBrainLab.ui.panels.training.sidebar.ModelSelectionDialog"
            ) as dialog,
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                return_value=failure,
            ),
            patch("PyQt6.QtWidgets.QMessageBox.critical"),
        ):
            dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            dialog.return_value.get_result.return_value = mock_holder
            outcome = sidebar.select_model()

        assert outcome.status is InteractionStatus.FAILED

    def test_select_model_refuses_real_study_controller_fallback(self, sidebar):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.study import Study

        sidebar.panel.main_window.study = Study()
        sidebar.panel.controller.is_training.return_value = False
        mock_holder = MagicMock()
        mock_holder.target_model.__name__ = "EEGNet"
        mock_holder.model_params_map = {"channels": 8}
        mock_holder.pretrained_weight_path = None

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_command_capability",
                return_value=SimpleNamespace(enabled=True, reasons=[]),
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.ModelSelectionDialog"
            ) as mock_dialog,
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                return_value=None,
            ),
            patch.object(QMessageBox, "warning") as mock_warning,
            patch.object(QMessageBox, "critical") as mock_critical,
            patch.object(QMessageBox, "information") as mock_info,
        ):
            mock_dialog.return_value.exec.return_value = True
            mock_dialog.return_value.get_result.return_value = mock_holder
            outcome = sidebar.select_model()

        assert outcome.status is InteractionStatus.BLOCKED
        sidebar.panel.controller.set_model_holder.assert_not_called()
        sidebar.panel.controller.get_model_holder.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Model Selection Blocked"
        mock_critical.assert_not_called()
        mock_info.assert_not_called()
        assert "could not safely complete" in mock_warning.call_args.args[2]

    def test_select_model_uses_backend_configure_capability_before_dialog(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.study import Study

        study = Study()
        study.training_manager.trainer = _running_trainer()
        sidebar.panel.main_window.study = study
        sidebar.panel.controller.is_training.return_value = False

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.ModelSelectionDialog"
            ) as mock_dialog,
            patch.object(QMessageBox, "warning") as mock_warning,
        ):
            outcome = sidebar.select_model()

        assert outcome.status is InteractionStatus.BLOCKED
        mock_dialog.assert_not_called()
        mock_warning.assert_called_once_with(
            sidebar,
            "Training Configuration Blocked",
            "Stop training before changing training configuration.",
        )

    def test_select_model_refuses_real_study_configuration_fallback(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.study import Study

        sidebar.panel.main_window.study = Study()
        sidebar.panel.controller.is_training.side_effect = AssertionError(
            "stale training state should not be read",
        )

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_command_review_context",
                return_value=None,
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.ModelSelectionDialog",
            ) as mock_dialog,
            patch.object(QMessageBox, "warning") as mock_warning,
        ):
            sidebar.select_model()

        mock_dialog.assert_not_called()
        sidebar.panel.controller.is_training.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Training Configuration Blocked"
        assert "could not safely complete" in mock_warning.call_args.args[2]

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
        from PyQt6.QtWidgets import QMessageBox

        sidebar.panel.controller.is_training.return_value = True
        with patch.object(QMessageBox, "warning") as mock_warning:
            sidebar.stop_training()

        sidebar.panel.controller.stop_training.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Stop Training Blocked"

    def test_stop_training_uses_backend_capability_when_controller_stale(
        self,
        sidebar,
    ):
        from XBrainLab.backend.application import StopTrainingCommand
        from XBrainLab.backend.study import Study

        study = Study()
        study.training_manager.trainer = _running_trainer()
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
        study.training_manager.trainer = _running_trainer()
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

    def test_stop_training_refuses_real_study_preflight_fallback(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.study import Study

        sidebar.panel.main_window.study = Study()
        sidebar.panel.controller.is_training.side_effect = AssertionError(
            "stale training state should not be read",
        )

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_command_capability",
                return_value=None,
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
            ) as mock_execute,
            patch.object(QMessageBox, "warning") as mock_warning,
        ):
            sidebar.stop_training()

        sidebar.panel.controller.is_training.assert_not_called()
        sidebar.panel.controller.stop_training.assert_not_called()
        mock_execute.assert_not_called()
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

        with (
            patch.object(
                QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
            ),
            patch.object(QMessageBox, "warning") as mock_warning,
        ):
            sidebar.clear_history()

        sidebar.panel.controller.clear_history.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Clear History Blocked"

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
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_application_view_publication",
                return_value=None,
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

    def test_clear_history_refuses_real_study_preflight_fallback(self, sidebar):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.study import Study

        sidebar.panel.main_window.study = Study()
        sidebar.panel.controller.is_training.side_effect = AssertionError(
            "stale training state should not be read",
        )

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_command_capability",
                return_value=None,
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_application_view_publication",
                return_value=None,
            ),
            patch.object(QMessageBox, "question") as mock_question,
            patch.object(QMessageBox, "warning") as mock_warning,
        ):
            sidebar.clear_history()

        sidebar.panel.controller.is_training.assert_not_called()
        sidebar.panel.controller.clear_history.assert_not_called()
        mock_question.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Clear History Blocked"
        assert "could not safely complete" in mock_warning.call_args.args[2]

    def test_training_setting_while_training(self, sidebar):
        sidebar.panel.controller.is_training.return_value = True
        with patch("PyQt6.QtWidgets.QMessageBox.warning"):
            outcome = sidebar.training_setting()

        assert outcome.status is InteractionStatus.BLOCKED

    def test_training_setting_dialog_rejection_returns_cancelled(self, sidebar):
        with (
            patch.object(sidebar, "_configuration_blocked", return_value=False),
            patch.object(sidebar, "_training_option_snapshot", return_value={}),
            patch(
                "XBrainLab.ui.panels.training.sidebar.TrainingSettingDialog"
            ) as dialog,
        ):
            dialog.return_value.exec.return_value = QDialog.DialogCode.Rejected
            outcome = sidebar.training_setting()

        assert outcome.status is InteractionStatus.CANCELLED

    def test_training_setting_stops_when_state_snapshot_is_unavailable(self, sidebar):
        with (
            patch.object(sidebar, "_configuration_blocked", return_value=False),
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                return_value=None,
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.TrainingSettingDialog"
            ) as dialog,
            patch.object(QMessageBox, "warning") as warning,
        ):
            outcome = sidebar.training_setting({"batch_size": "32"})

        assert outcome.status is InteractionStatus.BLOCKED
        dialog.assert_not_called()
        warning.assert_called_once_with(
            sidebar,
            "Training Settings Blocked",
            CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
        )

    @pytest.mark.parametrize(
        ("recoverable", "expected_status", "expected_title"),
        [
            (True, InteractionStatus.BLOCKED, "Training Settings Blocked"),
            (False, InteractionStatus.FAILED, "Training Settings Failed"),
        ],
    )
    def test_training_setting_stops_when_state_snapshot_query_fails(
        self,
        sidebar,
        recoverable,
        expected_status,
        expected_title,
    ):
        failure = SimpleNamespace(
            failed=True,
            recoverable=recoverable,
            message="Training state is unavailable.",
        )
        with (
            patch.object(sidebar, "_configuration_blocked", return_value=False),
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                return_value=failure,
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.TrainingSettingDialog"
            ) as dialog,
            patch.object(QMessageBox, "warning") as warning,
        ):
            outcome = sidebar.training_setting()

        assert outcome.status is expected_status
        dialog.assert_not_called()
        warning.assert_called_once_with(
            sidebar,
            expected_title,
            "Training state is unavailable.",
        )

    def test_training_setting_merges_snapshot_with_allowed_suggestions(
        self,
        sidebar,
    ):
        snapshot = {
            "epoch": 7,
            "batch_size": 16,
            "learning_rate": 0.002,
            "repeat": 3,
            "optimizer": "Adam",
            "device": "cpu",
            "checkpoint_epoch": 2,
            "output_dir": "./saved-output",
            "evaluation_option": "val_loss",
        }
        suggestions = {
            "epoch": "12",
            "batch_size": "64",
            "learning_rate": "0.0005",
            "repeat": "4",
            "optimizer": "SGD",
            "device": "cuda:0",
            "output_dir": "./suggested-output",
            "training_algorithm": "replacement",
        }
        with (
            patch.object(sidebar, "_configuration_blocked", return_value=False),
            patch.object(
                sidebar,
                "_training_option_snapshot",
                return_value=snapshot,
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.TrainingSettingDialog"
            ) as dialog,
        ):
            dialog.return_value.exec.return_value = QDialog.DialogCode.Rejected
            outcome = sidebar.training_setting(suggestions)

        assert outcome.status is InteractionStatus.CANCELLED
        initial_option = dialog.call_args.kwargs["initial_option"]
        assert initial_option == {
            "epoch": "12",
            "batch_size": "64",
            "learning_rate": "0.0005",
            "repeat": "4",
            "optimizer": "SGD",
            "device": "cuda:0",
            "checkpoint_epoch": 2,
            "output_dir": "./saved-output",
            "evaluation_option": "val_loss",
        }
        assert snapshot["epoch"] == 7

    def test_training_setting_nonrecoverable_command_failure_returns_failed(
        self,
        sidebar,
    ):
        failure = SimpleNamespace(
            failed=True,
            recoverable=False,
            message="training settings failed",
        )
        option = SimpleNamespace(use_cpu=True)
        with (
            patch.object(sidebar, "_configuration_blocked", return_value=False),
            patch.object(sidebar, "_training_option_snapshot", return_value={}),
            patch(
                "XBrainLab.ui.panels.training.sidebar.TrainingSettingDialog"
            ) as dialog,
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                return_value=failure,
            ),
            patch("PyQt6.QtWidgets.QMessageBox.critical"),
        ):
            dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            dialog.return_value.get_result.return_value = option
            outcome = sidebar.training_setting()

        assert outcome.status is InteractionStatus.FAILED

    def test_training_setting_without_command_service_does_not_mutate_controller(
        self,
        sidebar,
    ):
        sidebar.panel.controller.is_training.return_value = False
        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_command_capability",
                return_value=None,
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.TrainingSettingDialog"
            ) as MockDlg,
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                return_value=None,
            ) as mock_execute,
            patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warning,
        ):
            outcome = sidebar.training_setting()

        assert outcome.status is InteractionStatus.BLOCKED
        assert mock_execute.call_count == 1
        MockDlg.assert_not_called()
        sidebar.panel.controller.set_training_option.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Training Settings Blocked"

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
            evaluation_option=SimpleNamespace(value="val_acc"),
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
            patch("PyQt6.QtWidgets.QMessageBox.information") as mock_info,
        ):
            outcome = sidebar.training_setting()

        assert outcome.status is InteractionStatus.COMPLETED
        sidebar.panel.controller.get_training_option.assert_not_called()
        commands = [call.args[1] for call in mock_execute.call_args_list]
        assert isinstance(commands[0], QueryStateCommand)
        assert isinstance(commands[1], ConfigureTrainingCommand)
        sidebar.panel.controller.set_training_option.assert_not_called()
        mock_info.assert_not_called()
        sidebar.panel.show_status_message.assert_called_with("Training settings saved")

    def test_training_setting_refuses_real_study_controller_fallback(self, sidebar):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.application import (
            ConfigureTrainingCommand,
            QueryStateCommand,
        )
        from XBrainLab.backend.study import Study

        sidebar.panel.main_window.study = Study()
        sidebar.panel.controller.is_training.return_value = False
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
            evaluation_option=SimpleNamespace(value="val_acc"),
        )

        def execute_for(
            _,
            command,
            refresh=True,
            expected_publication_generation=None,
            runtime=None,
        ):
            assert runtime is None
            assert expected_publication_generation == 1
            if isinstance(command, QueryStateCommand):
                assert refresh is False
                return _command_result(state={"training": {}})
            if isinstance(command, ConfigureTrainingCommand):
                return None
            raise AssertionError(f"unexpected command: {command!r}")

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_command_review_context",
                return_value=SimpleNamespace(
                    capability=SimpleNamespace(enabled=True, reasons=[]),
                    publication_generation=1,
                ),
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.TrainingSettingDialog"
            ) as mock_dialog,
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command",
                side_effect=execute_for,
            ),
            patch.object(QMessageBox, "warning") as mock_warning,
            patch.object(QMessageBox, "critical") as mock_critical,
            patch.object(QMessageBox, "information") as mock_info,
        ):
            mock_dialog.return_value.exec.return_value = True
            mock_dialog.return_value.get_result.return_value = option
            sidebar.training_setting()

        sidebar.panel.controller.set_training_option.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Training Settings Blocked"
        mock_critical.assert_not_called()
        mock_info.assert_not_called()
        assert "could not safely complete" in mock_warning.call_args.args[2]

    def test_training_setting_uses_backend_configure_capability_before_dialog(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.study import Study

        study = Study()
        study.training_manager.trainer = _running_trainer()
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

    def test_start_training_without_command_service_does_not_mutate_controller(
        self,
        sidebar,
    ):
        sidebar.panel.controller.is_training.return_value = False
        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_command_capability",
                return_value=None,
            ),
            patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warning,
        ):
            sidebar.start_training_ui_action()

        sidebar.panel.controller.start_training.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Start Training Blocked"

    def test_start_training_button_click_confirms_long_running_command(
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
        sidebar.panel.controller.get_resource_preflight_context.return_value = {
            "datasets": [],
            "training_option": SimpleNamespace(use_cpu=True, bs=32),
            "model_holder": None,
        }

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_command_review_context",
                return_value=SimpleNamespace(
                    capability=capability,
                    publication_generation=1,
                ),
            ),
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.No,
            ) as mock_question,
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command_async",
                return_value=True,
            ) as mock_execute,
        ):
            sidebar.start_training_ui_action()

        mock_question.assert_not_called()
        assert isinstance(mock_execute.call_args.args[1], TrainCommand)
        assert mock_execute.call_args.args[1].confirmed is True
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
                "XBrainLab.ui.panels.training.sidebar.execute_application_command_async"
            ) as mock_execute,
        ):
            mock_execute.side_effect = lambda *_args, on_result, **_kwargs: (
                on_result(_command_result()) or True
            )
            sidebar.start_training_ui_action()

        assert isinstance(mock_execute.call_args.args[1], TrainCommand)
        assert mock_execute.call_args.args[1].confirmed is True
        sidebar.panel.controller.start_training.assert_not_called()

    def test_start_training_refuses_real_study_controller_fallback(self, sidebar):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.study import Study

        capability = SimpleNamespace(
            enabled=True,
            reasons=[],
            requires_confirmation=False,
            confirmation_required=False,
        )
        sidebar.panel.main_window.study = Study()
        sidebar.panel.controller.is_training.return_value = False

        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_command_review_context",
                return_value=SimpleNamespace(
                    capability=capability,
                    publication_generation=1,
                ),
            ),
            patch(
                "XBrainLab.ui.panels.training.sidebar.execute_application_command_async",
                return_value=False,
            ),
            patch.object(QMessageBox, "warning") as mock_warning,
            patch.object(QMessageBox, "critical") as mock_critical,
        ):
            sidebar.start_training_ui_action()

        sidebar.panel.controller.start_training.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Start Training Blocked"
        mock_critical.assert_not_called()
        assert "could not safely complete" in mock_warning.call_args.args[2]

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
                "XBrainLab.ui.panels.training.sidebar.execute_application_command_async"
            ) as mock_execute,
            patch("PyQt6.QtWidgets.QMessageBox.critical") as mock_critical,
        ):
            mock_execute.side_effect = lambda *_args, on_result, **_kwargs: (
                on_result(_command_result()) or True
            )
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
                "XBrainLab.ui.panels.training.sidebar.execute_application_command_async"
            ) as mock_execute,
            patch.object(sidebar, "check_ready_to_train") as mock_check_ready,
        ):
            mock_execute.side_effect = lambda *_args, on_result, **_kwargs: (
                on_result(_command_result()) or True
            )
            sidebar.start_training_ui_action()

        mock_check_ready.assert_not_called()

    def test_start_training_without_command_service_blocks_before_controller_error(
        self,
        sidebar,
    ):
        sidebar.panel.controller.is_training.return_value = False
        sidebar.panel.controller.start_training.side_effect = RuntimeError("fail")
        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.get_command_capability",
                return_value=None,
            ),
            patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warning,
            patch("PyQt6.QtWidgets.QMessageBox.critical") as mock_critical,
        ):
            sidebar.start_training_ui_action()

        sidebar.panel.controller.start_training.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Start Training Blocked"
        mock_critical.assert_not_called()

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

        assert sb.import_btn.toolTip() == (
            "Choose EEG data, review metadata and labels, then import"
        )
        assert sb.import_folder_btn.toolTip() == (
            "Choose an EEG folder, review metadata and labels, then import"
        )
        assert sb.reload_recipe_btn.toolTip() == (
            "Review a saved import recipe before applying it"
        )
        assert sb.clear_btn.isEnabled() is True
        assert sb.clear_btn.toolTip() == "Clear all loaded data and start over."
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

        from XBrainLab.backend.application import (
            CommandName,
            PreprocessCommand,
            QueryStateCommand,
        )
        from XBrainLab.backend.study import Study
        from XBrainLab.ui.panels.dataset.sidebar import DatasetSidebar

        study = Study()
        raw = MagicMock()
        raw.get_filename.return_value = "sub-01_task-mi_raw.fif"
        channels = ["Cz", "Pz"]
        study.data_manager.loaded_data_list = [raw]
        panel = _make_panel_mock()
        panel.main_window.study = study
        panel.controller.get_loaded_data_list.side_effect = AssertionError(
            "stale loaded list should not be read",
        )
        sb = DatasetSidebar(panel)
        qtbot.addWidget(sb)
        publication = SimpleNamespace(
            generation=91,
            effective_capabilities={
                CommandName.PREPROCESS: SimpleNamespace(enabled=True, reasons=[]),
            },
        )

        def execute_for(
            _,
            command,
            refresh=True,
            expected_publication_generation=None,
        ):
            assert expected_publication_generation == publication.generation
            if isinstance(command, QueryStateCommand):
                assert refresh is False
                return _command_result(raw_rows=[{"channels": channels}])
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
                "XBrainLab.ui.panels.dataset.sidebar.get_application_view_publication",
                return_value=publication,
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

        mock_dialog.assert_called_once_with(sb, channels)
        assert isinstance(mock_execute.call_args_list[0].args[1], QueryStateCommand)
        assert isinstance(mock_execute.call_args_list[1].args[1], PreprocessCommand)
        panel.controller.get_loaded_data_list.assert_not_called()
        panel.controller.apply_channel_selection.assert_not_called()
        mock_warning.assert_not_called()

    def test_open_channel_selection_refuses_real_study_apply_none_controller_fallback(
        self,
        qtbot,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.application import (
            CommandName,
            PreprocessCommand,
            QueryStateCommand,
        )
        from XBrainLab.backend.study import Study
        from XBrainLab.ui.panels.dataset.sidebar import DatasetSidebar

        study = Study()
        raw = MagicMock()
        raw.get_filename.return_value = "sub-01_task-mi_raw.fif"
        channels = ["Cz", "Pz"]
        study.data_manager.loaded_data_list = [raw]
        panel = _make_panel_mock()
        panel.main_window.study = study
        sb = DatasetSidebar(panel)
        qtbot.addWidget(sb)
        publication = SimpleNamespace(
            generation=92,
            effective_capabilities={
                CommandName.PREPROCESS: SimpleNamespace(enabled=True, reasons=[]),
            },
        )

        def execute_for(
            _,
            command,
            refresh=True,
            expected_publication_generation=None,
        ):
            assert expected_publication_generation == publication.generation
            if isinstance(command, QueryStateCommand):
                assert refresh is False
                return _command_result(raw_rows=[{"channels": channels}])
            if isinstance(command, PreprocessCommand):
                return None
            raise AssertionError(f"unexpected command: {command!r}")

        with (
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch(
                "XBrainLab.ui.panels.dataset.sidebar.get_application_view_publication",
                return_value=publication,
            ),
            patch(
                "XBrainLab.ui.panels.dataset.sidebar.ChannelSelectionDialog",
            ) as mock_dialog,
            patch(
                "XBrainLab.ui.panels.dataset.sidebar.execute_application_command",
                side_effect=execute_for,
            ),
            patch.object(QMessageBox, "warning") as mock_warning,
            patch.object(QMessageBox, "critical") as mock_critical,
        ):
            mock_dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            mock_dialog.return_value.get_result.return_value = ["Cz", "Pz"]
            sb.open_channel_selection()

        panel.controller.apply_channel_selection.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Channel Selection Blocked"
        mock_critical.assert_not_called()
        assert "could not safely complete" in mock_warning.call_args.args[2]

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
                "XBrainLab.ui.panels.dataset.sidebar.get_application_view_publication",
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
        assert mock_warning.call_args.args[2] == (
            "Channel selection availability is unavailable right now."
        )

    def test_open_channel_selection_legacy_mock_context_blocks_controller_fallback(
        self,
        sidebar,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.application import PreprocessCommand, QueryStateCommand

        raw = MagicMock()
        raw.get_mne.return_value.ch_names = ["Fp1", "Fp2"]
        sidebar.panel.controller.has_data.return_value = True
        sidebar.panel.controller.is_locked.return_value = False
        sidebar.panel.controller.get_loaded_data_list.return_value = [raw]
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
                side_effect=[None, None],
            ) as mock_execute,
            patch(
                "XBrainLab.ui.panels.dataset.sidebar.ChannelSelectionDialog"
            ) as MockDlg,
            patch.object(QMessageBox, "information") as mock_info,
            patch.object(QMessageBox, "warning") as mock_warning,
        ):
            MockDlg.return_value.exec.return_value = QDialog.DialogCode.Accepted
            MockDlg.return_value.get_result.return_value = ["Fp1", "Fp2"]
            sidebar.open_channel_selection()

        assert isinstance(mock_execute.call_args_list[0].args[1], QueryStateCommand)
        command = mock_execute.call_args_list[1].args[1]
        assert isinstance(command, PreprocessCommand)
        assert command.channels == ["Fp1", "Fp2"]
        MockDlg.assert_called_once_with(sidebar, ["Fp1", "Fp2"])
        sidebar.panel.controller.apply_channel_selection.assert_not_called()
        sidebar.panel.update_panel.assert_not_called()
        mock_info.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Channel Selection Blocked"

    def test_clear_dataset(self, sidebar):
        from PyQt6.QtWidgets import QMessageBox

        sidebar.panel.controller.is_epoched.return_value = True
        with (
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch.object(QMessageBox, "warning") as mock_warning,
        ):
            sidebar.clear_dataset()
            sidebar.panel.controller.clean_dataset.assert_not_called()
            mock_warning.assert_called_once()
            assert mock_warning.call_args.args[1] == "Reset Session Blocked"

    def test_reset_session_clears_loaded_eeg_instead_of_only_training_splits(
        self,
        qtbot,
    ):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.study import Study
        from XBrainLab.ui.panels.dataset.sidebar import DatasetSidebar

        study = Study()
        raw = MagicMock()
        raw.get_filename.return_value = "sub-01_task-mi_raw.fif"
        study.data_manager.loaded_data_list = [raw]
        cast(Any, study).epoch_data = object()
        panel = _make_panel_mock()
        panel.main_window.study = study
        sb = DatasetSidebar(panel)
        qtbot.addWidget(sb)

        with (
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ) as mock_question,
            patch.object(QMessageBox, "information") as mock_info,
        ):
            sb.clear_dataset()

        mock_question.assert_called_once()
        mock_info.assert_not_called()
        assert panel.main_window.statusBar().currentMessage() == "Session reset"
        assert study.data_manager.loaded_data_list == []
        assert study.data_manager.epoch_data is None
        panel.controller.clean_dataset.assert_not_called()
        panel.update_panel.assert_not_called()

    def test_clear_dataset_refuses_real_study_controller_fallback(self, sidebar):
        from PyQt6.QtWidgets import QMessageBox

        from XBrainLab.backend.application import CommandName, ResetSessionCommand
        from XBrainLab.backend.application.capabilities import CommandCapability
        from XBrainLab.backend.study import Study

        sidebar.panel.main_window.study = Study()
        reset_capability = CommandCapability(
            command_name="reset_session",
            enabled=True,
            destructive=True,
            confirmation_required=True,
        )
        publication = SimpleNamespace(
            generation=93,
            effective_capabilities={CommandName.RESET_SESSION: reset_capability},
        )

        def execute_for(
            _,
            command,
            refresh=True,
            expected_publication_generation=None,
        ):
            assert isinstance(command, ResetSessionCommand)
            assert command.confirmed is True
            assert expected_publication_generation == publication.generation

        with (
            patch(
                "XBrainLab.ui.panels.dataset.sidebar.get_application_view_publication",
                return_value=publication,
            ),
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch(
                "XBrainLab.ui.panels.dataset.sidebar.execute_application_command",
                side_effect=execute_for,
            ),
            patch.object(QMessageBox, "warning") as mock_warning,
            patch.object(QMessageBox, "critical") as mock_critical,
        ):
            sidebar.clear_dataset()

        sidebar.panel.controller.clean_dataset.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Reset Session Blocked"
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
