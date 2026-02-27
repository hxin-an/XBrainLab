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

#: Tool names that the system supports (kept in sync with ToolRegistry).
_KNOWN_TOOLS: frozenset[str] = frozenset(
    {
        "load_data",
        "attach_labels",
        "get_data_summary",
        "apply_filter",
        "apply_notch_filter",
        "resample_data",
        "set_montage",
        "epoch_data",
        "set_model",
        "configure_training",
        "run_training",
        "stop_training",
        "get_training_status",
        "export_output_csv",
        "evaluate",
        "get_result_summary",
        "generate_saliency",
        "get_channel_names",
        "select_channels",
    },
)

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
