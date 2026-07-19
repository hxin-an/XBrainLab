"""Real implementations of dataset tools.

These tools interact with the ApplicationService command spine to perform
actual dataset operations (file listing, loading, label attachment, etc.).
"""

import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from XBrainLab.backend.utils.logger import logger

from .. import execute_real_application_tool
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
from ..result_contract import ToolResult, redact_public_text, runtime_tool_failure


def _existing_env_realpath(name: str) -> str | None:
    value = os.environ.get(name)
    return os.path.realpath(value) if value else None


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
    ) -> ToolResult:
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
            return ToolResult(False, "A folder path is required.", error_type="input")

        # Resolve to absolute path and guard against directory traversal
        directory = os.path.realpath(directory)

        # Security: block access to sensitive system directories
        dir_path = Path(directory)
        for sensitive in _SENSITIVE_DIRS:
            sensitive_path = Path(sensitive)
            if dir_path == sensitive_path or sensitive_path in dir_path.parents:
                logger.warning(
                    "RealListFilesTool blocked access to sensitive path: %s",
                    redact_public_text(directory),
                )
                return ToolResult(
                    False,
                    "Protected system folders cannot be browsed.",
                    error_type="permission",
                    recoverable=False,
                )

        if not os.path.isdir(directory):
            return ToolResult(
                False,
                "The selected folder does not exist.",
                error_type="input",
            )

        try:
            files = []
            for f in os.listdir(directory):
                # Simple pattern logic (extension based)
                if pattern and pattern.startswith("*") and not f.endswith(pattern[1:]):
                    continue
                files.append(f)
            return ToolResult(
                True,
                f"Found {len(files)} file(s).",
                payload=files,
            )
        except Exception as error:
            return runtime_tool_failure(
                "list_files",
                error,
                developer_logger=logger,
            )


class RealLoadDataTool(BaseLoadDataTool):
    """Real implementation of :class:`BaseLoadDataTool`.

    Loads EEG data files through ApplicationService, automatically
    expanding directory paths to individual files.
    """

    def execute(
        self,
        study: Any,
        paths: list[str] | None = None,
        **kwargs,
    ) -> ToolResult:
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
        return execute_real_application_tool(
            study,
            self.name,
            {
                "paths": paths,
                "allow_append": kwargs.get("allow_append", True),
                "resource_preflight_confirmed": kwargs.get(
                    "resource_preflight_confirmed",
                    False,
                ),
                "resource_preflight_token": kwargs.get("resource_preflight_token"),
            },
        )


class RealScanSourceTool(BaseScanSourceTool):
    """Real implementation of :class:`BaseScanSourceTool`."""

    def execute(
        self,
        study: Any,
        source_path: str | None = None,
        source_hint: str = "auto",
        label_sources: list[str] | None = None,
        **kwargs,
    ) -> ToolResult:
        return execute_real_application_tool(
            study,
            self.name,
            {
                "source_path": source_path,
                "source_hint": source_hint,
                "label_sources": label_sources,
            },
        )


class RealPreviewInterpretationTool(BasePreviewInterpretationTool):
    """Real implementation of :class:`BasePreviewInterpretationTool`."""

    def execute(
        self,
        study: Any,
        scan_id: str | None = None,
        choices: dict[str, Any] | None = None,
        **kwargs,
    ) -> ToolResult:
        return execute_real_application_tool(
            study,
            self.name,
            {
                "scan_id": scan_id,
                "choices": choices,
                "resource_preflight_confirmed": kwargs.get(
                    "resource_preflight_confirmed",
                    False,
                ),
                "resource_preflight_token": kwargs.get("resource_preflight_token"),
            },
        )


class RealValidateInterpretationTool(BaseValidateInterpretationTool):
    """Real implementation of :class:`BaseValidateInterpretationTool`."""

    def execute(
        self,
        study: Any,
        candidate_id: str | None = None,
        **kwargs,
    ) -> ToolResult:
        return execute_real_application_tool(
            study,
            self.name,
            {"candidate_id": candidate_id},
        )


class RealApplyInterpretationTool(BaseApplyInterpretationTool):
    """Real implementation of :class:`BaseApplyInterpretationTool`."""

    def execute(
        self,
        study: Any,
        candidate_id: str | None = None,
        confirmed: bool = False,
        **kwargs,
    ) -> ToolResult:
        return execute_real_application_tool(
            study,
            self.name,
            {
                "candidate_id": candidate_id,
                "confirmed": confirmed,
                "resource_preflight_confirmed": kwargs.get(
                    "resource_preflight_confirmed",
                    False,
                ),
                "resource_preflight_token": kwargs.get("resource_preflight_token"),
            },
        )


class RealSaveInterpretationRecipeTool(BaseSaveInterpretationRecipeTool):
    """Real implementation of :class:`BaseSaveInterpretationRecipeTool`."""

    def execute(
        self,
        study: Any,
        recipe_path: str | None = None,
        **kwargs,
    ) -> ToolResult:
        return execute_real_application_tool(
            study,
            self.name,
            {"recipe_path": recipe_path},
        )


class RealReloadInterpretationRecipeTool(BaseReloadInterpretationRecipeTool):
    """Real implementation of :class:`BaseReloadInterpretationRecipeTool`."""

    def execute(
        self,
        study: Any,
        recipe_path: str | None = None,
        **kwargs,
    ) -> ToolResult:
        return execute_real_application_tool(
            study,
            self.name,
            {
                "recipe_path": recipe_path,
                "resource_preflight_confirmed": kwargs.get(
                    "resource_preflight_confirmed",
                    False,
                ),
                "resource_preflight_token": kwargs.get("resource_preflight_token"),
            },
        )


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
    ) -> ToolResult:
        """Attach label files to loaded data files.

        Args:
            study: The global ``Study`` instance.
            mapping: Dictionary mapping data filenames to label file paths.
            label_format: Optional label file format hint.
            **kwargs: Additional keyword arguments.

        Returns:
            A message indicating how many files received labels.

        """
        return execute_real_application_tool(
            study,
            self.name,
            {
                "mapping": mapping,
                "label_format": label_format,
                "resource_preflight_confirmed": kwargs.get(
                    "resource_preflight_confirmed",
                    False,
                ),
                "resource_preflight_token": kwargs.get("resource_preflight_token"),
            },
        )


class RealClearDatasetTool(BaseClearDatasetTool):
    """Real implementation of :class:`BaseClearDatasetTool`."""

    def execute(self, study: Any, **kwargs) -> ToolResult:
        """Clear all loaded data and reset Study state.

        Args:
            study: The global ``Study`` instance.
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation message.

        """
        return execute_real_application_tool(
            study,
            self.name,
            {"confirmed": kwargs.get("confirmed", False)},
        )


class RealGetDatasetInfoTool(BaseGetDatasetInfoTool):
    """Real implementation of :class:`BaseGetDatasetInfoTool`."""

    def execute(self, study: Any, **kwargs) -> ToolResult:
        """Retrieve summary information about the loaded dataset.

        Args:
            study: The global ``Study`` instance.
            **kwargs: Additional keyword arguments.

        Returns:
            A newline-separated summary string.

        """
        result = execute_real_application_tool(
            study,
            "query_state",
            {"query": "data_summary"},
        )
        if not result.ok:
            return result
        summary = dict(result.diagnostics)
        if (
            not summary
            and isinstance(result.payload, dict)
            and "status" not in result.payload
        ):
            summary = dict(result.payload)

        if summary.get("count", 0) == 0:
            return replace(
                result,
                message="No data is loaded.",
            )

        info = [f"Loaded {summary['count']} files:"]
        info.extend(str(item) for item in summary.get("files", []))

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

        return replace(result, message="\n".join(info))


class RealQueryStateTool(BaseQueryStateTool):
    """Real implementation of :class:`BaseQueryStateTool`."""

    def execute(self, study: Any, **kwargs) -> ToolResult:
        return execute_real_application_tool(
            study,
            self.name,
            {"query": kwargs.get("query", "state")},
        )


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
    ) -> ToolResult:
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
        return execute_real_application_tool(
            study,
            self.name,
            {
                "test_ratio": test_ratio,
                "val_ratio": val_ratio,
                "split_strategy": split_strategy,
                "training_mode": training_mode,
            },
        )
