"""Heuristic confidence estimator for LLM tool calls.

When the LLM provider does not expose token-level log-probabilities,
this module derives a ``0.0-1.0`` confidence score from observable
structural cues in the raw response text and parsed command(s).

Scoring heuristics (each contributes a fraction of 1.0):

* **JSON in code fence** (+0.25) — tool output wrapped in ````json```
* **Single command** (+0.15) — exactly one tool call (vs. ambiguous multi)
* **Known tool name** (+0.20) — tool_name matches a registered tool
* **Non-empty parameters** (+0.15) — parameters dict is non-trivial
* **No surrounding prose** (+0.15) — response is *only* JSON
* **No retry markers** (+0.10) — does not contain "sorry" / "I think"
"""

from __future__ import annotations

import re

from XBrainLab.llm.pipeline_state import STAGE_CONFIG


def _collect_known_tools() -> frozenset[str]:
    """Derive the set of known tool names from :data:`STAGE_CONFIG`.

    This keeps the confidence heuristic automatically in sync with the
    pipeline state machine — no manual duplication needed.
    """
    names: set[str] = set()
    for config in STAGE_CONFIG.values():
        names.update(config["tools"])
    return frozenset(names)


#: Tool names derived from STAGE_CONFIG (always in sync).
_KNOWN_TOOLS: frozenset[str] = _collect_known_tools()

_HEDGE_PATTERN = re.compile(
    r"\b(i think|maybe|sorry|i'?m not sure|possibly|i believe)\b",
    re.IGNORECASE,
)

_JSON_FENCE = re.compile(r"```json\s*\n")


def estimate_confidence(
    response_text: str,
    commands: list[tuple[str, dict]],
    known_tools: frozenset[str] | None = None,
) -> float:
    """Return a heuristic confidence score in ``[0.0, 1.0]``.

    Args:
        response_text: The raw LLM response before any parsing.
        commands: Parsed ``(tool_name, params)`` tuples.
        known_tools: Optional override for the set of valid tool names.

    Returns:
        A float between 0.0 and 1.0 representing structural confidence.
    """
    if not commands:
        return 0.0

    tools = known_tools if known_tools is not None else _KNOWN_TOOLS
    score = 0.0

    # 1. JSON inside a code-fence (+0.25)
    if _JSON_FENCE.search(response_text):
        score += 0.25

    # 2. Single unambiguous command (+0.15)
    if len(commands) == 1:
        score += 0.15

    # 3. Known tool name (+0.20)
    if all(name in tools for name, _ in commands):
        score += 0.20

    # 4. Non-empty parameters (+0.15)
    if all(bool(params) for _, params in commands):
        score += 0.15

    # 5. Response is mostly JSON — little surrounding prose (+0.15)
    stripped = response_text.strip()
    if stripped.startswith(("{", "[", "```")):
        score += 0.15

    # 6. No hedging language (+0.10)
    if not _HEDGE_PATTERN.search(response_text):
        score += 0.10

    return min(score, 1.0)
