from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QTreeWidget

from scripts.dev.report_data_interpretation_format_matrix import (
    FORMAT_CASES,
    FormatCase,
    _write_case_fixture,
)
from XBrainLab.backend.application import (
    ApplicationService,
    PreviewInterpretationCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.backend.study import Study
from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (
    DataInterpretationPreviewDialog,
)

STEP_TITLES = (
    "Choose EEG Data",
    "Load Labels",
    "Review Metadata",
    "Match Labels",
    "Review and Import",
)


@pytest.mark.parametrize("case", FORMAT_CASES, ids=lambda case: case.case_id)
def test_data_import_wizard_opens_all_steps_for_format_matrix(
    qtbot,
    tmp_path: Path,
    case: FormatCase,
) -> None:
    """Every supported format-boundary case should survive the real wizard shell."""

    case_dir = tmp_path / case.case_id
    _write_case_fixture(case_dir, case)
    source_path = case_dir / case.source_entry
    service = ApplicationService(Study())

    scan = service.execute(
        ScanSourceCommand(
            source_path=str(source_path),
            source_hint=case.source_hint,
        ),
    )
    assert scan.ok, scan.message

    preview = service.execute(PreviewInterpretationCommand())
    assert preview.ok, preview.message

    validation = service.execute(ValidateInterpretationCommand())
    assert validation.ok, validation.message
    validation_decision = validation.diagnostics["validation_decision"]
    assert validation_decision["decision"] == case.expected_validation

    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result=scan.diagnostics["scan_result"],
        preview=preview.diagnostics["preview"],
        validation_decision=validation_decision,
    )
    qtbot.addWidget(dialog)
    dialog.resize(1220, 920)
    dialog.show()
    qtbot.wait(0)

    for step_title in STEP_TITLES:
        dialog._go_to_step(dialog._step_titles.index(step_title))
        qtbot.wait(0)

        assert dialog.cancel_button.isVisibleTo(dialog)
        assert dialog.back_button.isVisibleTo(dialog)
        assert _visible_step_text(dialog).strip()
        assert _nested_tree_scrollbars_are_disabled(dialog)

        if step_title == "Review and Import":
            assert dialog.apply_button.isVisibleTo(dialog)
            assert not dialog.next_button.isVisibleTo(dialog)
        else:
            assert dialog.next_button.isVisibleTo(dialog)
            assert step_title in dialog._step_titles

    assert "Found" in str(preview.diagnostics["preview"].get("summary", ""))


def _visible_step_text(dialog: DataInterpretationPreviewDialog) -> str:
    current = dialog.step_stack.currentWidget()
    assert current is not None
    return "\n".join(
        label.text()
        for label in current.findChildren(QLabel)
        if label.isVisibleTo(current) and label.text().strip()
    )


def _nested_tree_scrollbars_are_disabled(
    dialog: DataInterpretationPreviewDialog,
) -> bool:
    return all(
        tree.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        for tree in dialog.findChildren(QTreeWidget)
    )
