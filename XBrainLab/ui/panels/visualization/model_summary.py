"""Dialog window for displaying a model architecture summary."""

from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
)

from XBrainLab.ui.core.base_dialog import BaseDialog


class ModelSummaryWindow(BaseDialog):
    """Dialog that displays a ``torchinfo`` model summary for a selected plan.

    Allows the user to choose from available training plans and shows
    a monospace-formatted summary of the model architecture.

    Attributes:
        trainers: List of ``Trainer`` instances to summarize.
        trainer_map: Mapping of trainer display names to ``Trainer`` objects.
        plan_combo: ``QComboBox`` for selecting a training plan.
        summary_text: ``QTextEdit`` displaying the model summary.

    """

    def __init__(self, parent, trainers):
        """Initialize the model summary dialog.

        Args:
            parent: Parent widget.
            trainers: List of ``Trainer`` instances.

        """
        self.trainers = trainers
        self.trainer_map = {t.get_name(): t for t in trainers}

        # super().__init__ calls init_ui via BaseDialog
        super().__init__(parent, title="Model Summary")

        self.check_data()

    def check_data(self):
        """Validate that at least one trainer is available."""
        if not self.trainers:
            QMessageBox.warning(self, "Warning", "No valid training plan is generated")
            # We don't reject here immediately to allow window to show empty state if
            # needed,
            # but usually this is called before showing.

    def init_ui(self):
        """Build the layout with plan selector and summary text area."""
        layout = QVBoxLayout(self)

        # Top: Plan Selection
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Select Plan:"))

        self.plan_combo = QComboBox()
        self.plan_combo.addItem("Select a plan")
        self.plan_combo.addItems(list(self.trainer_map.keys()))
        self.plan_combo.currentTextChanged.connect(self.on_plan_select)
        top_layout.addWidget(self.plan_combo)

        layout.addLayout(top_layout)

        # Center: Summary Text
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setFontFamily("Courier New")  # Monospace for alignment
        layout.addWidget(self.summary_text)

    def on_plan_select(self, plan_name):
        """Generate and display the model summary for the selected plan.

        Args:
            plan_name: The display name of the selected training plan.

        """
        self.summary_text.clear()
        if plan_name not in self.trainer_map:
            return

        trainer = self.trainer_map[plan_name]
        try:
            # Logic adapted from original
            model_instance = trainer.model_holder.get_model(
                trainer.dataset.get_epoch_data().get_model_args(),
            ).to(trainer.option.get_device())

            X, _ = trainer.dataset.get_training_data()
            # Assuming X is [N, C, T] or similar
            # Original code: train_shape = (self.trainer.option.bs, 1, *X.shape[-2:])
            # We need to be careful about dimensions.
            # If X is [N, C, T], shape[-2:] is (C, T).
            # If model expects (Batch, 1, C, T) (e.g. EEGNet often treats channels as
            # spatial dim), then this is correct.
            # But let's trust the original logic.

            train_shape = (trainer.option.bs, 1, *X.shape[-2:])

            from torchinfo import summary  # noqa: PLC0415 — lazy: optional dep

            summary_str = str(
                summary(model_instance, input_size=train_shape, verbose=0),
            )

            self.summary_text.setText(summary_str)

        except Exception as e:
            self.summary_text.setText(f"Error generating summary: {e}")
