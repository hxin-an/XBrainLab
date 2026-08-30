from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import torch
from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QFrame, QGroupBox, QLabel

from XBrainLab.backend.application import ApplicationService, SaveDatasetSplitCommand
from XBrainLab.backend.application.dataset_split_preview import (
    DatasetSplitPreviewRequest,
    DatasetSplitSpecification,
)
from XBrainLab.backend.application.epoch_context import build_epoching_context
from XBrainLab.backend.application.errors import PreconditionError
from XBrainLab.backend.dataset import Epochs
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import TrainingEvaluation, TrainingOption
from XBrainLab.ui.dialogs.dataset.event_filter_dialog import EventFilterDialog
from XBrainLab.ui.dialogs.dataset.label_mapping_dialog import LabelMappingDialog
from XBrainLab.ui.dialogs.preprocess.epoching_dialog import (
    EpochingDialog,
    EpochSubmissionIssue,
    validate_epoch_baseline,
    validate_epoch_submission,
)
from XBrainLab.ui.dialogs.training.training_setting_dialog import TrainingSettingDialog


def _show_dialog(qtbot, dialog: QDialog) -> None:
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)


def _click_ok(qtbot, dialog: QDialog) -> None:
    buttons = dialog.findChild(QDialogButtonBox)
    assert buttons is not None
    ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert ok_button is not None
    qtbot.mouseClick(ok_button, Qt.MouseButton.LeftButton)
    qtbot.wait(50)


def _admitted_epoch_context(data: MagicMock) -> dict[str, object]:
    """Build a dialog context from the same import handoff used in production."""
    hint = data.get_runtime_detail.return_value
    if not isinstance(hint, dict):
        hint = {
            "source": "Labels inside EEG files",
            "placement_method": "internal_events",
            "class_map": {"left": "left", "right": "right"},
            "recommended_events": ["left", "right"],
        }
        data.get_runtime_detail.return_value = hint
    else:
        hint = dict(hint)
        if "bids" in str(hint.get("source") or "").casefold():
            stats = hint.get("duration_stats")
            if isinstance(stats, dict):
                numeric_count = int(stats.get("numeric_count") or 0)
                if numeric_count > 0:
                    hint.setdefault("placement_event_count", numeric_count)
                    hint.setdefault("unknown_duration_count", 0)
                else:
                    unknown_count = max(len(hint.get("class_map") or {}), 1)
                    hint.setdefault("placement_event_count", unknown_count)
                    hint.setdefault("unknown_duration_count", unknown_count)
        data.get_runtime_detail.return_value = hint
    placement = str(hint.get("placement_method") or "internal_events")
    source = str(hint.get("source") or "").casefold()
    label_source = (
        "bids_events"
        if "bids" in source
        else "internal_events"
        if placement == "internal_events"
        else "loaded_label_files"
    )
    return build_epoching_context(
        [data],
        epoch_handoff={
            "ready": True,
            "supervised_ready": True,
            "default_epoch_events": list((hint.get("class_map") or {}).values()),
            "selected_event_names": list((hint.get("class_map") or {}).values()),
            "label_source": label_source,
            "placement_modes": [placement],
        },
    )


def test_label_mapping_dialog_accepts_auto_sorted_mapping(qtbot):
    dialog = LabelMappingDialog(
        None,
        ["/tmp/sub01.set", "/tmp/sub02.set"],
        ["/tmp/sub02_labels.txt", "/tmp/sub01_labels.txt"],
    )

    _show_dialog(qtbot, dialog)
    _click_ok(qtbot, dialog)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.get_mapping() == {
        "/tmp/sub01.set": "/tmp/sub01_labels.txt",
        "/tmp/sub02.set": "/tmp/sub02_labels.txt",
    }


def test_event_filter_dialog_accepts_checked_selection_via_ok_button(qtbot):
    fake_settings = MagicMock()
    fake_settings.value.return_value = []

    with patch(
        "XBrainLab.ui.dialogs.dataset.event_filter_dialog.QSettings",
        return_value=fake_settings,
    ):
        dialog = EventFilterDialog(None, ["left_hand", "right_hand", "feet"])

    _show_dialog(qtbot, dialog)

    dialog.set_all_checked(False)
    assert dialog.list_widget is not None
    item = dialog.list_widget.item(1)
    assert item is not None
    item.setCheckState(Qt.CheckState.Checked)

    _click_ok(qtbot, dialog)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.get_selected_ids() == ["right_hand"]
    fake_settings.setValue.assert_called_once_with(
        "last_selected_events",
        ["right_hand"],
    )


def test_epoching_dialog_accepts_selected_event_and_baseline_toggle(qtbot):
    data = MagicMock()
    data.get_event_list.return_value = (None, {"left": 1, "right": 2})
    dialog = EpochingDialog(
        None,
        epoch_context=_admitted_epoch_context(data),
    )

    _show_dialog(qtbot, dialog)

    assert dialog.event_list is not None
    for row in range(dialog.event_list.rowCount()):
        check_item = dialog.event_list.item(row, 0)
        event_item = dialog.event_list.item(row, 1)
        assert check_item is not None
        assert event_item is not None
        check_item.setCheckState(
            Qt.CheckState.Checked
            if event_item.text() == "left"
            else Qt.CheckState.Unchecked
        )
    assert dialog.baseline_check is not None
    assert dialog.tmin_spin is not None
    assert dialog.tmax_spin is not None
    dialog.baseline_check.setChecked(False)
    dialog.tmin_spin.setValue(-0.1)
    dialog.tmax_spin.setValue(0.8)

    _click_ok(qtbot, dialog)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.get_result() == (None, ["left"], -0.1, 0.8)


def test_epoching_dialog_uses_import_interval_defaults(qtbot):
    data = MagicMock()
    data.get_event_list.return_value = (
        None,
        {"Left hand": 1, "Right hand": 2, "Artifact": 99},
    )
    data.get_runtime_detail.return_value = {
        "source": "BIDS events.tsv",
        "placement_method": "interval",
        "label_field": "trial_type",
        "time_field": "onset",
        "duration_field": "duration",
        "duration_stats": {"numeric_count": 288, "min": 0.5, "max": 1.25},
        "class_map": {"left": "Left hand", "right": "Right hand"},
    }
    dialog = EpochingDialog(
        None,
        epoch_context=_admitted_epoch_context(data),
    )

    _show_dialog(qtbot, dialog)

    visible_text = "\n".join(
        label.text()
        for label in dialog.findChildren(QLabel)
        if label.text().strip() and label.isVisibleTo(dialog)
    )
    assert "BIDS events from import" in visible_text
    assert "Label field" in visible_text
    assert "trial_type" in visible_text
    assert "Epoch anchor" not in visible_text
    assert "Event onset" not in visible_text
    assert "Window mode" in visible_text
    assert "Fixed to largest duration" in visible_text
    assert dialog.tmin_spin is not None
    assert dialog.tmax_spin is not None
    assert dialog.baseline_check is not None
    assert dialog.event_list is not None
    assert dialog.tmin_spin.value() == 0.0
    assert dialog.tmax_spin.value() == 1.25
    assert dialog.baseline_check.isChecked() is False
    checked = [
        event_item.text()
        for row in range(dialog.event_list.rowCount())
        if (check_item := dialog.event_list.item(row, 0)) is not None
        and (event_item := dialog.event_list.item(row, 1)) is not None
        and check_item.checkState() == Qt.CheckState.Checked
    ]
    assert checked == ["Left hand", "Right hand"]


def test_epoching_dialog_shows_effective_event_locked_timing_and_separate_baseline(
    qtbot,
):
    data = MagicMock()
    data.get_event_list.return_value = (None, {"TARGET": 1, "NON TARGET": 2})
    data.get_runtime_detail.return_value = {
        "source": "BIDS events.tsv",
        "placement_method": "interval",
        "label_field": "value",
        "time_field": "onset",
        "duration_field": "duration",
        "duration_stats": {"numeric_count": 0, "min": None, "max": None},
        "class_map": {"target": "TARGET", "standard": "NON TARGET"},
    }
    dialog = EpochingDialog(
        None,
        epoch_context=_admitted_epoch_context(data),
    )

    _show_dialog(qtbot, dialog)

    visible_text = "\n".join(
        label.text()
        for label in dialog.findChildren(QLabel)
        if label.text().strip() and label.isVisibleTo(dialog)
    )
    import_card = dialog.findChild(QFrame, "EpochImportHintCard")
    baseline_card = dialog.findChild(QFrame, "EpochBaselineSection")

    assert import_card is not None
    assert baseline_card is not None
    assert "Label field" in visible_text
    assert "value" in visible_text
    assert "Epoch anchor" not in visible_text
    assert "Event onset" not in visible_text
    assert "Window mode" in visible_text
    assert "Event-locked" in visible_text
    assert "Timing\nonset + duration" not in visible_text
    assert "Baseline Correction" in visible_text
    assert (
        "When enabled, the average signal in this interval will be removed "
        "from each epoch." in visible_text
    )


@pytest.mark.parametrize(
    (
        "placement_method",
        "time_field",
        "duration_field",
        "expected_labels",
        "unexpected_labels",
    ),
    [
        (
            "internal_events",
            "",
            "",
            (),
            ("Event anchor", "Epoch anchor", "Event onset"),
        ),
        (
            "event_code",
            "719",
            "",
            (),
            ("Event anchor", "Epoch anchor", "719"),
        ),
        (
            "eeg_event",
            "",
            "",
            (),
            ("Event anchor", "Epoch anchor"),
        ),
        (
            "time_field",
            "onset",
            "",
            ("Time field", "onset"),
            ("Event anchor", "Epoch anchor"),
        ),
        (
            "interval",
            "onset",
            "duration",
            ("Start field", "onset", "Duration field", "duration"),
            ("Event anchor", "Epoch anchor"),
        ),
    ],
)
def test_epoching_dialog_names_import_timing_fields_by_placement(
    qtbot,
    placement_method,
    time_field,
    duration_field,
    expected_labels,
    unexpected_labels,
):
    """Only actionable imported timing fields belong in the epoch setup card."""
    data = MagicMock()
    data.get_event_list.return_value = (None, {"Left hand": 1, "Right hand": 2})
    data.get_runtime_detail.return_value = {
        "source": "Loaded label files",
        "placement_method": placement_method,
        "label_field": "classlabel",
        "time_field": time_field,
        "duration_field": duration_field,
        "duration_stats": {"numeric_count": 2, "min": 0.5, "max": 1.0},
        "class_map": {"left": "Left hand", "right": "Right hand"},
    }
    dialog = EpochingDialog(None, epoch_context=_admitted_epoch_context(data))

    _show_dialog(qtbot, dialog)

    visible_text = "\n".join(
        label.text()
        for label in dialog.findChildren(QLabel)
        if label.text().strip() and label.isVisibleTo(dialog)
    )
    assert "Imported event setup" in visible_text
    assert dialog.handoff_label is None
    assert "Timing" not in visible_text
    for label in expected_labels:
        assert label in visible_text
    for label in unexpected_labels:
        assert label not in visible_text


def test_epoching_baseline_validation_reacts_without_waiting_for_accept(qtbot):
    data = MagicMock()
    data.get_event_list.return_value = (None, {"left": 1})
    data.get_runtime_detail.return_value = {
        "source": "Labels inside EEG files",
        "placement_method": "internal_events",
        "suggested_t_min": -0.2,
        "suggested_t_max": 1.0,
        "suggested_baseline": (-0.2, 0.0),
        "class_map": {"left": "left"},
    }
    dialog = EpochingDialog(
        None,
        epoch_context=_admitted_epoch_context(data),
    )
    _show_dialog(qtbot, dialog)

    assert dialog.baseline_check is not None
    assert dialog.b_min_spin is not None
    assert dialog.b_max_spin is not None
    assert dialog.tmin_spin is not None
    assert dialog.baseline_error_label is not None
    assert dialog.create_button is not None
    dialog.baseline_check.setChecked(True)

    dialog.b_min_spin.setValue(0.2)
    dialog.b_max_spin.setValue(0.1)
    assert not dialog.create_button.isEnabled()
    assert "Baseline start" in dialog.baseline_error_label.text()

    dialog.b_min_spin.setValue(-0.2)
    dialog.b_max_spin.setValue(0.0)
    assert dialog.create_button.isEnabled()
    assert not dialog.baseline_error_label.isVisibleTo(dialog)

    dialog.tmin_spin.setValue(-0.1)
    assert not dialog.create_button.isEnabled()
    assert "inside the EEG epoch" in dialog.baseline_error_label.text()

    dialog.tmin_spin.setValue(-0.2)
    assert dialog.create_button.isEnabled()


@pytest.mark.parametrize(
    ("baseline_min", "baseline_max", "expected_error"),
    [
        (-0.2, 0.0, None),
        (0.0, 1.0, None),
        (0.1, 0.0, "Baseline start must be less than or equal to baseline end."),
        (-0.21, 0.0, "Baseline must stay inside the EEG epoch time window."),
        (-0.2, 1.01, "Baseline must stay inside the EEG epoch time window."),
    ],
)
def test_epoching_baseline_boundaries_match_live_and_accept_validation(
    qtbot,
    baseline_min,
    baseline_max,
    expected_error,
):
    data = MagicMock()
    data.get_event_list.return_value = (None, {"left": 1})
    dialog = EpochingDialog(
        None,
        epoch_context=_admitted_epoch_context(data),
    )
    _show_dialog(qtbot, dialog)

    assert dialog.baseline_check is not None
    assert dialog.b_min_spin is not None
    assert dialog.b_max_spin is not None
    assert dialog.baseline_error_label is not None
    assert dialog.create_button is not None
    dialog.baseline_check.setChecked(True)
    dialog.b_min_spin.setValue(baseline_min)
    dialog.b_max_spin.setValue(baseline_max)

    pure_error = validate_epoch_baseline(
        enabled=True,
        baseline_min=baseline_min,
        baseline_max=baseline_max,
        t_min=-0.2,
        t_max=1.0,
    )
    assert pure_error == expected_error
    assert dialog.baseline_error_label.text() == (expected_error or "")
    assert dialog.create_button.isEnabled() is (expected_error is None)

    with patch(
        "XBrainLab.ui.dialogs.preprocess.epoching_dialog.show_warning"
    ) as warning:
        dialog.accept()

    if expected_error is not None:
        warning.assert_called_once_with(dialog, "Invalid Input", expected_error)
        assert dialog.get_params() is None
    else:
        warning.assert_not_called()
        assert dialog.result() == QDialog.DialogCode.Accepted
        assert dialog.get_params() == (
            (baseline_min, baseline_max),
            ["left"],
            -0.2,
            1.0,
        )


def test_epoching_dialog_unknown_window_mode_needs_review_and_blocks_submit(qtbot):
    dialog = EpochingDialog(
        None,
        epoch_context={
            "available_events": [{"name": "target", "count": 12}],
            "recommended_events": ["target"],
            "suggested_t_min": -0.2,
            "suggested_t_max": 1.0,
            "suggested_baseline": (-0.2, 0.0),
            "has_import_hint": True,
            "source": "BIDS events",
            "placement_method": "interval",
            "placement_label": "Label interval",
            "label_field": "trial_type",
            "window_mode": "legacy_duration_mode",
        },
    )
    _show_dialog(qtbot, dialog)

    visible_text = "\n".join(
        label.text()
        for label in dialog.findChildren(QLabel)
        if label.text().strip() and label.isVisibleTo(dialog)
    )
    assert "Window mode" in visible_text
    assert "Needs review" in visible_text
    assert "Event-locked" not in visible_text
    assert "Fixed to largest duration" not in visible_text
    assert dialog.window_mode is None
    assert dialog.create_button is not None
    assert not dialog.create_button.isEnabled()

    with patch(
        "XBrainLab.ui.dialogs.preprocess.epoching_dialog.show_warning"
    ) as warning:
        dialog.accept()

    warning.assert_called_once()
    assert warning.call_args.args[1] == "Review epoch window"
    assert "window mode needs review" in warning.call_args.args[2]
    assert dialog.get_params() is None


def test_epoch_submission_validator_includes_confirmation_requirement():
    validation = validate_epoch_submission(
        context_available=True,
        context_unavailable_reason="",
        window_mode="duration",
        selected_events=["left"],
        t_min=0.0,
        t_max=1.0,
        baseline_enabled=False,
        baseline_min=-0.2,
        baseline_max=0.0,
        confirmation_required=True,
        confirmation_accepted=False,
        confirmation_title="Review BIDS event durations",
        confirmation_message="Review the imported duration range.",
    )

    assert validation.allowed is False
    assert validation.issue is EpochSubmissionIssue.CONFIRMATION_REQUIRED
    assert validation.title == "Review BIDS event durations"
    assert validation.message == "Review the imported duration range."


@pytest.mark.parametrize(
    ("case", "expected_title", "expected_message"),
    [
        ("events", "Warning", "Please select at least one event."),
        ("order", "Invalid Input", "Start time must be less than End time."),
        (
            "duration",
            "Invalid Input",
            "EEG epoch duration is too short (< 0.1s).",
        ),
    ],
)
def test_epoching_live_and_accept_share_event_and_window_validation(
    qtbot,
    case,
    expected_title,
    expected_message,
):
    data = MagicMock()
    data.get_event_list.return_value = (None, {"left": 1})
    data.get_runtime_detail.return_value = {
        "source": "Labels inside EEG files",
        "placement_method": "internal_events",
        "class_map": {"left": "left"},
        "recommended_events": ["left"],
    }
    context = build_epoching_context(
        [data],
        epoch_handoff={
            "ready": True,
            "supervised_ready": True,
            "default_epoch_events": ["left"],
            "selected_event_names": ["left"],
            "label_source": "internal_events",
            "placement_modes": ["internal_events"],
        },
    )
    dialog = EpochingDialog(None, epoch_context=context)
    _show_dialog(qtbot, dialog)

    assert dialog.event_list is not None
    assert dialog.tmin_spin is not None
    assert dialog.tmax_spin is not None
    assert dialog.create_button is not None
    if case == "events":
        dialog.event_list.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
    elif case == "order":
        dialog.tmin_spin.setValue(0.5)
        dialog.tmax_spin.setValue(0.5)
    else:
        dialog.tmin_spin.setValue(0.0)
        dialog.tmax_spin.setValue(0.05)

    assert dialog.create_button.isEnabled() is False
    assert dialog.warning_label is not None
    assert dialog.warning_label.text() == expected_message
    assert dialog.warning_label.isVisible()

    with patch(
        "XBrainLab.ui.dialogs.preprocess.epoching_dialog.show_warning"
    ) as warning:
        dialog.accept()

    warning.assert_called_once_with(dialog, expected_title, expected_message)
    assert dialog.get_params() is None


def test_epoching_dialog_rejects_handoff_from_another_context(qtbot):
    data = MagicMock()
    data.get_event_list.return_value = (None, {"left": 1, "right": 2})
    data.get_runtime_detail.return_value = {
        "source": "Labels inside EEG files",
        "placement_method": "internal_events",
        "class_map": {"left": "left", "right": "right"},
        "recommended_events": ["left", "right"],
    }
    context = _admitted_epoch_context(data)

    dialog = EpochingDialog(
        None,
        epoch_context=context,
        epoch_handoff={
            "ready": True,
            "supervised_ready": True,
            "default_epoch_events": ["other"],
            "selected_event_names": ["other"],
            "label_source": "internal_events",
            "placement_modes": ["internal_events"],
        },
    )
    _show_dialog(qtbot, dialog)

    assert dialog.context_availability.available is False
    assert dialog.create_button is not None
    assert dialog.create_button.isEnabled() is False
    assert dialog.handoff_label is not None
    assert "does not match" in dialog.handoff_label.text()


def test_epoching_internal_event_hint_does_not_clip_dialog_at_compact_width(qtbot):
    dialog = EpochingDialog(
        None,
        epoch_context={
            "available_events": [{"name": "769", "count": 72}],
            "recommended_events": ["769"],
            "suggested_t_min": -0.2,
            "suggested_t_max": 1.0,
            "suggested_baseline": (-0.2, 0.0),
            "has_import_hint": True,
            "source": "labels inside EEG files",
            "placement_method": "internal_events",
            "placement_label": "Events inside EEG files",
            "window_mode": "event_locked",
        },
    )
    dialog.resize(QSize(640, 720))

    _show_dialog(qtbot, dialog)

    for object_name in ("EpochDialogTitle", "EpochImportHintCard"):
        widget = dialog.findChild(
            QFrame if object_name.endswith("Card") else QLabel, object_name
        )
        assert widget is not None
        bounds = QRect(widget.mapTo(dialog, QPoint(0, 0)), widget.size())
        assert dialog.rect().contains(bounds)
        assert widget.visibleRegion().contains(widget.rect())


def test_epoching_short_window_note_is_model_neutral(qtbot):
    data = MagicMock()
    data.get_event_list.return_value = (None, {"left": 1})
    dialog = EpochingDialog(
        None,
        epoch_context=_admitted_epoch_context(data),
    )
    _show_dialog(qtbot, dialog)

    assert dialog.tmin_spin is not None
    assert dialog.tmax_spin is not None
    assert dialog.warning_label is not None
    dialog.tmin_spin.setValue(-0.2)
    dialog.tmax_spin.setValue(0.5)

    warning = dialog.warning_label.text()
    assert "Short analysis window" in warning
    assert "selected model" in warning
    assert "EEGNet" not in warning
    assert "SCCNet" not in warning
    assert "ShallowConvNet" not in warning
    assert "high sampling" not in warning


def test_epoching_dialog_displays_and_returns_backend_duration_requirement(
    qtbot,
):
    data = MagicMock()
    data.get_event_list.return_value = (
        None,
        {"left": 1, "right": 2},
    )
    data.get_sfreq.return_value = 100.0
    data.get_runtime_detail.return_value = {
        "source": "BIDS events.tsv",
        "placement_method": "interval",
        "label_field": "trial_type",
        "time_field": "onset",
        "duration_field": "duration",
        "duration_stats": {"numeric_count": 2, "min": 0.25, "max": 12.0},
        "class_map": {"left": "left", "right": "right"},
    }
    dialog = EpochingDialog(
        None,
        epoch_context=_admitted_epoch_context(data),
    )
    _show_dialog(qtbot, dialog)

    requirement = dialog.confirmation_requirement
    assert requirement is not None
    assert dialog.warning_label is not None
    assert requirement["message"] in dialog.warning_label.text()
    assert dialog.confirmation_check is not None
    assert dialog.confirmation_check.text() == requirement["confirmation_label"]

    with patch(
        "XBrainLab.ui.dialogs.preprocess.epoching_dialog.show_warning"
    ) as warning:
        dialog.accept()
    warning.assert_called_once_with(
        dialog,
        requirement["title"],
        requirement["message"],
    )
    assert dialog.get_params() is None
    assert dialog.get_confirmation_receipt() is None

    dialog.confirmation_check.setChecked(True)
    initial_receipt = requirement["receipt"]
    assert dialog.tmax_spin is not None
    dialog.tmax_spin.setValue(10.0)
    assert dialog.confirmation_check.isChecked() is False
    assert dialog.confirmation_requirement is not None
    assert dialog.confirmation_requirement["receipt"] != initial_receipt

    window_receipt = dialog.confirmation_requirement["receipt"]
    dialog.confirmation_check.setChecked(True)
    assert dialog.event_list is not None
    for row in range(dialog.event_list.rowCount()):
        event_item = dialog.event_list.item(row, 1)
        check_item = dialog.event_list.item(row, 0)
        if (
            event_item is not None
            and check_item is not None
            and event_item.text() == "right"
        ):
            check_item.setCheckState(Qt.CheckState.Unchecked)
            break
    assert dialog.confirmation_check.isChecked() is False
    assert dialog.confirmation_requirement is not None
    assert dialog.confirmation_requirement["receipt"] != window_receipt

    dialog.confirmation_check.setChecked(True)
    dialog.accept()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert (
        dialog.get_confirmation_receipt()
        == (dialog.confirmation_requirement["receipt"])
    )


def test_epoching_dialog_preserves_sample_aligned_bids_tmax_precision(qtbot):
    data = MagicMock()
    data.get_event_list.return_value = (None, {"late_event": 1})
    data.get_sfreq.return_value = 250.0
    data.get_runtime_detail.return_value = {
        "source": "BIDS events.tsv",
        "placement_method": "interval",
        "label_field": "trial_type",
        "time_field": "onset",
        "duration_field": "duration",
        "duration_stats": {"numeric_count": 1, "min": 0.5, "max": 0.5},
        "class_map": {"late_event": "late_event"},
    }
    context = _admitted_epoch_context(data)

    dialog = EpochingDialog(None, epoch_context=context)
    _show_dialog(qtbot, dialog)

    assert dialog.tmax_spin is not None
    assert dialog.duration_label is not None
    assert context["suggested_t_max"] == 0.496
    assert dialog.tmax_spin.value() == 0.496
    assert "0.50 s window" in dialog.duration_label.text()


def test_epoching_dialog_uses_card_sections_not_groupbox_legends(qtbot):
    data = MagicMock()
    data.get_event_list.return_value = (None, {"Left hand": 1, "Right hand": 2})
    data.get_runtime_detail.return_value = {
        "source": "Labels inside EEG files",
        "placement_method": "internal_events",
        "class_map": {"769": "Left hand", "770": "Right hand"},
    }
    dialog = EpochingDialog(
        None,
        epoch_context=_admitted_epoch_context(data),
    )

    _show_dialog(qtbot, dialog)

    assert dialog.findChildren(QGroupBox) == []


def test_training_setting_dialog_accepts_user_edits_via_ok_button(qtbot):
    controller = MagicMock()
    controller.get_training_option.return_value = None

    with patch(
        "XBrainLab.ui.dialogs.training.training_setting_dialog.get_optimizer_classes",
        return_value={"Adam": torch.optim.Adam},
    ):
        dialog = TrainingSettingDialog(None, controller)

    _show_dialog(qtbot, dialog)

    assert dialog.epoch_entry is not None
    assert dialog.bs_entry is not None
    assert dialog.lr_entry is not None
    assert dialog.checkpoint_entry is not None
    assert dialog.repeat_entry is not None
    assert dialog.output_dir_label is not None
    assert dialog.evaluation_combo is not None
    dialog.epoch_entry.setText("12")
    dialog.bs_entry.setText("16")
    dialog.lr_entry.setText("0.0005")
    dialog.checkpoint_entry.setText("2")
    dialog.repeat_entry.setText("3")
    dialog.output_dir = "/tmp/train-output"
    dialog.output_dir_label.setText("/tmp/train-output")
    dialog.evaluation_combo.setCurrentText("Last Epoch")

    _click_ok(qtbot, dialog)

    option = dialog.get_result()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert option is not None
    assert option.epoch == 12
    assert option.bs == 16
    assert option.lr == 0.0005
    assert option.output_dir == "/tmp/train-output"
    assert option.repeat_num == 3


def test_training_setting_dialog_uses_real_saved_split_recommendation(qtbot):
    sample_count = 1_000
    labels = np.arange(sample_count, dtype=int) % 2
    epoch_data = Epochs([])
    epoch_data.data = np.zeros((sample_count, 2, 64), dtype=np.float32)
    epoch_data.event_id = {"Left": 0, "Right": 1}
    epoch_data.label_map = {0: "Left", 1: "Right"}
    epoch_data.label = labels
    epoch_data.subject = np.zeros(sample_count, dtype=int)
    epoch_data.session = np.zeros(sample_count, dtype=int)
    epoch_data.idx = np.arange(sample_count, dtype=int)
    epoch_data.trial_group = np.arange(sample_count, dtype=int)
    epoch_data.subject_map = {0: "S01"}
    epoch_data.session_map = {0: "001"}
    epoch_data.ch_names = ["C3", "C4"]
    epoch_data.sfreq = 128.0

    study = Study()
    study.data_manager.epoch_data = epoch_data
    study.set_training_option(
        TrainingOption(
            output_dir="/tmp/training-recommendation-output",
            optim=torch.optim.Adam,
            optim_params={},
            use_cpu=True,
            gpu_idx=None,
            epoch=10,
            bs=16,
            lr=0.001,
            checkpoint_epoch=0,
            evaluation_option=TrainingEvaluation.LAST_EPOCH,
            repeat_num=1,
        )
    )
    service = ApplicationService(study)

    try:
        split_specification = DatasetSplitSpecification.from_payload(
            {
                "train_type": "Individual",
                "is_cross_validation": False,
                "val_splitters": [
                    {
                        "split_type": "By Trial",
                        "split_unit": "Ratio",
                        "value": "0.1",
                    }
                ],
                "test_splitters": [
                    {
                        "split_type": "By Trial",
                        "split_unit": "Ratio",
                        "value": "0.1",
                    }
                ],
            }
        )
        pre_save_generation = service.get_view_publication().generation
        preview = service.get_dataset_split_preview(
            DatasetSplitPreviewRequest(
                request_id="training-recommendation-acceptance",
                publication_generation=pre_save_generation,
                specification=split_specification,
            )
        )
        saved = service.execute(
            SaveDatasetSplitCommand(
                split_config=split_specification.to_payload(),
                preview_receipt=preview.receipt,
            ),
            expected_publication_generation=pre_save_generation,
        )

        assert saved.ok is True
        assert saved.state.dataset.split_spec_saved is True
        assert saved.state.dataset.split_materialized is False
        assert saved.state.dataset.split_preview_summary["train_count"] >= 512
        saved_generation = service.get_view_publication().generation
        assert saved_generation > pre_save_generation

        baseline = service.get_training_recommendation(
            expected_publication_generation=saved_generation,
        )
        prospective = service.get_training_recommendation(
            expected_publication_generation=saved_generation,
            prospective_model_name="braindecode.deep4net",
            prospective_model_params={"n_filters_time": 25},
        )

        assert service.get_state().training.model_name is None
        assert prospective.context_fingerprint != baseline.context_fingerprint
        assert prospective.recommended_values.epochs > (
            baseline.recommended_values.epochs
        )
        assert prospective.recommended_values.batch_size > (
            baseline.recommended_values.batch_size
        )
        assert prospective.recommended_values.optimizer == "AdamW"

        dialog = TrainingSettingDialog(
            None,
            None,
            initial_option=saved.state.training.training_option,
            recommendation=prospective,
        )
        _show_dialog(qtbot, dialog)

        assert dialog.get_recommendation() == prospective
        assert dialog.epoch_entry is not None
        assert dialog.bs_entry is not None
        assert dialog.lr_entry is not None
        assert dialog.evaluation_combo is not None
        assert int(dialog.epoch_entry.text()) == prospective.values.epochs
        assert int(dialog.bs_entry.text()) == prospective.values.batch_size
        assert float(dialog.lr_entry.text()) == prospective.values.learning_rate
        assert dialog.optim is torch.optim.AdamW
        assert dialog.evaluation_combo.currentData() is TrainingEvaluation.VAL_LOSS

        _click_ok(qtbot, dialog)

        option = dialog.get_result()
        assert dialog.result() == QDialog.DialogCode.Accepted
        assert option is not None
        assert option.epoch == prospective.values.epochs
        assert option.bs == prospective.values.batch_size
        assert option.lr == prospective.values.learning_rate
        assert option.optim is torch.optim.AdamW
        assert service.get_state().training.model_name is None

        with pytest.raises(
            PreconditionError,
            match=r"Training context changed\. Review the settings again\.",
        ):
            service.get_training_recommendation(
                expected_publication_generation=pre_save_generation,
            )
    finally:
        service.close()
