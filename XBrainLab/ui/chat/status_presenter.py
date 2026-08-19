"""Pure product-language presentation for assistant workflow status."""

from __future__ import annotations


def assistant_footer_hint(
    stage: str,
    display_commands: list[str] | None,
    blocked_reason: str | None = None,
) -> str:
    """Return a stage-only status-bar hint without duplicating panel actions."""
    del display_commands
    if blocked_reason:
        return f"{stage} · Action required"
    if stage == "No data loaded":
        return "No EEG data open"
    return stage
