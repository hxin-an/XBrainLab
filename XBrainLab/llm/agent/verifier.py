"""Verification layer for validating proposed tool calls.

Provides safety checks between the LLM output parser and the tool
execution engine, including structure validation and confidence gating.
"""

from typing import NamedTuple


class VerificationResult(NamedTuple):
    """Result of a tool-call verification check.

    Attributes:
        is_valid: Whether the tool call passed all verification checks.
        error_message: Human-readable reason for rejection, or ``None``
            if the call is valid.
    """

    is_valid: bool
    error_message: str | None = None


class VerificationLayer:
    """Safety guard between LLM output and tool execution.

    Validates the structure of proposed tool calls and optionally gates
    execution based on a confidence threshold.

    Attributes:
        confidence_threshold: Minimum confidence score (0.0-1.0) required
            for a tool call to pass verification.
    """

    def __init__(self, confidence_threshold: float = 0.5):
        """Initializes the VerificationLayer.

        Args:
            confidence_threshold: Minimum confidence score required for a
                tool call to be considered valid. Defaults to ``0.5``.
        """
        self.confidence_threshold = confidence_threshold

    def verify_tool_call(
        self, tool_call: tuple[str, dict], confidence: float | None = None
    ) -> VerificationResult:
        """Verifies a proposed tool call before execution.

        Checks structural validity (correct tuple format and types) and
        optionally rejects calls whose confidence falls below the
        configured threshold.

        Args:
            tool_call: A ``(tool_name, parameters)`` tuple representing
                the proposed tool invocation.
            confidence: Optional confidence score in the range 0.0-1.0.
                If provided and below ``confidence_threshold``, the call
                is rejected.

        Returns:
            A ``VerificationResult`` indicating whether the call is valid.

        Raises:
            ValueError: If ``tool_call`` is not a two-element tuple of
                ``(str, dict)``.
        """
        # 1. Structure Check
        if not isinstance(tool_call, tuple) or len(tool_call) != 2:
            raise ValueError("Tool call must be a tuple of (name, params)")

        name, params = tool_call
        if not isinstance(name, str) or not isinstance(params, dict):
            # This is technically structure failure, but let's treat as invalid
            raise ValueError("Tool call elements must be (str, dict)")

        if confidence is not None and confidence < self.confidence_threshold:
            return VerificationResult(
                is_valid=False,
                error_message=(
                    f"Confidence too low ({confidence:.2f} < "
                    f"{self.confidence_threshold})"
                ),
            )

        # 3. Script Validation (Future: Check specific logic via Validator Strategies)
        # For now, we assume simple validity if structure passes

        return VerificationResult(is_valid=True)
