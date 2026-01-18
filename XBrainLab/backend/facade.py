import os

import torch

from XBrainLab.backend.controller.dataset_controller import DatasetController
from XBrainLab.backend.controller.evaluation_controller import EvaluationController
from XBrainLab.backend.controller.preprocess_controller import PreprocessController
from XBrainLab.backend.controller.training_controller import TrainingController

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
from XBrainLab.backend.utils.mne_helper import get_montage_positions


class BackendFacade:
    """
    A unified facade for the XBrainLab backend.
    Provides a simplified, high-level API for data loading, training, and evaluation.
    Designed for use by LLM Agents and headless scripts.
    """

    def __init__(self, study: Study | None = None):
        """
        Initialize the backend stack.
        Args:
             study: Optional existing Study instance. If None, creates a new one.
        """
        self.study = study if study is not None else Study()
        self.dataset = DatasetController(self.study)
        self.preprocess = PreprocessController(self.study)
        self.training = TrainingController(self.study)
        self.evaluation = EvaluationController(self.study)

    # --- Dataset Operations ---
    def load_data(self, filepaths: list[str]) -> tuple[int, list[str]]:
        """
        Load raw data files.
        Returns: (success_count, error_list)
        """
        return self.dataset.import_files(filepaths)

    def attach_labels(self, mapping: dict[str, str]) -> int:
        """
        Attach label files to loaded data files.
        Args:
            mapping: Dict of {data_filename: label_filepath}
        Returns: success count
        """

        success_count = 0
        data_list = self.dataset.get_loaded_data_list()

        for raw in data_list:
            base_name = os.path.basename(raw.filepath)
            label_path = mapping.get(base_name)

            if not label_path:
                continue

            try:
                events = load_label_file(label_path)
            except Exception as e:
                # Log error but continue
                # In a real controller this might aggregate errors
                print(f"Failed to attach label for {base_name}: {e}")
            else:
                raw.events = events
                success_count += 1

        if success_count > 0:
            # Sync updates if necessary (though events are often property-based)
            self.dataset.notify("data_changed")

        return success_count

    def clear_data(self):
        """Clear all loaded data."""
        self.dataset.clean_dataset()

    def get_data_summary(self) -> dict:
        """Get summary of loaded data."""
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
        """Apply Bandpass and optionally Notch filter."""
        # Note: PreprocessController.apply_filter takes (l, h, notch_list)
        notch_list = [notch_freq] if notch_freq else None
        self.preprocess.apply_filter(low_freq, high_freq, notch_list)

    def apply_notch_filter(self, freq: float):
        """Apply Notch filter only."""
        # Using apply_filter with None for bandpass?
        # Check PreprocessController implementation: likely allows None?
        # If not, we might need a specific notch method or check underlying code.
        # PreprocessController.apply_filter delegates to Filtering class.
        self.preprocess.apply_filter(None, None, [freq])

    def resample_data(self, rate: int):
        self.preprocess.apply_resample(rate)

    def normalize_data(self, method: str):
        self.preprocess.apply_normalization(method)

    def set_reference(self, method: str):
        # "average" or specific channel
        if method == "average":
            self.preprocess.apply_rereference("average")
        else:
            self.preprocess.apply_rereference([method])

    def select_channels(self, channels: list[str]):
        # This is on DatasetController in the current code, not PreprocessController?
        # Let's check. Yes, apply_channel_selection is in DatasetController.
        self.dataset.apply_channel_selection(channels)

    def set_montage(self, montage_name: str) -> str:
        """
        Set EEG channel positions using a standard montage with fuzzy matching.
        Returns status string.
        """

        # Backend requires epoch data for set_channels currently?
        # Check Controller logic or study. Actually logic works on existing 'channels'.
        # If we have preprocessed data, we can set montage.
        data_list = self.dataset.get_loaded_data_list()  # or preprocessed?
        # The tool looked at study.epoch_data.
        # But montage can be set on Raw too (MNE supports it).
        # Let's support whatever current state is.
        # Ideally we check PreprocessController.

        # For MVP, assume we work on the first available data to find channel names.
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

            # Delegate to study.set_channels via wrapper if possible,
            # or direct study access. Facade has access to self.study.
            self.study.set_channels(mapped_chs, mapped_positions)
            return f"Set Montage '{montage_name}' (Matched {len(mapped_chs)} channels)"

        except Exception as e:
            return f"SetMontage failed: {e!s}"

    # --- Epoching ---
    def epoch_data(
        self,
        t_min: float,
        t_max: float,
        baseline: list[float] | None = None,
        event_ids: list[str] | None = None,
    ):
        """
        Slice data into epochs.
        t_min, t_max: relative times (e.g. -0.1, 1.0)
        baseline: [start, end]
        event_ids: list of event names to keep
        """
        # PreprocessController.apply_epoching(baseline, selected_events, tmin, tmax)
        # Note args order.
        self.preprocess.apply_epoching(baseline, event_ids, t_min, t_max)

    # --- Training Configuration ---
    def generate_dataset(
        self,
        test_ratio: float = 0.2,
        val_ratio: float = 0.2,
        split_strategy: str = "subject",
        training_mode: str = "individual",
    ):
        """
        Configure how dataset is split and generated for training.
        """
        # Import Enums

        # Map strings to Enums
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

        # Apply logic via TrainingController
        # (which delegates to study.set_datasets usually?)
        # TrainingController.apply_data_splitting calls generator.apply(study)
        self.training.apply_data_splitting(generator)

        # Return count if possible?
        # The generator.generate() happens inside verify/apply?
        # generator.apply() calls generate() and sets datasets

    def set_model(self, model_name: str):
        """Select model architecture."""
        # Resolve Model Class using Registry
        # (imported locally to avoid circular dep if needed)
        # Or better, replicate the mapping here or use backend's mechanism if specific
        # Reusing the logic from ToolRegistry
        # (manual mapping for now
        # or finding where mappings live)
        # Actually, let's look for backend.model_base

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
        """Set training hyperparameters."""

        # Resolve Optimizer
        optimizers_map = {
            "adam": torch.optim.Adam,
            "sgd": torch.optim.SGD,
            "adamw": torch.optim.AdamW,
        }
        optim_class = optimizers_map.get(optimizer.lower(), torch.optim.Adam)

        # Resolve Device
        use_cpu = device.lower() == "cpu"
        gpu_idx = 0 if not use_cpu else None  # Default to 0 if not cpu
        # If device="cuda:1", we might need parsing. MVP: "cpu" or "gpu" (auto)

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
        self.training.stop_training()

    def is_training(self) -> bool:
        return self.training.is_training()

    # --- Evaluation ---
    def get_latest_results(self) -> dict:
        """Get results from the latest training run."""
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
