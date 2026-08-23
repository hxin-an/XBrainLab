"""Dataset workflow and saliency-view behavior at public UI boundaries."""

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
from XBrainLab.ui.components.modal_presentation import AlertSeverity
from XBrainLab.ui.components.user_error_presentation import UnexpectedErrorContext
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
# DatasetActionHandler
# ====================================================================


class TestDatasetActionHandler:
    @pytest.fixture
    def handler(self, qtbot):
        from XBrainLab.ui.dialogs.dataset.eeg_source_chooser_dialog import (
            EegSourceSelection,
        )
        from XBrainLab.ui.panels.dataset import actions
        from XBrainLab.ui.panels.dataset.actions import DatasetActionHandler

        del qtbot  # Ensure QApplication exists even when this fixture runs alone.
        panel = MagicMock()
        panel.table = MagicMock()
        panel.table.selectedIndexes.return_value = []
        panel.table.rowCount.return_value = 3
        panel.table.mapToGlobal.return_value = MagicMock()
        # This unit fixture has no real top-level QWidget. Mirror QWidget.window()
        # returning the panel itself so the coordinator correctly chooses an
        # unparented loading dialog instead of passing a MagicMock into Qt.
        panel.window.return_value = panel
        h = DatasetActionHandler(panel)

        class _LegacyFileChooser:
            """Keep old file-oriented cases focused on post-selection behavior."""

            def __init__(self, parent, *, start_directory=""):
                filter_str = (
                    "All files (*);;"
                    "EEG files (*.set *.SET *.gdf *.GDF *.fif *.FIF *.edf *.EDF "
                    "*.bdf *.BDF *.cnt *.CNT *.vhdr *.VHDR);;"
                    "EEGLAB (*.set *.SET);;GDF (*.gdf *.GDF);;"
                    "FIF (*.fif *.FIF);;EDF/BDF (*.edf *.EDF *.bdf *.BDF);;"
                    "Neuroscan CNT (*.cnt *.CNT);;BrainVision (*.vhdr *.VHDR)"
                )
                paths, _ = actions.QFileDialog.getOpenFileNames(
                    parent,
                    "Choose EEG Source for Interpretation",
                    start_directory,
                    filter_str,
                    options=actions.QFileDialog.Option.DontUseNativeDialog,
                )
                self._result = (
                    EegSourceSelection(kind="files", paths=tuple(paths))
                    if paths
                    else None
                )

            def exec(self):
                return self._result is not None

            def get_result(self):
                return self._result

        h._data_interpretation._source_chooser_dialog_class = lambda: (
            _LegacyFileChooser
        )
        h._data_interpretation._review_state_from_parts = MagicMock(
            side_effect=_mock_interpretation_review_state,
        )
        return h

    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
    def test_import_data_locked(self, mock_mb, handler):
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = True
        outcome = handler.import_data()

        assert outcome.status is InteractionStatus.BLOCKED
        mock_mb.assert_called_once()

    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
    def test_import_data_no_files(self, mock_mb, mock_fd, handler):
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getOpenFileNames.return_value = ([], "")
        outcome = handler.import_data()

        assert outcome.status is InteractionStatus.CANCELLED
        handler.panel.controller.import_files.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.present_unexpected_error")
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
        mock_mb.assert_called_once_with(
            handler.panel,
            UnexpectedErrorContext.DATA_IMPORT,
        )

    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
    def test_import_data_picker_starts_from_canonical_dataset_root(
        self,
        mock_mb,
        mock_fd,
        handler,
        tmp_path,
        monkeypatch,
    ):
        dataset_root = tmp_path / "datasets"
        dataset_root.mkdir()
        monkeypatch.setenv("XBRAINLAB_DATA_DIR", str(tmp_path))
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getOpenFileNames.return_value = ([], "")

        handler.import_data()

        assert mock_fd.getOpenFileNames.call_args.args[2] == str(dataset_root)

    def test_import_data_folder_selection_uses_typed_classification(
        self,
        handler,
    ):
        from XBrainLab.ui.dialogs.dataset.eeg_source_chooser_dialog import (
            EegSourceSelection,
        )

        class _FolderChooser:
            def __init__(self, _parent, *, start_directory=""):
                assert isinstance(start_directory, str)

            def exec(self):
                return True

            def get_result(self):
                return EegSourceSelection(kind="folder", paths=("/data/eeg",))

        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        handler._data_interpretation._source_chooser_dialog_class = lambda: (
            _FolderChooser
        )

        with patch.object(
            handler._data_interpretation,
            "_start_source_classification_async",
            return_value=InteractionOutcome.accepted("scheduled"),
        ) as classify:
            outcome = handler.import_data()

        assert outcome.status is InteractionStatus.ACCEPTED
        classify.assert_called_once_with("/data/eeg")

    def test_import_data_chooser_cancel_does_not_start_backend_work(
        self,
        handler,
    ):
        class _CancelledChooser:
            def __init__(self, _parent, *, start_directory=""):
                assert isinstance(start_directory, str)

            def exec(self):
                return False

            def get_result(self):
                raise AssertionError("cancelled chooser has no result")

        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        handler._data_interpretation._source_chooser_dialog_class = lambda: (
            _CancelledChooser
        )

        with (
            patch.object(
                handler._data_interpretation,
                "_start_source_classification_async",
            ) as classify,
            patch.object(
                handler._data_interpretation,
                "_run_data_interpretation_import",
            ) as review,
        ):
            outcome = handler.import_data()

        assert outcome.status is InteractionStatus.CANCELLED
        classify.assert_not_called()
        review.assert_not_called()

    def test_typed_generic_folder_classification_enters_existing_review(
        self,
        handler,
    ):
        from XBrainLab.backend.application import ScanSourceCommand

        commands = []

        def fake_async(_panel, command, *, on_result, **_kwargs):
            commands.append(command)
            on_result(
                _command_result(
                    payload_type="source_classification",
                    source_kind="folder",
                )
            )
            return True

        with (
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command_async",
                side_effect=fake_async,
            ),
            patch.object(
                handler._data_interpretation,
                "_run_data_interpretation_import",
                return_value=InteractionOutcome.accepted("review scheduled"),
            ) as review,
        ):
            outcome = handler._data_interpretation._start_source_classification_async(
                "/data/eeg"
            )

        assert outcome is not None
        assert outcome.status is InteractionStatus.ACCEPTED
        assert len(commands) == 1
        assert isinstance(commands[0], ScanSourceCommand)
        assert commands[0].source_hint == "auto"
        assert commands[0].catalog_only is True
        review.assert_called_once_with(["/data/eeg"], source_hint="folder")

    def test_typed_bids_classification_reuses_subject_selector(
        self,
        handler,
    ):
        catalog = {
            "eeg_file_count": 1,
            "subjects": [{"subject": "01", "eeg_file_count": 1}],
        }

        def fake_async(_panel, _command, *, on_result, **_kwargs):
            on_result(
                _command_result(
                    payload_type="source_classification",
                    source_kind="bids",
                    bids_subject_catalog=catalog,
                )
            )
            return True

        with (
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command_async",
                side_effect=fake_async,
            ),
            patch.object(
                handler._data_interpretation,
                "_present_bids_subject_catalog",
                return_value=InteractionOutcome.accepted("subjects scheduled"),
            ) as subjects,
        ):
            outcome = handler._data_interpretation._start_source_classification_async(
                "/data/bids"
            )

        assert outcome is not None
        assert outcome.status is InteractionStatus.ACCEPTED
        subjects.assert_called_once_with("/data/bids", catalog)

    def test_dataset_folder_picker_prefers_existing_canonical_bids_root(
        self,
        tmp_path,
        monkeypatch,
    ):
        from XBrainLab.ui.panels.dataset.data_interpretation_action_coordinator import (
            _dataset_dialog_start_directory,
        )

        bids_root = tmp_path / "datasets" / "bids"
        bids_root.mkdir(parents=True)
        monkeypatch.setenv("XBRAINLAB_DATA_DIR", str(tmp_path))

        assert _dataset_dialog_start_directory() == str(tmp_path / "datasets")
        assert _dataset_dialog_start_directory(prefer_bids=True) == str(bids_root)

    @pytest.mark.parametrize(
        ("method_name", "expected_relative"),
        (("import_folder_source", "datasets"), ("import_bids_source", "datasets/bids")),
    )
    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
    def test_directory_pickers_use_the_canonical_dataset_hierarchy(
        self,
        mock_mb,
        mock_fd,
        method_name,
        expected_relative,
        handler,
        tmp_path,
        monkeypatch,
    ):
        del mock_mb
        expected = tmp_path / expected_relative
        expected.mkdir(parents=True)
        monkeypatch.setenv("XBRAINLAB_DATA_DIR", str(tmp_path))
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getExistingDirectory.return_value = ""

        getattr(handler, method_name)()

        assert mock_fd.getExistingDirectory.call_args.args[2] == str(expected)

    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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
        mock_mb.assert_called_once()
        assert mock_mb.call_args.args[1] == "Interpretation Blocked"

    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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
            patch("XBrainLab.ui.panels.dataset.actions.show_error") as mock_error,
        ):
            handler.import_data()

        mock_execute.assert_not_called()
        handler.panel.controller.import_files.assert_not_called()
        mock_mb.assert_called_once()
        assert mock_mb.call_args.args[1] == "Interpretation Blocked"
        assert mock_mb.call_args.args[2] == (
            "Data interpretation availability is unavailable right now."
        )
        mock_error.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.show_error")
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
        mock_mb.assert_called_once_with(
            handler.panel,
            "Interpretation unavailable",
            "Data Interpretation command service is unavailable.",
        )

    @patch("XBrainLab.ui.panels.dataset.actions.DataInterpretationPreviewDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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
        mock_mb.assert_called_once()
        assert mock_mb.call_args.args[1] == "Interpretation Blocked"
        assert "could not safely complete" in mock_mb.call_args.args[2]

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
            patch("XBrainLab.ui.panels.dataset.actions.show_warning") as mock_mb,
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
        mock_mb.assert_not_called()

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
            patch("XBrainLab.ui.panels.dataset.actions.show_warning") as mock_mb,
        ):
            mock_fd.getOpenFileNames.return_value = ([], "")
            outcome = handler.import_data()

        handler.panel.controller.is_locked.assert_not_called()
        mock_fd.getOpenFileNames.assert_not_called()
        assert outcome.status is InteractionStatus.BLOCKED
        mock_mb.assert_called_once_with(
            handler.panel,
            "Interpretation Blocked",
            "Data interpretation availability is unavailable right now.",
        )

    @patch("XBrainLab.ui.panels.dataset.actions.DataInterpretationPreviewDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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

        with (
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command",
                side_effect=fake_execute,
            ),
            patch("XBrainLab.ui.panels.dataset.actions.show_error") as mock_error,
        ):
            handler.import_bids_source()

        assert isinstance(commands[0], ScanSourceCommand)
        assert commands[0].catalog_only is True
        assert isinstance(commands[1], ReviewInterpretationCommand)
        assert commands[1].source_path == "/tmp/bids-root"
        assert commands[1].source_hint == "bids"
        assert commands[1].choices["selected_bids_subjects"] == ["02"]
        mock_error.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.BidsSubjectSelectionDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.DataInterpretationPreviewDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    def test_import_bids_catalog_and_review_use_async_command_surface(
        self,
        mock_fd,
        mock_preview_dialog,
        mock_subject_dialog,
        handler,
    ):
        from XBrainLab.backend.application import (
            ReviewInterpretationCommand,
            ScanSourceCommand,
        )

        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getExistingDirectory.return_value = "/tmp/bids-root"
        mock_subject_dialog.return_value.exec.return_value = True
        mock_subject_dialog.return_value.get_result.return_value = ["02"]
        mock_preview_dialog.return_value.exec.return_value = False
        async_commands = []

        def fake_async(_panel, command, *, on_result, **_kwargs):
            async_commands.append(command)
            if isinstance(command, ScanSourceCommand):
                on_result(
                    _command_result(
                        bids_subject_catalog={
                            "eeg_file_count": 1,
                            "subjects": [
                                {
                                    "subject": "02",
                                    "label": "sub-02",
                                    "eeg_file_count": 1,
                                }
                            ],
                        }
                    )
                )
            elif isinstance(command, ReviewInterpretationCommand):
                on_result(
                    _command_result(
                        scan_result={"scan_id": "scan-1"},
                        preview={},
                        candidate={"candidate_id": "candidate-1"},
                        validation_decision={
                            "candidate_id": "candidate-1",
                            "decision": "needs_confirmation",
                            "required_confirmations": [],
                            "blocked_reasons": [],
                        },
                    )
                )
            else:
                raise AssertionError(f"unexpected command: {command!r}")
            return True

        with (
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command_async",
                side_effect=fake_async,
            ),
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command",
                side_effect=AssertionError(
                    "BIDS discovery must not block the UI thread"
                ),
            ),
            patch("XBrainLab.ui.panels.dataset.actions.show_error") as mock_error,
        ):
            handler.import_bids_source()

        assert [type(command) for command in async_commands] == [
            ScanSourceCommand,
            ReviewInterpretationCommand,
        ]
        assert async_commands[0].catalog_only is True
        assert async_commands[1].choices["selected_bids_subjects"] == ["02"]

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
            patch("XBrainLab.ui.panels.dataset.actions.show_warning") as mock_mb,
        ):
            mock_fd.getExistingDirectory.return_value = "/tmp/bids-root"
            handler.import_folder_source()

        mock_fd.getExistingDirectory.assert_called_once()
        mock_interpret.assert_called_once_with(["/tmp/bids-root"])
        mock_mb.assert_not_called()

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
            patch("XBrainLab.ui.panels.dataset.actions.show_warning") as mock_mb,
        ):
            handler.import_folder_source()

        handler.panel.controller.is_locked.assert_not_called()
        mock_fd.getExistingDirectory.assert_not_called()
        mock_mb.assert_called_once()
        assert mock_mb.call_args.args[1] == "Interpretation Blocked"
        assert "could not safely complete" in mock_mb.call_args.args[2]

    @patch("XBrainLab.ui.panels.dataset.actions.DataInterpretationPreviewDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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

    @patch("XBrainLab.ui.panels.dataset.actions.show_error")
    @patch("XBrainLab.ui.panels.dataset.actions.DataInterpretationPreviewDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
    def test_reload_interpretation_recipe_repreviews_blocked_label_carrier_remap(
        self,
        mock_mb,
        mock_fd,
        mock_preview_dialog,
        mock_error,
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
        mock_error.assert_not_called()
        handler.panel.update_panel.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.show_error")
    @patch("XBrainLab.ui.panels.dataset.actions.DataInterpretationPreviewDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
    def test_reload_interpretation_recipe_repreviews_blocked_eeg_file_remap(
        self,
        mock_mb,
        mock_fd,
        mock_preview_dialog,
        mock_error,
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
        mock_error.assert_not_called()
        handler.panel.update_panel.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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

        mock_mb.assert_called_once()
        assert "Recipe reload is unavailable" in mock_mb.call_args.args[2]
        mock_fd.getOpenFileName.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.DataInterpretationPreviewDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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
            qtbot.waitUntil(
                lambda: panel_context.set_busy.call_count == 2,
                timeout=1000,
            )

        assert panel_context.set_busy.call_args_list == [((True,),), ((False,),)]
        assert [record.args for record in show_status.call_args_list] == [
            ("Applied.",),
        ]
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
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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
        mock_mb.assert_not_called()

    def test_save_interpretation_recipe_uses_backend_capability_before_file_dialog(
        self,
        handler,
    ):
        from XBrainLab.backend.study import Study

        handler.panel.study = Study()
        completions = []

        with (
            patch("XBrainLab.ui.panels.dataset.actions.QFileDialog") as mock_fd,
            patch("XBrainLab.ui.panels.dataset.actions.show_warning") as mock_mb,
        ):
            handled = handler._data_interpretation._save_interpretation_recipe(
                on_complete=completions.append,
            )

        assert handled is True
        assert completions == [""]
        mock_fd.getSaveFileName.assert_not_called()
        mock_mb.assert_called_once()
        assert (
            "Apply an interpretation before saving a recipe."
            in mock_mb.call_args.args[2]
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
            patch("XBrainLab.ui.panels.dataset.actions.show_warning") as mock_mb,
            patch(
                "XBrainLab.ui.panels.dataset.actions.ask_confirmation"
            ) as mock_confirmation,
        ):
            message = handler._offer_label_recipe_save(result)

        assert message == "Interpretation recipe trace updated in this session."
        mock_confirmation.assert_not_called()
        mock_fd.getSaveFileName.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.DataInterpretationPreviewDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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

        with (
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command",
                side_effect=fake_execute,
            ),
            patch("XBrainLab.ui.panels.dataset.actions.show_error") as mock_error,
        ):
            outcome = handler.import_data()

        assert outcome.status is InteractionStatus.BLOCKED
        mock_error.assert_not_called()
        handler.panel.controller.import_files.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.DataInterpretationPreviewDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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

        with (
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command",
                side_effect=fake_execute,
            ),
            patch("XBrainLab.ui.panels.dataset.actions.show_error") as mock_error,
        ):
            outcome = handler.import_data()

        assert isinstance(commands[0], ReviewInterpretationCommand)
        assert commands[0].source_path == first_file
        assert outcome.status is InteractionStatus.BLOCKED
        mock_error.assert_not_called()
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

    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
    def test_on_import_finished_success(self, mock_mb, handler):
        handler.on_import_finished(2, [])
        handler.panel.update_panel.assert_not_called()
        mock_mb.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
    def test_on_import_finished_errors(self, mock_mb, handler):
        handler.on_import_finished(1, ["err1", "err2"])
        mock_mb.assert_called_once()

    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
    def test_open_smart_parser_locked(self, mock_mb, handler):
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = True
        handler.open_smart_parser()
        mock_mb.assert_called_once()

    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
    def test_open_smart_parser_no_data(self, mock_mb, handler):
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        handler.panel.controller.has_data.return_value = False
        handler.open_smart_parser()
        mock_mb.assert_called_once()

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
        with patch("XBrainLab.ui.panels.dataset.actions.show_warning") as mock_mb:
            handler.show_context_menu(MagicMock())
        handler.panel.controller.update_metadata.assert_not_called()
        mock_mb.assert_called_once()
        assert mock_mb.call_args.args[1] == "Metadata Update Blocked"

    @patch("XBrainLab.ui.panels.dataset.actions.ask_confirmation", return_value=True)
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
    def test_remove_files(self, mock_mb, ask_confirmation, handler):
        handler.panel.controller = MagicMock()
        handler._remove_files([0, 1])
        handler.panel.controller.remove_files.assert_not_called()
        mock_mb.assert_called_once()
        assert mock_mb.call_args.args[1] == "Remove Files Blocked"
        assert ask_confirmation.call_args.kwargs == {
            "severity": AlertSeverity.WARNING,
            "title": "Confirm",
            "message": "Remove 2 files?",
            "confirm_text": "Remove files",
            "cancel_text": "Cancel",
            "destructive": True,
        }

    def test_remove_files_refuses_real_study_controller_fallback(self, handler):
        from XBrainLab.backend.study import Study

        study = Study()
        study.data_manager.loaded_data_list = [MagicMock()]
        handler.panel.study = study
        handler.panel.controller = MagicMock()

        with (
            patch("XBrainLab.ui.panels.dataset.actions.show_warning") as mock_mb,
            patch(
                "XBrainLab.ui.panels.dataset.actions.ask_confirmation",
                return_value=True,
            ),
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command",
                return_value=None,
            ),
        ):
            handler._remove_files([0])

        handler.panel.controller.remove_files.assert_not_called()
        mock_mb.assert_called_once()
        assert mock_mb.call_args.args[1] == "Review File Removal Again"
        assert "Refresh Dataset" in mock_mb.call_args.args[2]

    def test_remove_files_service_success_uses_coordinator_refresh(self, handler):
        handler.panel.controller = MagicMock()

        with (
            patch("XBrainLab.ui.panels.dataset.actions.show_warning") as mock_mb,
            patch(
                "XBrainLab.ui.panels.dataset.actions.ask_confirmation",
                return_value=True,
            ),
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command",
                return_value=_command_result(),
            ),
        ):
            handler._remove_files([0])

        handler.panel.update_panel.assert_not_called()

    def test_remove_files_uses_backend_capability_before_confirm(self, handler):
        from XBrainLab.backend.study import Study

        handler.panel.study = Study()
        handler.panel.controller = MagicMock()

        with (
            patch("XBrainLab.ui.panels.dataset.actions.show_warning") as mock_mb,
            patch(
                "XBrainLab.ui.panels.dataset.actions.ask_confirmation"
            ) as mock_confirmation,
        ):
            handler._remove_files([0, 1])

        mock_confirmation.assert_not_called()
        mock_mb.assert_called_once()
        assert "Load raw data before removing files." in mock_mb.call_args.args[2]
        handler.panel.controller.remove_files.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
    def test_batch_set_session(self, mock_mb, handler):
        handler.panel.controller = MagicMock()
        with patch("XBrainLab.ui.panels.dataset.actions.QInputDialog") as mock_input:
            mock_input.getText.return_value = ("sess1", True)
            handler._batch_set([0], "Session")
        handler.panel.controller.update_metadata.assert_not_called()
        mock_mb.assert_called_once()
        assert mock_mb.call_args.args[1] == "Metadata Update Blocked"

    def test_batch_set_uses_backend_capability_before_prompt(self, handler):
        from XBrainLab.backend.study import Study

        handler.panel.study = Study()
        handler.panel.controller = MagicMock()

        with (
            patch("XBrainLab.ui.panels.dataset.actions.QInputDialog") as mock_input,
            patch("XBrainLab.ui.panels.dataset.actions.show_warning") as mock_mb,
        ):
            handler._batch_set([0], "Session")

        mock_input.getText.assert_not_called()
        mock_mb.assert_called_once()
        assert "Load raw data before updating metadata." in (mock_mb.call_args.args[2])
        handler.panel.controller.update_metadata.assert_not_called()

    def test_batch_set_refuses_real_study_controller_fallback(self, handler):
        from XBrainLab.backend.study import Study

        study = Study()
        study.data_manager.loaded_data_list = [MagicMock()]
        handler.panel.study = study
        handler.panel.controller = MagicMock()

        with (
            patch("XBrainLab.ui.panels.dataset.actions.QInputDialog") as mock_input,
            patch("XBrainLab.ui.panels.dataset.actions.show_warning") as mock_mb,
            patch(
                "XBrainLab.ui.panels.dataset.actions.ask_confirmation",
                return_value=True,
            ),
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command",
                return_value=None,
            ),
        ):
            mock_input.getText.return_value = ("session-01", True)
            handler._batch_set([0], "Session")

        handler.panel.controller.update_metadata.assert_not_called()
        mock_mb.assert_called_once()
        assert mock_mb.call_args.args[1] == "Review Metadata Again"
        assert "Refresh Dataset" in mock_mb.call_args.args[2]

    @patch("XBrainLab.ui.panels.dataset.actions.ask_confirmation")
    def test_get_target_files_no_selection_apply_all(self, mock_mb, handler):
        handler.panel.table.selectedIndexes.return_value = []
        mock_mb.return_value = True
        handler.panel.controller = MagicMock()
        handler.panel.controller.get_loaded_data_list.return_value = ["a", "b", "c"]
        result = handler._get_target_files_for_import()
        assert len(result) == 3
        assert mock_mb.call_args.kwargs["title"] == "Add Labels to Loaded Data"
        assert mock_mb.call_args.kwargs["message"] == (
            "No files selected. Add labels to all loaded files?"
        )

    @patch("XBrainLab.ui.panels.dataset.actions.ask_confirmation")
    def test_get_target_files_no_selection_cancel(self, mock_mb, handler):
        handler.panel.table.selectedIndexes.return_value = []
        mock_mb.return_value = False
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
            with patch("XBrainLab.ui.panels.dataset.actions.show_warning") as mock_mb:
                handler.open_smart_parser()
                handler.panel.controller.apply_smart_parse.assert_not_called()
                mock_mb.assert_called_once()
                assert mock_mb.call_args.args[1] == "Smart Parse Blocked"

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
            patch("XBrainLab.ui.panels.dataset.actions.show_warning") as mock_mb,
        ):
            handler.open_smart_parser()

        mock_dialog.assert_not_called()
        mock_mb.assert_called_once()
        assert (
            "Load raw data before applying smart parse." in (mock_mb.call_args.args[2])
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
            patch("XBrainLab.ui.panels.dataset.actions.show_warning") as mock_mb,
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
        mock_mb.assert_not_called()

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
            patch("XBrainLab.ui.panels.dataset.actions.show_warning") as mock_mb,
        ):
            mock_dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            mock_dialog.return_value.get_result.return_value = {
                "/tmp/sub-01_task-mi_raw.fif": ("S01", "session-01")
            }
            handler.open_smart_parser()

        handler.panel.controller.apply_smart_parse.assert_not_called()
        mock_mb.assert_called_once()
        assert mock_mb.call_args.args[1] == "Smart Parse Blocked"
        assert "could not safely complete" in mock_mb.call_args.args[2]

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
            patch("XBrainLab.ui.panels.dataset.actions.show_warning") as mock_mb,
        ):
            handler.open_smart_parser()

        handler.panel.controller.is_locked.assert_not_called()
        handler.panel.controller.has_data.assert_not_called()
        mock_dialog.assert_not_called()
        mock_mb.assert_called_once()
        assert mock_mb.call_args.args[1] == "Smart Parse Blocked"
        assert "Load raw data before applying smart parse." in mock_mb.call_args.args[2]

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
            patch("XBrainLab.ui.panels.dataset.actions.show_warning") as mock_mb,
        ):
            handler.open_smart_parser()

        handler.panel.controller.get_filenames.assert_not_called()
        mock_dialog.assert_not_called()
        mock_mb.assert_called_once()
        assert mock_mb.call_args.args[1] == "Smart Parse Blocked"
        assert "could not safely complete" in mock_mb.call_args.args[2]

    def test_import_label_returns_early_no_files(self, handler):
        """import_label calls _get_target_files_for_import first; if empty, returns."""
        handler.panel.table.selectedIndexes.return_value = []
        with patch(
            "XBrainLab.ui.panels.dataset.actions.ask_confirmation",
            return_value=False,
        ) as mock_confirm:
            handler.import_label()
        mock_confirm.assert_called_once()

    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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

        mock_mb.assert_called_once()
        assert "Interpret a data source" in mock_mb.call_args.args[2]
        mock_dlg.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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

        mock_mb.assert_called_once()
        assert (
            "Reset the session before changing labels." in (mock_mb.call_args.args[2])
        )
        mock_dlg.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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

    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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

    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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

    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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
        mock_mb.assert_called()

    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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

    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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
        mock_mb.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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
        mock_mb.assert_called_once()
        assert mock_mb.call_args.args[1] == "Add Labels Blocked"
        assert "could not safely complete" in mock_mb.call_args.args[2]

    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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

        mock_mb.assert_called()
        assert mock_mb.call_args.args[1] == "No Labels Applied"

    @patch("XBrainLab.ui.panels.dataset.actions.LabelMappingDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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
        mock_mb.assert_called_once()
        assert mock_mb.call_args.args[1] == "Label Import Blocked"

    @patch("XBrainLab.ui.panels.dataset.actions.LabelMappingDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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
        mock_mb.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.LabelMappingDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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
        mock_mb.assert_called_once()
        assert mock_mb.call_args.args[1] == "Label Import Blocked"

    @patch("XBrainLab.ui.panels.dataset.actions.show_error")
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
        mock_mb.assert_called_once()

    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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
        mock_mb.assert_called_once()
        assert mock_mb.call_args.args[1] == "Label Import Blocked"

    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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
            patch(
                "XBrainLab.ui.panels.dataset.actions.ask_confirmation",
                return_value=True,
            ),
        ):
            handler.import_label()

        assert saved
        assert saved[0].recipe_path == "/recipes/with_labels.json"
        mock_mb.assert_not_called()
        status_bar = handler.panel.main_window.statusBar.return_value
        assert "Recipe saved." in status_bar.showMessage.call_args.args[0]
        handler.panel.update_panel.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.show_error")
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
    @patch("XBrainLab.ui.panels.dataset.actions.ImportLabelDialog")
    def test_import_label_exception(self, mock_dlg, mock_mb, mock_error, handler):
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
        mock_mb.assert_called_once()
        assert mock_mb.call_args.args[1] == "Label Import Blocked"
        mock_error.assert_not_called()

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
        with patch("XBrainLab.ui.panels.dataset.actions.show_warning") as mock_mb:
            handler.on_import_finished(0, [f"err{i}" for i in range(15)])
            mock_mb.assert_called_once()

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
        with (
            patch(
                "XBrainLab.ui.panels.dataset.actions.ask_confirmation",
                return_value=True,
            ),
            patch("XBrainLab.ui.panels.dataset.actions.show_warning") as mock_mb,
        ):
            handler.show_context_menu(MagicMock())
        handler.panel.controller.remove_files.assert_not_called()
        mock_mb.assert_called_once()
        assert mock_mb.call_args.args[1] == "Remove Files Blocked"

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
        with patch("XBrainLab.ui.panels.dataset.actions.show_warning") as mock_mb:
            handler.show_context_menu(MagicMock())
        handler.panel.controller.update_metadata.assert_not_called()
        mock_mb.assert_called_once()
        assert mock_mb.call_args.args[1] == "Metadata Update Blocked"

    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
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
        mock_mb.assert_called_once()
        assert mock_mb.call_args.args[1] == "Label Import Blocked"

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

    def test_show_warning(self, widget):
        widget.show_warning("test warning")
        assert "test warning" in widget.error_label.text()

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
            selected_label_key=None,
            display_mode="all",
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
        preparation_key = ("test-lineage",)

        assert (
            widget._render_plot(
                publication.data,
                widget._preparation_cache,
                preparation_key,
                False,
            )
            is None
        )

        mock_vt.SaliencySpectrogramMap.value.assert_called_once_with(publication.data)
        mock_vt.SaliencySpectrogramMap.value.return_value.get_plt.assert_called_once_with(
            method="grad",
            display_normalized=False,
            preparation_cache=widget._preparation_cache,
            preparation_key=preparation_key,
            selected_label_key=None,
            display_mode="all",
        )

    @patch(
        "XBrainLab.ui.panels.visualization.saliency_views.spectrogram_view.VisualizerType"
    )
    def test_render_plot_propagates_visualizer_failure(self, mock_vt, widget):
        publication = _saliency_render_publication()
        mock_vt.SaliencySpectrogramMap.value.side_effect = RuntimeError("fail")

        with pytest.raises(RuntimeError, match="fail"):
            widget._render_plot(
                publication.data,
                widget._preparation_cache,
                ("test-lineage",),
                False,
            )
