import os
from typing import Any

from XBrainLab.backend.facade import BackendFacade

from ..definitions.dataset_def import (
    BaseAttachLabelsTool,
    BaseClearDatasetTool,
    BaseGenerateDatasetTool,
    BaseGetDatasetInfoTool,
    BaseListFilesTool,
    BaseLoadDataTool,
)


class RealListFilesTool(BaseListFilesTool):
    def execute(
        self,
        study: Any,
        directory: str | None = None,
        pattern: str | None = None,
        **kwargs,
    ) -> str:
        if not directory:
            return "Error: directory is required"
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
    # No is_valid needed, always valid to load data (merges into existing)
    def execute(self, study: Any, paths: list[str] | None = None, **kwargs) -> str:
        if not paths:
            return "Error: paths list cannot be empty."

        # Auto-expand directories
        expanded_paths = []
        for p in paths:
            if os.path.isdir(p):
                # If directory, list all files
                try:
                    for f in os.listdir(p):
                        full_path = os.path.join(p, f)
                        if os.path.isfile(full_path):
                            expanded_paths.append(full_path)
                except Exception as e:
                    return f"Error scanning directory {p}: {e}"
            else:
                expanded_paths.append(p)

        if not expanded_paths:
            return "Error: No valid files found in provided paths."

        paths = expanded_paths

        # Use Facade to handle standard loading logic
        facade = BackendFacade(study)
        count, errors = facade.load_data(paths)

        if count > 0:
            if errors:
                return f"Successfully loaded {count} files. Errors: {errors}"
            return f"Successfully loaded {count} files."
        else:
            return f"Failed to load any data. Errors: {errors}"


class RealAttachLabelsTool(BaseAttachLabelsTool):
    def is_valid(self, study: Any) -> bool:
        # Requires at least one loaded file
        return bool(study.loaded_data_list)

    def execute(
        self,
        study: Any,
        mapping: dict | None = None,
        label_format: str | None = None,
        **kwargs,
    ) -> str:
        if mapping is None:
            return "Error: mapping is required"

        facade = BackendFacade(study)
        success_count = facade.attach_labels(mapping)

        if success_count > 0:
            return f"Attached labels to {success_count} files."
        else:
            return "No labels attached. Check file name mapping."


class RealClearDatasetTool(BaseClearDatasetTool):
    def is_valid(self, study: Any) -> bool:
        return bool(study.loaded_data_list)

    def execute(self, study: Any, **kwargs) -> str:
        facade = BackendFacade(study)
        facade.clear_data()
        return "Dataset cleared."


class RealGetDatasetInfoTool(BaseGetDatasetInfoTool):
    def is_valid(self, study: Any) -> bool:
        return bool(study.loaded_data_list)

    def execute(self, study: Any, **kwargs) -> str:
        facade = BackendFacade(study)
        summary = facade.get_data_summary()

        if summary["count"] == 0:
            return "No data loaded."

        info = [f"Loaded {summary['count']} files:"]
        info.extend(summary["files"])

        # Facade returns basic dict. If we need MNE info,
        # get_data_summary currently returns dataset_controller.get_event_info()
        # which is {"total", "unique_count", "unique_labels"}

        if "total" in summary:
            info.append(
                f"Events: {summary['total']} (Unique: {summary['unique_count']})"
            )

        # MNE specifics (sfreq, channels) might be missing
        # from Facade.get_data_summary()
        # Should we enhance facade?
        # Yes, let's make facade generic or stick to what's available.
        # For now, let's trust the summary dict.

        return "\n".join(info)


class RealGenerateDatasetTool(BaseGenerateDatasetTool):
    def is_valid(self, study: Any) -> bool:
        # Requires epoch_data to generate dataset
        return study.epoch_data is not None

    def execute(
        self,
        study: Any,
        test_ratio: float = 0.2,
        val_ratio: float = 0.2,
        split_strategy: str = "trial",
        training_mode: str = "individual",
        **kwargs,
    ) -> str:
        facade = BackendFacade(study)

        try:
            facade.generate_dataset(
                test_ratio=test_ratio,
                val_ratio=val_ratio,
                split_strategy=split_strategy,
                training_mode=training_mode,
            )
            # Fetch count from study.datasets explicitly if needed
            count = 0
            if study.datasets:
                count = len(study.datasets)

        except Exception as e:
            return f"Dataset generation failed: {e!s}"
        else:
            return (
                f"Dataset successfully generated. Count: {count} "
                f"(Test: {test_ratio}, Val: {val_ratio})."
            )
