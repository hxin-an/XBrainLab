from typing import Dict, List, Optional, Tuple

import numpy as np
from torchinfo import summary

from XBrainLab.backend.study import Study
from XBrainLab.backend.training import TrainingPlanHolder
from XBrainLab.backend.training.record import EvalRecord, TrainRecord


class EvaluationController:
    """
    Controller for handling evaluation data retrieval and processing.
    Decouples UI from direct Study/Backend manipulation.
    """
    def __init__(self, study: Study):
        self._study = study

    def get_plans(self) -> List[TrainingPlanHolder]:
        """Get list of training plan holders (groups)."""
        if self._study.trainer:
            return self._study.trainer.get_training_plan_holders()
        return []

    def get_pooled_eval_result(self, plan: TrainingPlanHolder) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], Dict]:
        """
        Pool labels and outputs from all finished runs in a plan.
        Returns (pooled_labels, pooled_outputs, pooled_metrics).
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
        # Note: Gradients are passed as empty dicts as we don't need them for metrics here
        temp_record = EvalRecord(pooled_labels, pooled_outputs, {}, {}, {}, {}, {})
        metrics = temp_record.get_per_class_metrics()

        return pooled_labels, pooled_outputs, metrics

    def get_model_summary_str(self, plan: TrainingPlanHolder, record: Optional[TrainRecord] = None) -> str:
        """Generate model summary string."""
        try:
            # Get model instance
            # If record is provided, use its trained model
            if record and hasattr(record, 'model'):
                model_instance = record.model
            else:
                # Instantiate new model from holder
                # We need input shape to initialize some models or just for summary
                args = plan.dataset.get_epoch_data().get_model_args()
                model_instance = plan.model_holder.get_model(args).to(plan.option.get_device())

            # Get input shape
            # We need to access dataset to get shape.
            # Controller assumes backend objects are accessible via plan.
            X, _ = plan.dataset.get_training_data()
            # Assuming X is [N, C, T]
            train_shape = (plan.option.bs, 1, *X.shape[-2:])

            summary_str = str(summary(
                model_instance, input_size=train_shape, verbose=0
            ))

            if record:
                summary_str = f"=== Run: {record.get_name()} ===\n" + summary_str

            return summary_str

        except Exception as e:
            return f"Error generating summary: {e}"
