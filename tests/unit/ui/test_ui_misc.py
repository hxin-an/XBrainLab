"""Batch 5: deeper coverage for data_splitting_preview, actions, import_label,
agent_manager, preprocess_plotter, saliency views, and remaining gaps."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PyQt6.QtWidgets import QDialog, QMainWindow, QWidget

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
from XBrainLab.llm.agent.response_presentation import (
    AssistantPanelNavigationRequest,
    AssistantPanelTarget,
)
from XBrainLab.llm.agent.runtime_state import (
    AssistantRuntimePhase,
    AssistantRuntimeSnapshot,
)
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.ui.components.assistant_runtime_lifecycle import (
    RuntimeActivationResult,
    RuntimeActivationStatus,
)
from XBrainLab.ui.interaction_outcome import InteractionOutcome, InteractionStatus


def _command_result(**diagnostics):
    return SimpleNamespace(
        ok=True,
        failed=False,
        message="ok",
        diagnostics=diagnostics,
    )


def _mock_interpretation_review_state(
    *,
    scan: dict[str, Any],
    preview: dict[str, Any],
    candidate: dict[str, Any],
    decision: dict[str, Any],
):
    from XBrainLab.ui.panels.dataset.data_interpretation_action_coordinator import (
        _InterpretationReviewState,
    )

    return _InterpretationReviewState(
        scan=scan,
        preview=preview,
        candidate=candidate,
        candidate_id=str(candidate.get("candidate_id") or "") or None,
        decision=decision,
        publication_generation=None,
    )


def _label_selection(
    paths: list[str],
    *,
    mode: str = "sequence",
    target_count: int | None = None,
):
    from XBrainLab.ui.dialogs.dataset.import_label_dialog import LabelImportSelection

    return LabelImportSelection(
        preview_id="label-preview-test",
        label_paths=tuple(paths),
        label_configs={path: {} for path in paths},
        mode=mode,
        target_count=target_count,
    )


def _label_preview_summary(
    paths: list[str],
    unique_labels: list[object],
    *,
    mode: str = "sequence",
    target_count: int | None = None,
    total_count: int | None = None,
) -> dict[str, object]:
    return {
        "preview_id": "label-preview-test",
        "label_paths": paths,
        "label_configs": {path: {} for path in paths},
        "mode": mode,
        "target_count": target_count,
        "total_label_count": total_count or len(unique_labels),
        "mapping_cardinality_limit": 256,
        "unique_labels": unique_labels,
    }


def _complete_saliency_coverage(method: str) -> SaliencyMethodCoverageSnapshot:
    return SaliencyMethodCoverageSnapshot(
        method=method,
        available=True,
        complete=True,
        classes=[
            SaliencyClassCoverageSnapshot(
                class_index=0,
                display_name="class 0",
                available=True,
            )
        ],
    )


def _saliency_render_publication(
    method: str = "grad",
    *,
    channel_positions: tuple[tuple[float, ...], ...] = ((0.0, 0.0, 0.1),),
) -> SaliencyRenderPublication:
    request = SaliencyRenderRequest(
        publication_generation=2,
        run=SaliencyRunIdentity(
            plan=SaliencyPlanIdentity(plan_index=0),
            run_index=0,
        ),
        method=method,
    )
    return SaliencyRenderPublication(
        request=request,
        generation=2,
        training_generation=3,
        data=SaliencyRenderData(
            method=method,
            saliency_by_class={0: np.ones((1, 1, 3))},
            class_map=((0, "class 0"),),
            event_ids={"class 0": 0},
            channel_names=("C3",),
            channel_positions=channel_positions,
            sfreq=128.0,
            tmin=0.0,
        ),
    )


# ====================================================================
# DataSplitterHolder (pure logic - no Qt needed)
# ====================================================================


class TestDataSplitterHolder:
    def _make(self, is_option=True, split_type=None):
        from XBrainLab.backend.dataset import SplitByType

        if split_type is None:
            split_type = SplitByType.TRIAL
        from XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog import (
            DataSplitterHolder,
        )

        return DataSplitterHolder(is_option, split_type)

    def test_init(self):
        h = self._make()
        assert h.is_option is True

    def test_set_split_unit_ratio(self):
        from XBrainLab.backend.dataset import SplitUnit

        h = self._make()
        h.set_split_unit_var(SplitUnit.RATIO.value)
        assert h.split_unit == SplitUnit.RATIO

    def test_set_split_unit_number(self):
        from XBrainLab.backend.dataset import SplitUnit

        h = self._make()
        h.set_split_unit_var(SplitUnit.NUMBER.value)
        assert h.split_unit == SplitUnit.NUMBER

    def test_set_split_unit_invalid(self):
        h = self._make()
        h.set_split_unit_var("non_existent_unit")
        assert h.split_unit is None

    def test_set_entry_var(self):
        h = self._make()
        h.set_entry_var("0.3")
        assert h.value_var == "0.3"

    def test_to_thread(self):
        h = self._make()
        h.set_entry_var("0.25")
        h.to_thread()

        assert h.value_var == "0.25"

    def test_not_option(self):
        h = self._make(is_option=False)
        assert h.is_option is False


# ====================================================================
# DatasetActionHandler
# ====================================================================


class TestDatasetActionHandler:
    @pytest.fixture
    def handler(self):
        from XBrainLab.ui.panels.dataset.actions import DatasetActionHandler

        panel = MagicMock()
        panel.table = MagicMock()
        panel.table.selectedIndexes.return_value = []
        panel.table.rowCount.return_value = 3
        panel.table.mapToGlobal.return_value = MagicMock()
        h = DatasetActionHandler(panel)
        h._data_interpretation._review_state_from_parts = MagicMock(
            side_effect=_mock_interpretation_review_state,
        )
        return h

    def test_controller_property(self, handler):
        handler.panel.controller = MagicMock()
        assert handler.controller is handler.panel.controller

    def test_main_window_property(self, handler):
        handler.panel.main_window = MagicMock()
        assert handler.main_window is handler.panel.main_window

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_data_locked(self, mock_mb, handler):
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = True
        outcome = handler.import_data()

        assert outcome.status is InteractionStatus.BLOCKED
        mock_mb.warning.assert_called_once()

    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_data_no_files(self, mock_mb, mock_fd, handler):
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getOpenFileNames.return_value = ([], "")
        outcome = handler.import_data()

        assert outcome.status is InteractionStatus.CANCELLED
        handler.panel.controller.import_files.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_data_exception_returns_failed(self, mock_mb, mock_fd, handler):
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getOpenFileNames.return_value = (["/a.set"], "")

        with patch.object(
            handler._data_interpretation,
            "_run_data_interpretation_import",
            side_effect=RuntimeError("scan failed"),
        ):
            outcome = handler.import_data()

        assert outcome.status is InteractionStatus.FAILED
        mock_mb.critical.assert_called_once()

    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_data_file_picker_does_not_hide_files(
        self,
        mock_mb,
        mock_fd,
        handler,
    ):
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getOpenFileNames.return_value = ([], "")

        handler.import_data()

        filter_text = mock_fd.getOpenFileNames.call_args.args[3]
        assert filter_text.startswith("All files (*)")
        assert "*.gdf" in filter_text
        assert "*.GDF" in filter_text
        assert "*.vhdr" in filter_text
        assert "*.VHDR" in filter_text

    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_data_without_command_service_does_not_import_via_controller(
        self,
        mock_mb,
        mock_fd,
        handler,
    ):
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getOpenFileNames.return_value = (["/a.set"], "")
        handler.import_data()
        handler.panel.controller.import_files.assert_not_called()
        mock_mb.warning.assert_called_once()
        assert mock_mb.warning.call_args.args[1] == "Interpretation Blocked"

    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_data_service_load_success_does_not_fallback_to_controller(
        self,
        mock_mb,
        mock_fd,
        handler,
    ):
        from XBrainLab.backend.application import LoadDataCommand

        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getOpenFileNames.return_value = (["/a.set"], "")

        with (
            patch.object(
                handler._data_interpretation,
                "_run_data_interpretation_import",
                return_value=None,
            ),
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command",
                return_value=_command_result(success_count=1),
            ) as mock_execute,
        ):
            outcome = handler.import_data()

        assert outcome.status is InteractionStatus.COMPLETED
        assert isinstance(mock_execute.call_args.args[1], LoadDataCommand)
        handler.panel.controller.import_files.assert_not_called()
        handler.panel.update_panel.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_data_refuses_real_study_direct_load_fallback(
        self,
        mock_mb,
        mock_fd,
        handler,
    ):
        from XBrainLab.backend.study import Study

        handler.panel.study = Study()
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getOpenFileNames.return_value = (["/a.set"], "")

        with (
            patch.object(
                handler._data_interpretation,
                "_run_data_interpretation_import",
                return_value=None,
            ),
            patch(
                "XBrainLab.ui.panels.dataset.actions.get_command_capability",
                return_value=None,
            ),
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command",
                return_value=None,
            ) as mock_execute,
        ):
            handler.import_data()

        mock_execute.assert_not_called()
        handler.panel.controller.import_files.assert_not_called()
        mock_mb.warning.assert_called_once()
        assert mock_mb.warning.call_args.args[1] == "Interpretation Blocked"
        assert mock_mb.warning.call_args.args[2] == (
            "Data interpretation availability is unavailable right now."
        )
        mock_mb.critical.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_data_does_not_bypass_interpretation_when_command_surface_exists(
        self,
        mock_mb,
        mock_fd,
        handler,
    ):
        from XBrainLab.backend.application import CommandName
        from XBrainLab.backend.application.capabilities import CommandCapability

        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getOpenFileNames.return_value = (["/a.set"], "")

        with (
            patch.object(
                handler._data_interpretation,
                "_run_data_interpretation_import",
                return_value=None,
            ),
            patch(
                "XBrainLab.ui.panels.dataset.actions.get_command_capability",
                return_value=CommandCapability(
                    command_name=CommandName.SCAN_SOURCE.value,
                    enabled=True,
                ),
            ),
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command",
            ) as mock_execute,
        ):
            handler.import_data()

        mock_execute.assert_not_called()
        handler.panel.controller.import_files.assert_not_called()
        mock_mb.critical.assert_called_once_with(
            handler.panel,
            "Interpretation unavailable",
            "Data Interpretation command service is unavailable.",
        )

    @patch("XBrainLab.ui.panels.dataset.actions.DataInterpretationPreviewDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_data_real_study_uses_interpretation_commands(
        self,
        mock_mb,
        mock_fd,
        mock_preview_dialog,
        handler,
    ):
        from XBrainLab.backend.application import (
            ApplyInterpretationCommand,
            ReviewInterpretationCommand,
        )

        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getOpenFileNames.return_value = (["/tmp/sub-01_task-mi.fif"], "")
        mock_preview_dialog.return_value.exec.return_value = True
        mock_preview_dialog.return_value.get_result.return_value = {
            "confirmed": False,
            "save_recipe": False,
        }
        commands = []

        def fake_execute(_panel, command, **_kwargs):
            commands.append(command)
            if isinstance(command, ReviewInterpretationCommand):
                return _command_result(
                    scan_result={
                        "scan_id": "scan-1",
                        "source_path": command.source_path,
                    },
                    preview={"summary": "Found 1 EEG file(s)."},
                    candidate={"candidate_id": "candidate-1"},
                    validation_decision={
                        "candidate_id": "candidate-1",
                        "decision": "safe",
                        "required_confirmations": [],
                        "blocked_reasons": [],
                    },
                )
            if isinstance(command, ApplyInterpretationCommand):
                return _command_result(
                    applied_interpretation={"candidate_id": "candidate-1"}
                )
            raise AssertionError(f"unexpected command: {command!r}")

        with (
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command",
                side_effect=fake_execute,
            ),
            patch.object(
                handler._data_interpretation,
                "_review_state_from_parts",
                side_effect=_mock_interpretation_review_state,
            ),
        ):
            handler.import_data()

        assert [type(command) for command in commands] == [
            ReviewInterpretationCommand,
            ApplyInterpretationCommand,
        ]
        assert commands[0].source_hint == "file"
        assert commands[-1].candidate_id == "candidate-1"
        assert commands[-1].confirmed is False
        handler.panel.controller.import_files.assert_not_called()
        handler.panel.update_panel.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_data_real_study_does_not_sync_review_when_worker_unavailable(
        self,
        mock_mb,
        mock_fd,
        handler,
        qtbot,
    ):
        from XBrainLab.backend.study import Study

        main_window = cast(Any, QMainWindow())
        qtbot.addWidget(main_window)
        main_window.study = Study()
        handler.panel.main_window = main_window
        handler.panel.study = main_window.study
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getOpenFileNames.return_value = (["/tmp/sub-01_task-mi.fif"], "")

        with (
            patch(
                "XBrainLab.ui.panels.dataset.actions.get_command_capability",
                return_value=SimpleNamespace(enabled=True, reasons=[]),
            ),
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command_async",
                return_value=False,
            ),
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command",
                side_effect=AssertionError(
                    "real Study review must not fall back to sync",
                ),
            ) as mock_execute,
        ):
            handler.import_data()

        mock_execute.assert_not_called()
        mock_mb.warning.assert_called_once()
        assert mock_mb.warning.call_args.args[1] == "Interpretation Blocked"
        assert "could not safely complete" in mock_mb.warning.call_args.args[2]

    def test_import_data_prefers_backend_scan_capability_over_stale_controller(
        self,
        handler,
    ):
        from XBrainLab.backend.study import Study

        handler.panel.study = Study()
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = True

        with (
            patch("XBrainLab.ui.panels.dataset.actions.QFileDialog") as mock_fd,
            patch.object(
                handler._data_interpretation,
                "_run_data_interpretation_import",
                return_value=InteractionOutcome.accepted(
                    "Data interpretation review started."
                ),
            ) as mock_interpret,
            patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb,
        ):
            mock_fd.getOpenFileNames.return_value = (
                ["/tmp/sub-01_task-mi_raw.fif"],
                "",
            )
            outcome = handler.import_data()

        assert outcome.status is InteractionStatus.ACCEPTED
        mock_fd.getOpenFileNames.assert_called_once()
        mock_interpret.assert_called_once_with(
            ["/tmp/sub-01_task-mi_raw.fif"],
            source_hint="file",
        )
        mock_mb.warning.assert_not_called()

    def test_import_data_blocks_real_study_when_scan_capability_is_unavailable(
        self,
        handler,
    ):
        from XBrainLab.backend.study import Study

        handler.panel.study = Study()
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.side_effect = AssertionError(
            "stale lock state should not be read",
        )

        with (
            patch(
                "XBrainLab.ui.panels.dataset.actions.get_command_capability",
                return_value=None,
            ),
            patch("XBrainLab.ui.panels.dataset.actions.QFileDialog") as mock_fd,
            patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb,
        ):
            mock_fd.getOpenFileNames.return_value = ([], "")
            outcome = handler.import_data()

        handler.panel.controller.is_locked.assert_not_called()
        mock_fd.getOpenFileNames.assert_not_called()
        assert outcome.status is InteractionStatus.BLOCKED
        mock_mb.warning.assert_called_once_with(
            handler.panel,
            "Interpretation Blocked",
            "Data interpretation availability is unavailable right now.",
        )

    @patch("XBrainLab.ui.panels.dataset.actions.DataInterpretationPreviewDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_folder_source_uses_folder_or_bids_root(
        self,
        mock_mb,
        mock_fd,
        mock_preview_dialog,
        handler,
    ):
        from XBrainLab.backend.application import (
            ApplyInterpretationCommand,
            ReviewInterpretationCommand,
        )

        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getExistingDirectory.return_value = "/tmp/bids-root"
        mock_preview_dialog.return_value.exec.return_value = True
        mock_preview_dialog.return_value.get_result.return_value = {
            "confirmed": False,
            "save_recipe": False,
        }
        commands = []

        def fake_execute(_panel, command):
            commands.append(command)
            if isinstance(command, ReviewInterpretationCommand):
                return _command_result(
                    scan_result={"source_path": command.source_path},
                    preview={"summary": "Found 1 EEG file(s)."},
                    candidate={"candidate_id": "candidate-1"},
                    validation_decision={
                        "candidate_id": "candidate-1",
                        "decision": "safe",
                        "required_confirmations": [],
                        "blocked_reasons": [],
                    },
                )
            if isinstance(command, ApplyInterpretationCommand):
                return _command_result(applied_interpretation={})
            raise AssertionError(f"unexpected command: {command!r}")

        with patch(
            "XBrainLab.ui.panels.dataset.actions.execute_application_command",
            side_effect=fake_execute,
        ):
            handler.import_folder_source()

        assert isinstance(commands[0], ReviewInterpretationCommand)
        assert commands[0].source_path == "/tmp/bids-root"
        assert [type(command) for command in commands] == [
            ReviewInterpretationCommand,
            ApplyInterpretationCommand,
        ]
        handler.panel.controller.import_files.assert_not_called()
        handler.panel.update_panel.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.BidsSubjectSelectionDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.DataInterpretationPreviewDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_bids_source_routes_bids_source_hint(
        self,
        mock_mb,
        mock_fd,
        mock_preview_dialog,
        mock_subject_dialog,
        handler,
    ):
        from XBrainLab.backend.application import (
            ApplyInterpretationCommand,
            ReviewInterpretationCommand,
            ScanSourceCommand,
        )

        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getExistingDirectory.return_value = "/tmp/bids-root"
        mock_preview_dialog.return_value.exec.return_value = True
        mock_preview_dialog.return_value.get_result.return_value = {
            "confirmed": False,
            "save_recipe": False,
        }
        mock_subject_dialog.return_value.exec.return_value = True
        mock_subject_dialog.return_value.get_result.return_value = ["02"]
        commands = []

        def fake_execute(_panel, command):
            commands.append(command)
            if isinstance(command, ScanSourceCommand):
                return _command_result(
                    bids_subject_catalog={
                        "eeg_file_count": 2,
                        "subjects": [
                            {
                                "subject": "02",
                                "label": "sub-02",
                                "eeg_file_count": 2,
                            }
                        ],
                    }
                )
            if isinstance(command, ReviewInterpretationCommand):
                return _command_result(
                    scan_result={"source_path": command.source_path},
                    preview={"summary": "Found 1 EEG file(s)."},
                    candidate={"candidate_id": "candidate-1"},
                    validation_decision={
                        "candidate_id": "candidate-1",
                        "decision": "safe",
                        "required_confirmations": [],
                        "blocked_reasons": [],
                    },
                )
            if isinstance(command, ApplyInterpretationCommand):
                return _command_result(applied_interpretation={})
            raise AssertionError(f"unexpected command: {command!r}")

        with patch(
            "XBrainLab.ui.panels.dataset.actions.execute_application_command",
            side_effect=fake_execute,
        ):
            handler.import_bids_source()

        assert isinstance(commands[0], ScanSourceCommand)
        assert commands[0].catalog_only is True
        assert isinstance(commands[1], ReviewInterpretationCommand)
        assert commands[1].source_path == "/tmp/bids-root"
        assert commands[1].source_hint == "bids"
        assert commands[1].choices["selected_bids_subjects"] == ["02"]
        mock_mb.critical.assert_not_called()

    def test_import_folder_prefers_backend_scan_capability_over_stale_controller(
        self,
        handler,
    ):
        from XBrainLab.backend.study import Study

        handler.panel.study = Study()
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = True

        with (
            patch("XBrainLab.ui.panels.dataset.actions.QFileDialog") as mock_fd,
            patch.object(
                handler._data_interpretation,
                "_run_data_interpretation_import",
                return_value=True,
            ) as mock_interpret,
            patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb,
        ):
            mock_fd.getExistingDirectory.return_value = "/tmp/bids-root"
            handler.import_folder_source()

        mock_fd.getExistingDirectory.assert_called_once()
        mock_interpret.assert_called_once_with(["/tmp/bids-root"])
        mock_mb.warning.assert_not_called()

    def test_import_folder_refuses_real_study_no_capability_lock_fallback(
        self,
        handler,
    ):
        from XBrainLab.backend.study import Study

        handler.panel.study = Study()
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.side_effect = AssertionError(
            "stale lock state should not be read",
        )

        with (
            patch(
                "XBrainLab.ui.panels.dataset.actions.get_command_capability",
                return_value=None,
            ),
            patch("XBrainLab.ui.panels.dataset.actions.QFileDialog") as mock_fd,
            patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb,
        ):
            handler.import_folder_source()

        handler.panel.controller.is_locked.assert_not_called()
        mock_fd.getExistingDirectory.assert_not_called()
        mock_mb.warning.assert_called_once()
        assert mock_mb.warning.call_args.args[1] == "Interpretation Blocked"
        assert "could not safely complete" in mock_mb.warning.call_args.args[2]

    @patch("XBrainLab.ui.panels.dataset.actions.DataInterpretationPreviewDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_reload_interpretation_recipe_reviews_then_applies(
        self,
        mock_mb,
        mock_fd,
        mock_preview_dialog,
        handler,
    ):
        from XBrainLab.backend.application import (
            ApplyInterpretationCommand,
            ReloadInterpretationRecipeCommand,
        )

        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getOpenFileName.return_value = ("/tmp/import_recipe.json", "")
        mock_preview_dialog.return_value.exec.return_value = True
        mock_preview_dialog.return_value.get_result.return_value = {
            "confirmed": True,
            "save_recipe": False,
        }
        commands = []

        def fake_execute(_panel, command):
            commands.append(command)
            if isinstance(command, ReloadInterpretationRecipeCommand):
                return _command_result(
                    scan_result={"scan_id": "scan-1"},
                    preview={"summary": "Recipe ready for review."},
                    candidate={"candidate_id": "candidate-1"},
                    validation_decision={
                        "candidate_id": "candidate-1",
                        "decision": "needs_confirmation",
                        "required_confirmations": ["Confirm recipe choices."],
                        "blocked_reasons": [],
                    },
                    recipe={"recipe_id": "recipe-1"},
                )
            if isinstance(command, ApplyInterpretationCommand):
                return _command_result(applied_interpretation={})
            raise AssertionError(f"unexpected command: {command!r}")

        with (
            patch.object(
                handler._data_interpretation,
                "_execute_interpretation_command_async",
                side_effect=lambda command, on_result, **_kwargs: (
                    on_result(fake_execute(handler.panel, command)) or True
                ),
            ),
            patch.object(
                handler._data_interpretation,
                "_review_state_from_parts",
                side_effect=_mock_interpretation_review_state,
            ),
        ):
            handler.reload_interpretation_recipe()

        assert isinstance(commands[0], ReloadInterpretationRecipeCommand)
        assert commands[0].recipe_path == "/tmp/import_recipe.json"
        assert isinstance(commands[1], ApplyInterpretationCommand)
        assert commands[1].candidate_id == "candidate-1"
        assert commands[1].confirmed is True
        handler.panel.update_panel.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.DataInterpretationPreviewDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_reload_interpretation_recipe_repreviews_blocked_label_carrier_remap(
        self,
        mock_mb,
        mock_fd,
        mock_preview_dialog,
        handler,
    ):
        from XBrainLab.backend.application import (
            ApplyInterpretationCommand,
            PreviewInterpretationCommand,
            ReloadInterpretationRecipeCommand,
            ValidateInterpretationCommand,
        )

        old_events = "/tmp/old_events.tsv"
        new_events = "/tmp/renamed_events.tsv"
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getOpenFileName.return_value = ("/tmp/import_recipe.json", "")
        mock_preview_dialog.return_value.exec.return_value = True
        mock_preview_dialog.return_value.get_result.return_value = {
            "confirmed": True,
            "save_recipe": False,
            "choices": {"label_carrier_remap": {old_events: new_events}},
        }
        commands = []

        def fake_execute(_panel, command):
            commands.append(command)
            if isinstance(command, ReloadInterpretationRecipeCommand):
                return _command_result(
                    scan_result={"scan_id": "scan-1", "label_carriers": [new_events]},
                    preview={"summary": "Recipe needs remap."},
                    candidate={
                        "candidate_id": "candidate-1",
                        "choices": {
                            "recipe_id": "recipe-1",
                            "required_label_carriers": [old_events],
                            "label_carrier_choices": {
                                old_events: {"label_field": "trial_type"},
                            },
                        },
                    },
                    validation_decision={
                        "candidate_id": "candidate-1",
                        "decision": "blocked",
                        "blocked_reasons": [
                            "Saved label/event carrier(s) were not found in the current scan: old_events.tsv.",
                        ],
                    },
                    recipe={"recipe_id": "recipe-1"},
                )
            if isinstance(command, PreviewInterpretationCommand):
                assert command.scan_id == "scan-1"
                assert command.choices["required_label_carriers"] == [old_events]
                assert command.choices["label_carrier_remap"] == {
                    old_events: new_events,
                }
                return _command_result(
                    preview={"summary": "Recipe remap ready."},
                    candidate={"candidate_id": "candidate-2"},
                )
            if isinstance(command, ValidateInterpretationCommand):
                return _command_result(
                    validation_decision={
                        "candidate_id": "candidate-2",
                        "decision": "needs_confirmation",
                        "required_confirmations": ["Confirm carrier remap."],
                        "blocked_reasons": [],
                    },
                )
            if isinstance(command, ApplyInterpretationCommand):
                return _command_result(applied_interpretation={})
            raise AssertionError(f"unexpected command: {command!r}")

        with (
            patch.object(
                handler._data_interpretation,
                "_execute_interpretation_command_async",
                side_effect=lambda command, on_result, **_kwargs: (
                    on_result(fake_execute(handler.panel, command)) or True
                ),
            ),
            patch.object(
                handler._data_interpretation,
                "_review_state_from_parts",
                side_effect=_mock_interpretation_review_state,
            ),
        ):
            handler.reload_interpretation_recipe()

        assert [type(command) for command in commands] == [
            ReloadInterpretationRecipeCommand,
            PreviewInterpretationCommand,
            ValidateInterpretationCommand,
            ApplyInterpretationCommand,
        ]
        apply_command = commands[-1]
        assert isinstance(apply_command, ApplyInterpretationCommand)
        assert apply_command.candidate_id == "candidate-2"
        assert apply_command.confirmed is True
        mock_mb.critical.assert_not_called()
        handler.panel.update_panel.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.DataInterpretationPreviewDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_reload_interpretation_recipe_repreviews_blocked_eeg_file_remap(
        self,
        mock_mb,
        mock_fd,
        mock_preview_dialog,
        handler,
    ):
        from XBrainLab.backend.application import (
            ApplyInterpretationCommand,
            PreviewInterpretationCommand,
            ReloadInterpretationRecipeCommand,
            ValidateInterpretationCommand,
        )

        old_file = "/tmp/old_raw.fif"
        new_file = "/tmp/renamed_raw.fif"
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getOpenFileName.return_value = ("/tmp/import_recipe.json", "")
        mock_preview_dialog.return_value.exec.return_value = True
        mock_preview_dialog.return_value.get_result.return_value = {
            "confirmed": True,
            "save_recipe": False,
            "choices": {"eeg_file_remap": {old_file: new_file}},
        }
        commands = []

        def fake_execute(_panel, command):
            commands.append(command)
            if isinstance(command, ReloadInterpretationRecipeCommand):
                return _command_result(
                    scan_result={"scan_id": "scan-1", "eeg_files": [new_file]},
                    preview={"summary": "Recipe needs EEG file remap."},
                    candidate={
                        "candidate_id": "candidate-1",
                        "choices": {
                            "recipe_id": "recipe-1",
                            "selected_eeg_files": [old_file],
                        },
                    },
                    validation_decision={
                        "candidate_id": "candidate-1",
                        "decision": "blocked",
                        "blocked_reasons": [
                            "Selected EEG file(s) were not found in the current scan: old_raw.fif.",
                        ],
                    },
                    recipe={"recipe_id": "recipe-1"},
                )
            if isinstance(command, PreviewInterpretationCommand):
                assert command.scan_id == "scan-1"
                assert command.choices["selected_eeg_files"] == [old_file]
                assert command.choices["eeg_file_remap"] == {
                    old_file: new_file,
                }
                return _command_result(
                    preview={"summary": "Recipe remap ready."},
                    candidate={"candidate_id": "candidate-2"},
                )
            if isinstance(command, ValidateInterpretationCommand):
                return _command_result(
                    validation_decision={
                        "candidate_id": "candidate-2",
                        "decision": "needs_confirmation",
                        "required_confirmations": ["Confirm EEG file remap."],
                        "blocked_reasons": [],
                    },
                )
            if isinstance(command, ApplyInterpretationCommand):
                return _command_result(applied_interpretation={})
            raise AssertionError(f"unexpected command: {command!r}")

        with (
            patch.object(
                handler._data_interpretation,
                "_execute_interpretation_command_async",
                side_effect=lambda command, on_result, **_kwargs: (
                    on_result(fake_execute(handler.panel, command)) or True
                ),
            ),
            patch.object(
                handler._data_interpretation,
                "_review_state_from_parts",
                side_effect=_mock_interpretation_review_state,
            ),
        ):
            handler.reload_interpretation_recipe()

        assert [type(command) for command in commands] == [
            ReloadInterpretationRecipeCommand,
            PreviewInterpretationCommand,
            ValidateInterpretationCommand,
            ApplyInterpretationCommand,
        ]
        apply_command = commands[-1]
        assert isinstance(apply_command, ApplyInterpretationCommand)
        assert apply_command.candidate_id == "candidate-2"
        assert apply_command.confirmed is True
        mock_mb.critical.assert_not_called()
        handler.panel.update_panel.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_reload_interpretation_recipe_uses_reload_capability_gate(
        self,
        mock_mb,
        mock_fd,
        handler,
    ):
        from XBrainLab.backend.application import CommandName

        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False

        def fake_capability(_panel, command_name):
            if command_name == CommandName.RELOAD_INTERPRETATION_RECIPE:
                return SimpleNamespace(
                    enabled=False,
                    reasons=["Recipe reload is unavailable."],
                )
            return SimpleNamespace(enabled=True, reasons=[])

        with patch(
            "XBrainLab.ui.panels.dataset.actions.get_command_capability",
            side_effect=fake_capability,
        ):
            handler.reload_interpretation_recipe()

        mock_mb.warning.assert_called_once()
        assert "Recipe reload is unavailable" in mock_mb.warning.call_args.args[2]
        mock_fd.getOpenFileName.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.DataInterpretationPreviewDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_data_needs_confirmation_applies_confirmed(
        self,
        mock_mb,
        mock_fd,
        mock_preview_dialog,
        handler,
    ):
        from XBrainLab.backend.application import (
            ApplyInterpretationCommand,
            ReviewInterpretationCommand,
        )

        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getOpenFileNames.return_value = (["/tmp/sub-01_task-mi.fif"], "")
        mock_preview_dialog.return_value.exec.return_value = True
        mock_preview_dialog.return_value.get_result.return_value = {
            "confirmed": True,
            "save_recipe": False,
        }
        applied: list[ApplyInterpretationCommand] = []

        def fake_execute(_panel, command):
            if isinstance(command, ReviewInterpretationCommand):
                return _command_result(
                    scan_result={"scan_id": "scan-1"},
                    preview={},
                    candidate={"candidate_id": "candidate-1"},
                    validation_decision={
                        "candidate_id": "candidate-1",
                        "decision": "needs_confirmation",
                        "required_confirmations": ["Confirm event roles."],
                        "blocked_reasons": [],
                    },
                )
            if isinstance(command, ApplyInterpretationCommand):
                applied.append(command)
                return _command_result(applied_interpretation={})
            raise AssertionError(f"unexpected command: {command!r}")

        with (
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command",
                side_effect=fake_execute,
            ),
            patch.object(
                handler._data_interpretation,
                "_review_state_from_parts",
                side_effect=_mock_interpretation_review_state,
            ),
        ):
            handler.import_data()

        assert applied
        assert applied[0].confirmed is True

    @patch("XBrainLab.ui.panels.dataset.actions.DataInterpretationPreviewDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_data_reviews_and_applies_off_ui_thread(
        self,
        mock_mb,
        mock_fd,
        mock_preview_dialog,
        handler,
    ):
        from XBrainLab.backend.application import (
            ApplyInterpretationCommand,
            ReviewInterpretationCommand,
        )

        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getOpenFileNames.return_value = (["/tmp/sub-01_task-mi.fif"], "")
        mock_preview_dialog.return_value.exec.return_value = True
        mock_preview_dialog.return_value.get_result.return_value = {
            "confirmed": False,
            "save_recipe": False,
        }
        async_commands = []
        sync_commands = []

        def fake_async(_panel, command, *, on_result, **_kwargs):
            async_commands.append(command)
            if isinstance(command, ReviewInterpretationCommand):
                on_result(
                    _command_result(
                        scan_result={},
                        preview={},
                        candidate={"candidate_id": "candidate-1"},
                        validation_decision={
                            "candidate_id": "candidate-1",
                            "decision": "safe",
                            "required_confirmations": [],
                            "blocked_reasons": [],
                        },
                    )
                )
                return True
            if isinstance(command, ApplyInterpretationCommand):
                on_result(_command_result(applied_interpretation={}))
                return True
            raise AssertionError(f"unexpected command: {command!r}")

        def fake_execute(_panel, command):
            sync_commands.append(command)
            if isinstance(command, ApplyInterpretationCommand):
                return _command_result(applied_interpretation={})
            raise AssertionError(f"unexpected command: {command!r}")

        with (
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command",
                side_effect=fake_execute,
            ),
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command_async",
                side_effect=fake_async,
            ),
        ):
            handler.import_data()

        assert [type(command) for command in async_commands] == [
            ReviewInterpretationCommand,
            ApplyInterpretationCommand,
        ]
        assert sync_commands == []
        apply_command = async_commands[-1]
        assert apply_command.candidate_id == "candidate-1"
        assert apply_command.confirmed is False

    def test_apply_interpretation_real_study_keeps_qt_event_loop_responsive(
        self,
        qtbot,
        monkeypatch,
    ):
        import threading

        from PyQt6.QtCore import QTimer

        from XBrainLab.backend.application import (
            ApplyInterpretationCommand,
            ChangedState,
            CommandResult,
        )
        from XBrainLab.backend.application.state import ApplicationStateSnapshot
        from XBrainLab.backend.study import Study
        from XBrainLab.ui import application_capabilities
        from XBrainLab.ui.panels.dataset import actions
        from XBrainLab.ui.panels.dataset.actions import DatasetActionHandler
        from XBrainLab.ui.panels.dataset.data_interpretation_action_coordinator import (
            _InterpretationReviewState,
        )

        panel = QWidget()
        qtbot.addWidget(panel)
        panel_context = cast(Any, panel)
        panel_context.study = Study()
        panel_context.set_busy = MagicMock()
        handler = DatasetActionHandler(panel)
        dialog = MagicMock()
        dialog.exec.return_value = True
        dialog.get_result.return_value = {
            "confirmed": False,
            "save_recipe": False,
        }
        worker_started = threading.Event()
        worker_release = threading.Event()
        worker_threads: list[int] = []
        result = CommandResult.success_result(
            command_name="apply_interpretation",
            message="Applied.",
            state=ApplicationStateSnapshot.empty(),
            changed_state=ChangedState(interpretation_changed=True),
            diagnostics={"applied_interpretation": {}},
        )

        class _ApplicationRuntimeFake:
            def __init__(self):
                self.commands = []

            def get_view_publication(self):
                raise AssertionError("this test does not read capability publication")

            def execute(self, command):
                assert isinstance(command, ApplyInterpretationCommand)
                self.commands.append(command)
                worker_threads.append(threading.get_ident())
                worker_started.set()
                assert worker_release.wait(timeout=2.0)
                return result

            def request_shutdown_fence(self):
                raise AssertionError("this test does not request shutdown")

            def release_shutdown_fence(self):
                raise AssertionError("this test does not release shutdown")

        runtime = _ApplicationRuntimeFake()

        monkeypatch.setattr(
            actions, "DataInterpretationPreviewDialog", lambda *_a, **_k: dialog
        )
        monkeypatch.setattr(
            application_capabilities,
            "application_ui_runtime",
            lambda _context: runtime,
        )
        review_state = _InterpretationReviewState(
            scan={},
            preview={},
            candidate={"candidate_id": "candidate-1"},
            candidate_id="candidate-1",
            decision={
                "candidate_id": "candidate-1",
                "decision": "safe",
                "required_confirmations": [],
                "blocked_reasons": [],
            },
        )

        with (
            patch.object(handler, "_show_status") as show_status,
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command",
                side_effect=AssertionError("apply must not run on the GUI thread"),
            ),
        ):
            handled = handler._data_interpretation._continue_data_interpretation_import(
                source_path="/tmp/sub-01_task-mi.fif",
                source_hint="auto",
                choices={},
                label_sources=[],
                review_state=review_state,
            )
            assert handled.status is InteractionStatus.ACCEPTED
            qtbot.waitUntil(worker_started.is_set, timeout=1000)

            heartbeat: list[bool] = []
            QTimer.singleShot(0, lambda: heartbeat.append(True))
            qtbot.waitUntil(lambda: bool(heartbeat), timeout=1000)
            assert worker_threads != [threading.get_ident()]

            worker_release.set()
            qtbot.waitUntil(lambda: show_status.call_count == 1, timeout=1000)

        assert panel_context.set_busy.call_args_list == [((True,),), ((False,),)]
        assert runtime.commands[0].resource_preflight_confirmed is False
        assert runtime.commands[0].resource_preflight_token is None

    def test_interpretation_command_helper_continues_from_compatibility_result(
        self,
        handler,
    ):
        from XBrainLab.backend.application import ScanSourceCommand

        commands = []
        expected_result = _command_result(scan_result={"scan_id": "scan-1"})

        def fake_sync(_panel, command):
            commands.append(command)
            return expected_result

        results = []
        with patch(
            "XBrainLab.ui.panels.dataset.actions.execute_application_command",
            side_effect=fake_sync,
        ):
            started = (
                handler._data_interpretation._execute_interpretation_command_async(
                    ScanSourceCommand(source_path="/tmp/eeg"),
                    on_result=results.append,
                    error_title="Source scan failed",
                )
            )

        assert started.status is InteractionStatus.COMPLETED
        assert results == [expected_result]
        assert isinstance(commands[0], ScanSourceCommand)

    def test_interpretation_command_helper_returns_false_when_unavailable(
        self,
        qtbot,
    ):
        from XBrainLab.backend.application import ScanSourceCommand
        from XBrainLab.ui.panels.dataset.actions import DatasetActionHandler

        panel = QWidget()
        panel_with_attrs = cast(Any, panel)
        panel_with_attrs.table = MagicMock()
        handler = DatasetActionHandler(panel)

        with patch(
            "XBrainLab.ui.panels.dataset.actions.execute_application_command",
            return_value=None,
        ) as mock_sync:
            started = (
                handler._data_interpretation._execute_interpretation_command_async(
                    ScanSourceCommand(source_path="/tmp/eeg"),
                    on_result=MagicMock(),
                    error_title="Source scan failed",
                )
            )

        assert started is None
        mock_sync.assert_called_once()

    @patch("XBrainLab.ui.panels.dataset.actions.DataInterpretationPreviewDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_data_repreviews_choices_that_resolve_initial_blocker(
        self,
        mock_mb,
        mock_fd,
        mock_preview_dialog,
        handler,
    ):
        from XBrainLab.backend.application import (
            ApplyInterpretationCommand,
            PreviewInterpretationCommand,
            ReviewInterpretationCommand,
            ValidateInterpretationCommand,
        )

        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getOpenFileNames.return_value = (["/tmp/sub-01_task-mi.fif"], "")
        mock_preview_dialog.return_value.exec.return_value = True
        mock_preview_dialog.return_value.get_result.return_value = {
            "confirmed": True,
            "save_recipe": False,
            "choices": {
                "metadata_overrides": {"sub-01_task-mi.fif": {"session": "session-01"}},
                "class_map": {"1": "left hand", "2": "right hand"},
            },
        }
        reviews: list[ReviewInterpretationCommand] = []
        previews: list[PreviewInterpretationCommand] = []
        validations: list[ValidateInterpretationCommand] = []
        applied: list[ApplyInterpretationCommand] = []

        def fake_execute(_panel, command):
            if isinstance(command, ReviewInterpretationCommand):
                reviews.append(command)
                return _command_result(
                    scan_result={
                        "scan_id": "scan-1",
                        "source_path": command.source_path,
                    },
                    preview={"summary": "Found 1 EEG file(s)."},
                    candidate={"candidate_id": "candidate-1"},
                    validation_decision={
                        "candidate_id": "candidate-1",
                        "decision": "blocked",
                        "required_confirmations": [],
                        "blocked_reasons": ["Event mapping is incomplete."],
                    },
                )
            if isinstance(command, PreviewInterpretationCommand):
                previews.append(command)
                return _command_result(
                    preview={"summary": "Edited event mapping ready."},
                    candidate={"candidate_id": "candidate-2"},
                )
            if isinstance(command, ValidateInterpretationCommand):
                validations.append(command)
                return _command_result(
                    validation_decision={
                        "candidate_id": "candidate-2",
                        "decision": "needs_confirmation",
                        "required_confirmations": ["Confirm event roles."],
                        "blocked_reasons": [],
                    },
                )
            if isinstance(command, ApplyInterpretationCommand):
                applied.append(command)
                return _command_result(applied_interpretation={})
            raise AssertionError(f"unexpected command: {command!r}")

        with (
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command",
                side_effect=fake_execute,
            ),
        ):
            handler.import_data()

        assert len(reviews) == 1
        assert len(previews) == 1
        assert previews[0].scan_id == "scan-1"
        assert previews[0].choices["metadata_overrides"] == {
            "sub-01_task-mi.fif": {"session": "session-01"}
        }
        assert previews[0].choices["class_map"] == {
            "1": "left hand",
            "2": "right hand",
        }
        assert [command.candidate_id for command in validations] == ["candidate-2"]
        assert applied
        assert applied[0].candidate_id == "candidate-2"
        assert applied[0].confirmed is True

    @patch("XBrainLab.ui.panels.dataset.actions.DataInterpretationPreviewDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_data_rescans_after_add_label_folder_product_flow(
        self,
        mock_mb,
        mock_fd,
        mock_preview_dialog,
        handler,
    ):
        from XBrainLab.backend.application import (
            ApplyInterpretationCommand,
            PreviewInterpretationCommand,
            ReviewInterpretationCommand,
            ValidateInterpretationCommand,
        )

        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        eeg_file = "/tmp/eeg/sub-01_task-mi_raw.fif"
        label_folder = "/tmp/labels"
        label_file = "/tmp/labels/sub-01_task-mi_events.tsv"
        mock_fd.getOpenFileNames.return_value = ([eeg_file], "")

        first_dialog = MagicMock()
        first_dialog.exec.return_value = True
        first_dialog.get_result.return_value = {
            "confirmed": False,
            "save_recipe": False,
            "label_sources_changed": True,
            "label_sources": [label_folder],
            "resume_step": "Review Metadata",
            "choices": {
                "label_carrier": "embedded_events",
                "internal_event_selection": {"selected_codes": ["769"]},
                "class_map": {"769": "left hand"},
            },
        }
        second_dialog = MagicMock()
        second_dialog.exec.return_value = True
        second_dialog.get_result.return_value = {
            "confirmed": True,
            "save_recipe": False,
            "choices": {
                "metadata_overrides": {
                    "sub-01_task-mi_raw.fif": {"subject": "S01", "task": "mi"}
                },
                "label_carrier_choices": {
                    label_file: {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "time_model": "seconds",
                        "granularity": "trial",
                        "role": "class cue labels",
                    }
                },
            },
        }
        mock_preview_dialog.side_effect = [first_dialog, second_dialog]
        commands = []

        def fake_execute(_panel, command):
            commands.append(command)
            if isinstance(command, ReviewInterpretationCommand):
                labels = [label_file] if command.label_sources else []
                review_count = len(
                    [c for c in commands if isinstance(c, ReviewInterpretationCommand)]
                )
                candidate_id = (
                    "candidate-with-labels"
                    if command.label_sources
                    else "candidate-no-labels"
                )
                return _command_result(
                    scan_result={
                        "scan_id": f"scan-{review_count}",
                        "source_path": command.source_path,
                        "eeg_files": [eeg_file],
                        "label_sources": list(command.label_sources),
                        "label_carriers": labels,
                    },
                    preview={"summary": "Found EEG data."},
                    candidate={"candidate_id": candidate_id},
                    validation_decision={
                        "candidate_id": candidate_id,
                        "decision": "needs_confirmation",
                        "required_confirmations": ["Confirm label matching."],
                        "blocked_reasons": [],
                    },
                )
            if isinstance(command, PreviewInterpretationCommand):
                return _command_result(
                    preview={"summary": "Edited label mapping ready."},
                    candidate={"candidate_id": "candidate-with-labels-reviewed"},
                )
            if isinstance(command, ValidateInterpretationCommand):
                return _command_result(
                    validation_decision={
                        "candidate_id": "candidate-with-labels-reviewed",
                        "decision": "needs_confirmation",
                        "required_confirmations": ["Confirm label matching."],
                        "blocked_reasons": [],
                    },
                )
            if isinstance(command, ApplyInterpretationCommand):
                return _command_result(applied_interpretation={})
            raise AssertionError(f"unexpected command: {command!r}")

        with (
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command",
                side_effect=fake_execute,
            ),
        ):
            handler.import_data()

        reviews = [
            command
            for command in commands
            if isinstance(command, ReviewInterpretationCommand)
        ]
        applies = [
            command
            for command in commands
            if isinstance(command, ApplyInterpretationCommand)
        ]
        previews = [
            command
            for command in commands
            if isinstance(command, PreviewInterpretationCommand)
        ]
        assert len(reviews) == 2
        assert reviews[0].label_sources == []
        assert reviews[1].label_sources == [label_folder]
        assert "label_carrier" not in reviews[1].choices
        assert "internal_event_selection" not in reviews[1].choices
        assert "class_map" not in reviews[1].choices
        second_dialog_kwargs = mock_preview_dialog.call_args_list[1].kwargs
        assert second_dialog_kwargs["initial_step"] == "Review Metadata"
        assert len(previews) == 1
        assert previews[0].scan_id == "scan-2"
        assert previews[0].choices["metadata_overrides"] == {
            "sub-01_task-mi_raw.fif": {"subject": "S01", "task": "mi"}
        }
        assert (
            previews[0].choices["label_carrier_choices"][label_file]["label_field"]
            == "trial_type"
        )
        assert applies[-1].candidate_id == "candidate-with-labels-reviewed"
        assert applies[-1].confirmed is True

    @patch("XBrainLab.ui.panels.dataset.actions.DataInterpretationPreviewDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_data_saves_recipe_when_requested(
        self,
        mock_mb,
        mock_fd,
        mock_preview_dialog,
        handler,
    ):
        from XBrainLab.backend.application import (
            ApplyInterpretationCommand,
            ReviewInterpretationCommand,
            SaveInterpretationRecipeCommand,
        )

        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getOpenFileNames.return_value = (["/tmp/sub-01_task-mi.fif"], "")
        mock_fd.getSaveFileName.return_value = ("/recipes/import_recipe.json", "")
        mock_preview_dialog.return_value.exec.return_value = True
        mock_preview_dialog.return_value.get_result.return_value = {
            "confirmed": False,
            "save_recipe": True,
        }
        saved: list[SaveInterpretationRecipeCommand] = []

        def fake_execute(_panel, command, **_kwargs):
            if isinstance(command, ReviewInterpretationCommand):
                return _command_result(
                    scan_result={"scan_id": "scan-1"},
                    preview={},
                    candidate={"candidate_id": "candidate-1"},
                    validation_decision={
                        "candidate_id": "candidate-1",
                        "decision": "safe",
                        "required_confirmations": [],
                        "blocked_reasons": [],
                    },
                )
            if isinstance(command, ApplyInterpretationCommand):
                return _command_result(applied_interpretation={})
            if isinstance(command, SaveInterpretationRecipeCommand):
                saved.append(command)
                return _command_result(import_recipe={"recipe_id": "recipe-1"})
            raise AssertionError(f"unexpected command: {command!r}")

        with (
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command",
                side_effect=fake_execute,
            ),
            patch.object(
                handler._data_interpretation,
                "_review_state_from_parts",
                side_effect=_mock_interpretation_review_state,
            ),
        ):
            handler.import_data()

        assert saved
        assert saved[0].recipe_path == "/recipes/import_recipe.json"
        mock_mb.information.assert_not_called()
        status_bar = handler.panel.main_window.statusBar.return_value
        assert "Recipe saved." in status_bar.showMessage.call_args.args[0]

    def test_save_interpretation_recipe_uses_backend_capability_before_file_dialog(
        self,
        handler,
    ):
        from XBrainLab.backend.study import Study

        handler.panel.study = Study()
        completions = []

        with (
            patch("XBrainLab.ui.panels.dataset.actions.QFileDialog") as mock_fd,
            patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb,
        ):
            handled = handler._data_interpretation._save_interpretation_recipe(
                on_complete=completions.append,
            )

        assert handled is True
        assert completions == [""]
        mock_fd.getSaveFileName.assert_not_called()
        mock_mb.warning.assert_called_once()
        assert (
            "Apply an interpretation before saving a recipe."
            in mock_mb.warning.call_args.args[2]
        )

    def test_offer_label_recipe_save_skips_confirmation_when_save_blocked(
        self,
        handler,
    ):
        from XBrainLab.backend.study import Study

        handler.panel.study = Study()
        result = SimpleNamespace(diagnostics={"recipe_updated": True})

        with (
            patch("XBrainLab.ui.panels.dataset.actions.QFileDialog") as mock_fd,
            patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb,
        ):
            message = handler._offer_label_recipe_save(result)

        assert message == "Interpretation recipe trace updated in this session."
        mock_mb.question.assert_not_called()
        mock_fd.getSaveFileName.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.DataInterpretationPreviewDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_data_blocked_preview_does_not_apply(
        self,
        mock_mb,
        mock_fd,
        mock_preview_dialog,
        handler,
    ):
        from XBrainLab.backend.application import (
            ApplyInterpretationCommand,
            ReviewInterpretationCommand,
        )

        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getOpenFileNames.return_value = (["/tmp/no-labels.txt"], "")
        mock_preview_dialog.return_value.exec.return_value = True
        mock_preview_dialog.return_value.get_result.return_value = {
            "confirmed": False,
            "save_recipe": False,
        }

        def fake_execute(_panel, command):
            if isinstance(command, ReviewInterpretationCommand):
                return _command_result(
                    scan_result={},
                    preview={},
                    candidate={"candidate_id": "candidate-1"},
                    validation_decision={
                        "candidate_id": "candidate-1",
                        "decision": "blocked",
                        "required_confirmations": [],
                        "blocked_reasons": ["No supported EEG data files were found."],
                    },
                )
            if isinstance(command, ApplyInterpretationCommand):
                raise AssertionError("blocked interpretation must not apply")
            raise AssertionError(f"unexpected command: {command!r}")

        with patch(
            "XBrainLab.ui.panels.dataset.actions.execute_application_command",
            side_effect=fake_execute,
        ):
            handler.import_data()

        mock_mb.critical.assert_called_once()
        handler.panel.controller.import_files.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.DataInterpretationPreviewDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_data_blocks_multi_parent_selection_missing_from_scan(
        self,
        mock_mb,
        mock_fd,
        mock_preview_dialog,
        handler,
    ):
        from XBrainLab.backend.application import (
            ApplyInterpretationCommand,
            ReviewInterpretationCommand,
        )

        first_file = "/mnt/a/sub-01.fif"
        second_file = "/tmp/b/sub-02.fif"
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getOpenFileNames.return_value = ([first_file, second_file], "")
        mock_preview_dialog.return_value.exec.return_value = True
        mock_preview_dialog.return_value.get_result.return_value = {
            "confirmed": False,
            "save_recipe": False,
        }
        commands = []

        def fake_execute(_panel, command):
            commands.append(command)
            if isinstance(command, ReviewInterpretationCommand):
                assert command.choices["selected_eeg_files"] == [
                    first_file,
                    second_file,
                ]
                return _command_result(
                    scan_result={
                        "scan_id": "scan-1",
                        "source_path": command.source_path,
                        "eeg_files": [first_file],
                    },
                    preview={},
                    candidate={"candidate_id": "candidate-1"},
                    validation_decision={
                        "candidate_id": "candidate-1",
                        "decision": "blocked",
                        "required_confirmations": [],
                        "blocked_reasons": [
                            (
                                "Selected EEG file(s) were not found in the current "
                                "scan: sub-02.fif."
                            )
                        ],
                    },
                )
            if isinstance(command, ApplyInterpretationCommand):
                raise AssertionError("blocked multi-parent selection must not apply")
            raise AssertionError(f"unexpected command: {command!r}")

        with patch(
            "XBrainLab.ui.panels.dataset.actions.execute_application_command",
            side_effect=fake_execute,
        ):
            handler.import_data()

        assert isinstance(commands[0], ReviewInterpretationCommand)
        assert commands[0].source_path == first_file
        mock_mb.critical.assert_called_once()
        handler.panel.controller.import_files.assert_not_called()

    def test_interpretation_source_avoids_common_root_scan(self, handler):
        source_path, choices = (
            handler._data_interpretation._interpretation_source_and_choices(
                ["/mnt/a/sub-01.fif", "/tmp/b/sub-02.fif"],
            )
        )

        assert source_path == "/mnt/a/sub-01.fif"
        assert choices == {
            "selected_eeg_files": ["/mnt/a/sub-01.fif", "/tmp/b/sub-02.fif"],
        }

    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_data_exception(self, mock_mb, mock_fd, handler):
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getOpenFileNames.return_value = (["/a.set"], "")
        handler.panel.controller.import_files.side_effect = RuntimeError("fail")
        handler.import_data()
        handler.panel.controller.import_files.assert_not_called()
        mock_mb.warning.assert_called_once()
        assert mock_mb.warning.call_args.args[1] == "Interpretation Blocked"
        mock_mb.critical.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_on_import_finished_success(self, mock_mb, handler):
        handler.on_import_finished(2, [])
        handler.panel.update_panel.assert_not_called()
        mock_mb.warning.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_on_import_finished_errors(self, mock_mb, handler):
        handler.on_import_finished(1, ["err1", "err2"])
        mock_mb.warning.assert_called_once()

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_open_smart_parser_locked(self, mock_mb, handler):
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = True
        handler.open_smart_parser()
        mock_mb.warning.assert_called_once()

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_open_smart_parser_no_data(self, mock_mb, handler):
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        handler.panel.controller.has_data.return_value = False
        handler.open_smart_parser()
        mock_mb.warning.assert_called_once()

    @patch("XBrainLab.ui.panels.dataset.actions.QInputDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMenu")
    def test_show_context_menu_no_rows(self, mock_menu, mock_input, handler):
        handler.panel.table.selectedIndexes.return_value = []
        handler.show_context_menu(MagicMock())
        # no menu exec when no rows

    @patch("XBrainLab.ui.panels.dataset.actions.QInputDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMenu")
    def test_show_context_menu_with_rows(self, mock_menu_cls, mock_input, handler):
        idx = MagicMock()
        idx.row.return_value = 0
        handler.panel.table.selectedIndexes.return_value = [idx]
        menu = MagicMock()
        mock_menu_cls.return_value = menu
        a_subj = MagicMock()
        a_sess = MagicMock()
        a_rem = MagicMock()
        menu.addAction.side_effect = [a_subj, a_sess, a_rem]
        menu.exec.return_value = a_subj
        mock_input.getText.return_value = ("S1", True)
        handler.panel.controller = MagicMock()
        with patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb:
            handler.show_context_menu(MagicMock())
        handler.panel.controller.update_metadata.assert_not_called()
        mock_mb.warning.assert_called_once()
        assert mock_mb.warning.call_args.args[1] == "Metadata Update Blocked"

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_remove_files(self, mock_mb, handler):
        mock_mb.question.return_value = MagicMock()
        mock_mb.StandardButton.Yes = MagicMock()
        mock_mb.question.return_value = mock_mb.StandardButton.Yes
        handler.panel.controller = MagicMock()
        handler._remove_files([0, 1])
        handler.panel.controller.remove_files.assert_not_called()
        mock_mb.warning.assert_called_once()
        assert mock_mb.warning.call_args.args[1] == "Remove Files Blocked"

    def test_remove_files_refuses_real_study_controller_fallback(self, handler):
        from XBrainLab.backend.study import Study

        study = Study()
        study.data_manager.loaded_data_list = [MagicMock()]
        handler.panel.study = study
        handler.panel.controller = MagicMock()

        with (
            patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb,
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command",
                return_value=None,
            ),
        ):
            mock_mb.StandardButton.Yes = 1
            mock_mb.StandardButton.No = 2
            mock_mb.question.return_value = 1
            handler._remove_files([0])

        handler.panel.controller.remove_files.assert_not_called()
        mock_mb.warning.assert_called_once()
        assert mock_mb.warning.call_args.args[1] == "Review File Removal Again"
        assert "Refresh Dataset" in mock_mb.warning.call_args.args[2]

    def test_remove_files_service_success_uses_coordinator_refresh(self, handler):
        handler.panel.controller = MagicMock()

        with (
            patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb,
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command",
                return_value=_command_result(),
            ),
        ):
            mock_mb.StandardButton.Yes = 1
            mock_mb.StandardButton.No = 2
            mock_mb.question.return_value = 1
            handler._remove_files([0])

        handler.panel.update_panel.assert_not_called()

    def test_remove_files_uses_backend_capability_before_confirm(self, handler):
        from XBrainLab.backend.study import Study

        handler.panel.study = Study()
        handler.panel.controller = MagicMock()

        with patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb:
            handler._remove_files([0, 1])

        mock_mb.question.assert_not_called()
        mock_mb.warning.assert_called_once()
        assert (
            "Load raw data before removing files." in mock_mb.warning.call_args.args[2]
        )
        handler.panel.controller.remove_files.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_batch_set_session(self, mock_mb, handler):
        handler.panel.controller = MagicMock()
        with patch("XBrainLab.ui.panels.dataset.actions.QInputDialog") as mock_input:
            mock_input.getText.return_value = ("sess1", True)
            handler._batch_set([0], "Session")
        handler.panel.controller.update_metadata.assert_not_called()
        mock_mb.warning.assert_called_once()
        assert mock_mb.warning.call_args.args[1] == "Metadata Update Blocked"

    def test_batch_set_uses_backend_capability_before_prompt(self, handler):
        from XBrainLab.backend.study import Study

        handler.panel.study = Study()
        handler.panel.controller = MagicMock()

        with (
            patch("XBrainLab.ui.panels.dataset.actions.QInputDialog") as mock_input,
            patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb,
        ):
            handler._batch_set([0], "Session")

        mock_input.getText.assert_not_called()
        mock_mb.warning.assert_called_once()
        assert (
            "Load raw data before updating metadata."
            in (mock_mb.warning.call_args.args[2])
        )
        handler.panel.controller.update_metadata.assert_not_called()

    def test_batch_set_refuses_real_study_controller_fallback(self, handler):
        from XBrainLab.backend.study import Study

        study = Study()
        study.data_manager.loaded_data_list = [MagicMock()]
        handler.panel.study = study
        handler.panel.controller = MagicMock()

        with (
            patch("XBrainLab.ui.panels.dataset.actions.QInputDialog") as mock_input,
            patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb,
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command",
                return_value=None,
            ),
        ):
            mock_input.getText.return_value = ("session-01", True)
            handler._batch_set([0], "Session")

        handler.panel.controller.update_metadata.assert_not_called()
        mock_mb.warning.assert_called_once()
        assert mock_mb.warning.call_args.args[1] == "Review Metadata Again"
        assert "Refresh Dataset" in mock_mb.warning.call_args.args[2]

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_get_target_files_no_selection_apply_all(self, mock_mb, handler):
        handler.panel.table.selectedIndexes.return_value = []
        mock_mb.StandardButton.Yes = 1
        mock_mb.StandardButton.No = 2
        mock_mb.question.return_value = 1
        handler.panel.controller = MagicMock()
        handler.panel.controller.get_loaded_data_list.return_value = ["a", "b", "c"]
        result = handler._get_target_files_for_import()
        assert len(result) == 3
        assert mock_mb.question.call_args.args[1] == "Add Labels to Loaded Data"
        assert mock_mb.question.call_args.args[2] == (
            "No files selected. Add labels to all loaded files?"
        )

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_get_target_files_no_selection_cancel(self, mock_mb, handler):
        handler.panel.table.selectedIndexes.return_value = []
        mock_mb.StandardButton.Yes = 1
        mock_mb.StandardButton.No = 2
        mock_mb.question.return_value = 2
        result = handler._get_target_files_for_import()
        assert result == []

    def test_open_smart_parser_success(self, handler):
        handler.panel.controller.is_locked.return_value = False
        handler.panel.controller.has_data.return_value = True
        handler.panel.controller.get_filenames.return_value = ["file1.set"]
        with patch("XBrainLab.ui.panels.dataset.actions.SmartParserDialog") as MockDlg:
            from PyQt6.QtWidgets import QDialog

            MockDlg.return_value.exec.return_value = QDialog.DialogCode.Accepted
            MockDlg.return_value.get_result.return_value = {"rule": "test"}
            with patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb:
                handler.open_smart_parser()
                handler.panel.controller.apply_smart_parse.assert_not_called()
                mock_mb.warning.assert_called_once()
                assert mock_mb.warning.call_args.args[1] == "Smart Parse Blocked"

    def test_open_smart_parser_uses_backend_capability(self, handler):
        from XBrainLab.backend.study import Study

        handler.panel.study = Study()
        handler.panel.controller.is_locked.return_value = False
        handler.panel.controller.has_data.return_value = True
        handler.panel.controller.get_filenames.return_value = ["file1.set"]

        with (
            patch(
                "XBrainLab.ui.panels.dataset.actions.SmartParserDialog",
            ) as mock_dialog,
            patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb,
        ):
            handler.open_smart_parser()

        mock_dialog.assert_not_called()
        mock_mb.warning.assert_called_once()
        assert (
            "Load raw data before applying smart parse."
            in (mock_mb.warning.call_args.args[2])
        )

    def test_open_smart_parser_prefers_backend_capability_over_stale_controller(
        self,
        handler,
    ):
        from XBrainLab.backend.study import Study

        study = Study()
        raw = MagicMock()
        raw.get_filename.return_value = "sub-01_task-mi_raw.fif"
        raw.get_filepath.return_value = "/tmp/sub-01_task-mi_raw.fif"
        study.data_manager.loaded_data_list = [raw]
        handler.panel.study = study
        handler.panel.controller.is_locked.return_value = True
        handler.panel.controller.has_data.return_value = False
        handler.panel.controller.get_filenames.return_value = ["sub-01_task-mi_raw.fif"]

        query_result = _command_result()
        query_result.diagnostics = {
            "raw_rows": [
                {
                    "filepath": "/tmp/sub-01_task-mi_raw.fif",
                    "filename": "sub-01_task-mi_raw.fif",
                }
            ],
        }
        apply_result = _command_result(success_count=1)

        with (
            patch(
                "XBrainLab.ui.panels.dataset.actions.SmartParserDialog",
            ) as mock_dialog,
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command",
                side_effect=[query_result, apply_result],
            ) as mock_execute,
            patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb,
        ):
            mock_dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            mock_dialog.return_value.get_result.return_value = {
                "/tmp/sub-01_task-mi_raw.fif": ("S01", "session-01")
            }
            handler.open_smart_parser()

        handler.panel.controller.get_filenames.assert_not_called()
        mock_dialog.assert_called_once_with(
            ["/tmp/sub-01_task-mi_raw.fif"],
            handler.panel,
        )
        assert mock_execute.call_count == 2
        handler.panel.controller.apply_smart_parse.assert_not_called()
        mock_mb.warning.assert_not_called()

    def test_open_smart_parser_refuses_real_study_controller_fallback(
        self,
        handler,
    ):
        from XBrainLab.backend.study import Study

        study = Study()
        raw = MagicMock()
        raw.get_filename.return_value = "sub-01_task-mi_raw.fif"
        raw.get_filepath.return_value = "/tmp/sub-01_task-mi_raw.fif"
        study.data_manager.loaded_data_list = [raw]
        handler.panel.study = study
        handler.panel.controller = MagicMock()

        query_result = _command_result()
        query_result.diagnostics = {
            "raw_rows": [
                {
                    "filepath": "/tmp/sub-01_task-mi_raw.fif",
                    "filename": "sub-01_task-mi_raw.fif",
                }
            ],
        }

        with (
            patch(
                "XBrainLab.ui.panels.dataset.actions.SmartParserDialog",
            ) as mock_dialog,
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command",
                side_effect=[query_result, None],
            ),
            patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb,
        ):
            mock_dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            mock_dialog.return_value.get_result.return_value = {
                "/tmp/sub-01_task-mi_raw.fif": ("S01", "session-01")
            }
            handler.open_smart_parser()

        handler.panel.controller.apply_smart_parse.assert_not_called()
        mock_mb.warning.assert_called_once()
        assert mock_mb.warning.call_args.args[1] == "Smart Parse Blocked"
        assert "could not safely complete" in mock_mb.warning.call_args.args[2]

    def test_open_smart_parser_refuses_real_study_no_capability_preflight_fallback(
        self,
        handler,
    ):
        from XBrainLab.backend.study import Study

        handler.panel.study = Study()
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.side_effect = AssertionError(
            "stale lock state should not be read",
        )
        handler.panel.controller.has_data.side_effect = AssertionError(
            "stale loaded-data state should not be read",
        )

        with (
            patch(
                "XBrainLab.ui.panels.dataset.actions.get_command_capability",
                return_value=None,
            ),
            patch(
                "XBrainLab.ui.panels.dataset.actions.SmartParserDialog",
            ) as mock_dialog,
            patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb,
        ):
            handler.open_smart_parser()

        handler.panel.controller.is_locked.assert_not_called()
        handler.panel.controller.has_data.assert_not_called()
        mock_dialog.assert_not_called()
        mock_mb.warning.assert_called_once()
        assert mock_mb.warning.call_args.args[1] == "Smart Parse Blocked"
        assert (
            "Load raw data before applying smart parse."
            in mock_mb.warning.call_args.args[2]
        )

    def test_open_smart_parser_refuses_real_study_filename_fallback(
        self,
        handler,
    ):
        from XBrainLab.backend.study import Study

        study = Study()
        raw = MagicMock()
        raw.get_filename.return_value = "sub-01_task-mi_raw.fif"
        raw.get_filepath.return_value = "/tmp/sub-01_task-mi_raw.fif"
        study.data_manager.loaded_data_list = [raw]
        handler.panel.study = study
        handler.panel.controller = MagicMock()

        with (
            patch(
                "XBrainLab.ui.panels.dataset.actions.SmartParserDialog",
            ) as mock_dialog,
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command",
                return_value=None,
            ),
            patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb,
        ):
            handler.open_smart_parser()

        handler.panel.controller.get_filenames.assert_not_called()
        mock_dialog.assert_not_called()
        mock_mb.warning.assert_called_once()
        assert mock_mb.warning.call_args.args[1] == "Smart Parse Blocked"
        assert "could not safely complete" in mock_mb.warning.call_args.args[2]

    def test_import_label_returns_early_no_files(self, handler):
        """import_label calls _get_target_files_for_import first; if empty, returns."""
        handler.panel.table.selectedIndexes.return_value = []
        with patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb:
            mock_mb.StandardButton.Yes = 1
            mock_mb.StandardButton.No = 2
            mock_mb.question.return_value = 2  # user cancels
            handler.import_label()
            # No warning called since user just cancelled target selection

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    @patch("XBrainLab.ui.panels.dataset.actions.ImportLabelDialog")
    def test_import_label_without_loaded_rows_guides_to_interpret_source(
        self,
        mock_dlg,
        mock_mb,
        handler,
    ):
        handler.panel.table.rowCount.return_value = 0
        handler.panel.table.selectedIndexes.return_value = []
        handler.panel.controller = MagicMock()
        handler.panel.controller.get_loaded_data_list.return_value = []

        handler.import_label()

        mock_mb.warning.assert_called_once()
        assert "Interpret a data source" in mock_mb.warning.call_args.args[2]
        mock_dlg.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    @patch("XBrainLab.ui.panels.dataset.actions.ImportLabelDialog")
    def test_import_label_respects_backend_capability_block(
        self,
        mock_dlg,
        mock_mb,
        handler,
    ):
        capability = MagicMock()
        capability.enabled = False
        capability.reasons = ["Reset the session before changing labels."]

        with patch(
            "XBrainLab.ui.panels.dataset.actions.get_command_capability",
            return_value=capability,
        ):
            handler.import_label()

        mock_mb.warning.assert_called_once()
        assert (
            "Reset the session before changing labels."
            in (mock_mb.warning.call_args.args[2])
        )
        mock_dlg.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    @patch("XBrainLab.ui.panels.dataset.actions.ImportLabelDialog")
    def test_import_label_dialog_cancelled(self, mock_dlg, mock_mb, handler):
        idx = MagicMock()
        idx.row.return_value = 0
        handler.panel.table.selectedIndexes.return_value = [idx]
        handler.panel.controller = MagicMock()
        handler.panel.controller.get_loaded_data_list.return_value = [MagicMock()]
        mock_dlg.return_value.exec.return_value = False
        handler.import_label()
        handler.panel.controller.apply_labels_sequence.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    @patch("XBrainLab.ui.panels.dataset.actions.ImportLabelDialog")
    def test_import_label_passes_target_context_to_dialog(
        self,
        mock_dlg,
        mock_mb,
        handler,
    ):
        idx = MagicMock()
        idx.row.return_value = 0
        handler.panel.table.selectedIndexes.return_value = [idx]
        handler.panel.controller = MagicMock()
        data_obj = MagicMock()
        handler.panel.controller.get_loaded_data_list.return_value = [data_obj]
        mock_dlg.return_value.exec.return_value = False

        handler.import_label()

        mock_dlg.assert_called_once_with(handler.panel, target_files=[data_obj])

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    @patch("XBrainLab.ui.panels.dataset.actions.ImportLabelDialog")
    def test_import_label_compatibility_path_uses_controller_without_product_runtime(
        self,
        mock_dlg,
        mock_mb,
        handler,
    ):
        idx = MagicMock()
        idx.row.return_value = 0
        data_obj = MagicMock()

        handler.panel.table.rowCount.return_value = 1
        handler.panel.table.selectedIndexes.return_value = [idx]
        handler.panel.capture_table_selection = None
        handler.panel.resolve_table_selection = None
        handler.panel.controller = MagicMock()
        handler.panel.controller.get_loaded_data_list.return_value = [data_obj]
        mock_dlg.return_value.exec.return_value = False

        handler.import_label()

        mock_dlg.assert_called_once_with(handler.panel, target_files=[data_obj])
        handler.panel.controller.get_loaded_data_list.assert_called_once()
        handler.panel.table.item.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_label_real_study_refuses_controller_target_fallback(
        self,
        mock_mb,
        handler,
    ):
        from PyQt6.QtWidgets import QTableWidgetItem

        from XBrainLab.backend.study import Study

        idx = MagicMock()
        idx.row.return_value = 0
        item = QTableWidgetItem("sub-01_task-mi_raw.fif")
        handler.panel.study = Study()
        handler.panel.table.rowCount.return_value = 1
        handler.panel.table.selectedIndexes.return_value = [idx]
        handler.panel.table.item.return_value = item
        handler.panel.controller = MagicMock()
        handler.panel.controller.get_loaded_data_list.side_effect = AssertionError(
            "stale loaded list should not be read",
        )

        result = handler._get_target_files_for_import()

        assert result == []
        handler.panel.controller.get_loaded_data_list.assert_not_called()
        mock_mb.warning.assert_called()

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    @patch("XBrainLab.ui.panels.dataset.actions.ImportLabelDialog")
    def test_import_label_null_label_map(self, mock_dlg, mock_mb, handler):
        idx = MagicMock()
        idx.row.return_value = 0
        handler.panel.table.selectedIndexes.return_value = [idx]
        handler.panel.controller = MagicMock()
        handler.panel.controller.get_loaded_data_list.return_value = [MagicMock()]
        mock_dlg.return_value.exec.return_value = True
        mock_dlg.return_value.get_result.return_value = (None, None)
        handler.import_label()

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    @patch("XBrainLab.ui.panels.dataset.actions.ImportLabelDialog")
    def test_import_label_single_same_length(self, mock_dlg, mock_mb, handler):
        idx = MagicMock()
        idx.row.return_value = 0
        handler.panel.table.selectedIndexes.return_value = [idx]
        handler.panel.controller = MagicMock()
        data_obj = MagicMock()
        data_obj.is_raw.return_value = False
        handler.panel.controller.get_loaded_data_list.return_value = [data_obj]
        mock_dlg.return_value.exec.return_value = True
        mock_dlg.return_value.get_result.return_value = (
            _label_selection(["file1.txt"], target_count=4),
            "mapping",
        )
        captured = []

        def _execute_async(_panel, command, *, on_result, **_kwargs):
            captured.append(command)
            on_result(_command_result(success_count=1, recipe_updated=False))
            return True

        with patch(
            "XBrainLab.ui.panels.dataset.actions.execute_application_command_async",
            side_effect=_execute_async,
        ):
            handler.import_label()

        handler.panel.controller.apply_labels_sequence.assert_not_called()
        assert len(captured) == 1
        assert captured[0].plan.preview_id == "label-preview-test"
        mock_mb.warning.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    @patch("XBrainLab.ui.panels.dataset.actions.ImportLabelDialog")
    def test_import_label_refuses_real_study_controller_fallback(
        self,
        mock_dlg,
        mock_mb,
        handler,
    ):
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QTableWidgetItem

        from XBrainLab.backend.study import Study

        idx = MagicMock()
        idx.row.return_value = 0
        data_obj = MagicMock()
        data_obj.is_raw.return_value = False
        item = QTableWidgetItem("sub-01_task-mi_raw.fif")
        item.setData(Qt.ItemDataRole.UserRole, data_obj)

        study = Study()
        study.data_manager.loaded_data_list = [data_obj]
        handler.panel.study = study
        handler.panel.table.rowCount.return_value = 1
        handler.panel.table.selectedIndexes.return_value = [idx]
        handler.panel.table.item.return_value = item
        handler.panel.controller = MagicMock()
        mock_dlg.return_value.exec.return_value = True
        mock_dlg.return_value.get_result.return_value = (
            _label_selection(["file1.txt"], target_count=4),
            "mapping",
        )

        with (
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command_async",
                return_value=False,
            ),
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command",
                return_value=None,
            ),
        ):
            handler.import_label()

        handler.panel.controller.apply_labels_sequence.assert_not_called()
        handler.panel.controller.apply_labels_batch.assert_not_called()
        mock_mb.warning.assert_called_once()
        assert mock_mb.warning.call_args.args[1] == "Add Labels Blocked"
        assert "could not safely complete" in mock_mb.warning.call_args.args[2]

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    @patch("XBrainLab.ui.panels.dataset.actions.ImportLabelDialog")
    def test_import_label_warns_when_no_labels_applied(
        self,
        mock_dlg,
        mock_mb,
        handler,
    ):
        idx = MagicMock()
        idx.row.return_value = 0
        handler.panel.table.selectedIndexes.return_value = [idx]
        handler.panel.controller = MagicMock()
        data_obj = MagicMock()
        data_obj.is_raw.return_value = False
        handler.panel.controller.get_loaded_data_list.return_value = [data_obj]
        mock_dlg.return_value.exec.return_value = True
        mock_dlg.return_value.get_result.return_value = (
            _label_selection(["file1.txt"], target_count=4),
            "mapping",
        )
        with patch(
            "XBrainLab.ui.panels.dataset.actions.execute_application_command",
            return_value=_command_result(success_count=0, recipe_updated=False),
        ):
            handler.import_label()

        mock_mb.warning.assert_called()
        assert mock_mb.warning.call_args.args[1] == "No Labels Applied"

    @patch("XBrainLab.ui.panels.dataset.actions.LabelMappingDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    @patch("XBrainLab.ui.panels.dataset.actions.ImportLabelDialog")
    def test_import_label_batch(self, mock_dlg, mock_mb, mock_map_dlg, handler):
        idx = MagicMock()
        idx.row.return_value = 0
        handler.panel.table.selectedIndexes.return_value = [idx]
        handler.panel.controller = MagicMock()
        data_obj = MagicMock()
        data_obj.is_raw.return_value = False
        data_obj.get_filepath.return_value = "/file1.set"
        handler.panel.controller.get_loaded_data_list.return_value = [data_obj]
        mock_dlg.return_value.exec.return_value = True
        mock_dlg.return_value.get_result.return_value = (
            _label_selection(["label1.txt", "label2.txt"], target_count=2),
            "mapping",
        )
        mock_map_dlg.return_value.exec.return_value = True
        mock_map_dlg.return_value.get_mapping.return_value = {
            "/file1.set": "label1.txt"
        }
        handler.panel.controller.apply_labels_batch.return_value = 1
        handler.import_label()
        handler.panel.controller.apply_labels_batch.assert_not_called()
        mock_mb.warning.assert_called_once()
        assert mock_mb.warning.call_args.args[1] == "Label Import Blocked"

    @patch("XBrainLab.ui.panels.dataset.actions.LabelMappingDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    @patch("XBrainLab.ui.panels.dataset.actions.ImportLabelDialog")
    def test_import_label_batch_mapping_cancelled(
        self,
        mock_dlg,
        mock_mb,
        mock_map_dlg,
        handler,
    ):
        idx = MagicMock()
        idx.row.return_value = 0
        handler.panel.table.selectedIndexes.return_value = [idx]
        handler.panel.controller = MagicMock()
        data_obj = MagicMock()
        data_obj.is_raw.return_value = False
        data_obj.get_filepath.return_value = "/file1.set"
        handler.panel.controller.get_loaded_data_list.return_value = [data_obj]
        mock_dlg.return_value.exec.return_value = True
        mock_dlg.return_value.get_result.return_value = (
            _label_selection(["label1.txt", "label2.txt"], target_count=2),
            "mapping",
        )
        mock_map_dlg.return_value.exec.return_value = False

        handler.import_label()

        handler.panel.controller.apply_labels_batch.assert_not_called()
        mock_mb.warning.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.LabelMappingDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    @patch("XBrainLab.ui.panels.dataset.actions.ImportLabelDialog")
    def test_import_label_batch_inconsistent_sequence_lengths_no_target_hint(
        self,
        mock_dlg,
        mock_mb,
        mock_map_dlg,
        handler,
    ):
        idx = MagicMock()
        idx.row.return_value = 0
        handler.panel.table.selectedIndexes.return_value = [idx]
        handler.panel.controller = MagicMock()
        data_obj = MagicMock()
        data_obj.is_raw.return_value = True
        data_obj.get_filepath.return_value = "/file1.set"
        handler.panel.controller.get_loaded_data_list.return_value = [data_obj]
        mock_dlg.return_value.exec.return_value = True
        mock_dlg.return_value.get_result.return_value = (
            _label_selection(["label1.txt", "label2.txt"], target_count=None),
            "mapping",
        )
        mock_map_dlg.return_value.exec.return_value = True
        mock_map_dlg.return_value.get_mapping.return_value = {
            "/file1.set": "label1.txt"
        }
        handler.panel.controller.apply_labels_batch.return_value = 1

        with patch.object(
            handler._external_label_import,
            "filter_events_for_import",
            return_value=None,
        ) as mock_filter:
            handler.import_label()

        mock_filter.assert_called_once_with([data_obj], None)
        handler.panel.controller.apply_labels_batch.assert_not_called()
        mock_mb.warning.assert_called_once()
        assert mock_mb.warning.call_args.args[1] == "Label Import Blocked"

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    @patch("XBrainLab.ui.panels.dataset.actions.ImportLabelDialog")
    def test_import_label_mixed_label_modes_rejected(self, mock_dlg, mock_mb, handler):
        idx = MagicMock()
        idx.row.return_value = 0
        handler.panel.table.selectedIndexes.return_value = [idx]
        handler.panel.controller = MagicMock()
        data_obj = MagicMock()
        data_obj.is_raw.return_value = False
        handler.panel.controller.get_loaded_data_list.return_value = [data_obj]
        mock_dlg.return_value.exec.return_value = True
        mock_dlg.return_value.get_result.return_value = (
            _label_selection(["labels.txt", "events.csv"], mode="mixed"),
            "mapping",
        )

        handler.import_label()

        handler.panel.controller.apply_labels_batch.assert_not_called()
        handler.panel.controller.apply_labels_sequence.assert_not_called()
        mock_mb.critical.assert_called_once()

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    @patch("XBrainLab.ui.panels.dataset.actions.ImportLabelDialog")
    def test_import_label_timestamp(self, mock_dlg, mock_mb, handler):
        idx = MagicMock()
        idx.row.return_value = 0
        handler.panel.table.selectedIndexes.return_value = [idx]
        handler.panel.controller = MagicMock()
        data_obj = MagicMock()
        data_obj.is_raw.return_value = False
        data_obj.get_filepath.return_value = "/file1.set"
        handler.panel.controller.get_loaded_data_list.return_value = [data_obj]
        mock_dlg.return_value.exec.return_value = True
        mock_dlg.return_value.get_result.return_value = (
            _label_selection(["label1.txt"], mode="timestamp"),
            "mapping",
        )
        handler.panel.controller.apply_labels_batch.return_value = 1
        handler.import_label()
        handler.panel.controller.apply_labels_batch.assert_not_called()
        mock_mb.warning.assert_called_once()
        assert mock_mb.warning.call_args.args[1] == "Label Import Blocked"

    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    @patch("XBrainLab.ui.panels.dataset.actions.ImportLabelDialog")
    def test_import_label_offers_to_save_updated_recipe(
        self,
        mock_dlg,
        mock_mb,
        mock_fd,
        handler,
    ):
        from XBrainLab.backend.application import (
            ImportLabelsCommand,
            SaveInterpretationRecipeCommand,
        )

        idx = MagicMock()
        idx.row.return_value = 0
        handler.panel.table.selectedIndexes.return_value = [idx]
        handler.panel.controller = MagicMock()
        data_obj = MagicMock()
        data_obj.is_raw.return_value = False
        data_obj.get_filepath.return_value = "/file1.set"
        handler.panel.controller.get_loaded_data_list.return_value = [data_obj]
        mock_dlg.return_value.exec.return_value = True
        mock_dlg.return_value.get_result.return_value = (
            _label_selection(["label1.txt"], target_count=2),
            {0: "left", 1: "right"},
        )
        mock_mb.StandardButton.Yes = 1
        mock_mb.StandardButton.No = 2
        mock_mb.question.return_value = 1
        mock_fd.getSaveFileName.return_value = ("/recipes/with_labels.json", "")
        saved: list[SaveInterpretationRecipeCommand] = []

        def fake_execute(_panel, command):
            if isinstance(command, ImportLabelsCommand):
                return _command_result(success_count=1, recipe_updated=True)
            if isinstance(command, SaveInterpretationRecipeCommand):
                saved.append(command)
                return _command_result(import_recipe={"recipe_id": "recipe-1"})
            raise AssertionError(f"unexpected command: {command!r}")

        with (
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command",
                side_effect=fake_execute,
            ),
        ):
            handler.import_label()

        assert saved
        assert saved[0].recipe_path == "/recipes/with_labels.json"
        mock_mb.information.assert_not_called()
        status_bar = handler.panel.main_window.statusBar.return_value
        assert "Recipe saved." in status_bar.showMessage.call_args.args[0]
        handler.panel.update_panel.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    @patch("XBrainLab.ui.panels.dataset.actions.ImportLabelDialog")
    def test_import_label_exception(self, mock_dlg, mock_mb, handler):
        idx = MagicMock()
        idx.row.return_value = 0
        handler.panel.table.selectedIndexes.return_value = [idx]
        handler.panel.controller = MagicMock()
        data_obj = MagicMock()
        data_obj.is_raw.return_value = False
        handler.panel.controller.get_loaded_data_list.return_value = [data_obj]
        mock_dlg.return_value.exec.return_value = True
        mock_dlg.return_value.get_result.return_value = (
            _label_selection(["f.txt"], target_count=2),
            "mapping",
        )
        handler.panel.controller.apply_labels_sequence.side_effect = RuntimeError(
            "fail"
        )
        handler.import_label()
        handler.panel.controller.apply_labels_sequence.assert_not_called()
        mock_mb.warning.assert_called_once()
        assert mock_mb.warning.call_args.args[1] == "Label Import Blocked"
        mock_mb.critical.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.EventFilterDialog")
    def test_filter_events_no_raw_files(self, mock_efd, handler):
        handler.panel.controller = MagicMock()
        data = MagicMock()
        data.is_raw.return_value = False
        data.has_event.return_value = False
        result = handler._filter_events_for_import([data], 4)
        assert result is None

    @patch("XBrainLab.ui.panels.dataset.actions.EventFilterDialog")
    def test_filter_events_with_suggestions(self, mock_efd, handler):
        handler.panel.controller = MagicMock()
        data = MagicMock()
        data.is_raw.return_value = True
        data.has_event.return_value = True
        data.get_raw_event_list.return_value = ([], {"left": 1, "right": 2})
        handler.panel.controller.get_smart_filter_suggestions.return_value = [1, 2]
        mock_efd.return_value.exec.return_value = True
        mock_efd.return_value.get_selected_ids.return_value = ["left", "right"]
        result = handler._filter_events_for_import([data], 2)
        assert result == {"left", "right"}

    @patch("XBrainLab.ui.panels.dataset.actions.EventFilterDialog")
    def test_filter_events_uses_service_suggestions_before_stale_controller(
        self,
        mock_efd,
        handler,
    ):
        from XBrainLab.backend.application import QueryStateCommand
        from XBrainLab.backend.study import Study

        handler.panel.study = Study()
        handler.panel.controller = MagicMock()
        handler.panel.controller.get_smart_filter_suggestions.side_effect = (
            AssertionError("stale smart-filter suggestions should not be read")
        )
        handler._external_label_import._remember_target_file_indices([2])
        data = MagicMock()
        data.is_raw.return_value = True
        data.has_event.return_value = True
        data.get_raw_event_list.return_value = ([], {"left": 1, "right": 2})
        mock_efd.return_value.exec.return_value = True
        mock_efd.return_value.get_selected_ids.return_value = ["left"]

        with patch(
            "XBrainLab.ui.panels.dataset.actions.execute_application_command",
            return_value=_command_result(suggestions=[1]),
        ) as mock_execute:
            result = handler._filter_events_for_import([data], 2)

        assert result == {"left"}
        handler.panel.controller.get_smart_filter_suggestions.assert_not_called()
        command = mock_execute.call_args.args[1]
        assert isinstance(command, QueryStateCommand)
        assert command.query == "smart_filter_suggestions"
        assert command.params == {"target_index": 2, "target_count": 2}
        mock_efd.return_value.set_selection.assert_called_once_with(["left"])

    @patch("XBrainLab.ui.panels.dataset.actions.EventFilterDialog")
    def test_filter_events_aggregates_suggestions_from_multiple_files(
        self, mock_efd, handler
    ):
        handler.panel.controller = MagicMock()

        data1 = MagicMock()
        data1.is_raw.return_value = True
        data1.has_event.return_value = True
        data1.get_raw_event_list.return_value = ([], {"left": 1, "right": 2})

        data2 = MagicMock()
        data2.is_raw.return_value = True
        data2.has_event.return_value = True
        data2.get_raw_event_list.return_value = ([], {"foot": 3, "tongue": 4})

        handler.panel.controller.get_smart_filter_suggestions.side_effect = [[1], [4]]
        mock_efd.return_value.exec.return_value = True
        mock_efd.return_value.get_selected_ids.return_value = ["left", "tongue"]

        result = handler._filter_events_for_import([data1, data2], 2)

        assert result == {"left", "tongue"}
        mock_efd.return_value.set_selection.assert_called_once_with(["left", "tongue"])

    @patch("XBrainLab.ui.panels.dataset.actions.EventFilterDialog")
    def test_filter_events_cancelled(self, mock_efd, handler):
        data = MagicMock()
        data.is_raw.return_value = True
        data.has_event.return_value = True
        data.get_raw_event_list.return_value = ([], {"ev1": 1})
        handler.panel.controller = MagicMock()
        mock_efd.return_value.exec.return_value = False
        result = handler._filter_events_for_import([data], 2)
        assert result is False

    def test_on_import_finished_many_errors(self, handler):
        with patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb:
            handler.on_import_finished(0, [f"err{i}" for i in range(15)])
            mock_mb.warning.assert_called_once()

    @patch("XBrainLab.ui.panels.dataset.actions.QInputDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMenu")
    def test_context_menu_remove(self, mock_menu_cls, mock_input, handler):
        idx = MagicMock()
        idx.row.return_value = 0
        handler.panel.table.selectedIndexes.return_value = [idx]
        menu = MagicMock()
        mock_menu_cls.return_value = menu
        a_subj = MagicMock()
        a_sess = MagicMock()
        a_rem = MagicMock()
        menu.addAction.side_effect = [a_subj, a_sess, a_rem]
        menu.exec.return_value = a_rem
        handler.panel.controller = MagicMock()
        with patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb:
            mock_mb.StandardButton.Yes = 1
            mock_mb.StandardButton.No = 2
            mock_mb.question.return_value = 1
            handler.show_context_menu(MagicMock())
        handler.panel.controller.remove_files.assert_not_called()
        mock_mb.warning.assert_called_once()
        assert mock_mb.warning.call_args.args[1] == "Remove Files Blocked"

    @patch("XBrainLab.ui.panels.dataset.actions.QInputDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMenu")
    def test_context_menu_session(self, mock_menu_cls, mock_input, handler):
        idx = MagicMock()
        idx.row.return_value = 0
        handler.panel.table.selectedIndexes.return_value = [idx]
        menu = MagicMock()
        mock_menu_cls.return_value = menu
        a_subj = MagicMock()
        a_sess = MagicMock()
        a_rem = MagicMock()
        menu.addAction.side_effect = [a_subj, a_sess, a_rem]
        menu.exec.return_value = a_sess
        mock_input.getText.return_value = ("sess1", True)
        handler.panel.controller = MagicMock()
        with patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb:
            handler.show_context_menu(MagicMock())
        handler.panel.controller.update_metadata.assert_not_called()
        mock_mb.warning.assert_called_once()
        assert mock_mb.warning.call_args.args[1] == "Metadata Update Blocked"

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    @patch("XBrainLab.ui.panels.dataset.actions.ImportLabelDialog")
    def test_import_label_with_event_filter(self, mock_dlg, mock_mb, handler):
        """Tests import_label where target has raw events requiring filtering."""
        idx = MagicMock()
        idx.row.return_value = 0
        handler.panel.table.selectedIndexes.return_value = [idx]
        handler.panel.controller = MagicMock()
        data_obj = MagicMock()
        data_obj.is_raw.return_value = True
        data_obj.has_event.return_value = True
        data_obj.get_raw_event_list.return_value = ([], {"left": 1, "right": 2})
        handler.panel.controller.get_loaded_data_list.return_value = [data_obj]
        handler.panel.controller.get_smart_filter_suggestions.return_value = [1]
        mock_dlg.return_value.exec.return_value = True
        mock_dlg.return_value.get_result.return_value = (
            _label_selection(["file1.txt"], target_count=4),
            "mapping",
        )
        handler.panel.controller.apply_labels_sequence.return_value = 1
        with patch("XBrainLab.ui.panels.dataset.actions.EventFilterDialog") as mock_efd:
            mock_efd.return_value.exec.return_value = True
            mock_efd.return_value.get_selected_ids.return_value = ["left"]
            handler.import_label()
        handler.panel.controller.apply_labels_sequence.assert_not_called()
        mock_mb.warning.assert_called_once()
        assert mock_mb.warning.call_args.args[1] == "Label Import Blocked"

    def test_build_label_import_plan_carries_reviewed_preview_identity(self, handler):
        selection = _label_selection(["file1.txt"], target_count=4)
        handler._external_label_import._remember_target_file_indices([2])

        plan = handler._build_label_import_plan(
            selection,
            {0: "left", 1: "right"},
            "sequence",
            file_mapping={"recording.fif": "file1.txt"},
            selected_event_names={"right", "left"},
        )

        assert plan.preview_id == "label-preview-test"
        assert plan.label_paths == ["file1.txt"]
        assert plan.label_configs == {"file1.txt": {}}
        assert plan.target_indices == [2]
        assert plan.selected_event_names == ["left", "right"]


# ====================================================================
# ImportLabelDialog
# ====================================================================


class TestImportLabelDialog:
    @pytest.fixture
    def dlg(self, qtbot) -> Any:
        from XBrainLab.ui.dialogs.dataset.import_label_dialog import ImportLabelDialog

        d = ImportLabelDialog(parent=None)
        qtbot.addWidget(d)
        return d

    def test_creates(self, dlg):
        assert dlg.label_paths == []
        assert dlg.preview_summary == {}
        assert isinstance(dlg, QDialog)

    def test_remove_files_empty(self, dlg):
        dlg.remove_files()

        assert dlg.label_paths == []
        assert dlg.preview_summary == {}
        assert dlg.file_list.count() == 0

    def test_update_unique_labels_empty(self, dlg):
        dlg.update_unique_labels()
        assert dlg.unique_labels == []
        assert "No labels" in dlg.info_label.text()

    def test_update_unique_labels_sequence(self, dlg):
        dlg._apply_preview_summary(
            _label_preview_summary(
                ["f.txt"],
                [1, 2, 3],
                target_count=4,
                total_count=4,
            )
        )
        assert dlg.unique_labels == [1, 2, 3]
        assert "3 unique" in dlg.info_label.text()

    def test_update_unique_labels_timestamp(self, dlg):
        dlg._apply_preview_summary(
            _label_preview_summary(
                ["f.csv"],
                [1, 2],
                mode="timestamp",
                total_count=2,
            )
        )
        assert dlg.unique_labels == [1, 2]

    def test_get_results_none_when_empty(self, dlg):
        lm, m = dlg.get_results()
        assert lm is None and m is None

    def test_get_result_alias(self, dlg):
        r = dlg.get_result()
        assert r == (None, None)

    def test_get_results_with_data(self, dlg):
        dlg._apply_preview_summary(
            _label_preview_summary(["f.txt"], [1, 2], target_count=2)
        )
        selection, m = dlg.get_results()
        assert selection is not None
        assert selection.label_paths == ("f.txt",)
        assert 1 in m and 2 in m

    @patch("XBrainLab.ui.dialogs.dataset.import_label_dialog.QMessageBox")
    def test_accept_empty(self, mock_mb, dlg):
        dlg.accept()
        mock_mb.warning.assert_called()

    @patch("XBrainLab.ui.dialogs.dataset.import_label_dialog.QMessageBox")
    def test_accept_no_mapping(self, mock_mb, dlg):
        dlg._apply_preview_summary(
            _label_preview_summary(["f.txt"], [1], target_count=1)
        )
        dlg.map_table.item(0, 1).setText("")
        dlg.accept()
        mock_mb.warning.assert_called()

    def test_on_file_selection_changed(self, dlg):
        dlg._apply_preview_summary(
            _label_preview_summary(["f.txt"], [1, 2], target_count=2)
        )

        dlg.on_file_selection_changed()

        assert dlg.label_paths == ["f.txt"]
        assert dlg.preview_summary["preview_id"] == "label-preview-test"

    def test_load_file(self, dlg, tmp_path):
        label_path = tmp_path / "labels.txt"
        label_path.write_text("1 2 3\n", encoding="utf-8")
        with patch.object(dlg, "_request_preview") as request_preview:
            dlg.load_file(str(label_path))
        assert dlg.label_paths == [str(label_path)]
        request_preview.assert_called_once_with()

    def test_browse_files(self, dlg):
        dlg._add_label_path("/tmp/a.txt")
        dlg._apply_preview_summary(
            _label_preview_summary(["/tmp/a.txt"], [1, 2], target_count=2)
        )
        assert dlg.file_list.count() == 1
        assert dlg.unique_labels == [1, 2]


# ====================================================================
# AgentManager deeper coverage
# ====================================================================


class TestAgentManagerDeep:
    @pytest.fixture
    def mgr(self, qtbot):
        with (
            patch("XBrainLab.ui.components.agent_manager.ChatController") as mock_cc,
            patch("XBrainLab.ui.components.agent_manager.ChatPanel"),
            patch("XBrainLab.ui.components.agent_manager.Stylesheets"),
        ):
            from XBrainLab.ui.components.agent_manager import AgentManager
            from XBrainLab.ui.components.assistant_runtime_lifecycle import (
                AssistantRuntimeLifecycle,
                RuntimeCommandAdmissionResult,
                RuntimeCommandAdmissionStatus,
            )

            mw = QMainWindow()
            qtbot.addWidget(mw)
            study = MagicMock()
            study.get_controller.return_value = MagicMock()
            runtime = MagicMock(spec=AssistantRuntimeLifecycle)
            runtime.controller = MagicMock()
            runtime.initialized = True
            runtime.current = AssistantRuntimeSnapshot(
                phase=AssistantRuntimePhase.READY,
                initialized=True,
                backend_mode="local",
                model_id="test-model",
            )
            runtime.switch_model.return_value = RuntimeActivationResult(
                RuntimeActivationStatus.SWITCHING,
                model_id="microsoft/Phi-4-mini-instruct",
            )
            runtime.active_local_runtime_blocks_model_deletion.return_value = False
            runtime.close.return_value = True
            runtime.submit.return_value = RuntimeCommandAdmissionResult(
                command_name="submit",
                status=RuntimeCommandAdmissionStatus.ACCEPTED,
                turn_id=1,
                generation=1,
            )
            runtime.reset_conversation.return_value = RuntimeCommandAdmissionResult(
                command_name="reset",
                status=RuntimeCommandAdmissionStatus.ACCEPTED,
            )
            m = AgentManager(mw, study, runtime_lifecycle=runtime)
            m.chat_controller = mock_cc.return_value
            m.chat_controller.is_processing = False
            m.chat_controller.can_accept_turn.return_value = True
            yield m

    def test_update_ai_btn_state(self, mgr):
        mgr.main_window.ai_btn = MagicMock()
        mgr.update_ai_btn_state(True)
        mgr.main_window.ai_btn.setChecked.assert_called_with(True)

    def test_toggle_float_no_dock(self, mgr):
        mgr.chat_dock = None
        mgr._place_floating_dock = MagicMock()

        mgr._toggle_float()

        mgr._place_floating_dock.assert_not_called()

    def test_toggle_float_with_dock(self, mgr, qtbot):
        from PyQt6.QtWidgets import QDockWidget

        dock = QDockWidget("test", mgr.main_window)
        mgr.chat_dock = dock
        mgr._toggle_float()
        assert dock.isFloating()

    def test_handle_user_input(self, mgr):
        mgr.handle_user_input("hello")
        mgr.chat_controller.add_user_message.assert_called_with("hello")
        mgr._assistant_runtime.submit.assert_called_with("hello", generation=1)

    def test_stop_generation(self, mgr):
        mgr.stop_generation()
        mgr._assistant_runtime.stop_generation.assert_called_once()
        mgr.chat_controller.set_processing.assert_not_called()

    def test_set_model(self, mgr):
        mgr.vram_checker = MagicMock()
        model_id = LLMConfig.default_local_model_id()
        mgr._assistant_runtime.switch_model.return_value = RuntimeActivationResult(
            RuntimeActivationStatus.SWITCHING,
            model_id=model_id,
        )

        mgr.set_model(model_id)

        mgr._assistant_runtime.switch_model.assert_called_with(model_id)
        mgr.vram_checker.check.assert_called_once_with(switching_to_local=True)

    def test_on_processing_state_changed(self, mgr):
        mgr.chat_panel = MagicMock()
        mgr.on_processing_state_changed(True)
        mgr.chat_panel.set_processing_state.assert_called_with(True)

    def test_start_new_conversation(self, mgr):
        mgr.start_new_conversation()
        mgr.chat_controller.clear_conversation.assert_called_once()
        mgr._assistant_runtime.reset_conversation.assert_called_once()

    def test_status_text_does_not_own_processing_terminal_state(self, mgr):
        mgr.on_agent_status_update("Error occurred")
        mgr.chat_controller.set_processing.assert_not_called()

    def test_on_agent_status_update_stopping_keeps_processing(self, mgr):
        mgr.on_agent_status_update("Stopping...")
        mgr.chat_controller.set_processing.assert_not_called()

    def test_close(self, mgr):
        mgr.close()
        mgr._assistant_runtime.close.assert_called_once()

    def test_handle_panel_navigation_dataset(self, mgr):
        mgr.main_window.switch_page = MagicMock()
        mgr.main_window.statusBar = MagicMock(return_value=MagicMock())
        mgr.handle_panel_navigation(
            AssistantPanelNavigationRequest(AssistantPanelTarget.DATASET)
        )
        mgr.main_window.switch_page.assert_called_with(0)

    def test_handle_panel_navigation_preprocess(self, mgr):
        mgr.main_window.switch_page = MagicMock()
        mgr.main_window.statusBar = MagicMock(return_value=MagicMock())
        mgr.handle_panel_navigation(
            AssistantPanelNavigationRequest(AssistantPanelTarget.PREPROCESS)
        )
        mgr.main_window.switch_page.assert_called_with(1)

    def test_handle_panel_navigation_training(self, mgr):
        mgr.main_window.switch_page = MagicMock()
        mgr.main_window.statusBar = MagicMock(return_value=MagicMock())
        mgr.handle_panel_navigation(
            AssistantPanelNavigationRequest(AssistantPanelTarget.TRAINING)
        )
        mgr.main_window.switch_page.assert_called_with(2)

    def test_handle_panel_navigation_evaluation(self, mgr):
        mgr.main_window.switch_page = MagicMock()
        mgr.main_window.statusBar = MagicMock(return_value=MagicMock())
        mgr.handle_panel_navigation(
            AssistantPanelNavigationRequest(AssistantPanelTarget.EVALUATION)
        )
        mgr.main_window.switch_page.assert_called_with(3)

    def test_handle_panel_navigation_visualization_with_view(self, mgr):
        ready_callbacks = []

        def _switch_page(index, *, on_ready=None):
            assert index == 4
            ready_callbacks.append(on_ready)
            return False

        mgr.main_window.switch_page = MagicMock(side_effect=_switch_page)
        target = MagicMock()
        mgr.main_window.stack = MagicMock()
        mgr.main_window.stack.widget.return_value = target
        status_bar = MagicMock()
        mgr.main_window.statusBar = MagicMock(return_value=status_bar)
        mgr.handle_panel_navigation(
            AssistantPanelNavigationRequest(
                AssistantPanelTarget.VISUALIZATION,
                view_mode="saliency_map",
            )
        )

        mgr.main_window.switch_page.assert_called_once()
        assert mgr.main_window.switch_page.call_args.args == (4,)
        callback = mgr.main_window.switch_page.call_args.kwargs["on_ready"]
        assert callback is ready_callbacks[0]
        assert callable(callback)
        target.tabs.setCurrentIndex.assert_not_called()
        status_bar.showMessage.assert_called_with("Opening Visualization...")

        callback(target)

        target.tabs.setCurrentIndex.assert_called_with(0)
        status_bar.showMessage.assert_called_with("Opened Visualization panel.")

    def test_handle_panel_navigation_rejects_untyped_payload(self, mgr):
        mgr.chat_panel = MagicMock()
        mgr.main_window.switch_page = MagicMock()
        mgr.handle_panel_navigation({"panel": "unknown_panel"})

        mgr.main_window.switch_page.assert_not_called()
        mgr.chat_panel.show_notice.assert_called_once_with(
            "The requested XBrainLab view could not be opened."
        )

    def test_prepare_model_deletion_no_controller(self, mgr):
        mgr._assistant_runtime.controller = None
        assert mgr.prepare_model_deletion("model") is True

    def test_prepare_model_deletion_local_mode(self, mgr):
        mgr._assistant_runtime.active_local_runtime_blocks_model_deletion.return_value = True
        with patch("XBrainLab.ui.components.agent_manager.QMessageBox.warning"):
            assert mgr.prepare_model_deletion("model") is False

    def test_prepare_model_deletion_gemini(self, mgr):
        mgr._assistant_runtime.active_local_runtime_blocks_model_deletion.return_value = True
        with patch("XBrainLab.ui.components.agent_manager.QMessageBox.warning"):
            assert mgr.prepare_model_deletion("model") is False

    def test_check_vram_not_local(self, mgr):
        mgr.check_vram_conflict(switching_to_local=False)
        # no warning when not local

    @patch("XBrainLab.ui.components.vram_checker.QMessageBox")
    def test_check_vram_local_and_3d(self, mock_mb, mgr):
        mgr.main_window.visualization_panel = MagicMock()
        mgr.check_vram_conflict(switching_to_local=True, switching_to_3d=True)
        mock_mb.warning.assert_called_once()

    def test_on_viz_tab_changed_non_3d(self, mgr):
        mgr.check_vram_conflict = MagicMock()
        mgr.on_viz_tab_changed(0)
        mgr.check_vram_conflict.assert_not_called()

    def test_on_viz_tab_changed_3d(self, mgr):
        mgr.vram_checker = MagicMock()
        mgr.on_viz_tab_changed(3)
        mgr.vram_checker.on_viz_tab_changed.assert_called_with(3)


# ====================================================================
# SaliencyTopographicMapWidget
# ====================================================================


class TestTopoMapView:
    @pytest.fixture
    def widget(self, qtbot):
        from XBrainLab.ui.panels.visualization.saliency_views.topomap_view import (
            SaliencyTopographicMapWidget,
        )

        w = SaliencyTopographicMapWidget()
        qtbot.addWidget(w)
        return w

    def test_creates(self, widget):
        assert isinstance(widget, QWidget)

    def test_show_warning(self, widget):
        widget.show_warning("test warning")
        assert "test warning" in widget.error_label.text()

    def test_update_plot_rejects_unpublished_render_data(self, widget):
        widget.update_plot(MagicMock(), False)
        assert "publication is invalid" in widget.error_label.text()

    @patch(
        "XBrainLab.ui.panels.visualization.saliency_views.topomap_view.VisualizerType"
    )
    def test_update_plot_no_montage(self, mock_vt, widget):
        widget.set_saliency_coverage(_complete_saliency_coverage("grad"))
        widget.update_plot(
            _saliency_render_publication(channel_positions=()),
            False,
        )
        assert "Montage" in widget.error_label.text()
        mock_vt.SaliencyTopoMap.value.assert_not_called()

    @patch(
        "XBrainLab.ui.panels.visualization.saliency_views.topomap_view.VisualizerType"
    )
    def test_update_plot_success(self, mock_vt, widget):
        publication = _saliency_render_publication()
        widget.set_saliency_coverage(_complete_saliency_coverage("grad"))
        widget._render_figure_async = MagicMock()

        widget.update_plot(publication, False)

        widget._render_figure_async.assert_called_once()
        assert (
            widget._render_figure_async.call_args.kwargs["publication_generation"]
            == publication.generation
        )
        mock_vt.SaliencyTopoMap.value.assert_not_called()

    @patch(
        "XBrainLab.ui.panels.visualization.saliency_views.topomap_view.VisualizerType"
    )
    def test_render_plot_delegates_typed_data(self, mock_vt, widget):
        publication = _saliency_render_publication()
        mock_vt.SaliencyTopoMap.value.return_value.get_plt.return_value = None

        assert widget._render_plot(publication.data, False) is None

        mock_vt.SaliencyTopoMap.value.assert_called_once_with(publication.data)
        mock_vt.SaliencyTopoMap.value.return_value.get_plt.assert_called_once_with(
            method="grad",
            absolute=False,
        )


# ====================================================================
# SaliencySpectrogramWidget
# ====================================================================


class TestSpectrogramView:
    @pytest.fixture
    def widget(self, qtbot):
        from XBrainLab.ui.panels.visualization.saliency_views.spectrogram_view import (
            SaliencySpectrogramWidget,
        )

        w = SaliencySpectrogramWidget()
        qtbot.addWidget(w)
        return w

    def test_creates(self, widget):
        assert isinstance(widget, QWidget)

    def test_update_plot_rejects_unpublished_render_data(self, widget):
        widget.update_plot(MagicMock(), False)
        assert "publication is invalid" in widget.error_label.text()

    @patch(
        "XBrainLab.ui.panels.visualization.saliency_views.spectrogram_view.VisualizerType"
    )
    def test_update_plot_success(self, mock_vt, widget):
        publication = _saliency_render_publication()
        widget.set_saliency_coverage(_complete_saliency_coverage("grad"))
        widget._render_figure_async = MagicMock()

        widget.update_plot(publication, False)

        widget._render_figure_async.assert_called_once()
        assert (
            widget._render_figure_async.call_args.kwargs["publication_generation"]
            == publication.generation
        )
        mock_vt.SaliencySpectrogramMap.value.assert_not_called()

    @patch(
        "XBrainLab.ui.panels.visualization.saliency_views.spectrogram_view.VisualizerType"
    )
    def test_render_plot_delegates_typed_data(self, mock_vt, widget):
        publication = _saliency_render_publication()
        mock_vt.SaliencySpectrogramMap.value.return_value.get_plt.return_value = None

        assert widget._render_plot(publication.data) is None

        mock_vt.SaliencySpectrogramMap.value.assert_called_once_with(publication.data)
        mock_vt.SaliencySpectrogramMap.value.return_value.get_plt.assert_called_once_with(
            method="grad",
        )

    @patch(
        "XBrainLab.ui.panels.visualization.saliency_views.spectrogram_view.VisualizerType"
    )
    def test_render_plot_propagates_visualizer_failure(self, mock_vt, widget):
        publication = _saliency_render_publication()
        mock_vt.SaliencySpectrogramMap.value.side_effect = RuntimeError("fail")

        with pytest.raises(RuntimeError, match="fail"):
            widget._render_plot(publication.data)
