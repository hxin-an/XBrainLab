"""Unified facade providing a simplified, high-level API for the XBrainLab backend."""

import os

import numpy as np
import torch

# Imports for constructing backend objects from primitives
from XBrainLab.backend.dataset import (
    DataSplitter,
    DataSplittingConfig,
    SplitByType,
    SplitUnit,
    TrainingType,
    ValSplitByType,
)
from XBrainLab.backend.load_data.label_loader import load_label_file
from XBrainLab.backend.model_base.EEGNet import EEGNet
from XBrainLab.backend.model_base.SCCNet import SCCNet
from XBrainLab.backend.model_base.ShallowConvNet import ShallowConvNet
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import ModelHolder, TrainingEvaluation, TrainingOption
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

    def __init__(self, study: Study | None = None):
        """Initialize the backend stack.

        Args:
            study: Optional existing Study instance. If None, creates a new one.
        """
        self.study = study if study is not None else Study()
        # Use Study's cached controllers for singleton-like access
        # This ensures all components share the same controller instances
        self.dataset = self.study.get_controller("dataset")
        self.preprocess = self.study.get_controller("preprocess")
        self.training = self.study.get_controller("training")
        self.evaluation = self.study.get_controller("evaluation")

    # --- Dataset Operations ---
    def load_data(self, filepaths: list[str]) -> tuple[int, list[str]]:
        """Load raw data files.

        Args:
            filepaths: List of file paths to load.

        Returns:
            A tuple of (success_count, error_list).
        """
        return self.dataset.import_files(filepaths)

    def attach_labels(self, mapping: dict[str, str]) -> int:
        """Attach label files to loaded data files.

        Args:
            mapping: Dict mapping ``{data_filename: label_filepath}``.

        Returns:
            The number of files that had labels successfully attached.
        """

        success_count = 0
        data_list = self.dataset.get_loaded_data_list()

        for raw in data_list:
            base_name = os.path.basename(raw.filepath)
            label_path = mapping.get(base_name)

            if not label_path:
                continue

            try:
                labels = load_label_file(label_path)

                # Convert 1D labels to MNE events format (n, 3)
                # Columns: onset (sample), 0, event_id
                n_labels = len(labels)
                events = np.zeros((n_labels, 3), dtype=int)
                events[:, 0] = np.arange(n_labels)  # placeholder onset
                events[:, 2] = labels

                # Build event_id dict from unique labels
                unique_labels = np.unique(labels)
                event_id = {str(label): int(label) for label in unique_labels}

                # Use proper setter
                raw.set_event(events, event_id)
                raw.set_labels_imported(True)
                success_count += 1

            except Exception as e:
                logger.error(
                    f"Failed to attach label for {base_name}: {e}", exc_info=True
                )

        if success_count > 0:
            self.dataset.notify("data_changed")

        return success_count

    def clear_data(self):
        """Clear all loaded data."""
        self.dataset.clean_dataset()

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

        return summary

    # --- Preprocessing Operations ---
    def apply_filter(
        self, low_freq: float, high_freq: float, notch_freq: float | None = None
    ):
        """Apply bandpass and optionally notch filter.

        Args:
            low_freq: Low cutoff frequency for the bandpass filter (Hz).
            high_freq: High cutoff frequency for the bandpass filter (Hz).
            notch_freq: Frequency to notch out (Hz), or None to skip.
        """
        notch_list = [notch_freq] if notch_freq else None
        self.preprocess.apply_filter(low_freq, high_freq, notch_list)

    def apply_notch_filter(self, freq: float):
        """Apply a notch filter at the specified frequency.

        Args:
            freq: The frequency (Hz) to notch out.
        """
        self.preprocess.apply_filter(None, None, [freq])

    def resample_data(self, rate: int):
        """Resample data to the specified sampling rate.

        Args:
            rate: Target sampling rate in Hz.
        """
        self.preprocess.apply_resample(rate)

    def normalize_data(self, method: str):
        """Apply normalization to the data.

        Args:
            method: Normalization method name.
        """
        self.preprocess.apply_normalization(method)

    def set_reference(self, method: str):
        """Set the EEG reference.

        Args:
            method: Reference method — ``"average"`` or a specific channel name.
        """
        if method == "average":
            self.preprocess.apply_rereference("average")
        else:
            self.preprocess.apply_rereference([method])

    def select_channels(self, channels: list[str]):
        """Select a subset of EEG channels to keep.

        Args:
            channels: List of channel names to retain.
        """
        self.dataset.apply_channel_selection(channels)

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
        self.preprocess.apply_epoching(baseline, event_ids, t_min, t_max)

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
        s_strat = SplitByType.TRIAL
        if split_strategy.lower() == "session":
            s_strat = SplitByType.SESSION
        elif split_strategy.lower() == "subject":
            s_strat = SplitByType.SUBJECT

        t_mode = TrainingType.IND
        if training_mode.lower() == "group":
            t_mode = TrainingType.FULL

        # Construct Splitters
        test_splitter = DataSplitter(
            split_type=s_strat,
            value_var=str(test_ratio),
            split_unit=SplitUnit.RATIO,
        )

        # For validation, we use the corresponding VAL enum
        v_strat_val = ValSplitByType.TRIAL
        if s_strat == SplitByType.SESSION:
            v_strat_val = ValSplitByType.SESSION
        elif s_strat == SplitByType.SUBJECT:
            v_strat_val = ValSplitByType.SUBJECT

        val_splitter = DataSplitter(
            split_type=v_strat_val,
            value_var=str(val_ratio),
            split_unit=SplitUnit.RATIO,
        )

        config = DataSplittingConfig(
            train_type=t_mode,
            is_cross_validation=False,
            val_splitter_list=[val_splitter],
            test_splitter_list=[test_splitter],
        )

        generator = self.study.get_datasets_generator(config)

        self.training.apply_data_splitting(generator)

    def set_model(self, model_name: str):
        """Select a model architecture by name.

        Args:
            model_name: Model name (case-insensitive). Supported values:
                ``"eegnet"``, ``"sccnet"``, ``"shallowconvnet"``.

        Raises:
            ValueError: If the model name is not recognized.
        """
        models_map = {
            "eegnet": EEGNet,
            "sccnet": SCCNet,
            "shallowconvnet": ShallowConvNet,
        }

        model_class = models_map.get(model_name.lower())
        if not model_class:
            raise ValueError(f"Unknown model architecture: {model_name}")

        holder = ModelHolder(model_class, {})
        self.training.set_model_holder(holder)

    def configure_training(
        self,
        epoch: int,
        batch_size: int,
        learning_rate: float,
        repeat: int = 1,
        device: str = "auto",
        optimizer: str = "adam",
        save_checkpoints_every: int = 0,
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
        """
        # Resolve Optimizer
        optimizers_map = {
            "adam": torch.optim.Adam,
            "sgd": torch.optim.SGD,
            "adamw": torch.optim.AdamW,
        }
        optim_class = optimizers_map.get(optimizer.lower(), torch.optim.Adam)

        # Resolve Device
        use_cpu = device.lower() == "cpu"
        gpu_idx = 0 if not use_cpu else None

        option = TrainingOption(
            output_dir=getattr(self.study, "output_dir", "./output"),
            optim=optim_class,
            optim_params={},
            use_cpu=use_cpu,
            gpu_idx=gpu_idx,
            epoch=epoch,
            bs=batch_size,
            lr=learning_rate,
            checkpoint_epoch=save_checkpoints_every,
            evaluation_option=TrainingEvaluation.LAST_EPOCH,
            repeat_num=repeat,
        )

        self.training.set_training_option(option)

    # --- Training Execution ---
    def run_training(self):
        """Start training (threaded)."""
        self.training.start_training()

    def stop_training(self):
        """Stop the current training run."""
        self.training.stop_training()

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
        plans = self.evaluation.get_plans()
        if not plans:
            return {"status": "no_plans"}

        finished_runs = 0
        total_runs = 0
        for plan in plans:
            runs = plan.get_plans()
            total_runs += len(runs)
            finished_runs += len([r for r in runs if r.is_finished()])

        return {
            "total_plans": len(plans),
            "total_runs": total_runs,
            "finished_runs": finished_runs,
            "training_active": self.is_training(),
        }
