from unittest.mock import MagicMock, patch

import pytest
import torch
from PyQt6.QtCore import QPoint, QRect, QSize
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QLabel,
    QScrollArea,
    QWidget,
)

from XBrainLab.backend.application.training_recommendation import (
    TrainingRecommendation,
    TrainingRecommendationField,
    TrainingRecommendationValues,
    TrainingSettingProvenance,
)
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import TrainingEvaluation
from XBrainLab.backend.training.utils import instantiate_optimizer
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
        assert window.windowTitle() == "Training Setting"
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

    def test_recommendation_note_lists_user_edited_fields(self, qtbot):
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

        assert dialog.recommendation_note.isHidden() is False
        assert dialog.recommendation_note.text() == (
            "Recommended starting points; fields you edit are retained. "
            "Manual fields: none."
        )

        dialog.epoch_entry.textEdited.emit("50")

        assert dialog.recommendation_note.text() == (
            "Recommended starting points; fields you edit are retained. "
            "Manual fields: training epochs."
        )
        assert dialog.get_recommendation().provenance["epochs"] is (
            TrainingSettingProvenance.MANUAL
        )

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
