"""Real implementations of dataset tools.

These tools interact with the ApplicationService command spine to perform
actual dataset operations (file listing, loading, label attachment, etc.).
"""

import os
from pathlib import Path
from typing import Any

from XBrainLab.backend.application import (
    ApplyInterpretationCommand,
    AttachLabelsCommand,
    GenerateDatasetCommand,
    LoadDataCommand,
    PreviewInterpretationCommand,
    QueryStateCommand,
    ReloadInterpretationRecipeCommand,
    ResetSessionCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
    get_application_service,
)
from XBrainLab.backend.utils.logger import logger

from ..definitions.dataset_def import (
    BaseApplyInterpretationTool,
    BaseAttachLabelsTool,
    BaseClearDatasetTool,
    BaseGenerateDatasetTool,
    BaseGetDatasetInfoTool,
    BaseListFilesTool,
    BaseLoadDataTool,
    BasePreviewInterpretationTool,
    BaseQueryStateTool,
    BaseReloadInterpretationRecipeTool,
    BaseSaveInterpretationRecipeTool,
    BaseScanSourceTool,
    BaseValidateInterpretationTool,
)


def _existing_env_realpath(name: str) -> str | None:
    value = os.environ.get(name)
    return os.path.realpath(value) if value else None


def _application_result_message(result: Any) -> str:
    """Return a legacy-safe string for direct real-tool callers."""
    if getattr(result, "ok", False):
        return str(result.message)
    return f"Failed: {result.message}"


# Directories that should NEVER be exposed to the LLM agent. Windows paths are
# included only when the environment variables exist; otherwise WSL/Linux would
# resolve fallback strings relative to the repo and block the workspace itself.
_SENSITIVE_DIRS: frozenset[str] = frozenset(
    path
    for path in {
        _existing_env_realpath("SYSTEMROOT"),
        _existing_env_realpath("PROGRAMFILES"),
        _existing_env_realpath("PROGRAMFILES(X86)"),
        # Unix
        "/etc",
        "/var",
        "/usr",
        "/bin",
        "/sbin",
        "/boot",
        "/proc",
        "/sys",
    }
    if path
)


class RealListFilesTool(BaseListFilesTool):
    """Real implementation of :class:`BaseListFilesTool`.

    Lists files in a directory using ``os.listdir`` with optional
    extension-based filtering.
    """

    def execute(
        self,
        study: Any,
        directory: str | None = None,
        pattern: str | None = None,
        **kwargs,
    ) -> str:
        """List files in the specified directory.

        Args:
            study: The global ``Study`` instance (unused directly).
            directory: Absolute path to the target directory.
            pattern: Glob-style pattern for filtering (e.g., ``'*.gdf'``).
            **kwargs: Additional keyword arguments.

        Returns:
            A string representation of the matched file list, or an
            error message on failure.

        """
        if not directory:
            return "Error: directory is required"

        # Resolve to absolute path and guard against directory traversal
        directory = os.path.realpath(directory)

        # Security: block access to sensitive system directories
        dir_path = Path(directory)
        for sensitive in _SENSITIVE_DIRS:
            sensitive_path = Path(sensitive)
            if dir_path == sensitive_path or sensitive_path in dir_path.parents:
                logger.warning(
                    "RealListFilesTool blocked access to sensitive path: %s",
                    directory,
                )
                return "Error: Access to system directories is not allowed."

        if not os.path.isdir(directory):
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
    """Real implementation of :class:`BaseLoadDataTool`.

    Loads EEG data files through ApplicationService, automatically
    expanding directory paths to individual files.
    """

    def execute(self, study: Any, paths: list[str] | None = None, **kwargs) -> str:
        """Load EEG data from the given file or directory paths.

        Directories are auto-expanded to include all contained files.

        Args:
            study: The global ``Study`` instance.
            paths: List of absolute file or directory paths.
            **kwargs: Additional keyword arguments.

        Returns:
            A success message with the count of loaded files, or an
            error message on failure.

        """
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

        result = get_application_service(study).execute(LoadDataCommand(paths=paths))
        if result.failed:
            errors = result.diagnostics.get("errors") or [result.message]
            return f"Failed to load any data. Errors: {list(errors)}"

        count = int(result.diagnostics.get("success_count", 0))
        errors = list(result.diagnostics.get("errors", []))

        if count > 0:
            if errors:
                return f"Successfully loaded {count} files. Errors: {errors}"
            return f"Successfully loaded {count} files."
        return f"Failed to load any data. Errors: {errors}"


class RealScanSourceTool(BaseScanSourceTool):
    """Real implementation of :class:`BaseScanSourceTool`."""

    def execute(
        self,
        study: Any,
        source_path: str | None = None,
        source_hint: str = "auto",
        label_sources: list[str] | None = None,
        **kwargs,
    ) -> str:
        if not source_path:
            return "Error: source_path is required"
        result = get_application_service(study).execute(
            ScanSourceCommand(
                source_path=source_path,
                source_hint=source_hint,
                label_sources=label_sources or [],
            ),
        )
        return _application_result_message(result)


class RealPreviewInterpretationTool(BasePreviewInterpretationTool):
    """Real implementation of :class:`BasePreviewInterpretationTool`."""

    def execute(
        self,
        study: Any,
        scan_id: str | None = None,
        choices: dict[str, Any] | None = None,
        **kwargs,
    ) -> str:
        result = get_application_service(study).execute(
            PreviewInterpretationCommand(scan_id=scan_id, choices=dict(choices or {})),
        )
        return _application_result_message(result)


class RealValidateInterpretationTool(BaseValidateInterpretationTool):
    """Real implementation of :class:`BaseValidateInterpretationTool`."""

    def execute(
        self,
        study: Any,
        candidate_id: str | None = None,
        **kwargs,
    ) -> str:
        result = get_application_service(study).execute(
            ValidateInterpretationCommand(candidate_id=candidate_id),
        )
        return _application_result_message(result)


class RealApplyInterpretationTool(BaseApplyInterpretationTool):
    """Real implementation of :class:`BaseApplyInterpretationTool`."""

    def execute(
        self,
        study: Any,
        candidate_id: str | None = None,
        confirmed: bool = False,
        **kwargs,
    ) -> str:
        result = get_application_service(study).execute(
            ApplyInterpretationCommand(candidate_id=candidate_id, confirmed=confirmed),
        )
        return _application_result_message(result)


class RealSaveInterpretationRecipeTool(BaseSaveInterpretationRecipeTool):
    """Real implementation of :class:`BaseSaveInterpretationRecipeTool`."""

    def execute(
        self,
        study: Any,
        recipe_path: str | None = None,
        **kwargs,
    ) -> str:
        result = get_application_service(study).execute(
            SaveInterpretationRecipeCommand(recipe_path=recipe_path),
        )
        return _application_result_message(result)


class RealReloadInterpretationRecipeTool(BaseReloadInterpretationRecipeTool):
    """Real implementation of :class:`BaseReloadInterpretationRecipeTool`."""

    def execute(
        self,
        study: Any,
        recipe_path: str | None = None,
        **kwargs,
    ) -> str:
        if not recipe_path:
            return "Error: recipe_path is required"
        result = get_application_service(study).execute(
            ReloadInterpretationRecipeCommand(recipe_path=recipe_path),
        )
        return _application_result_message(result)


class RealAttachLabelsTool(BaseAttachLabelsTool):
    """Real implementation of :class:`BaseAttachLabelsTool`.

    Attaches label files to loaded data through ApplicationService.
    """

    def execute(
        self,
        study: Any,
        mapping: dict | None = None,
        label_format: str | None = None,
        **kwargs,
    ) -> str:
        """Attach label files to loaded data files.

        Args:
            study: The global ``Study`` instance.
            mapping: Dictionary mapping data filenames to label file paths.
            label_format: Optional label file format hint.
            **kwargs: Additional keyword arguments.

        Returns:
            A message indicating how many files received labels.

        """
        if mapping is None:
            return "Error: mapping is required"

        result = get_application_service(study).execute(
            AttachLabelsCommand(
                mapping={str(key): str(value) for key, value in mapping.items()},
            ),
        )
        if result.failed:
            return f"Failed to attach labels: {result.message}"
        success_count = int(result.diagnostics.get("success_count", 0))

        if success_count > 0:
            return f"Attached labels to {success_count} files."
        return "No labels attached. Check file name mapping."


class RealClearDatasetTool(BaseClearDatasetTool):
    """Real implementation of :class:`BaseClearDatasetTool`."""

    def execute(self, study: Any, **kwargs) -> str:
        """Clear all loaded data and reset Study state.

        Args:
            study: The global ``Study`` instance.
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation message.

        """
        result = get_application_service(study).execute(
            ResetSessionCommand(confirmed=True),
        )
        if result.failed:
            return f"Failed to clear dataset: {result.message}"
        return "Dataset cleared."


class RealGetDatasetInfoTool(BaseGetDatasetInfoTool):
    """Real implementation of :class:`BaseGetDatasetInfoTool`."""

    def execute(self, study: Any, **kwargs) -> str:
        """Retrieve summary information about the loaded dataset.

        Args:
            study: The global ``Study`` instance.
            **kwargs: Additional keyword arguments.

        Returns:
            A newline-separated summary string.

        """
        result = get_application_service(study).execute(
            QueryStateCommand(query="data_summary"),
        )
        summary = dict(result.diagnostics) if result.ok else {"count": 0, "files": []}

        if summary["count"] == 0:
            return "No data loaded."

        info = [f"Loaded {summary['count']} files:"]
        info.extend(summary["files"])

        if "total" in summary:
            info.append(
                f"Events: {summary['total']} (Unique: {summary['unique_count']})",
            )

        diagnostics = summary.get("gdf_duplicate_channel_details", [])
        if diagnostics:
            info.append("Diagnostics:")
            for detail in diagnostics:
                filename = detail.get("file") or "unknown file"
                bases = detail.get("generated_bases") or []
                base_text = ", ".join(bases) if bases else "unknown bases"
                info.append(
                    "- GDF duplicate-channel ambiguity: "
                    f"{filename} (bases: {base_text})",
                )

        return "\n".join(info)


class RealQueryStateTool(BaseQueryStateTool):
    """Real implementation of :class:`BaseQueryStateTool`."""

    def execute(self, study: Any, **kwargs) -> str:
        result = get_application_service(study).execute(
            QueryStateCommand(query=str(kwargs.get("query", "state"))),
        )
        return str(result.message)


class RealGenerateDatasetTool(BaseGenerateDatasetTool):
    """Real implementation of :class:`BaseGenerateDatasetTool`.

    Generates train/validation/test splits from epoched EEG data.
    """

    def execute(
        self,
        study: Any,
        test_ratio: float = 0.2,
        val_ratio: float = 0.2,
        split_strategy: str = "trial",
        training_mode: str = "individual",
        **kwargs,
    ) -> str:
        """Generate a training dataset from epoched data.

        Args:
            study: The global ``Study`` instance.
            test_ratio: Fraction of data reserved for testing.
            val_ratio: Fraction of data reserved for validation.
            split_strategy: How to split data (``'trial'``, ``'session'``,
                or ``'subject'``).
            training_mode: Training paradigm (``'individual'`` or
                ``'group'``).
            **kwargs: Additional keyword arguments.

        Returns:
            A success message with dataset count or an error message.

        """
        result = get_application_service(study).execute(
            GenerateDatasetCommand(
                test_ratio=test_ratio,
                val_ratio=val_ratio,
                split_strategy=split_strategy,
                training_mode=training_mode,
            ),
        )
        if result.failed:
            return f"Dataset generation failed: {result.message}"
        count = int(result.diagnostics.get("dataset_count", 0))
        return (
            f"Dataset successfully generated. Count: {count} "
            f"(Test: {test_ratio}, Val: {val_ratio})."
        )
