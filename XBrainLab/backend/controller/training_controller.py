"""UI compatibility adapter over the Study-owned training service."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any, ClassVar

from XBrainLab.backend.services.training_state_service import TrainingStateService
from XBrainLab.backend.utils.observer import Observable

if TYPE_CHECKING:
    from XBrainLab.backend.study import Study
    from XBrainLab.backend.training import Trainer


class TrainingController(Observable):
    """Expose the legacy UI controller API over shared training ownership."""

    events: ClassVar[list[str]] = [
        "training_started",
        "training_started_state",
        "training_stopped",
        "training_terminal_published",
        "training_analysis_published",
        "training_updated",
        "config_changed",
        "history_cleared",
    ]

    def __init__(self, study: Study) -> None:
        super().__init__()
        self._study = study
        shared_service = getattr(study, "training_state_service", None)
        self._training_state = (
            shared_service
            if isinstance(shared_service, TrainingStateService)
            else TrainingStateService(study)
        )
        self._service_relays = {
            event_name: partial(self._relay_event, event_name)
            for event_name in self.events
        }
        for event_name, callback in self._service_relays.items():
            self._training_state.subscribe(event_name, callback)

    def _relay_event(self, event_name: str, *args: Any, **kwargs: Any) -> bool:
        return self.notify(event_name, *args, **kwargs)

    def is_training(self) -> bool:
        return self._training_state.is_training()

    def start_training(self, *, append: bool = True, interactive: bool = True) -> int:
        return self._training_state.start_training(
            append=append,
            interactive=interactive,
        )

    def stop_training(self) -> None:
        self._training_state.stop_training()

    def shutdown(self) -> None:
        self._training_state.shutdown()

    def wait_for_terminal_notification(
        self,
        generation: int | None = None,
        *,
        timeout: float | None = None,
    ) -> bool:
        return self._training_state.wait_for_terminal_notification(
            generation,
            timeout=timeout,
        )

    def wait_until_restart_safe(self, *, timeout: float | None = None) -> bool:
        return self._training_state.wait_until_restart_safe(timeout=timeout)

    def cancel_terminal_notification_waits(self, reason: str) -> None:
        self._training_state.cancel_terminal_notification_waits(reason)

    def clear_history(self) -> None:
        self._training_state.clear_history()

    def get_trainer(self) -> Trainer | None:
        return self._training_state.get_trainer()

    def get_progress_text(self) -> str:
        return self._training_state.get_progress_text()

    def get_formatted_history(self) -> list[dict[str, Any]]:
        return self._training_state.get_formatted_history()

    def validate_ready(self) -> bool:
        return self._training_state.validate_ready()

    def get_missing_requirements(self) -> list[str]:
        return self._training_state.get_missing_requirements()

    def has_loaded_data(self) -> bool:
        return self._training_state.has_loaded_data()

    def has_epoch_data(self) -> bool:
        return self._training_state.has_epoch_data()

    def get_epoch_data(self) -> Any:
        return self._training_state.get_epoch_data()

    def has_datasets(self) -> bool:
        return self._training_state.has_datasets()

    def has_model(self) -> bool:
        return self._training_state.has_model()

    def has_training_option(self) -> bool:
        return self._training_state.has_training_option()

    def clean_datasets(self, force_update: bool = False) -> None:
        self._training_state.clean_datasets(force_update=force_update)

    def apply_data_splitting(self, generator: Any) -> None:
        self._training_state.apply_data_splitting(generator)

    def set_model_holder(self, holder: Any) -> None:
        self._training_state.set_model_holder(holder)

    def set_training_option(self, option: Any) -> None:
        self._training_state.set_training_option(option)

    def apply_configuration(
        self,
        *,
        model_holder: Any | None,
        training_option: Any | None,
        update_model: bool,
        update_option: bool,
    ) -> None:
        self._training_state.apply_configuration(
            model_holder=model_holder,
            training_option=training_option,
            update_model=update_model,
            update_option=update_option,
        )

    def get_training_option(self) -> Any:
        return self._training_state.get_training_option()

    def get_resource_preflight_context(self) -> dict[str, Any]:
        return self._training_state.get_resource_preflight_context()

    def get_model_holder(self) -> Any:
        return self._training_state.get_model_holder()

    def get_dataset_generator(self) -> Any:
        return self._training_state.get_dataset_generator()

    def get_loaded_data_list(self) -> list[Any]:
        return self._training_state.get_loaded_data_list()

    def get_preprocessed_data_list(self) -> list[Any]:
        return self._training_state.get_preprocessed_data_list()
