"""Verification layer for validating proposed tool calls.

Provides safety checks between the LLM output parser and the tool
execution engine, including structure validation, confidence gating,
and parameter-level semantic validation via pluggable strategies.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Any, ClassVar, NamedTuple

logger = logging.getLogger(__name__)


class VerificationResult(NamedTuple):
    """Result of a tool-call verification check.

    Attributes:
        is_valid: Whether the tool call passed all verification checks.
        error_message: Human-readable reason for rejection, or ``None``
            if the call is valid.

    """

    is_valid: bool
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Validator Strategy interface + built-in strategies
# ---------------------------------------------------------------------------


class ValidatorStrategy(ABC):
    """Abstract base for parameter-level validation strategies."""

    @abstractmethod
    def validate(self, name: str, params: dict[str, Any]) -> VerificationResult:
        """Validate parameters for a tool call.

        Args:
            name: Tool name.
            params: Tool parameters dict.

        Returns:
            ``VerificationResult`` with ``is_valid=True`` if OK.

        """


class FrequencyRangeValidator(ValidatorStrategy):
    """Reject bandpass where low_freq >= high_freq or non-positive."""

    TOOLS: ClassVar[set[str]] = {
        "apply_bandpass_filter",
        "apply_standard_preprocess",
    }

    def validate(self, name: str, params: dict[str, Any]) -> VerificationResult:
        if name not in self.TOOLS:
            return VerificationResult(is_valid=True)

        # Determine parameter names (standard_preprocess uses l_freq/h_freq)
        if name == "apply_standard_preprocess":
            lo, hi = params.get("l_freq"), params.get("h_freq")
        else:
            lo, hi = params.get("low_freq"), params.get("high_freq")

        if lo is not None and hi is not None:
            try:
                lo, hi = float(lo), float(hi)
            except (TypeError, ValueError):
                return VerificationResult(
                    is_valid=False,
                    error_message=(
                        f"Frequency values must be numeric, got {lo!r} and {hi!r}"
                    ),
                )
            if lo <= 0 or hi <= 0:
                return VerificationResult(
                    is_valid=False,
                    error_message=(
                        f"Frequencies must be positive, got low={lo}, high={hi}"
                    ),
                )
            if lo >= hi:
                return VerificationResult(
                    is_valid=False,
                    error_message=f"low_freq ({lo}) must be < high_freq ({hi})",
                )
        return VerificationResult(is_valid=True)


class TrainingParamValidator(ValidatorStrategy):
    """Reject training configurations with clearly invalid values."""

    TOOLS: ClassVar[set[str]] = {"configure_training"}

    def validate(self, name: str, params: dict[str, Any]) -> VerificationResult:
        if name not in self.TOOLS:
            return VerificationResult(is_valid=True)

        epoch = params.get("epoch")
        if epoch is not None:
            try:
                epoch = int(epoch)
            except (TypeError, ValueError):
                return VerificationResult(
                    is_valid=False,
                    error_message=f"epoch must be a positive integer, got {epoch!r}",
                )
            if epoch <= 0:
                return VerificationResult(
                    is_valid=False,
                    error_message=f"epoch must be > 0, got {epoch}",
                )
            if epoch > 10000:
                return VerificationResult(
                    is_valid=False,
                    error_message=f"epoch={epoch} is suspiciously large (max 10000)",
                )

        lr = params.get("learning_rate")
        if lr is not None:
            try:
                lr = float(lr)
            except (TypeError, ValueError):
                return VerificationResult(
                    is_valid=False,
                    error_message=f"learning_rate must be numeric, got {lr!r}",
                )
            if lr <= 0 or lr >= 1.0:
                return VerificationResult(
                    is_valid=False,
                    error_message=f"learning_rate should be in (0, 1), got {lr}",
                )

        batch_size = params.get("batch_size")
        if batch_size is not None:
            try:
                batch_size = int(batch_size)
            except (TypeError, ValueError):
                return VerificationResult(
                    is_valid=False,
                    error_message=(
                        f"batch_size must be a positive integer, got {batch_size!r}"
                    ),
                )
            if batch_size <= 0:
                return VerificationResult(
                    is_valid=False,
                    error_message=f"batch_size must be > 0, got {batch_size}",
                )

        return VerificationResult(is_valid=True)


class PathExistsValidator(ValidatorStrategy):
    """Reject file/directory tool calls where path does not exist."""

    TOOLS: ClassVar[set[str]] = {"load_data", "list_files"}

    def validate(self, name: str, params: dict[str, Any]) -> VerificationResult:
        if name not in self.TOOLS:
            return VerificationResult(is_valid=True)

        # Try common parameter names for paths
        path = params.get("file_path") or params.get("directory") or params.get("path")
        if path and isinstance(path, str) and not os.path.exists(path):
            return VerificationResult(
                is_valid=False,
                error_message=f"Path does not exist: {path}",
            )
        return VerificationResult(is_valid=True)


# Default validators applied to every tool call
DEFAULT_VALIDATORS: list[ValidatorStrategy] = [
    FrequencyRangeValidator(),
    TrainingParamValidator(),
    PathExistsValidator(),
]


class VerificationLayer:
    """Safety guard between LLM output and tool execution.

    Validates the structure of proposed tool calls, optionally gates
    execution based on a confidence threshold, and runs pluggable
    ``ValidatorStrategy`` checks against tool parameters.

    Attributes:
        confidence_threshold: Minimum confidence score (0.0-1.0) required
            for a tool call to pass verification.
        validators: List of ``ValidatorStrategy`` instances to run on
            each tool call after structure/confidence checks pass.

    """

    def __init__(
        self,
        confidence_threshold: float = 0.5,
        validators: list[ValidatorStrategy] | None = None,
    ):
        """Initializes the VerificationLayer.

        Args:
            confidence_threshold: Minimum confidence score required for a
                tool call to be considered valid. Defaults to ``0.5``.
            validators: Optional list of ``ValidatorStrategy``
                instances.  Defaults to :data:`DEFAULT_VALIDATORS`.

        """
        self.confidence_threshold = confidence_threshold
        self.validators = (
            validators if validators is not None else list(DEFAULT_VALIDATORS)
        )

    def verify_tool_call(
        self,
        tool_call: tuple[str, dict],
        confidence: float | None = None,
    ) -> VerificationResult:
        """Verifies a proposed tool call before execution.

        Checks structural validity (correct tuple format and types),
        optionally rejects calls whose confidence falls below the
        configured threshold, and then runs all registered
        ``ValidatorStrategy`` checks.

        Args:
            tool_call: A ``(tool_name, parameters)`` tuple representing
                the proposed tool invocation.
            confidence: Optional confidence score in the range 0.0-1.0.
                If provided and below ``confidence_threshold``, the call
                is rejected.

        Returns:
            A ``VerificationResult`` indicating whether the call is valid.

        """
        # 1. Structure Check
        if not isinstance(tool_call, tuple) or len(tool_call) != 2:
            return VerificationResult(
                is_valid=False,
                error_message="Tool call must be a tuple of (name, params)",
            )

        name, params = tool_call
        if not isinstance(name, str) or not isinstance(params, dict):
            return VerificationResult(
                is_valid=False,
                error_message="Tool call elements must be (str, dict)",
            )

        # 2. Confidence Gating
        if confidence is not None and confidence < self.confidence_threshold:
            return VerificationResult(
                is_valid=False,
                error_message=(
                    f"Confidence too low ({confidence:.2f} < "
                    f"{self.confidence_threshold})"
                ),
            )

        # 3. Parameter Validation Strategies
        for validator in self.validators:
            result = validator.validate(name, params)
            if not result.is_valid:
                logger.warning(
                    "Validator %s rejected %s: %s",
                    type(validator).__name__,
                    name,
                    result.error_message,
                )
                return result

        return VerificationResult(is_valid=True)
