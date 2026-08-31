from typing import cast
from unittest.mock import MagicMock, patch

import pytest
import torch
from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QScrollArea,
    QWidget,
)

from XBrainLab.backend.application.resource_guard import (
    RISK_UNKNOWN,
    RISK_WARNING,
    TrainingResourcePreviewReceipt,
    TrainingResourcePreviewRequest,
    TrainingResourcePreviewResult,
)
from XBrainLab.backend.application.training_recommendation import (
    TrainingRecommendation,
    TrainingRecommendationField,
    TrainingRecommendationValues,
    TrainingSettingProvenance,
)
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import TrainingEvaluation
from XBrainLab.backend.training.utils import (
    get_optimizer_classes,
    instantiate_optimizer,
)
from XBrainLab.ui.dialogs.training import (
    DeviceSettingDialog,
    OptimizerSettingDialog,
    TrainingSettingDialog,
)


class _StudyWidget(QWidget):
    study: Study


def _recommendation(
    fingerprint: str,
    *,
    epochs: int,
    batch_size: int,
    learning_rate: float,
    optimizer: str = "Adam",
    evaluation_strategy: str = "Best validation loss",
) -> TrainingRecommendation:
    values = TrainingRecommendationValues(
        epochs=epochs,
        batch_size=batch_size,
        learning_rate=learning_rate,
        optimizer=optimizer,
        evaluation_strategy=evaluation_strategy,
    )
    return TrainingRecommendation(
        context_fingerprint=fingerprint,
        recommended_values=values,
        values=values,
        provenance={
            field.value: TrainingSettingProvenance.RECOMMENDED
            for field in TrainingRecommendationField
        },
        reasons=(),
        warnings=(
            "These values are a conservative starting point, not a claim of best "
            "parameters.",
        ),
    )


class TestTrainingSetting:
    def test_uses_four_category_sections_and_inline_validation_state(self, qtbot):
        dialog = TrainingSettingDialog(
            None,
            None,
            initial_option={"validation_samples_available": False},
        )
        qtbot.addWidget(dialog)

        section_titles = {
            label.text()
            for label in dialog.findChildren(QLabel, "TrainingSettingSectionHeader")
        }
        text = {label.text() for label in dialog.findChildren(QLabel)}

        assert "Training Settings" in text
        assert (
            "Configure training, validation, runtime, and output preferences."
        ) in text
        assert {
            "Training Run",
            "Optimization",
            "Validation & Checkpoints",
            "Runtime & Output",
        } <= section_titles
        assert (
            "Close this dialog and configure a validation split in Data Splitting "
            "to enable early stopping."
        ) in text

        validation_layout = dialog.section_layouts["Validation & Checkpoints"]
        validation_labels = [
            cast(QLabel, validation_layout.itemAtPosition(row, 0).widget()).text()
            for row in range(5)
        ]
        assert validation_labels == [
            "Evaluation",
            "Early stopping",
            "Patience",
            "Minimum improvement",
            "Checkpoint interval (training epochs)",
        ]

        runtime_layout = dialog.section_layouts["Runtime & Output"]
        runtime_labels = [
            cast(QLabel, runtime_layout.itemAtPosition(row, 0).widget()).text()
            for row in range(3)
        ]
        assert runtime_labels == ["Batch size", "Device", "Output directory"]
        assert dialog.resource_preview_note is not None
        assert (
            runtime_layout.itemAtPosition(3, 0).widget() is dialog.resource_preview_note
        )
        section_cards = dialog.findChildren(QFrame, "TrainingSettingSectionCard")
        assert len(section_cards) == 4
        assert all(
            "QFrame#TrainingSettingSectionCard" in card.styleSheet()
            and "QFrame {" not in card.styleSheet()
            for card in section_cards
        )

    def test_early_stopping_is_disabled_without_validation_samples(self, qtbot):
        dialog = TrainingSettingDialog(
            None,
            None,
            initial_option={"validation_samples_available": False},
        )
        qtbot.addWidget(dialog)

        assert dialog.early_stopping_check is not None
        assert dialog.early_stopping_check.isEnabled() is False
        assert dialog.early_stopping_patience_entry is not None
        assert dialog.early_stopping_patience_entry.isEnabled() is False

    @pytest.fixture
    def window(self, qtbot):
        mock_controller = MagicMock()
        # Ensure get_training_option returns None so load_settings is skipped
        mock_controller.get_training_option.return_value = None

        # Use actual torch.optim.Adam
        with patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog.get_optimizer_classes"
        ) as mock_get_classes:
            mock_get_classes.return_value = {"Adam": torch.optim.Adam}

            window = TrainingSettingDialog(None, mock_controller)
            qtbot.addWidget(window)
            yield window

    def test_init(self, window):
        assert window.windowTitle() == "Training Settings"
        # Verify default values are set
        assert window.epoch_entry.text() == "10"
        assert window.bs_entry.text() == "32"
        assert window.lr_entry.text() == "0.001"
        assert window.checkpoint_entry.text() == "0"
        assert window.repeat_entry.text() == "1"
        assert window.output_dir == "./output/runs"
        assert window.optim == torch.optim.Adam  # Real Adam class
        assert window.opt_label.text() == "Adam"
        assert window.use_cpu is True
        assert window.get_device_value() == "auto"
        assert window.dev_label.text() == "Auto"
        assert window.evaluation_combo.currentText() == "Validation loss"
        assert window.evaluation_combo.currentData() is TrainingEvaluation.VAL_LOSS
        assert all(
            "testing" not in window.evaluation_combo.itemText(index).lower()
            for index in range(window.evaluation_combo.count())
        )

    def test_ok_cancel_buttons_have_no_icons(self, window):
        buttons = window.findChild(QDialogButtonBox)
        assert buttons is not None
        for standard in (
            QDialogButtonBox.StandardButton.Ok,
            QDialogButtonBox.StandardButton.Cancel,
        ):
            button = buttons.button(standard)
            assert button is not None
            assert button.icon().isNull()

    def test_footer_renders_cancel_left_and_ok_rightmost(self, window, qtbot):
        window.show()
        qtbot.waitUntil(lambda: window.isVisible())

        buttons = window.findChild(QDialogButtonBox)
        assert buttons is not None
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        assert ok_button is not None
        assert cancel_button is not None

        assert buttons.layoutDirection() is Qt.LayoutDirection.LeftToRight
        assert cancel_button.geometry().right() < ok_button.geometry().left()
        dialog_layout = window.layout()
        assert dialog_layout is not None
        footer = dialog_layout.itemAt(dialog_layout.count() - 1).layout()
        assert footer is not None
        assert buttons.geometry().right() == (
            window.contentsRect().right() - footer.contentsMargins().right()
        )

    @pytest.mark.parametrize("font_scale", [1.0, 1.25, 1.5])
    def test_training_setting_labels_fit_at_supported_font_scales(
        self,
        window,
        qtbot,
        font_scale,
    ):
        app = QApplication.instance()
        assert isinstance(app, QApplication)
        original_font = QFont(app.font())
        scaled_font = QFont(original_font)
        scaled_font.setPointSizeF(original_font.pointSizeF() * font_scale)
        app.setFont(scaled_font)
        try:
            window.adjustSize()
            window.show()
            qtbot.wait(0)
            checkpoint_label = next(
                label
                for label in window.findChildren(QLabel)
                if label.text() == "Checkpoint interval (training epochs)"
            )

            if (
                checkpoint_label.fontMetrics().horizontalAdvance(
                    checkpoint_label.text()
                )
                > checkpoint_label.width()
            ):
                assert checkpoint_label.wordWrap()
                assert checkpoint_label.height() >= (
                    checkpoint_label.fontMetrics().lineSpacing() * 2
                )
            assert window.contentsRect().contains(checkpoint_label.geometry())
        finally:
            app.setFont(original_font)

    def test_training_setting_constructed_at_150_percent_keeps_labels_visible(
        self,
        qtbot,
    ):
        app = QApplication.instance()
        assert isinstance(app, QApplication)
        original_font = QFont(app.font())
        scaled_font = QFont(original_font)
        scaled_font.setPointSizeF(original_font.pointSizeF() * 1.5)
        app.setFont(scaled_font)
        controller = MagicMock()
        controller.get_training_option.return_value = None
        try:
            with patch(
                "XBrainLab.ui.dialogs.training.training_setting_dialog."
                "get_optimizer_classes",
                return_value={"Adam": torch.optim.Adam},
            ):
                dialog = TrainingSettingDialog(None, controller)
                qtbot.addWidget(dialog)
                dialog.show()
                qtbot.wait(0)

            checkpoint_label = next(
                label
                for label in dialog.findChildren(QLabel)
                if label.text() == "Checkpoint interval (training epochs)"
            )
            if (
                checkpoint_label.fontMetrics().horizontalAdvance(
                    checkpoint_label.text()
                )
                > checkpoint_label.width()
            ):
                assert checkpoint_label.wordWrap()
                assert checkpoint_label.height() >= (
                    checkpoint_label.fontMetrics().lineSpacing() * 2
                )
            assert dialog.contentsRect().contains(checkpoint_label.geometry())
            assert checkpoint_label.geometry().right() < (
                dialog.checkpoint_entry.geometry().left()
            )
            assert dialog.content_scroll is not None
            viewport = dialog.content_scroll.viewport()
            for button in (dialog.opt_btn, dialog.dev_btn, dialog.out_btn):
                dialog.content_scroll.ensureWidgetVisible(button)
                qtbot.wait(0)
                bounds = QRect(button.mapTo(viewport, QPoint(0, 0)), button.size())
                assert viewport.rect().contains(bounds)
                assert button.visibleRegion().contains(button.rect())
        finally:
            app.setFont(original_font)

    def test_training_setting_footer_stays_reachable_on_720p_at_150_percent(
        self,
        qtbot,
    ):
        app = QApplication.instance()
        assert isinstance(app, QApplication)
        original_font = QFont(app.font())
        scaled_font = QFont(original_font)
        scaled_font.setPointSizeF(original_font.pointSizeF() * 1.5)
        app.setFont(scaled_font)
        controller = MagicMock()
        controller.get_training_option.return_value = None
        recommendation = _recommendation(
            "compact-training-dialog",
            epochs=20,
            batch_size=16,
            learning_rate=0.0005,
        )
        try:
            with patch(
                "XBrainLab.ui.dialogs.training.training_setting_dialog."
                "get_optimizer_classes",
                return_value={"Adam": torch.optim.Adam},
            ):
                dialog = TrainingSettingDialog(
                    None,
                    controller,
                    recommendation=recommendation,
                )
                qtbot.addWidget(dialog)

            # 720 physical pixels at 150% scaling leaves about 480 logical pixels.
            dialog.resize(QSize(640, 480))
            dialog.show()
            qtbot.wait(0)

            content_scroll = dialog.findChild(
                QScrollArea,
                "TrainingSettingContentScroll",
            )
            buttons = dialog.findChild(QDialogButtonBox)
            assert content_scroll is not None
            assert buttons is not None
            assert content_scroll.verticalScrollBar().maximum() > 0
            button_bounds = QRect(buttons.mapTo(dialog, QPoint(0, 0)), buttons.size())
            assert dialog.rect().contains(button_bounds)
            assert buttons.visibleRegion().contains(buttons.rect())

            content_scroll.verticalScrollBar().setValue(
                content_scroll.verticalScrollBar().maximum()
            )
            assert dialog.repeat_entry is not None
            assert dialog.repeat_entry.isVisibleTo(content_scroll.viewport())
        finally:
            app.setFont(original_font)

    def test_set_values_and_confirm(self, window):
        # Set simple values
        window.epoch_entry.setText("10")
        window.bs_entry.setText("32")
        window.lr_entry.setText("0.001")
        window.checkpoint_entry.setText("5")
        window.repeat_entry.setText("1")

        # Mock Optimizer and Device setting (since they open dialogs)
        window.optim = torch.optim.Adam
        window.optim_params = {}  # lr is separate parameter
        window.use_cpu = True
        window.gpu_idx = None
        window.output_dir = "/mock/output"

        # Select Evaluation
        window.evaluation_combo.setCurrentIndex(0)

        # Confirm
        with patch("PyQt6.QtWidgets.QDialog.accept") as mock_accept:
            window.accept()
            mock_accept.assert_called_once()

        # Verify result
        option = window.get_result()
        assert option.epoch == 10
        assert option.bs == 32
        assert option.lr == 0.001
        assert option.output_dir == "/mock/output"
        assert option.use_cpu is True

    def test_initial_snapshot_restores_evaluation_selection(self, qtbot):
        controller = MagicMock()
        controller.get_training_option.return_value = None
        snapshot = {
            "epoch": 10,
            "batch_size": 32,
            "learning_rate": 0.001,
            "repeat": 1,
            "device": "cpu",
            "optimizer": "Adam",
            "optimizer_params": {},
            "checkpoint_epoch": 0,
            "output_dir": "./output",
            "evaluation_option": "Best validation performance",
        }
        with patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog.get_optimizer_classes",
            return_value={"Adam": torch.optim.Adam},
        ):
            dialog = TrainingSettingDialog(None, controller, initial_option=snapshot)
            qtbot.addWidget(dialog)

        assert dialog.evaluation_combo.currentText() == "Validation accuracy"
        assert dialog.evaluation_combo.currentData() is TrainingEvaluation.VAL_ACC

    def test_class_weight_multiplier_rows_only_show_for_custom_and_restore_values(
        self,
        qtbot,
    ):
        controller = MagicMock()
        controller.get_training_option.return_value = None
        snapshot = {
            "class_weight_mode": "custom",
            "custom_class_weights": {"left": 2.5, "right": 0.5},
            "class_map": {0: "left", 1: "right"},
            "class_map_fingerprint": "a" * 64,
        }
        with patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog.get_optimizer_classes",
            return_value={"Adam": torch.optim.Adam},
        ):
            dialog = TrainingSettingDialog(None, controller, initial_option=snapshot)
            qtbot.addWidget(dialog)
        dialog.resize(QSize(520, 390))
        dialog.show()
        qtbot.wait(0)

        assert dialog.class_weight_combo.currentData() == "custom"
        assert dialog.class_weight_entries["left"].text() == "2.5"
        assert not dialog.class_weight_entries["left"].isHidden()

        for mode in ("off", "balanced"):
            dialog.class_weight_combo.setCurrentIndex(
                dialog.class_weight_combo.findData(mode)
            )
            assert all(
                entry.isHidden() for entry in dialog.class_weight_entries.values()
            )

        dialog.class_weight_combo.setCurrentIndex(
            dialog.class_weight_combo.findData("custom")
        )
        assert all(
            not entry.isHidden() for entry in dialog.class_weight_entries.values()
        )
        assert dialog.class_weight_entries["left"].text() == "2.5"
        dialog.content_scroll.ensureWidgetVisible(dialog.class_weight_combo)
        qtbot.wait(0)
        assert dialog.class_weight_combo.visibleRegion().contains(
            dialog.class_weight_combo.rect()
        )
        with patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog.show_warning"
        ) as warning:
            dialog.accept()

        warning.assert_not_called()
        result = dialog.get_result()
        assert result is not None
        assert result.custom_class_weights == {"left": 2.5, "right": 0.5}

    @pytest.mark.parametrize("mode", ("off", "balanced"))
    def test_non_custom_weighting_ignores_stale_invalid_custom_input(
        self,
        qtbot,
        mode,
    ):
        controller = MagicMock()
        controller.get_training_option.return_value = None
        snapshot = {
            "class_map": {0: "left", 1: "right"},
            "class_map_fingerprint": "a" * 64,
        }
        with patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog.get_optimizer_classes",
            return_value={"Adam": torch.optim.Adam},
        ):
            dialog = TrainingSettingDialog(None, controller, initial_option=snapshot)
            qtbot.addWidget(dialog)

        dialog.class_weight_combo.setCurrentIndex(
            dialog.class_weight_combo.findData(mode)
        )
        dialog.class_weight_entries["left"].setText("not-a-number")

        with patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog.show_warning"
        ) as warning:
            dialog.accept()

        warning.assert_not_called()
        result = dialog.get_result()
        assert result is not None
        assert result.custom_class_weights == {}

    def test_custom_weight_invalid_value_is_blocked_before_accept(self, qtbot):
        controller = MagicMock()
        controller.get_training_option.return_value = None
        snapshot = {
            "class_weight_mode": "custom",
            "class_map": {0: "left", 1: "right"},
            "class_map_fingerprint": "a" * 64,
        }
        with patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog.get_optimizer_classes",
            return_value={"Adam": torch.optim.Adam},
        ):
            dialog = TrainingSettingDialog(None, controller, initial_option=snapshot)
            qtbot.addWidget(dialog)
        dialog.class_weight_entries["left"].setText("0")

        with patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog.show_warning"
        ) as warning:
            dialog.accept()

        warning.assert_called_once()
        assert dialog.get_result() is None

    def test_backend_recommendation_prefills_only_recommended_fields(self, qtbot):
        controller = MagicMock()
        controller.get_training_option.return_value = None
        snapshot = {
            "repeat": 3,
            "device": "cpu",
            "checkpoint_epoch": 7,
            "output_dir": "/existing/output",
        }
        recommendation = _recommendation(
            "compact-context",
            epochs=50,
            batch_size=64,
            learning_rate=0.001,
            optimizer="AdamW",
            evaluation_strategy="Best validation performance",
        )
        with patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog."
            "get_optimizer_classes",
            return_value={
                "Adam": torch.optim.Adam,
                "AdamW": torch.optim.AdamW,
            },
        ):
            dialog = TrainingSettingDialog(
                None,
                controller,
                initial_option=snapshot,
                recommendation=recommendation,
            )
            qtbot.addWidget(dialog)

        assert dialog.epoch_entry.text() == "50"
        assert dialog.bs_entry.text() == "64"
        assert dialog.lr_entry.text() == "0.001"
        assert dialog.optim is torch.optim.AdamW
        assert dialog.evaluation_combo.currentData() is TrainingEvaluation.VAL_ACC
        assert dialog.use_cpu is True
        assert dialog.output_dir == "/existing/output"
        assert dialog.checkpoint_entry.text() == "7"
        assert dialog.repeat_entry.text() == "3"

    def test_recommended_optimizer_switch_resets_incompatible_params_and_instantiates(
        self,
        qtbot,
    ):
        controller = MagicMock()
        controller.get_training_option.return_value = None
        recommendation = _recommendation(
            "optimizer-context",
            epochs=50,
            batch_size=32,
            learning_rate=0.001,
            optimizer="AdamW",
        )
        snapshot = {
            "optimizer": "SGD",
            "optimizer_params": {"momentum": 0.9},
        }

        with patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog."
            "get_optimizer_classes",
            return_value={
                "Adam": torch.optim.Adam,
                "AdamW": torch.optim.AdamW,
                "SGD": torch.optim.SGD,
            },
        ):
            dialog = TrainingSettingDialog(
                None,
                controller,
                initial_option=snapshot,
                recommendation=recommendation,
            )
            qtbot.addWidget(dialog)

        assert dialog.optim is torch.optim.AdamW
        assert dialog.optim_params == {}
        assert dialog.opt_label.text() == "AdamW"

        with patch("PyQt6.QtWidgets.QDialog.accept"):
            dialog.accept()

        option = dialog.get_result()
        assert option is not None
        optimizer = instantiate_optimizer(
            option.optim,
            option.optim_params,
            lr=option.lr,
        )
        assert isinstance(optimizer, torch.optim.AdamW)

        dialog.apply_proposed_values({"optimizer": "SGD"})

        assert dialog.optim is torch.optim.SGD
        assert dialog.optim_params == {}
        assert TrainingRecommendationField.OPTIMIZER in (
            dialog.get_edited_recommendation_fields()
        )

    def test_device_change_refreshes_untouched_recommendation_fields(
        self,
        qtbot,
    ):
        controller = MagicMock()
        controller.get_training_option.return_value = None
        initial = _recommendation(
            "auto-device-context",
            epochs=50,
            batch_size=8,
            learning_rate=0.001,
        )
        cpu = _recommendation(
            "cpu-device-context",
            epochs=50,
            batch_size=32,
            learning_rate=0.001,
        )
        recommendation_provider = MagicMock(return_value=cpu)

        with patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog."
            "get_optimizer_classes",
            return_value={"Adam": torch.optim.Adam},
        ):
            dialog = TrainingSettingDialog(
                None,
                controller,
                recommendation=initial,
                device_recommendation_provider=recommendation_provider,
            )
            qtbot.addWidget(dialog)

        dialog.epoch_entry.setText("61")
        dialog.epoch_entry.textEdited.emit("61")
        with patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog.DeviceSettingDialog"
        ) as device_dialog:
            device_dialog.return_value.exec.return_value = True
            device_dialog.return_value.get_result.return_value = (True, None)
            dialog.set_device()

        recommendation_provider.assert_called_once_with("cpu")
        assert dialog.get_device_value() == "cpu"
        assert dialog.epoch_entry.text() == "61"
        assert dialog.bs_entry.text() == "32"
        assert dialog.get_recommendation().context_fingerprint == "cpu-device-context"
        assert dialog.get_recommendation().provenance["batch_size"] is (
            TrainingSettingProvenance.RECOMMENDED
        )
        assert dialog.get_edited_recommendation_fields() == frozenset(
            {TrainingRecommendationField.EPOCHS}
        )

        with patch("PyQt6.QtWidgets.QDialog.accept"):
            dialog.accept()

        option = dialog.get_result()
        assert option is not None
        assert option.epoch == 61
        assert option.bs == 32
        assert option.use_cpu is True

    def test_preloaded_proposed_device_still_refreshes_recommendation(
        self,
        qtbot,
    ):
        initial = _recommendation(
            "auto-device-context",
            epochs=50,
            batch_size=8,
            learning_rate=0.001,
        )
        cpu = _recommendation(
            "cpu-device-context",
            epochs=50,
            batch_size=32,
            learning_rate=0.001,
        )
        recommendation_provider = MagicMock(return_value=cpu)

        with patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog."
            "get_optimizer_classes",
            return_value={"Adam": torch.optim.Adam},
        ):
            dialog = TrainingSettingDialog(
                None,
                None,
                initial_option={"device": "cpu"},
                recommendation=initial,
                proposed_values={"device": "cpu"},
                device_recommendation_provider=recommendation_provider,
            )
            qtbot.addWidget(dialog)

        recommendation_provider.assert_called_once_with("cpu")
        assert dialog.bs_entry.text() == "32"
        assert dialog.get_recommendation().provenance["batch_size"] is (
            TrainingSettingProvenance.RECOMMENDED
        )

    def test_tracks_only_actual_and_explicit_recommendation_edits(self, qtbot):
        controller = MagicMock()
        controller.get_training_option.return_value = None
        recommendation = _recommendation(
            "edited-fields-context",
            epochs=50,
            batch_size=32,
            learning_rate=0.001,
        )
        with patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog."
            "get_optimizer_classes",
            return_value={"Adam": torch.optim.Adam},
        ):
            dialog = TrainingSettingDialog(
                None,
                controller,
                recommendation=recommendation,
                proposed_values={"learning_rate": "0.002"},
            )
            qtbot.addWidget(dialog)

        dialog.epoch_entry.setText("61")
        assert dialog.get_edited_recommendation_fields() == frozenset(
            {TrainingRecommendationField.LEARNING_RATE}
        )

        dialog.epoch_entry.textEdited.emit("61")
        assert dialog.get_edited_recommendation_fields() == frozenset(
            {
                TrainingRecommendationField.EPOCHS,
                TrainingRecommendationField.LEARNING_RATE,
            }
        )

    def test_context_refresh_preserves_explicit_edit_at_recommended_value(
        self,
        qtbot,
    ):
        controller = MagicMock()
        controller.get_training_option.return_value = None
        initial = _recommendation(
            "compact-context",
            epochs=50,
            batch_size=64,
            learning_rate=0.001,
        )
        with patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog."
            "get_optimizer_classes",
            return_value={"Adam": torch.optim.Adam, "AdamW": torch.optim.AdamW},
        ):
            dialog = TrainingSettingDialog(
                None,
                controller,
                recommendation=initial,
            )
            qtbot.addWidget(dialog)

        dialog.bs_entry.setText("12")
        dialog.bs_entry.textEdited.emit("12")
        attention = _recommendation(
            "attention-context",
            epochs=75,
            batch_size=16,
            learning_rate=0.0003,
            optimizer="AdamW",
        )

        dialog.apply_recommendation(attention)

        assert dialog.epoch_entry.text() == "75"
        assert dialog.bs_entry.text() == "12"
        assert dialog.lr_entry.text() == "0.0003"
        assert dialog.optim is torch.optim.AdamW
        assert dialog.get_recommendation().manual_fields == (
            TrainingRecommendationField.BATCH_SIZE,
        )

        dialog.bs_entry.setText("16")
        dialog.bs_entry.textEdited.emit("16")
        high_dimensional = _recommendation(
            "high-dimensional-context",
            epochs=75,
            batch_size=8,
            learning_rate=0.0003,
            optimizer="AdamW",
        )
        dialog.apply_recommendation(high_dimensional)

        assert dialog.bs_entry.text() == "16"
        assert dialog.get_recommendation().manual_fields == (
            TrainingRecommendationField.BATCH_SIZE,
        )
        assert dialog.get_edited_recommendation_fields() == frozenset(
            {TrainingRecommendationField.BATCH_SIZE}
        )

    def test_recommendation_provenance_remains_without_first_layer_note(self, qtbot):
        controller = MagicMock()
        controller.get_training_option.return_value = None
        recommendation = _recommendation(
            "note-context",
            epochs=50,
            batch_size=32,
            learning_rate=0.001,
        )
        with patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog."
            "get_optimizer_classes",
            return_value={"Adam": torch.optim.Adam},
        ):
            dialog = TrainingSettingDialog(
                None,
                controller,
                recommendation=recommendation,
            )
            qtbot.addWidget(dialog)

        assert dialog.recommendation_note is None
        assert dialog.findChild(QLabel, "TrainingRecommendationNote") is None

        dialog.epoch_entry.textEdited.emit("50")

        assert dialog.get_recommendation().provenance["epochs"] is (
            TrainingSettingProvenance.MANUAL
        )

    def test_resource_preview_reduces_only_an_untouched_batch(self, qtbot):
        request = TrainingResourcePreviewRequest(
            request_generation=0,
            publication_generation=22,
            model_name="EEGNet",
            model_params={},
            device="cuda:0",
            batch_size=32,
            optimizer="Adam",
        )
        with patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog."
            "get_optimizer_classes",
            return_value={"Adam": torch.optim.Adam},
        ):
            dialog = TrainingSettingDialog(
                None,
                None,
                recommendation=_recommendation(
                    "preview-context",
                    epochs=40,
                    batch_size=32,
                    learning_rate=0.001,
                ),
                resource_preview_request=request,
            )
            qtbot.addWidget(dialog)

        current = dialog.build_training_resource_preview_request()
        assert current is not None
        receipt = TrainingResourcePreviewReceipt(
            token="accepted-preview",  # noqa: S106 - opaque test receipt, not a secret
            request_generation=current.request_generation,
            publication_generation=22,
            requested_batch_size=32,
            suggested_batch_size=8,
        )
        applied = dialog.apply_training_resource_preview(
            TrainingResourcePreviewResult(
                request_generation=current.request_generation,
                publication_generation=22,
                requested_batch_size=32,
                suggested_batch_size=8,
                estimated_vram_bytes=128 * 1024**2,
                available_vram_bytes=512 * 1024**2,
                risk_level=RISK_WARNING,
                vram_known=True,
                warning=None,
                receipt=receipt,
            )
        )

        assert applied is True
        assert dialog.bs_entry.text() == "8"
        assert dialog.resource_preview_note is not None
        assert "adjusted to 8" in dialog.resource_preview_note.text()
        assert dialog.resource_preview_note.isHidden() is False
        dialog.show()
        QApplication.processEvents()
        viewport = dialog.content_scroll.viewport()
        note_top_left = dialog.resource_preview_note.mapTo(viewport, QPoint(0, 0))
        note_rect = QRect(note_top_left, dialog.resource_preview_note.size())
        assert viewport.rect().contains(note_rect) is False
        assert TrainingRecommendationField.BATCH_SIZE not in (
            dialog.get_edited_recommendation_fields()
        )
        assert dialog.get_applied_resource_preview_receipt() == receipt

        dialog.bs_entry.textEdited.emit("8")

        assert dialog.get_applied_resource_preview_receipt() is None

    @pytest.mark.parametrize("font_scale", [1.0, 1.25, 1.5])
    def test_async_resource_preview_preserves_current_scroll_position(
        self,
        qtbot,
        font_scale,
    ):
        app = QApplication.instance()
        assert isinstance(app, QApplication)
        original_font = QFont(app.font())
        scaled_font = QFont(original_font)
        scaled_font.setPointSizeF(original_font.pointSizeF() * font_scale)
        app.setFont(scaled_font)
        dispatched = []
        request_template = TrainingResourcePreviewRequest(
            request_generation=0,
            publication_generation=27,
            model_name="EEGNet",
            model_params={},
            device="cuda:0",
            batch_size=32,
            optimizer="Adam",
        )
        try:
            with patch(
                "XBrainLab.ui.dialogs.training.training_setting_dialog."
                "get_optimizer_classes",
                return_value={"Adam": torch.optim.Adam},
            ):
                dialog = TrainingSettingDialog(
                    None,
                    None,
                    initial_option={"device": "cuda:0", "batch_size": 32},
                    resource_preview_request=request_template,
                    resource_preview_dispatcher=(
                        lambda request, callback: dispatched.append((request, callback))
                    ),
                )
                qtbot.addWidget(dialog)

            dialog.setMaximumHeight(480)
            dialog.resize(QSize(640, 480))
            dialog.show()
            qtbot.waitUntil(lambda: len(dispatched) == 1)

            assert dialog.bs_entry is not None
            assert dialog.resource_preview_note is not None
            assert dialog.content_scroll is not None
            assert dialog.bs_entry.text() == "32"
            assert dialog.resource_preview_note.isHidden()

            scroll_bar = dialog.content_scroll.verticalScrollBar()
            assert scroll_bar.maximum() > 0
            scroll_bar.setValue(0)
            request, callback = dispatched[0]
            result = TrainingResourcePreviewResult(
                request_generation=request.request_generation,
                publication_generation=request.publication_generation,
                requested_batch_size=32,
                suggested_batch_size=8,
                estimated_vram_bytes=128 * 1024**2,
                available_vram_bytes=512 * 1024**2,
                risk_level=RISK_WARNING,
                vram_known=True,
                warning=("Batch size was adjusted to 8 for the available GPU memory."),
            )
            assert callback(result) is True

            viewport = dialog.content_scroll.viewport()
            note_rect = QRect(
                dialog.resource_preview_note.mapTo(viewport, QPoint(0, 0)),
                dialog.resource_preview_note.size(),
            )
            assert dialog.bs_entry.text() == "8"
            assert "adjusted to 8" in dialog.resource_preview_note.text()
            assert scroll_bar.value() == 0
            assert viewport.rect().contains(
                dialog.findChild(QLabel, "TrainingSettingPageHeader").mapTo(
                    viewport,
                    QPoint(0, 0),
                )
            )
            assert viewport.rect().contains(note_rect) is False
        finally:
            app.setFont(original_font)

    def test_resource_preview_never_overwrites_manual_batch_or_stale_generation(
        self,
        qtbot,
    ):
        request = TrainingResourcePreviewRequest(
            request_generation=0,
            publication_generation=23,
            model_name="EEGNet",
            model_params={},
            device="cuda:0",
            batch_size=32,
            optimizer="Adam",
        )
        with patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog."
            "get_optimizer_classes",
            return_value={"Adam": torch.optim.Adam},
        ):
            dialog = TrainingSettingDialog(
                None,
                None,
                recommendation=_recommendation(
                    "preview-context",
                    epochs=40,
                    batch_size=32,
                    learning_rate=0.001,
                ),
                resource_preview_request=request,
            )
            qtbot.addWidget(dialog)

        stale = dialog.build_training_resource_preview_request()
        current = dialog.build_training_resource_preview_request()
        assert stale is not None and current is not None
        stale_result = TrainingResourcePreviewResult(
            request_generation=stale.request_generation,
            publication_generation=23,
            requested_batch_size=32,
            suggested_batch_size=4,
            estimated_vram_bytes=128 * 1024**2,
            available_vram_bytes=512 * 1024**2,
            risk_level=RISK_WARNING,
            vram_known=True,
            warning=None,
        )
        assert dialog.apply_training_resource_preview(stale_result) is False
        assert dialog.bs_entry.text() == "32"

        dialog.bs_entry.setText("12")
        dialog.bs_entry.textEdited.emit("12")
        current_result = TrainingResourcePreviewResult(
            request_generation=current.request_generation,
            publication_generation=23,
            requested_batch_size=32,
            suggested_batch_size=8,
            estimated_vram_bytes=128 * 1024**2,
            available_vram_bytes=512 * 1024**2,
            risk_level=RISK_WARNING,
            vram_known=True,
            warning=None,
        )
        assert dialog.apply_training_resource_preview(current_result) is False
        assert dialog.bs_entry.text() == "12"

    def test_optimizer_change_invalidates_in_flight_resource_preview(self, qtbot):
        request = TrainingResourcePreviewRequest(
            request_generation=0,
            publication_generation=25,
            model_name="EEGNet",
            model_params={},
            device="cuda:0",
            batch_size=32,
            optimizer="Adam",
        )
        with patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog."
            "get_optimizer_classes",
            return_value={"Adam": torch.optim.Adam, "SGD": torch.optim.SGD},
        ):
            dialog = TrainingSettingDialog(
                None,
                None,
                initial_option={"optimizer": "Adam", "batch_size": 32},
                resource_preview_request=request,
            )
            qtbot.addWidget(dialog)

        in_flight = dialog.build_training_resource_preview_request()
        assert in_flight is not None
        with patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog."
            "OptimizerSettingDialog"
        ) as optimizer_dialog:
            optimizer_dialog.return_value.exec.return_value = True
            optimizer_dialog.return_value.get_result.return_value = (
                torch.optim.SGD,
                {"momentum": 0.9},
            )
            dialog.set_optimizer()

        assert optimizer_dialog.call_args.kwargs["optimizer"] is torch.optim.Adam
        assert optimizer_dialog.call_args.kwargs["optimizer_params"] == {}
        assert (
            dialog.apply_training_resource_preview(
                TrainingResourcePreviewResult(
                    request_generation=in_flight.request_generation,
                    publication_generation=25,
                    requested_batch_size=32,
                    suggested_batch_size=8,
                    estimated_vram_bytes=128 * 1024**2,
                    available_vram_bytes=512 * 1024**2,
                    risk_level=RISK_WARNING,
                    vram_known=True,
                    warning="Batch size was reduced for available GPU memory.",
                )
            )
            is False
        )
        assert dialog.bs_entry.text() == "32"

    def test_device_change_invalidates_in_flight_resource_preview(self, qtbot):
        request = TrainingResourcePreviewRequest(
            request_generation=0,
            publication_generation=26,
            model_name="EEGNet",
            model_params={},
            device="cuda:0",
            batch_size=32,
            optimizer="Adam",
        )
        with patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog."
            "get_optimizer_classes",
            return_value={"Adam": torch.optim.Adam},
        ):
            dialog = TrainingSettingDialog(
                None,
                None,
                initial_option={"device": "cuda:0", "batch_size": 32},
                resource_preview_request=request,
                device_recommendation_provider=lambda _device: _recommendation(
                    "cpu-preview",
                    epochs=10,
                    batch_size=32,
                    learning_rate=0.001,
                ),
            )
            qtbot.addWidget(dialog)

        in_flight = dialog.build_training_resource_preview_request()
        assert in_flight is not None
        with patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog.DeviceSettingDialog"
        ) as device_dialog:
            device_dialog.return_value.exec.return_value = True
            device_dialog.return_value.get_result.return_value = (True, None)
            dialog.set_device()

        assert (
            dialog.apply_training_resource_preview(
                TrainingResourcePreviewResult(
                    request_generation=in_flight.request_generation,
                    publication_generation=26,
                    requested_batch_size=32,
                    suggested_batch_size=8,
                    estimated_vram_bytes=128 * 1024**2,
                    available_vram_bytes=512 * 1024**2,
                    risk_level=RISK_WARNING,
                    vram_known=True,
                    warning="Batch size was reduced for available GPU memory.",
                )
            )
            is False
        )
        assert dialog.bs_entry.text() == "32"

    def test_unknown_vram_preview_adds_no_persistent_warning(self, qtbot):
        request = TrainingResourcePreviewRequest(
            request_generation=0,
            publication_generation=24,
            model_name="EEGNet",
            model_params={},
            device="cuda:0",
            batch_size=8,
            optimizer="Adam",
        )
        with patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog."
            "get_optimizer_classes",
            return_value={"Adam": torch.optim.Adam},
        ):
            dialog = TrainingSettingDialog(
                None,
                None,
                initial_option={"batch_size": 8},
                resource_preview_request=request,
            )
            qtbot.addWidget(dialog)
        current = dialog.build_training_resource_preview_request()
        assert current is not None

        applied = dialog.apply_training_resource_preview(
            TrainingResourcePreviewResult(
                request_generation=current.request_generation,
                publication_generation=24,
                requested_batch_size=8,
                suggested_batch_size=8,
                estimated_vram_bytes=128 * 1024**2,
                available_vram_bytes=None,
                risk_level=RISK_UNKNOWN,
                vram_known=False,
                warning=None,
            )
        )

        assert applied is False
        assert dialog.bs_entry.text() == "8"
        visible_text = " ".join(
            label.text() for label in dialog.findChildren(QLabel) if label.isVisible()
        )
        assert "GPU memory" not in visible_text

    def test_set_output_dir(self, window):
        with patch(
            "PyQt6.QtWidgets.QFileDialog.getExistingDirectory",
            return_value="/mock/test",
        ):
            window.set_output_dir()
            assert window.output_dir == "/mock/test"
            assert window.output_dir_label.text() == "/mock/test"

    def test_load_settings(self, qtbot):
        # Create mock controller
        mock_controller = MagicMock()
        mock_option = MagicMock()

        # Configure option
        mock_option.epoch = 50
        mock_option.bs = 64
        mock_option.lr = 0.005
        mock_option.checkpoint_epoch = 10
        mock_option.repeat_num = 3
        mock_option.output_dir = "/mock/loaded"
        mock_option.use_cpu = False
        mock_option.gpu_idx = 0
        mock_option.optim = torch.optim.Adam  # Use real Adam
        mock_option.optim_params = {}  # lr is separate parameter
        mock_option.evaluation_option.value = "Last Epoch"

        mock_controller.get_training_option.return_value = mock_option

        # Use real Adam class in get_optimizer_classes
        # Use real Adam class in get_optimizer_classes
        with (
            patch(
                "XBrainLab.ui.dialogs.training.training_setting_dialog.get_optimizer_classes",
                return_value={"Adam": torch.optim.Adam},
            ),
            patch(
                "torch.cuda.get_device_name",
                side_effect=AssertionError("dialog display queried GPU name"),
            ),
        ):
            window = TrainingSettingDialog(None, mock_controller)
            qtbot.addWidget(window)

            # Verify fields are populated
            assert window.epoch_entry is not None
            assert window.bs_entry is not None
            assert window.lr_entry is not None
            assert window.checkpoint_entry is not None
            assert window.repeat_entry is not None
            assert window.output_dir_label is not None
            assert window.opt_label is not None
            assert window.dev_label is not None
            assert window.evaluation_combo is not None
            assert window.epoch_entry.text() == "50"
            assert window.bs_entry.text() == "64"
            assert window.lr_entry.text() == "0.005"
            assert window.checkpoint_entry.text() == "10"
            assert window.repeat_entry.text() == "3"
            assert window.output_dir == "/mock/loaded"
            assert window.output_dir_label.text() == "/mock/loaded"
            assert window.use_cpu is False
            assert window.gpu_idx == 0
            assert "Adam" in window.opt_label.text()
            assert window.dev_label.text() == "GPU 0"

        assert window.evaluation_combo.currentText() == "Last epoch"
        assert window.evaluation_combo.currentData() is TrainingEvaluation.LAST_EPOCH

    def test_real_study_without_initial_option_does_not_read_controller_defaults(
        self,
        qtbot,
        monkeypatch,
    ):
        study = Study()
        controller = study.get_controller("training")
        parent = _StudyWidget()
        parent.study = study
        qtbot.addWidget(parent)
        get_training_option = MagicMock(
            side_effect=AssertionError(
                "real Study dialog should not read stale controller defaults",
            ),
        )
        monkeypatch.setattr(controller, "get_training_option", get_training_option)

        with patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog.get_optimizer_classes",
            return_value={"Adam": torch.optim.Adam},
        ):
            window = TrainingSettingDialog(parent, controller)
            qtbot.addWidget(window)

        get_training_option.assert_not_called()
        assert window.epoch_entry is not None
        assert window.bs_entry is not None
        assert window.lr_entry is not None
        assert window.epoch_entry.text() == "10"
        assert window.bs_entry.text() == "32"
        assert window.lr_entry.text() == "0.001"

    def test_constructor_uses_auto_without_any_gpu_api(self, qtbot):
        mock_controller = MagicMock()
        mock_controller.get_training_option.return_value = None
        with (
            patch(
                "XBrainLab.ui.dialogs.training.training_setting_dialog.get_optimizer_classes",
                return_value={"Adam": torch.optim.Adam},
            ),
            patch(
                "torch.cuda.device_count",
                side_effect=AssertionError("dialog constructor queried GPU count"),
            ),
            patch(
                "torch.cuda.get_device_name",
                side_effect=AssertionError("dialog constructor queried GPU name"),
            ),
        ):
            window = TrainingSettingDialog(None, mock_controller)
            qtbot.addWidget(window)

        assert window.use_cpu is True
        assert window.gpu_idx is None
        assert window.get_device_value() == "auto"
        assert window.dev_label is not None
        assert window.dev_label.text() == "Auto"


class TestSetOptimizer:
    @pytest.fixture
    def window(self, qtbot):
        # Mock torch.optim members
        mock_adam = MagicMock()
        mock_adam.__name__ = "Adam"

        with patch(
            "XBrainLab.ui.dialogs.training.optimizer_setting_dialog.get_optimizer_classes",
            return_value={"Adam": mock_adam},
        ):
            window = OptimizerSettingDialog(None)
            qtbot.addWidget(window)
            yield window

    def test_init_and_populate(self, window):
        assert window.algo_combo.count() == 1
        assert window.algo_combo.currentText() == "Adam"

    def test_confirm(self, window):
        window.accept()
        result = window.get_result()
        assert result is not None
        optim_class, optim_params = result
        assert optim_class is not None
        assert isinstance(optim_params, dict)

    def test_discovery_exposes_only_concrete_optimizer_subclasses(self):
        optimizers = get_optimizer_classes()

        assert set(optimizers) == {"Adam", "AdamW", "SGD"}
        assert optimizers["Adam"] is torch.optim.Adam
        assert optimizers["AdamW"] is torch.optim.AdamW
        assert optimizers["SGD"] is torch.optim.SGD
        assert "Optimizer" not in optimizers
        assert all(
            issubclass(optimizer, torch.optim.Optimizer)
            and optimizer is not torch.optim.Optimizer
            for optimizer in optimizers.values()
        )

    def test_current_optimizer_and_parameters_are_restored(self, qtbot):
        dialog = OptimizerSettingDialog(
            None,
            optimizer=torch.optim.AdamW,
            optimizer_params={"weight_decay": 0.125, "amsgrad": True},
        )
        qtbot.addWidget(dialog)

        assert dialog.algo_combo.currentText() == "AdamW"
        values = {
            dialog.params_table.item(row, 0).text(): dialog.params_table.item(
                row, 1
            ).text()
            for row in range(dialog.params_table.rowCount())
        }
        assert values["weight_decay"] == "0.125"
        assert values["amsgrad"] == "True"

    def test_every_visible_optimizer_accepts_its_native_defaults(self):
        from XBrainLab.backend.training.utils import (
            get_optimizer_params,
            parse_optimizer_param,
        )

        def default_failure(name, optimizer):
            try:
                params = {
                    parameter: parse_optimizer_param(
                        optimizer,
                        parameter,
                        default_text,
                    )
                    for parameter, default_text in get_optimizer_params(optimizer)
                    if default_text
                }
                instantiate_optimizer(optimizer, params)
            except Exception as exc:  # pragma: no cover - assertion records details
                return name, type(exc).__name__, str(exc)
            return None

        failures = [
            failure
            for name, optimizer in get_optimizer_classes().items()
            if (failure := default_failure(name, optimizer)) is not None
        ]

        assert failures == []

    @pytest.mark.parametrize(
        ("optimizer_name", "expected_params"),
        [
            ("Adam", {"betas": (0.9, 0.999), "amsgrad": False}),
            ("AdamW", {"betas": (0.9, 0.999), "amsgrad": False}),
            ("SGD", {"momentum": 0, "nesterov": False}),
        ],
    )
    def test_real_optimizer_native_defaults_switch_and_submit_without_warning(
        self,
        qtbot,
        optimizer_name,
        expected_params,
    ):
        with patch(
            "XBrainLab.ui.dialogs.training.optimizer_setting_dialog.show_warning"
        ) as warning:
            dialog = OptimizerSettingDialog(None)
            qtbot.addWidget(dialog)
            dialog.algo_combo.setCurrentText(optimizer_name)
            with patch("PyQt6.QtWidgets.QDialog.accept") as accepted:
                dialog.accept()

        accepted.assert_called_once()
        warning.assert_not_called()
        optimizer, params = dialog.get_result()
        assert optimizer is getattr(torch.optim, optimizer_name)
        for name, value in expected_params.items():
            assert params[name] == value
        assert isinstance(instantiate_optimizer(optimizer, params), optimizer)

    def test_optimizer_validation_error_names_the_invalid_field(self, qtbot):
        dialog = OptimizerSettingDialog(None)
        qtbot.addWidget(dialog)
        dialog.algo_combo.setCurrentText("Adam")
        betas_row = next(
            row
            for row in range(dialog.params_table.rowCount())
            if dialog.params_table.item(row, 0).text() == "betas"
        )
        dialog.params_table.item(betas_row, 1).setText("not-a-tuple")

        with patch(
            "XBrainLab.ui.dialogs.training.optimizer_setting_dialog.show_warning"
        ) as warning:
            dialog.accept()

        warning.assert_called_once()
        parent, title, message = warning.call_args.args
        assert parent is dialog
        assert title == "Validation Error"
        assert "betas" in message


class TestSetDevice:
    @pytest.fixture
    def window(self, qtbot):
        with (
            patch("torch.cuda.device_count", return_value=1),
            patch("torch.cuda.get_device_name", return_value="Test GPU"),
        ):
            window = DeviceSettingDialog(None)
            qtbot.addWidget(window)
            yield window

    def test_init(self, window):
        assert window.device_list.count() == 2  # CPU + 1 GPU
        assert window.device_list.item(0).text() == "CPU"
        assert "Test GPU" in window.device_list.item(1).text()

    def test_confirm_cpu(self, window):
        window.device_list.setCurrentRow(0)
        with patch("PyQt6.QtWidgets.QDialog.accept") as mock_accept:
            window.accept()
            mock_accept.assert_called_once()

        use_cpu, gpu_idx = window.get_result()
        assert use_cpu is True
        assert gpu_idx is None

    def test_confirm_gpu(self, window):
        window.device_list.setCurrentRow(1)
        with patch("PyQt6.QtWidgets.QDialog.accept") as mock_accept:
            window.accept()
            mock_accept.assert_called_once()

        use_cpu, gpu_idx = window.get_result()
        assert use_cpu is False
        assert gpu_idx == 0
