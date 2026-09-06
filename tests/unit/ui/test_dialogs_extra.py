"""Manual selection, channel validation, and epoch dialog behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QScrollArea,
)

from XBrainLab.backend.application.epoch_context import build_epoching_context

# ============ ManualSplitDialog ============


class TestManualSplitDialog:
    @pytest.fixture
    def dlg(self, qtbot):
        from XBrainLab.ui.dialogs.dataset.manual_split_dialog import ManualSplitDialog

        choices = ["S01", "S02", "S03", "S04"]
        d = ManualSplitDialog(None, choices)
        qtbot.addWidget(d)
        return d

    def test_accept(self, dlg):
        # Select first 2 items
        for i in range(2):
            item = dlg.list_widget.item(i)
            item.setSelected(True)
        dlg.accept()
        result = dlg.get_result()
        assert result is not None


# ============ ChannelSelectionDialog ============


class TestChannelSelectionDialog:
    @pytest.fixture
    def dlg(self, qtbot):
        from XBrainLab.ui.dialogs.dataset.channel_selection_dialog import (
            ChannelSelectionDialog,
        )

        channels = [
            "C3",
            "C4",
            "Cz",
            "Fz",
            "Pz",
            "O1",
            "O2",
        ]
        d = ChannelSelectionDialog(None, channels)
        qtbot.addWidget(d)
        return d

    def test_accept_none_selected(self, dlg):
        dlg.set_all_checked(False)
        with patch(
            "XBrainLab.ui.dialogs.dataset.channel_selection_dialog.show_warning"
        ) as warning:
            dlg.accept()

        warning.assert_called_once_with(
            dlg,
            "Warning",
            "Please select at least one channel.",
        )


# ============ EpochingDialog ============


class TestEpochingDialog:
    @pytest.fixture
    def dlg(self, qtbot):
        from XBrainLab.ui.dialogs.preprocess.epoching_dialog import EpochingDialog

        data_list = [MagicMock()]
        data_list[0].get_events_from_annotations.return_value = (
            {"left": 1, "right": 2},
            [],
        )
        data_list[0].get_event_list.return_value = (
            None,
            {"left": 1, "right": 2},
        )
        data_list[0].get_runtime_detail.return_value = {
            "source": "Labels inside EEG files",
            "placement_method": "internal_events",
            "class_map": {"left": "left", "right": "right"},
        }
        d = EpochingDialog(
            None,
            epoch_context=build_epoching_context(
                data_list,
                epoch_handoff={
                    "ready": True,
                    "supervised_ready": True,
                    "label_source": "internal_events",
                    "placement_modes": ["internal_events"],
                    "default_epoch_events": ["left", "right"],
                    "selected_event_names": ["left", "right"],
                },
            ),
        )
        qtbot.addWidget(d)
        return d

    def test_baseline_uses_right_aligned_on_off_toggle(self, dlg, qtbot):
        assert isinstance(dlg.baseline_check, QPushButton)
        assert dlg.baseline_check.objectName() == "PreprocessToggle"

        dlg.show()
        qtbot.wait(0)

        assert dlg.baseline_title_label is not None
        assert dlg.baseline_check.x() > dlg.baseline_title_label.x()
        assert dlg.baseline_check.text() in {"On", "Off"}
        assert dlg.baseline_check.accessibleName() == "Baseline correction"

    def test_disabled_baseline_retains_values_without_blocking_create(self, dlg):
        assert dlg.baseline_check is not None
        assert dlg.baseline_content is not None
        assert dlg.baseline_help_label is not None
        assert dlg.baseline_min_label is not None
        assert dlg.baseline_max_label is not None
        assert dlg.baseline_error_label is not None
        assert dlg.b_min_spin is not None
        assert dlg.b_max_spin is not None
        assert dlg.create_button is not None

        dlg.baseline_check.setChecked(True)
        dlg.b_min_spin.setValue(0.5)
        dlg.b_max_spin.setValue(0.2)

        retained_values = (dlg.b_min_spin.value(), dlg.b_max_spin.value())
        assert not dlg.create_button.isEnabled()
        assert dlg.baseline_error_label.isVisibleTo(dlg)

        dlg.baseline_check.setChecked(False)

        assert dlg.baseline_check.text() == "Off"
        assert not dlg.baseline_content.isEnabled()
        assert not dlg.baseline_help_label.isEnabled()
        assert not dlg.baseline_min_label.isEnabled()
        assert not dlg.baseline_max_label.isEnabled()
        assert not dlg.baseline_error_label.isEnabled()
        assert not dlg.b_min_spin.isEnabled()
        assert not dlg.b_max_spin.isEnabled()
        assert (dlg.b_min_spin.value(), dlg.b_max_spin.value()) == retained_values
        assert not dlg.baseline_error_label.isVisibleTo(dlg)
        assert dlg.create_button.isEnabled()

        dlg.baseline_check.setChecked(True)

        assert dlg.baseline_check.text() == "On"
        assert dlg.baseline_content.isEnabled()
        assert dlg.baseline_help_label.isEnabled()
        assert dlg.baseline_min_label.isEnabled()
        assert dlg.baseline_max_label.isEnabled()
        assert dlg.baseline_error_label.isEnabled()
        assert (dlg.b_min_spin.value(), dlg.b_max_spin.value()) == retained_values
        assert dlg.baseline_error_label.isVisibleTo(dlg)
        assert not dlg.create_button.isEnabled()

    def test_disabled_baseline_submits_none_through_create_button(self, dlg, qtbot):
        assert dlg.baseline_check is not None
        assert dlg.baseline_help_label is not None
        assert dlg.b_min_spin is not None
        assert dlg.b_max_spin is not None
        assert dlg.create_button is not None

        dlg.show()
        dlg.baseline_check.setChecked(True)
        dlg.b_min_spin.setValue(0.5)
        dlg.b_max_spin.setValue(0.2)
        assert not dlg.create_button.isEnabled()

        dlg.baseline_check.setChecked(False)
        assert dlg.create_button.isEnabled()
        assert dlg.baseline_help_label.text().startswith("When enabled,")

        with qtbot.waitSignal(dlg.accepted, timeout=1000):
            qtbot.mouseClick(dlg.create_button, Qt.MouseButton.LeftButton)

        params = dlg.get_params()
        assert params is not None
        baseline, selected_events, _t_min, _t_max = params
        assert baseline is None
        assert selected_events == ["left", "right"]

    def test_baseline_surface_matches_section_and_never_paints_black(self, dlg, qtbot):
        assert dlg.baseline_group is not None
        assert dlg.baseline_content is not None
        assert dlg.baseline_check is not None
        assert dlg.baseline_help_label is not None
        assert dlg.baseline_min_label is not None
        assert dlg.baseline_max_label is not None
        assert dlg.b_min_spin is not None
        assert dlg.b_max_spin is not None
        assert "QWidget#EpochBaselineContent:disabled" in dlg.styleSheet()
        assert (
            'QFrame#EpochBaselineSection[baselineEnabled="false"]' in dlg.styleSheet()
        )

        dlg.show()
        expected_surfaces = {
            True: (34, 36, 38),
            False: (32, 33, 36),
        }
        for enabled, expected_rgb in expected_surfaces.items():
            dlg.baseline_check.setChecked(enabled)
            dlg.repaint()
            qtbot.wait(0)
            sample = dlg.baseline_content.mapTo(
                dlg,
                QPoint(
                    max(dlg.baseline_content.width() - 6, 0),
                    max(dlg.baseline_content.height() - 6, 0),
                ),
            )
            color = dlg.grab().toImage().pixelColor(sample).getRgb()[:3]

            assert (
                max(
                    abs(actual - expected)
                    for actual, expected in zip(color, expected_rgb, strict=True)
                )
                <= 5
            )
            assert min(color) >= 24
            assert dlg.baseline_help_label.isVisibleTo(dlg)
            assert dlg.baseline_min_label.isVisibleTo(dlg)
            assert dlg.baseline_max_label.isVisibleTo(dlg)
            assert dlg.b_min_spin.isVisibleTo(dlg)
            assert dlg.b_max_spin.isVisibleTo(dlg)
            for label in (
                dlg.baseline_help_label,
                dlg.baseline_min_label,
                dlg.baseline_max_label,
            ):
                required_height = (
                    label.heightForWidth(label.width())
                    if label.wordWrap()
                    else label.fontMetrics().lineSpacing()
                )
                assert required_height <= label.contentsRect().height()

    def test_baseline_first_layer_does_not_restore_legacy_checkbox_copy(self):
        from inspect import getsource

        from XBrainLab.ui.dialogs.preprocess.epoching_dialog import EpochingDialog

        assert 'QCheckBox("Apply baseline correction")' not in getsource(
            EpochingDialog.init_ui
        )

    def test_label_backgrounds_are_transparent(self, dlg):
        assert "QLabel {" in dlg.styleSheet()
        assert "background-color: transparent" in dlg.styleSheet()

        labels_with_local_style = [
            label for label in dlg.findChildren(QLabel) if label.styleSheet().strip()
        ]
        assert labels_with_local_style
        assert all(
            "background-color: transparent" in label.styleSheet()
            for label in labels_with_local_style
        )

    def test_content_scrolls_above_fixed_footer(self, qtbot):
        from XBrainLab.ui.dialogs.preprocess.epoching_dialog import EpochingDialog

        dialog = EpochingDialog(
            None,
            epoch_context={
                "available_events": [
                    {"name": f"event_{index:02d}", "count": 20} for index in range(16)
                ],
                "has_import_hint": True,
                "source": "loaded label files",
                "placement_label": "Label interval",
                "label_field": "trial_type",
                "time_field": "onset",
                "duration_field": "duration",
                "window_evidence": (
                    "Suggested from imported event timing. Review this if the "
                    "dataset uses a different reference point."
                ),
            },
        )
        qtbot.addWidget(dialog)
        dialog.resize(620, 420)
        dialog.show()
        qtbot.wait(0)

        scroll = dialog.findChild(QScrollArea, "EpochDialogContentScroll")
        assert scroll is not None
        assert scroll.widgetResizable()
        assert (
            scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        assert scroll.isVisibleTo(dialog)

        footer = dialog.findChild(QDialogButtonBox)
        assert footer is not None
        assert footer.isVisibleTo(dialog)

    def test_import_handoff_preselects_epoch_targets(self, qtbot):
        from XBrainLab.ui.dialogs.preprocess.epoching_dialog import EpochingDialog

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
            "duration_stats": {"numeric_count": 0, "min": None, "max": None},
            "placement_event_count": 3,
            "unknown_duration_count": 3,
            "class_map": {"left": "Left hand", "right": "Right hand"},
        }
        handoff = {
            "ready": True,
            "supervised_ready": True,
            "default_epoch_events": ["Left hand", "Right hand"],
            "selected_event_names": ["Left hand", "Right hand"],
            "label_source": "bids_events",
            "placement_modes": ["interval"],
        }
        dialog = EpochingDialog(
            None,
            epoch_context=build_epoching_context([data], epoch_handoff=handoff),
        )
        qtbot.addWidget(dialog)

        assert dialog.event_list is not None
        assert dialog.handoff_label is None
        checked = [
            dialog.event_list.item(row, 1).text()
            for row in range(dialog.event_list.rowCount())
            if dialog.event_list.item(row, 0).checkState() == Qt.CheckState.Checked
        ]

        assert checked == ["Left hand", "Right hand"]
        assert not dialog.event_list.selectedItems()
        assert any(
            "BIDS events from import" in label.text()
            for label in dialog.findChildren(QLabel)
        )

    def test_epoch_event_table_exposes_applied_nonclass_event_catalog(self, qtbot):
        """The visible epoch surface must retain Apply's non-class semantics."""
        from XBrainLab.ui.dialogs.preprocess.epoching_dialog import EpochingDialog

        data = MagicMock()
        data.get_event_list.return_value = (None, {"left": 1, "right": 2})
        data.get_runtime_detail.return_value = {
            "source": "BIDS events.tsv",
            "placement_method": "interval",
            "label_field": "trial_type",
            "time_field": "onset",
        }
        handoff = {
            "ready": True,
            "supervised_ready": True,
            "default_epoch_events": ["left", "right"],
            "selected_event_names": ["left", "right"],
            "label_source": "bids_events",
            "placement_modes": ["interval"],
            "event_catalog": [
                {
                    "raw_value": "left",
                    "role": "stimulus",
                    "keep_event": True,
                    "use_as_class": True,
                    "class_name": "left",
                    "target_file": "sub-01_task-mi_events.tsv",
                },
                {
                    "raw_value": "right",
                    "role": "stimulus",
                    "keep_event": True,
                    "use_as_class": True,
                    "class_name": "right",
                    "target_file": "sub-01_task-mi_events.tsv",
                },
                {
                    "raw_value": "boundary",
                    "role": "boundary",
                    "keep_event": True,
                    "use_as_class": False,
                    "class_name": "",
                    "target_file": "sub-01_task-mi_events.tsv",
                },
            ],
        }
        dialog = EpochingDialog(
            None,
            epoch_context=build_epoching_context([data], epoch_handoff=handoff),
        )
        qtbot.addWidget(dialog)

        assert dialog.event_list is not None
        assert dialog.event_list.property("appliedEventCatalog") == [
            {
                "event_value": "boundary",
                "event_role": "boundary",
                "keep_event": True,
                "use_as_class": False,
                "class_name": "",
                "sources": ["sub-01_task-mi_events.tsv"],
            },
            {
                "event_value": "left",
                "event_role": "stimulus",
                "keep_event": True,
                "use_as_class": True,
                "class_name": "left",
                "sources": ["sub-01_task-mi_events.tsv"],
            },
            {
                "event_value": "right",
                "event_role": "stimulus",
                "keep_event": True,
                "use_as_class": True,
                "class_name": "right",
                "sources": ["sub-01_task-mi_events.tsv"],
            },
        ]

    def test_assistant_handoff_prefills_explicit_event_and_window(self, qtbot):
        from XBrainLab.ui.dialogs.preprocess.epoching_dialog import EpochingDialog

        data = MagicMock()
        data.get_event_list.return_value = (
            None,
            {"768": 1, "769": 2, "770": 3},
        )
        dialog = EpochingDialog(
            None,
            epoch_context=build_epoching_context([data]),
            assistant_suggestions={
                "target_event": "769",
                "t_min": "-0.2",
                "t_max": "0.8",
            },
        )
        qtbot.addWidget(dialog)

        checked = [
            dialog.event_list.item(row, 1).text()
            for row in range(dialog.event_list.rowCount())
            if dialog.event_list.item(row, 0).checkState() == Qt.CheckState.Checked
        ]
        assert checked == ["769"]
        assert dialog.tmin_spin.value() == pytest.approx(-0.2)
        assert dialog.tmax_spin.value() == pytest.approx(0.8)

    def test_bids_epoch_dialog_surfaces_duration_policy(self, qtbot):
        from XBrainLab.ui.dialogs.preprocess.epoching_dialog import EpochingDialog

        data = MagicMock()
        data.get_event_list.return_value = (
            None,
            {"left": 1, "right": 2},
        )
        data.get_runtime_detail.return_value = {
            "source": "BIDS events.tsv",
            "placement_method": "interval",
            "label_field": "trial_type",
            "time_field": "onset",
            "duration_field": "duration",
            "duration_stats": {"numeric_count": 3, "min": 0.25, "max": 12.0},
            "placement_event_count": 3,
            "unknown_duration_count": 0,
            "class_map": {"left": "left", "right": "right"},
        }

        dialog = EpochingDialog(
            None,
            epoch_context=build_epoching_context(
                [data],
                epoch_handoff={
                    "ready": True,
                    "supervised_ready": True,
                    "label_source": "bids_events",
                    "placement_modes": ["interval"],
                    "default_epoch_events": ["left", "right"],
                    "selected_event_names": ["left", "right"],
                },
            ),
        )
        qtbot.addWidget(dialog)
        dialog.show()
        qtbot.wait(0)

        labels_text = "\n".join(
            label.text()
            for label in dialog.findChildren(QLabel)
            if label.text().strip()
        )

        assert "BIDS events from import" in labels_text
        assert "BIDS events confirmed in Match Labels" not in labels_text
        assert "Use one fixed window" in labels_text
        assert "Review event durations and the selected window." in labels_text
        assert dialog.tmin_spin.value() == 0.0
        assert dialog.tmax_spin.value() == 12.0
        assert not dialog.baseline_check.isChecked()

    def test_import_handoff_uses_checked_events_not_stale_selection(self, qtbot):
        from XBrainLab.ui.dialogs.preprocess.epoching_dialog import EpochingDialog

        data = MagicMock()
        data.get_event_list.return_value = (
            None,
            {"Left hand": 1, "Right hand": 2},
        )
        data.get_runtime_detail.return_value = {
            "source": "BIDS events.tsv",
            "placement_method": "interval",
            "label_field": "trial_type",
            "time_field": "onset",
            "duration_field": "duration",
            "duration_stats": {"numeric_count": 0, "min": None, "max": None},
            "placement_event_count": 2,
            "unknown_duration_count": 2,
            "class_map": {"left": "Left hand", "right": "Right hand"},
        }
        handoff = {
            "ready": True,
            "supervised_ready": True,
            "default_epoch_events": ["Left hand", "Right hand"],
            "selected_event_names": ["Left hand", "Right hand"],
            "label_source": "bids_events",
            "placement_modes": ["interval"],
        }
        dialog = EpochingDialog(
            None,
            epoch_context=build_epoching_context([data], epoch_handoff=handoff),
        )
        qtbot.addWidget(dialog)

        assert dialog.event_list is not None
        for row in range(dialog.event_list.rowCount()):
            dialog.event_list.item(row, 0).setCheckState(Qt.CheckState.Unchecked)

        with patch(
            "XBrainLab.ui.dialogs.preprocess.epoching_dialog.show_warning"
        ) as warning:
            dialog.accept()

        warning.assert_called_once()
        assert dialog.get_params() is None

    def test_rejects_baseline_outside_epoch_window(self, qtbot):
        from XBrainLab.ui.dialogs.preprocess.epoching_dialog import EpochingDialog

        data = MagicMock()
        data.get_event_list.return_value = (
            None,
            {"Left hand": 1},
        )
        dialog = EpochingDialog(
            None,
            epoch_context=build_epoching_context([data]),
        )
        qtbot.addWidget(dialog)

        assert dialog.event_list is not None
        dialog.event_list.item(0, 0).setCheckState(Qt.CheckState.Checked)
        dialog.tmin_spin.setValue(0.0)
        dialog.tmax_spin.setValue(1.0)
        dialog.baseline_check.setChecked(True)
        dialog.b_min_spin.setValue(-0.2)
        dialog.b_max_spin.setValue(0.0)

        with patch(
            "XBrainLab.ui.dialogs.preprocess.epoching_dialog.show_warning"
        ) as warning:
            dialog.accept()

        warning.assert_called_once()
        assert dialog.get_params() is None

    def test_import_handoff_blockers_override_epoch_defaults(self, qtbot):
        from XBrainLab.ui.dialogs.preprocess.epoching_dialog import EpochingDialog

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
            "duration_stats": {"numeric_count": 0, "min": None, "max": None},
            "placement_event_count": 3,
            "unknown_duration_count": 3,
            "class_map": {"left": "Left hand", "right": "Right hand"},
        }
        handoff = {
            "ready": False,
            "supervised_ready": False,
            "default_epoch_events": ["Left hand", "Right hand"],
            "selected_event_names": ["Left hand", "Right hand"],
            "supervised_blockers": ["No class labels were reviewed."],
            "label_source": "bids_events",
            "placement_modes": ["interval"],
        }
        dialog = EpochingDialog(
            None,
            epoch_context=build_epoching_context([data], epoch_handoff=handoff),
        )
        qtbot.addWidget(dialog)

        assert dialog.event_list is not None
        assert dialog.handoff_label is not None
        selected = [item.text() for item in dialog.event_list.selectedItems()]

        assert selected == []
        assert "needs review" in dialog.handoff_label.text()
        assert "No class labels" in dialog.handoff_label.text()
