"""Deterministic admission for explicit assistant workflow requests.

The local model is useful for language and parameter extraction, but it must not
decide whether an ApplicationService command is currently possible or invent a
required workflow decision.  This boundary reads one atomic application
publication and either permits generation, presents the backend blocker, or
hands the missing decision to the existing product UI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from XBrainLab.backend.application.commands import CommandName
from XBrainLab.backend.application.view_publication import (
    PUBLIC_VIEW_UNAVAILABLE_MESSAGE,
    ApplicationViewPublication,
)
from XBrainLab.backend.application.workflow_projection import (
    build_workflow_projection,
    decision_fields_for_command,
)
from XBrainLab.backend.training.input_contract import (
    REQUIRED_TRAINING_FIELDS,
)

from .intent import (
    command_for_intent,
    infer_user_intent,
)
from .training_request import (
    contains_explicit_training_options,
    extract_explicit_training_model,
    extract_explicit_training_options,
)
from .turn import AssistantTurnScope
from .turn_scope import workflow_command_is_within_endpoint


class UserRequestAdmissionAction(str, Enum):
    """Host action selected before optional RAG or model generation."""

    GENERATE = "generate"
    EXECUTE_READ_ONLY = "execute_read_only"
    BLOCKED = "blocked"
    UI_HANDOFF = "ui_handoff"


@dataclass(frozen=True, slots=True)
class UserRequestAdmission:
    """Typed result for one explicit user request."""

    action: UserRequestAdmissionAction
    command: CommandName | None = None
    message: str = ""
    decision_fields: tuple[str, ...] = ()
    suggested_values: tuple[tuple[str, str], ...] = ()

    @property
    def suggestions(self) -> dict[str, str]:
        """Return user-supplied values preserved for the existing UI surface."""
        return dict(self.suggested_values)


class UserRequestAdmissionPolicy:
    """Resolve workflow truth before asking the local model to choose a tool."""

    def evaluate(
        self,
        text: str,
        publication: ApplicationViewPublication | None,
        *,
        scope: AssistantTurnScope = AssistantTurnScope.SINGLE_ACTION,
        terminal_command: str | None = None,
    ) -> UserRequestAdmission:
        """Evaluate one request against one committed backend publication."""
        intent = infer_user_intent(text)
        command = command_for_intent(intent)
        if (
            scope is AssistantTurnScope.GUIDED_WORKFLOW
            and publication is not None
            and publication.usable
        ):
            projection = build_workflow_projection(
                publication.state,
                publication.effective_capabilities,
            )
            if (
                projection.recommended_command is not None
                and workflow_command_is_within_endpoint(
                    projection.recommended_command,
                    terminal_command,
                )
            ):
                command = CommandName(projection.recommended_command)
            elif terminal_command is not None:
                command = None
        if command is None:
            return UserRequestAdmission(UserRequestAdmissionAction.GENERATE)

        if publication is None or not publication.usable:
            return UserRequestAdmission(
                UserRequestAdmissionAction.BLOCKED,
                command=command,
                message=PUBLIC_VIEW_UNAVAILABLE_MESSAGE,
            )

        capabilities = publication.effective_capabilities
        try:
            capability = capabilities.get(command)
        except KeyError:
            return UserRequestAdmission(
                UserRequestAdmissionAction.BLOCKED,
                command=command,
                message="This workflow action is not available in the current app.",
            )

        if not capability.enabled:
            return UserRequestAdmission(
                UserRequestAdmissionAction.BLOCKED,
                command=command,
                message=self._reason_text(capability.reasons),
            )

        if command is CommandName.QUERY_STATE:
            return UserRequestAdmission(
                UserRequestAdmissionAction.EXECUTE_READ_ONLY,
                command=command,
            )

        decision_fields = self._missing_decision_fields(
            command,
            text,
            publication,
        )
        if decision_fields:
            return UserRequestAdmission(
                UserRequestAdmissionAction.UI_HANDOFF,
                command=command,
                message="Review the required choices in XBrainLab.",
                decision_fields=decision_fields,
                suggested_values=tuple(self._explicit_values(command, text).items()),
            )
        return UserRequestAdmission(
            UserRequestAdmissionAction.GENERATE,
            command=command,
        )

    @classmethod
    def _missing_decision_fields(
        cls,
        command: CommandName,
        text: str,
        publication: ApplicationViewPublication,
    ) -> tuple[str, ...]:
        # The requested command may differ from the projected next command;
        # decision ownership still remains in the backend workflow contract.
        fields = decision_fields_for_command(
            command,
            publication.state,
        )

        # A narrow model-selection request is complete on its own. It should
        # not be widened into the full Training Setting decision surface.
        if command is CommandName.CONFIGURE_TRAINING and cls._is_model_only(text):
            return ()

        return tuple(
            field
            for field in fields
            if not cls._field_is_explicit(field, text, publication)
        )

    @classmethod
    def _field_is_explicit(
        cls,
        field: str,
        text: str,
        publication: ApplicationViewPublication,
    ) -> bool:
        normalized = text.casefold()
        if field == "source_path":
            return bool(
                publication.state.interpretation.source_path
                or cls._contains_absolute_path(text)
            )
        if field in {"file_path", "recipe_path"}:
            return cls._contains_absolute_path(text)
        if field == "preprocess_settings":
            return bool(
                re.search(
                    r"\b(?:standard|default)\s+(?:preprocess(?:ing)?|pipeline)\b",
                    normalized,
                )
                or re.search(
                    r"\b(?:preprocess(?:ing)?|pipeline)\s+defaults?\b",
                    normalized,
                )
                or any(
                    phrase in normalized
                    for phrase in ("標準前處理", "預設前處理", "前處理預設值")
                )
            )
        if field == "target_event":
            return cls._target_event_value(text) is not None
        if field == "epoch_window":
            return cls._epoch_window_values(text) is not None
        if field == "split_strategy":
            return bool(
                re.search(
                    r"\b(?:trial|session|subject)(?:[- ]wise)?\b",
                    normalized,
                )
                or any(term in normalized for term in ("試次", "受試者", "工作階段"))
            )
        if field == "training_mode":
            return cls._training_mode_value(normalized) is not None
        if field == "model":
            return cls._model_value(text) is not None
        if field == "training_options":
            option_values = cls._training_option_values(text)
            return all(key in option_values for key in REQUIRED_TRAINING_FIELDS)
        return False

    @classmethod
    def _explicit_values(
        cls,
        command: CommandName,
        text: str,
    ) -> dict[str, str]:
        """Extract only values the user wrote; never synthesize workflow defaults."""
        values: dict[str, str] = {}
        normalized = text.casefold()

        if command is CommandName.CREATE_EPOCH:
            target_event = cls._target_event_value(text)
            if target_event is not None:
                values["target_event"] = target_event
            epoch_window = cls._epoch_window_values(text)
            if epoch_window is not None:
                values["t_min"], values["t_max"] = epoch_window

        if command is CommandName.GENERATE_DATASET:
            training_mode = cls._training_mode_value(normalized)
            if training_mode is not None:
                values["training_mode"] = training_mode

            split_strategy = cls._split_strategy_value(normalized)
            if split_strategy is not None:
                values["split_strategy"] = split_strategy
            test_ratio = cls._percentage_ratio(normalized, "test(?:ing)?")
            if test_ratio is not None:
                values["test_ratio"] = test_ratio
            validation_ratio = cls._percentage_ratio(
                normalized,
                "validation|validating|val",
            )
            if validation_ratio is not None:
                values["validation_ratio"] = validation_ratio

        if command is CommandName.CONFIGURE_TRAINING:
            model = cls._model_value(text)
            if model is not None:
                values["model"] = model
            values.update(cls._training_option_values(text))

        return values

    @staticmethod
    def _target_event_value(text: str) -> str | None:
        match = re.search(
            r"(?:\bevent(?:s)?\s+|事件\s*)([-\w.]+)",
            text.casefold(),
        )
        return match.group(1).rstrip(".,;:!?") if match is not None else None

    @staticmethod
    def _epoch_window_values(text: str) -> tuple[str, str] | None:
        match = re.search(
            r"(-?\d+(?:\.\d+)?)\s*(?:to|through|until|到|至|~)\s*"
            r"(-?\d+(?:\.\d+)?)",
            text.casefold(),
        )
        if match is None:
            return None
        return match.group(1), match.group(2)

    @staticmethod
    def _split_strategy_value(normalized: str) -> str | None:
        if re.search(r"\btrial(?:[- ]wise)?\b", normalized) or "試次" in normalized:
            return "trial"
        if (
            re.search(r"\bsession(?:[- ]wise)?\b", normalized)
            or "工作階段" in normalized
        ):
            return "session"
        if re.search(r"\bsubject(?:[- ]wise)?\b", normalized) or "受試者" in normalized:
            return "subject"
        return None

    @staticmethod
    def _training_mode_value(normalized: str) -> str | None:
        if "individual" in normalized or "個人" in normalized:
            return "individual"
        if re.search(r"\bgroup\b", normalized) or "群組" in normalized:
            return "group"
        if re.search(r"\bfull(?: data)?\b", normalized) or "完整資料" in normalized:
            return "full"
        return None

    @staticmethod
    def _percentage_ratio(normalized: str, label_pattern: str) -> str | None:
        patterns = (
            rf"(\d+(?:\.\d+)?)\s*%\s*(?:{label_pattern})",
            rf"(?:{label_pattern})[^\d%]{{0,16}}(\d+(?:\.\d+)?)\s*%",
        )
        for pattern in patterns:
            match = re.search(pattern, normalized)
            if match is not None:
                return format(float(match.group(1)) / 100.0, ".12g")
        return None

    @staticmethod
    def _contains_absolute_path(text: str) -> bool:
        return bool(
            re.search(
                r"(?<![:\w])(?:[A-Za-z]:[\\/][^\s,;`\"']+|/(?!/)[^\s,;`\"']+)",
                text,
            )
        )

    @staticmethod
    def _is_model_only(text: str) -> bool:
        normalized = text.casefold()
        return UserRequestAdmissionPolicy._model_value(
            text
        ) is not None and not UserRequestAdmissionPolicy._contains_training_options(
            normalized
        )

    @staticmethod
    def _model_value(text: str) -> str | None:
        return extract_explicit_training_model(text)

    @staticmethod
    def _training_option_values(text: str) -> dict[str, str]:
        return extract_explicit_training_options(text)

    @staticmethod
    def _contains_training_options(normalized: str) -> bool:
        return contains_explicit_training_options(normalized)

    @staticmethod
    def _reason_text(reasons: list[str]) -> str:
        cleaned = [
            " ".join(str(reason).split()) for reason in reasons if str(reason).strip()
        ]
        return " ".join(cleaned) or "This workflow action is not available yet."
