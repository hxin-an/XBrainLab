"""Deterministic product responses that must not depend on model generation."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, cast

from XBrainLab.backend.application import CommandName, get_application_service
from XBrainLab.backend.application.view_publication import ApplicationViewPublication
from XBrainLab.backend.application.workflow_projection import (
    build_workflow_projection,
)
from XBrainLab.llm.tools.result_contract import safe_unexpected_failure

from .intent import (
    infer_user_intent,
    is_unresolved_historical_action_reference,
    resolve_blocked_explanation_intent,
)
from .tool_feedback import clean_reason

if TYPE_CHECKING:
    from XBrainLab.backend.study import Study

logger = logging.getLogger(__name__)

_GREETING_COPY = (
    "Hello. I can help you move through the EEG workflow: import raw data, "
    "prepare preprocessing, create EEG epochs, build a training dataset, configure "
    "training, and explain why a step is blocked. To begin, choose EEG files or "
    "ask what is ready now."
)
_CLARIFICATION_COPY = (
    "Tell me which step you want to do next: import data, preview labels and "
    "metadata, preprocess, create EEG epochs, build a dataset, train, evaluate, or "
    "inspect saliency."
)
_BLOCKED_EXPLANATION_AMBIGUOUS_COPY = (
    "Which XBrainLab workflow step do you mean: import data, preprocess, "
    "create EEG epochs, build a dataset, configure training, train, evaluate, "
    "visualize, or inspect saliency?"
)
_HISTORICAL_REFERENCE_CLARIFICATION_COPY = (
    "I cannot safely tell which earlier option you mean. Name the workflow step "
    "you want, such as preprocess, create EEG epochs, build a dataset, train, "
    "evaluate, or inspect saliency."
)
_RESET_SESSION_UNAVAILABLE_COPY = (
    "Reset Session is not available from the interface or Assistant. "
    "Close and reopen XBrainLab to start over. No session state was changed."
)
_GREETINGS = frozenset({"hello", "hi", "hey", "嗨", "你好", "您好"})
_COMMAND_SUBJECTS: dict[CommandName, str] = {
    CommandName.SCAN_SOURCE: "Data import",
    CommandName.PREVIEW_INTERPRETATION: "Data interpretation preview",
    CommandName.VALIDATE_INTERPRETATION: "Data interpretation validation",
    CommandName.APPLY_INTERPRETATION: "Applying data interpretation",
    CommandName.SAVE_INTERPRETATION_RECIPE: "Saving the interpretation recipe",
    CommandName.RELOAD_INTERPRETATION_RECIPE: "Reloading the interpretation recipe",
    CommandName.LOAD_DATA: "Data import",
    CommandName.PREPROCESS: "Preprocessing",
    CommandName.RESET_PREPROCESS: "Resetting preprocessing",
    CommandName.CREATE_EPOCH: "EEG epoch creation",
    CommandName.CONFIGURE_DATASET_SPLIT: "Dataset generation",
    CommandName.CONFIGURE_TRAINING: "Training configuration",
    CommandName.TRAIN: "Training",
    CommandName.STOP_TRAINING: "Stopping training",
    CommandName.EVALUATE: "Evaluation",
    CommandName.VISUALIZE: "Visualization",
    CommandName.SALIENCY: "Saliency analysis",
    CommandName.QUERY_STATE: "Workflow state",
}


class ProductTurnKind(str, Enum):
    """Typed deterministic response selected before RAG or model generation."""

    GREETING = "greeting"
    CLARIFICATION = "clarification"
    WORKFLOW_READY = "workflow_ready"
    WORKFLOW_BLOCKED = "workflow_blocked"
    WORKFLOW_UNAVAILABLE = "workflow_unavailable"
    BLOCKED_EXPLANATION_AMBIGUOUS = "blocked_explanation_ambiguous"


@dataclass(frozen=True, slots=True)
class ProductTurnDecision:
    """One product response whose text is ready for controller publication."""

    kind: ProductTurnKind
    message: str
    contextual_command: CommandName | None = None


class ProductTurnPolicy:
    """Classify deterministic turns and publish backend-backed readiness copy."""

    def __init__(
        self,
        study: object,
        *,
        publication_reader: Callable[[], ApplicationViewPublication] | None = None,
    ) -> None:
        self._study = study
        self._publication_reader = publication_reader

    def evaluate(self, text: str) -> ProductTurnDecision | None:
        """Return a deterministic product response or defer to normal generation."""
        if self._is_greeting(text):
            return ProductTurnDecision(ProductTurnKind.GREETING, _GREETING_COPY)

        if is_unresolved_historical_action_reference(text):
            return ProductTurnDecision(
                ProductTurnKind.CLARIFICATION,
                _HISTORICAL_REFERENCE_CLARIFICATION_COPY,
            )

        if self._is_explicit_reset_session_request(text):
            return self._reset_session_unavailable_decision()

        blocked_explanation = resolve_blocked_explanation_intent(text)
        if blocked_explanation is not None:
            command = blocked_explanation.target_command
            if command is CommandName.RESET_SESSION:
                return self._reset_session_unavailable_decision()
            if command is None:
                return ProductTurnDecision(
                    ProductTurnKind.BLOCKED_EXPLANATION_AMBIGUOUS,
                    _BLOCKED_EXPLANATION_AMBIGUOUS_COPY,
                )
            return self._workflow_readiness_decision(command)

        intent = infer_user_intent(text)
        if intent == "reset_session":
            return self._reset_session_unavailable_decision()
        if intent == "ask_clarification":
            return ProductTurnDecision(
                ProductTurnKind.CLARIFICATION,
                _CLARIFICATION_COPY,
                contextual_command=self._clarification_command(),
            )
        return None

    @staticmethod
    def _reset_session_unavailable_decision() -> ProductTurnDecision:
        return ProductTurnDecision(
            ProductTurnKind.WORKFLOW_UNAVAILABLE,
            _RESET_SESSION_UNAVAILABLE_COPY,
        )

    @staticmethod
    def _is_explicit_reset_session_request(text: str) -> bool:
        normalized = text.strip().lower()
        if re.search(r"\b(?:preprocess|preprocessing)\b|前處理|預處理", normalized):
            return False
        return bool(
            re.search(
                r"\b(?:reset|clear|wipe|empty)\b.*\b"
                r"(?:session|workspace|dataset|data)\b",
                normalized,
            )
            or re.search(r"(?:重設|清空).*(?:工作階段|資料|數據)", normalized)
        )

    def _clarification_command(self) -> CommandName | None:
        """Return the current workflow surface without guessing from user text."""
        try:
            publication = self._read_publication()
            if not publication.usable or not publication.state.state_reliable:
                return None
            workflow = build_workflow_projection(
                publication.state,
                publication.effective_capabilities,
            )
            command_name = workflow.recommended_command or workflow.blocked_command
            return CommandName(command_name) if command_name else None
        except (KeyError, TypeError, ValueError):
            return None
        except Exception as exc:
            safe_unexpected_failure(
                logger,
                exc,
                boundary="product_turn_policy",
                operation="read_clarification_context",
            )
            return None

    @staticmethod
    def _is_greeting(text: str) -> bool:
        normalized = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE).strip().lower()
        return normalized in _GREETINGS

    def _workflow_readiness_decision(
        self,
        command: CommandName,
    ) -> ProductTurnDecision:
        try:
            publication = self._read_publication()
            if not publication.usable:
                return self._workflow_unavailable_decision(command)
            capability = publication.effective_capabilities.get(command)
        except Exception as exc:
            safe_unexpected_failure(
                logger,
                exc,
                boundary="product_turn_policy",
                operation=f"read_{command.value}_readiness",
            )
            return self._workflow_unavailable_decision(command)

        if not capability.enabled:
            if not capability.reasons:
                return self._workflow_unavailable_decision(command)
            reason = clean_reason("; ".join(capability.reasons))
            return ProductTurnDecision(
                ProductTurnKind.WORKFLOW_BLOCKED,
                f"{self._subject(command)} is not ready yet: {reason}",
            )
        confirmation = (
            " It still requires confirmation before execution."
            if capability.requires_confirmation or capability.confirmation_required
            else ""
        )
        return ProductTurnDecision(
            ProductTurnKind.WORKFLOW_READY,
            f"{self._subject(command)} is available in the current workflow."
            f"{confirmation}",
        )

    def _read_publication(self) -> ApplicationViewPublication:
        if self._publication_reader is not None:
            return self._publication_reader()
        study = cast("Study", self._study)
        return get_application_service(study).get_view_publication()

    @classmethod
    def _workflow_unavailable_decision(
        cls,
        command: CommandName,
    ) -> ProductTurnDecision:
        subject = cls._subject(command).lower()
        action_subject = "training" if command is CommandName.TRAIN else "workflow"
        return ProductTurnDecision(
            ProductTurnKind.WORKFLOW_UNAVAILABLE,
            f"I could not verify whether {subject} is ready because the "
            "application state is temporarily unavailable. "
            f"No {action_subject} action was started. Try again after the "
            "current operation finishes.",
        )

    @staticmethod
    def _subject(command: CommandName) -> str:
        if command in _COMMAND_SUBJECTS:
            return _COMMAND_SUBJECTS[command]
        return command.value.replace("_", " ").capitalize()
