"""Drive the product's inline assistant confirmation card in UI walkthroughs."""

from __future__ import annotations

from typing import Any


def describe_visible_confirmation_card(
    panel: Any,
    *,
    approved: bool,
) -> dict[str, Any] | None:
    """Return serializable evidence for one actionable inline card."""
    card = getattr(panel, "confirmation_card_widget", None)
    if card is None or not card.isVisible():
        return None
    request_id = getattr(card, "request_id", None)
    if not isinstance(request_id, str) or not request_id:
        return None
    command_name = getattr(card, "command_name", None)
    if not isinstance(command_name, str) or not command_name:
        return None
    button = card.primary_button if approved else card.secondary_button
    if not button.isEnabled():
        return None
    return {
        "surface": "inline_card",
        "request_id": request_id,
        "command_name": command_name,
        "title": _widget_text(card.title_label),
        "action": _widget_text(card.description_label)
        or _widget_text(card.primary_button),
        "reason": _widget_text(card.reason_label),
        "approved": approved,
    }


def resolve_visible_confirmation_card(
    panel: Any,
    *,
    request_id: str,
    expected_command_name: str,
    approved: bool,
) -> bool:
    """Click only the exact visible request and expected product command."""
    event = describe_visible_confirmation_card(panel, approved=approved)
    if (
        event is None
        or event["request_id"] != request_id
        or event["command_name"] != expected_command_name
    ):
        return False
    card = panel.confirmation_card_widget
    button = card.primary_button if approved else card.secondary_button
    button.click()
    return True


def _widget_text(widget: Any) -> str:
    value = widget.text()
    return " ".join(value.split()) if isinstance(value, str) else ""
