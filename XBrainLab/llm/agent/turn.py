"""Correlated host lifecycle contracts for one assistant conversation turn."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

from XBrainLab.chat_contract import (
    MAX_CHAT_MESSAGE_CONTENT_LENGTH,
    bounded_chat_string,
)
from XBrainLab.llm.core.generation import GenerationProfile


class AssistantResponseContract(str, Enum):
    """Output grammar expected from one model generation."""

    NATURAL_LANGUAGE = "natural_language"
    STRUCTURED_ACTION = "structured_action"

    @property
    def generation_profile(self) -> GenerationProfile:
        """Return the decoding profile that protects this output grammar."""
        if self is AssistantResponseContract.STRUCTURED_ACTION:
            return GenerationProfile.STRUCTURED_DECISION
        return GenerationProfile.INFORMATIONAL_TEXT


class AssistantGenerationEventPhase(str, Enum):
    """Observable phases from one correlated model-generation request."""

    STARTED = "started"
    CHUNK = "chunk"
    FINISHED = "finished"
    CANCELLED = "cancelled"
    ERROR = "error"


class AssistantGenerationDispatchPhase(str, Enum):
    """Worker acknowledgement phases before model output is consumed."""

    ACCEPTED = "accepted"
    STARTED = "started"


class AssistantTurnDeliveryPhase(str, Enum):
    """Host-to-controller delivery result for one correlated turn."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class AssistantGenerationDispatchAcknowledgement:
    """Worker evidence that one queued request was accepted or started."""

    generation_id: int
    phase: AssistantGenerationDispatchPhase

    def __post_init__(self) -> None:
        if (
            isinstance(self.generation_id, bool)
            or not isinstance(self.generation_id, int)
            or self.generation_id <= 0
        ):
            raise ValueError("Assistant generation dispatch IDs must be positive.")
        if not isinstance(self.phase, AssistantGenerationDispatchPhase):
            raise TypeError("Assistant generation dispatch phase must be typed.")


@dataclass(frozen=True)
class AssistantGenerationEvent:
    """Controller-level generation evidence without exposing worker internals."""

    generation_id: int
    phase: AssistantGenerationEventPhase
    text: str = ""

    def __post_init__(self) -> None:
        if (
            isinstance(self.generation_id, bool)
            or not isinstance(self.generation_id, int)
            or self.generation_id <= 0
        ):
            raise ValueError("Assistant generation event IDs must be positive.")
        if (
            self.phase
            in {
                AssistantGenerationEventPhase.CHUNK,
                AssistantGenerationEventPhase.ERROR,
            }
            and not self.text
        ):
            raise ValueError(f"Assistant generation {self.phase.value} requires text.")
        if (
            self.phase
            in {
                AssistantGenerationEventPhase.STARTED,
                AssistantGenerationEventPhase.FINISHED,
                AssistantGenerationEventPhase.CANCELLED,
            }
            and self.text
        ):
            raise ValueError(
                f"Assistant generation {self.phase.value} cannot include text."
            )


@dataclass(frozen=True)
class AssistantGenerationRequest:
    """Typed model request crossing the controller-to-worker boundary."""

    messages: tuple[tuple[tuple[str, Any], ...], ...]
    response_contract: AssistantResponseContract
    generation_id: int = 0

    def __post_init__(self) -> None:
        if (
            isinstance(self.generation_id, bool)
            or not isinstance(self.generation_id, int)
            or self.generation_id < 0
        ):
            raise ValueError("Assistant generation IDs must be non-negative integers.")

    @classmethod
    def from_messages(
        cls,
        messages: Iterable[Mapping[str, Any]],
        *,
        response_contract: AssistantResponseContract,
    ) -> AssistantGenerationRequest:
        """Copy model messages so later history mutation cannot alter a turn."""
        frozen_messages = tuple(tuple(dict(message).items()) for message in messages)
        if not frozen_messages:
            raise ValueError("Assistant generation requires at least one message.")
        return cls(
            messages=frozen_messages,
            response_contract=response_contract,
        )

    @property
    def generation_profile(self) -> GenerationProfile:
        """Return the backend decoding profile for this response contract."""
        return self.response_contract.generation_profile

    def to_model_messages(self) -> list[dict[str, Any]]:
        """Return a fresh mutable payload for tokenizer/backend APIs."""
        return [dict(message) for message in self.messages]

    def correlated(self, generation_id: int) -> AssistantGenerationRequest:
        """Return this immutable request tagged for one controller generation."""
        if isinstance(generation_id, bool) or generation_id <= 0:
            raise ValueError("Correlated assistant generation IDs must be positive.")
        return replace(self, generation_id=generation_id)


@dataclass(frozen=True, slots=True)
class AssistantGenerationStopRequest:
    """Cancellation request for exactly one model generation."""

    generation_id: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.generation_id, bool)
            or not isinstance(self.generation_id, int)
            or self.generation_id <= 0
        ):
            raise ValueError("Assistant generation stop IDs must be positive.")


@dataclass(frozen=True, slots=True)
class AssistantGenerationStopAcknowledgement:
    """Worker acknowledgement for exactly one cancellation request."""

    generation_id: int
    stopped: bool

    def __post_init__(self) -> None:
        if (
            isinstance(self.generation_id, bool)
            or not isinstance(self.generation_id, int)
            or self.generation_id <= 0
        ):
            raise ValueError("Assistant generation stop IDs must be positive.")
        if not isinstance(self.stopped, bool):
            raise TypeError("Assistant generation stop status must be a boolean.")


@dataclass(frozen=True, slots=True)
class AssistantTurnCorrelation:
    """Exact UI generation and runtime turn lease for one admitted turn."""

    generation: int
    turn_id: int

    def __post_init__(self) -> None:
        for field_name in ("generation", "turn_id"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"Assistant turn {field_name} must be an integer.")
            if value <= 0:
                raise ValueError(f"Assistant turn {field_name} must be positive.")


@dataclass(frozen=True, slots=True)
class AssistantTurnDeliveryAcknowledgement:
    """Controller delivery evidence returned through the host transport."""

    correlation: AssistantTurnCorrelation
    phase: AssistantTurnDeliveryPhase
    message: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.correlation, AssistantTurnCorrelation):
            raise TypeError("Assistant turn delivery requires typed correlation.")
        if not isinstance(self.phase, AssistantTurnDeliveryPhase):
            raise TypeError("Assistant turn delivery phase must be typed.")
        if not isinstance(self.message, str):
            raise TypeError("Assistant turn delivery message must be a string.")
        object.__setattr__(self, "message", " ".join(self.message.split()))


@dataclass(frozen=True, slots=True)
class AssistantTurnRequest:
    """One user turn admitted by the desktop runtime owner."""

    correlation: AssistantTurnCorrelation
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.correlation, AssistantTurnCorrelation):
            raise TypeError("Assistant turn requests require typed correlation.")
        object.__setattr__(
            self,
            "text",
            bounded_chat_string(
                self.text,
                field_name="Assistant turn text",
                maximum_length=MAX_CHAT_MESSAGE_CONTENT_LENGTH,
            ),
        )
        if not self.text.strip():
            raise ValueError("Assistant turn text must not be empty.")

    @property
    def turn_id(self) -> int:
        return self.correlation.turn_id

    @property
    def generation(self) -> int:
        return self.correlation.generation


@dataclass(frozen=True, slots=True)
class AssistantDebugToolRequest:
    """One diagnostic tool call admitted as an exact host turn."""

    correlation: AssistantTurnCorrelation
    tool_name: str
    params: tuple[tuple[str, Any], ...]
    confirmed: bool = False
    authorization_text: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.correlation, AssistantTurnCorrelation):
            raise TypeError("Assistant debug requests require typed correlation.")
        if not isinstance(self.tool_name, str):
            raise TypeError("Assistant debug tool names must be strings.")
        normalized_name = self.tool_name.strip()
        if not normalized_name:
            raise ValueError("Assistant debug tool names must not be empty.")
        if len(normalized_name) > 128:
            raise ValueError(
                "Assistant debug tool names are limited to 128 characters."
            )
        object.__setattr__(self, "tool_name", normalized_name)
        if not isinstance(self.params, tuple) or any(
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], str)
            for item in self.params
        ):
            raise TypeError("Assistant debug parameters must be string-keyed pairs.")
        if type(self.confirmed) is not bool:
            raise TypeError("Assistant debug confirmation must be a boolean.")
        if not isinstance(self.authorization_text, str):
            raise TypeError("Assistant debug path authorization must be a string.")
        if len(self.authorization_text) > MAX_CHAT_MESSAGE_CONTENT_LENGTH:
            raise ValueError("Assistant debug path authorization is too long.")

    @classmethod
    def from_params(
        cls,
        *,
        correlation: AssistantTurnCorrelation,
        tool_name: str,
        params: Mapping[str, Any],
        confirmed: bool = False,
        authorization_text: str = "",
    ) -> AssistantDebugToolRequest:
        """Copy diagnostic parameters before they cross a queued boundary."""
        if not isinstance(params, Mapping):
            raise TypeError("Assistant debug parameters must be a mapping.")
        copied = deepcopy(dict(params))
        return cls(
            correlation=correlation,
            tool_name=tool_name,
            params=tuple(copied.items()),
            confirmed=confirmed,
            authorization_text=authorization_text,
        )

    def to_params(self) -> dict[str, Any]:
        """Return a fresh mutable payload for the concrete tool adapter."""
        return deepcopy(dict(self.params))

    @property
    def turn_id(self) -> int:
        return self.correlation.turn_id

    @property
    def generation(self) -> int:
        return self.correlation.generation


@dataclass(frozen=True, slots=True)
class AssistantTurnTerminal:
    """Terminal acknowledgement for exactly one admitted host turn."""

    correlation: AssistantTurnCorrelation
    outcome: str = "completed"

    def __post_init__(self) -> None:
        if not isinstance(self.correlation, AssistantTurnCorrelation):
            raise TypeError("Assistant turn terminals require typed correlation.")
        if not isinstance(self.outcome, str):
            raise TypeError("Assistant turn terminal outcome must be a string.")
        object.__setattr__(self, "outcome", " ".join(self.outcome.split()))
        if not self.outcome:
            raise ValueError("Assistant turn terminal outcome cannot be empty.")

    @property
    def turn_id(self) -> int:
        return self.correlation.turn_id

    @property
    def generation(self) -> int:
        return self.correlation.generation
