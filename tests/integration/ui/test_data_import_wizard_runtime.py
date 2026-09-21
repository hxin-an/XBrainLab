from __future__ import annotations

from pathlib import Path

import mne
import numpy as np
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QComboBox, QFileDialog, QLabel, QLineEdit

from tests.integration.ui.data_import_wizard_harness import (
    replace_line_edit_text,
    select_combo_data,
)
from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    CreateEpochCommand,
    PreviewInterpretationCommand,
    ReloadInterpretationRecipeCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (
    DataInterpretationPreviewDialog,
)


def _show_step(dialog: DataInterpretationPreviewDialog, title: str) -> None:
    dialog._go_to_step(dialog._step_titles.index(title))


def _start_dialog(
    service: ApplicationService,
    eeg_file: Path,
    *,
    label_sources: list[str] | None = None,
) -> DataInterpretationPreviewDialog:
    scan_result = service.execute(
        ScanSourceCommand(
            source_path=str(eeg_file),
            source_hint="file",
            label_sources=list(label_sources or []),
        ),
    )
    assert scan_result.ok, scan_result.message
    preview_result = service.execute(PreviewInterpretationCommand())
    assert preview_result.ok, preview_result.message
    candidate = preview_result.diagnostics["candidate"]
    validation_result = service.execute(
        ValidateInterpretationCommand(candidate_id=candidate["candidate_id"]),
    )
    assert validation_result.ok, validation_result.message

    return DataInterpretationPreviewDialog(
        parent=None,
        scan_result=scan_result.diagnostics["scan_result"],
        preview=preview_result.diagnostics["preview"],
        validation_decision=validation_result.diagnostics["validation_decision"],
    )


def test_load_label_folder_rescan_selects_loaded_labels_for_matching(
    qtbot,
    monkeypatch,
    tmp_path: Path,
) -> None:
    eeg_file = tmp_path / "sub-01_task-mi_raw.fif"
    label_folder = tmp_path / "external-labels"
    label_file = label_folder / "sub-01_task-mi_labels.tsv"
    eeg_file.write_bytes(b"not loaded during interpretation scan")
    label_folder.mkdir()
    label_file.write_text(
        "onset\ttrial_type\n0.0\tleft\n1.0\tright\n",
        encoding="utf-8",
    )
    service = ApplicationService()
    dialog = _start_dialog(service, eeg_file)
    qtbot.addWidget(dialog)
    dialog.resize(1040, 760)
    dialog.show()
    qtbot.wait(0)
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *_args, **_kwargs: str(label_folder),
    )

    _show_step(dialog, "Load Labels")
    dialog.add_label_folder_btn.click()
    qtbot.wait(0)
    dialog.next_button.click()
    qtbot.wait(0)

    result = dialog.get_result()
    assert result["label_sources_changed"] is True
    assert result["resume_step"] == "Review Metadata"

    dialog = _start_dialog(
        service,
        eeg_file,
        label_sources=[str(label_folder)],
    )
    qtbot.addWidget(dialog)
    dialog.resize(1040, 760)
    dialog.show()
    qtbot.wait(0)
    assert str(label_file.resolve()) in dialog.scan_result.get("label_carriers", [])

    _show_step(dialog, "Match Labels")
    qtbot.wait(0)

    assert dialog.label_source_mode_combo.currentData() == "loaded_label_files"
    assert dialog.pairing_card.isVisibleTo(dialog)
    assert "1/1 EEG files paired" in dialog.pairing_status_label.text()
    assert label_file.name in "\n".join(
        combo.currentText() for combo in dialog._eeg_label_widgets.values()
    )


@pytest.mark.parametrize("extension,delimiter", [("tsv", "\t"), ("csv", ",")])
def test_changing_label_field_requests_backend_repreview_at_match_labels(
    qtbot,
    tmp_path: Path,
    extension: str,
    delimiter: str,
) -> None:
    """Visible timestamp/field choices must survive real apply, epoch and replay.

    This drives the real widget and Commands, not the outer async coordinator.
    """
    eeg_file = tmp_path / "sub-01_task-mi_raw.fif"
    label_file = tmp_path / f"sub-01_task-mi_events.{extension}"
    raw = mne.io.RawArray(
        np.zeros((2, 400)), mne.create_info(["C3", "C4"], 100, "eeg"), first_samp=500
    )
    raw.save(eeg_file, overwrite=True, verbose=False)
    label_file.write_text(
        "\n".join(
            delimiter.join(row)
            for row in (
                ("onset", "trial_type", "value"),
                ("0.5", "stimulus", "left"),
                ("1.5", "stimulus", "right"),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    source_bytes = {path: path.read_bytes() for path in (eeg_file, label_file)}
    service = ApplicationService()
    dialog = _start_dialog(
        service,
        eeg_file,
        label_sources=[str(label_file)],
    )
    qtbot.addWidget(dialog)
    dialog.resize(1040, 760)
    dialog.show()
    qtbot.wait(0)

    _show_step(dialog, "Match Labels")
    dialog.scroll_area.ensureWidgetVisible(dialog.rule_label_field_combo)
    select_combo_data(dialog.rule_label_field_combo, "value")
    QTest.mouseClick(dialog.next_button, Qt.MouseButton.LeftButton)
    qtbot.wait(0)

    result = dialog.get_result()
    assert dialog.result() == dialog.DialogCode.Accepted
    assert result["resume_step"] == "Match Labels"
    assert {
        choice["label_field"]
        for choice in result["choices"]["label_carrier_choices"].values()
    } == {"value"}
    try:
        preview = service.execute(
            PreviewInterpretationCommand(choices=result["choices"])
        )
        validation = service.execute(ValidateInterpretationCommand())
        assert preview.ok, preview.message
        assert validation.ok, validation.message
        refreshed = DataInterpretationPreviewDialog(
            scan_result=dialog.scan_result,
            preview=preview.diagnostics["preview"],
            validation_decision=validation.diagnostics["validation_decision"],
            choices=result["choices"],
            initial_step="Match Labels",
        )
        qtbot.addWidget(refreshed)
        refreshed.show()
        qtbot.wait(0)
        editor = refreshed.event_value_editor
        assert editor is not None and editor.isVisibleTo(refreshed)
        values = [
            label.text()
            for label in editor.findChildren(QLabel, "DataImportValueDecisionValue")
        ]
        assert values == ["left", "right"]
        for role, use, name, expected in zip(
            editor.findChildren(QComboBox, "EventValueRoleSelector"),
            editor.findChildren(QComboBox, "EventValueUseSelector"),
            editor.findChildren(QLineEdit, "EventValueClassNameEditor"),
            ("A", "B"),
            strict=True,
        ):
            refreshed.scroll_area.ensureWidgetVisible(role)
            select_combo_data(role, "stimulus")
            select_combo_data(use, "class")
            replace_line_edit_text(name, expected)
            QTest.keyClick(name, Qt.Key.Key_Tab)
        assert editor.is_complete()
        assert not service.study.loaded_data_list
        choices = refreshed.get_result()["choices"]
        recipe = tmp_path / "timestamp-recipe.json"
        for command in (
            PreviewInterpretationCommand(choices=choices),
            ValidateInterpretationCommand(),
            ApplyInterpretationCommand(confirmed=True),
            SaveInterpretationRecipeCommand(str(recipe)),
        ):
            outcome = service.execute(command)
            assert outcome.ok, outcome.message
        replay = ApplicationService()
        try:
            for command in (
                ReloadInterpretationRecipeCommand(str(recipe)),
                ValidateInterpretationCommand(),
                ApplyInterpretationCommand(confirmed=True),
            ):
                outcome = replay.execute(command)
                assert outcome.ok, outcome.message
            for imported in (service, replay):
                outcome = imported.execute(CreateEpochCommand(t_min=0.0, t_max=0.25))
                assert outcome.ok, outcome.message
                epochs = imported.study.preprocessed_data_list[0].get_mne()
                assert isinstance(epochs, mne.BaseEpochs)
                np.testing.assert_array_equal(epochs.events[:, 0], [550, 650])
                names = {value: key for key, value in epochs.event_id.items()}
                assert [names[row[2]] for row in epochs.events] == ["A", "B"]
        finally:
            replay.close()
        assert {path: path.read_bytes() for path in source_bytes} == source_bytes
    finally:
        service.close()
