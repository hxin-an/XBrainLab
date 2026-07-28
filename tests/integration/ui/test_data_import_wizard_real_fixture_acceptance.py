"""Bounded real-fixture acceptance for the user-facing Data Import wizard."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from PyQt6.QtCore import Qt, QThreadPool, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
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
)
from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.study import Study
from XBrainLab.ui.application_capabilities import application_ui_runtime
from XBrainLab.ui.async_command_runner import application_command_registry
from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (
    DataInterpretationPreviewDialog,
)
from XBrainLab.ui.panels.dataset.panel import DatasetPanel

TEST_DATA_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "data"
PUBLIC_ROOT = TEST_DATA_ROOT / "public"
PHYSIONET_REST_EDF = PUBLIC_ROOT / "physionet-eegmmidb-S008R01.edf"
PHYSIONET_MOTOR_EDF = PUBLIC_ROOT / "physionet-eegmmidb-S008R04.edf"
BBCI_GDF = PUBLIC_ROOT / "bbci-competition-iii-O3VR.gdf"
SCCN_EEGLAB_SET = PUBLIC_ROOT / "sccn-eeglab_data.set"
MNE_CNT = PUBLIC_ROOT / "scan41_short.cnt"
MNE_BRAINVISION = PUBLIC_ROOT / "test_NO.vhdr"
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


@dataclass(frozen=True)
class _PublicFileAcceptanceCase:
    fixture_group: str
    source: Path
    expected_event_total: int
    expected_unique_events: tuple[str, ...]
    expected_table_summary: str


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
        "Events not scanned",
    ),
)


@pytest.fixture(autouse=True)
def mock_ui_blocking() -> Iterator[None]:
    """Use the real modal wizard instead of the suite-wide dialog patch."""
    yield


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
    skip_labels: bool = False
    resolve_bids_values: bool = False
    expect_blocked: bool = False
    phase: int = 0
    dialog: DataInterpretationPreviewDialog | None = None
    trace: list[str] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


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
        pytest.skip(
            f"Public fixture group {group_name} is not downloaded: {', '.join(missing)}"
        )
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


def _complete_bids_event_values(dialog: DataInterpretationPreviewDialog) -> None:
    if dialog.label_source_mode_combo.currentData() != "loaded_label_files":
        _select_combo_data(dialog.label_source_mode_combo, "loaded_label_files")

    editor = dialog.event_value_editor
    if editor is None or not editor.isVisibleTo(dialog):
        raise AssertionError("BIDS Match Labels did not expose event-value decisions.")
    values = [
        label.text()
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
    skip_labels: bool = False,
    resolve_bids_values: bool = False,
    expect_blocked: bool = False,
) -> _WizardDriver:
    driver = _WizardDriver(
        timer=QTimer(),
        skip_labels=skip_labels,
        resolve_bids_values=resolve_bids_values,
        expect_blocked=expect_blocked,
    )
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
                    _fail("Dataset Resource Check did not expose Yes.", modal)
                    return
                driver.trace.append("confirm resource check")
                QTEST.mouseClick(yes_button, Qt.MouseButton.LeftButton)
                return

            if not isinstance(modal, DataInterpretationPreviewDialog):
                return
            if driver.dialog is None:
                driver.dialog = modal
            elif modal is not driver.dialog:
                _fail("The acceptance flow unexpectedly opened a second wizard.", modal)
                return

            if driver.phase >= len(STEP_TITLES):
                return
            _assert_step_surface(modal, driver.phase)
            driver.trace.append(STEP_TITLES[driver.phase])

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
                if driver.resolve_bids_values:
                    _complete_bids_event_values(modal)
                    driver.trace.append("review BIDS event values")
                driver.phase = 4
                QTEST.mouseClick(modal.next_button, Qt.MouseButton.LeftButton)
                return

            if driver.expect_blocked:
                if modal.apply_button.isEnabled():
                    _fail("Blocked BIDS review unexpectedly enabled Apply.", modal)
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
    qtbot.waitUntil(lambda: panel.table.rowCount() == 1, timeout=5_000)


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
                    QApplication.activeModalWidget(),
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
    modal = QApplication.activeModalWidget()
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

    assert chooser_calls == ["Choose EEG Source for Interpretation"]
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

    blocked_driver = _start_wizard_driver(expect_blocked=True)
    QTEST.mouseClick(panel.sidebar.import_bids_btn, Qt.MouseButton.LeftButton)
    _wait_for_blocked_cancel(qtbot, blocked_driver, panel)

    blocked_state = runtime.get_view_publication().state
    assert blocked_driver.phase == 5
    assert blocked_driver.trace == [
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

    recovery_driver = _start_wizard_driver(resolve_bids_values=True)
    QTEST.mouseClick(panel.sidebar.import_bids_btn, Qt.MouseButton.LeftButton)
    _wait_for_applied_interpretation(qtbot, recovery_driver, runtime, panel)

    assert chooser_calls == [
        "Choose BIDS Folder for Import",
        "Choose BIDS Folder for Import",
    ]
    assert recovery_driver.phase == 5
    assert recovery_driver.trace == [
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
