"""Typed lazy adapters from ApplicationService to existing workflow controllers."""

from __future__ import annotations

from typing import Any, Protocol, cast

from XBrainLab.backend.study import Study
from XBrainLab.backend.utils.logger import logger


class _ObservableControllerPort(Protocol):
    def notify(self, event: str, *args: Any, **kwargs: Any) -> Any: ...


class _DatasetControllerPort(_ObservableControllerPort, Protocol):
    loaded: Any
    imported_paths: Any

    def clean_dataset(self) -> Any: ...
    def import_files(self, paths: list[str]) -> Any: ...
    def get_loaded_data_list(self) -> Any: ...
    def apply_labels_batch(self, *args: Any, **kwargs: Any) -> Any: ...
    def update_metadata(self, *args: Any, **kwargs: Any) -> Any: ...
    def apply_smart_parse(self, *args: Any, **kwargs: Any) -> Any: ...
    def remove_files(self, *args: Any, **kwargs: Any) -> Any: ...
    def apply_channel_selection(self, channels: list[str]) -> Any: ...
    def get_runtime_diagnostics(self) -> Any: ...
    def get_event_info(self) -> Any: ...
    def get_smart_filter_suggestions(self, *args: Any, **kwargs: Any) -> Any: ...


class _PreprocessControllerPort(_ObservableControllerPort, Protocol):
    def get_runtime_diagnostics(self) -> Any: ...
    def is_epoched(self) -> bool: ...
    def get_channel_names(self) -> Any: ...
    def apply_filter(self, *args: Any, **kwargs: Any) -> Any: ...
    def apply_resample(self, rate: float) -> Any: ...
    def apply_normalization(self, method: str) -> Any: ...
    def apply_rereference(self, channels: str | list[str]) -> Any: ...
    def apply_epoching(self, *args: Any, **kwargs: Any) -> Any: ...
    def batch_notifications(self) -> Any: ...
    def apply_montage(self, *args: Any, **kwargs: Any) -> Any: ...


class _TrainingControllerPort(_ObservableControllerPort, Protocol):
    def set_training_option(self, option: Any) -> Any: ...
    def set_model_holder(self, holder: Any) -> Any: ...
    def start_training(self, *args: Any, **kwargs: Any) -> Any: ...
    def stop_training(self, *args: Any, **kwargs: Any) -> Any: ...
    def clear_history(self) -> Any: ...
    def apply_data_splitting(self, generator: Any) -> Any: ...
    def clean_datasets(self, *args: Any, **kwargs: Any) -> Any: ...
    def is_training(self) -> bool: ...
    def get_formatted_history(self) -> list[dict[str, Any]]: ...
    def get_missing_requirements(self) -> list[str]: ...


class _EvaluationControllerPort(_ObservableControllerPort, Protocol):
    def get_pooled_eval_result(self, *args: Any, **kwargs: Any) -> Any: ...
    def get_model_summary_str(self, *args: Any, **kwargs: Any) -> Any: ...
    def get_plans(self) -> list[Any]: ...


class _VisualizationControllerPort(_ObservableControllerPort, Protocol):
    def get_trainers(self) -> Any: ...
    def set_saliency_params(self, params: Any) -> Any: ...
    def get_saliency_params(self) -> Any: ...
    def get_averaged_record(self, trainer: Any) -> Any: ...


class LazyControllerAdapter:
    """Resolve one existing controller only when a command service needs it."""

    def __init__(self, study: Study, controller_name: str) -> None:
        self._study = study
        self._controller_name = controller_name
        self._controller_instance: Any | None = None

    def _resolve_controller(self) -> Any:
        if self._controller_instance is None:
            self._controller_instance = self._study.get_controller(
                self._controller_name
            )
        return self._controller_instance

    def _observable_controller(self) -> _ObservableControllerPort:
        return cast(_ObservableControllerPort, self._resolve_controller())

    def notify(self, event: str, *args: Any, **kwargs: Any) -> Any:
        return self._observable_controller().notify(event, *args, **kwargs)


class _TrainingStateReadModel:
    """Lightweight training state read model that avoids loading training modules."""

    def __init__(self, study: Study) -> None:
        self._study = study

    def is_training(self) -> bool:
        training_manager = getattr(self._study, "training_manager", None)
        if training_manager is None:
            return False
        try:
            return bool(training_manager.is_training())
        except Exception:
            logger.debug("Failed to read training state", exc_info=True)
            return False

    def get_formatted_history(self) -> list[dict[str, Any]]:
        if getattr(self._study, "trainer", None) is None:
            return []
        controller = cast(
            _TrainingControllerPort,
            self._study.get_controller("training"),
        )
        return list(controller.get_formatted_history())

    def get_missing_requirements(self) -> list[str]:
        missing: list[str] = []
        if not list(getattr(self._study, "datasets", []) or []):
            missing.append("Data Splitting")
        if getattr(self._study, "model_holder", None) is None:
            missing.append("Model Selection")
        if getattr(self._study, "training_option", None) is None:
            missing.append("Training Settings")
        return missing


class _EvaluationStateReadModel:
    """Lightweight evaluation state read model for plan availability."""

    def __init__(self, study: Study) -> None:
        self._study = study

    def get_plans(self) -> list[Any]:
        trainer = getattr(self._study, "trainer", None)
        if trainer is None:
            return []
        try:
            return list(trainer.get_training_plan_holders())
        except Exception:
            logger.debug("Failed to read training plans", exc_info=True)
            return []


class DatasetControllerAdapter(LazyControllerAdapter):
    """Dataset-controller surface used by application command services."""

    def __init__(self, study: Study) -> None:
        super().__init__(study, "dataset")

    def _controller(self) -> _DatasetControllerPort:
        return cast(_DatasetControllerPort, self._resolve_controller())

    @property
    def loaded(self) -> Any:
        return self._controller().loaded

    @loaded.setter
    def loaded(self, value: Any) -> None:
        self._controller().loaded = value

    @property
    def imported_paths(self) -> Any:
        return self._controller().imported_paths

    @imported_paths.setter
    def imported_paths(self, value: Any) -> None:
        self._controller().imported_paths = value

    def clean_dataset(self) -> Any:
        return self._controller().clean_dataset()

    def import_files(self, paths: list[str]) -> Any:
        return self._controller().import_files(paths)

    def get_loaded_data_list(self) -> Any:
        return self._controller().get_loaded_data_list()

    def apply_labels_batch(self, *args: Any, **kwargs: Any) -> Any:
        return self._controller().apply_labels_batch(*args, **kwargs)

    def update_metadata(self, *args: Any, **kwargs: Any) -> Any:
        return self._controller().update_metadata(*args, **kwargs)

    def apply_smart_parse(self, *args: Any, **kwargs: Any) -> Any:
        return self._controller().apply_smart_parse(*args, **kwargs)

    def remove_files(self, *args: Any, **kwargs: Any) -> Any:
        return self._controller().remove_files(*args, **kwargs)

    def apply_channel_selection(self, channels: list[str]) -> Any:
        return self._controller().apply_channel_selection(channels)

    def get_runtime_diagnostics(self) -> Any:
        return self._controller().get_runtime_diagnostics()

    def get_event_info(self) -> Any:
        return self._controller().get_event_info()

    def get_smart_filter_suggestions(self, *args: Any, **kwargs: Any) -> Any:
        return self._controller().get_smart_filter_suggestions(*args, **kwargs)


class PreprocessControllerAdapter(LazyControllerAdapter):
    """Preprocess-controller surface used by application command services."""

    def __init__(self, study: Study) -> None:
        super().__init__(study, "preprocess")

    def _controller(self) -> _PreprocessControllerPort:
        return cast(_PreprocessControllerPort, self._resolve_controller())

    def get_runtime_diagnostics(self) -> Any:
        return self._controller().get_runtime_diagnostics()

    def is_epoched(self) -> bool:
        return bool(self._controller().is_epoched())

    def get_channel_names(self) -> Any:
        return self._controller().get_channel_names()

    def apply_filter(self, *args: Any, **kwargs: Any) -> Any:
        return self._controller().apply_filter(*args, **kwargs)

    def apply_resample(self, rate: float) -> Any:
        return self._controller().apply_resample(rate)

    def apply_normalization(self, method: str) -> Any:
        return self._controller().apply_normalization(method)

    def apply_rereference(self, channels: str | list[str]) -> Any:
        return self._controller().apply_rereference(channels)

    def apply_epoching(self, *args: Any, **kwargs: Any) -> Any:
        return self._controller().apply_epoching(*args, **kwargs)

    def batch_notifications(self) -> Any:
        return self._controller().batch_notifications()

    def apply_montage(self, *args: Any, **kwargs: Any) -> Any:
        return self._controller().apply_montage(*args, **kwargs)


class TrainingControllerAdapter(LazyControllerAdapter):
    """Training-controller surface used by application command services."""

    def __init__(self, study: Study) -> None:
        super().__init__(study, "training")
        self._read_model = _TrainingStateReadModel(study)

    def _controller(self) -> _TrainingControllerPort:
        return cast(_TrainingControllerPort, self._resolve_controller())

    def set_training_option(self, option: Any) -> Any:
        return self._controller().set_training_option(option)

    def set_model_holder(self, holder: Any) -> Any:
        return self._controller().set_model_holder(holder)

    def start_training(self, *args: Any, **kwargs: Any) -> Any:
        return self._controller().start_training(*args, **kwargs)

    def stop_training(self, *args: Any, **kwargs: Any) -> Any:
        return self._controller().stop_training(*args, **kwargs)

    def clear_history(self) -> Any:
        return self._controller().clear_history()

    def apply_data_splitting(self, generator: Any) -> Any:
        return self._controller().apply_data_splitting(generator)

    def clean_datasets(self, *args: Any, **kwargs: Any) -> Any:
        return self._controller().clean_datasets(*args, **kwargs)

    def is_training(self) -> bool:
        return self._read_model.is_training()

    def get_formatted_history(self) -> list[dict[str, Any]]:
        return self._read_model.get_formatted_history()

    def get_missing_requirements(self) -> list[str]:
        return self._read_model.get_missing_requirements()


class EvaluationControllerAdapter(LazyControllerAdapter):
    """Evaluation-controller surface used by analysis and state queries."""

    def __init__(self, study: Study) -> None:
        super().__init__(study, "evaluation")
        self._read_model = _EvaluationStateReadModel(study)

    def _controller(self) -> _EvaluationControllerPort:
        return cast(_EvaluationControllerPort, self._resolve_controller())

    def get_pooled_eval_result(self, *args: Any, **kwargs: Any) -> Any:
        return self._controller().get_pooled_eval_result(*args, **kwargs)

    def get_model_summary_str(self, *args: Any, **kwargs: Any) -> Any:
        return self._controller().get_model_summary_str(*args, **kwargs)

    def get_plans(self) -> list[Any]:
        return self._read_model.get_plans()


class VisualizationControllerAdapter(LazyControllerAdapter):
    """Visualization-controller surface used by analysis command services."""

    def __init__(self, study: Study) -> None:
        super().__init__(study, "visualization")

    def _controller(self) -> _VisualizationControllerPort:
        return cast(_VisualizationControllerPort, self._resolve_controller())

    def get_trainers(self) -> Any:
        return self._controller().get_trainers()

    def set_saliency_params(self, params: Any) -> Any:
        return self._controller().set_saliency_params(params)

    def get_saliency_params(self) -> Any:
        return self._controller().get_saliency_params()

    def get_averaged_record(self, trainer: Any) -> Any:
        return self._controller().get_averaged_record(trainer)
