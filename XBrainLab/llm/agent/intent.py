"""Lightweight user-intent helpers for agent command boundaries."""

from __future__ import annotations

import re
from dataclasses import dataclass

from XBrainLab.backend.application import CommandName
from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS

from .training_request import (
    contains_explicit_training_options,
    extract_explicit_training_model,
)

INTENT_TO_COMMAND: dict[str, CommandName] = AGENT_ACTION_CONTRACTS.intent_to_command()


@dataclass(frozen=True, slots=True)
class BlockedExplanationIntent:
    """Resolved workflow target for one state-readiness explanation."""

    target_intents: tuple[str, ...]

    @property
    def target_intent(self) -> str | None:
        return self.target_intents[0] if len(self.target_intents) == 1 else None

    @property
    def target_command(self) -> CommandName | None:
        intent = self.target_intent
        return command_for_intent(intent) if intent is not None else None

    @property
    def ambiguous(self) -> bool:
        return len(self.target_intents) != 1


def resolve_blocked_explanation_intent(
    text: str,
) -> BlockedExplanationIntent | None:
    """Resolve an inability/readiness question to exactly one workflow command.

    ``None`` means the text is not asking about current application readiness.
    A returned object without a target is deliberately ambiguous and must not be
    answered from a guessed command.
    """
    normalized = text.casefold().replace("\u2019", "'")
    if not _has_blocked_explanation_language(normalized):
        return None

    target_clause = _blocked_explanation_target_clause(normalized)
    if _is_knowledge_definition_clause(target_clause):
        return None

    targets = _blocked_target_intents(target_clause)
    if not targets and not _has_workflow_reference(normalized):
        return None
    return BlockedExplanationIntent(target_intents=targets)


def is_explicit_workflow_continuation(text: str) -> bool:
    """Return whether the user explicitly asks to advance the current workflow."""
    normalized = " ".join(text.casefold().strip().split()).rstrip(
        ".?!\u3002\uff01\uff1f"
    )
    if normalized in {
        "continue",
        "continue the workflow",
        "next",
        "next step",
        "proceed",
        "proceed to the next step",
        "\u7e7c\u7e8c",
        "\u4e0b\u4e00\u6b65",
    }:
        return True

    if re.fullmatch(
        r"(?:please\s+)?(?:continue|proceed)\s+"
        r"(?:with|to|through)\s+"
        r"(?:(?:the|this|that|current)\s+)?"
        r"(?:reviewed\s+)?"
        r"(?:workflow|process|import|recording|data|dataset|analysis|next\s+step|it)",
        normalized,
    ):
        return True

    return bool(
        re.fullmatch(
            r"\u7e7c\u7e8c(?:\u76ee\u524d|\u9019\u500b|\u8a72)?"
            r"(?:\u6d41\u7a0b|\u6b65\u9a5f|\u532f\u5165|\u8cc7\u6599|\u5206\u6790|\u8655\u7406)",
            normalized,
        )
    )


def is_unresolved_historical_action_reference(text: str) -> bool:
    """Return whether an action points only to non-authoritative earlier prose."""
    normalized = " ".join(text.casefold().strip().split()).strip(
        " \t\r\n.,!?;:\u3002\uff0c\uff01\uff1f\uff1b\uff1a"
    )
    if not normalized:
        return False
    if _is_explanatory_no_tool_request(normalized) or is_explicit_workflow_continuation(
        normalized
    ):
        return False

    if _has_authoritative_current_surface_reference(normalized):
        return False

    explicit_numeric_condition = bool(
        re.search(
            r"\d(?:[\d.\s-]*\d)?\s*"
            r"(?:hz|khz|ms|milliseconds?|seconds?|minutes?|%|percent)\b",
            normalized,
        )
    )
    if explicit_numeric_condition:
        return False

    english_action = bool(
        re.match(
            r"^(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?"
            r"(?:use|do|choose|select|pick|run|open|take|execute|apply|follow|"
            r"go\s+with)\b",
            normalized,
        )
        or re.match(
            r"^let(?:'s|\s+us)\s+"
            r"(?:use|do|choose|select|pick|run|open|take|execute|apply|follow|"
            r"go\s+with)\b",
            normalized,
        )
    )
    english_historical = bool(
        re.search(
            r"\b(?:earlier|before|previous|prior|above|last|formerly)\b",
            normalized,
        )
    )
    english_reference = bool(
        re.search(
            r"\b(?:option|choice|action|step|setting|model|configuration|"
            r"parameter|selection|suggestion|recommendation|one|what)\b",
            normalized,
        )
        or re.search(r"\b(?:mentioned|suggested|recommended|proposed)\b", normalized)
    )
    english_deictic = bool(
        re.search(
            r"\b(?:that|this)\s+"
            r"(?:one|option|choice|action|step|suggestion|recommendation)\b",
            normalized,
        )
    )
    english_bare_deictic = bool(
        re.fullmatch(
            r"(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?"
            r"(?:use|do|choose|select|pick|run|open|take|execute|apply|follow|"
            r"go\s+with)\s+(?:it|that|this)",
            normalized,
        )
        or re.fullmatch(
            r"let(?:'s|\s+us)\s+"
            r"(?:use|do|choose|select|pick|run|open|take|execute|apply|follow|"
            r"go\s+with)\s+(?:it|that|this)",
            normalized,
        )
    )
    english_standalone_deictic = bool(
        re.fullmatch(r"(?:it|this|that|this\s+one|that\s+one)", normalized)
    )

    chinese_action = bool(
        re.match(
            r"^(?:(?:可以|能否|能不能|可否)(?:請)?(?:幫我)?|"
            r"(?:那)?就|請幫我|幫我|請)?"
            r"(?:用|使用|套用|選|選擇|執行|開啟|採用|照|依照|做|跑)",
            normalized,
        )
    )
    chinese_historical = any(
        marker in normalized
        for marker in (
            "剛剛",
            "剛才",
            "之前",
            "先前",
            "前面",
            "上面",
            "上次",
            "前一個",
        )
    )
    chinese_reference = any(
        marker in normalized
        for marker in (
            "那個",
            "選項",
            "操作",
            "步驟",
            "設定",
            "模型",
            "建議",
            "提到",
            "提過",
            "前一個",
            "它",
            "這個",
        )
    )
    chinese_elliptical_reference = normalized.endswith(
        ("剛剛的", "剛才的", "之前的", "先前的", "前面的", "上面的")
    )
    chinese_bare_deictic = bool(
        re.fullmatch(
            r"(?:(?:用|使用|套用|選|選擇|執行|開啟|採用|做))?"
            r"(?:它|這個|那個)",
            normalized,
        )
    )
    return bool(
        english_bare_deictic
        or english_standalone_deictic
        or (
            english_action
            and english_reference
            and (english_historical or english_deictic)
        )
    ) or bool(
        chinese_bare_deictic
        or (
            chinese_action
            and (
                (chinese_reference and (chinese_historical or "那個" in normalized))
                or chinese_elliptical_reference
            )
        )
    )


def _has_authoritative_current_surface_reference(normalized: str) -> bool:
    """Recognize a spatial locator on a current or explicitly named UI surface."""
    surface = r"(?:dialog|wizard|panel|window|screen|menu|list|row|form)"

    # An explicit current-surface locator is authoritative even when the user
    # asks for a spatially previous row within that surface.
    if re.search(
        rf"\b(?:current|open|this)\s+(?:[\w-]+\s+){{0,4}}{surface}\b",
        normalized,
    ):
        return True
    if re.search(
        r"(?:目前|當前|這個)(?:對話框|精靈|面板|視窗|畫面|選單|列表|表單)",
        normalized,
    ):
        return True

    # Temporal references remain unresolved regardless of whether the named
    # surface appears before or after the marker. A dialog name identifies the
    # workflow area, but not which earlier prose or recommendation was meant.
    if re.search(
        r"\b(?:earlier|before|previous|prior|last|former|formerly)\b",
        normalized,
    ):
        return False
    if any(
        marker in normalized
        for marker in ("剛剛", "剛才", "之前", "先前", "前面", "上次")
    ):
        return False

    if re.search(
        rf"\b{surface}\b.{{0,80}}\b"
        r"(?:mentioned|suggested|recommended|proposed)\b",
        normalized,
    ):
        return False
    if re.search(
        rf"\b(?:in|inside|within|on|from)\s+(?:the\s+)?"
        rf"(?:[\w-]+\s+){{1,5}}{surface}\b",
        normalized,
    ):
        return True
    return bool(
        re.search(
            r"[\u4e00-\u9fffA-Za-z0-9_]{1,16}"
            r"(?:對話框|精靈|面板|視窗|畫面|選單|列表|表單)"
            r"(?:中|內|裡|上面|上方|下面|下方|的)",
            normalized,
        )
    )


def infer_user_intent(text: str) -> str:
    """Infer the next workflow intent from user-visible text."""
    normalized = text.lower()
    has_it = re.search(r"\bit\b", normalized) is not None
    blocked_explanation = resolve_blocked_explanation_intent(text)
    if blocked_explanation is not None:
        return blocked_explanation.target_intent or "ask_clarification"
    if is_unresolved_historical_action_reference(text):
        return "ask_clarification"
    if _is_workflow_state_request(normalized):
        return "query_state"
    if _is_file_browse_request(normalized):
        return "browse_files"
    if _is_explanatory_no_tool_request(normalized):
        return "no_tool"
    if _is_ambiguous_workflow_request(normalized):
        return "ask_clarification"
    if _is_explicit_legacy_load_request(normalized):
        return "load_data"
    if _is_reset_preprocess_request(normalized):
        return "reset_preprocess"
    if "reset" in normalized or "clear the dataset" in normalized:
        return "reset_session"
    if "重設" in normalized or "清空" in normalized:
        return "reset_session"
    if re.search(r"\b(?:validate|validation)\b", normalized) and (
        "interpret" in normalized or "candidate" in normalized or has_it
    ):
        return "validate_interpretation"
    if "check whether" in normalized and "interpretation" in normalized:
        return "validate_interpretation"
    if "reload recipe" in normalized or "reload the interpretation recipe" in (
        normalized
    ):
        return "reload_interpretation_recipe"
    if "remap" in normalized and (
        "recipe" in normalized
        or "eeg file" in normalized
        or "label carrier" in normalized
        or "event carrier" in normalized
        or "saved" in normalized
    ):
        return "preview_interpretation"
    if "save" in normalized and "recipe" in normalized:
        return "save_interpretation_recipe"
    if "儲存" in normalized and "recipe" in normalized:
        return "save_interpretation_recipe"
    if "apply" in normalized and ("interpret" in normalized or has_it):
        return "apply_interpretation"
    if _is_reviewed_import_apply_request(normalized):
        return "apply_interpretation"
    if "preview" in normalized and (
        "interpret" in normalized
        or "candidate" in normalized
        or "subject" in normalized
        or "session" in normalized
        or "task" in normalized
        or "run" in normalized
        or "event role" in normalized
        or "remap" in normalized
        or has_it
    ):
        return "preview_interpretation"
    if "預覽" in normalized and ("資料" in normalized or "標籤" in normalized):
        return "preview_interpretation"
    if _is_natural_interpretation_preview_request(normalized):
        return "preview_interpretation"
    if "驗證" in normalized and ("資料" in normalized or "標籤" in normalized):
        return "validate_interpretation"
    if "套用" in normalized and ("資料" in normalized or "標籤" in normalized):
        return "apply_interpretation"
    if _is_chinese_data_interpretation_request(normalized):
        return "scan_source"
    if _is_english_data_interpretation_request(normalized):
        return "scan_source"
    if (
        "interpret data source" in normalized
        or "interpret my eeg dataset" in normalized
        or ("scan" in normalized and "bids" in normalized)
        or "scan bids" in normalized
        or "scan /" in normalized
        or "scan a data source" in normalized
        or "scan data source" in normalized
        or "scan the bids dataset" in normalized
        or "scan the source" in normalized
        or (
            "scan" in normalized
            and any(
                marker in normalized
                for marker in ("data", "dataset", "source", "file", "folder", "eeg")
            )
        )
    ):
        return "scan_source"
    if "saliency" in normalized:
        return "saliency"
    if "顯著" in normalized or "可解釋" in normalized:
        return "saliency"
    if "evaluate" in normalized or "evaluation" in normalized:
        return "evaluate"
    if "評估" in normalized or "評價" in normalized:
        return "evaluate"
    if (
        "visualize" in normalized
        or "visualise" in normalized
        or "visualization" in normalized
        or "visualisation" in normalized
    ):
        return "visualize"
    if "視覺化" in normalized or "可視化" in normalized:
        return "visualize"
    if any(
        marker in normalized
        for marker in (
            "preprocess",
            "bandpass",
            "filter",
            "resample",
            "normalize",
            "normalise",
            "reference",
            "select channel",
        )
    ):
        return "preprocess"
    if any(
        marker in normalized
        for marker in (
            "前處理",
            "濾波",
            "帶通",
            "重採樣",
            "重新採樣",
            "正規化",
            "標準化",
            "參考電極",
            "選擇通道",
        )
    ):
        return "preprocess"
    if _is_dataset_generation_request(normalized):
        return "configure_dataset_split"
    if (
        "create epoch" in normalized
        or "epochs from" in normalized
        or "epoch creation" in normalized
        or "epoching" in normalized
    ):
        return "create_epoch"
    if "切 epoch" in normalized or "切epoch" in normalized or "切片段" in normalized:
        return "create_epoch"
    if _is_stop_training_request(normalized):
        return "stop_training"
    if _is_primary_train_with_conditional_fallback(normalized):
        return "train"
    if re.search(r"\btrain\b", normalized) or re.search(
        r"\b(?:start|run|begin)\s+(?:the\s+)?training\b",
        normalized,
    ):
        return "train"
    if extract_explicit_training_model(normalized) is not None:
        return "configure_training"
    if "configure training" in normalized or contains_explicit_training_options(
        normalized
    ):
        return "configure_training"
    if ("設定" in normalized or "配置" in normalized or "選擇" in normalized) and (
        "訓練" in normalized or "模型" in normalized
    ):
        return "configure_training"
    if "train it" in normalized or ("train" in normalized and "blocked" in normalized):
        return "train"
    if "train" in normalized or "training" in normalized:
        return "train"
    if "訓練" in normalized:
        return "train"
    if "model" in normalized and "use" in normalized:
        return "configure_training"
    return "unknown"


def _has_blocked_explanation_language(normalized: str) -> bool:
    has_blocked_signal = bool(
        re.search(
            r"\b(?:can(?:not|'t)|unable\s+to|blocked|not\s+ready|"
            r"unavailable|disabled)\b",
            normalized,
        )
        or any(
            marker in normalized
            for marker in (
                "不能",
                "無法",
                "不可以",
                "不可用",
                "被擋",
                "阻擋",
                "尚未開放",
                "還不能",
            )
        )
    )
    if not has_blocked_signal:
        return False

    has_explanation_cue = bool(
        re.search(r"\b(?:why|how\s+come)\b", normalized)
        or any(marker in normalized for marker in ("為什麼", "為何"))
    )
    if has_explanation_cue:
        return True

    # The assistant accepts both ASCII and CJK question punctuation.
    is_question = normalized.rstrip().endswith(("?", "？"))  # noqa: RUF001
    if not is_question:
        return False
    return bool(
        re.search(
            r"\b(?:can(?:not|'t)|unable\s+to|blocked|not\s+ready|"
            r"unavailable|disabled)\b",
            normalized,
        )
        or any(
            marker in normalized
            for marker in ("不能", "無法", "不可以", "不可用", "被擋", "還不能")
        )
    )


def _blocked_explanation_target_clause(normalized: str) -> str:
    english_subject = re.search(
        r"\bwhy\s+(?:is|are)\s+(.+?)\s+"
        r"(?:blocked|not\s+ready|unavailable|disabled)\b",
        normalized,
    )
    if english_subject is not None:
        clause = english_subject.group(1)
    else:
        english_action = re.search(
            r"\b(?:can(?:not|'t)|unable\s+to)\s+"
            r"(?:(?:i|we|the\s+app|xbrainlab)\s+)?(.+)",
            normalized,
        )
        clause = english_action.group(1) if english_action is not None else normalized

    chinese_action = re.search(
        r"為什麼(?:現在|目前)?\s*"
        r"(?:不能|無法|不可以|還不能)\s*(.+)",
        clause,
    )
    if chinese_action is not None:
        clause = chinese_action.group(1)
    else:
        chinese_subject = re.search(
            r"為什麼(?:現在|目前)?\s*(.+?)\s*"
            r"(?:不能|無法|不可以|不可用|被擋|阻擋|尚未開放|還不能)",
            clause,
        )
        if chinese_subject is not None:
            clause = chinese_subject.group(1)
        else:
            trailing_action = re.search(
                r"(?:不能|無法|不可以|還不能)\s*(.+)",
                clause,
            )
            if trailing_action is not None:
                clause = trailing_action.group(1)

    clause = re.split(
        r"\b(?:because|before|until|unless|without|after|if)\b|"
        r"(?:因為|之前|直到|除非|沒有|之後)",
        clause,
        maxsplit=1,
    )[0]
    return clause.strip(" \t\r\n.,!?;:\u3002\uff0c\uff01\uff1f\uff1b\uff1a")


def _is_knowledge_definition_clause(clause: str) -> bool:
    return bool(
        re.search(r"\bwhat\b.{0,40}\bmeans?\b", clause)
        or re.search(r"\b(?:remember|explain|define)\b", clause)
        or re.search(
            r"\b(?:useful|important|concept|theory|scientific(?:ally)?)\b",
            clause,
        )
        or re.search(
            r"\b(?:remove|prevent|detect|explain)\b.{0,16}\b(?:all|every)\b",
            clause,
        )
        or re.search(
            r"\b(?:alpha|beta|theta|delta|brain)\s+waves?\b.{0,30}"
            r"\bbe\s+visuali[sz]ed\b",
            clause,
        )
        or any(marker in clause for marker in ("什麼是", "是什麼", "解釋", "定義"))
    )


def _has_workflow_reference(normalized: str) -> bool:
    return bool(
        re.search(
            r"\b(?:xbrainlab|workflow|step|action|operation|readiness|"
            r"continue|proceed|next)\b",
            normalized,
        )
        or any(
            marker in normalized
            for marker in (
                "流程",
                "步驟",
                "操作",
                "功能",
                "目前",
                "現在",
                "繼續",
                "下一步",
            )
        )
    )


def _blocked_target_intents(clause: str) -> tuple[str, ...]:
    """Reuse the canonical intent parser for one or more explicit targets."""
    segments = re.split(r"\s+\b(?:or|and)\b\s+|(?:或|還是|、)", clause)
    targets: list[str] = []
    commands: set[CommandName] = set()
    for segment in segments:
        sanitized = re.sub(
            r"\b(?:why|can(?:not|'t)|unable\s+to|blocked|not\s+ready|"
            r"unavailable|disabled)\b",
            " ",
            segment,
        )
        for marker in ("不能", "無法", "不可以", "不可用", "被擋", "阻擋"):
            sanitized = sanitized.replace(marker, " ")
        normalized = " ".join(sanitized.split())
        if not normalized:
            continue

        intent = infer_user_intent(normalized)
        command = command_for_intent(intent)
        if command is None:
            continue
        if command is CommandName.QUERY_STATE and not (
            re.search(r"\b(?:state|status|readiness)\b", normalized)
            or any(marker in normalized for marker in ("狀態", "進度"))
        ):
            continue
        if command not in commands:
            targets.append(intent)
            commands.add(command)
    return tuple(targets)


def command_for_intent(intent: str) -> CommandName | None:
    """Return the backend command represented by an inferred intent."""
    return INTENT_TO_COMMAND.get(intent)


def path_label_for_intent(intent: str) -> str | None:
    """Return the user-facing path label implied by an intent."""
    if intent == "load_data":
        return "file path"
    if intent == "scan_source":
        return "source path"
    if intent == "reload_interpretation_recipe":
        return "recipe path"
    return None


def _is_explanatory_no_tool_request(normalized: str) -> bool:
    if _is_natural_interpretation_preview_request(normalized):
        return False
    explanatory_markers = (
        "why",
        "what is",
        "what are",
        "explain",
        "compare",
        "concept",
        "為什麼",
        "什麼是",
        "是什麼",
        "解釋",
        "比較",
        "我想了解",
        "請幫我了解",
        "了解",
        "概念",
    )
    asks_to_understand = bool(re.search(r"\bunderstand(?:ing)?\b", normalized))
    if not (
        any(marker in normalized for marker in explanatory_markers)
        or asks_to_understand
    ):
        return False
    return not any(
        marker in normalized
        for marker in (
            "workflow state",
            "current workflow",
            "目前狀態",
            "現在狀態",
        )
    )


def _is_reset_preprocess_request(normalized: str) -> bool:
    """Recognize a narrow preprocessing reset before generic session reset."""
    english_action = re.search(
        r"\b(?:reset|clear|discard|remove|undo|revert)\b",
        normalized,
    )
    english_target = re.search(
        r"\bpre[- ]?process(?:ing|ed)?\b",
        normalized,
    )
    chinese_action = any(
        action in normalized for action in ("重設", "重置", "清除", "還原")
    )
    chinese_target = "前處理" in normalized or "預處理" in normalized
    return bool(
        (english_action is not None and english_target is not None)
        or (chinese_action and chinese_target)
    )


def _is_stop_training_request(normalized: str) -> bool:
    """Recognize explicit training-stop language before generic training intent."""
    english_action = re.search(
        r"\b(?:stop|cancel|abort|terminate|interrupt)\b",
        normalized,
    )
    english_target = re.search(r"\btrain(?:ing)?\b", normalized)
    chinese_action = any(
        action in normalized for action in ("停止", "中止", "終止", "取消")
    )
    return bool(
        (english_action is not None and english_target is not None)
        or (chinese_action and "訓練" in normalized)
    )


def _is_workflow_state_request(normalized: str) -> bool:
    return any(
        marker in normalized
        for marker in (
            "workflow state",
            "current workflow",
            "current xbrainlab workflow",
            "what is ready",
            "what's ready",
            "which steps are ready",
            "what changed",
            "what dataset is loaded",
            "current dataset information",
            "dataset info",
            "dataset summary",
            "目前狀態",
            "現在狀態",
            "目前可以做什麼",
            "現在可以做什麼",
            "目前資料集",
            "現在資料集",
            "資料集資訊",
        )
    )


def _is_file_browse_request(normalized: str) -> bool:
    """Distinguish browsing a directory from importing a concrete source."""
    return bool(
        re.search(r"\b(?:list|show|browse)\b[^\n]{0,40}\bfiles?\b", normalized)
        or re.search(r"\bfiles?\b[^\n]{0,24}\b(?:in|under|from)\b", normalized)
        or any(marker in normalized for marker in ("列出檔案", "顯示檔案", "瀏覽檔案"))
    )


def _is_ambiguous_workflow_request(normalized: str) -> bool:
    if any(
        marker in normalized
        for marker in (
            "help me process the data",
            "handle this data",
            "do the eeg workflow",
            "幫我處理資料",
            "幫我弄資料",
            "把資料處理一下",
            "幫我貼標籤",
        )
    ):
        return True

    explicit_choice = bool(
        re.search(
            r"\beither\b.+\bor\b.+\b(?:ask|tell)\s+me\s+which\b",
            normalized,
        )
        or re.search(
            r"(?:或|還是).{0,32}(?:先)?問我.{0,8}(?:選|要)(?:哪|那)",
            normalized,
        )
    )
    if not explicit_choice:
        return False

    endpoint_concepts = sum(
        (
            bool(re.search(r"\bvisuali[sz]", normalized))
            or "視覺化" in normalized
            or "可視化" in normalized,
            "saliency" in normalized or "顯著圖" in normalized,
            bool(re.search(r"\bevaluat", normalized)) or "評估" in normalized,
            bool(re.search(r"\btrain(?:ing)?\b", normalized)) or "訓練" in normalized,
        )
    )
    return endpoint_concepts >= 2


def _is_primary_train_with_conditional_fallback(normalized: str) -> bool:
    """Keep an explicit train command primary over a conditional fallback."""
    fallback = re.search(r"(?:[;,]\s*)?\b(?:if|otherwise)\b", normalized)
    if fallback is None:
        return False
    primary_clause = normalized[: fallback.start()]
    return re.search(r"\btrain(?:\s+it|\s+the\s+model)?\b", primary_clause) is not None


def _is_chinese_data_interpretation_request(normalized: str) -> bool:
    if (
        "腦波" not in normalized
        and "eeg" not in normalized
        and "bci" not in normalized
        and "bids" not in normalized
    ):
        return False
    return any(
        marker in normalized
        for marker in (
            "讀",
            "載入",
            "匯入",
            "貼標籤",
            "標籤",
            "資料",
        )
    )


def _is_explicit_legacy_load_request(normalized: str) -> bool:
    """Return True only when the user explicitly asks for compatibility loading."""
    return (
        "load_data" in normalized
        or "legacy load" in normalized
        or "legacy compatibility" in normalized
        or "compatibility path" in normalized
        or "direct load" in normalized
    )


def _is_english_data_interpretation_request(normalized: str) -> bool:
    """Detect user-facing data-entry phrasing that should start scan_source."""
    has_source_locator = any(
        marker in normalized
        for marker in (
            "/",
            "\\",
            ".gdf",
            ".edf",
            ".bdf",
            ".set",
            ".vhdr",
            ".xdf",
            ".fif",
        )
    )
    if has_source_locator and re.search(
        r"\buse\b.{0,100}\b(?:eeg\s+recording|recording|dataset|source|file|folder)\b",
        normalized,
    ):
        return True

    data_entry_verbs = (
        r"\bload(?:ing)?\b",
        r"\bimport(?:ing)?\b",
        r"\bopen(?:ing)?\b",
        r"\bread(?:ing)?\b",
        r"\bfind(?:ing)?\b",
        r"\bselect(?:ing)?\b",
        r"\b(?:choose|chosen)\b",
        r"\binspect(?:ing)?\b",
    )
    if not any(re.search(pattern, normalized) for pattern in data_entry_verbs):
        return False
    data_entry_objects = (
        "data",
        "dataset",
        "source",
        "file",
        "folder",
        "eeg",
        "bci",
        "bids",
        ".gdf",
        ".edf",
        ".bdf",
        ".set",
        ".vhdr",
        ".xdf",
        "/",
        "\\",
    )
    return any(marker in normalized for marker in data_entry_objects)


def _is_reviewed_import_apply_request(normalized: str) -> bool:
    """Recognize applying an already-reviewed interpretation as import."""
    return bool(
        re.search(r"\bimport\b", normalized)
        and re.search(r"\breviewed\b", normalized)
        and re.search(r"\b(?:recording|data|dataset|source|file)\b", normalized)
    )


def _is_natural_interpretation_preview_request(normalized: str) -> bool:
    """Recognize user-facing review language without requiring backend terms."""
    return bool(
        re.search(r"\b(?:show|review)\b", normalized)
        and (
            "how xbrainlab understands" in normalized
            or "before it is imported" in normalized
            or "before importing" in normalized
        )
    )


def _is_dataset_generation_request(normalized: str) -> bool:
    """Keep dataset construction distinct from starting model training."""
    return bool(
        (
            "dataset" in normalized
            and re.search(
                r"\b(?:generate|generation|build|create|prepare|split)\b",
                normalized,
            )
        )
        or (
            "資料集" in normalized
            and any(
                marker in normalized
                for marker in ("建立", "產生", "生成", "切分", "分割")
            )
        )
    )
