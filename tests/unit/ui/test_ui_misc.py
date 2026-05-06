"""Batch 5: deeper coverage for data_splitting_preview, actions, import_label,
agent_manager, preprocess_plotter, saliency views, and remaining gaps."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PyQt6.QtWidgets import QDialog, QMainWindow, QWidget


def _command_result(**diagnostics):
    return SimpleNamespace(
        ok=True,
        failed=False,
        message="ok",
        diagnostics=diagnostics,
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
        h.to_thread()  # should not raise

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
        handler.import_data()
        mock_mb.warning.assert_called_once()

    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_data_no_files(self, mock_mb, mock_fd, handler):
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getOpenFileNames.return_value = ([], "")
        handler.import_data()
        handler.panel.controller.import_files.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_data_success(self, mock_mb, mock_fd, handler):
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getOpenFileNames.return_value = (["/a.set"], "")
        handler.import_data()
        handler.panel.controller.import_files.assert_called_once_with(["/a.set"])

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
                handler, "_run_data_interpretation_import", return_value=False
            ),
            patch(
                "XBrainLab.ui.panels.dataset.actions.execute_application_command",
                return_value=_command_result(success_count=1),
            ) as mock_execute,
        ):
            handler.import_data()

        assert isinstance(mock_execute.call_args.args[1], LoadDataCommand)
        handler.panel.controller.import_files.assert_not_called()
        handler.panel.update_panel.assert_not_called()

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
                handler, "_run_data_interpretation_import", return_value=False
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
            PreviewInterpretationCommand,
            ScanSourceCommand,
            ValidateInterpretationCommand,
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

        def fake_execute(_panel, command):
            commands.append(command)
            if isinstance(command, ScanSourceCommand):
                return _command_result(scan_result={"source_path": command.source_path})
            if isinstance(command, PreviewInterpretationCommand):
                return _command_result(
                    preview={"summary": "Found 1 EEG file(s)."},
                    candidate={"candidate_id": "candidate-1"},
                )
            if isinstance(command, ValidateInterpretationCommand):
                return _command_result(
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

        with patch(
            "XBrainLab.ui.panels.dataset.actions.execute_application_command",
            side_effect=fake_execute,
        ):
            handler.import_data()

        assert [type(command) for command in commands] == [
            ScanSourceCommand,
            PreviewInterpretationCommand,
            ValidateInterpretationCommand,
            ApplyInterpretationCommand,
        ]
        assert commands[-1].candidate_id == "candidate-1"
        assert commands[-1].confirmed is False
        handler.panel.controller.import_files.assert_not_called()
        handler.panel.update_panel.assert_not_called()

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
                handler,
                "_run_data_interpretation_import",
                return_value=True,
            ) as mock_interpret,
            patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb,
        ):
            mock_fd.getOpenFileNames.return_value = (
                ["/tmp/sub-01_task-mi_raw.fif"],
                "",
            )
            handler.import_data()

        mock_fd.getOpenFileNames.assert_called_once()
        mock_interpret.assert_called_once_with(["/tmp/sub-01_task-mi_raw.fif"])
        mock_mb.warning.assert_not_called()

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
            PreviewInterpretationCommand,
            ScanSourceCommand,
            ValidateInterpretationCommand,
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
            if isinstance(command, ScanSourceCommand):
                return _command_result(scan_result={"source_path": command.source_path})
            if isinstance(command, PreviewInterpretationCommand):
                return _command_result(
                    preview={"summary": "Found 1 EEG file(s)."},
                    candidate={"candidate_id": "candidate-1"},
                )
            if isinstance(command, ValidateInterpretationCommand):
                return _command_result(
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

        assert isinstance(commands[0], ScanSourceCommand)
        assert commands[0].source_path == "/tmp/bids-root"
        assert [type(command) for command in commands] == [
            ScanSourceCommand,
            PreviewInterpretationCommand,
            ValidateInterpretationCommand,
            ApplyInterpretationCommand,
        ]
        handler.panel.controller.import_files.assert_not_called()
        handler.panel.update_panel.assert_not_called()

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
                handler,
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

        with patch(
            "XBrainLab.ui.panels.dataset.actions.execute_application_command",
            side_effect=fake_execute,
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

        with patch(
            "XBrainLab.ui.panels.dataset.actions.execute_application_command",
            side_effect=fake_execute,
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

        with patch(
            "XBrainLab.ui.panels.dataset.actions.execute_application_command",
            side_effect=fake_execute,
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
            PreviewInterpretationCommand,
            ScanSourceCommand,
            ValidateInterpretationCommand,
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
            if isinstance(command, ScanSourceCommand):
                return _command_result(scan_result={})
            if isinstance(command, PreviewInterpretationCommand):
                return _command_result(
                    preview={},
                    candidate={"candidate_id": "candidate-1"},
                )
            if isinstance(command, ValidateInterpretationCommand):
                return _command_result(
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

        with patch(
            "XBrainLab.ui.panels.dataset.actions.execute_application_command",
            side_effect=fake_execute,
        ):
            handler.import_data()

        assert applied
        assert applied[0].confirmed is True

    @patch("XBrainLab.ui.panels.dataset.actions.DataInterpretationPreviewDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_data_repreviews_dialog_review_choices(
        self,
        mock_mb,
        mock_fd,
        mock_preview_dialog,
        handler,
    ):
        from XBrainLab.backend.application import (
            ApplyInterpretationCommand,
            PreviewInterpretationCommand,
            ScanSourceCommand,
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
        previews: list[PreviewInterpretationCommand] = []
        applied: list[ApplyInterpretationCommand] = []

        def fake_execute(_panel, command):
            if isinstance(command, ScanSourceCommand):
                return _command_result(
                    scan_result={
                        "scan_id": "scan-1",
                        "source_path": command.source_path,
                    }
                )
            if isinstance(command, PreviewInterpretationCommand):
                previews.append(command)
                candidate_id = f"candidate-{len(previews)}"
                return _command_result(
                    preview={"summary": "Found 1 EEG file(s)."},
                    candidate={"candidate_id": candidate_id},
                )
            if isinstance(command, ValidateInterpretationCommand):
                return _command_result(
                    validation_decision={
                        "candidate_id": command.candidate_id,
                        "decision": "needs_confirmation",
                        "required_confirmations": ["Confirm event roles."],
                        "blocked_reasons": [],
                    },
                )
            if isinstance(command, ApplyInterpretationCommand):
                applied.append(command)
                return _command_result(applied_interpretation={})
            raise AssertionError(f"unexpected command: {command!r}")

        with patch(
            "XBrainLab.ui.panels.dataset.actions.execute_application_command",
            side_effect=fake_execute,
        ):
            handler.import_data()

        assert len(previews) == 2
        assert previews[1].scan_id == "scan-1"
        assert previews[1].choices["metadata_overrides"] == {
            "sub-01_task-mi.fif": {"session": "session-01"}
        }
        assert previews[1].choices["class_map"] == {
            "1": "left hand",
            "2": "right hand",
        }
        assert applied
        assert applied[0].candidate_id == "candidate-2"
        assert applied[0].confirmed is True

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
            PreviewInterpretationCommand,
            SaveInterpretationRecipeCommand,
            ScanSourceCommand,
            ValidateInterpretationCommand,
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

        def fake_execute(_panel, command):
            if isinstance(command, ScanSourceCommand):
                return _command_result(scan_result={})
            if isinstance(command, PreviewInterpretationCommand):
                return _command_result(
                    preview={},
                    candidate={"candidate_id": "candidate-1"},
                )
            if isinstance(command, ValidateInterpretationCommand):
                return _command_result(
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

        with patch(
            "XBrainLab.ui.panels.dataset.actions.execute_application_command",
            side_effect=fake_execute,
        ):
            handler.import_data()

        assert saved
        assert saved[0].recipe_path == "/recipes/import_recipe.json"
        mock_mb.information.assert_called_once()
        assert "Recipe saved." in mock_mb.information.call_args.args[2]

    def test_save_interpretation_recipe_uses_backend_capability_before_file_dialog(
        self,
        handler,
    ):
        from XBrainLab.backend.study import Study

        handler.panel.study = Study()

        with (
            patch("XBrainLab.ui.panels.dataset.actions.QFileDialog") as mock_fd,
            patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb,
        ):
            message = handler._save_interpretation_recipe()

        assert message == ""
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
            PreviewInterpretationCommand,
            ScanSourceCommand,
            ValidateInterpretationCommand,
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
            if isinstance(command, ScanSourceCommand):
                return _command_result(scan_result={})
            if isinstance(command, PreviewInterpretationCommand):
                return _command_result(
                    preview={},
                    candidate={"candidate_id": "candidate-1"},
                )
            if isinstance(command, ValidateInterpretationCommand):
                return _command_result(
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

    def test_interpretation_source_avoids_common_root_scan(self, handler):
        source_path, choices = handler._interpretation_source_and_choices(
            ["/mnt/a/sub-01.fif", "/tmp/b/sub-02.fif"],
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
        mock_mb.critical.assert_called_once()

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
        handler.show_context_menu(MagicMock())
        handler.panel.controller.update_metadata.assert_called()

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_remove_files(self, mock_mb, handler):
        mock_mb.question.return_value = MagicMock()
        mock_mb.StandardButton.Yes = MagicMock()
        mock_mb.question.return_value = mock_mb.StandardButton.Yes
        handler.panel.controller = MagicMock()
        handler._remove_files([0, 1])
        handler.panel.controller.remove_files.assert_called_once_with([0, 1])

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
        assert mock_mb.warning.call_args.args[1] == "Remove Files Blocked"
        assert "could not safely complete" in mock_mb.warning.call_args.args[2]

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
        handler.panel.controller.update_metadata.assert_called_once_with(
            0, session="sess1"
        )

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
        assert mock_mb.warning.call_args.args[1] == "Metadata Update Blocked"
        assert "could not safely complete" in mock_mb.warning.call_args.args[2]

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
            with patch("XBrainLab.ui.panels.dataset.actions.QMessageBox"):
                handler.open_smart_parser()
                handler.panel.controller.apply_smart_parse.assert_called()

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
            "state": {
                "raw": {
                    "files": ["sub-01_task-mi_raw.fif"],
                },
            },
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
        mock_dialog.assert_called_once_with(["sub-01_task-mi_raw.fif"], handler.panel)
        assert mock_execute.call_count == 2
        handler.panel.controller.apply_smart_parse.assert_not_called()
        mock_mb.warning.assert_not_called()

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
        handler.panel.controller.apply_labels_legacy.assert_not_called()

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
    def test_import_label_uses_table_user_role_before_stale_controller_list(
        self,
        mock_dlg,
        mock_mb,
        handler,
    ):
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QTableWidgetItem

        idx = MagicMock()
        idx.row.return_value = 0
        data_obj = MagicMock()
        item = QTableWidgetItem("sub-01_task-mi_raw.fif")
        item.setData(Qt.ItemDataRole.UserRole, data_obj)

        handler.panel.table.rowCount.return_value = 1
        handler.panel.table.selectedIndexes.return_value = [idx]
        handler.panel.table.item.return_value = item
        handler.panel.controller = MagicMock()
        handler.panel.controller.get_loaded_data_list.side_effect = AssertionError(
            "stale loaded list should not be read",
        )
        mock_dlg.return_value.exec.return_value = False

        handler.import_label()

        mock_dlg.assert_called_once_with(handler.panel, target_files=[data_obj])
        handler.panel.controller.get_loaded_data_list.assert_not_called()

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
            {"file1.txt": [0, 1, 0, 1]},
            "mapping",
        )
        handler.panel.controller.apply_labels_legacy.return_value = 1
        handler.import_label()
        handler.panel.controller.apply_labels_legacy.assert_called_once()

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
            {"file1.txt": [0, 1, 0, 1]},
            "mapping",
        )
        handler.panel.controller.apply_labels_legacy.return_value = 0

        handler.import_label()

        mock_mb.warning.assert_called()

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
            {"label1.txt": [0, 1], "label2.txt": [1, 0]},
            "mapping",
        )
        mock_map_dlg.return_value.exec.return_value = True
        mock_map_dlg.return_value.get_mapping.return_value = {
            "/file1.set": "label1.txt"
        }
        handler.panel.controller.apply_labels_batch.return_value = 1
        handler.import_label()
        handler.panel.controller.apply_labels_batch.assert_called_once()

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
            {"label1.txt": [0, 1], "label2.txt": [1, 0]},
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
            {"label1.txt": [0, 1], "label2.txt": [1, 0, 1, 0]},
            "mapping",
        )
        mock_map_dlg.return_value.exec.return_value = True
        mock_map_dlg.return_value.get_mapping.return_value = {
            "/file1.set": "label1.txt"
        }
        handler.panel.controller.apply_labels_batch.return_value = 1

        with patch.object(
            handler, "_filter_events_for_import", return_value=None
        ) as mock_filter:
            handler.import_label()

        mock_filter.assert_called_once_with([data_obj], None)
        handler.panel.controller.apply_labels_batch.assert_called_once()

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
            {
                "labels.txt": [0, 1],
                "events.csv": [{"onset": 0.0, "duration": 1.0, "label": "A"}],
            },
            "mapping",
        )

        handler.import_label()

        handler.panel.controller.apply_labels_batch.assert_not_called()
        handler.panel.controller.apply_labels_legacy.assert_not_called()
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
            {"label1.txt": [{"onset": 0.0, "duration": 1.0, "label": "A"}]},
            "mapping",
        )
        handler.panel.controller.apply_labels_batch.return_value = 1
        handler.import_label()
        handler.panel.controller.apply_labels_batch.assert_called_once()

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
            {"label1.txt": [0, 1]},
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

        with patch(
            "XBrainLab.ui.panels.dataset.actions.execute_application_command",
            side_effect=fake_execute,
        ):
            handler.import_label()

        assert saved
        assert saved[0].recipe_path == "/recipes/with_labels.json"
        assert "Recipe saved." in mock_mb.information.call_args.args[2]
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
            {"f.txt": [0, 1]},
            "mapping",
        )
        handler.panel.controller.apply_labels_legacy.side_effect = RuntimeError("fail")
        handler.import_label()
        mock_mb.critical.assert_called_once()

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
        handler.panel.controller.remove_files.assert_called()

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
        handler.show_context_menu(MagicMock())
        handler.panel.controller.update_metadata.assert_called_with(0, session="sess1")

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
            {"file1.txt": [0, 1, 0, 1]},
            "mapping",
        )
        handler.panel.controller.apply_labels_legacy.return_value = 1
        with patch("XBrainLab.ui.panels.dataset.actions.EventFilterDialog") as mock_efd:
            mock_efd.return_value.exec.return_value = True
            mock_efd.return_value.get_selected_ids.return_value = ["left"]
            handler.import_label()
        handler.panel.controller.apply_labels_legacy.assert_called_once()

    def test_analyze_label_map_single_sequence(self, handler):
        is_timestamp, target_count = handler._analyze_label_map(
            {"file1.txt": np.array([0, 1, 0, 1])}
        )
        assert is_timestamp is False
        assert target_count == 4

    def test_analyze_label_map_inconsistent_sequence_lengths(self, handler):
        is_timestamp, target_count = handler._analyze_label_map(
            {"file1.txt": np.array([0, 1]), "file2.txt": np.array([0, 1, 0])}
        )
        assert is_timestamp is False
        assert target_count is None

    def test_analyze_label_map_mixed_modes_raises(self, handler):
        with pytest.raises(
            ValueError,
            match="Cannot mix timestamp-style and sequence-style label files",
        ):
            handler._analyze_label_map(
                {
                    "file1.txt": np.array([0, 1]),
                    "events.csv": [{"onset": 0.0, "duration": 1.0, "label": "A"}],
                }
            )


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
        assert dlg.label_data_map == {}
        assert isinstance(dlg, QDialog)

    def test_remove_files_empty(self, dlg):
        dlg.remove_files()  # no items, should not crash

    def test_update_unique_labels_empty(self, dlg):
        dlg.update_unique_labels()
        assert dlg.unique_labels == []
        assert "No labels" in dlg.info_label.text()

    def test_update_unique_labels_sequence(self, dlg):
        dlg.label_data_map["f.txt"] = np.array([1, 2, 1, 3])
        dlg.update_unique_labels()
        assert dlg.unique_labels == [1, 2, 3]
        assert "3 unique" in dlg.info_label.text()

    def test_update_unique_labels_timestamp(self, dlg):
        dlg.label_data_map["f.csv"] = [
            {"label": 1, "onset": 0.0},
            {"label": 2, "onset": 1.0},
        ]
        dlg.update_unique_labels()
        assert dlg.unique_labels == [1, 2]

    def test_get_results_none_when_empty(self, dlg):
        lm, m = dlg.get_results()
        assert lm is None and m is None

    def test_get_result_alias(self, dlg):
        r = dlg.get_result()
        assert r == (None, None)

    def test_get_results_with_data(self, dlg):
        dlg.label_data_map["f.txt"] = np.array([1, 2])
        dlg.update_unique_labels()
        lm, m = dlg.get_results()
        assert lm is not None
        assert 1 in m and 2 in m

    @patch("XBrainLab.ui.dialogs.dataset.import_label_dialog.QMessageBox")
    def test_accept_empty(self, mock_mb, dlg):
        dlg.accept()
        mock_mb.warning.assert_called()

    @patch("XBrainLab.ui.dialogs.dataset.import_label_dialog.QMessageBox")
    def test_accept_no_mapping(self, mock_mb, dlg):
        dlg.label_data_map["f.txt"] = np.array([1])
        dlg.accept()
        mock_mb.warning.assert_called()

    def test_on_file_selection_changed(self, dlg):
        dlg.on_file_selection_changed()  # no-op, should not crash

    @patch("XBrainLab.ui.dialogs.dataset.import_label_dialog.load_label_file")
    def test_load_file(self, mock_load, dlg):
        mock_load.return_value = np.array([1, 2, 3])
        dlg.load_file("/path/labels.txt")
        assert "/path/labels.txt" in dlg.label_data_map

    def test_browse_files(self, dlg):
        # Manually simulate what browse_files does after file dialog
        dlg.load_file = MagicMock()
        dlg.label_data_map["a.txt"] = np.array([1, 2])
        dlg.file_list.addItem("a.txt")
        assert dlg.file_list.count() == 1
        dlg.update_unique_labels()
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

            mw = QMainWindow()
            qtbot.addWidget(mw)
            study = MagicMock()
            study.get_controller.return_value = MagicMock()
            m = AgentManager(mw, study)
            m.chat_controller = mock_cc.return_value
            yield m

    def test_update_ai_btn_state(self, mgr):
        mgr.main_window.ai_btn = MagicMock()
        mgr.update_ai_btn_state(True)
        mgr.main_window.ai_btn.setChecked.assert_called_with(True)

    def test_toggle_float_no_dock(self, mgr):
        mgr.chat_dock = None
        mgr._toggle_float()  # should not crash

    def test_toggle_float_with_dock(self, mgr, qtbot):
        from PyQt6.QtWidgets import QDockWidget

        dock = QDockWidget("test", mgr.main_window)
        mgr.chat_dock = dock
        mgr._toggle_float()
        assert dock.isFloating()

    def test_handle_user_input(self, mgr):
        mgr.agent_controller = MagicMock()
        mgr.handle_user_input("hello")
        mgr.chat_controller.add_user_message.assert_called_with("hello")
        mgr.agent_controller.handle_user_input.assert_called_with("hello")

    def test_stop_generation(self, mgr):
        mgr.agent_controller = MagicMock()
        mgr.stop_generation()
        mgr.agent_controller.stop_generation.assert_called_once()
        mgr.chat_controller.set_processing.assert_called_with(False)

    def test_set_model(self, mgr):
        mgr.agent_controller = MagicMock()
        mgr.vram_checker = MagicMock()
        mgr.set_model("Gemini")
        mgr.agent_controller.set_model.assert_called_with("local")
        mgr.vram_checker.check.assert_called_once_with(switching_to_local=True)

    def test_on_processing_state_changed(self, mgr):
        mgr.chat_panel = MagicMock()
        mgr.on_processing_state_changed(True)
        mgr.chat_panel.set_processing_state.assert_called_with(True)

    def test_start_new_conversation(self, mgr):
        mgr.agent_controller = MagicMock()
        mgr.agent_controller.reset_conversation = MagicMock()
        mgr.start_new_conversation()
        mgr.chat_controller.clear_conversation.assert_called_once()
        mgr.agent_controller.reset_conversation.assert_called_once()

    def test_on_generation_started(self, mgr):
        mgr.chat_panel = MagicMock()
        mgr._on_generation_started()
        assert mgr.chat_panel.current_agent_bubble is None
        mgr.chat_controller.set_processing.assert_called_with(True)

    def test_on_processing_finished(self, mgr):
        mgr.on_processing_finished()
        mgr.chat_controller.set_processing.assert_called_with(False)

    def test_on_agent_status_update_error(self, mgr):
        mgr.on_agent_status_update("Error occurred")
        mgr.chat_controller.set_processing.assert_called_with(False)

    def test_handle_agent_error(self, mgr):
        mgr.handle_agent_error("test error")
        mgr.chat_controller.set_processing.assert_called_with(False)
        mgr.chat_controller.add_agent_message.assert_called_once()

    def test_close(self, mgr):
        mgr.agent_controller = MagicMock()
        mgr.close()
        mgr.agent_controller.close.assert_called_once()

    def test_handle_user_interaction_switch_panel(self, mgr):
        mgr.main_window.switch_page = MagicMock()
        mgr.main_window.statusBar = MagicMock(return_value=MagicMock())
        mgr.handle_user_interaction("switch_panel", {"panel": "dataset"})
        mgr.main_window.switch_page.assert_called_with(0)

    def test_switch_panel_preprocess(self, mgr):
        mgr.main_window.switch_page = MagicMock()
        mgr.main_window.statusBar = MagicMock(return_value=MagicMock())
        mgr.switch_panel({"panel": "preprocess"})
        mgr.main_window.switch_page.assert_called_with(1)

    def test_switch_panel_training(self, mgr):
        mgr.main_window.switch_page = MagicMock()
        mgr.main_window.statusBar = MagicMock(return_value=MagicMock())
        mgr.switch_panel({"panel": "training"})
        mgr.main_window.switch_page.assert_called_with(2)

    def test_switch_panel_eval(self, mgr):
        mgr.main_window.switch_page = MagicMock()
        mgr.main_window.statusBar = MagicMock(return_value=MagicMock())
        mgr.switch_panel({"panel": "evaluation"})
        mgr.main_window.switch_page.assert_called_with(3)

    def test_switch_panel_visual_with_view(self, mgr):
        mgr.main_window.switch_page = MagicMock()
        target = MagicMock()
        mgr.main_window.stack = MagicMock()
        mgr.main_window.stack.widget.return_value = target
        mgr.main_window.statusBar = MagicMock(return_value=MagicMock())
        mgr.switch_panel({"panel": "visualization", "view_mode": "saliency_map"})
        mgr.main_window.switch_page.assert_called_with(4)
        target.tabs.setCurrentIndex.assert_called_with(0)

    def test_switch_panel_unknown(self, mgr):
        mgr.main_window.switch_page = MagicMock()
        mgr.main_window.statusBar = MagicMock(return_value=MagicMock())
        mgr.switch_panel({"panel": "unknown_panel"})
        # Should not crash; statusBar shows error

    def test_prepare_model_deletion_no_controller(self, mgr):
        mgr.agent_controller = None
        assert mgr.prepare_model_deletion("model") is True

    def test_prepare_model_deletion_local_mode(self, mgr):
        mgr.agent_controller = MagicMock()
        worker = MagicMock()
        mgr.agent_controller.worker = worker
        worker.engine.config.active_mode = "local"
        with patch("XBrainLab.ui.components.agent_manager.QMessageBox.warning"):
            assert mgr.prepare_model_deletion("model") is False
        mgr.agent_controller.set_model.assert_not_called()

    def test_prepare_model_deletion_gemini(self, mgr):
        mgr.agent_controller = MagicMock()
        worker = MagicMock()
        mgr.agent_controller.worker = worker
        worker.engine.config.active_mode = "gemini"
        with patch("XBrainLab.ui.components.agent_manager.QMessageBox.warning"):
            assert mgr.prepare_model_deletion("model") is False
        mgr.agent_controller.set_model.assert_not_called()

    def test_check_vram_not_local(self, mgr):
        mgr.agent_controller = None
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

    @patch("XBrainLab.ui.components.agent_manager.PickMontageDialog")
    def test_open_montage_no_epoch(self, mock_dlg, mgr):
        mgr.study.epoch_data = None
        mgr.main_window.statusBar = MagicMock(return_value=MagicMock())
        mgr.open_montage_picker_dialog({})
        mock_dlg.assert_not_called()

    @patch("XBrainLab.ui.components.agent_manager.PickMontageDialog")
    def test_open_montage_accepted(self, mock_dlg_cls, mgr):
        mgr.study.epoch_data = MagicMock()
        mgr.study.epoch_data.get_mne.return_value.info = {"ch_names": ["C3", "C4"]}
        dlg = MagicMock()
        mock_dlg_cls.return_value = dlg
        dlg.exec.return_value = True
        dlg.get_result.return_value = (["C3", "C4"], [[0, 0], [1, 0]])
        mgr.chat_panel = MagicMock()
        mgr.chat_panel.debug_mode = False
        mgr.agent_controller = MagicMock()
        mgr.open_montage_picker_dialog({"montage_name": "standard_1020"})
        mgr.preprocess_controller.apply_montage.assert_called()


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

    def test_update_plot_no_eval(self, widget):
        plan = MagicMock()
        plan.get_eval_record.return_value = None
        widget.update_plot(plan, MagicMock(), "grad", False, None)
        assert "No evaluation" in widget.error_label.text()

    @patch(
        "XBrainLab.ui.panels.visualization.saliency_views.topomap_view.VisualizerType"
    )
    def test_update_plot_no_montage(self, mock_vt, widget):
        plan = MagicMock()
        eval_rec = MagicMock()
        trainer = MagicMock()
        epoch_data = MagicMock()
        epoch_data.get_montage_position.return_value = None
        trainer.get_dataset.return_value.get_epoch_data.return_value = epoch_data
        widget.update_plot(plan, trainer, "grad", False, eval_rec)
        assert "Montage" in widget.error_label.text()

    @patch(
        "XBrainLab.ui.panels.visualization.saliency_views.topomap_view.VisualizerType"
    )
    def test_update_plot_success(self, mock_vt, widget):
        import matplotlib.pyplot as plt

        plan = MagicMock()
        eval_rec = MagicMock()
        trainer = MagicMock()
        epoch_data = MagicMock()
        epoch_data.get_montage_position.return_value = [[0, 0, 0]]
        trainer.get_dataset.return_value.get_epoch_data.return_value = epoch_data
        fig, _ax = plt.subplots()
        mock_vt.SaliencyTopoMap.value.return_value.get_plt.return_value = fig
        widget.update_plot(plan, trainer, "grad", False, eval_rec)
        plt.close(fig)

    @patch(
        "XBrainLab.ui.panels.visualization.saliency_views.topomap_view.VisualizerType"
    )
    def test_update_plot_no_data(self, mock_vt, widget):
        plan = MagicMock()
        eval_rec = MagicMock()
        trainer = MagicMock()
        epoch_data = MagicMock()
        epoch_data.get_montage_position.return_value = [[0, 0, 0]]
        trainer.get_dataset.return_value.get_epoch_data.return_value = epoch_data
        mock_vt.SaliencyTopoMap.value.return_value.get_plt.return_value = None
        widget.update_plot(plan, trainer, "grad", False, eval_rec)


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

    def test_update_plot_no_eval(self, widget):
        plan = MagicMock()
        plan.get_eval_record.return_value = None
        widget.update_plot(plan, MagicMock(), "grad", False, None)
        assert "No evaluation" in widget.error_label.text()

    @patch(
        "XBrainLab.ui.panels.visualization.saliency_views.spectrogram_view.VisualizerType"
    )
    def test_update_plot_success(self, mock_vt, widget):
        import matplotlib.pyplot as plt

        plan = MagicMock()
        eval_rec = MagicMock()
        trainer = MagicMock()
        epoch_data = MagicMock()
        trainer.get_dataset.return_value.get_epoch_data.return_value = epoch_data
        fig, _ax = plt.subplots()
        mock_vt.SaliencySpectrogramMap.value.return_value.get_plt.return_value = fig
        widget.update_plot(plan, trainer, "grad", False, eval_rec)
        plt.close(fig)

    @patch(
        "XBrainLab.ui.panels.visualization.saliency_views.spectrogram_view.VisualizerType"
    )
    def test_update_plot_none(self, mock_vt, widget):
        plan = MagicMock()
        eval_rec = MagicMock()
        trainer = MagicMock()
        epoch_data = MagicMock()
        trainer.get_dataset.return_value.get_epoch_data.return_value = epoch_data
        mock_vt.SaliencySpectrogramMap.value.return_value.get_plt.return_value = None
        widget.update_plot(plan, trainer, "grad", False, eval_rec)

    @patch(
        "XBrainLab.ui.panels.visualization.saliency_views.spectrogram_view.VisualizerType"
    )
    def test_update_plot_exception(self, mock_vt, widget):
        plan = MagicMock()
        eval_rec = MagicMock()
        trainer = MagicMock()
        trainer.get_dataset.side_effect = RuntimeError("fail")
        widget.update_plot(plan, trainer, "grad", False, eval_rec)


# ====================================================================
# PreprocessPlotter (partial - covers _get_chan_data and helpers)
# ====================================================================


class TestPreprocessPlotter:
    @pytest.fixture
    def plotter(self):
        from XBrainLab.ui.panels.preprocess.plotters.preprocess_plotter import (
            PreprocessPlotter,
        )

        widget = MagicMock()
        ctrl = MagicMock()
        return PreprocessPlotter(widget, ctrl)

    def test_get_chan_data_raw(self, plotter):
        obj = MagicMock()
        obj.is_raw.return_value = True
        obj.get_sfreq.return_value = 256.0
        mne_obj = MagicMock()
        mne_obj.times = np.arange(0, 5 * 256) / 256
        mne_obj.get_data.return_value = np.random.randn(1, 256 * 5)
        obj.get_mne.return_value = mne_obj
        x, y = plotter._get_chan_data(obj, 0, start_time=0, duration=5)
        assert x is not None and y is not None
        assert len(y) == 256 * 5

    def test_get_chan_data_raw_out_of_range(self, plotter):
        obj = MagicMock()
        obj.is_raw.return_value = True
        obj.get_sfreq.return_value = 256.0
        mne_obj = MagicMock()
        mne_obj.times = np.array([0.0])  # very short
        obj.get_mne.return_value = mne_obj
        x, y = plotter._get_chan_data(obj, 0, start_time=100, duration=5)
        assert x is None and y is None

    def test_get_chan_data_raw_empty(self, plotter):
        obj = MagicMock()
        obj.is_raw.return_value = True
        obj.get_sfreq.return_value = 256.0
        mne_obj = MagicMock()
        mne_obj.times = np.arange(0, 256) / 256
        mne_obj.get_data.return_value = np.array([])
        obj.get_mne.return_value = mne_obj
        x, y = plotter._get_chan_data(obj, 0, start_time=0, duration=5)
        assert x is None and y is None
