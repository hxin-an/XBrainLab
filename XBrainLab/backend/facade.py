"""Unified facade providing a simplified, high-level API for the XBrainLab backend."""

import os
from typing import Any

import numpy as np

from XBrainLab.backend.application import (
    ApplicationService,
    AttachLabelsCommand,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    ErrorType,
    EvaluateCommand,
    GenerateDatasetCommand,
    LoadDataCommand,
    NewSessionCommand,
    PreprocessCommand,
    PreprocessOperation,
    ResetSessionCommand,
    SaliencyCommand,
    StopTrainingCommand,
    TrainCommand,
    VisualizeCommand,
)
from XBrainLab.backend.study import Study
from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.utils.mne_helper import get_montage_positions


class BackendFacade:
    """Unified facade for the XBrainLab backend.

    Provides a simplified, high-level API for data loading, preprocessing,
    training, and evaluation. Designed for use by LLM agents and headless scripts.

    Attributes:
        study: The underlying Study instance managing state.
        dataset: Controller for dataset operations.
        preprocess: Controller for preprocessing operations.
        training: Controller for training operations.
        evaluation: Controller for evaluation operations.

    """

    def __init__(
        self,
        study: Study | None = None,
        service: ApplicationService | None = None,
    ):
        """Initialize the backend stack.

        Args:
            study: Optional existing Study instance. If None, creates a new one.
            service: Optional existing application service. Used by tests or
                adapters that already own the command layer.

        """
        if service is not None:
            self.service = service
        else:
            self.service = ApplicationService(study if study is not None else Study())
        self.study = self.service.study
        # Use Study's cached controllers for singleton-like access
        # This ensures all components share the same controller instances
        self.dataset = self.service.dataset
        self.preprocess = self.service.preprocess
        self.training = self.service.training
        self.evaluation = self.service.evaluation

    def get_state(self):
        """Return the shared application state snapshot."""
        return self.service.get_state()

    def get_capabilities(self):
        """Return the backend-owned command capability policy."""
        return self.service.get_capabilities()

    @staticmethod
    def _raise_if_failed(result) -> None:
        if result.failed:
            if result.recoverable:
                raise ValueError(result.message)
            raise RuntimeError(result.message)

    # --- Dataset Operations ---
    def load_data(self, filepaths: list[str]) -> tuple[int, list[str]]:
        """Load raw data files.

        Args:
            filepaths: List of file paths to load.

        Returns:
            A tuple of (success_count, error_list).

        """
        result = self.service.execute(LoadDataCommand(paths=filepaths))
        if result.failed:
            errors = result.diagnostics.get("errors")
            if errors:
                return 0, list(errors)
            return 0, [result.message]
        return (
            int(result.diagnostics.get("success_count", 0)),
            list(result.diagnostics.get("errors", [])),
        )

    def attach_labels(self, mapping: dict[str, str]) -> int:
        """Attach label files to loaded data files.

        Args:
            mapping: Dict mapping ``{data_filename_or_path: label_filepath}``.

        Returns:
            The number of files that had labels successfully attached.

        """
        result = self.service.execute(AttachLabelsCommand(mapping=mapping))
        return int(result.diagnostics.get("success_count", 0))

    @staticmethod
    def _resolve_label_attachment_path(raw, mapping: dict[str, str]) -> str | None:
        """Resolve a label mapping entry for a raw file using path or basename."""
        filepath = raw.get_filepath()
        filename = raw.get_filename()

        return (
            mapping.get(filepath)
            or mapping.get(filename)
            or mapping.get(
                os.path.basename(filepath),
            )
        )

    @staticmethod
    def _build_default_label_name_map(label_map: dict[str, Any]) -> dict[Any, str]:
        """Create a default event-name map from non-timestamp labels."""
        event_name_map: dict[Any, str] = {}

        for labels in label_map.values():
            if (
                isinstance(labels, list)
                and len(labels) > 0
                and isinstance(labels[0], dict)
            ):
                continue

            for label in np.array(labels).flatten():
                normalized = label.item() if isinstance(label, np.generic) else label
                event_name_map.setdefault(normalized, str(normalized))

        return event_name_map

    def clear_data(self):
        """Clear all loaded data."""
        result = self.service.execute(ResetSessionCommand(confirmed=True))
        self._raise_if_failed(result)

    def new_session(self):
        """Clear current state and start a new single-backend session."""
        result = self.service.execute(NewSessionCommand(confirmed=True))
        self._raise_if_failed(result)

    def get_data_summary(self) -> dict:
        """Get a summary of loaded data.

        Returns:
            Dictionary containing file count and filenames.

        """
        data_list = self.dataset.get_loaded_data_list()

        summary = {
            "count": len(data_list),
            "files": [d.get_filename() for d in data_list],
        }

        if hasattr(self.dataset, "get_event_info"):
            summary.update(self.dataset.get_event_info())

        if hasattr(self.dataset, "get_runtime_diagnostics"):
            diagnostics = self.dataset.get_runtime_diagnostics()
            if diagnostics:
                summary.update(diagnostics)

        return summary

    def get_preprocess_diagnostics(self) -> dict:
        """Get runtime diagnostics for the current preprocess state."""
        if hasattr(self.preprocess, "get_runtime_diagnostics"):
            diagnostics = self.preprocess.get_runtime_diagnostics()
            if diagnostics:
                return diagnostics
        return {}

    # --- Preprocessing Operations ---
    def apply_filter(
        self,
        low_freq: float,
        high_freq: float,
        notch_freq: float | None = None,
    ):
        """Apply bandpass and optionally notch filter.

        Args:
            low_freq: Low cutoff frequency for the bandpass filter (Hz).
            high_freq: High cutoff frequency for the bandpass filter (Hz).
            notch_freq: Frequency to notch out (Hz), or None to skip.

        """
        result = self.service.execute(
            PreprocessCommand(
                operation=PreprocessOperation.BANDPASS,
                low_freq=low_freq,
                high_freq=high_freq,
                notch_freq=notch_freq,
            ),
        )
        self._raise_if_failed(result)

    def apply_notch_filter(self, freq: float):
        """Apply a notch filter at the specified frequency.

        Args:
            freq: The frequency (Hz) to notch out.

        """
        result = self.service.execute(
            PreprocessCommand(
                operation=PreprocessOperation.NOTCH,
                notch_freq=freq,
            ),
        )
        self._raise_if_failed(result)

    def resample_data(self, rate: int):
        """Resample data to the specified sampling rate.

        Args:
            rate: Target sampling rate in Hz.

        """
        result = self.service.execute(
            PreprocessCommand(operation=PreprocessOperation.RESAMPLE, rate=rate),
        )
        self._raise_if_failed(result)

    def normalize_data(self, method: str):
        """Apply normalization to the data.

        Args:
            method: Normalization method name.

        """
        result = self.service.execute(
            PreprocessCommand(operation=PreprocessOperation.NORMALIZE, method=method),
        )
        self._raise_if_failed(result)

    def set_reference(self, method: str):
        """Set the EEG reference.

        Args:
            method: Reference method — ``"average"`` or a specific channel name.

        """
        result = self.service.execute(
            PreprocessCommand(operation=PreprocessOperation.REREFERENCE, method=method),
        )
        self._raise_if_failed(result)

    def select_channels(self, channels: list[str]):
        """Select a subset of EEG channels to keep.

        Args:
            channels: List of channel names to retain.

        """
        result = self.service.execute(
            PreprocessCommand(
                operation=PreprocessOperation.SELECT_CHANNELS,
                channels=channels,
            ),
        )
        self._raise_if_failed(result)

    def set_montage(self, montage_name: str) -> str:
        """Set EEG channel positions using a standard montage with fuzzy matching.

        Args:
            montage_name: Name of a standard MNE montage (e.g., ``"standard_1020"``).

        Returns:
            Status string describing the result of the montage application.

        """
        data_list = self.dataset.get_loaded_data_list()
        target_info = None
        if self.training.has_epoch_data():
            target_info = self.training.get_epoch_data().get_mne().info
        elif data_list:
            target_info = data_list[0].get_mne().info

        if not target_info:
            return "Error: No data loaded to apply montage."

        try:
            # Get Standard Positions
            loaded_positions = get_montage_positions(montage_name)
            if not loaded_positions:
                return f"Error: Failed to load montage '{montage_name}'"

            ch_pos_dict = loaded_positions["ch_pos"]
            current_chs = target_info["ch_names"]

            mapped_chs = []
            mapped_positions = []
            montage_lookup = {k.lower(): k for k in ch_pos_dict}

            for ch in current_chs:
                clean_ch = (
                    ch.lower()
                    .replace("eeg", "")
                    .replace("ref", "")
                    .replace("-", "")
                    .strip()
                )
                real_name = None
                if ch.lower() in montage_lookup:
                    real_name = montage_lookup[ch.lower()]
                elif clean_ch in montage_lookup:
                    real_name = montage_lookup[clean_ch]

                if real_name:
                    mapped_chs.append(ch)
                    mapped_positions.append(tuple(ch_pos_dict[real_name]))

            if not mapped_chs:
                return f"Request: Verify Montage '{montage_name}'"

            if len(mapped_chs) < len(current_chs):
                return (
                    f"Request: Verify Montage '{montage_name}' "
                    f"(Only {len(mapped_chs)}/{len(current_chs)} channels matched)"
                )

            self.study.set_channels(mapped_chs, mapped_positions)
            return f"Set Montage '{montage_name}' (Matched {len(mapped_chs)} channels)"

        except Exception as e:
            logger.error("SetMontage failed", exc_info=True)
            return f"SetMontage failed: {e!s}"

    # --- Epoching ---
    def epoch_data(
        self,
        t_min: float,
        t_max: float,
        baseline: list[float] | None = None,
        event_ids: list[str] | None = None,
    ):
        """Slice continuous data into epochs around events.

        Args:
            t_min: Start time of the epoch relative to the event (seconds).
            t_max: End time of the epoch relative to the event (seconds).
            baseline: Start and end times for baseline correction, or None.
            event_ids: List of event names to keep, or None for all events.

        """
        result = self.service.execute(
            CreateEpochCommand(
                t_min=t_min,
                t_max=t_max,
                baseline=baseline,
                event_ids=event_ids,
            ),
        )
        self._raise_if_failed(result)

    # --- Training Configuration ---
    def generate_dataset(
        self,
        test_ratio: float = 0.2,
        val_ratio: float = 0.2,
        split_strategy: str = "subject",
        training_mode: str = "individual",
    ):
        """Configure how the dataset is split and generated for training.

        Args:
            test_ratio: Fraction of data reserved for testing.
            val_ratio: Fraction of training data reserved for validation.
            split_strategy: Split granularity — ``"trial"``, ``"session"``,
                or ``"subject"``.
            training_mode: Training paradigm — ``"individual"`` or ``"group"``.

        """
        result = self.service.execute(
            GenerateDatasetCommand(
                test_ratio=test_ratio,
                val_ratio=val_ratio,
                split_strategy=split_strategy,
                training_mode=training_mode,
            ),
        )
        self._raise_if_failed(result)

    def set_model(self, model_name: str):
        """Select a model architecture by name.

        Args:
            model_name: Model name (case-insensitive). Supported values:
                ``"eegnet"``, ``"sccnet"``, ``"shallowconvnet"``.

        Raises:
            ValueError: If the model name is not recognized.

        """
        result = self.service.execute(
            ConfigureTrainingCommand(model_name=model_name),
        )
        self._raise_if_failed(result)

    def configure_training(
        self,
        epoch: int,
        batch_size: int,
        learning_rate: float,
        repeat: int = 1,
        device: str = "auto",
        optimizer: str = "adam",
        save_checkpoints_every: int = 0,
        output_dir: str = "./output",
    ):
        """Set training hyperparameters.

        Args:
            epoch: Number of training epochs.
            batch_size: Mini-batch size.
            learning_rate: Learning rate for the optimizer.
            repeat: Number of times to repeat the experiment.
            device: Device string — ``"cpu"``, ``"auto"``, or a CUDA device.
            optimizer: Optimizer name — ``"adam"``, ``"sgd"``, or ``"adamw"``.
            save_checkpoints_every: Save a checkpoint every *N* epochs
                (0 to disable).
            output_dir: Directory for saving training outputs.

        """
        result = self.service.execute(
            ConfigureTrainingCommand(
                epoch=epoch,
                batch_size=batch_size,
                learning_rate=learning_rate,
                repeat=repeat,
                device=device,
                optimizer=optimizer,
                save_checkpoints_every=save_checkpoints_every,
                output_dir=output_dir,
            ),
        )
        self._raise_if_failed(result)

    # --- Training Execution ---
    def run_training(self):
        """Start training (threaded)."""
        result = self.service.execute(TrainCommand())
        self._raise_if_failed(result)

    def stop_training(self):
        """Stop the current training run."""
        result = self.service.execute(StopTrainingCommand())
        if result.failed and result.error_type == ErrorType.PRECONDITION:
            return
        self._raise_if_failed(result)

    def is_training(self) -> bool:
        """Check whether training is currently running.

        Returns:
            True if training is active, False otherwise.

        """
        return self.training.is_training()

    # --- Evaluation ---
    def get_latest_results(self) -> dict:
        """Get results from the latest training run.

        Returns:
            Dictionary with plan counts, run counts, and training status.

        """
        result = self.service.execute(EvaluateCommand())
        diagnostics = dict(result.diagnostics)
        if result.ok and diagnostics.get("plan_count", 0) == 0:
            return {"status": "no_plans"}

        plans = diagnostics.get("plans", [])
        total_runs = sum(
            int(plan.get("run_count", 0)) for plan in plans if isinstance(plan, dict)
        )
        return {
            "status": "ok" if result.ok else "failed",
            "total_plans": int(diagnostics.get("plan_count", 0)),
            "total_runs": total_runs,
            "finished_runs": int(diagnostics.get("finished_run_count", 0)),
            "training_active": self.is_training(),
            "plans": plans,
            "available": bool(diagnostics.get("available", False)),
            "application_diagnostics": diagnostics,
        }

    def get_visualization_summary(self, view: str | None = None) -> dict:
        """Return a service-backed visualization readiness summary."""
        result = self.service.execute(VisualizeCommand(view=view))
        diagnostics = dict(result.diagnostics)
        diagnostics["status"] = "ok" if result.ok else "failed"
        return diagnostics

    def get_saliency_summary(self) -> dict:
        """Return service-backed saliency readiness and configuration."""
        result = self.service.execute(SaliencyCommand())
        diagnostics = dict(result.diagnostics)
        diagnostics["status"] = "ok" if result.ok else "failed"
        return diagnostics
