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

    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
    def test_import_data_real_study_blocks_without_interpretation_service(
        self,
        mock_mb,
        mock_fd,
        handler,
    ):
        from XBrainLab.backend.study import Study

        handler.panel.study = Study()
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
        mock_mb.assert_called_once_with(
            handler.panel,
            "Interpretation unavailable",
            "Data Interpretation command service is unavailable.",
        )

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

    def test_import_data_uses_interpretation_review_result(
        self,
        handler,
    ):
        from XBrainLab.backend.study import Study

        handler.panel.study = Study()

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

    @pytest.mark.parametrize("real_study", [False, True])
    def test_import_data_blocks_before_choosing_without_scan_capability(
        self,
        handler,
        real_study,
    ):
        from XBrainLab.backend.study import Study

        if real_study:
            handler.panel.study = Study()

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

        mock_fd.getOpenFileNames.assert_not_called()
        assert outcome.status is InteractionStatus.BLOCKED
        mock_mb.assert_called_once_with(
            handler.panel,
            "Interpretation Blocked",
            "Data interpretation availability is unavailable right now.",
        )

    def test_import_folder_uses_interpretation_review_result(
        self,
        handler,
    ):
        from XBrainLab.backend.study import Study

        handler.panel.study = Study()

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

    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.show_warning")
    def test_reload_interpretation_recipe_uses_reload_capability_gate(
        self,
        mock_mb,
        mock_fd,
        handler,
    ):
        from XBrainLab.backend.application import CommandName

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
    def test_open_smart_parser_without_product_review_is_blocked(
        self,
        mock_mb,
        handler,
    ):
        handler.open_smart_parser()
        mock_mb.assert_called_once()

    def test_remove_files_real_study_requires_fresh_review(self, handler):
        from XBrainLab.backend.study import Study
        from XBrainLab.ui.panels.dataset.actions import (
            DatasetTableRowIdentity,
            DatasetTableSelection,
        )

        study = Study()
        study.data_manager.loaded_data_list = [MagicMock()]
        handler.panel.study = study

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
            handler._remove_files(
                DatasetTableSelection(
                    publication_generation=1,
                    rows=(
                        DatasetTableRowIdentity(
                            canonical_filepath="/data/row-0.fif",
                            rendered_row=0,
                        ),
                    ),
                )
            )

        mock_mb.assert_called_once()
        assert mock_mb.call_args.args[1] == "Review File Removal Again"
        assert "Refresh Dataset" in mock_mb.call_args.args[2]

    def test_remove_files_uses_backend_capability_before_confirm(self, handler):
        from XBrainLab.backend.study import Study
        from XBrainLab.ui.panels.dataset.actions import (
            DatasetTableRowIdentity,
            DatasetTableSelection,
        )

        handler.panel.study = Study()

        with (
            patch("XBrainLab.ui.panels.dataset.actions.show_warning") as mock_mb,
            patch(
                "XBrainLab.ui.panels.dataset.actions.ask_confirmation"
            ) as mock_confirmation,
        ):
            handler._remove_files(
                DatasetTableSelection(
                    publication_generation=1,
                    rows=(
                        DatasetTableRowIdentity("/data/row-0.fif", 0),
                        DatasetTableRowIdentity("/data/row-1.fif", 1),
                    ),
                )
            )

        mock_confirmation.assert_not_called()
        mock_mb.assert_called_once()
        assert "Load raw data before removing files." in mock_mb.call_args.args[2]

    def test_batch_set_uses_backend_capability_before_prompt(self, handler):
        from XBrainLab.backend.study import Study
        from XBrainLab.ui.panels.dataset.actions import (
            DatasetTableRowIdentity,
            DatasetTableSelection,
        )

        handler.panel.study = Study()

        with (
            patch("XBrainLab.ui.panels.dataset.actions.QInputDialog") as mock_input,
            patch("XBrainLab.ui.panels.dataset.actions.show_warning") as mock_mb,
        ):
            handler._batch_set(
                DatasetTableSelection(
                    publication_generation=1,
                    rows=(DatasetTableRowIdentity("/data/row-0.fif", 0),),
                ),
                "Session",
            )

        mock_input.getText.assert_not_called()
        mock_mb.assert_called_once()
        assert "Load raw data before updating metadata." in (mock_mb.call_args.args[2])

    def test_batch_set_real_study_requires_fresh_review(self, handler):
        from XBrainLab.backend.study import Study
        from XBrainLab.ui.panels.dataset.actions import (
            DatasetTableRowIdentity,
            DatasetTableSelection,
        )

        study = Study()
        study.data_manager.loaded_data_list = [MagicMock()]
        handler.panel.study = study

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
            handler._batch_set(
                DatasetTableSelection(
                    publication_generation=1,
                    rows=(DatasetTableRowIdentity("/data/row-0.fif", 0),),
                ),
                "Session",
            )

        mock_mb.assert_called_once()
        assert mock_mb.call_args.args[1] == "Review Metadata Again"
        assert "Refresh Dataset" in mock_mb.call_args.args[2]

    def test_open_smart_parser_uses_backend_capability(self, handler):
        from XBrainLab.backend.study import Study

        handler.panel.study = Study()

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

    def test_open_smart_parser_uses_published_rows(
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

        mock_dialog.assert_called_once_with(
            ["/tmp/sub-01_task-mi_raw.fif"],
            handler.panel,
        )
        assert mock_execute.call_count == 2
        mock_mb.assert_not_called()

    def test_open_smart_parser_real_study_blocks_without_command_result(
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

        mock_mb.assert_called_once()
        assert mock_mb.call_args.args[1] == "Smart Parse Blocked"
        assert "could not safely complete" in mock_mb.call_args.args[2]

    def test_open_smart_parser_blocks_when_capability_is_unavailable(
        self,
        handler,
    ):
        from XBrainLab.backend.study import Study

        handler.panel.study = Study()

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

        mock_dialog.assert_not_called()
        mock_mb.assert_called_once()
        assert mock_mb.call_args.args[1] == "Smart Parse Blocked"
        assert "Load raw data before applying smart parse." in mock_mb.call_args.args[2]


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
