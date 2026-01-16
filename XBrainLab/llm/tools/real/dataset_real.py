import os
from typing import Any

from XBrainLab.backend.dataset import (
    DataSplitter,
    DataSplittingConfig,
    SplitByType,
    SplitUnit,
    TrainingType,
    ValSplitByType,
)
from XBrainLab.backend.load_data.factory import RawDataLoaderFactory
from XBrainLab.backend.load_data.label_loader import load_label_file

from ..definitions.dataset_def import (
    BaseAttachLabelsTool,
    BaseClearDatasetTool,
    BaseGenerateDatasetTool,
    BaseGetDatasetInfoTool,
    BaseListFilesTool,
    BaseLoadDataTool,
)


class RealListFilesTool(BaseListFilesTool):
    def execute(self, study: Any, directory: str, pattern: str | None = None) -> str:
        if not os.path.exists(directory):
            return f"Error: Directory '{directory}' does not exist."

        try:
            files = []
            for f in os.listdir(directory):
                # Simple pattern logic (extension based)
                if pattern and pattern.startswith("*") and not f.endswith(pattern[1:]):
                    continue
                files.append(f)
            return str(files)
        except Exception as e:
            return f"Error listing files: {e!s}"


class RealLoadDataTool(BaseLoadDataTool):
    def execute(self, study: Any, paths: list[str]) -> str:
        if not paths:
            return "Error: paths list cannot be empty."

        loaded_count = 0
        errors = []
        raw_list = []

        # NOTE: Backend expects 'Raw' objects, not paths if calling
        # set_loaded_data_list directly?
        # No, LoadData logic is usually: Load Raw -> set to study
        # study.load_raw_data_list? study.py doesn't have it.
        # study.set_loaded_data_list expects List[Raw].
        # So we must USE FACTORY directly here.

        for p in paths:
            try:
                # We need to make sure loader is registered
                # Assuming raw_data_loader is imported somewhere in entry point
                raw = RawDataLoaderFactory.load(p)
                if raw:
                    raw_list.append(raw)
                    loaded_count += 1
                else:
                    errors.append(f"{p}: Loaded None")
            except Exception as e:  # noqa: PERF203
                errors.append(f"{p}: {e!s}")

        if raw_list:
            study.set_loaded_data_list(raw_list, force_update=True)
            return f"Successfully loaded {loaded_count} files. Errors: {errors}"
        else:
            return f"Failed to load any data. Errors: {errors}"


class RealAttachLabelsTool(BaseAttachLabelsTool):
    def execute(
        self, study: Any, mapping: dict, label_format: str | None = None
    ) -> str:
        # Check if we have loaded data
        if not study.loaded_data_list:
            return "Error: No raw data loaded in Study."

        success_count = 0

        for raw in study.loaded_data_list:
            # Find filename in mapping
            base_name = os.path.basename(raw.filepath)
            label_path = mapping.get(base_name)

            if not label_path:
                continue

            try:
                # Load label
                events = load_label_file(label_path)
                raw.events = events
                success_count += 1

            except Exception as e:
                return f"Error attaching labels for {base_name}: {e!s}"

        return f"Attached labels to {success_count} files."


class RealClearDatasetTool(BaseClearDatasetTool):
    def execute(self, study: Any) -> str:
        study.clean_raw_data(force_update=True)
        return "Dataset cleared."


class RealGetDatasetInfoTool(BaseGetDatasetInfoTool):
    def execute(self, study: Any) -> str:
        # Construct summary string
        if not study.loaded_data_list:
            return "No data loaded."

        info = [f"Loaded {len(study.loaded_data_list)} files."]
        # Pick first one for details
        first = study.loaded_data_list[0]

        # Assuming Raw wrapper has some info
        # MNE Raw: first.raw.info

        if hasattr(first, "raw") and first.raw is not None:
            mne_info = first.raw.info
            info.append(f"Sample Rate: {mne_info['sfreq']} Hz")
            info.append(f"Channels: {len(mne_info['ch_names'])}")

        return "\n".join(info)


class RealGenerateDatasetTool(BaseGenerateDatasetTool):
    def execute(
        self,
        study: Any,
        test_ratio: float = 0.2,
        val_ratio: float = 0.2,
        split_strategy: str = "trial",
        training_mode: str = "individual",
    ) -> str:
        try:
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

            generator = study.get_datasets_generator(config)
            datasets = generator.generate()
            study.set_datasets(datasets)

            return (
                f"Dataset successfully generated. Count: {len(datasets)} "
                f"(Test: {test_ratio}, Val: {val_ratio})."
            )

        except Exception as e:
            return f"Dataset generation failed: {e!s}"
