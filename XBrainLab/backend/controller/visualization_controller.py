from typing import List, Optional, Tuple, Dict
import numpy as np
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import Trainer, TrainingPlanHolder
from XBrainLab.backend.training.record.eval import EvalRecord

class VisualizationController:
    """
    Controller for handling visualization operations and data retrieval.
    Decouples UI from direct Study/Backend manipulation.
    """
    def __init__(self, study: Study):
        self._study = study

    def get_trainers(self) -> List[TrainingPlanHolder]:
        """Get list of training plan holders (groups)."""
        if self._study.trainer:
            return self._study.trainer.get_training_plan_holders()
        return []

    def set_montage(self, chs: List[str], positions: List[Tuple[float, float, float]]) -> None:
        """Set channel montage in Study."""
        self._study.set_channels(chs, positions)

    def get_channel_names(self) -> List[str]:
        """Get channel names from epoch data."""
        if self._study.epoch_data:
            return self._study.epoch_data.get_channel_names()
        return []

    def get_saliency_params(self) -> Dict:
        """Get current saliency parameters."""
        return self._study.get_saliency_params()

    def set_saliency_params(self, params: Dict) -> None:
        """Set saliency parameters in Study."""
        self._study.set_saliency_params(params)

    def get_averaged_record(self, trainer_holder: TrainingPlanHolder) -> Optional[EvalRecord]:
        """
        Compute average EvalRecord from all finished runs in a plan holder.
        """
        plans = trainer_holder.get_plans()
        # Filter for plans with valid eval records
        records = [p.get_eval_record() for p in plans if p.get_eval_record() is not None]
        
        if not records:
            return None
            
        base = records[0]
        
        def avg_dict(attr_name):
            result = {}
            # attributes like 'gradient', 'smoothgrad' are dictionaries
            base_attr = getattr(base, attr_name)
            if not base_attr:
                return {}
                
            keys = base_attr.keys()
            for k in keys:
                # Stack arrays from all records and compute mean
                arrays = [getattr(r, attr_name)[k] for r in records]
                result[k] = np.mean(np.stack(arrays), axis=0)
            return result

        avg_gradient = avg_dict('gradient')
        avg_gradient_input = avg_dict('gradient_input')
        avg_smoothgrad = avg_dict('smoothgrad')
        avg_smoothgrad_sq = avg_dict('smoothgrad_sq')
        avg_vargrad = avg_dict('vargrad')
        
        return EvalRecord(
            label=base.label,
            output=base.output, # Output might differ per run, but here we assume consistent shape/classes
            gradient=avg_gradient,
            gradient_input=avg_gradient_input,
            smoothgrad=avg_smoothgrad,
            smoothgrad_sq=avg_smoothgrad_sq,
            vargrad=avg_vargrad
        )
