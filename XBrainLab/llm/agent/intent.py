"""Language checks for suppressing action examples in RAG retrieval.

These checks filter example retrieval only; they do not select or authorize tools.
"""

from __future__ import annotations

import re


def should_suppress_action_examples(text: str) -> bool:
    """Keep explanatory or unresolved requests free of action examples."""
    normalized = text.lower()
    if _is_blocked_workflow_explanation(text):
        return True
    if is_unresolved_historical_action_reference(text):
        return True
    if _is_workflow_state_request(normalized):
        return False
    if _is_file_browse_request(normalized):
        return False
    if _is_explanatory_no_tool_request(normalized):
        return True
    return _is_ambiguous_workflow_request(normalized)


def _is_blocked_workflow_explanation(text: str) -> bool:
    normalized = text.casefold().replace("\u2019", "'")
    if not _has_blocked_explanation_language(normalized):
        return False
    target_clause = _blocked_explanation_target_clause(normalized)
    if _is_knowledge_definition_clause(target_clause):
        return False
    return _has_workflow_reference(normalized)


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
