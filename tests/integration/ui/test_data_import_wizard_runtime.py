from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QFileDialog

from XBrainLab.backend.application import (
    ApplicationService,
    PreviewInterpretationCommand,
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


def test_changing_label_field_requests_backend_repreview_at_match_labels(
    qtbot,
    tmp_path: Path,
) -> None:
    eeg_file = tmp_path / "sub-01_task-mi_raw.fif"
    label_file = tmp_path / "sub-01_task-mi_events.tsv"
    eeg_file.write_bytes(b"not loaded during interpretation scan")
    label_file.write_text(
        "onset\ttrial_type\tvalue\n0.0\tstimulus\tleft\n1.0\tstimulus\tright\n",
        encoding="utf-8",
    )
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
    value_index = dialog.rule_label_field_combo.findData("value")
    assert value_index >= 0
    dialog.rule_label_field_combo.setCurrentIndex(value_index)
    dialog.next_button.click()
    qtbot.wait(0)

    result = dialog.get_result()
    assert dialog.result() == dialog.DialogCode.Accepted
    assert result["resume_step"] == "Match Labels"
    assert {
        choice["label_field"]
        for choice in result["choices"]["label_carrier_choices"].values()
    } == {"value"}
