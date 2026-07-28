"""Resolve one immutable host execution scope from a user-authored turn."""

from __future__ import annotations

import re
from dataclasses import dataclass

from XBrainLab.backend.application import CommandName

from .intent import infer_user_intent, is_explicit_workflow_continuation
from .turn import AssistantTurnScope


@dataclass(frozen=True, slots=True)
class AssistantTurnScopeResolution:
    """Host autonomy and optional endpoint granted to one user turn."""

    scope: AssistantTurnScope
    terminal_command: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scope, AssistantTurnScope):
            raise TypeError("Assistant turn scope resolution must be typed.")
        if self.terminal_command is not None:
            if self.scope is not AssistantTurnScope.GUIDED_WORKFLOW:
                raise ValueError(
                    "Only guided workflow scope may define a terminal command."
                )
            if not isinstance(self.terminal_command, str):
                raise TypeError("Terminal command must be a string.")
            normalized = self.terminal_command.strip()
            if not normalized:
                raise ValueError("Terminal command must not be empty.")
            object.__setattr__(self, "terminal_command", normalized)


_SINGLE = AssistantTurnScopeResolution(AssistantTurnScope.SINGLE_ACTION)
_GUIDED = AssistantTurnScopeResolution(AssistantTurnScope.GUIDED_WORKFLOW)
_WORKFLOW_ORDER = {
    CommandName.SCAN_SOURCE.value: 10,
    CommandName.PREVIEW_INTERPRETATION.value: 20,
    CommandName.VALIDATE_INTERPRETATION.value: 30,
    CommandName.APPLY_INTERPRETATION.value: 40,
    CommandName.PREPROCESS.value: 50,
    CommandName.CREATE_EPOCH.value: 60,
    CommandName.GENERATE_DATASET.value: 70,
    CommandName.CONFIGURE_TRAINING.value: 80,
    CommandName.TRAIN.value: 90,
    CommandName.EVALUATE.value: 100,
    CommandName.VISUALIZE.value: 110,
    CommandName.SALIENCY.value: 110,
}


def resolve_assistant_turn_scope(text: str) -> AssistantTurnScopeResolution:
    """Resolve safe turn autonomy without delegating policy to the LLM.

    A direct command remains one action. Explicit workflow continuation may
    proceed one verified command at a time until the next decision boundary.
    A multi-stage request is widened only when it names an unambiguous endpoint;
    that endpoint is carried with the request and enforced by the controller.
    """
    normalized = " ".join(str(text or "").casefold().split())
    if not normalized:
        return _SINGLE

    intent = infer_user_intent(text)
    if intent in {
        "no_tool",
        "query_state",
        "browse_files",
        "ask_clarification",
    } or _is_hypothetical_or_negated(normalized):
        return _SINGLE

    if is_explicit_workflow_continuation(text) or _continues_until_decision(normalized):
        return _GUIDED

    terminal = _explicit_workflow_endpoint(normalized)
    if terminal is None:
        return _SINGLE
    return AssistantTurnScopeResolution(
        AssistantTurnScope.GUIDED_WORKFLOW,
        terminal.value,
    )


def workflow_command_is_within_endpoint(
    command_name: str,
    terminal_command: str | None,
) -> bool:
    """Return whether a projected command stays inside the delegated goal."""
    if terminal_command is None:
        return True
    command_order = _WORKFLOW_ORDER.get(str(command_name))
    terminal_order = _WORKFLOW_ORDER.get(str(terminal_command))
    if command_order is None or terminal_order is None:
        return command_name == terminal_command
    return command_order <= terminal_order


def _is_hypothetical_or_negated(normalized: str) -> bool:
    if re.search(
        r"\b(?:what\s+(?:would|will)|what\s+happens?|if|suppose|"
        r"do\s+not|don't|never|without)\b",
        normalized,
    ):
        return True
    compact = re.sub(r"\s+", "", normalized)
    return any(
        marker in compact
        for marker in ("如果", "假如", "會發生什麼", "會怎樣", "不要", "別", "不可")
    )


def _continues_until_decision(normalized: str) -> bool:
    """Recognize explicit delegation that names the next decision as its bound."""
    if re.search(
        r"\bcontinue\s+until\s+(?:a\s+|the\s+)?"
        r"(?:decision|choice|confirmation)\s+(?:is\s+)?(?:needed|required)\b",
        normalized,
    ):
        return True
    compact = re.sub(r"\s+", "", normalized)
    return bool(
        re.search(
            r"(?:繼續|往下做|繼續執行).{0,12}(?:需要|遇到)"
            r".{0,4}(?:決定|選擇|確認)(?:時|為止)",
            compact,
        )
    )


def _explicit_workflow_endpoint(normalized: str) -> CommandName | None:
    compact = re.sub(r"\s+", "", normalized)

    if (
        re.search(
            r"\b(?:finish|complete)\b.{0,56}\bdata\s+import\s+workflow\b",
            normalized,
        )
        or re.search(r"\bimport\b.{0,48}\b(?:workflow|process)\b", normalized)
        or re.search(r"(?:完成|跑完|做完).{0,20}(?:資料)?匯入流程", compact)
    ):
        return CommandName.APPLY_INTERPRETATION

    if re.search(
        r"\bprepare\b.{0,64}\b(?:for\s+training|to\s+train)\b", normalized
    ) or re.search(r"(?:準備|處理).{0,24}(?:可以|能夠)?訓練", compact):
        return CommandName.GENERATE_DATASET

    stages = _ordered_stage_mentions(normalized)
    commands = {command for _, command in stages}
    if len(commands) < 2:
        return None
    return max(commands, key=lambda command: _WORKFLOW_ORDER[command.value])


def _ordered_stage_mentions(normalized: str) -> list[tuple[int, CommandName]]:
    patterns = (
        (CommandName.SCAN_SOURCE, r"\b(?:load|import|scan)\b|載入|匯入|讀取"),
        (
            CommandName.PREPROCESS,
            r"\b(?:preprocess|filter|resample|re-reference|rereference)\b"
            r"|前處理|濾波|重採樣|重參考",
        ),
        (
            CommandName.CREATE_EPOCH,
            r"\b(?:create|make|build)\s+epochs?\b|\bepoching\b"
            r"|切片段|建立\s*epochs?",
        ),
        (
            CommandName.GENERATE_DATASET,
            r"\b(?:split|generate)\b.{0,24}\bdataset\b|資料切分|建立資料集",
        ),
        (
            CommandName.CONFIGURE_TRAINING,
            r"\b(?:configure|select|set)\b.{0,32}"
            r"\b(?:model|batch|training)\b|設定模型|設定訓練",
        ),
        (
            CommandName.TRAIN,
            r"\btrain\b|\b(?:start|run|begin)\s+training\b"
            r"|開始訓練|進行訓練|訓練(?:模型|資料)",
        ),
        (CommandName.EVALUATE, r"\bevaluat(?:e|ion)\b|評估"),
        (
            CommandName.VISUALIZE,
            r"\b(?:visuali[sz]e|saliency)\b|視覺化|可視化|顯著圖",
        ),
    )
    mentions: list[tuple[int, CommandName]] = []
    for command, pattern in patterns:
        match = re.search(pattern, normalized)
        if match is not None:
            mentions.append((match.start(), command))
    return mentions
