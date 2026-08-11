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
    excluded_commands: tuple[CommandName, ...] = ()

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
        excluded = self.excluded_commands
        if not isinstance(excluded, tuple):
            raise TypeError("Excluded workflow commands must be a tuple.")
        if any(not isinstance(command, CommandName) for command in excluded):
            raise TypeError("Excluded workflow commands must be typed.")
        if len(set(excluded)) != len(excluded):
            raise ValueError("Excluded workflow commands must be unique.")


_SINGLE = AssistantTurnScopeResolution(AssistantTurnScope.SINGLE_ACTION)
_GUIDED = AssistantTurnScopeResolution(AssistantTurnScope.GUIDED_WORKFLOW)
_WORKFLOW_ORDER = {
    CommandName.SCAN_SOURCE.value: 10,
    CommandName.PREVIEW_INTERPRETATION.value: 20,
    CommandName.VALIDATE_INTERPRETATION.value: 30,
    CommandName.APPLY_INTERPRETATION.value: 40,
    CommandName.PREPROCESS.value: 50,
    CommandName.CREATE_EPOCH.value: 60,
    CommandName.CONFIGURE_DATASET_SPLIT.value: 70,
    CommandName.CONFIGURE_TRAINING.value: 80,
    CommandName.TRAIN.value: 90,
    CommandName.STOP_TRAINING.value: 95,
    CommandName.EVALUATE.value: 100,
    CommandName.VISUALIZE.value: 110,
    CommandName.SALIENCY.value: 110,
}


@dataclass(frozen=True, slots=True)
class _WorkflowStageSpec:
    """One shared vocabulary for endpoint and exclusion detection."""

    command: CommandName
    mention_pattern: str
    english_exclusion_pattern: str
    chinese_exclusion_pattern: str


_WORKFLOW_STAGE_SPECS = (
    _WorkflowStageSpec(
        command=CommandName.SCAN_SOURCE,
        mention_pattern=r"\b(?:load|import|scan)\b|載入|匯入|讀取",
        english_exclusion_pattern=r"(?:load|import|scan)(?:ing)?",
        chinese_exclusion_pattern=r"(?:載入|匯入|掃描|讀取)",
    ),
    _WorkflowStageSpec(
        command=CommandName.PREVIEW_INTERPRETATION,
        mention_pattern=(
            r"\bpreview\b.{0,24}\b(?:interpretation|import)\b"
            r"|預覽(?:資料)?解讀|預覽匯入"
        ),
        english_exclusion_pattern=(
            r"preview(?:ing)?\s+(?:the\s+)?(?:data\s+)?"
            r"(?:interpretation|import)"
        ),
        chinese_exclusion_pattern=r"(?:預覽(?:資料)?解讀|預覽匯入)",
    ),
    _WorkflowStageSpec(
        command=CommandName.VALIDATE_INTERPRETATION,
        mention_pattern=(
            r"\bvalidat(?:e|ing|ion)\b.{0,32}"
            r"\b(?:interpretation|candidate|import)\b"
            r"|驗證(?:資料)?解讀|驗證匯入"
        ),
        english_exclusion_pattern=(
            r"validat(?:e|ing|ion)\s+(?:the\s+)?(?:data\s+)?"
            r"(?:interpretation|candidate|import)"
        ),
        chinese_exclusion_pattern=r"(?:驗證(?:資料)?解讀|驗證匯入)",
    ),
    _WorkflowStageSpec(
        command=CommandName.APPLY_INTERPRETATION,
        mention_pattern=(
            r"\bapply\b.{0,24}\b(?:interpretation|import)\b"
            r"|\bconfirm\b.{0,16}\bimport\b"
            r"|套用(?:資料)?解讀|確認匯入"
        ),
        english_exclusion_pattern=(
            r"(?:apply(?:ing)?\s+(?:the\s+)?(?:data\s+)?interpretation|"
            r"confirm(?:ing)?\s+(?:the\s+)?import)"
        ),
        chinese_exclusion_pattern=r"(?:套用(?:資料)?解讀|確認匯入)",
    ),
    _WorkflowStageSpec(
        command=CommandName.PREPROCESS,
        mention_pattern=(
            r"\b(?:preprocess|filter|resample|re-reference|rereference)\b"
            r"|前處理|濾波|重採樣|重參考"
        ),
        english_exclusion_pattern=(
            r"(?:preprocess(?:ing)?|filter(?:ing)?|resampl(?:e|ing)|"
            r"re-?referenc(?:e|ing))"
        ),
        chinese_exclusion_pattern=r"(?:前處理|濾波|重採樣|重參考)",
    ),
    _WorkflowStageSpec(
        command=CommandName.CREATE_EPOCH,
        mention_pattern=(
            r"\b(?:create|make|build)\s+epochs?\b|\bepoching\b"
            r"|切片段|建立\s*epochs?"
        ),
        english_exclusion_pattern=(r"(?:(?:create|make|build)\s+epochs?|epoching)"),
        chinese_exclusion_pattern=r"(?:建立epochs?|切epochs?|切片段)",
    ),
    _WorkflowStageSpec(
        command=CommandName.CONFIGURE_DATASET_SPLIT,
        mention_pattern=(
            r"\b(?:split|generate)\b.{0,24}\bdataset\b|資料切分|建立資料集"
        ),
        english_exclusion_pattern=(
            r"(?:generate|split)\s+(?:(?:the|a|this)\s+)?dataset"
        ),
        chinese_exclusion_pattern=r"(?:建立資料集|資料切分)",
    ),
    _WorkflowStageSpec(
        command=CommandName.CONFIGURE_TRAINING,
        mention_pattern=(
            r"\b(?:configure|select|set)\b.{0,32}"
            r"\b(?:model|batch|training)\b|設定模型|設定訓練"
        ),
        english_exclusion_pattern=(
            r"(?:(?:configure|set|select)\s+"
            r"(?:(?:the|a|this|current)\s+)?"
            r"(?:training|model|batch(?:\s+size)?)|"
            r"training\s+(?:configuration|settings?|setup))"
        ),
        chinese_exclusion_pattern=(r"(?:(?:設定|配置)(?:訓練|模型|批次)|選擇模型)"),
    ),
    _WorkflowStageSpec(
        command=CommandName.TRAIN,
        mention_pattern=(
            r"\btrain\b|\b(?:start|run|begin)\s+training\b"
            r"|開始訓練|進行訓練|訓練(?:模型|資料)"
        ),
        english_exclusion_pattern=(
            r"(?:(?:start|begin|run)\s+training|"
            r"train(?:ing)?(?!\s+(?:data|labels?|settings?|configuration|setup)\b))"
        ),
        chinese_exclusion_pattern=(r"(?:(?:開始|進行)?訓練(?!標籤|資料|設定|配置))"),
    ),
    _WorkflowStageSpec(
        command=CommandName.STOP_TRAINING,
        mention_pattern=r"\b(?:stop|cancel)\s+training\b|停止訓練|取消訓練",
        english_exclusion_pattern=r"(?:stop|cancel)(?:ping)?\s+training",
        chinese_exclusion_pattern=r"(?:停止訓練|取消訓練)",
    ),
    _WorkflowStageSpec(
        command=CommandName.EVALUATE,
        mention_pattern=r"\bevaluat(?:e|ion)\b|評估",
        english_exclusion_pattern=r"evaluat(?:e|ing|ion)",
        chinese_exclusion_pattern=r"評估",
    ),
    _WorkflowStageSpec(
        command=CommandName.VISUALIZE,
        mention_pattern=r"\bvisuali[sz](?:e|ing|ation)\b|視覺化|可視化",
        english_exclusion_pattern=r"visuali[sz](?:e|ing|ation)",
        chinese_exclusion_pattern=r"(?:視覺化|可視化)",
    ),
    _WorkflowStageSpec(
        command=CommandName.SALIENCY,
        mention_pattern=r"\bsaliency\b|顯著圖",
        english_exclusion_pattern=(r"(?:(?:compute|generate)\s+saliency|saliency)"),
        chinese_exclusion_pattern=r"(?:計算顯著圖?|顯著圖)",
    ),
)


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
    excluded_commands = _excluded_workflow_commands(normalized)
    if intent in {
        "no_tool",
        "query_state",
        "browse_files",
        "ask_clarification",
    } or _is_hypothetical(normalized):
        return (
            AssistantTurnScopeResolution(
                AssistantTurnScope.SINGLE_ACTION,
                excluded_commands=excluded_commands,
            )
            if excluded_commands
            else _SINGLE
        )
    if excluded_commands:
        return AssistantTurnScopeResolution(
            AssistantTurnScope.SINGLE_ACTION,
            excluded_commands=excluded_commands,
        )

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


def _is_hypothetical(normalized: str) -> bool:
    if re.search(
        r"\b(?:what\s+(?:would|will)|what\s+happens?|if|suppose|unless)\b",
        normalized,
    ):
        return True
    compact = re.sub(r"\s+", "", normalized)
    return any(marker in compact for marker in ("如果", "假如", "會發生什麼", "會怎樣"))


def _excluded_workflow_commands(normalized: str) -> tuple[CommandName, ...]:
    """Extract user-authored workflow exclusions as immutable host policy."""
    compact = re.sub(r"\s+", "", normalized)
    english_negation = (
        r"(?:"
        r"do\s+not|don't|never|without|no|"
        r"not(?!\s+(?:only|just|merely)\b)|"
        r"avoid(?:s|ed|ing)?|except|skip(?:s|ped|ping)?|"
        r"exclud(?:e|es|ed|ing)"
        r")"
    )
    modifiers = (
        r"(?:(?:for|the|this|that|current|any|all|further|directly|"
        r"immediately|apply(?:ing)?|use|using|do|doing|perform(?:ing)?|"
        r"run(?:ning)?|execute|executing|start(?:ing)?|begin(?:ning)?|"
        r"complete|completing|finish|finishing)\s+){0,4}"
    )
    chinese_negation = (
        r"(?:不要|別|略過|跳過|排除|避免|除了|除外|無需|毋須|"
        r"不(?!只|僅|但))"
    )
    chinese_modifiers = r"(?:(?:再|進行|做|執行|完成|開始|直接|使用))*"
    return tuple(
        stage.command
        for stage in _WORKFLOW_STAGE_SPECS
        if re.search(
            rf"\b{english_negation}\b\s+{modifiers}"
            rf"(?:{stage.english_exclusion_pattern})\b",
            normalized,
        )
        or re.search(
            rf"{chinese_negation}{chinese_modifiers}"
            rf"(?:{stage.chinese_exclusion_pattern})",
            compact,
        )
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
        return CommandName.CONFIGURE_DATASET_SPLIT

    stages = _ordered_stage_mentions(normalized)
    commands = {command for _, command in stages}
    if len(commands) < 2:
        return None
    highest_order = max(_WORKFLOW_ORDER[command.value] for command in commands)
    highest_stage_mentions = [
        (position, command)
        for position, command in stages
        if _WORKFLOW_ORDER[command.value] == highest_order
    ]
    latest_position = max(position for position, _ in highest_stage_mentions)
    latest_commands = {
        command
        for position, command in highest_stage_mentions
        if position == latest_position
    }
    if len(latest_commands) != 1:
        return None
    return latest_commands.pop()


def _ordered_stage_mentions(normalized: str) -> list[tuple[int, CommandName]]:
    mentions: list[tuple[int, CommandName]] = []
    for stage in _WORKFLOW_STAGE_SPECS:
        mentions.extend(
            (match.start(), stage.command)
            for match in re.finditer(stage.mention_pattern, normalized)
        )
    return sorted(mentions, key=lambda mention: mention[0])
