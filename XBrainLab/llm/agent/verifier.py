from typing import NamedTuple


class VerificationResult(NamedTuple):
    is_valid: bool
    error_message: str | None = None


class VerificationLayer:
    """
    Acts as a safety guard between the LLM and the Tool Execution.
    Performs script validation and confidence checks.
    """

    def __init__(self, confidence_threshold: float = 0.5):
        self.confidence_threshold = confidence_threshold

    def verify_tool_call(
        self, tool_call: tuple[str, dict], confidence: float | None = None
    ) -> VerificationResult:
        """
        Verifies a proposed tool call.

        Args:
            tool_call: Tuple of (tool_name, parameters).
            confidence: Optional confidence score (0.0 - 1.0).

        Returns:
            VerificationResult indicating success or failure.
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
