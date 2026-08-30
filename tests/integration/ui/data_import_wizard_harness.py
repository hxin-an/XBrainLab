from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QPoint, QRect, Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.study import Study
from XBrainLab.ui.application_capabilities import application_ui_runtime
from XBrainLab.ui.dialogs.dataset.bids_subject_selection_dialog import (
    BidsSubjectSelectionDialog,
)
from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (
    DataInterpretationPreviewDialog,
)
from XBrainLab.ui.dialogs.dataset.eeg_source_chooser_dialog import (
    EegSourceChooserDialog,
)
from XBrainLab.ui.panels.dataset.panel import DatasetPanel


class RefreshProbe:
    def update_panel(self) -> None:
        pass

    def mark_refresh_dirty(self) -> None:
        pass


class DatasetHost(QWidget):
    def __init__(self, study: Study) -> None:
        super().__init__()
        self.study = study
        self.stack = QStackedWidget(self)
        self.dataset_panel: DatasetPanel | None = None
        self.preprocess_panel = RefreshProbe()
        self.training_panel = RefreshProbe()
        self.evaluation_panel = RefreshProbe()
        self.visualization_panel = RefreshProbe()
        self.info_refresh_count = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack)

    def update_info_panel(self) -> None:
        self.info_refresh_count += 1


def build_dataset_panel(qtbot: Any) -> tuple[DatasetHost, DatasetPanel, Any]:
    host = DatasetHost(Study())
    qtbot.addWidget(host)
    controller = host.study.get_controller("dataset")
    panel = DatasetPanel(controller=controller, parent=host)
    host.dataset_panel = panel
    host.stack.addWidget(panel)
    host.resize(1180, 760)
    host.show()
    panel.update_panel()
    qtbot.wait(0)
    runtime = application_ui_runtime(panel)
    assert runtime is not None
    return host, panel, runtime


def build_dataset_panel_for_runner() -> tuple[
    QApplication, DatasetHost, DatasetPanel, Any
]:
    app = QApplication.instance() or QApplication([])
    host = DatasetHost(Study())
    controller = host.study.get_controller("dataset")
    panel = DatasetPanel(controller=controller, parent=host)
    host.dataset_panel = panel
    host.stack.addWidget(panel)
    host.resize(1180, 760)
    host.show()
    panel.update_panel()
    app.processEvents()
    runtime = application_ui_runtime(panel)
    assert runtime is not None
    return app, host, panel, runtime


@dataclass
class Heartbeat:
    timer: QTimer = field(default_factory=QTimer)
    ticks: list[float] = field(default_factory=list)

    def start(self, interval_ms: int = 50) -> None:
        self.timer.setInterval(interval_ms)
        self.timer.timeout.connect(self._record)
        self._record()
        self.timer.start()

    def stop(self) -> list[float]:
        if self.timer.isActive():
            self.timer.stop()
        return list(self.ticks)

    def _record(self) -> None:
        self.ticks.append(time.perf_counter())


def select_combo_data(combo: QComboBox, value: str) -> None:
    index = combo.findData(value)
    if index < 0:
        raise AssertionError(f"{combo.objectName()} does not offer {value!r}.")
    combo.setFocus()
    QTest.mouseClick(combo, Qt.MouseButton.LeftButton)
    QTest.keyClick(combo, Qt.Key.Key_Home)
    for _ in range(index):
        QTest.keyClick(combo, Qt.Key.Key_Down)
    QTest.keyClick(combo, Qt.Key.Key_Return)
    combo.hidePopup()
    QApplication.processEvents()
    if combo.currentData() != value:
        raise AssertionError(
            f"{combo.objectName()} selected {combo.currentData()!r}, expected {value!r}."
        )


def replace_line_edit_text(editor: QLineEdit, value: str) -> None:
    QTest.mouseClick(editor, Qt.MouseButton.LeftButton)
    QTest.keyClick(editor, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(editor, value)


def decision_value_text(label: QLabel) -> str:
    return str(label.accessibleName() or label.text())


def capture_teacher_ui(
    dialog: DataInterpretationPreviewDialog,
    filename: str,
    *,
    widget: QWidget | None = None,
) -> None:
    """Capture an entire visible teaching surface when artifacts are requested."""
    raw_output_dir = os.environ.get("XBRAINLAB_TEACHER_UI_ARTIFACT_DIR", "").strip()
    if not raw_output_dir:
        return
    output_dir = Path(raw_output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    QApplication.processEvents()
    if widget is None:
        pixmap = dialog.grab()
    else:
        target_rect = QRect(widget.mapTo(dialog, QPoint(0, 0)), widget.size())
        if not dialog.rect().contains(target_rect):
            raise AssertionError(
                f"UI artifact target is not fully visible in the dialog: {filename}"
            )
        pixmap = dialog.grab(target_rect)
    output_path = output_dir / filename
    if pixmap.isNull() or not pixmap.save(str(output_path), "PNG"):
        raise AssertionError(f"Failed to capture current UI artifact: {output_path}")


def complete_required_metadata(dialog: DataInterpretationPreviewDialog) -> None:
    for index in range(dialog.file_tree.topLevelItemCount()):
        item = dialog.file_tree.topLevelItem(index)
        if item is None:
            continue
        if not item.text(1).strip():
            item.setText(1, f"subject-{index + 1:02d}")
        if not item.text(3).strip():
            item.setText(3, "rest")
    missing = dialog._metadata_required_missing_fields(
        dialog._metadata_completion_counts()[1]
    )
    if missing:
        raise AssertionError(f"Required metadata remains incomplete: {missing!r}")


def complete_bbci_internal_event_choices(
    dialog: DataInterpretationPreviewDialog,
) -> None:
    def move_event(code: str, action: str) -> None:
        button = next(
            (
                candidate
                for candidate in dialog.findChildren(QPushButton)
                if candidate.objectName() == "DataImportInlineAction"
                and candidate.property("event_code") == code
                and candidate.text() == action
            ),
            None,
        )
        if button is None:
            raise AssertionError(f"Missing {action!r} control for GDF {code}.")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        QApplication.processEvents()

    for code in ("768", "781", "785"):
        move_event(code, "Exclude from training")
    for code in ("769", "770"):
        move_event(code, "Use for training")
    table = dialog.findChild(QFrame, "DataImportInternalLabelsTable")
    if table is None:
        raise AssertionError("BBCI training-label table is not visible.")
    selectors = [item for item in table.findChildren(QComboBox) if item.isEditable()]
    if len(selectors) != 2:
        raise AssertionError(
            f"Expected two visible BBCI class-name controls, found {len(selectors)}."
        )
    for selector, class_name in zip(selectors, ("left", "right"), strict=True):
        selector.setFocus()
        QTest.mouseClick(selector, Qt.MouseButton.LeftButton)
        QTest.keyClick(selector, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClicks(selector, class_name)
    QApplication.processEvents()
    if not dialog.next_button.isEnabled():
        raise AssertionError("Complete BBCI Match Labels did not enable Next.")


@dataclass
class BbciWizardDriver:
    modal_getter: Any
    timer: QTimer = field(default_factory=QTimer)
    phase: int = 0
    errors: list[str] = field(default_factory=list)
    chooser_accepted_at: float | None = None
    wizard_ready_at: float | None = None
    apply_clicked_at: float | None = None

    def start(self) -> None:
        self.timer.setInterval(20)
        self.timer.timeout.connect(self._poll)
        self.timer.start()

    def stop(self) -> None:
        self.timer.stop()

    def _fail(self, message: str, modal: QWidget | None) -> None:
        self.errors.append(message)
        self.stop()
        if isinstance(modal, QDialog):
            modal.reject()

    def _poll(self) -> None:
        modal = self.modal_getter()
        if isinstance(modal, EegSourceChooserDialog):
            QTest.mouseClick(modal.choose_files_button, Qt.MouseButton.LeftButton)
            button = modal.button_box.button(QDialogButtonBox.StandardButton.Ok)
            if button is None or not button.isEnabled():
                self._fail("Import Data did not retain the selected BBCI file.", modal)
                return
            self.chooser_accepted_at = time.perf_counter()
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
            return
        if not isinstance(modal, DataInterpretationPreviewDialog):
            return
        try:
            if self.wizard_ready_at is None:
                self.wizard_ready_at = time.perf_counter()
            if modal.step_stack.currentIndex() != self.phase:
                return
            if self.phase == 0:
                self.phase = 1
                QTest.mouseClick(modal.next_button, Qt.MouseButton.LeftButton)
            elif self.phase == 1:
                self.phase = 2
                QTest.mouseClick(modal.next_button, Qt.MouseButton.LeftButton)
            elif self.phase == 2:
                complete_required_metadata(modal)
                self.phase = 3
                QTest.mouseClick(modal.next_button, Qt.MouseButton.LeftButton)
            elif self.phase == 3:
                complete_bbci_internal_event_choices(modal)
                self.phase = 4
                QTest.mouseClick(modal.next_button, Qt.MouseButton.LeftButton)
            elif self.phase == 4:
                if not modal.apply_button.isEnabled():
                    self._fail("Reviewed BBCI import did not enable Apply.", modal)
                    return
                self.apply_clicked_at = time.perf_counter()
                self.phase = 5
                QTest.mouseClick(modal.apply_button, Qt.MouseButton.LeftButton)
        except Exception as exc:
            self._fail(f"{type(exc).__name__}: {exc}", modal)


@dataclass
class SuggestedLabelWizardDriver:
    """Drive the real suggested-label path for file or folder EEG sources.

    This deliberately accepts the visible defaults instead of reconstructing
    import choices.  It is shared by the external-label integration test and
    the dev profiler so both exercise the same chooser, review, Apply, and
    publication path.
    """

    modal_getter: Any
    source_kind: str = "files"
    timer: QTimer = field(default_factory=QTimer)
    phase: int = 0
    errors: list[str] = field(default_factory=list)
    unexpected_messages: list[str] = field(default_factory=list)
    chooser_accepted_at: float | None = None
    wizard_ready_at: float | None = None
    apply_clicked_at: float | None = None

    def start(self, interval_ms: int = 5) -> None:
        if self.source_kind not in {"files", "folder"}:
            raise ValueError(f"Unsupported EEG source kind: {self.source_kind!r}")
        self.timer.setInterval(interval_ms)
        self.timer.timeout.connect(self._poll)
        self.timer.start()

    def stop(self) -> None:
        self.timer.stop()

    def _fail(self, message: str, modal: QWidget | None) -> None:
        self.errors.append(message)
        self.stop()
        if isinstance(modal, QDialog):
            modal.reject()

    def _poll(self) -> None:
        modal = self.modal_getter()
        try:
            if isinstance(modal, EegSourceChooserDialog):
                button = (
                    modal.choose_files_button
                    if self.source_kind == "files"
                    else modal.choose_folder_button
                )
                QTest.mouseClick(button, Qt.MouseButton.LeftButton)
                continue_button = modal.button_box.button(
                    QDialogButtonBox.StandardButton.Ok
                )
                if continue_button is None or not continue_button.isEnabled():
                    self._fail(
                        "Import Data did not retain the selected EEG source.", modal
                    )
                    return
                self.chooser_accepted_at = time.perf_counter()
                QTest.mouseClick(continue_button, Qt.MouseButton.LeftButton)
                return
            if isinstance(modal, QMessageBox):
                self.unexpected_messages.append(
                    f"{modal.windowTitle()}: {modal.text()}"
                )
                self._fail(self.unexpected_messages[-1], modal)
                return
            if not isinstance(modal, DataInterpretationPreviewDialog):
                return
            if self.wizard_ready_at is None:
                self.wizard_ready_at = time.perf_counter()
            if self.phase < 4:
                if modal.step_stack.currentIndex() != self.phase:
                    return
                if self.phase == 2:
                    for row in range(modal.file_tree.topLevelItemCount()):
                        item = modal.file_tree.topLevelItem(row)
                        if item is not None:
                            item.setText(1, item.text(0).rsplit(".", 1)[0])
                if not modal.next_button.isEnabled():
                    self._fail(
                        f"Next is disabled at {modal._step_titles[self.phase]}", modal
                    )
                    return
                self.phase += 1
                QTest.mouseClick(modal.next_button, Qt.MouseButton.LeftButton)
                return
            if modal.step_stack.currentIndex() != 4:
                return
            if not modal.apply_button.isEnabled():
                self._fail(
                    "Confirm and Import is disabled for suggested defaults: "
                    f"facts={modal._submission_facts()!r}; "
                    f"choices={modal.get_result().get('choices')!r}; "
                    f"placement={modal._review_label_placement_text()!r}",
                    modal,
                )
                return
            self.apply_clicked_at = time.perf_counter()
            self.phase = 5
            QTest.mouseClick(modal.apply_button, Qt.MouseButton.LeftButton)
        except Exception as exc:
            self._fail(f"{type(exc).__name__}: {exc}", modal)


def complete_openneuro_event_values(dialog: DataInterpretationPreviewDialog) -> None:
    if dialog.label_source_mode_combo.currentData() != "loaded_label_files":
        select_combo_data(dialog.label_source_mode_combo, "loaded_label_files")
    editor = dialog.event_value_editor
    if editor is None or not editor.isVisibleTo(dialog):
        raise AssertionError("OpenNeuro Match Labels did not expose value decisions.")
    expected = {
        "ignore",
        "noise",
        "noise_with_reponse",
        "oddball",
        "oddball_with_reponse",
        "response",
        "standard",
        "standard_with_reponse",
    }
    if set(editor.unresolved_values()) != expected:
        raise AssertionError(
            "OpenNeuro value preview did not refresh to the selected `value` "
            f"column: {editor.unresolved_values()!r}"
        )
    values = [
        decision_value_text(label)
        for label in editor.findChildren(QLabel)
        if label.objectName() == "DataImportValueDecisionValue"
    ]
    role_selectors = editor.findChildren(QComboBox, "EventValueRoleSelector")
    use_selectors = editor.findChildren(QComboBox, "EventValueUseSelector")
    class_editors = editor.findChildren(QLineEdit, "EventValueClassNameEditor")
    if not (
        len(values)
        == len(role_selectors)
        == len(use_selectors)
        == len(class_editors)
        == len(expected)
    ):
        raise AssertionError(
            "OpenNeuro value controls are incomplete: "
            f"values={values!r}, roles={len(role_selectors)}, "
            f"uses={len(use_selectors)}, classes={len(class_editors)}."
        )
    decisions = {
        raw_value: (
            ("response", "ignore", "")
            if raw_value == "response"
            else ("system", "ignore", "")
            if raw_value == "ignore"
            else ("stimulus", "class", raw_value.replace("_with_reponse", ""))
        )
        for raw_value in expected
    }
    for raw_value, role_selector, use_selector, class_editor in zip(
        values, role_selectors, use_selectors, class_editors, strict=True
    ):
        if raw_value not in decisions:
            raise AssertionError(f"Unexpected OpenNeuro event value: {raw_value}")
        role, use, class_name = decisions[raw_value]
        dialog.scroll_area.ensureWidgetVisible(role_selector)
        select_combo_data(role_selector, role)
        select_combo_data(use_selector, use)
        if class_name:
            replace_line_edit_text(class_editor, class_name)
    if not editor.is_complete():
        raise AssertionError(
            "OpenNeuro event-value decisions remain incomplete: "
            f"{editor.unresolved_values()!r}"
        )
    capture_teacher_ui(dialog, "openneuro-match-labels-dialog.png")
    value_table = editor.findChild(QFrame, "DataImportValueDecisionTable")
    if value_table is None:
        raise AssertionError("OpenNeuro event-value table is unavailable.")
    capture_teacher_ui(
        dialog,
        "openneuro-event-value-controls.png",
        widget=value_table,
    )


@dataclass
class P300BidsWizardDriver:
    modal_getter: Any
    timer: QTimer = field(default_factory=QTimer)
    phase: int = 0
    errors: list[str] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)
    chooser_accepted_at: float | None = None
    wizard_ready_at: float | None = None
    apply_clicked_at: float | None = None
    dialog: DataInterpretationPreviewDialog | None = None
    fresh_review_count: int = 0
    max_heartbeat_gap_seconds: float = 0.0
    max_heartbeat_gap_context: str = "P300 shared modal driver"
    last_heartbeat_at: float = field(default_factory=time.monotonic)

    def start(self, interval_ms: int = 20) -> None:
        self.timer.setInterval(interval_ms)
        self.timer.timeout.connect(self._poll)
        self.timer.start()

    def stop(self) -> None:
        self.timer.stop()

    def _fail(self, message: str, modal: QWidget | None) -> None:
        self.errors.append(message)
        self.stop()
        if isinstance(modal, QDialog):
            modal.reject()

    def _poll(self) -> None:
        heartbeat_at = time.monotonic()
        heartbeat_gap = heartbeat_at - self.last_heartbeat_at
        if heartbeat_gap > self.max_heartbeat_gap_seconds:
            self.max_heartbeat_gap_seconds = heartbeat_gap
            self.max_heartbeat_gap_context = f"phase={self.phase}"
        self.last_heartbeat_at = heartbeat_at
        modal = self.modal_getter()
        try:
            if isinstance(modal, EegSourceChooserDialog):
                QTest.mouseClick(modal.choose_folder_button, Qt.MouseButton.LeftButton)
                continue_button = modal.button_box.button(
                    QDialogButtonBox.StandardButton.Ok
                )
                if continue_button is None or not continue_button.isEnabled():
                    self._fail(
                        "Import Data did not retain the selected P300 BIDS root.", modal
                    )
                    return
                self.chooser_accepted_at = time.perf_counter()
                QTest.mouseClick(continue_button, Qt.MouseButton.LeftButton)
                return
            if isinstance(modal, BidsSubjectSelectionDialog):
                selected = modal.get_result()
                if (
                    not selected
                    or modal.continue_button is None
                    or not modal.continue_button.isEnabled()
                ):
                    self._fail("P300 BIDS subject selection cannot continue.", modal)
                    return
                self.trace.append("select BIDS subjects: " + ", ".join(selected))
                QTest.mouseClick(modal.continue_button, Qt.MouseButton.LeftButton)
                return
            if isinstance(modal, QMessageBox):
                yes_button = modal.button(QMessageBox.StandardButton.Yes)
                if (
                    modal.windowTitle() != "Dataset Resource Check"
                    or yes_button is None
                ):
                    self._fail(
                        f"Unexpected message box: {modal.windowTitle()}: {modal.text()}",
                        modal,
                    )
                    return
                self.trace.append("confirm resource check")
                QTest.mouseClick(yes_button, Qt.MouseButton.LeftButton)
                return
            if not isinstance(modal, DataInterpretationPreviewDialog):
                return
            if self.wizard_ready_at is None:
                self.wizard_ready_at = time.perf_counter()
            if self.dialog is None:
                self.dialog = modal
            elif modal is not self.dialog:
                if self.phase != 4 or self.fresh_review_count:
                    self._fail(
                        "P300 wizard unexpectedly opened another review dialog.", modal
                    )
                    return
                self.dialog = modal
                self.fresh_review_count = 1
                self.trace.append("fresh BIDS review")
            if self.phase == 0:
                self.trace.append("Choose EEG Data")
                self.phase = 1
                QTest.mouseClick(modal.next_button, Qt.MouseButton.LeftButton)
                return
            if self.phase == 1:
                self.trace.append("Load Labels")
                self.phase = 2
                QTest.mouseClick(modal.next_button, Qt.MouseButton.LeftButton)
                return
            if self.phase == 2:
                self.trace.append("Review Metadata")
                complete_required_metadata(modal)
                self.phase = 3
                QTest.mouseClick(modal.next_button, Qt.MouseButton.LeftButton)
                return
            if self.phase == 3:
                if modal.rule_label_field_combo.currentData() != "value":
                    self._fail(
                        "OpenNeuro value is not the recommended label field.", modal
                    )
                    return
                self.trace.append("Match Labels")
                self.trace.append("accept recommended label field value")
                QTest.mouseClick(
                    modal.placement_method_buttons["time_field"],
                    Qt.MouseButton.LeftButton,
                )
                select_combo_data(modal.time_field_combo, "onset")
                complete_openneuro_event_values(modal)
                self.trace.append("review OpenNeuro event values")
                self.phase = 4
                QTest.mouseClick(modal.next_button, Qt.MouseButton.LeftButton)
                return
            if self.phase == 4:
                if not modal.apply_button.isEnabled():
                    self._fail(
                        "Reviewed OpenNeuro P300 import did not enable Apply.", modal
                    )
                    return
                self.trace.append("Review and Import")
                self.trace.append("confirm and import")
                capture_teacher_ui(modal, "openneuro-review-and-import.png")
                self.apply_clicked_at = time.perf_counter()
                self.phase = 5
                QTest.mouseClick(modal.apply_button, Qt.MouseButton.LeftButton)
        except Exception as exc:
            self._fail(f"{type(exc).__name__}: {exc}", modal)
