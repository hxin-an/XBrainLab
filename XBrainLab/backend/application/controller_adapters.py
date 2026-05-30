"""Typed lazy adapters from ApplicationService to existing workflow controllers."""

from __future__ import annotations

from typing import Any

from XBrainLab.backend.study import Study
from XBrainLab.backend.utils.logger import logger


class LazyControllerAdapter:
    """Resolve one existing controller only when a command service needs it."""

    def __init__(self, study: Study, controller_name: str) -> None:
        self.study = study
        self.controller_name = controller_name
        self._controller_instance: Any | None = None

    def _controller(self) -> Any:
        if self._controller_instance is None:
            self._controller_instance = self.study.get_controller(self.controller_name)
        return self._controller_instance

    def _call(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        method = getattr(self._controller(), method_name)
        return method(*args, **kwargs)

    def _get_attr(self, attribute_name: str, default: Any = None) -> Any:
        return getattr(self._controller(), attribute_name, default)

    def _set_attr(self, attribute_name: str, value: Any) -> None:
        setattr(self._controller(), attribute_name, value)

    def notify(self, event: str, *args: Any, **kwargs: Any) -> Any:
        return self._call("notify", event, *args, **kwargs)


class DatasetControllerAdapter(LazyControllerAdapter):
    """Dataset-controller surface used by application command services."""

    def __init__(self, study: Study) -> None:
        super().__init__(study, "dataset")

    @property
    def loaded(self) -> Any:
        return self._get_attr("loaded", [])

    @loaded.setter
    def loaded(self, value: Any) -> None:
        self._set_attr("loaded", value)

    @property
    def imported_paths(self) -> Any:
        return self._get_attr("imported_paths", [])

    @imported_paths.setter
    def imported_paths(self, value: Any) -> None:
        self._set_attr("imported_paths", value)

    def clean_dataset(self) -> Any:
        return self._call("clean_dataset")

    def import_files(self, paths: list[str]) -> Any:
        return self._call("import_files", paths)

    def get_loaded_data_list(self) -> Any:
        return self._call("get_loaded_data_list")

    def apply_labels_batch(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("apply_labels_batch", *args, **kwargs)

    def update_metadata(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("update_metadata", *args, **kwargs)

    def apply_smart_parse(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("apply_smart_parse", *args, **kwargs)

    def remove_files(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("remove_files", *args, **kwargs)

    def apply_channel_selection(self, channels: list[str]) -> Any:
        return self._call("apply_channel_selection", channels)

    def get_runtime_diagnostics(self) -> Any:
        return self._call("get_runtime_diagnostics")

    def get_event_info(self) -> Any:
        return self._call("get_event_info")

    def get_smart_filter_suggestions(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("get_smart_filter_suggestions", *args, **kwargs)


class PreprocessControllerAdapter(LazyControllerAdapter):
    """Preprocess-controller surface used by application command services."""

    def __init__(self, study: Study) -> None:
        super().__init__(study, "preprocess")

    def get_runtime_diagnostics(self) -> Any:
        return self._call("get_runtime_diagnostics")

    def is_epoched(self) -> bool:
        return bool(self._call("is_epoched"))

    def get_channel_names(self) -> Any:
        return self._call("get_channel_names")

    def apply_filter(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("apply_filter", *args, **kwargs)

    def apply_resample(self, rate: float) -> Any:
        return self._call("apply_resample", rate)

    def apply_normalization(self, method: str) -> Any:
        return self._call("apply_normalization", method)

    def apply_rereference(self, channels: str | list[str]) -> Any:
        return self._call("apply_rereference", channels)

    def apply_epoching(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("apply_epoching", *args, **kwargs)

    def batch_notifications(self) -> Any:
        return self._call("batch_notifications")

    def apply_montage(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("apply_montage", *args, **kwargs)


class TrainingControllerAdapter(LazyControllerAdapter):
    """Training-controller surface used by application command services."""

    def __init__(self, study: Study) -> None:
        super().__init__(study, "training")

    def set_training_option(self, option: Any) -> Any:
        return self._call("set_training_option", option)

    def set_model_holder(self, holder: Any) -> Any:
        return self._call("set_model_holder", holder)

    def start_training(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("start_training", *args, **kwargs)

    def stop_training(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("stop_training", *args, **kwargs)

    def clear_history(self) -> Any:
        return self._call("clear_history")

    def apply_data_splitting(self, generator: Any) -> Any:
        return self._call("apply_data_splitting", generator)

    def clean_datasets(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("clean_datasets", *args, **kwargs)

    def is_training(self) -> bool:
        training_manager = getattr(self.study, "training_manager", None)
        if training_manager is None:
            return False
        try:
            return bool(training_manager.is_training())
        except Exception:
            logger.debug("Failed to read training state", exc_info=True)
            return False

    def get_formatted_history(self) -> list[dict[str, Any]]:
        if getattr(self.study, "trainer", None) is None:
            return []
        return list(self._call("get_formatted_history"))

    def get_missing_requirements(self) -> list[str]:
        missing: list[str] = []
        if not list(getattr(self.study, "datasets", []) or []):
            missing.append("Data Splitting")
        if getattr(self.study, "model_holder", None) is None:
            missing.append("Model Selection")
        if getattr(self.study, "training_option", None) is None:
            missing.append("Training Settings")
        return missing


class EvaluationControllerAdapter(LazyControllerAdapter):
    """Evaluation-controller surface used by analysis and state queries."""

    def __init__(self, study: Study) -> None:
        super().__init__(study, "evaluation")

    def get_pooled_eval_result(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("get_pooled_eval_result", *args, **kwargs)

    def get_model_summary_str(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("get_model_summary_str", *args, **kwargs)

    def get_plans(self) -> list[Any]:
        trainer = getattr(self.study, "trainer", None)
        if trainer is None:
            return []
        try:
            return list(trainer.get_training_plan_holders())
        except Exception:
            logger.debug("Failed to read training plans", exc_info=True)
            return []


class VisualizationControllerAdapter(LazyControllerAdapter):
    """Visualization-controller surface used by analysis command services."""

    def __init__(self, study: Study) -> None:
        super().__init__(study, "visualization")

    def get_trainers(self) -> Any:
        return self._call("get_trainers")

    def set_saliency_params(self, params: Any) -> Any:
        return self._call("set_saliency_params", params)

    def get_saliency_params(self) -> Any:
        return self._call("get_saliency_params")

    def get_averaged_record(self, trainer: Any) -> Any:
        return self._call("get_averaged_record", trainer)
