"""Real implementations of EEG preprocessing tools.

These tools interact with the ApplicationService command spine to apply
actual preprocessing operations (filtering, resampling, normalisation, etc.)
to the loaded EEG data.
"""

from typing import Any

from XBrainLab.llm.tools import execute_real_application_tool
from XBrainLab.llm.tools.result_contract import (
    ToolResult,
    UiRequest,
    UiRequestKind,
)

from ..definitions.preprocess_def import (
    BaseBandPassFilterTool,
    BaseChannelSelectionTool,
    BaseEpochDataTool,
    BaseNormalizeTool,
    BaseNotchFilterTool,
    BaseRereferenceTool,
    BaseResampleTool,
    BaseResetPreprocessTool,
    BaseSetMontageTool,
    BaseStandardPreprocessTool,
)


def _format_channel_identity_guardrail(diagnostics: dict[str, Any]) -> str:
    """Format a concise guardrail note for ambiguous generated channel names."""
    details = diagnostics.get("gdf_duplicate_channel_details", [])
    if not isinstance(details, list) or not details:
        return ""

    summaries: list[str] = []
    for detail in details[:2]:
        if not isinstance(detail, dict):
            continue
        filename = detail.get("file") or "unknown file"
        generated_bases = detail.get("generated_bases", [])
        if isinstance(generated_bases, list):
            base_text = ", ".join(str(base) for base in generated_bases if base)
        else:
            base_text = ""
        if not base_text:
            base_text = "generated names"
        summaries.append(f"{filename} (bases: {base_text})")

    if not summaries:
        return ""

    extra = ""
    remaining = len(details) - len(summaries)
    if remaining > 0:
        extra = f" +{remaining} more"

    return (
        " Warning: verify channel-sensitive preprocessing carefully; "
        f"GDF duplicate-channel ambiguity remains for {'; '.join(summaries)}{extra}."
    )


def _preprocess_diagnostics(study: Any) -> dict[str, Any]:
    """Return preprocess diagnostics from the shared command service."""
    result = execute_real_application_tool(
        study,
        "query_state",
        {"query": "preprocess_diagnostics"},
    )
    if result.ok and isinstance(result.payload, dict):
        return dict(result.payload)
    return {}


class RealStandardPreprocessTool(BaseStandardPreprocessTool):
    """Real implementation of :class:`BaseStandardPreprocessTool`.

    Applies a full preprocessing pipeline (bandpass, notch, resample,
    re-reference, normalise) via ApplicationService.
    """

    def execute(
        self,
        study: Any,
        l_freq: float = 4,
        h_freq: float = 40,
        notch_freq: float = 50,
        rereference: str | None = None,
        resample_rate: int | None = None,
        normalize_method: str = "z-score",
        **kwargs,
    ) -> ToolResult:
        """Apply the standard preprocessing pipeline.

        Args:
            study: The global ``Study`` instance.
            l_freq: Lower bandpass cutoff in Hz.
            h_freq: Upper bandpass cutoff in Hz.
            notch_freq: Notch filter frequency in Hz.
            rereference: Re-reference method (e.g., ``'average'``).
            resample_rate: Target sampling rate in Hz.
            normalize_method: Normalisation method (``'z-score'`` or
                ``'min-max'``).
            **kwargs: Additional keyword arguments.

        Returns:
            A success message or an error description.

        """
        return execute_real_application_tool(
            study,
            self.name,
            {
                "l_freq": l_freq,
                "h_freq": h_freq,
                "notch_freq": notch_freq,
                "rereference": rereference,
                "resample_rate": resample_rate,
                "normalize_method": normalize_method,
            },
        )


class RealResetPreprocessTool(BaseResetPreprocessTool):
    """Reset preprocessing through the canonical ApplicationService command."""

    def execute(self, study: Any, **kwargs) -> ToolResult:
        """Retain loaded raw EEG while clearing derived preprocessing state."""
        return execute_real_application_tool(
            study,
            self.name,
            {"confirmed": kwargs.get("confirmed", False)},
        )


class RealBandPassFilterTool(BaseBandPassFilterTool):
    """Real implementation of :class:`BaseBandPassFilterTool`."""

    def execute(
        self,
        study: Any,
        low_freq: float | None = None,
        high_freq: float | None = None,
        **kwargs,
    ) -> ToolResult:
        """Apply a bandpass filter to loaded EEG data.

        Args:
            study: The global ``Study`` instance.
            low_freq: Lower cutoff frequency in Hz.
            high_freq: Upper cutoff frequency in Hz.
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.

        """
        return execute_real_application_tool(
            study,
            self.name,
            {"low_freq": low_freq, "high_freq": high_freq},
        )


class RealNotchFilterTool(BaseNotchFilterTool):
    """Real implementation of :class:`BaseNotchFilterTool`."""

    def execute(self, study: Any, freq: float | None = None, **kwargs) -> ToolResult:
        """Apply a notch filter to remove power-line noise.

        Args:
            study: The global ``Study`` instance.
            freq: Notch frequency in Hz.
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.

        """
        return execute_real_application_tool(
            study,
            self.name,
            {"freq": freq},
        )


class RealResampleTool(BaseResampleTool):
    """Real implementation of :class:`BaseResampleTool`."""

    def execute(self, study: Any, rate: int | None = None, **kwargs) -> ToolResult:
        """Resample the loaded EEG data to a new sampling rate.

        Args:
            study: The global ``Study`` instance.
            rate: Target sampling rate in Hz.
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.

        """
        return execute_real_application_tool(
            study,
            self.name,
            {"rate": rate},
        )


class RealNormalizeTool(BaseNormalizeTool):
    """Real implementation of :class:`BaseNormalizeTool`."""

    def execute(self, study: Any, method: str | None = None, **kwargs) -> ToolResult:
        """Normalise the loaded EEG data.

        Args:
            study: The global ``Study`` instance.
            method: Normalisation method (``'z-score'`` or ``'min-max'``).
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.

        """
        return execute_real_application_tool(
            study,
            self.name,
            {"method": method},
        )


class RealRereferenceTool(BaseRereferenceTool):
    """Real implementation of :class:`BaseRereferenceTool`."""

    def execute(self, study: Any, method: str | None = None, **kwargs) -> ToolResult:
        """Set the EEG reference.

        Args:
            study: The global ``Study`` instance.
            method: Reference method (e.g., ``'average'``).
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.

        """
        return execute_real_application_tool(
            study,
            self.name,
            {"method": method},
        )


class RealChannelSelectionTool(BaseChannelSelectionTool):
    """Real implementation of :class:`BaseChannelSelectionTool`."""

    def execute(
        self,
        study: Any,
        channels: list[str] | None = None,
        **kwargs,
    ) -> ToolResult:
        """Select specific EEG channels to keep.

        Args:
            study: The global ``Study`` instance.
            channels: List of channel names to retain.
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.

        """
        return execute_real_application_tool(
            study,
            self.name,
            {"channels": channels},
        )


class RealSetMontageTool(BaseSetMontageTool):
    """Real implementation of :class:`BaseSetMontageTool`.

    Requests UI confirmation instead of auto-applying, allowing the
    user to visually verify the channel-to-electrode mapping.
    """

    def execute(
        self,
        study: Any,
        montage_name: str | None = None,
        **kwargs,
    ) -> ToolResult | UiRequest:
        """Request montage application with UI confirmation.

        Args:
            study: The global ``Study`` instance.
            montage_name: Standard montage name (e.g., ``'standard_1020'``).
            **kwargs: Additional keyword arguments.

        Returns:
            A request string for UI confirmation, or an error message.

        """
        if montage_name is None:
            return ToolResult(
                ok=False,
                message="A montage name is required.",
                error_type="input",
            )

        warning = _format_channel_identity_guardrail(_preprocess_diagnostics(study))
        return UiRequest(
            kind=UiRequestKind.CONFIRM_MONTAGE,
            params={
                "montage_name": montage_name,
                "warning": warning.strip(),
            },
        )


class RealEpochDataTool(BaseEpochDataTool):
    """Real implementation of :class:`BaseEpochDataTool`."""

    def execute(
        self,
        study: Any,
        t_min: float = -0.1,
        t_max: float = 1.0,
        baseline: list[float] | None = None,
        event_id: list[str] | None = None,  # Note: Definitions use 'event_id'
        **kwargs,
    ) -> ToolResult:
        """Epoch continuous EEG data based on event markers.

        Args:
            study: The global ``Study`` instance.
            t_min: Start time of each epoch in seconds.
            t_max: End time of each epoch in seconds.
            baseline: Baseline correction interval ``[start, end]``.
            event_id: Event identifiers to epoch around.
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation message or an error description.

        """
        return execute_real_application_tool(
            study,
            self.name,
            {
                "t_min": t_min,
                "t_max": t_max,
                "baseline": baseline,
                "event_id": event_id,
            },
        )
