"""Shared strict-envelope recovery contract for product and evaluation loops."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .parser import ToolEnvelopeParseResult, ToolEnvelopeStatus
from .prompt_policy import STRICT_TOOL_RESPONSE_PROMPT_POLICY


class StrictEnvelopeRecoveryAction(str, Enum):
    """Host action after classifying one complete model generation."""

    ACCEPT_TOOL = "accept_tool"
    ACCEPT_NO_TOOL = "accept_no_tool"
    RETRY_FORMAT = "retry_format"
    EXHAUSTED = "exhausted"


class StrictEnvelopeRecoveryTaxonomy(str, Enum):
    """Stable artifact taxonomy for one strict-envelope generation path."""

    FIRST_ATTEMPT_TOOL = "first_attempt_tool"
    FIRST_ATTEMPT_BLOCKED = "first_attempt_blocked"
    FIRST_ATTEMPT_MISSING_INPUT = "first_attempt_missing_input"
    FIRST_ATTEMPT_ANSWER = "first_attempt_answer"
    FIRST_ATTEMPT_PLAIN_TEXT = "first_attempt_plain_text"
    RECOVERED_TOOL = "recovered_tool"
    RECOVERED_BLOCKED = "recovered_blocked"
    RECOVERED_MISSING_INPUT = "recovered_missing_input"
    RECOVERED_ANSWER = "recovered_answer"
    RECOVERED_PLAIN_TEXT = "recovered_plain_text"
    FORMAT_ERROR_RETRY = "format_error_retry"
    FORMAT_RECOVERY_EXHAUSTED = "format_recovery_exhausted"


@dataclass(frozen=True)
class StrictEnvelopeRecoveryMessage:
    """Canonical format-correction context shown to the local model."""

    content: str


@dataclass(frozen=True)
class StrictEnvelopeRecoveryRequest:
    """Typed input for one strict-envelope recovery decision."""

    envelope: ToolEnvelopeParseResult
    recovery_attempts_used: int


@dataclass(frozen=True)
class StrictEnvelopeRecoveryDecision:
    """Typed host decision that cannot execute malformed model output."""

    action: StrictEnvelopeRecoveryAction
    taxonomy: StrictEnvelopeRecoveryTaxonomy
    recovery_attempts_after: int
    message: StrictEnvelopeRecoveryMessage | None = None

    @property
    def should_retry(self) -> bool:
        return self.action is StrictEnvelopeRecoveryAction.RETRY_FORMAT


@dataclass(frozen=True)
class StrictEnvelopeRecoveryPolicy:
    """Bound retries to parser-classified format failures only."""

    max_recovery_attempts: int = (
        STRICT_TOOL_RESPONSE_PROMPT_POLICY.max_format_recovery_attempts
    )

    def __post_init__(self) -> None:
        if self.max_recovery_attempts < 0:
            raise ValueError("max_recovery_attempts must be non-negative")

    def decide(
        self,
        request: StrictEnvelopeRecoveryRequest,
    ) -> StrictEnvelopeRecoveryDecision:
        """Return the next host action without altering or reparsing output."""
        attempts_used = request.recovery_attempts_used
        if attempts_used < 0:
            raise ValueError("recovery_attempts_used must be non-negative")

        status = request.envelope.status
        if status is ToolEnvelopeStatus.VALID:
            taxonomy = (
                StrictEnvelopeRecoveryTaxonomy.FIRST_ATTEMPT_TOOL
                if attempts_used == 0
                else StrictEnvelopeRecoveryTaxonomy.RECOVERED_TOOL
            )
            return StrictEnvelopeRecoveryDecision(
                action=StrictEnvelopeRecoveryAction.ACCEPT_TOOL,
                taxonomy=taxonomy,
                recovery_attempts_after=attempts_used,
            )

        if status is ToolEnvelopeStatus.NO_TOOL:
            taxonomy = self._accepted_no_tool_taxonomy(
                request.envelope,
                recovered=attempts_used > 0,
            )
            return StrictEnvelopeRecoveryDecision(
                action=StrictEnvelopeRecoveryAction.ACCEPT_NO_TOOL,
                taxonomy=taxonomy,
                recovery_attempts_after=attempts_used,
            )

        if attempts_used >= self.max_recovery_attempts:
            return StrictEnvelopeRecoveryDecision(
                action=StrictEnvelopeRecoveryAction.EXHAUSTED,
                taxonomy=(StrictEnvelopeRecoveryTaxonomy.FORMAT_RECOVERY_EXHAUSTED),
                recovery_attempts_after=attempts_used,
            )

        return StrictEnvelopeRecoveryDecision(
            action=StrictEnvelopeRecoveryAction.RETRY_FORMAT,
            taxonomy=StrictEnvelopeRecoveryTaxonomy.FORMAT_ERROR_RETRY,
            recovery_attempts_after=attempts_used + 1,
            message=StrictEnvelopeRecoveryMessage(
                content=STRICT_TOOL_RESPONSE_PROMPT_POLICY.recovery_instructions()
            ),
        )

    @staticmethod
    def _accepted_no_tool_taxonomy(
        envelope: ToolEnvelopeParseResult,
        *,
        recovered: bool,
    ) -> StrictEnvelopeRecoveryTaxonomy:
        """Preserve the parser's accepted response branch in artifacts."""
        if recovered:
            return {
                "blocked": StrictEnvelopeRecoveryTaxonomy.RECOVERED_BLOCKED,
                "missing_input": (
                    StrictEnvelopeRecoveryTaxonomy.RECOVERED_MISSING_INPUT
                ),
                "answer": StrictEnvelopeRecoveryTaxonomy.RECOVERED_ANSWER,
                None: StrictEnvelopeRecoveryTaxonomy.RECOVERED_PLAIN_TEXT,
            }[envelope.decision]
        return {
            "blocked": StrictEnvelopeRecoveryTaxonomy.FIRST_ATTEMPT_BLOCKED,
            "missing_input": (
                StrictEnvelopeRecoveryTaxonomy.FIRST_ATTEMPT_MISSING_INPUT
            ),
            "answer": StrictEnvelopeRecoveryTaxonomy.FIRST_ATTEMPT_ANSWER,
            None: StrictEnvelopeRecoveryTaxonomy.FIRST_ATTEMPT_PLAIN_TEXT,
        }[envelope.decision]


DEFAULT_STRICT_ENVELOPE_RECOVERY_POLICY = StrictEnvelopeRecoveryPolicy()
