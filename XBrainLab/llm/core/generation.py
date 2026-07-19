"""Per-turn generation policy resolved before a backend is invoked."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

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
        if self.max_new_tokens <= 0:
            raise ValueError("max_new_tokens must be positive")
        if self.do_sample:
            if self.temperature is None or self.temperature <= 0:
                raise ValueError("sampling requires a positive temperature")
            if self.top_p is None or not 0 < self.top_p <= 1:
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
    if profile is GenerationProfile.STRUCTURED_DECISION:
        return ResolvedGenerationOptions(
            max_new_tokens=min(
                int(max_new_tokens),
                STRUCTURED_DECISION_MAX_NEW_TOKENS,
            ),
            do_sample=False,
        )

    sampling_enabled = bool(do_sample) and float(temperature) > 0
    if not sampling_enabled:
        return ResolvedGenerationOptions(
            max_new_tokens=int(max_new_tokens),
            do_sample=False,
        )
    return ResolvedGenerationOptions(
        max_new_tokens=int(max_new_tokens),
        do_sample=True,
        temperature=float(temperature),
        top_p=float(top_p),
    )
