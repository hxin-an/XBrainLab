"""Evaluation controller for model performance analysis.

Provides methods for pooling evaluation results across training runs
and generating model architecture summaries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from XBrainLab.backend.training import TrainingPlanHolder
from XBrainLab.backend.training.record import EvalRecord, TrainRecord
from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.utils.observer import Observable

if TYPE_CHECKING:
    from XBrainLab.backend.study import Study


class EvaluationController(Observable):
    """Controller for evaluation data retrieval and processing.

    Decouples the UI from direct Study/Backend manipulation by
    providing a clean interface for querying evaluation metrics,
    pooling results across runs, and generating model summaries.

    Events:
        evaluation_updated: Emitted when evaluation data changes.

    Attributes:
        _study: Reference to the :class:`Study` backend instance.
    """

    def __init__(self, study: Study):
        """Initialise the evaluation controller.

        Args:
            study: The :class:`Study` backend instance to query.
        """
        Observable.__init__(self)
        self._study = study

    def get_loaded_data_list(self):
        """Return the loaded raw data list from the study.

        Returns:
            The list of raw data objects held by the study.
        """
        return self._study.loaded_data_list

    def get_preprocessed_data_list(self):
        """Return the preprocessed data list from the study.

        Returns:
            The list of preprocessed data objects held by the study.
        """
        return self._study.preprocessed_data_list

    def get_plans(self) -> list[TrainingPlanHolder]:
        """Return the list of training plan holders (groups).

        Returns:
            A list of :class:`TrainingPlanHolder` instances, or an
            empty list if no trainer exists.
        """
        if self._study.trainer:
            return self._study.trainer.get_training_plan_holders()
        return []

    def get_pooled_eval_result(
        self, plan: TrainingPlanHolder
    ) -> tuple[np.ndarray | None, np.ndarray | None, dict]:
        """Pool evaluation labels and outputs from all finished runs.

        Concatenates ground-truth labels and model outputs across
        every completed run in the given plan and computes per-class
        metrics on the pooled data.

        Args:
            plan: The :class:`TrainingPlanHolder` whose finished runs
                are to be pooled.

        Returns:
            A 3-tuple ``(pooled_labels, pooled_outputs, metrics)``:

            - *pooled_labels*: Concatenated label array, or ``None``
              if no finished runs exist.
            - *pooled_outputs*: Concatenated output array, or ``None``
              if no finished runs exist.
            - *metrics*: Per-class metrics dictionary, or an empty
              dictionary if no data is available.
        """
        records = [r for r in plan.get_plans() if r.is_finished()]
        if not records:
            return None, None, {}

        all_labels = []
        all_outputs = []

        for r in records:
            if r.eval_record:
                all_labels.append(r.eval_record.label)
                all_outputs.append(r.eval_record.output)

        if not all_labels:
            return None, None, {}

        # Concatenate for pooling
        pooled_labels = np.concatenate(all_labels)
        pooled_outputs = np.concatenate(all_outputs)

        # Calculate metrics on pooled data
        # We create a temporary EvalRecord to calculate metrics
        # Note: Gradients are passed as empty dicts as we don't need them for
        # metrics here
        temp_record = EvalRecord(pooled_labels, pooled_outputs, {}, {}, {}, {}, {})
        metrics = temp_record.get_per_class_metrics()

        return pooled_labels, pooled_outputs, metrics

    def get_model_summary_str(
        self, plan: TrainingPlanHolder, record: TrainRecord | None = None
    ) -> str:
        """Generate a human-readable model architecture summary.

        If a *record* with a trained model is provided, its model
        is used; otherwise a fresh model instance is created from
        the plan's model holder.

        Args:
            plan: The :class:`TrainingPlanHolder` containing model and
                dataset information.
            record: Optional :class:`TrainRecord` whose trained model
                should be summarised. When ``None``, a new model is
                instantiated from the plan.

        Returns:
            A string representation of the model summary produced by
            ``torchinfo.summary``, or an error message if summary
            generation fails.
        """
        try:
            from torchinfo import summary  # noqa: PLC0415 — lazy: optional dep

            # Get model instance
            # If record is provided, use its trained model
            if record and hasattr(record, "model"):
                model_instance = record.model
            else:
                # Instantiate new model from holder
                # We need input shape to initialize some models or just for summary
                args = plan.dataset.get_epoch_data().get_model_args()
                model_instance = plan.model_holder.get_model(args).to(
                    plan.option.get_device()
                )

            # Get input shape
            # We need to access dataset to get shape.
            # Controller assumes backend objects are accessible via plan.
            X, _ = plan.dataset.get_training_data()
            # Assuming X is [N, C, T]
            train_shape = (plan.option.bs, 1, *X.shape[-2:])

            summary_str = str(
                summary(model_instance, input_size=train_shape, verbose=0)
            )

            if record:
                summary_str = f"=== Run: {record.get_name()} ===\n" + summary_str

        except Exception as e:
            logger.error("Error generating model summary", exc_info=True)
            return f"Error generating summary: {e}"

        return summary_str
