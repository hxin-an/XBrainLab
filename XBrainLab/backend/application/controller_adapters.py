"""Typed lazy command adapters from ApplicationService to workflow controllers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from typing import Any, Protocol, cast

from XBrainLab.backend.study import Study


class _ObservableControllerPort(Protocol):
    def notify(self, event: str, *args: Any, **kwargs: Any) -> Any: ...
    def subscribe(self, event: str, callback: Any) -> Any: ...
    def unsubscribe(self, event: str, callback: Any) -> Any: ...


class _DatasetControllerPort(_ObservableControllerPort, Protocol):
    loaded: Any
    imported_paths: Any

    def clean_dataset(self) -> Any: ...
    def import_files(self, paths: list[str]) -> tuple[int, list[str]]: ...
    def get_loaded_data_list(self) -> list[Any]: ...
    def apply_labels_batch(
        self,
        target_files: Sequence[Any],
        label_map: Mapping[str, Any],
        file_mapping: Mapping[str, str],
        mapping: Mapping[str, Any],
        selected_event_names: Sequence[str],
    ) -> int: ...
    def update_metadata(
        self,
        index: int,
        subject: str | None = None,
        session: str | None = None,
    ) -> None: ...
    def update_metadata_batch(
        self,
        updates: Sequence[tuple[int, str | None, str | None]],
    ) -> int: ...
    def apply_smart_parse(self, results: Mapping[str, tuple[str, str]]) -> int: ...
    def remove_files(self, indices: Sequence[int]) -> None: ...
    def apply_channel_selection(self, channels: list[str]) -> bool: ...
    def get_runtime_diagnostics(self) -> dict[str, Any]: ...
    def get_event_info(self) -> dict[str, Any]: ...
    def get_smart_filter_suggestions(
        self,
        data: Any,
        target_count: int,
    ) -> list[int]: ...


class _PreprocessControllerPort(_ObservableControllerPort, Protocol):
    def get_preprocessed_data_list(self) -> list[Any]: ...
    def get_runtime_diagnostics(self) -> dict[str, Any]: ...
    def is_epoched(self) -> bool: ...
    def get_channel_names(self) -> list[str]: ...
    def apply_filter(
        self,
        l_freq: float | None,
        h_freq: float | None,
        notch_freqs: Sequence[float] | None = None,
    ) -> bool: ...
    def apply_resample(self, rate: float) -> bool: ...
    def apply_normalization(self, method: str) -> bool: ...
    def apply_rereference(self, channels: str | list[str]) -> bool: ...
    def apply_standard_pipeline(
        self,
        *,
        l_freq: float,
        h_freq: float,
        notch_freq: float | None = None,
        rate: float | None = None,
        ref_channels: str | list[str] | None = None,
        normalization: str | None = None,
    ) -> bool: ...
    def apply_epoching(
        self,
        baseline: tuple[float | None, float | None] | None,
        selected_events: Mapping[str, int],
        tmin: float,
        tmax: float,
    ) -> bool: ...
    def batch_notifications(self) -> AbstractContextManager[None]: ...
    def apply_montage(
        self,
        mapped_channels: list[str],
        mapped_positions: list[tuple[float, float, float]],
    ) -> None: ...


class _TrainingControllerPort(_ObservableControllerPort, Protocol):
    def set_training_option(self, option: Any) -> None: ...
    def set_model_holder(self, holder: Any) -> None: ...
    def apply_configuration(
        self,
        *,
        model_holder: Any | None,
        training_option: Any | None,
        update_model: bool,
        update_option: bool,
    ) -> None: ...
    def start_training(
        self,
        *,
        append: bool = True,
        interactive: bool = True,
    ) -> int: ...
    def clear_history(self) -> Any: ...
    def apply_data_splitting(self, generator: Any) -> Any: ...
    def clean_datasets(self, *args: Any, **kwargs: Any) -> Any: ...
    def is_training(self) -> bool: ...
    def wait_for_terminal_notification(
        self,
        generation: int | None = None,
        *,
        timeout: float | None = None,
    ) -> bool: ...
    def wait_until_restart_safe(self, *, timeout: float | None = None) -> bool: ...
    def cancel_terminal_notification_waits(self, reason: str) -> None: ...
    def get_progress_text(self) -> str: ...
    def get_formatted_history(self) -> list[dict[str, Any]]: ...


class _EvaluationControllerPort(_ObservableControllerPort, Protocol):
    def get_pooled_eval_result(self, plan: Any) -> tuple[Any, Any, dict[str, Any]]: ...
    def get_model_summary_str(self, plan: Any, record: Any | None = None) -> str: ...
    def get_plans(self) -> list[Any]: ...


class _VisualizationControllerPort(_ObservableControllerPort, Protocol):
    notifications_deferred: bool
    notification_batch_generation: int | None

    def get_trainers(self) -> Any: ...
    def batch_notifications(self) -> AbstractContextManager[None]: ...
    def consume_batched_delivery(
        self,
        event_name: str,
        generation: int,
    ) -> bool | None: ...
    def is_notification_batch_active(self, generation: int) -> bool: ...
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

    def subscribe(self, event: str, callback: Any) -> Any:
        """Subscribe application orchestration to one controller lifecycle event."""
        return self._observable_controller().subscribe(event, callback)

    def unsubscribe(self, event: str, callback: Any) -> Any:
        """Remove an application orchestration lifecycle subscription."""
        return self._observable_controller().unsubscribe(event, callback)


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

    def apply_labels_batch(
        self,
        target_files: Sequence[Any],
        label_map: Mapping[str, Any],
        file_mapping: Mapping[str, str],
        mapping: Mapping[str, Any],
        selected_event_names: Sequence[str],
    ) -> int:
        return self._controller().apply_labels_batch(
            target_files,
            label_map,
            file_mapping,
            mapping,
            selected_event_names,
        )

    def update_metadata(
        self,
        index: int,
        subject: str | None = None,
        session: str | None = None,
    ) -> None:
        return self._controller().update_metadata(index, subject, session)

    def update_metadata_batch(
        self,
        updates: Sequence[tuple[int, str | None, str | None]],
    ) -> int:
        return int(self._controller().update_metadata_batch(updates))

    def apply_smart_parse(self, results: Mapping[str, tuple[str, str]]) -> int:
        return self._controller().apply_smart_parse(results)

    def remove_files(self, indices: Sequence[int]) -> None:
        return self._controller().remove_files(indices)

    def apply_channel_selection(self, channels: list[str]) -> Any:
        return self._controller().apply_channel_selection(channels)

    def get_runtime_diagnostics(self) -> dict[str, Any]:
        return self._controller().get_runtime_diagnostics()

    def get_event_info(self) -> dict[str, Any]:
        return self._controller().get_event_info()

    def get_smart_filter_suggestions(
        self,
        data: Any,
        target_count: int,
    ) -> list[int]:
        return [
            int(item)
            for item in self._controller().get_smart_filter_suggestions(
                data,
                target_count,
            )
        ]


class PreprocessControllerAdapter(LazyControllerAdapter):
    """Preprocess-controller surface used by application command services."""

    def __init__(self, study: Study) -> None:
        super().__init__(study, "preprocess")

    def _controller(self) -> _PreprocessControllerPort:
        return cast(_PreprocessControllerPort, self._resolve_controller())

    def get_runtime_diagnostics(self) -> dict[str, Any]:
        return self._controller().get_runtime_diagnostics()

    def get_preprocessed_data_list(self) -> list[Any]:
        return self._controller().get_preprocessed_data_list()

    def is_epoched(self) -> bool:
        return bool(self._controller().is_epoched())

    def get_channel_names(self) -> list[str]:
        return self._controller().get_channel_names()

    def apply_filter(
        self,
        l_freq: float | None,
        h_freq: float | None,
        notch_freqs: Sequence[float] | None = None,
    ) -> bool:
        return self._controller().apply_filter(l_freq, h_freq, notch_freqs)

    def apply_resample(self, rate: float) -> Any:
        return self._controller().apply_resample(rate)

    def apply_normalization(self, method: str) -> Any:
        return self._controller().apply_normalization(method)

    def apply_rereference(self, channels: str | list[str]) -> Any:
        return self._controller().apply_rereference(channels)

    def apply_standard_pipeline(
        self,
        *,
        l_freq: float,
        h_freq: float,
        notch_freq: float | None = None,
        rate: float | None = None,
        ref_channels: str | list[str] | None = None,
        normalization: str | None = None,
    ) -> bool:
        return bool(
            self._controller().apply_standard_pipeline(
                l_freq=l_freq,
                h_freq=h_freq,
                notch_freq=notch_freq,
                rate=rate,
                ref_channels=ref_channels,
                normalization=normalization,
            )
        )

    def apply_epoching(
        self,
        baseline: tuple[float | None, float | None] | None,
        selected_events: Mapping[str, int],
        tmin: float,
        tmax: float,
    ) -> bool:
        return self._controller().apply_epoching(
            baseline,
            selected_events,
            tmin,
            tmax,
        )

    def batch_notifications(self) -> AbstractContextManager[None]:
        return self._controller().batch_notifications()

    def apply_montage(
        self,
        mapped_channels: list[str],
        mapped_positions: list[tuple[float, float, float]],
    ) -> None:
        return self._controller().apply_montage(mapped_channels, mapped_positions)


class TrainingControllerAdapter(LazyControllerAdapter):
    """Training-controller surface used by application command services."""

    def __init__(self, study: Study) -> None:
        super().__init__(study, "training")

    def _controller(self) -> _TrainingControllerPort:
        return cast(_TrainingControllerPort, self._resolve_controller())

    def set_training_option(self, option: Any) -> Any:
        return self._controller().set_training_option(option)

    def set_model_holder(self, holder: Any) -> Any:
        return self._controller().set_model_holder(holder)

    def apply_configuration(
        self,
        *,
        model_holder: Any | None,
        training_option: Any | None,
        update_model: bool,
        update_option: bool,
    ) -> Any:
        return self._controller().apply_configuration(
            model_holder=model_holder,
            training_option=training_option,
            update_model=update_model,
            update_option=update_option,
        )

    def start_training(self, *, append: bool = True, interactive: bool = True) -> int:
        return self._controller().start_training(
            append=append,
            interactive=interactive,
        )

    def clear_history(self) -> Any:
        return self._controller().clear_history()

    def apply_data_splitting(self, generator: Any) -> Any:
        return self._controller().apply_data_splitting(generator)

    def clean_datasets(self, *args: Any, **kwargs: Any) -> Any:
        return self._controller().clean_datasets(*args, **kwargs)

    def is_training(self) -> bool:
        return bool(self._controller().is_training())

    def wait_for_terminal_notification(
        self,
        generation: int | None = None,
        *,
        timeout: float | None = None,
    ) -> bool:
        """Wait until callbacks complete for one exact controller-admitted run."""
        return bool(
            self._controller().wait_for_terminal_notification(
                generation,
                timeout=timeout,
            ),
        )

    def wait_until_restart_safe(self, *, timeout: float | None = None) -> bool:
        """Wait outside command serialization for the old monitor to retire."""
        return bool(
            self._controller().wait_until_restart_safe(timeout=timeout),
        )

    def cancel_terminal_notification_waits(self, reason: str) -> None:
        """Wake pending run handoffs when application ownership is closing."""
        self._controller().cancel_terminal_notification_waits(reason)

    def get_progress_text(self) -> str:
        """Return the controller-owned terminal or in-progress status text."""
        return str(self._controller().get_progress_text() or "")

    def get_formatted_history(self) -> list[dict[str, Any]]:
        return list(self._controller().get_formatted_history())


class EvaluationControllerAdapter(LazyControllerAdapter):
    """Evaluation-controller surface used by analysis and state queries."""

    def __init__(self, study: Study) -> None:
        super().__init__(study, "evaluation")

    def _controller(self) -> _EvaluationControllerPort:
        return cast(_EvaluationControllerPort, self._resolve_controller())

    def get_pooled_eval_result(self, plan: Any) -> tuple[Any, Any, dict[str, Any]]:
        return self._controller().get_pooled_eval_result(plan)

    def get_model_summary_str(self, plan: Any, record: Any | None = None) -> str:
        return self._controller().get_model_summary_str(plan, record)

    def get_plans(self) -> list[Any]:
        return list(self._controller().get_plans())


class VisualizationControllerAdapter(LazyControllerAdapter):
    """Visualization-controller surface used by analysis command services."""

    def __init__(self, study: Study) -> None:
        super().__init__(study, "visualization")

    def _controller(self) -> _VisualizationControllerPort:
        return cast(_VisualizationControllerPort, self._resolve_controller())

    def get_trainers(self) -> Any:
        return self._controller().get_trainers()

    def batch_notifications(self) -> AbstractContextManager[None]:
        """Defer controller events until the Application command boundary exits."""
        return self._controller().batch_notifications()

    @property
    def notifications_deferred(self) -> bool:
        """Return whether the controller is holding one notification batch."""
        return bool(self._controller().notifications_deferred)

    @property
    def notification_batch_generation(self) -> int | None:
        """Return the generation currently holding deferred notifications."""
        return self._controller().notification_batch_generation

    def consume_batched_delivery(
        self,
        event_name: str,
        generation: int,
    ) -> bool | None:
        """Consume one exact deferred delivery result through the typed port."""
        return self._controller().consume_batched_delivery(event_name, generation)

    def is_notification_batch_active(self, generation: int) -> bool:
        """Return whether the exact command batch still owns delivery."""
        return bool(self._controller().is_notification_batch_active(generation))

    def set_saliency_params(self, params: Any) -> Any:
        return self._controller().set_saliency_params(params)

    def get_saliency_params(self) -> Any:
        return self._controller().get_saliency_params()

    def get_averaged_record(self, trainer: Any) -> Any:
        return self._controller().get_averaged_record(trainer)
