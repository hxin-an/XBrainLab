"""Bounded real-fixture acceptance for the user-facing Data Import wizard."""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Any

import pytest
from PyQt6.QtCore import QPoint, QRect, Qt, QThreadPool, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QLabel,
    QLineEdit,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from pytestqt.exceptions import TimeoutError as QtBotTimeoutError

from scripts.dev.fetch_public_eeg_fixtures import (
    FIXTURE_GROUPS,
    fixture_file_is_valid,
    resolve_public_fixture_dir,
)
from tests.integration.ui.modal_helpers import visible_modal_dialog
from XBrainLab.backend.application import (
    data_interpretation_scan,
    get_application_service,
)
from XBrainLab.backend.application.owned_work import OwnedWorkPhase
from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.study import Study
from XBrainLab.ui.application_capabilities import application_ui_runtime
from XBrainLab.ui.async_command_runner import application_command_registry
from XBrainLab.ui.dialogs.dataset.bids_subject_selection_dialog import (
    BidsSubjectSelectionDialog,
)
from XBrainLab.ui.dialogs.dataset.data_interpretation_loading_dialog import (
    DataInterpretationLoadingDialog,
)
from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (
    DataInterpretationPreviewDialog,
)
from XBrainLab.ui.dialogs.dataset.eeg_source_chooser_dialog import (
    EegSourceChooserDialog,
)
from XBrainLab.ui.panels.dataset.panel import DatasetPanel

TEST_DATA_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "data"
PUBLIC_ROOT = resolve_public_fixture_dir()
PHYSIONET_REST_EDF = PUBLIC_ROOT / "physionet-eegmmidb-S008R01.edf"
PHYSIONET_MOTOR_EDF = PUBLIC_ROOT / "physionet-eegmmidb-S008R04.edf"
BBCI_GDF = PUBLIC_ROOT / "bbci-competition-iii-O3VR.gdf"
SCCN_EEGLAB_SET = PUBLIC_ROOT / "sccn-eeglab_data.set"
MNE_CNT = PUBLIC_ROOT / "scan41_short.cnt"
MNE_BRAINVISION = PUBLIC_ROOT / "test_NO.vhdr"
CHBMIT_ROOT = PUBLIC_ROOT / "chbmit-chb01"
CHBMIT_EDF = CHBMIT_ROOT / "chb01_03.edf"
SLEEP_EDFX_ROOT = PUBLIC_ROOT / "sleep-edfx-st7011"
SLEEP_EDFX_PSG = SLEEP_EDFX_ROOT / "ST7011J0-PSG.edf"
OPENNEURO_P300_ROOT = PUBLIC_ROOT / "openneuro-ds003061-p300"
PUBLIC_BIDS_ROOT = PUBLIC_ROOT / "mne-bids-tiny-eeg"
PUBLIC_BIDS_EEG = (
    PUBLIC_BIDS_ROOT
    / "sub-01"
    / "ses-eeg"
    / "eeg"
    / "sub-01_ses-eeg_task-rest_eeg.vhdr"
)
PUBLIC_BIDS_EVENTS = PUBLIC_BIDS_EEG.with_name("sub-01_ses-eeg_task-rest_events.tsv")
STEP_TITLES = (
    "Choose EEG Data",
    "Load Labels",
    "Review Metadata",
    "Match Labels",
    "Review and Import",
)
QTEST: Any = QTest
REQUIRE_REAL_FIXTURES = (
    os.environ.get("XBRAINLAB_REQUIRE_REAL_FIXTURES", "").strip() == "1"
)

pytestmark = [
    pytest.mark.optional_public_fixture,
    pytest.mark.usefixtures("allow_real_modals"),
]


@dataclass(frozen=True)
class _PublicFileAcceptanceCase:
    fixture_group: str
    source: Path
    expected_event_total: int
    expected_unique_events: tuple[str, ...]
    expected_table_summary: str


@dataclass(frozen=True)
class _PublicFolderAcceptanceCase:
    fixture_group: str
    source: Path
    expected_eeg: Path


PUBLIC_FILE_ACCEPTANCE_CASES = (
    _PublicFileAcceptanceCase(
        "physionet-edf-rest",
        PHYSIONET_REST_EDF,
        1,
        ("T0",),
        "Events (1)",
    ),
    _PublicFileAcceptanceCase(
        "physionet-edf-motor",
        PHYSIONET_MOTOR_EDF,
        30,
        ("T0", "T1", "T2"),
        "Events (30)",
    ),
    _PublicFileAcceptanceCase(
        "bbci-gdf",
        BBCI_GDF,
        2_560,
        ("768", "769", "770", "781", "783", "785"),
        "Events (2560)",
    ),
    _PublicFileAcceptanceCase(
        "sccn-eeglab",
        SCCN_EEGLAB_SET,
        154,
        ("rt", "square"),
        "Events (154)",
    ),
    _PublicFileAcceptanceCase(
        "mne-testing-cnt",
        MNE_CNT,
        6,
        ("0", "109", "7"),
        "Events (6)",
    ),
    _PublicFileAcceptanceCase(
        "mne-testing-brainvision",
        MNE_BRAINVISION,
        0,
        (),
        "No events",
    ),
)

PUBLIC_FOLDER_ACCEPTANCE_CASES = (
    _PublicFolderAcceptanceCase(
        "chbmit-chb01",
        CHBMIT_ROOT,
        CHBMIT_EDF,
    ),
    _PublicFolderAcceptanceCase(
        "sleep-edfx-st7011",
        SLEEP_EDFX_ROOT,
        SLEEP_EDFX_PSG,
    ),
)


class _RefreshProbe:
    def update_panel(self) -> None:
        pass

    def mark_refresh_dirty(self) -> None:
        pass


class _DatasetHost(QWidget):
    """Minimal real-Study host for the Dataset panel refresh contract."""

    def __init__(self, study: Study) -> None:
        super().__init__()
        self.study = study
        self.stack = QStackedWidget(self)
        self.dataset_panel: DatasetPanel | None = None
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
    source_picker: str = "files"
    skip_labels: bool = False
    resolve_bids_values: bool = False
    resolve_openneuro_values: bool = False
    resolve_openneuro_trial_types: bool = False
    expect_blocked: bool = False
    awaiting_label_field_refresh: bool = False
    dialog_count: int = 0
    phase: int = 0
    dialog: DataInterpretationPreviewDialog | None = None
    trace: list[str] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    heartbeat_count: int = 0
    last_heartbeat_at: float = field(default_factory=time.monotonic)
    max_heartbeat_gap_seconds: float = 0.0
    openneuro_values_started: bool = False
    openneuro_setup_stage: int = 0
    openneuro_value_index: int = 0
    openneuro_value_stage: int = 0
    last_surface_key: tuple[int, int] | None = None
    last_heartbeat_context: str = "driver startup"
    max_heartbeat_gap_context: str = ""
    last_progress_at: float = field(default_factory=time.monotonic)
    last_progress_key: tuple[object, ...] | None = None


def _require_manifest_group(group_name: str) -> None:
    group = next(
        (item for item in FIXTURE_GROUPS if item["name"] == group_name),
        None,
    )
    assert group is not None, f"Public fixture manifest group is missing: {group_name}"
    missing = [
        item["filename"]
        for item in group["files"]
        if not (PUBLIC_ROOT / item["filename"]).exists()
    ]
    if missing:
        present = [
            item["filename"]
            for item in group["files"]
            if (PUBLIC_ROOT / item["filename"]).exists()
        ]
        if present:
            pytest.fail(
                f"Public fixture group {group_name} is partially installed. "
                f"Present: {present}; missing: {missing}."
            )
        message = (
            f"Public fixture group {group_name} is not downloaded: {', '.join(missing)}"
        )
        if REQUIRE_REAL_FIXTURES:
            pytest.fail(message)
        pytest.skip(message)
    invalid = [
        item["filename"]
        for item in group["files"]
        if not fixture_file_is_valid(
            PUBLIC_ROOT / item["filename"],
            item["sha256"],
            item["size_bytes"],
        )
    ]
    assert invalid == [], (
        f"Public fixture group {group_name} failed size/hash validation: {invalid}"
    )


def _build_dataset_panel(qtbot: Any) -> tuple[_DatasetHost, DatasetPanel, Any]:
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
    return host, panel, runtime


def _select_combo_data(combo: QComboBox, value: str) -> None:
    index = combo.findData(value)
    if index < 0:
        raise AssertionError(f"{combo.objectName()} does not offer {value!r}.")
    combo.setFocus()
    QTEST.mouseClick(combo, Qt.MouseButton.LeftButton)
    QTEST.keyClick(combo, Qt.Key.Key_Home)
    for _ in range(index):
        QTEST.keyClick(combo, Qt.Key.Key_Down)
    QTEST.keyClick(combo, Qt.Key.Key_Return)
    combo.hidePopup()
    QApplication.processEvents()
    if combo.currentData() != value:
        raise AssertionError(
            f"{combo.objectName()} selected {combo.currentData()!r}, expected {value!r}."
        )


def _replace_line_edit_text(editor: QLineEdit, value: str) -> None:
    QTEST.mouseClick(editor, Qt.MouseButton.LeftButton)
    QTEST.keyClick(
        editor,
        Qt.Key.Key_A,
        Qt.KeyboardModifier.ControlModifier,
    )
    QTEST.keyClicks(editor, value)


def _decision_value_text(label: QLabel) -> str:
    """Read the semantic value even when the visible label is safely elided."""
    return str(label.accessibleName() or label.text())


def _capture_teacher_ui(
    dialog: DataInterpretationPreviewDialog,
    filename: str,
    *,
    widget: QWidget | None = None,
) -> None:
    raw_output_dir = os.environ.get("XBRAINLAB_TEACHER_UI_ARTIFACT_DIR", "").strip()
    if not raw_output_dir:
        return
    output_dir = Path(raw_output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    QApplication.processEvents()
    target = widget or dialog
    if widget is None:
        pixmap = target.grab()
    else:
        target_rect = QRect(target.mapTo(dialog, QPoint(0, 0)), target.size())
        if not dialog.rect().contains(target_rect):
            raise AssertionError(
                f"UI artifact target is not fully visible in the dialog: {filename}"
            )
        pixmap = dialog.grab(target_rect)
    output_path = output_dir / filename
    if pixmap.isNull() or not pixmap.save(str(output_path), "PNG"):
        raise AssertionError(f"Failed to capture current UI artifact: {output_path}")


def _complete_bids_event_values(dialog: DataInterpretationPreviewDialog) -> None:
    if dialog.label_source_mode_combo.currentData() != "loaded_label_files":
        _select_combo_data(dialog.label_source_mode_combo, "loaded_label_files")

    editor = dialog.event_value_editor
    if editor is None or not editor.isVisibleTo(dialog):
        raise AssertionError("BIDS Match Labels did not expose event-value decisions.")
    values = [
        _decision_value_text(label)
        for label in editor.findChildren(QLabel)
        if label.objectName() == "DataImportValueDecisionValue"
    ]
    role_selectors = editor.findChildren(QComboBox, "EventValueRoleSelector")
    use_selectors = editor.findChildren(QComboBox, "EventValueUseSelector")
    class_editors = editor.findChildren(QLineEdit, "EventValueClassNameEditor")
    if not (
        values == ["show_stimulus", "start_experiment"]
        and len(role_selectors) == len(use_selectors) == len(class_editors) == 2
    ):
        raise AssertionError(
            "Unexpected BIDS event-value controls: "
            f"values={values!r}, roles={len(role_selectors)}, "
            f"uses={len(use_selectors)}, classes={len(class_editors)}."
        )

    decisions = {
        "show_stimulus": ("stimulus", "class", "show stimulus"),
        "start_experiment": ("system", "ignore", ""),
    }
    for raw_value, role_selector, use_selector, class_editor in zip(
        values,
        role_selectors,
        use_selectors,
        class_editors,
        strict=True,
    ):
        role, use, class_name = decisions[raw_value]
        dialog.scroll_area.ensureWidgetVisible(role_selector)
        _select_combo_data(role_selector, role)
        _select_combo_data(use_selector, use)
        if class_name:
            _replace_line_edit_text(class_editor, class_name)

    if not editor.is_complete():
        raise AssertionError(
            f"BIDS event-value decisions remain incomplete: {editor.unresolved_values()!r}"
        )


def _complete_openneuro_trial_types(
    dialog: DataInterpretationPreviewDialog,
) -> None:
    """Review the coarse BIDS trial_type field through visible controls."""
    if dialog.rule_label_field_combo.currentData() != "trial_type":
        raise AssertionError("OpenNeuro trial_type is not the selected label field.")
    editor = dialog.event_value_editor
    if editor is None or not editor.isVisibleTo(dialog):
        raise AssertionError("OpenNeuro trial_type decisions are not visible.")
    values = [
        _decision_value_text(label)
        for label in editor.findChildren(QLabel)
        if label.objectName() == "DataImportValueDecisionValue"
    ]
    role_selectors = editor.findChildren(QComboBox, "EventValueRoleSelector")
    use_selectors = editor.findChildren(QComboBox, "EventValueUseSelector")
    class_editors = editor.findChildren(QLineEdit, "EventValueClassNameEditor")
    if not (
        set(values) == {"response", "stimulus"}
        and len(values)
        == len(role_selectors)
        == len(use_selectors)
        == len(class_editors)
        == 2
    ):
        raise AssertionError(
            "Unexpected OpenNeuro trial_type controls: "
            f"values={values!r}, roles={len(role_selectors)}, "
            f"uses={len(use_selectors)}, classes={len(class_editors)}."
        )
    decisions = {
        "response": ("response", "ignore", ""),
        "stimulus": ("stimulus", "class", "stimulus"),
    }
    for raw_value, role_selector, use_selector, class_editor in zip(
        values,
        role_selectors,
        use_selectors,
        class_editors,
        strict=True,
    ):
        role, use, class_name = decisions[raw_value]
        dialog.scroll_area.ensureWidgetVisible(use_selector)
        _select_combo_data(role_selector, role)
        _select_combo_data(use_selector, use)
        if class_name:
            _replace_line_edit_text(class_editor, class_name)
    if not editor.is_complete():
        raise AssertionError(
            "OpenNeuro trial_type decisions remain incomplete: "
            f"{editor.unresolved_values()!r}"
        )


def _advance_openneuro_event_values(
    dialog: DataInterpretationPreviewDialog,
    driver: _WizardDriver,
) -> bool:
    """Perform one human-scale OpenNeuro control action per timer callback."""
    if dialog.label_source_mode_combo.currentData() != "loaded_label_files":
        _select_combo_data(dialog.label_source_mode_combo, "loaded_label_files")
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
    if (
        not driver.openneuro_values_started
        and set(editor.unresolved_values()) != expected
    ):
        raise AssertionError(
            "OpenNeuro value preview did not refresh to the selected `value` "
            f"column: {editor.unresolved_values()!r}"
        )
    driver.openneuro_values_started = True
    values = [
        _decision_value_text(label)
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
            (
                "response",
                "ignore",
                "",
            )
            if raw_value == "response"
            else (
                "system",
                "ignore",
                "",
            )
            if raw_value == "ignore"
            else (
                "stimulus",
                "class",
                raw_value.replace("_with_reponse", ""),
            )
        )
        for raw_value in expected
    }
    rows = list(
        zip(
            values,
            role_selectors,
            use_selectors,
            class_editors,
            strict=True,
        )
    )
    if driver.openneuro_value_index >= len(rows):
        if not editor.is_complete():
            raise AssertionError(
                "OpenNeuro event-value decisions remain incomplete: "
                f"{editor.unresolved_values()!r}"
            )
        scroll_content = dialog.scroll_area.widget()
        if scroll_content is None:
            raise AssertionError("Match Labels scroll content is unavailable.")
        editor_top = editor.mapTo(scroll_content, QPoint(0, 0)).y()
        vertical_scrollbar = dialog.scroll_area.verticalScrollBar()
        if vertical_scrollbar is None:
            raise AssertionError("Match Labels vertical scrollbar is unavailable.")
        vertical_scrollbar.setValue(max(editor_top - 96, 0))
        QApplication.processEvents()
        _capture_teacher_ui(
            dialog,
            "openneuro-match-labels-dialog.png",
        )
        value_table = editor.findChild(QFrame, "DataImportValueDecisionTable")
        if value_table is None:
            raise AssertionError("OpenNeuro event-value table is unavailable.")
        _capture_teacher_ui(
            dialog,
            "openneuro-event-value-controls.png",
            widget=value_table,
        )
        return True

    raw_value, role_selector, use_selector, class_editor = rows[
        driver.openneuro_value_index
    ]
    if raw_value not in decisions:
        raise AssertionError(f"Unexpected OpenNeuro event value: {raw_value}")
    role, use, class_name = decisions[raw_value]
    dialog.scroll_area.ensureWidgetVisible(role_selector)
    QApplication.processEvents()
    if (
        not role_selector.isEnabled()
        or not use_selector.isEnabled()
        or role_selector.size().isEmpty()
        or use_selector.size().isEmpty()
    ):
        raise AssertionError(f"OpenNeuro controls are not operable for {raw_value!r}.")

    if driver.openneuro_value_stage == 0:
        _select_combo_data(role_selector, role)
        driver.openneuro_value_stage = 1
        return False
    if driver.openneuro_value_stage == 1:
        _select_combo_data(use_selector, use)
        driver.openneuro_value_stage = 2
        return False
    if class_name:
        if class_editor.isReadOnly() or class_editor.size().isEmpty():
            raise AssertionError(
                f"Class-name editor is not operable for {raw_value!r}."
            )
        _replace_line_edit_text(class_editor, class_name)
        if class_editor.text() != class_name:
            raise AssertionError(
                f"Class name did not retain the typed value for {raw_value!r}."
            )
    driver.openneuro_value_index += 1
    driver.openneuro_value_stage = 0
    return False


def _complete_required_metadata(dialog: DataInterpretationPreviewDialog) -> None:
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


def _visible_step_text(dialog: DataInterpretationPreviewDialog) -> str:
    current = dialog.step_stack.currentWidget()
    if current is None:
        return ""
    return "\n".join(
        label.text()
        for label in current.findChildren(QLabel)
        if label.isVisibleTo(current) and label.text().strip()
    )


def _assert_step_surface(
    dialog: DataInterpretationPreviewDialog,
    expected_index: int,
) -> None:
    expected_title = STEP_TITLES[expected_index]
    if dialog.step_stack.currentIndex() != expected_index:
        raise AssertionError(
            f"Expected step {expected_index}, found {dialog.step_stack.currentIndex()}."
        )
    if dialog._step_titles[expected_index] != expected_title:
        raise AssertionError(
            f"Expected step title {expected_title!r}, "
            f"found {dialog._step_titles[expected_index]!r}."
        )
    if not _visible_step_text(dialog).strip():
        raise AssertionError(f"{expected_title} rendered no visible step text.")
    if not dialog.cancel_button.isVisibleTo(dialog):
        raise AssertionError(f"{expected_title} did not expose Cancel.")
    if expected_index == len(STEP_TITLES) - 1:
        if not dialog.apply_button.isVisibleTo(dialog):
            raise AssertionError("Review and Import did not expose Confirm and Import.")
    elif not dialog.next_button.isVisibleTo(dialog):
        raise AssertionError(f"{expected_title} did not expose Next.")


def _start_wizard_driver(
    *,
    source_picker: str = "files",
    skip_labels: bool = False,
    resolve_bids_values: bool = False,
    resolve_openneuro_values: bool = False,
    resolve_openneuro_trial_types: bool = False,
    expect_blocked: bool = False,
) -> _WizardDriver:
    driver = _WizardDriver(
        timer=QTimer(),
        source_picker=source_picker,
        skip_labels=skip_labels,
        resolve_bids_values=resolve_bids_values,
        resolve_openneuro_values=resolve_openneuro_values,
        resolve_openneuro_trial_types=resolve_openneuro_trial_types,
        expect_blocked=expect_blocked,
    )
    # Human-scale actions must leave one event-loop turn for combo popups,
    # geometry refreshes, and asynchronous command delivery to settle.
    driver.timer.setInterval(25)

    def _fail(message: str, modal: QWidget | None) -> None:
        driver.errors.append(message)
        driver.timer.stop()
        if isinstance(modal, QDialog):
            modal.reject()

    def _poll() -> None:
        heartbeat_at = time.monotonic()
        heartbeat_gap = heartbeat_at - driver.last_heartbeat_at
        if heartbeat_gap > driver.max_heartbeat_gap_seconds:
            driver.max_heartbeat_gap_seconds = heartbeat_gap
            driver.max_heartbeat_gap_context = driver.last_heartbeat_context
        driver.last_heartbeat_at = heartbeat_at
        driver.heartbeat_count += 1
        modal = visible_modal_dialog()
        progress_key = (
            driver.phase,
            driver.dialog_count,
            driver.awaiting_label_field_refresh,
            driver.openneuro_setup_stage,
            driver.openneuro_value_index,
            driver.openneuro_value_stage,
            type(modal).__name__ if modal is not None else "None",
        )
        if progress_key != driver.last_progress_key:
            driver.last_progress_key = progress_key
            driver.last_progress_at = heartbeat_at
        # Wizard interactions should advance promptly. Once Confirm and Import has
        # handed a real public dataset to the background Application command, the
        # outer workflow timeout owns the bounded wait because EEGLAB file reads do
        # not expose row-level progress events.
        stall_limit = 240.0 if driver.phase >= len(STEP_TITLES) else 60.0
        if (
            progress_key == driver.last_progress_key
            and heartbeat_at - driver.last_progress_at > stall_limit
        ):
            _fail(
                "Wizard driver made no visible progress for "
                f"{stall_limit:.0f} seconds: "
                f"phase={driver.phase}; dialog_count={driver.dialog_count}; "
                f"awaiting_refresh={driver.awaiting_label_field_refresh}; "
                f"openneuro_setup_stage={driver.openneuro_setup_stage}; "
                f"openneuro_row={driver.openneuro_value_index}; "
                f"openneuro_stage={driver.openneuro_value_stage}; "
                f"modal={type(modal).__name__ if modal is not None else 'None'}; "
                f"trace={driver.trace!r}",
                modal,
            )
            return
        driver.last_heartbeat_context = (
            f"phase={driver.phase}; dialog_count={driver.dialog_count}; "
            f"modal={type(modal).__name__ if modal is not None else 'None'}; "
            f"last_trace={driver.trace[-1] if driver.trace else 'none'}; "
            f"openneuro_row={driver.openneuro_value_index}; "
            f"openneuro_stage={driver.openneuro_value_stage}"
        )
        try:
            if isinstance(modal, EegSourceChooserDialog):
                picker = (
                    modal.choose_folder_button
                    if driver.source_picker == "folder"
                    else modal.choose_files_button
                )
                QTEST.mouseClick(picker, Qt.MouseButton.LeftButton)
                continue_button = modal.button_box.button(
                    QDialogButtonBox.StandardButton.Ok
                )
                if continue_button is None or not continue_button.isEnabled():
                    _fail("Import Data did not retain the selected source.", modal)
                    return
                QTEST.mouseClick(continue_button, Qt.MouseButton.LeftButton)
                return

            if isinstance(modal, BidsSubjectSelectionDialog):
                selected_subjects = modal.get_result()
                if not selected_subjects:
                    _fail("BIDS subject selection has no default subject.", modal)
                    return
                if (
                    modal.continue_button is None
                    or not modal.continue_button.isEnabled()
                ):
                    _fail("BIDS subject selection cannot continue.", modal)
                    return
                driver.trace.append(
                    "select BIDS subjects: " + ", ".join(selected_subjects)
                )
                QTEST.mouseClick(
                    modal.continue_button,
                    Qt.MouseButton.LeftButton,
                )
                return

            if isinstance(modal, QMessageBox):
                if modal.windowTitle() != "Dataset Resource Check":
                    _fail(
                        f"Unexpected message box: {modal.windowTitle()}: {modal.text()}",
                        modal,
                    )
                    return
                yes_button = modal.button(QMessageBox.StandardButton.Yes)
                if yes_button is None:
                    _fail("Dataset Resource Check did not expose Yes.", modal)
                    return
                driver.trace.append("confirm resource check")
                QTEST.mouseClick(yes_button, Qt.MouseButton.LeftButton)
                return

            if not isinstance(modal, DataInterpretationPreviewDialog):
                return
            if driver.dialog is None:
                driver.dialog = modal
                driver.dialog_count = 1
            elif modal is not driver.dialog:
                if (
                    driver.resolve_openneuro_values
                    or driver.resolve_openneuro_trial_types
                ) and driver.awaiting_label_field_refresh:
                    driver.dialog = modal
                    driver.dialog_count += 1
                    driver.awaiting_label_field_refresh = False
                    driver.trace.append("label field preview refreshed")
                else:
                    _fail(
                        "The acceptance flow unexpectedly opened a second wizard.",
                        modal,
                    )
                    return

            if driver.phase >= len(STEP_TITLES):
                return
            _assert_step_surface(modal, driver.phase)
            surface_key = (driver.dialog_count, driver.phase)
            if driver.last_surface_key != surface_key:
                driver.trace.append(STEP_TITLES[driver.phase])
                driver.last_surface_key = surface_key

            if driver.phase == 0:
                driver.phase = 1
                QTEST.mouseClick(modal.next_button, Qt.MouseButton.LeftButton)
                return

            if driver.phase == 1:
                if driver.skip_labels:
                    if not modal.skip_labels_btn.isVisibleTo(modal):
                        _fail(
                            "Load Labels did not expose Continue without labels.", modal
                        )
                        return
                    QTEST.mouseClick(
                        modal.skip_labels_btn,
                        Qt.MouseButton.LeftButton,
                    )
                    if not modal.get_result()["choices"].get("skip_labels"):
                        _fail(
                            "Continue without labels did not update wizard state.",
                            modal,
                        )
                        return
                    driver.trace.append("continue without labels")
                driver.phase = 2
                QTEST.mouseClick(modal.next_button, Qt.MouseButton.LeftButton)
                return

            if driver.phase == 2:
                _complete_required_metadata(modal)
                driver.phase = 3
                QTEST.mouseClick(modal.next_button, Qt.MouseButton.LeftButton)
                return

            if driver.phase == 3:
                if driver.resolve_openneuro_trial_types:
                    if (
                        driver.dialog_count == 1
                        and not driver.awaiting_label_field_refresh
                        and modal.rule_label_field_combo.currentData() != "trial_type"
                    ):
                        _select_combo_data(
                            modal.rule_label_field_combo,
                            "trial_type",
                        )
                        driver.awaiting_label_field_refresh = True
                        driver.trace.append("select label field trial_type")
                        QTEST.mouseClick(
                            modal.next_button,
                            Qt.MouseButton.LeftButton,
                        )
                        return
                    _complete_openneuro_trial_types(modal)
                    driver.trace.append("review OpenNeuro trial_type values")
                if (
                    driver.resolve_openneuro_values
                    and driver.dialog_count == 1
                    and not driver.awaiting_label_field_refresh
                ):
                    if driver.openneuro_setup_stage == 0:
                        if modal.rule_label_field_combo.currentData() != "value":
                            _fail(
                                "OpenNeuro value is not the recommended label field.",
                                modal,
                            )
                            return
                        driver.trace.append("accept recommended label field value")
                        driver.openneuro_setup_stage = 1
                        return
                    if driver.openneuro_setup_stage == 1:
                        placement_button = modal.placement_method_buttons["time_field"]
                        QTEST.mouseClick(
                            placement_button,
                            Qt.MouseButton.LeftButton,
                        )
                        driver.openneuro_setup_stage = 2
                        return
                    if driver.openneuro_setup_stage == 2:
                        _select_combo_data(modal.time_field_combo, "onset")
                        driver.openneuro_setup_stage = 3
                        return
                if driver.resolve_openneuro_values:
                    if not _advance_openneuro_event_values(modal, driver):
                        return
                    driver.trace.append("review OpenNeuro event values")
                if driver.resolve_bids_values:
                    _complete_bids_event_values(modal)
                    driver.trace.append("review BIDS event values")
                driver.phase = 4
                QTEST.mouseClick(modal.next_button, Qt.MouseButton.LeftButton)
                return

            if driver.expect_blocked:
                if modal.apply_button.isEnabled():
                    _fail(
                        "Blocked BIDS review unexpectedly enabled Apply: "
                        f"facts={modal._submission_facts()!r}, "
                        f"choices={modal._edited_choices()!r}, "
                        f"actions={modal.preview.get('action_items')!r}.",
                        modal,
                    )
                    return
                driver.blocked_reasons = [
                    str(reason)
                    for reason in modal.validation_decision.get("blocked_reasons", [])
                ]
                if not any("events.tsv" in reason for reason in driver.blocked_reasons):
                    _fail(
                        "Blocked BIDS review did not identify missing events.tsv: "
                        f"{driver.blocked_reasons!r}",
                        modal,
                    )
                    return
                driver.trace.append("cancel blocked review")
                driver.phase = 5
                QTEST.mouseClick(modal.cancel_button, Qt.MouseButton.LeftButton)
                return

            if driver.resolve_openneuro_values:
                _capture_teacher_ui(
                    modal,
                    "openneuro-review-and-import.png",
                )
            if not modal.apply_button.isEnabled():
                _fail(
                    "Reviewed import did not enable Apply: "
                    f"facts={modal._submission_facts()!r}, "
                    f"decision={modal.validation_decision!r}.",
                    modal,
                )
                return
            driver.trace.append("confirm and import")
            driver.phase = 5
            QTEST.mouseClick(modal.apply_button, Qt.MouseButton.LeftButton)
        except Exception as exc:
            _fail(f"{type(exc).__name__}: {exc}", modal)

    driver.timer.timeout.connect(_poll)
    driver.timer.start()
    return driver


def _wait_for_applied_interpretation(
    qtbot: Any,
    driver: _WizardDriver,
    runtime: Any,
    panel: DatasetPanel,
    *,
    timeout: int = 45_000,
    expected_rows: int = 1,
) -> None:
    try:
        qtbot.waitUntil(
            lambda: bool(driver.errors)
            or runtime.get_view_publication().state.interpretation.has_applied_interpretation,
            timeout=timeout,
        )
    except QtBotTimeoutError:
        _fail_with_runtime_state(driver, panel, "apply timed out")
    driver.timer.stop()
    assert driver.errors == []
    qtbot.waitUntil(
        lambda: application_command_registry().active_count(panel) == 0,
        timeout=10_000,
    )
    qtbot.waitUntil(
        lambda: panel.table.rowCount() == expected_rows,
        timeout=5_000,
    )


def _wait_for_blocked_cancel(
    qtbot: Any,
    driver: _WizardDriver,
    panel: DatasetPanel,
) -> None:
    try:
        qtbot.waitUntil(
            lambda: bool(driver.errors)
            or (
                driver.phase == 5
                and not isinstance(
                    visible_modal_dialog(),
                    DataInterpretationPreviewDialog,
                )
            ),
            timeout=30_000,
        )
    except QtBotTimeoutError:
        _fail_with_runtime_state(driver, panel, "blocked review cancel timed out")
    driver.timer.stop()
    assert driver.errors == []
    qtbot.waitUntil(
        lambda: application_command_registry().active_count(panel) == 0,
        timeout=10_000,
    )


def _fail_with_runtime_state(
    driver: _WizardDriver,
    panel: DatasetPanel,
    reason: str,
) -> None:
    modal = visible_modal_dialog()
    modal_name = type(modal).__name__ if modal is not None else "None"
    step_index = (
        modal.step_stack.currentIndex()
        if isinstance(modal, DataInterpretationPreviewDialog)
        else None
    )
    thread_pool = QThreadPool.globalInstance()
    active_threads = thread_pool.activeThreadCount() if thread_pool is not None else -1
    pytest.fail(
        f"{reason}: phase={driver.phase}, trace={driver.trace!r}, "
        f"errors={driver.errors!r}, active_modal={modal_name}, "
        f"step_index={step_index}, "
        f"active_commands={application_command_registry().active_count(panel)}, "
        f"active_threads={active_threads}."
    )


def _table_text(panel: DatasetPanel, row: int, column: int) -> str:
    item = panel.table.item(row, column)
    assert item is not None, f"Dataset table cell ({row}, {column}) is empty."
    return item.text()


def _non_interpretation_state(
    state: ApplicationStateSnapshot,
) -> dict[str, Any]:
    serialized = state.to_dict()
    serialized.pop("interpretation")
    return serialized


def _block_first_apply_raw_load(service: Any) -> tuple[Event, Event, Event]:
    """Pause the first detached Raw prepare at the real loader boundary.

    Cancellation wins while the production factory call is active.  Releasing
    the barrier still executes the original MNE/BrainVision loader so this
    test proves that a late native result is discarded rather than committed.
    The retry then uses the same production loader again for the same source.
    """
    load_started = Event()
    release_load = Event()
    real_load_finished = Event()
    original_factory = service.dataset._raw_factory_provider()
    should_block = True

    class _BlockingRawFactory:
        @staticmethod
        def load(path: str):
            nonlocal should_block
            if should_block:
                should_block = False
                load_started.set()
                if not release_load.wait(timeout=20.0):
                    raise TimeoutError("Timed out waiting to release BIDS Raw load.")
                try:
                    return original_factory.load(path)
                finally:
                    real_load_finished.set()
            return original_factory.load(path)

    service.dataset._raw_factory_provider = lambda: _BlockingRawFactory
    return load_started, release_load, real_load_finished


@pytest.mark.parametrize(
    "case",
    PUBLIC_FILE_ACCEPTANCE_CASES,
    ids=lambda case: case.fixture_group,
)
def test_public_file_formats_run_five_steps_and_apply_without_labels(
    qtbot: Any,
    monkeypatch: pytest.MonkeyPatch,
    case: _PublicFileAcceptanceCase,
) -> None:
    """Pinned public formats must apply through the visible wizard boundary."""
    _require_manifest_group(case.fixture_group)
    chooser_calls: list[str] = []

    def _choose_files(
        _parent: QWidget,
        title: str,
        _directory: str,
        _filter_text: str,
        **_kwargs: Any,
    ) -> tuple[list[str], str]:
        chooser_calls.append(title)
        return [str(case.source)], ""

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileNames",
        staticmethod(_choose_files),
    )
    _host, panel, runtime = _build_dataset_panel(qtbot)
    before = runtime.get_view_publication().state
    assert before.raw.count == 0

    driver = _start_wizard_driver(skip_labels=True)
    QTEST.mouseClick(panel.sidebar.import_btn, Qt.MouseButton.LeftButton)
    _wait_for_applied_interpretation(qtbot, driver, runtime, panel)

    assert chooser_calls == ["Choose EEG files"]
    assert driver.phase == 5
    assert driver.trace == [
        "Choose EEG Data",
        "Load Labels",
        "continue without labels",
        "Review Metadata",
        "Match Labels",
        "Review and Import",
        "confirm and import",
    ]

    publication = runtime.get_view_publication()
    state = publication.state
    interpretation = state.interpretation
    assert publication.usable is True
    assert state.raw.count == 1
    assert state.raw.files == [case.source.name]
    assert state.raw.event_total == case.expected_event_total
    assert state.raw.unique_events == list(case.expected_unique_events)
    assert state.active_dataset.has_raw_data is True
    assert interpretation.has_applied_interpretation is True
    assert interpretation.source_kind == "file"
    assert interpretation.class_map == {}
    assert interpretation.epoch_handoff["supervised_ready"] is False
    assert interpretation.epoch_handoff["supervised_blocker_codes"] == [
        "missing_class_labels"
    ]
    assert panel.data_surface.currentWidget() is panel.table
    assert _table_text(panel, 0, 0) == case.source.name
    assert _table_text(panel, 0, 6) == case.expected_table_summary


@pytest.mark.parametrize(
    "case",
    PUBLIC_FOLDER_ACCEPTANCE_CASES,
    ids=lambda case: case.fixture_group,
)
def test_public_raw_folders_ignore_context_sidecars_and_apply_selected_eeg(
    qtbot: Any,
    monkeypatch: pytest.MonkeyPatch,
    case: _PublicFolderAcceptanceCase,
) -> None:
    """Clinical/sleep folders must not promote context sidecars into EEG data."""
    _require_manifest_group(case.fixture_group)
    chooser_calls: list[str] = []

    def _choose_folder(
        _parent: QWidget,
        title: str,
        _directory: str,
        **_kwargs: Any,
    ) -> str:
        chooser_calls.append(title)
        return str(case.source)

    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        staticmethod(_choose_folder),
    )
    _host, panel, runtime = _build_dataset_panel(qtbot)

    driver = _start_wizard_driver(skip_labels=True, source_picker="folder")
    QTEST.mouseClick(panel.sidebar.import_btn, Qt.MouseButton.LeftButton)
    _wait_for_applied_interpretation(
        qtbot,
        driver,
        runtime,
        panel,
        timeout=60_000,
    )

    assert chooser_calls == ["Choose EEG folder"]
    assert driver.phase == 5
    assert driver.trace == [
        "Choose EEG Data",
        "Load Labels",
        "continue without labels",
        "Review Metadata",
        "Match Labels",
        "Review and Import",
        "confirm and import",
    ]

    publication = runtime.get_view_publication()
    state = publication.state
    interpretation = state.interpretation
    assert publication.usable is True
    assert state.raw.count == 1
    assert state.raw.files == [case.expected_eeg.name]
    assert state.raw.event_total == 0
    assert state.raw.unique_events == []
    assert interpretation.has_applied_interpretation is True
    assert interpretation.source_kind == "folder"
    assert interpretation.label_carriers == []
    assert interpretation.epoch_handoff["supervised_ready"] is False
    assert interpretation.epoch_handoff["supervised_blocker_codes"] == [
        "missing_class_labels"
    ]
    assert panel.data_surface.currentWidget() is panel.table
    assert panel.table.rowCount() == 1
    assert _table_text(panel, 0, 0) == case.expected_eeg.name
    assert _table_text(panel, 0, 6) == "No events"


def test_openneuro_p300_import_bids_uses_recommended_value_field_and_applies(
    qtbot: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A user can choose the public BIDS root and review its real label values."""
    _require_manifest_group("openneuro-ds003061-p300")
    chooser_calls: list[str] = []

    def _choose_bids_folder(
        _parent: QWidget,
        title: str,
        _directory: str,
        **_kwargs: Any,
    ) -> str:
        chooser_calls.append(title)
        return str(OPENNEURO_P300_ROOT)

    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        staticmethod(_choose_bids_folder),
    )
    _host, panel, runtime = _build_dataset_panel(qtbot)

    driver = _start_wizard_driver(
        resolve_openneuro_values=True,
        source_picker="folder",
    )
    QTEST.mouseClick(panel.sidebar.import_btn, Qt.MouseButton.LeftButton)
    _wait_for_applied_interpretation(
        qtbot,
        driver,
        runtime,
        panel,
        timeout=300_000,
        expected_rows=3,
    )

    assert chooser_calls == ["Choose EEG folder"]
    assert driver.phase == 5
    assert driver.trace == [
        "select BIDS subjects: 001",
        "Choose EEG Data",
        "Load Labels",
        "Review Metadata",
        "Match Labels",
        "accept recommended label field value",
        "review OpenNeuro event values",
        "Review and Import",
        "confirm and import",
    ]
    publication = runtime.get_view_publication()
    state = publication.state
    interpretation = state.interpretation
    assert publication.usable is True
    assert state.raw.count == 3
    assert state.raw.files == [
        "sub-001_task-P300_run-1_eeg.set",
        "sub-001_task-P300_run-2_eeg.set",
        "sub-001_task-P300_run-3_eeg.set",
    ]
    assert interpretation.has_applied_interpretation is True
    assert interpretation.source_kind == "bids"
    assert interpretation.bids["is_bids"] is True
    assert interpretation.class_map == {
        "noise": "noise",
        "noise_with_reponse": "noise",
        "oddball": "oddball",
        "oddball_with_reponse": "oddball",
        "standard": "standard",
        "standard_with_reponse": "standard",
    }
    assert interpretation.epoch_handoff["supervised_ready"] is True
    assert interpretation.epoch_handoff["default_epoch_events"] == [
        "noise",
        "oddball",
        "standard",
    ]
    assert driver.heartbeat_count >= 100
    assert driver.max_heartbeat_gap_seconds < 5.0, (
        f"Maximum GUI heartbeat gap was {driver.max_heartbeat_gap_seconds:.3f}s "
        f"after {driver.max_heartbeat_gap_context}."
    )
    assert panel.data_surface.currentWidget() is panel.table
    assert panel.table.rowCount() == 3


def test_openneuro_p300_import_bids_trial_type_excludes_na_and_applies(
    qtbot: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The visible trial_type flow must not block on sparse BIDS n/a rows."""
    _require_manifest_group("openneuro-ds003061-p300")

    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        staticmethod(
            lambda _parent, _title, _directory, **_kwargs: str(OPENNEURO_P300_ROOT)
        ),
    )
    _host, panel, runtime = _build_dataset_panel(qtbot)
    driver = _start_wizard_driver(
        resolve_openneuro_trial_types=True,
        source_picker="folder",
    )

    QTEST.mouseClick(panel.sidebar.import_btn, Qt.MouseButton.LeftButton)
    _wait_for_applied_interpretation(
        qtbot,
        driver,
        runtime,
        panel,
        timeout=300_000,
        expected_rows=3,
    )

    assert driver.phase == 5
    assert driver.errors == []
    assert "review OpenNeuro trial_type values" in driver.trace
    publication = runtime.get_view_publication()
    assert publication.state.raw.count == 3
    assert publication.state.interpretation.class_map == {"stimulus": "stimulus"}
    assert publication.state.interpretation.epoch_handoff["default_epoch_events"] == [
        "stimulus"
    ]
    assert panel.table.rowCount() == 3


def test_visible_bids_apply_cancel_reopens_identical_review_and_retries(
    qtbot: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real BIDS Apply Cancel preserves and reopens its exact review."""
    _require_manifest_group("mne-bids-tiny-eeg")
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        staticmethod(
            lambda _parent, _title, _directory, **_kwargs: str(PUBLIC_BIDS_ROOT)
        ),
    )
    host, panel, runtime = _build_dataset_panel(qtbot)
    service = get_application_service(host.study)
    load_started, release_load, real_load_finished = _block_first_apply_raw_load(
        service
    )
    driver = _start_wizard_driver(
        resolve_bids_values=True,
        source_picker="folder",
    )

    QTEST.mouseClick(panel.sidebar.import_btn, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(load_started.is_set, timeout=45_000)
    driver.timer.stop()

    before = runtime.get_view_publication()
    review_before = runtime.get_interpretation_review()
    expected_identity = {
        "scan_id": review_before["scan_result"]["scan_id"],
        "candidate_id": review_before["candidate"]["candidate_id"],
        "preview_id": review_before["preview"]["preview_id"],
        "publication_generation": before.generation,
    }
    presenter = panel.action_handler._data_interpretation._operation_presenter
    assert presenter is not None
    cancelled_operation_id = presenter.active_operation_id
    assert isinstance(cancelled_operation_id, str) and cancelled_operation_id
    assert panel.sidebar.import_cancel_btn.isVisibleTo(panel)
    assert panel.sidebar.import_cancel_btn.isEnabled()
    assert service.get_owned_operation(cancelled_operation_id).phase.value in {
        "pending",
        "running",
        "cancelling",
    }

    reopened_identities: list[dict[str, Any]] = []
    retry_timer = QTimer()

    def _accept_reopened_review() -> None:
        modal = visible_modal_dialog()
        if not isinstance(modal, DataInterpretationPreviewDialog):
            return
        reopened_identities.append(
            dict(modal.apply_button.property("reviewSessionIdentity") or {})
        )
        assert modal.apply_button.isEnabled()
        QTEST.mouseClick(modal.apply_button, Qt.MouseButton.LeftButton)
        retry_timer.stop()

    retry_timer.timeout.connect(_accept_reopened_review)
    retry_timer.start(10)
    cancel_started_at = time.monotonic()
    QTEST.mouseClick(panel.sidebar.import_cancel_btn, Qt.MouseButton.LeftButton)
    assert time.monotonic() - cancel_started_at <= 0.1
    release_load.set()
    qtbot.waitUntil(real_load_finished.is_set, timeout=20_000)
    qtbot.waitUntil(
        lambda: service.get_owned_operation(cancelled_operation_id).phase
        is OwnedWorkPhase.CANCELLED,
        timeout=20_000,
    )
    qtbot.waitUntil(
        lambda: bool(reopened_identities),
        timeout=20_000,
    )
    assert reopened_identities == [expected_identity]
    assert runtime.get_view_publication() == before
    assert runtime.get_interpretation_review() == review_before
    assert host.study.loaded_data_list == []

    qtbot.waitUntil(
        lambda: presenter.active_operation_id is not None
        and presenter.active_operation_id != cancelled_operation_id,
        timeout=10_000,
    )
    retry_operation_id = presenter.active_operation_id
    assert isinstance(retry_operation_id, str) and retry_operation_id
    qtbot.waitUntil(
        lambda: runtime.get_view_publication().state.interpretation.has_applied_interpretation,
        timeout=45_000,
    )
    qtbot.waitUntil(
        lambda: application_command_registry().active_count(panel) == 0,
        timeout=20_000,
    )
    assert service.get_owned_operation(cancelled_operation_id).phase is (
        OwnedWorkPhase.CANCELLED
    )
    assert service.get_owned_operation(retry_operation_id).phase is (
        OwnedWorkPhase.COMPLETED
    )


def test_visible_bids_subject_review_has_one_cancel_surface_and_retries(
    qtbot: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Post-subject loading must expose one cancel and discard late metadata."""
    _require_manifest_group("mne-bids-tiny-eeg")

    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        staticmethod(
            lambda _parent, _title, _directory, **_kwargs: str(PUBLIC_BIDS_ROOT)
        ),
    )
    original_bids_summary = data_interpretation_scan._bids_summary
    metadata_read_started = Event()
    release_metadata_read = Event()
    real_metadata_read_finished = Event()
    block_materialized_summary = True

    def _blocking_bids_summary(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal block_materialized_summary
        if block_materialized_summary and kwargs.get("materialize") is True:
            block_materialized_summary = False
            metadata_read_started.set()
            if not release_metadata_read.wait(timeout=20.0):
                raise TimeoutError("Timed out waiting to release BIDS metadata read.")
            try:
                return original_bids_summary(*args, **kwargs)
            finally:
                real_metadata_read_finished.set()
        return original_bids_summary(*args, **kwargs)

    monkeypatch.setattr(
        data_interpretation_scan,
        "_bids_summary",
        _blocking_bids_summary,
    )
    host, panel, runtime = _build_dataset_panel(qtbot)
    service = get_application_service(host.study)
    before = runtime.get_view_publication()
    driver = _start_wizard_driver(source_picker="folder")

    QTEST.mouseClick(panel.sidebar.import_btn, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(metadata_read_started.is_set, timeout=45_000)
    driver.timer.stop()
    loading = visible_modal_dialog()
    assert isinstance(loading, DataInterpretationLoadingDialog)
    operation_id = (
        panel.action_handler._data_interpretation._active_loading_operation_id
    )
    assert isinstance(operation_id, str) and operation_id
    assert loading.cancel_button.text() == "Cancel Import"
    assert loading.cancel_button.isEnabled()
    assert not panel.sidebar.import_cancel_btn.isVisibleTo(panel)

    cancel_started_at = time.monotonic()
    QTEST.mouseClick(loading.cancel_button, Qt.MouseButton.LeftButton)
    assert time.monotonic() - cancel_started_at <= 0.1
    assert not loading.isVisible()
    release_metadata_read.set()
    qtbot.waitUntil(real_metadata_read_finished.is_set, timeout=20_000)
    qtbot.waitUntil(
        lambda: service.get_owned_operation(operation_id).phase
        is OwnedWorkPhase.CANCELLED,
        timeout=20_000,
    )
    qtbot.waitUntil(
        lambda: application_command_registry().active_count(panel) == 0,
        timeout=20_000,
    )
    qtbot.wait(100)
    assert runtime.get_view_publication() == before
    assert host.study.loaded_data_list == []
    assert visible_modal_dialog() is None

    retry_driver = _start_wizard_driver(
        source_picker="folder",
        resolve_bids_values=True,
    )
    QTEST.mouseClick(panel.sidebar.import_btn, Qt.MouseButton.LeftButton)
    _wait_for_applied_interpretation(
        qtbot,
        retry_driver,
        runtime,
        panel,
        timeout=60_000,
    )
    assert retry_driver.errors == []
    assert runtime.get_view_publication().state.raw.count == 1


def test_bids_missing_events_preserves_data_state_then_valid_root_recovers(
    qtbot: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A blocked derived BIDS root must not load data; the next valid import must."""
    _require_manifest_group("mne-bids-tiny-eeg")
    broken_bids_root = tmp_path / "mne-bids-missing-events"
    shutil.copytree(PUBLIC_BIDS_ROOT, broken_bids_root)
    broken_events = broken_bids_root / PUBLIC_BIDS_EVENTS.relative_to(PUBLIC_BIDS_ROOT)
    broken_events.unlink()

    chooser_paths = iter((str(broken_bids_root), str(PUBLIC_BIDS_ROOT)))
    chooser_calls: list[str] = []

    def _choose_bids_folder(
        _parent: QWidget,
        title: str,
        _directory: str,
        **_kwargs: Any,
    ) -> str:
        chooser_calls.append(title)
        return next(chooser_paths)

    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        staticmethod(_choose_bids_folder),
    )
    _host, panel, runtime = _build_dataset_panel(qtbot)
    before = runtime.get_view_publication().state
    before_non_interpretation_state = _non_interpretation_state(before)

    blocked_driver = _start_wizard_driver(
        expect_blocked=True,
        source_picker="folder",
    )
    QTEST.mouseClick(panel.sidebar.import_btn, Qt.MouseButton.LeftButton)
    _wait_for_blocked_cancel(qtbot, blocked_driver, panel)

    blocked_state = runtime.get_view_publication().state
    assert blocked_driver.phase == 5
    assert blocked_driver.trace == [
        "select BIDS subjects: 01",
        "Choose EEG Data",
        "Load Labels",
        "Review Metadata",
        "Match Labels",
        "Review and Import",
        "cancel blocked review",
    ]
    assert _non_interpretation_state(blocked_state) == before_non_interpretation_state
    assert blocked_state.interpretation.has_applied_interpretation is False
    assert panel.table.rowCount() == 0

    recovery_driver = _start_wizard_driver(
        resolve_bids_values=True,
        source_picker="folder",
    )
    QTEST.mouseClick(panel.sidebar.import_btn, Qt.MouseButton.LeftButton)
    _wait_for_applied_interpretation(qtbot, recovery_driver, runtime, panel)

    assert chooser_calls == [
        "Choose EEG folder",
        "Choose EEG folder",
    ]
    assert recovery_driver.phase == 5
    assert recovery_driver.trace == [
        "select BIDS subjects: 01",
        "Choose EEG Data",
        "Load Labels",
        "Review Metadata",
        "Match Labels",
        "review BIDS event values",
        "Review and Import",
        "confirm and import",
    ]

    publication = runtime.get_view_publication()
    state = publication.state
    interpretation = state.interpretation
    assert publication.usable is True
    assert state.raw.count == 1
    assert state.raw.files == [PUBLIC_BIDS_EEG.name]
    assert state.active_dataset.has_raw_data is True
    assert interpretation.has_applied_interpretation is True
    assert interpretation.source_kind == "bids"
    assert interpretation.bids["is_bids"] is True
    assert interpretation.label_carriers == [str(PUBLIC_BIDS_EVENTS.resolve())]
    assert interpretation.class_map == {"show_stimulus": "show stimulus"}
    assert interpretation.epoch_handoff["label_source"] == "bids_events"
    assert interpretation.epoch_handoff["default_epoch_events"] == ["show stimulus"]
    [carrier] = interpretation.label_carrier_plan
    assert carrier["path"] == str(PUBLIC_BIDS_EVENTS.resolve())
    assert carrier["selected_label_field"] == "trial_type"
    assert carrier["selected_anchor"] == "onset"
    assert carrier["selected_duration_field"] == "duration"
    assert carrier["placement_method"] == "interval"
    assert carrier["time_model"] == "seconds"
    assert panel.data_surface.currentWidget() is panel.table
    assert _table_text(panel, 0, 0) == PUBLIC_BIDS_EEG.name
    assert _table_text(panel, 0, 6) == "Labels (1)"
