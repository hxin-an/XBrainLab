"""Visualization controller for EEG data and model result rendering.

Provides methods for montage configuration, saliency parameter
management, and computation of averaged evaluation records across
training runs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from XBrainLab.backend.training import TrainingPlanHolder
from XBrainLab.backend.training.record.eval import EvalRecord
from XBrainLab.backend.utils.observer import Observable

if TYPE_CHECKING:
    from XBrainLab.backend.study import Study


class VisualizationController(Observable):
    """Controller for visualization operations and data retrieval.

    Decouples the UI from direct Study/Backend manipulation by
    providing access to loaded data, montage configuration, saliency
    parameters, and averaged evaluation records.

    Events:
        montage_changed: Emitted when the channel montage is updated.
        saliency_changed: Emitted when saliency parameters are
            modified.

    Attributes:
        _study: Reference to the :class:`Study` backend instance.

    """

    def __init__(self, study: Study):
        """Initialise the visualization controller.

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

    def get_trainers(self) -> list[TrainingPlanHolder]:
        """Return the list of training plan holders (groups).

        Returns:
            A list of :class:`TrainingPlanHolder` instances, or an
            empty list if no trainer exists.

        """
        if self._study.trainer:
            return self._study.trainer.get_training_plan_holders()
        return []

    def set_montage(
        self,
        chs: list[str],
        positions: list[tuple[float, float, float]],
    ) -> None:
        """Set the channel montage in the study.

        Args:
            chs: List of channel name strings.
            positions: List of ``(x, y, z)`` position tuples for each
                channel.

        """
        self._study.set_channels(chs, positions)
        self.notify("montage_changed")

    def has_epoch_data(self) -> bool:
        """Check whether epoch data is available.

        Returns:
            ``True`` if epoch data has been set in the study.

        """
        return self._study.epoch_data is not None

    def get_channel_names(self) -> list[str]:
        """Return channel names from the epoch data.

        Returns:
            List of channel name strings, or an empty list if no
            epoch data is loaded.

        """
        if self._study.epoch_data:
            return self._study.epoch_data.get_channel_names()
        return []

    def get_saliency_params(self) -> dict | None:
        """Return the current saliency parameters.

        Returns:
            A dictionary of saliency parameters, or ``None`` if not
            configured.

        """
        return self._study.get_saliency_params()

    def set_saliency_params(self, params: dict) -> None:
        """Set saliency parameters in the study.

        Args:
            params: Dictionary of saliency configuration values.

        """
        self._study.set_saliency_params(params)
        self.notify("saliency_changed")

    def get_averaged_record(
        self,
        trainer_holder: TrainingPlanHolder,
    ) -> EvalRecord | None:
        """Compute an averaged :class:`EvalRecord` across finished runs.

        Gradient-based attributes (gradient, gradient*input,
        SmoothGrad, SmoothGrad², VarGrad) are averaged element-wise
        across all completed runs in the plan holder.

        Args:
            trainer_holder: The :class:`TrainingPlanHolder` whose
                finished runs are to be averaged.

        Returns:
            An :class:`EvalRecord` with averaged gradient maps, or
            ``None`` if no finished runs contain evaluation records.

        """
        plans = trainer_holder.get_plans()
        # Filter for plans with valid eval records
        records: list[EvalRecord] = []
        for p in plans:
            r = p.get_eval_record()
            if r is not None:
                records.append(r)

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

        avg_gradient = avg_dict("gradient")
        avg_gradient_input = avg_dict("gradient_input")
        avg_smoothgrad = avg_dict("smoothgrad")
        avg_smoothgrad_sq = avg_dict("smoothgrad_sq")
        avg_vargrad = avg_dict("vargrad")

        return EvalRecord(
            label=base.label,
            # Output might differ per run, but here we assume consistent
            # shape/classes
            output=base.output,
            gradient=avg_gradient,
            gradient_input=avg_gradient_input,
            smoothgrad=avg_smoothgrad,
            smoothgrad_sq=avg_smoothgrad_sq,
            vargrad=avg_vargrad,
        )
