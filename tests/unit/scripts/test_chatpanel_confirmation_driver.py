from types import SimpleNamespace

from scripts.dev.chatpanel_confirmation_driver import (
    describe_visible_confirmation_card,
    resolve_visible_confirmation_card,
)


class _Button:
    def __init__(self, text: str, *, enabled: bool = True) -> None:
        self._text = text
        self._enabled = enabled
        self.click_count = 0

    def text(self) -> str:
        return self._text

    def isEnabled(self) -> bool:
        return self._enabled

    def click(self) -> None:
        self.click_count += 1


class _Label:
    def __init__(self, text: str) -> None:
        self._text = text

    def text(self) -> str:
        return self._text


def _panel(*, visible: bool = True, enabled: bool = True):
    card = SimpleNamespace(
        request_id="confirmation-1",
        command_name="start_training",
        isVisible=lambda: visible,
        title_label=_Label("Confirmation required"),
        description_label=_Label("Start training"),
        reason_label=_Label("Training will use the current settings."),
        primary_button=_Button("Start training", enabled=enabled),
        secondary_button=_Button("Cancel", enabled=enabled),
    )
    return SimpleNamespace(confirmation_card_widget=card), card


def test_describe_visible_confirmation_card_returns_typed_ui_evidence() -> None:
    panel, _card = _panel()

    event = describe_visible_confirmation_card(panel, approved=False)

    assert event == {
        "surface": "inline_card",
        "request_id": "confirmation-1",
        "command_name": "start_training",
        "title": "Confirmation required",
        "action": "Start training",
        "reason": "Training will use the current settings.",
        "approved": False,
    }


def test_hidden_or_submitting_confirmation_card_is_not_actionable() -> None:
    hidden_panel, _hidden_card = _panel(visible=False)
    submitting_panel, _submitting_card = _panel(enabled=False)

    assert describe_visible_confirmation_card(hidden_panel, approved=True) is None
    assert describe_visible_confirmation_card(submitting_panel, approved=True) is None


def test_resolve_visible_confirmation_card_clicks_correlated_choice_only() -> None:
    panel, card = _panel()

    assert (
        resolve_visible_confirmation_card(
            panel,
            request_id="stale-confirmation",
            expected_command_name="start_training",
            approved=True,
        )
        is False
    )
    assert card.primary_button.click_count == 0
    assert (
        resolve_visible_confirmation_card(
            panel,
            request_id="confirmation-1",
            expected_command_name="reset_preprocess",
            approved=True,
        )
        is False
    )
    assert card.primary_button.click_count == 0
    assert (
        resolve_visible_confirmation_card(
            panel,
            request_id="confirmation-1",
            expected_command_name="start_training",
            approved=False,
        )
        is True
    )
    assert card.secondary_button.click_count == 1
    assert card.primary_button.click_count == 0
