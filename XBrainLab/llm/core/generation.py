"""Per-turn generation policy resolved before a backend is invoked."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite

STRUCTURED_DECISION_MAX_NEW_TOKENS = 512


class GenerationProfile(str, Enum):
    """Semantic output profile selected by the assistant controller."""

    INFORMATIONAL_TEXT = "informational_text"
    STRUCTURED_DECISION = "structured_decision"


@dataclass(frozen=True)
class ResolvedGenerationOptions:
    """Immutable decoding options consumed by local model backends."""

    max_new_tokens: int
    do_sample: bool
    temperature: float | None = None
    top_p: float | None = None

    def __post_init__(self) -> None:
        ResolvedGenerationOptions.validate(self)

    def validate(self) -> None:
        """Fail closed when a caller bypasses static generation-option types."""
        if type(self.max_new_tokens) is not int or self.max_new_tokens <= 0:
            raise ValueError("max_new_tokens must be a positive integer")
        if type(self.do_sample) is not bool:
            raise ValueError("do_sample must be a boolean")
        if self.do_sample:
            if (
                isinstance(self.temperature, bool)
                or not isinstance(self.temperature, (int, float))
                or not isfinite(self.temperature)
                or self.temperature <= 0
            ):
                raise ValueError("sampling requires a positive temperature")
            if (
                isinstance(self.top_p, bool)
                or not isinstance(self.top_p, (int, float))
                or not isfinite(self.top_p)
                or not 0 < self.top_p <= 1
            ):
                raise ValueError("sampling requires top_p in (0, 1]")
        elif self.temperature is not None or self.top_p is not None:
            raise ValueError("greedy generation must omit sampling parameters")


def resolve_generation_options(
    *,
    profile: GenerationProfile,
    max_new_tokens: int,
    do_sample: bool,
    temperature: float,
    top_p: float,
) -> ResolvedGenerationOptions:
    """Resolve user preferences and code-owned structured-output policy."""
    if type(profile) is not GenerationProfile:
        raise ValueError("profile must be a GenerationProfile")
    if type(max_new_tokens) is not int or max_new_tokens <= 0:
        raise ValueError("max_new_tokens must be a positive integer")
    if type(do_sample) is not bool:
        raise ValueError("do_sample must be a boolean")
    if (
        isinstance(temperature, bool)
        or not isinstance(temperature, (int, float))
        or not isfinite(temperature)
        or temperature < 0
    ):
        raise ValueError("temperature must be a finite non-negative number")
    if (
        isinstance(top_p, bool)
        or not isinstance(top_p, (int, float))
        or not isfinite(top_p)
        or not 0 < top_p <= 1
    ):
        raise ValueError("top_p must be a finite number in (0, 1]")

    if profile is GenerationProfile.STRUCTURED_DECISION:
        return ResolvedGenerationOptions(
            max_new_tokens=min(
                max_new_tokens,
                STRUCTURED_DECISION_MAX_NEW_TOKENS,
            ),
            do_sample=False,
        )

    sampling_enabled = do_sample and temperature > 0
    if not sampling_enabled:
        return ResolvedGenerationOptions(
            max_new_tokens=max_new_tokens,
            do_sample=False,
        )
    return ResolvedGenerationOptions(
        max_new_tokens=max_new_tokens,
        do_sample=True,
        temperature=float(temperature),
        top_p=float(top_p),
    )
