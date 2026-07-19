"""Real Qt gate for the DatasetActionHandler external-label wizard path."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from PyQt6.QtCore import Qt, QThreadPool, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from pytestqt.exceptions import TimeoutError as QtBotTimeoutError

from XBrainLab.backend.study import Study
from XBrainLab.ui.application_capabilities import application_ui_runtime
from XBrainLab.ui.async_command_runner import application_command_registry
from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (
    DataInterpretationPreviewDialog,
)
from XBrainLab.ui.panels.dataset.panel import DatasetPanel

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "data"
GDF_PATH = FIXTURE_ROOT / "A01T.gdf"
LABEL_PATH = FIXTURE_ROOT / "label" / "A01T.mat"
EXPECTED_CLASS_MAP = {
    "1": "left hand",
    "2": "right hand",
    "3": "feet",
    "4": "tongue",
}
EXPECTED_TARGET_EVENT_CODES = {"769", "770", "771", "772"}


@pytest.fixture(autouse=True)
def mock_ui_blocking() -> None:
    """Use the real wizard modal loop instead of the suite-wide dialog patch."""
    yield


class _RefreshProbe:
    def update_panel(self) -> None:
        pass

    def mark_refresh_dirty(self) -> None:
        pass


class _DatasetHost(QWidget):
    """Small real-Study host satisfying the shared UI refresh contract."""

    def __init__(self, study: Study) -> None:
        super().__init__()
        self.study = study
        self.stack = QStackedWidget(self)
        self.preprocess_panel = _RefreshProbe()
        self.training_panel = _RefreshProbe()
        self.evaluation_panel = _RefreshProbe()
        self.visualization_panel = _RefreshProbe()
        self.info_refresh_count = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack)

    def update_info_panel(self) -> None:
        self.info_refresh_count += 1


@dataclass
class _WizardDriver:
    timer: QTimer
    phase: int = 0
    dialogs: list[DataInterpretationPreviewDialog] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class _LabelSourceLifecycleDriver:
    timer: QTimer
    phase: int = 0
    dialogs: list[DataInterpretationPreviewDialog] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _select_combo_data(combo: QComboBox, value: str) -> None:
    index = combo.findData(value)
    if index < 0:
        raise AssertionError(f"{combo.objectName()} does not offer {value!r}.")
    combo.setFocus()
    QTest.mouseClick(combo, Qt.MouseButton.LeftButton)
    QTest.keyClick(combo, Qt.Key.Key_Home)
    for _ in range(index):
        QTest.keyClick(combo, Qt.Key.Key_Down)
    QTest.keyClick(combo, Qt.Key.Key_Return)
    if combo.currentData() != value:
        raise AssertionError(
            f"{combo.objectName()} selected {combo.currentData()!r}, expected {value!r}."
        )


def _complete_visible_external_label_controls(
    dialog: DataInterpretationPreviewDialog,
) -> None:
    dialog.scroll_area.ensureWidgetVisible(dialog.label_source_mode_combo)
    _select_combo_data(
        dialog.label_source_mode_combo,
        "loaded_label_files",
    )

    target_checks = {
        str(check.property("event_code")): check
        for check in dialog.findChildren(QCheckBox)
        if check.objectName() == "DataImportTargetEventCheckbox"
    }
    if not set(target_checks).issuperset(EXPECTED_TARGET_EVENT_CODES):
        raise AssertionError(
            "Match Labels did not expose all checked-in GDF class event controls."
        )
    for event_code, check in target_checks.items():
        expected = event_code in EXPECTED_TARGET_EVENT_CODES
        if check.isChecked() != expected:
            dialog.scroll_area.ensureWidgetVisible(check)
            QTest.mouseClick(check, Qt.MouseButton.LeftButton)

    editor = dialog.event_value_editor
    if editor is None or not editor.isVisibleTo(dialog):
        raise AssertionError(
            "Match Labels did not expose event-value decisions: "
            f"source={dialog.label_source_mode_combo.currentData()!r}, "
            f"field={dialog.rule_label_field_combo.currentData()!r}, "
            f"fallback={dialog._label_table_fallback_reason()!r}, "
            f"plans={dialog._event_value_carrier_plans()!r}, "
            f"scan_sources={dialog.scan_result.get('label_sources')!r}, "
            f"scan_carriers={dialog.scan_result.get('label_carriers')!r}, "
            "preview_carriers="
            f"{dialog.preview.get('label_carrier_preview')!r}."
        )
    values = [
        label.text()
        for label in editor.findChildren(QLabel)
        if label.objectName() == "DataImportValueDecisionValue"
    ]
    role_selectors = editor.findChildren(QComboBox, "EventValueRoleSelector")
    use_selectors = editor.findChildren(QComboBox, "EventValueUseSelector")
    class_editors = editor.findChildren(QLineEdit, "EventValueClassNameEditor")
    if values != list(EXPECTED_CLASS_MAP):
        raise AssertionError(f"Unexpected external label values: {values!r}.")
    if not (
        len(role_selectors) == len(use_selectors) == len(class_editors) == len(values)
    ):
        raise AssertionError("Event-value controls do not match the visible values.")

    for raw_value, role_selector, use_selector, class_editor in zip(
        values,
        role_selectors,
        use_selectors,
        class_editors,
        strict=True,
    ):
        dialog.scroll_area.ensureWidgetVisible(role_selector)
        _select_combo_data(role_selector, "stimulus")
        _select_combo_data(use_selector, "class")
        QTest.mouseClick(class_editor, Qt.MouseButton.LeftButton)
        QTest.keyClick(
            class_editor,
            Qt.Key.Key_A,
            Qt.KeyboardModifier.ControlModifier,
        )
        QTest.keyClicks(class_editor, EXPECTED_CLASS_MAP[raw_value])

    if not editor.is_complete():
        raise AssertionError("Visible event-value decisions remain incomplete.")


def _start_wizard_driver() -> _WizardDriver:
    driver = _WizardDriver(timer=QTimer())
    driver.timer.setInterval(5)

    def _fail(message: str, modal: QWidget | None) -> None:
        driver.errors.append(message)
        driver.timer.stop()
        if isinstance(modal, QDialog):
            modal.reject()

    def _poll() -> None:
        modal = QApplication.activeModalWidget()
        try:
            if isinstance(modal, QMessageBox):
                if modal.windowTitle() != "Dataset Resource Check":
                    _fail(
                        f"Unexpected message box: {modal.windowTitle()}: {modal.text()}",
                        modal,
                    )
                    return
                yes_button = modal.button(QMessageBox.StandardButton.Yes)
                if yes_button is None:
                    _fail("Resource check did not expose a Yes button.", modal)
                    return
                driver.trace.append("confirm resource check")
                yes_button.click()
                return

            if not isinstance(modal, DataInterpretationPreviewDialog):
                return
            if modal not in driver.dialogs:
                driver.dialogs.append(modal)

            if driver.phase == 0:
                if modal.step_stack.currentIndex() != 0:
                    return
                driver.trace.append(modal.next_button.text())
                driver.phase = 1
                QTest.mouseClick(modal.next_button, Qt.MouseButton.LeftButton)
                return

            if driver.phase == 1 and modal is driver.dialogs[0]:
                if modal.step_stack.currentIndex() != 1:
                    return
                if not modal.add_label_file_btn.isVisibleTo(modal):
                    _fail("Load label file is not visible.", modal)
                    return
                driver.trace.append("Load label file")
                QTest.mouseClick(
                    modal.add_label_file_btn,
                    Qt.MouseButton.LeftButton,
                )
                driver.trace.append(modal.next_button.text())
                driver.phase = 2
                QTest.mouseClick(modal.next_button, Qt.MouseButton.LeftButton)
                return

            if (
                driver.phase == 2
                and len(driver.dialogs) == 2
                and modal is driver.dialogs[1]
            ):
                if modal.step_stack.currentIndex() != 2:
                    return
                metadata_item = modal.file_tree.topLevelItem(0)
                if metadata_item is None:
                    _fail(
                        "Review Metadata did not expose the selected EEG file.", modal
                    )
                    return
                metadata_item.setText(1, "A01")
                metadata_item.setText(3, "motor-imagery")
                if modal._metadata_required_missing_fields(
                    modal._metadata_completion_counts()[1]
                ):
                    _fail("Required metadata remains incomplete.", modal)
                    return
                driver.trace.append("complete Review Metadata controls")
                driver.trace.append(modal.next_button.text())
                driver.phase = 3
                QTest.mouseClick(modal.next_button, Qt.MouseButton.LeftButton)
                return

            if driver.phase == 3 and modal is driver.dialogs[1]:
                if modal.step_stack.currentIndex() != 3:
                    return
                _complete_visible_external_label_controls(modal)
                driver.trace.append("complete Match Labels controls")
                driver.trace.append(modal.next_button.text())
                driver.phase = 4
                QTest.mouseClick(modal.next_button, Qt.MouseButton.LeftButton)
                return

            if driver.phase == 4 and modal is driver.dialogs[1]:
                if modal.step_stack.currentIndex() != 4:
                    return
                if not modal.apply_button.isVisibleTo(modal):
                    _fail("Confirm and Import is not visible.", modal)
                    return
                if not modal.apply_button.isEnabled():
                    _fail(
                        "Confirm and Import is disabled after visible review: "
                        f"facts={modal._submission_facts()!r}, "
                        "metadata="
                        f"{modal._metadata_completion_counts()!r}, "
                        "placement="
                        f"{modal._review_label_placement_text()!r}, "
                        "pairing="
                        f"{modal._loaded_label_pairing_result()!r}.",
                        modal,
                    )
                    return
                if not modal.save_recipe_check.isChecked():
                    _fail("Save recipe is not selected on the completed review.", modal)
                    return
                driver.trace.append(modal.apply_button.text())
                driver.phase = 5
                QTest.mouseClick(modal.apply_button, Qt.MouseButton.LeftButton)
        except Exception as exc:
            _fail(f"{type(exc).__name__}: {exc}", modal)

    driver.timer.timeout.connect(_poll)
    driver.timer.start()
    return driver


def _wait_for_interpretation_publication(
    qtbot: Any,
    driver: _WizardDriver,
    runtime: Any,
    *,
    timeout: int,
) -> None:
    """Wait for publication and preserve UI state when a walkthrough stalls."""
    try:
        qtbot.waitUntil(
            lambda: bool(driver.errors)
            or runtime.get_view_publication().state.interpretation.has_applied_interpretation,
            timeout=timeout,
        )
    except QtBotTimeoutError:
        modal = QApplication.activeModalWidget()
        modal_name = type(modal).__name__ if modal is not None else "None"
        step_index = (
            modal.step_stack.currentIndex()
            if isinstance(modal, DataInterpretationPreviewDialog)
            else None
        )
        thread_pool = QThreadPool.globalInstance()
        pytest.fail(
            "Data Import walkthrough stalled before publication: "
            f"driver_phase={driver.phase}, dialogs={len(driver.dialogs)}, "
            f"trace={driver.trace!r}, errors={driver.errors!r}, "
            f"active_modal={modal_name}, step_index={step_index}, "
            f"active_commands={application_command_registry().active_count()}, "
            f"active_threads={thread_pool.activeThreadCount()}, "
            f"max_threads={thread_pool.maxThreadCount()}."
        )


def _visible_label_source_titles(
    dialog: DataInterpretationPreviewDialog,
) -> list[str]:
    return [
        label.text()
        for label in dialog.findChildren(QLabel, "DataImportSourceTitle")
        if label.isVisibleTo(dialog)
    ]


def _visible_button(
    dialog: DataInterpretationPreviewDialog,
    text: str,
) -> QPushButton:
    matches = [
        button
        for button in dialog.findChildren(QPushButton)
        if button.text() == text and button.isVisibleTo(dialog)
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"Expected one visible {text!r} button, found {len(matches)}."
        )
    return matches[0]


def _complete_metadata(dialog: DataInterpretationPreviewDialog) -> None:
    metadata_item = dialog.file_tree.topLevelItem(0)
    if metadata_item is None:
        raise AssertionError("Review Metadata did not expose the selected EEG file.")
    metadata_item.setText(1, "A01")
    metadata_item.setText(3, "motor-imagery")
    if dialog._metadata_required_missing_fields(
        dialog._metadata_completion_counts()[1]
    ):
        raise AssertionError("Required metadata remains incomplete.")


def _start_label_source_lifecycle_driver(
    expected_label_path: Path,
) -> _LabelSourceLifecycleDriver:
    """Drive add/remove/re-add through the outer asynchronous rescan loop."""
    driver = _LabelSourceLifecycleDriver(timer=QTimer())
    driver.timer.setInterval(5)
    expected_path = str(expected_label_path)

    def _fail(message: str, modal: QWidget | None) -> None:
        driver.errors.append(message)
        driver.timer.stop()
        if isinstance(modal, QDialog):
            modal.reject()

    def _poll() -> None:
        modal = QApplication.activeModalWidget()
        try:
            if isinstance(modal, QMessageBox):
                if modal.windowTitle() != "Dataset Resource Check":
                    _fail(
                        f"Unexpected message box: {modal.windowTitle()}: {modal.text()}",
                        modal,
                    )
                    return
                yes_button = modal.button(QMessageBox.StandardButton.Yes)
                if yes_button is None:
                    _fail("Resource check did not expose a Yes button.", modal)
                    return
                driver.trace.append("confirm resource check")
                yes_button.click()
                return

            if not isinstance(modal, DataInterpretationPreviewDialog):
                return
            if modal not in driver.dialogs:
                driver.dialogs.append(modal)

            if driver.phase == 0:
                if modal.step_stack.currentIndex() != 0:
                    return
                driver.trace.append("open Load Labels")
                driver.phase = 1
                QTest.mouseClick(modal.next_button, Qt.MouseButton.LeftButton)
                return

            if driver.phase == 1 and modal is driver.dialogs[0]:
                if modal.step_stack.currentIndex() != 1:
                    return
                driver.trace.append("add label")
                QTest.mouseClick(
                    modal.add_label_file_btn,
                    Qt.MouseButton.LeftButton,
                )
                driver.phase = 2
                QTest.mouseClick(modal.next_button, Qt.MouseButton.LeftButton)
                return

            if (
                driver.phase == 2
                and len(driver.dialogs) == 2
                and modal is driver.dialogs[1]
            ):
                if modal.step_stack.currentIndex() != 2:
                    return
                driver.trace.append("return to Load Labels")
                driver.phase = 21
                QTest.mouseClick(modal.back_button, Qt.MouseButton.LeftButton)
                return

            if driver.phase == 21 and modal is driver.dialogs[1]:
                if modal.step_stack.currentIndex() != 1:
                    return
                if _visible_label_source_titles(modal) != [expected_label_path.name]:
                    _fail(
                        "First rescan did not expose exactly one loaded label file.",
                        modal,
                    )
                    return
                if modal.scan_result.get("label_carriers") != [expected_path]:
                    _fail(
                        "First rescan did not preserve one canonical label carrier.",
                        modal,
                    )
                    return
                driver.trace.append("remove label")
                driver.phase = 22
                QTest.mouseClick(
                    _visible_button(modal, "Remove file"),
                    Qt.MouseButton.LeftButton,
                )
                return

            if driver.phase == 22 and modal is driver.dialogs[1]:
                if expected_label_path.name in _visible_label_source_titles(modal):
                    return
                driver.phase = 3
                QTest.mouseClick(modal.next_button, Qt.MouseButton.LeftButton)
                return

            if (
                driver.phase == 3
                and len(driver.dialogs) == 3
                and modal is driver.dialogs[2]
            ):
                if modal.step_stack.currentIndex() != 2:
                    return
                driver.trace.append("return to empty Load Labels")
                driver.phase = 31
                QTest.mouseClick(modal.back_button, Qt.MouseButton.LeftButton)
                return

            if driver.phase == 31 and modal is driver.dialogs[2]:
                if modal.step_stack.currentIndex() != 1:
                    return
                if _visible_label_source_titles(modal):
                    _fail("Removed label file survived the outer rescan.", modal)
                    return
                driver.trace.append("re-add label")
                QTest.mouseClick(
                    modal.add_label_file_btn,
                    Qt.MouseButton.LeftButton,
                )
                driver.phase = 32
                return

            if driver.phase == 32 and modal is driver.dialogs[2]:
                if _visible_label_source_titles(modal) != [expected_label_path.name]:
                    return
                driver.phase = 4
                QTest.mouseClick(modal.next_button, Qt.MouseButton.LeftButton)
                return

            if (
                driver.phase == 4
                and len(driver.dialogs) == 4
                and modal is driver.dialogs[3]
            ):
                if modal.step_stack.currentIndex() != 2:
                    return
                driver.trace.append("verify re-added label")
                driver.phase = 41
                QTest.mouseClick(modal.back_button, Qt.MouseButton.LeftButton)
                return

            if driver.phase == 41 and modal is driver.dialogs[3]:
                if modal.step_stack.currentIndex() != 1:
                    return
                if _visible_label_source_titles(modal) != [expected_label_path.name]:
                    _fail(
                        "Re-added label file was duplicated or missing after rescan.",
                        modal,
                    )
                    return
                if modal.scan_result.get("label_sources") != [expected_path]:
                    _fail("Re-added label source identity is not canonical.", modal)
                    return
                if modal.scan_result.get("label_carriers") != [expected_path]:
                    _fail("Re-added label carrier identity is not canonical.", modal)
                    return
                driver.phase = 42
                QTest.mouseClick(modal.next_button, Qt.MouseButton.LeftButton)
                return

            if driver.phase == 42 and modal is driver.dialogs[3]:
                if modal.step_stack.currentIndex() != 2:
                    return
                _complete_metadata(modal)
                driver.phase = 43
                QTest.mouseClick(modal.next_button, Qt.MouseButton.LeftButton)
                return

            if driver.phase == 43 and modal is driver.dialogs[3]:
                if modal.step_stack.currentIndex() != 3:
                    return
                _complete_visible_external_label_controls(modal)
                driver.phase = 44
                QTest.mouseClick(modal.next_button, Qt.MouseButton.LeftButton)
                return

            if driver.phase == 44 and modal is driver.dialogs[3]:
                if modal.step_stack.currentIndex() != 4:
                    return
                if not modal.apply_button.isEnabled():
                    _fail("Completed review did not enable Confirm and Import.", modal)
                    return
                driver.trace.append("confirm import")
                driver.phase = 5
                QTest.mouseClick(modal.apply_button, Qt.MouseButton.LeftButton)
        except Exception as exc:
            _fail(f"{type(exc).__name__}: {exc}", modal)

    driver.timer.timeout.connect(_poll)
    driver.timer.start()
    return driver


def test_dataset_action_handler_imports_real_gdf_with_external_mat_labels(
    qtbot: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The visible Dataset action must publish one reviewed label import."""
    if not GDF_PATH.exists() or not LABEL_PATH.exists():
        pytest.skip("Checked-in A01T GDF/MAT fixtures are unavailable.")

    eeg_dir = tmp_path / "selected-eeg"
    label_dir = tmp_path / "external-labels"
    eeg_dir.mkdir()
    label_dir.mkdir()
    selected_gdf = eeg_dir / GDF_PATH.name
    external_label = label_dir / LABEL_PATH.name
    recipe_path = tmp_path / "import-recipe.json"
    shutil.copyfile(GDF_PATH, selected_gdf)
    shutil.copyfile(LABEL_PATH, external_label)

    chooser_calls: list[str] = []

    def _choose_files(
        _parent: QWidget,
        title: str,
        _directory: str,
        _filter_text: str,
    ) -> tuple[list[str], str]:
        chooser_calls.append(title)
        if title == "Choose EEG Source for Interpretation":
            return [str(selected_gdf)], ""
        if title == "Load label file":
            return [str(external_label)], ""
        raise AssertionError(f"Unexpected file chooser: {title}")

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileNames",
        staticmethod(_choose_files),
    )
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *_args, **_kwargs: (str(recipe_path), "JSON (*.json)")),
    )

    host = _DatasetHost(Study())
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
    driver = _start_wizard_driver()

    assert panel.sidebar.import_btn.isVisibleTo(panel)
    assert panel.sidebar.import_btn.isEnabled()
    QTest.mouseClick(panel.sidebar.import_btn, Qt.MouseButton.LeftButton)

    _wait_for_interpretation_publication(
        qtbot,
        driver,
        runtime,
        timeout=60_000,
    )
    assert driver.errors == []
    qtbot.waitUntil(
        lambda: application_command_registry().active_count(panel) == 0,
        timeout=10_000,
    )
    automatic_row_count = panel.table.rowCount()
    panel.update_panel()
    manual_row_count = panel.table.rowCount()
    driver.timer.stop()

    assert automatic_row_count == 1, (
        "The completed import did not refresh the Dataset table automatically; "
        f"manual refresh produced {manual_row_count} row(s), "
        f"driver phase={driver.phase}, errors={driver.errors!r}."
    )
    assert driver.phase == 5
    assert len(driver.dialogs) == 2
    assert chooser_calls == [
        "Choose EEG Source for Interpretation",
        "Load label file",
    ]
    assert driver.trace == [
        "Next: Load Labels",
        "Load label file",
        "Next: Review Metadata",
        "complete Review Metadata controls",
        "Next: Match Labels",
        "complete Match Labels controls",
        "Next: Review and Import",
        "Confirm and Import",
    ]

    assert panel.data_surface.currentWidget() is panel.table
    assert panel.table.item(0, 0).text() == selected_gdf.name
    assert panel.table.item(0, 6).text() == "Labels (288)"
    raw = panel.table.item(0, 0).data(Qt.ItemDataRole.UserRole)
    events, label_map = raw.get_event_list()
    assert set(events[:, 2]) == {1, 2, 3, 4}
    assert label_map == {
        class_name: int(raw_value)
        for raw_value, class_name in EXPECTED_CLASS_MAP.items()
    }
    assert raw.is_labels_imported() is True

    publication = runtime.get_view_publication()
    interpretation = publication.state.interpretation
    assert publication.usable is True
    assert publication.state.raw.files == [GDF_PATH.name]
    assert publication.state.active_dataset.has_raw_data is True
    assert interpretation.has_applied_interpretation is True
    assert interpretation.has_recipe is True
    assert recipe_path.exists()
    assert interpretation.latest_interpretation_id
    assert interpretation.latest_recipe_id
    assert interpretation.label_sources == [str(external_label)]
    assert interpretation.label_carriers == [str(external_label)]
    assert interpretation.class_map == EXPECTED_CLASS_MAP
    assert interpretation.epoch_handoff["default_epoch_events"] == sorted(
        EXPECTED_CLASS_MAP.values(),
        key=str.casefold,
    )
    [carrier] = interpretation.label_carrier_plan
    assert carrier["path"] == str(external_label)
    assert carrier["selected_label_field"] == "classlabel"
    assert set(carrier["selected_target_event_codes"]) == EXPECTED_TARGET_EVENT_CODES


def test_outer_async_review_remove_then_readd_keeps_one_real_label_source(
    qtbot: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Remove/re-add must survive each real outer rescan without duplication."""
    if not GDF_PATH.exists() or not LABEL_PATH.exists():
        pytest.skip("Checked-in A01T GDF/MAT fixtures are unavailable.")

    eeg_dir = tmp_path / "selected-eeg"
    label_dir = tmp_path / "external-labels"
    eeg_dir.mkdir()
    label_dir.mkdir()
    selected_gdf = eeg_dir / GDF_PATH.name
    external_label = label_dir / LABEL_PATH.name
    recipe_path = tmp_path / "remove-readd-recipe.json"
    shutil.copyfile(GDF_PATH, selected_gdf)
    shutil.copyfile(LABEL_PATH, external_label)

    chooser_calls: list[str] = []

    def _choose_files(
        _parent: QWidget,
        title: str,
        _directory: str,
        _filter_text: str,
    ) -> tuple[list[str], str]:
        chooser_calls.append(title)
        if title == "Choose EEG Source for Interpretation":
            return [str(selected_gdf)], ""
        if title == "Load label file":
            return [str(external_label)], ""
        raise AssertionError(f"Unexpected file chooser: {title}")

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileNames",
        staticmethod(_choose_files),
    )
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *_args, **_kwargs: (str(recipe_path), "JSON (*.json)")),
    )

    host = _DatasetHost(Study())
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
    driver = _start_label_source_lifecycle_driver(external_label)

    QTest.mouseClick(panel.sidebar.import_btn, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(
        lambda: bool(driver.errors)
        or any(
            record.getMessage() == "Async command result callback failed"
            for record in caplog.records
        )
        or runtime.get_view_publication().state.interpretation.has_applied_interpretation,
        timeout=45_000,
    )
    driver.timer.stop()
    callback_failures = [
        record
        for record in caplog.records
        if record.getMessage() == "Async command result callback failed"
    ]
    assert callback_failures == [], (
        "The outer label-source rescan callback crashed before completing; "
        f"phase={driver.phase}, dialogs={len(driver.dialogs)}, "
        f"trace={driver.trace!r}."
    )
    assert driver.errors == []
    qtbot.waitUntil(
        lambda: application_command_registry().active_count(panel) == 0,
        timeout=10_000,
    )

    assert driver.phase == 5
    assert len(driver.dialogs) == 4
    assert chooser_calls == [
        "Choose EEG Source for Interpretation",
        "Load label file",
        "Load label file",
    ]
    assert driver.trace == [
        "open Load Labels",
        "add label",
        "return to Load Labels",
        "remove label",
        "return to empty Load Labels",
        "re-add label",
        "verify re-added label",
        "confirm import",
    ]

    publication = runtime.get_view_publication()
    interpretation = publication.state.interpretation
    assert publication.state.raw.files == [selected_gdf.name]
    assert interpretation.has_applied_interpretation is True
    assert interpretation.label_sources == [str(external_label)]
    assert interpretation.label_carriers == [str(external_label)]
    assert len(interpretation.label_carrier_plan) == 1
    assert interpretation.label_carrier_plan[0]["path"] == str(external_label)
    assert panel.table.rowCount() == 1
    assert panel.table.item(0, 6).text() == "Labels (288)"
