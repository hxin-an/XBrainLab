#!/usr/bin/env python3
"""Run local-model tool-call evals against the deterministic case schema."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from scripts.agent.evals.run_tool_call_eval import (
    HOST_ASSISTED_DECISION_SCORE_SCOPE,
    METHOD_REFERENCES,
    RAW_MODEL_DECISION_SCORE_SCOPE,
    EvalCase,
    PredictedToolCall,
    Prediction,
    build_eval_cases,
    expected_decision_verification_result_for,
    expected_verification_result_for,
    infer_intent,
    make_state,
    render_markdown_report,
    score_case,
    summarize_scores,
)
from scripts.dev.inspect_local_assistant_runtime import classify_runtime
from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.view_publication import ApplicationViewPublication
from XBrainLab.backend.application.workflow_projection import (
    build_workflow_projection,
)
from XBrainLab.llm.agent.decision_contract import model_response_tool_contract
from XBrainLab.llm.agent.intent import (
    command_for_intent,
    infer_user_intent,
    path_label_for_intent,
)
from XBrainLab.llm.agent.parser import (
    CommandParser,
    ToolEnvelopeParseResult,
    ToolEnvelopeStatus,
)
from XBrainLab.llm.agent.prompt_policy import (
    DIRECT_ACTION_TOOL_NAMES,
    STRICT_TOOL_RESPONSE_PROMPT_POLICY,
    request_scoped_tool_names,
)
from XBrainLab.llm.agent.request_admission import (
    UserRequestAdmissionAction,
    UserRequestAdmissionPolicy,
)
from XBrainLab.llm.agent.strict_envelope_recovery import (
    DEFAULT_STRICT_ENVELOPE_RECOVERY_POLICY,
    StrictEnvelopeRecoveryDecision,
    StrictEnvelopeRecoveryMessage,
    StrictEnvelopeRecoveryPolicy,
    StrictEnvelopeRecoveryRequest,
)
from XBrainLab.llm.agent.tool_call_normalizer import normalize_tool_call
from XBrainLab.llm.agent.verifier import PlaceholderArgumentValidator, VerificationLayer
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import LLMEngine
from XBrainLab.llm.core.generation import GenerationProfile
from XBrainLab.llm.core.model_catalog import (
    available_disk_bytes,
    cache_usage_bytes,
    default_local_model_id,
    fallback_local_model_id,
    format_bytes,
    local_model_spec,
    model_cache_candidates,
)
from XBrainLab.llm.pipeline_state import STAGE_CONFIG, PipelineStage
from XBrainLab.llm.tools import get_all_tools
from XBrainLab.llm.tools.application_surface import READ_ONLY_TOOLS, TOOL_TO_COMMAND
from XBrainLab.llm.tools.schema_contract import (
    LEGACY_COMPATIBILITY_TOOLS,
    tool_contract_for_llm,
)


class TextGenerator(Protocol):
    """Callable interface used by tests and the real local model runner."""

    def __call__(self, messages: list[dict[str, str]]) -> str:
        """Return a model response for one prompt."""
        ...


class _EngineTextGenerator:
    """Callable local generator with explicit model/GPU ownership."""

    def __init__(self, config: LLMConfig) -> None:
        self._engine = LLMEngine(config)
        self._engine.load_model()
        self.constraint_report = configure_strict_generation_constraints(self._engine)

    def __call__(self, messages: list[dict[str, str]]) -> str:
        return "".join(
            self._engine.generate_stream(
                messages,
                profile=GenerationProfile.STRUCTURED_DECISION,
            )
        ).strip()

    def close(self) -> None:
        self._engine.close()


_STRICT_BLOCKED_GENERATION_PHRASES = (
    "`",
    "```",
    " ```",
    "/absolute/path",
    "/absolute",
    "/absolute/",
    "/path/to",
    "user_provided_path",
    "example_path",
)

_STRICT_CONTEXTUAL_PLACEHOLDER_PHRASES = frozenset(
    {
        "/absolute/path",
        "/absolute",
        "/absolute/",
        "/path/to",
        "user_provided_path",
        "example_path",
    }
)

_STRICT_PLACEHOLDER_CONTEXT_PREFIXES = ('"', " ", '": "')

_STRICT_DIRECT_REQUEST_TOOL_NOTE = (
    " Call this tool only when the latest user request directly asks for this "
    "exact operation. Do not call it as a prerequisite or substitute for a "
    "different requested operation."
)

_TOOL_MATCH_NOTES = {
    "list_files": (
        " Use only for an explicit request to list, browse, or discover directory "
        "contents. Do not use a file path as the directory for a load/import request."
    ),
    "scan_source": (
        " Use for a load/import request that provides an EEG file, folder, BIDS root, "
        "or recipe path, including a request to continue that import workflow."
    ),
}


def configure_strict_generation_constraints(engine: Any) -> dict[str, Any]:
    """Apply supported raw-generation constraints without rewriting output.

    The current Hugging Face backend does not expose JSON-schema constrained
    decoding. It does expose ``bad_words_ids``, so the eval runner prevents
    Markdown fences and known placeholder values at generation time. Contextual
    variants are encoded because tokenizers may merge a JSON quote or leading
    space with the first placeholder token. This leaves the model's JSON or
    prose untouched and falls back to one bounded recovery when unavailable.
    """
    fallback = {
        "mode": "bounded_recovery_only",
        "raw_output_postprocessed": False,
        "blocked_token_ids": [],
        "blocked_phrases": [],
    }
    backend = getattr(engine, "active_backend", None)
    tokenizer = getattr(backend, "tokenizer", None)
    model = getattr(backend, "model", None)
    generation_config = getattr(model, "generation_config", None)
    encode = getattr(tokenizer, "encode", None)
    if generation_config is None or not callable(encode):
        return fallback

    blocked_sequences: list[list[int]] = []
    canonical_sequences: list[list[int]] = []
    blocked_phrases: list[str] = []
    for text in _STRICT_BLOCKED_GENERATION_PHRASES:
        variants = [text]
        if text in _STRICT_CONTEXTUAL_PLACEHOLDER_PHRASES:
            variants.extend(
                f"{prefix}{text}" for prefix in _STRICT_PLACEHOLDER_CONTEXT_PREFIXES
            )
        encoded_variants: list[list[int]] = []
        for variant in variants:
            try:
                token_ids = encode(variant, add_special_tokens=False)
            except (KeyError, TypeError, ValueError):
                continue
            if not isinstance(token_ids, (list, tuple)) or not token_ids:
                continue
            encoded_variants.append([int(token_id) for token_id in token_ids])
        if not encoded_variants:
            continue
        canonical_sequences.append(encoded_variants[0])
        blocked_sequences.extend(encoded_variants)
        blocked_phrases.append(text)
    if not blocked_sequences:
        return fallback

    existing = [list(item) for item in (generation_config.bad_words_ids or [])]
    merged = list(existing)
    for sequence in blocked_sequences:
        if sequence not in merged:
            merged.append(sequence)
    generation_config.bad_words_ids = merged
    return {
        "mode": "hf_lexical_constraint",
        "raw_output_postprocessed": False,
        "blocked_token_ids": sorted(
            sequence[0] for sequence in canonical_sequences if len(sequence) == 1
        ),
        "blocked_phrases": blocked_phrases,
    }


@dataclass(frozen=True)
class _StrictEnvelopeAttempt:
    """One unmodified local-model output and its strict host decision."""

    attempt_index: int
    raw_output: str
    envelope: ToolEnvelopeParseResult
    latency_seconds: float
    generation_error: str | None
    decision: StrictEnvelopeRecoveryDecision | None


@dataclass(frozen=True)
class _StrictEnvelopeGeneration:
    """Complete bounded generation trajectory for one benchmark repeat."""

    raw_output: str
    envelope: ToolEnvelopeParseResult
    generation_error: str | None
    recovery_taxonomy: str
    attempts: tuple[_StrictEnvelopeAttempt, ...]


TOOL_INTENTS: dict[str, str] = {
    "scan_source": "scan_source",
    "preview_interpretation": "preview_interpretation",
    "validate_interpretation": "validate_interpretation",
    "apply_interpretation": "apply_interpretation",
    "save_interpretation_recipe": "save_interpretation_recipe",
    "reload_interpretation_recipe": "reload_interpretation_recipe",
    "load_data": "load_data",
    "apply_standard_preprocess": "preprocess",
    "apply_bandpass_filter": "preprocess",
    "epoch_data": "create_epoch",
    "configure_dataset_split": "configure_dataset_split",
    "set_model": "configure_training",
    "configure_training": "configure_training",
    "start_training": "train",
    "clear_dataset": "reset_session",
    "query_state": "query_state",
    "get_dataset_info": "query_state",
    "visualize": "visualize",
    "saliency": "saliency",
}

VRAM_PRESSURE_FREE_MIB = 2048
VRAM_PRESSURE_USED_RATIO = 0.90
FULL_LOCAL_GATE_REPEAT_COUNT = 3
RELEASE_LOCAL_EVAL_GATES = {"release", "thesis"}
LOCAL_EVAL_SCHEMA_VERSION = "xbrainlab.local_tool_call_eval.v5"
ENGINEERING_BASELINE_MIN_CASES = 50
THESIS_CANDIDATE_MIN_CASES = 100
MIN_NEGATIVE_BLOCKED_RECOVERY_RATIO = 0.30
STRICT_GATE_FAILURE_EXIT_CODE = 1
RESOURCE_PREFLIGHT_FAILURE_EXIT_CODE = 2

PHI4_DECISION_DEVELOPMENT_CASE_IDS = (
    "empty-train-block",
    "empty-load-path",
    "empty-load-missing-path",
    "multi-turn-load-recovery",
    "loaded-preprocess",
    "empty-preprocess-block",
    "preprocessed-create-epoch",
    "loaded-create-epoch-block",
    "epoched-generate-dataset",
    "loaded-generate-dataset-block",
    "dataset-train-missing-config",
    "dataset-set-model",
)
PHI4_DECISION_HELD_OUT_CASE_IDS = (
    "workflow-continue-empty-scan",
    "empty-preprocess-block-paraphrase",
    "loaded-create-epoch-block-paraphrase",
    "workflow-continue-loaded-epoch-block",
    "epoched-generate-dataset-missing-strategy",
    "loaded-generate-dataset-block-paraphrase",
    "dataset-train-missing-config-paraphrase",
)
PHI4_DECISION_CASE_SUITES = {
    "development": PHI4_DECISION_DEVELOPMENT_CASE_IDS,
    "held-out": PHI4_DECISION_HELD_OUT_CASE_IDS,
}


@dataclass(frozen=True)
class PromptConditionSpec:
    """Reproducible description of the information exposed to the model."""

    schema_version: str
    name: str
    description: str
    primary_raw_accuracy: bool
    evaluator_answer_fields_included: bool
    host_intent_included: bool
    case_specific_blocked_reason_included: bool
    host_normalization_hints_included: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


PRIMARY_PROMPT_CONDITION = PromptConditionSpec(
    schema_version="xbrainlab.local_tool_call_prompt_condition.v11",
    name="state_capability_unassisted",
    description=(
        "User conversation plus compact backend workflow state, a state-derived "
        "complete state-derived action policy, enabled tool contracts, and a "
        "model-owned structured decision envelope; no evaluator-derived answer "
        "or host intent hint."
    ),
    primary_raw_accuracy=True,
    evaluator_answer_fields_included=False,
    host_intent_included=False,
    case_specific_blocked_reason_included=False,
    host_normalization_hints_included=False,
)


def build_prompt_messages(
    case: EvalCase,
    *,
    prompt_condition: PromptConditionSpec = PRIMARY_PROMPT_CONDITION,
) -> list[dict[str, str]]:
    """Build the primary answer-leakage-free prompt for one eval case.

    Only user-authored turns, compact backend state, and capability-filtered tool
    contracts enter this prompt. Expected intent, expected calls, expected
    blocked reasons, evaluator intent inference, and host normalization advice
    are scoring-side information and must never enter the primary condition.
    """
    if prompt_condition != PRIMARY_PROMPT_CONDITION:
        raise ValueError(
            "Only the primary state-capability prompt condition is supported by "
            "this runner. Assisted prompt conditions require a separate runner."
        )
    earlier_turns = list(case.user_turns[:-1])
    latest_turn = case.user_turns[-1] if case.user_turns else ""
    available_tools = _available_tool_schemas(case.state_name)
    state_snapshot = _primary_prompt_state_snapshot(case.state_name)
    decision_context = _primary_prompt_decision_context(
        case,
        available_tools=available_tools,
    )
    system = (
        "You are the XBrainLab local assistant tool-call planner. "
        "Make one model-owned decision for the latest user request. Backend state, "
        "backend blocking reasons, and enabled tool contracts are authoritative. "
        "Never call an unlisted name and do not call a different tool as a "
        "prerequisite or substitute. Never invent placeholder paths, recipe paths, "
        "split choices, model settings, IDs, labels, or file names. Data "
        "Interpretation is the primary data entry workflow; legacy direct-load and "
        "label-attach paths are not enabled for new imports. If the latest user "
        "turn contains an explicit absolute path in a load/import request, it "
        "belongs to scan_source; list_files is only for an "
        "explicit browse/list request. Earlier turns are context, not permission to "
        "repeat an old action. Request categories in action_policy are semantic "
        "labels, never callable tool names. A blocked category requires "
        "respond_to_user.blocked; an enabled category permits only its listed exact "
        "callable names. No host answer or expected result is present.\n\n"
        f"{STRICT_TOOL_RESPONSE_PROMPT_POLICY.decision_instructions()}"
    )
    user = (
        "Workflow state:\n"
        f"{json.dumps(state_snapshot, ensure_ascii=False, sort_keys=True)}\n\n"
        "Backend workflow decision context (state-derived advice, not user "
        "intent):\n"
        f"{json.dumps(decision_context, ensure_ascii=False, sort_keys=True)}\n\n"
        "Enabled tool contracts:\n"
        f"{json.dumps(available_tools, ensure_ascii=False, sort_keys=True)}\n\n"
        "Earlier user-authored turns (context only):\n"
        f"{json.dumps(earlier_turns, ensure_ascii=False)}\n\n"
        "Latest user-authored request (authoritative):\n"
        f"{json.dumps(latest_turn, ensure_ascii=False)}\n\n"
        "Apply the decision order now. Match the exact request to one semantic "
        "request_category in action_policy. For status blocked, use "
        "respond_to_user.blocked and call no action tool. "
        "For status enabled, use only a listed callable_tool_name when all schema "
        "required values are present; otherwise use missing_input. Return one "
        "decision envelope only."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _primary_prompt_state_snapshot(state_name: str) -> dict[str, Any]:
    """Return compact product state without evaluator labels or expected answers."""
    state = make_state(state_name)
    return {
        "pipeline_stage": state.pipeline_stage,
        "raw": {"loaded": state.raw.loaded, "count": state.raw.count},
        "preprocessed": {
            "available": state.preprocessed.available,
            "count": state.preprocessed.count,
        },
        "epoch": {"available": state.epoch.available},
        "dataset": {
            "available": state.dataset.available,
            "count": state.dataset.count,
        },
        "training": {
            "has_model": state.training.has_model,
            "has_training_option": state.training.has_training_option,
            "has_trainer": state.training.has_trainer,
            "is_running": state.training.is_running,
        },
        "interpretation": {
            "has_scan_result": state.interpretation.has_scan_result,
            "has_preview": state.interpretation.has_preview,
            "has_validation_decision": (state.interpretation.has_validation_decision),
            "has_applied_interpretation": (
                state.interpretation.has_applied_interpretation
            ),
            "has_recipe": state.interpretation.has_recipe,
            "pending_confirmation": state.interpretation.pending_confirmation,
        },
        "state_reliable": state.state_reliable,
    }


def _primary_prompt_decision_context(
    case: EvalCase,
    *,
    available_tools: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return state-only workflow advice without inferring the user intent."""
    state = make_state(case.state_name)
    policy = build_capability_policy(state)
    projection = build_workflow_projection(state, policy)
    recommended = projection.recommended_command
    can_auto_continue = False
    if recommended is not None:
        capability = policy.get(recommended)
        can_auto_continue = bool(
            case.workflow_mode == "continue_until_decision"
            and capability.enabled
            and capability.can_auto_execute
            and not capability.requires_confirmation
            and not capability.confirmation_required
            and not capability.stop_after_success
            and not projection.decision_fields
        )
    published_tool_names = {
        str(tool.get("name", "")).strip()
        for tool in available_tools
        if str(tool.get("name", "")).strip()
    }
    action_policy: list[dict[str, Any]] = []
    for action, possible_tool_names in sorted(DIRECT_ACTION_TOOL_NAMES.items()):
        callable_names = sorted(published_tool_names.intersection(possible_tool_names))
        if callable_names:
            action_policy.append(
                {
                    "request_category": action.replace("_", " "),
                    "status": "enabled",
                    "callable_tool_names": callable_names,
                }
            )
            continue
        command = command_for_intent(action)
        if command is None:
            continue
        capability = policy.get(command)
        reasons = [
            str(reason).strip() for reason in capability.reasons if str(reason).strip()
        ]
        if reasons:
            action_policy.append(
                {
                    "request_category": action.replace("_", " "),
                    "status": "blocked",
                    "response_decision": "blocked",
                    "backend_reasons": reasons,
                }
            )
    continuation: dict[str, Any] | None = None
    if case.workflow_mode == "continue_until_decision":
        callable_names = sorted(
            published_tool_names.intersection(
                DIRECT_ACTION_TOOL_NAMES.get(str(recommended or ""), frozenset())
            )
        )
        continuation = {
            "allowed": bool(can_auto_continue and callable_names),
            "callable_tool_names": callable_names if can_auto_continue else [],
        }
    return {
        "workflow_mode": case.workflow_mode,
        "broad_continuation": continuation,
        "state_evidence": list(projection.evidence),
        "action_policy": action_policy,
    }


def score_local_case(case: EvalCase, raw_outputs: list[str]):
    """Score unmodified model decisions before host normalization or blocking."""
    predictions = [
        raw_prediction_from_model_output(case, raw_output) for raw_output in raw_outputs
    ]
    return score_case(
        case,
        predictions,
        score_scope=RAW_MODEL_DECISION_SCORE_SCOPE,
    )


def score_host_assisted_local_case(case: EvalCase, raw_outputs: list[str]):
    """Score the product host's normalized and safely blocked interpretation."""
    admission_prediction = _host_admission_prediction(case)
    predictions = [
        admission_prediction
        or _apply_product_prompt_publication_gate(
            case,
            prediction_from_model_output(case, raw_output),
        )
        for raw_output in raw_outputs
    ]
    return score_case(
        case,
        predictions,
        score_scope=HOST_ASSISTED_DECISION_SCORE_SCOPE,
    )


def _apply_product_prompt_publication_gate(
    case: EvalCase,
    prediction: Prediction,
) -> Prediction:
    """Represent the product's request-scoped publication safety boundary."""
    if not prediction.tool_calls or not case.user_turns:
        return prediction
    available = {
        str(tool.get("name", "")).strip()
        for tool in _available_tool_schemas(case.state_name)
        if str(tool.get("name", "")).strip()
    }
    latest_user_text = case.user_turns[-1]
    intent = infer_user_intent(latest_user_text)
    command = command_for_intent(intent)
    published = request_scoped_tool_names(
        available,
        intent=intent,
        authorized_command=(command.value if command is not None else None),
    )
    rejected = [
        call.tool_name
        for call in prediction.tool_calls
        if call.tool_name not in published
    ]
    if not rejected:
        return prediction
    message = (
        "The proposed assistant action was not published for this request, so "
        "XBrainLab stopped it without executing the tool."
    )
    return Prediction(
        intent=_inferred_case_intent(case),
        tool_calls=[],
        blocked=True,
        blocked_reason=message,
        final_message=message,
    )


def _host_admission_prediction(case: EvalCase) -> Prediction | None:
    """Return the product decision made before optional local-model generation."""
    if not case.user_turns:
        return None
    state = make_state(case.state_name)
    publication = ApplicationViewPublication(
        generation=1,
        state=state,
        capabilities=build_capability_policy(state),
    )
    admission = UserRequestAdmissionPolicy().evaluate(
        case.user_turns[-1],
        publication,
    )
    if admission.action is UserRequestAdmissionAction.GENERATE:
        return None

    requested_intent = _inferred_case_intent(case)
    if admission.action is UserRequestAdmissionAction.BLOCKED:
        return Prediction(
            intent=requested_intent,
            tool_calls=[],
            blocked=True,
            response_decision="blocked",
            blocked_reason=admission.message,
            final_message=admission.message,
        )

    field_text = ", ".join(
        field.replace("_", " ") for field in admission.decision_fields
    )
    message = (
        f"Required {field_text} is missing. Review the choices in XBrainLab."
        if field_text
        else admission.message
    )
    return Prediction(
        intent=requested_intent,
        tool_calls=[],
        blocked=True,
        ui_handoff=True,
        response_decision="missing_input",
        missing_inputs=tuple(admission.decision_fields),
        blocked_reason=message,
        final_message=message,
    )


def raw_prediction_from_model_output(case: EvalCase, raw_output: str) -> Prediction:
    """Preserve the model's structured decision and intent for honest scoring.

    This layer never normalizes aliases, fills arguments, removes blocked calls,
    injects benchmark outcomes, or replaces model prose with backend policy text.
    Host verification and capability blocking are scored in the assisted scope.
    """
    envelope = CommandParser.parse_product(raw_output)
    if envelope.status is ToolEnvelopeStatus.FORMAT_ERROR:
        return Prediction(
            intent="unknown",
            tool_calls=[],
            format_valid=False,
            format_error=envelope.error,
        )
    if envelope.status is ToolEnvelopeStatus.NO_TOOL:
        return _raw_no_tool_prediction(raw_output, envelope=envelope)

    name, params = envelope.commands[0]
    tool_calls = [PredictedToolCall(tool_name=name, arguments=dict(params))]
    intent = envelope.intent or TOOL_INTENTS.get(name, "unknown")
    return Prediction(
        intent=intent,
        tool_calls=tool_calls,
    )


def _raw_no_tool_prediction(
    raw_output: str,
    *,
    envelope: ToolEnvelopeParseResult,
) -> Prediction:
    """Classify response mode without assigning a host-inferred user intent."""
    text = envelope.message or raw_output.strip()
    if envelope.decision is not None:
        asks_clarification = envelope.decision == "missing_input"
        blocked = envelope.decision in {"blocked", "missing_input"}
        return Prediction(
            intent=envelope.intent,
            tool_calls=[],
            blocked=blocked,
            asks_clarification=asks_clarification,
            response_decision=envelope.decision,
            missing_inputs=envelope.missing_inputs,
            blocked_reason=text if blocked else "",
            final_message=text,
        )

    lower = text.lower()
    asks_clarification = any(
        marker in lower
        for marker in (
            "could you",
            "please specify",
            "provide",
            "missing",
            "which",
            "confirm",
            "提供",
            "缺少",
            "哪個",
            "確認",
        )
    ) or ("need" in lower and "path" in lower)
    blocked = asks_clarification or any(
        marker in lower
        for marker in ("blocked", "cannot", "can't", "not available", "unavailable")
    )
    blocked = blocked or ("before" in lower and not asks_clarification)
    return Prediction(
        intent="no_tool",
        tool_calls=[],
        blocked=blocked,
        asks_clarification=asks_clarification,
        response_decision=None,
        blocked_reason=text if blocked else "",
        final_message=text,
    )


def prediction_from_model_output(case: EvalCase, raw_output: str) -> Prediction:
    """Convert one raw local-model response into the shared scorer prediction."""
    envelope = CommandParser.parse_product(raw_output)
    requested_intent = _inferred_case_intent(case)
    if envelope.status is ToolEnvelopeStatus.FORMAT_ERROR:
        return Prediction(
            intent=requested_intent,
            tool_calls=[],
            format_valid=False,
            format_error=envelope.error,
        )
    parsed = list(envelope.commands)
    tool_calls = _prediction_tool_calls(case, parsed)
    if not tool_calls:
        text = envelope.message or raw_output.strip()
        lower = text.lower()
        if envelope.decision is not None:
            asks_clarification = envelope.decision == "missing_input"
            blocked = envelope.decision in {"blocked", "missing_input"}
            return Prediction(
                intent=requested_intent,
                tool_calls=[],
                blocked=blocked,
                asks_clarification=asks_clarification,
                response_decision=envelope.decision,
                missing_inputs=envelope.missing_inputs,
                blocked_reason=text if blocked else "",
                final_message=text,
            )
        if requested_intent == "no_tool":
            return Prediction(
                intent=requested_intent,
                tool_calls=[],
                response_decision="answer",
                final_message=text,
            )
        if requested_intent == "ask_clarification":
            asks_clarification = any(
                marker in lower
                for marker in (
                    "could you",
                    "please specify",
                    "specify",
                    "which",
                    "what",
                    "how",
                    "哪個",
                    "請",
                    "提供",
                )
            )
            if asks_clarification:
                message = "Please tell me which workflow step or input you want to use."
                return Prediction(
                    intent=requested_intent,
                    tool_calls=[],
                    blocked=True,
                    asks_clarification=True,
                    blocked_reason=message,
                    final_message=message,
                )
        blocked_intent_reason = _blocked_requested_intent_reason(
            case.state_name,
            requested_intent,
        )
        has_blocked_marker = any(
            marker in lower
            for marker in (
                "blocked",
                "cannot",
                "can't",
                "not available",
                "unavailable",
            )
        )
        if blocked_intent_reason and has_blocked_marker:
            return Prediction(
                intent=requested_intent,
                tool_calls=[],
                blocked=True,
                blocked_reason=blocked_intent_reason,
                final_message=blocked_intent_reason,
            )
        if blocked_intent_reason and _mentions_policy_reason(
            text,
            blocked_intent_reason,
        ):
            return Prediction(
                intent=requested_intent,
                tool_calls=[],
                blocked=True,
                blocked_reason=blocked_intent_reason,
                final_message=blocked_intent_reason,
            )
        asks_clarification = any(
            marker in lower
            for marker in (
                "provide",
                "missing",
                "which",
                "confirm",
                "提供",
                "缺少",
                "哪個",
                "確認",
            )
        ) or ("need" in lower and "path" in lower)
        blocked = any(
            marker in lower
            for marker in (
                "blocked",
                "cannot",
                "can't",
                "not available",
                "unavailable",
            )
        ) or ("before" in lower and not asks_clarification)
        blocked = blocked or asks_clarification
        return Prediction(
            intent=requested_intent,
            tool_calls=[],
            blocked=blocked,
            asks_clarification=asks_clarification,
            blocked_reason=text if blocked else "",
            final_message=text,
        )

    first_tool = tool_calls[0].tool_name
    first_params = tool_calls[0].arguments
    blocked_intent_reason = _blocked_requested_intent_reason(
        case.state_name,
        requested_intent,
    )
    if blocked_intent_reason:
        if TOOL_INTENTS.get(first_tool) == requested_intent:
            tool_calls = []
        return Prediction(
            intent=requested_intent,
            tool_calls=tool_calls,
            blocked=True,
            blocked_reason=blocked_intent_reason,
            final_message=blocked_intent_reason,
        )

    validation = _prediction_verifier().verify_tool_call((first_tool, first_params))
    if not validation.is_valid:
        message = validation.error_message or "Tool call did not pass verification."
        message = _intent_adjusted_verification_message(requested_intent, message)
        lower = message.lower()
        asks_clarification = any(
            marker in lower
            for marker in (
                "actual path",
                "absolute path",
                "missing required parameter",
                "required input",
                "is missing",
            )
        )
        return Prediction(
            intent=requested_intent,
            tool_calls=[],
            blocked=True,
            asks_clarification=asks_clarification,
            response_decision=("missing_input" if asks_clarification else "blocked"),
            missing_inputs=(
                _verification_missing_input_fields(
                    first_tool,
                    first_params,
                    message,
                )
                if asks_clarification
                else ()
            ),
            blocked_reason=message,
            final_message=message,
        )

    intent = TOOL_INTENTS.get(first_tool, "unknown")
    blocked_reason = _blocked_reason_for_tool(case.state_name, first_tool)
    confirmation_required = _confirmation_required_for_tool(case.state_name, first_tool)
    return Prediction(
        intent=intent,
        tool_calls=tool_calls,
        blocked=bool(blocked_reason),
        confirmation_required=confirmation_required,
        blocked_reason=blocked_reason,
        final_message="",
    )


def run_local_eval(
    *,
    model_id: str,
    repeat_count: int,
    case_ids: list[str] | None = None,
    case_limit: int | None = None,
    max_new_tokens: int = 160,
    generator: TextGenerator | None = None,
    resource_preflight: dict[str, Any] | None = None,
    prompt_condition: PromptConditionSpec = PRIMARY_PROMPT_CONDITION,
) -> dict[str, Any]:
    """Run local-model evals and return a JSON-friendly report."""
    cases = _select_cases(build_eval_cases(), case_ids=case_ids, case_limit=case_limit)
    config = LLMConfig.load_from_file() or LLMConfig()
    config.apply_runtime_selection("local", model_id=model_id, ui_active_mode="local")
    config.max_new_tokens = max_new_tokens
    config.do_sample = False
    runtime = _artifact_runtime(classify_runtime(config))

    owns_generator = generator is None
    local_generator = generator or _build_engine_generator(config)
    generation_constraints = _generation_constraint_report(local_generator)
    try:
        case_runs, raw_scores, host_assisted_scores = _evaluate_local_cases(
            cases=cases,
            repeat_count=repeat_count,
            generator=local_generator,
            prompt_condition=prompt_condition,
        )
    finally:
        if owns_generator:
            close = getattr(local_generator, "close", None)
            if callable(close):
                close()

    raw_model_summary = summarize_scores(raw_scores)
    host_assisted_summary = summarize_scores(host_assisted_scores)
    generated_at = datetime.now(UTC).isoformat()
    prompt_condition_payload = prompt_condition.to_dict()
    evidence_status = _evidence_status(
        cases=cases,
        repeat_count=repeat_count,
        prompt_condition=prompt_condition,
    )
    benchmark_coverage = _benchmark_coverage(cases)
    return {
        "schema_version": LOCAL_EVAL_SCHEMA_VERSION,
        "benchmark": "xbrainlab-local-tool-call",
        "runner": "local-llm",
        "prompt_condition": prompt_condition_payload,
        "evidence_status": evidence_status,
        "benchmark_coverage": benchmark_coverage,
        "measurement_contract": {
            "raw_model_score_scope": RAW_MODEL_DECISION_SCORE_SCOPE,
            "host_assisted_score_scope": HOST_ASSISTED_DECISION_SCORE_SCOPE,
            "dimension_groups": raw_model_summary["dimension_groups"],
            "backend_execution_observed": False,
            "backend_outcome_dimensions_measured": False,
            "host_intent_filtering_used": False,
            "metric_denominators": {
                "tool_selection": "cases expecting a direct tool call",
                "argument_correctness": (
                    "cases where the expected direct tool was selected"
                ),
                "tool_or_no_tool_decision": "all cases",
                "missing_input_fields": "cases expecting missing_input",
            },
            "host_owned_dimensions": [
                "verification_result",
                "runtime_safety",
                "confirmation_boundary",
            ],
        },
        "generated_at": generated_at,
        "model_id": model_id,
        "repeat_count": repeat_count,
        "exploratory": not evidence_status["engineering_baseline_protocol_complete"],
        "runtime": runtime,
        "generation_constraints": generation_constraints,
        "resource_preflight": resource_preflight or {},
        "method_references": METHOD_REFERENCES,
        "case_source_path": str(Path(__file__).with_name("run_tool_call_eval.py")),
        "fixture_source_paths": [
            str(Path(__file__).with_name("run_tool_call_eval.py")),
            str(Path(__file__)),
        ],
        "provenance": _build_eval_provenance(
            cases=cases,
            config=config,
            model_id=model_id,
            repeat_count=repeat_count,
            max_new_tokens=max_new_tokens,
            prompt_condition=prompt_condition,
            generation_constraints=generation_constraints,
        ),
        "total_cases": len(cases),
        # The top-level summary is intentionally the unassisted model score.
        # Product normalization and backend safety remain visible separately.
        "summary": raw_model_summary,
        "raw_model_summary": raw_model_summary,
        "host_assisted_summary": host_assisted_summary,
        "failure_taxonomy": _failure_taxonomy(raw_scores),
        "host_assisted_failure_taxonomy": _failure_taxonomy(
            host_assisted_scores,
        ),
        "recovery_taxonomy": _recovery_taxonomy(case_runs),
        "cases": case_runs,
    }


def _evaluate_local_cases(
    *,
    cases: list[EvalCase],
    repeat_count: int,
    generator: TextGenerator,
    recovery_policy: StrictEnvelopeRecoveryPolicy = (
        DEFAULT_STRICT_ENVELOPE_RECOVERY_POLICY
    ),
    prompt_condition: PromptConditionSpec = PRIMARY_PROMPT_CONDITION,
) -> tuple[list[dict[str, Any]], list[Any], list[Any]]:
    """Evaluate selected cases while the caller owns generator lifetime."""
    schema_verifier = _prediction_verifier()
    case_runs: list[dict[str, Any]] = []
    raw_scores = []
    host_assisted_scores = []
    for case in cases:
        runs: list[dict[str, Any]] = []
        raw_predictions: list[Prediction] = []
        host_assisted_predictions: list[Prediction] = []
        generation_errors: list[str] = []
        host_generation_errors: list[str] = []
        admission_prediction = _host_admission_prediction(case)
        host_admission_action = (
            "ui_handoff"
            if admission_prediction is not None and admission_prediction.ui_handoff
            else "blocked"
            if admission_prediction is not None
            else "generate"
        )
        for repeat_index in range(repeat_count):
            messages = build_prompt_messages(
                case,
                prompt_condition=prompt_condition,
            )
            generation = _generate_with_strict_envelope_recovery(
                messages=messages,
                generator=generator,
                recovery_policy=recovery_policy,
            )
            raw_output = generation.raw_output
            envelope = generation.envelope
            raw_parsed = (
                list(envelope.commands)
                if envelope.status is ToolEnvelopeStatus.VALID
                else []
            )
            normalized_parsed = (
                _normalized_parsed_tool_calls(case, list(envelope.commands))
                if envelope.status is ToolEnvelopeStatus.VALID
                else []
            )
            if generation.generation_error is not None:
                generation_errors.append(generation.generation_error)
                raw_prediction = _generation_failure_prediction(
                    case,
                    generation.generation_error,
                )
                host_assisted_prediction = admission_prediction or raw_prediction
                if admission_prediction is None:
                    host_generation_errors.append(generation.generation_error)
            else:
                raw_prediction = raw_prediction_from_model_output(case, raw_output)
                host_assisted_prediction = (
                    admission_prediction
                    or _apply_product_prompt_publication_gate(
                        case,
                        prediction_from_model_output(
                            case,
                            raw_output,
                        ),
                    )
                )
            raw_predictions.append(raw_prediction)
            host_assisted_predictions.append(host_assisted_prediction)
            raw_call_artifact = [
                {"tool_name": call.tool_name, "arguments": call.arguments}
                for call in raw_prediction.tool_calls
            ]
            host_call_artifact = [
                {"tool_name": call.tool_name, "arguments": call.arguments}
                for call in host_assisted_prediction.tool_calls
            ]
            normalized_call_artifact = [
                {"tool_name": name, "arguments": params}
                for name, params in normalized_parsed
            ]
            runs.append(
                {
                    "repeat_index": repeat_index,
                    "raw_output": raw_output,
                    "parsed_tool_calls": raw_call_artifact,
                    "raw_parsed_tool_calls": raw_call_artifact,
                    "normalized_tool_calls": normalized_call_artifact,
                    "host_assisted_parsed_tool_calls": host_call_artifact,
                    "host_admission_action": host_admission_action,
                    "host_model_generation_required": admission_prediction is None,
                    "normalization_applied": (
                        raw_call_artifact != normalized_call_artifact
                    ),
                    "host_safely_blocked": bool(host_assisted_prediction.blocked),
                    "schema_verification": _schema_verification(
                        schema_verifier,
                        raw_parsed,
                    ),
                    "host_assisted_schema_verification": _schema_verification(
                        schema_verifier,
                        [
                            (call.tool_name, call.arguments)
                            for call in host_assisted_prediction.tool_calls
                        ],
                    ),
                    "tool_envelope_status": envelope.status.value,
                    "tool_envelope_error": envelope.error,
                    "model_decision": envelope.decision,
                    "model_intent": envelope.intent,
                    "model_missing_inputs": list(envelope.missing_inputs),
                    "model_message": envelope.message,
                    "latency_seconds": round(
                        sum(attempt.latency_seconds for attempt in generation.attempts),
                        3,
                    ),
                    "error": generation.generation_error,
                    "recovery_taxonomy": generation.recovery_taxonomy,
                    "attempts": [
                        _strict_attempt_artifact(attempt)
                        for attempt in generation.attempts
                    ],
                },
            )

        raw_score = _mark_generation_failures(
            score_case(
                case,
                raw_predictions,
                score_scope=RAW_MODEL_DECISION_SCORE_SCOPE,
            ),
            generation_errors,
        )
        host_assisted_score = _mark_generation_failures(
            score_case(
                case,
                host_assisted_predictions,
                score_scope=HOST_ASSISTED_DECISION_SCORE_SCOPE,
            ),
            host_generation_errors,
        )
        raw_scores.append(raw_score)
        host_assisted_scores.append(host_assisted_score)
        case_runs.append(
            {
                "case_id": case.case_id,
                "title": case.title,
                "expected_verification_result": (
                    expected_verification_result_for(case)
                ),
                "runs": runs,
                "score": asdict(raw_score),
                "raw_model_score": asdict(raw_score),
                "host_assisted_score": asdict(host_assisted_score),
            },
        )

    return case_runs, raw_scores, host_assisted_scores


def _generation_failure_prediction(case: EvalCase, error: str) -> Prediction:
    """Represent runtime generation failure as an invalid benchmark output."""
    return Prediction(
        intent=_inferred_case_intent(case),
        tool_calls=[],
        format_valid=False,
        format_error=f"generation failed: {error}",
    )


def _mark_generation_failures(score: Any, errors: list[str]) -> Any:
    """Prevent repeated generation failure from scoring as stable no-tool output."""
    if not errors:
        return score
    breakdown = dict(score.score_breakdown)
    breakdown["output_format"] = False
    breakdown["local_llm_reliability"] = False
    failures = list(score.failures)
    if "generation failed" not in failures:
        failures.append("generation failed")
    return replace(
        score,
        passed=False,
        output_format=False,
        local_llm_reliability=False,
        score_breakdown=breakdown,
        failures=failures,
    )


def _generate_with_strict_envelope_recovery(
    *,
    messages: list[dict[str, str]],
    generator: TextGenerator,
    recovery_policy: StrictEnvelopeRecoveryPolicy,
) -> _StrictEnvelopeGeneration:
    """Run the product-equivalent strict format loop without output salvage."""
    prompt_messages = [dict(message) for message in messages]
    attempts: list[_StrictEnvelopeAttempt] = []
    recovery_attempts_used = 0

    while True:
        started = time.monotonic()
        try:
            raw_output = generator(prompt_messages)
            generation_error = None
        except Exception as exc:
            raw_output = ""
            generation_error = str(exc)
        elapsed = time.monotonic() - started
        envelope = CommandParser.parse_product(raw_output)

        if generation_error is not None:
            attempts.append(
                _StrictEnvelopeAttempt(
                    attempt_index=len(attempts),
                    raw_output=raw_output,
                    envelope=envelope,
                    latency_seconds=elapsed,
                    generation_error=generation_error,
                    decision=None,
                )
            )
            return _StrictEnvelopeGeneration(
                raw_output=raw_output,
                envelope=envelope,
                generation_error=generation_error,
                recovery_taxonomy="generation_error",
                attempts=tuple(attempts),
            )

        decision = recovery_policy.decide(
            StrictEnvelopeRecoveryRequest(
                envelope=envelope,
                recovery_attempts_used=recovery_attempts_used,
            )
        )
        attempts.append(
            _StrictEnvelopeAttempt(
                attempt_index=len(attempts),
                raw_output=raw_output,
                envelope=envelope,
                latency_seconds=elapsed,
                generation_error=None,
                decision=decision,
            )
        )
        if not decision.should_retry:
            return _StrictEnvelopeGeneration(
                raw_output=raw_output,
                envelope=envelope,
                generation_error=None,
                recovery_taxonomy=decision.taxonomy.value,
                attempts=tuple(attempts),
            )

        if decision.message is None:
            raise RuntimeError("Format retry decision is missing recovery context")
        recovery_attempts_used = decision.recovery_attempts_after
        prompt_messages = _append_recovery_context(
            prompt_messages,
            decision.message,
        )


def _append_recovery_context(
    messages: list[dict[str, str]],
    message: StrictEnvelopeRecoveryMessage,
) -> list[dict[str, str]]:
    """Append the canonical correction to system context without raw salvage."""
    updated = [dict(item) for item in messages]
    if updated and updated[0].get("role") == "system":
        updated[0]["content"] = f"{updated[0].get('content', '')}\n\n{message.content}"
    else:
        updated.insert(0, {"role": "system", "content": message.content})
    return updated


def _strict_attempt_artifact(
    attempt: _StrictEnvelopeAttempt,
) -> dict[str, Any]:
    """Serialize one generation attempt without discarding malformed output."""
    decision = attempt.decision
    return {
        "attempt_index": attempt.attempt_index,
        "raw_output": attempt.raw_output,
        "tool_envelope_status": attempt.envelope.status.value,
        "tool_envelope_error": attempt.envelope.error,
        "latency_seconds": round(attempt.latency_seconds, 3),
        "error": attempt.generation_error,
        "recovery_action": (
            decision.action.value if decision is not None else "generation_error"
        ),
        "recovery_taxonomy": (
            decision.taxonomy.value if decision is not None else "generation_error"
        ),
        "recovery_message": (
            decision.message.content
            if decision is not None and decision.message is not None
            else None
        ),
    }


def build_local_eval_cli_gate(
    result: dict[str, Any],
    *,
    strict: bool,
) -> dict[str, Any]:
    """Build the process-exit contract from the unassisted model score.

    Host normalization and capability blocking can make product execution safer,
    but they must not turn a failed raw-model benchmark into a passing hard gate.
    An empty or internally inconsistent score is also not a valid strict pass.
    """
    summary = result.get("raw_model_summary") or result.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("Local eval result is missing a raw-model summary.")
    total_cases = _int_or_zero(summary.get("total_cases"))
    passed_cases = _int_or_zero(summary.get("passed_cases"))
    failed_cases = _int_or_zero(summary.get("failed_cases"))
    passed = total_cases > 0 and failed_cases == 0 and passed_cases == total_cases
    exit_code = STRICT_GATE_FAILURE_EXIT_CODE if strict and not passed else 0
    return {
        "mode": "strict" if strict else "report_only",
        "score_scope": RAW_MODEL_DECISION_SCORE_SCOPE,
        "passed": passed,
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "failed_cases": failed_cases,
        "exit_code": exit_code,
    }


def write_local_artifacts(
    result: dict[str, Any], output_dir: Path
) -> tuple[Path, Path]:
    """Write local eval JSON and Markdown artifacts."""
    if "cli_gate" not in result:
        result = {
            **result,
            "cli_gate": build_local_eval_cli_gate(result, strict=False),
        }
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = _safe_suffix(str(result["model_id"]))
    json_path = output_dir / f"local_{suffix}.json"
    md_path = output_dir / f"local_{suffix}.md"
    result = {
        **result,
        "artifact_paths": {
            "json": str(json_path),
            "markdown": str(md_path),
            "latest_json": str(output_dir / "local_latest.json"),
            "latest_markdown": str(output_dir / "local_latest.md"),
        },
    }
    json_path.write_text(_compact_json(result), encoding="utf-8")
    md_path.write_text(render_local_markdown_report(result), encoding="utf-8")
    latest_json = output_dir / "local_latest.json"
    latest_md = output_dir / "local_latest.md"
    latest_json.write_text(
        _compact_json(
            {
                "schema_version": result["schema_version"],
                "latest_result": json_path.name,
                "latest_report": md_path.name,
                "runner": result["runner"],
                "model_id": result["model_id"],
                "prompt_condition": result["prompt_condition"],
                "evidence_status": result["evidence_status"],
                "benchmark_coverage": result["benchmark_coverage"],
                "measurement_contract": result["measurement_contract"],
                "generation_constraints": result["generation_constraints"],
                "cli_gate": result["cli_gate"],
                "generated_at": result["generated_at"],
                "repeat_count": result["repeat_count"],
                "exploratory": result["exploratory"],
                "provenance": result["provenance"],
                "summary": result["summary"],
                "raw_model_summary": result["raw_model_summary"],
                "host_assisted_summary": result["host_assisted_summary"],
                "failure_taxonomy": result["failure_taxonomy"],
                "recovery_taxonomy": result["recovery_taxonomy"],
            },
        ),
        encoding="utf-8",
    )
    latest_md.write_text(
        "\n".join(
            [
                "# XBrainLab Local Tool-Call Eval Latest",
                "",
                f"- latest result: `{json_path.name}`",
                f"- latest report: `{md_path.name}`",
                f"- model: `{result['model_id']}`",
                f"- prompt condition: `{result['prompt_condition']['name']}`",
                f"- raw model pass rate: "
                f"`{result['raw_model_summary']['pass_rate']:.2%}`",
                f"- CLI gate mode: `{result['cli_gate']['mode']}`",
                f"- CLI gate passed: `{result['cli_gate']['passed']}`",
                "",
            ],
        ),
        encoding="utf-8",
    )
    return json_path, md_path


def render_local_markdown_report(result: dict[str, Any]) -> str:
    """Render local-model eval results as Markdown."""
    base = render_markdown_report(
        {
            "runner": result["runner"],
            "method_references": result["method_references"],
            "summary": result["summary"],
            "cases": [case["score"] for case in result["cases"]],
        },
    )
    runtime = result["runtime"]
    cli_gate = result.get("cli_gate") or build_local_eval_cli_gate(
        result,
        strict=False,
    )
    header = [
        "# XBrainLab Local Tool-Call Eval",
        "",
        f"- runner: `{result['runner']}`",
        f"- artifact schema: `{result['schema_version']}`",
        f"- model: `{result['model_id']}`",
        f"- prompt condition: `{result['prompt_condition']['name']}`",
        "- prompt evidence role: `primary raw-accuracy condition`",
        f"- prompt condition description: {result['prompt_condition']['description']}",
        f"- engineering baseline protocol complete: "
        f"`{result['evidence_status']['engineering_baseline_protocol_complete']}`",
        f"- thesis-candidate protocol complete: "
        f"`{result['evidence_status']['thesis_candidate_protocol_complete']}`",
        f"- claim boundary: {result['evidence_status']['claim_boundary']}",
        f"- backend execution observed: "
        f"`{result['measurement_contract']['backend_execution_observed']}`",
        f"- generated at: `{result['generated_at']}`",
        f"- git commit: `{result['provenance']['git']['commit']}`",
        f"- worktree dirty: `{result['provenance']['git']['dirty']}`",
        f"- case fingerprint: `{result['provenance']['case_fingerprint']}`",
        f"- prompt fingerprint: `{result['provenance']['prompt_fingerprint']}`",
        f"- tool contract fingerprint: "
        f"`{result['provenance']['tool_contract_fingerprint']}`",
        f"- model revision: `{result['provenance']['model_revision']}`",
        f"- repeat count: `{result['repeat_count']}`",
        f"- exploratory: `{result['exploratory']}`",
        f"- CLI gate mode: `{cli_gate['mode']}`",
        f"- CLI gate passed: `{cli_gate['passed']}`",
        f"- CLI gate exit code: `{cli_gate['exit_code']}`",
        f"- runtime classification: `{runtime.get('classification')}`",
        f"- cache usage: `{runtime.get('cache_usage')}`",
        f"- generation constraint: `{result['generation_constraints']['mode']}`",
        f"- raw output postprocessed: "
        f"`{result['generation_constraints']['raw_output_postprocessed']}`",
        "",
        "## Score Interpretation",
        "",
        "### Raw Model Score",
        "",
        f"- pass rate: `{result['raw_model_summary']['pass_rate']:.2%}`",
        "- computed before tool alias normalization, argument repair, or safe "
        "backend blocking",
        "- host-assisted and backend outcome dimensions are N/A/excluded",
        "",
        "### Host-Assisted Product Score",
        "",
        f"- pass rate: `{result['host_assisted_summary']['pass_rate']:.2%}`",
        "- includes product normalization, verification, and capability-policy "
        "blocking",
        "- backend state delta and result interpretation remain N/A/excluded "
        "because this runner does not execute commands",
        "- this score must not be reported as raw model tool-call accuracy",
        "",
    ]
    preflight = result.get("resource_preflight") or {}
    if preflight:
        gpu = preflight.get("gpu") or {}
        header.extend(
            [
                "## Resource Preflight",
                "",
                f"- ok: `{preflight.get('ok')}`",
                f"- gate: `{preflight.get('gate')}`",
                f"- eval gate: `{preflight.get('eval_gate')}`",
                f"- resource pressure: `{preflight.get('resource_pressure')}`",
                f"- selected cases: `{preflight.get('selected_cases')}`",
                f"- cache usage: `{preflight.get('cache_usage')}`",
                f"- available disk: `{preflight.get('available_disk')}`",
                f"- estimated VRAM: `{preflight.get('estimated_vram_gb')}` GB",
                f"- GPU: `{gpu.get('name', 'unknown')}`",
                f"- VRAM used/free/total MiB: `{gpu.get('used_mib', 'n/a')}` / "
                f"`{gpu.get('free_mib', 'n/a')}` / `{gpu.get('total_mib', 'n/a')}`",
                f"- message: {preflight.get('message')}",
                "",
            ],
        )
    header.extend(["## Failure Taxonomy", ""])
    taxonomy = result["failure_taxonomy"]
    if taxonomy:
        header.extend(
            f"- {name}: `{count}`" for name, count in sorted(taxonomy.items())
        )
    else:
        header.append("- None.")
    header.extend(["", "## Strict Envelope Recovery", ""])
    recovery_taxonomy = result.get("recovery_taxonomy") or {}
    if recovery_taxonomy:
        header.extend(
            f"- {name}: `{count}`" for name, count in sorted(recovery_taxonomy.items())
        )
    else:
        header.append("- None.")
    header.extend(["", "## Scoring Detail", ""])
    return "\n".join(header) + "\n" + base


def _build_engine_generator(config: LLMConfig) -> TextGenerator:
    """Load a local engine once and return a generation callable."""
    if not config.local_backend_ready(config.model_name):
        raise RuntimeError(config.local_backend_status_message(config.model_name))
    return _EngineTextGenerator(config)


def _generation_constraint_report(generator: TextGenerator) -> dict[str, Any]:
    report = getattr(generator, "constraint_report", None)
    if isinstance(report, dict):
        return dict(report)
    return {
        "mode": "external_generator",
        "raw_output_postprocessed": False,
        "blocked_token_ids": [],
    }


def _artifact_runtime(runtime: dict[str, object]) -> dict[str, object]:
    """Keep local eval artifacts useful without storing host-specific paths."""
    keep = {
        "classification",
        "message",
        "has_local_cache",
        "gpu_fallback_reason",
        "load_in_4bit",
        "effective_load_in_4bit",
        "policy_error",
        "primary_local_model",
        "fallback_local_model",
        "cache_usage_bytes",
        "cache_usage",
        "max_total_cache_gb",
        "model_estimates",
    }
    return {key: value for key, value in runtime.items() if key in keep}


def _evidence_status(
    *,
    cases: list[EvalCase],
    repeat_count: int,
    prompt_condition: PromptConditionSpec,
) -> dict[str, Any]:
    """Encode protocol eligibility without turning an engineering run into a claim."""
    case_count = len(cases)
    coverage = _benchmark_coverage(cases)
    primary_condition = (
        prompt_condition.primary_raw_accuracy
        and not prompt_condition.evaluator_answer_fields_included
        and not prompt_condition.host_intent_included
        and not prompt_condition.case_specific_blocked_reason_included
        and not prompt_condition.host_normalization_hints_included
    )
    engineering_complete = (
        primary_condition
        and case_count >= ENGINEERING_BASELINE_MIN_CASES
        and repeat_count >= FULL_LOCAL_GATE_REPEAT_COUNT
        and coverage["protocol_mix_complete"]
    )
    thesis_complete = (
        primary_condition
        and case_count >= THESIS_CANDIDATE_MIN_CASES
        and repeat_count >= FULL_LOCAL_GATE_REPEAT_COUNT
        and coverage["protocol_mix_complete"]
    )
    return {
        "engineering_baseline_protocol_complete": engineering_complete,
        "thesis_candidate_protocol_complete": thesis_complete,
        "minimum_engineering_cases": ENGINEERING_BASELINE_MIN_CASES,
        "minimum_thesis_candidate_cases": THESIS_CANDIDATE_MIN_CASES,
        "minimum_repeats": FULL_LOCAL_GATE_REPEAT_COUNT,
        "benchmark_coverage": coverage,
        "backend_outcome_claim_supported": False,
        "claim_boundary": (
            "Scores support decision and strict host-safety comparisons only. "
            "Backend state delta and result interpretation require separately "
            "executed outcome evidence. A thesis-candidate decision-accuracy claim "
            "also requires primary and fallback reruns from a clean checkpoint with "
            "accepted artifacts."
        ),
    }


def _benchmark_coverage(cases: list[EvalCase]) -> dict[str, Any]:
    """Describe case composition used to qualify protocol-level evidence."""
    total = len(cases)
    blocked = sum(case.expected_blocked for case in cases)
    recovery = sum(case.expected_recovery for case in cases)
    missing_input = sum(
        expected_decision_verification_result_for(case) == "missing_input"
        for case in cases
    )
    no_tool = sum(case.expected_intent == "no_tool" for case in cases)
    negative_ids = {
        case.case_id
        for case in cases
        if case.expected_blocked
        or case.expected_recovery
        or case.expected_intent in {"no_tool", "ask_clarification"}
        or bool({"negative", "no_call", "missing_input"} & set(case.families))
    }
    negative_ratio = len(negative_ids) / total if total else 0.0
    required_categories_present = all(
        count > 0 for count in (blocked, recovery, missing_input, no_tool)
    )
    return {
        "total_cases": total,
        "blocked_cases": blocked,
        "recovery_cases": recovery,
        "missing_input_cases": missing_input,
        "no_tool_cases": no_tool,
        "negative_blocked_recovery_cases": len(negative_ids),
        "negative_blocked_recovery_ratio": negative_ratio,
        "minimum_negative_blocked_recovery_ratio": (
            MIN_NEGATIVE_BLOCKED_RECOVERY_RATIO
        ),
        "required_categories_present": required_categories_present,
        "protocol_mix_complete": (
            required_categories_present
            and negative_ratio >= MIN_NEGATIVE_BLOCKED_RECOVERY_RATIO
        ),
    }


def _build_eval_provenance(
    *,
    cases: list[EvalCase],
    config: LLMConfig,
    model_id: str,
    repeat_count: int,
    max_new_tokens: int,
    prompt_condition: PromptConditionSpec,
    generation_constraints: dict[str, Any],
) -> dict[str, Any]:
    """Return reproducibility metadata for one local-model eval artifact."""
    case_payload = [asdict(case) for case in cases]
    tool_contracts = sorted(
        (tool_contract_for_llm(tool) for tool in get_all_tools(mode="mock")),
        key=lambda contract: str(contract.get("name") or ""),
    )
    repo_root = Path(__file__).resolve().parents[3]
    source_paths = {
        "cases": Path(__file__).with_name("run_tool_call_eval.py"),
        "runner": Path(__file__),
        "strict_envelope_recovery": (
            repo_root / "XBrainLab/llm/agent/strict_envelope_recovery.py"
        ),
        "prompt_policy": repo_root / "XBrainLab/llm/agent/prompt_policy.py",
        "parser": repo_root / "XBrainLab/llm/agent/parser.py",
        "normalizer": repo_root / "XBrainLab/llm/agent/tool_call_normalizer.py",
        "verifier": repo_root / "XBrainLab/llm/agent/verifier.py",
        "capability_policy": (
            repo_root / "XBrainLab/backend/application/capabilities.py"
        ),
    }
    source_fingerprints = {
        name: _file_sha256(path) for name, path in source_paths.items()
    }
    case_fingerprint = _json_sha256(case_payload)
    prompt_condition_payload = prompt_condition.to_dict()
    prompt_condition_fingerprint = _json_sha256(prompt_condition_payload)
    prompt_fingerprint = _text_sha256(
        _compact_json(prompt_condition_payload)
        + inspect.getsource(_primary_prompt_state_snapshot)
        + inspect.getsource(_primary_prompt_decision_context)
        + inspect.getsource(build_prompt_messages)
        + inspect.getsource(StrictEnvelopeRecoveryPolicy)
    )
    tool_contract_fingerprint = _json_sha256(tool_contracts)
    evaluation_fingerprint = _json_sha256(
        {
            "model_id": model_id,
            "model_revision": _cached_model_revision(config.cache_dir, model_id),
            "repeat_count": repeat_count,
            "max_new_tokens": max_new_tokens,
            "prompt_condition": prompt_condition_payload,
            "prompt_condition_fingerprint": prompt_condition_fingerprint,
            "generation_constraints": generation_constraints,
            "case_ids": [case.case_id for case in cases],
            "case_fingerprint": case_fingerprint,
            "prompt_fingerprint": prompt_fingerprint,
            "tool_contract_fingerprint": tool_contract_fingerprint,
            "source_fingerprints": source_fingerprints,
        }
    )
    return {
        "git": _git_provenance(),
        "model_revision": _cached_model_revision(config.cache_dir, model_id),
        "prompt_condition": prompt_condition_payload,
        "prompt_condition_fingerprint": prompt_condition_fingerprint,
        "generation_constraints": generation_constraints,
        "case_fingerprint": case_fingerprint,
        "prompt_fingerprint": prompt_fingerprint,
        "tool_contract_fingerprint": tool_contract_fingerprint,
        "source_fingerprints": source_fingerprints,
        "evaluation_fingerprint": evaluation_fingerprint,
    }


def _git_provenance() -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[3]
    commit = _git_output(repo_root, "rev-parse", "HEAD") or "unknown"
    branch = _git_output(repo_root, "branch", "--show-current") or "detached"
    status = _git_output(repo_root, "status", "--porcelain")
    dirty_lines = [line for line in status.splitlines() if line.strip()]
    return {
        "commit": commit,
        "branch": branch,
        "dirty": bool(dirty_lines),
        "dirty_path_count": len(dirty_lines),
    }


def _git_output(repo_root: Path, *args: str) -> str:
    git_binary = shutil.which("git")
    if not git_binary:
        return ""
    try:
        completed = subprocess.run(  # noqa: S603 - fixed git binary, no shell.
            [git_binary, *args],
            cwd=repo_root,
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _cached_model_revision(cache_dir: str, model_id: str) -> str:
    """Return the cached Hugging Face revision without network access."""
    for candidate_text in model_cache_candidates(cache_dir, model_id):
        candidate = Path(candidate_text)
        ref = candidate / "refs" / "main"
        try:
            revision = ref.read_text(encoding="utf-8").strip()
        except OSError:
            revision = ""
        if revision:
            return revision
        snapshots = candidate / "snapshots"
        try:
            names = sorted(path.name for path in snapshots.iterdir() if path.is_dir())
        except OSError:
            names = []
        if len(names) == 1:
            return names[0]
    return "unknown"


def _file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "unavailable"


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_sha256(value: Any) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return _text_sha256(serialized)


def _compact_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"


def _select_cases(
    cases: list[EvalCase],
    *,
    case_ids: list[str] | None,
    case_limit: int | None,
) -> list[EvalCase]:
    if case_ids:
        requested = set(case_ids)
        selected = [case for case in cases if case.case_id in requested]
        missing = requested - {case.case_id for case in selected}
        if missing:
            raise ValueError(f"Unknown case id(s): {', '.join(sorted(missing))}")
    else:
        selected = list(cases)
    if case_limit is not None:
        return selected[:case_limit]
    return selected


def _available_tool_schemas(state_name: str) -> list[dict[str, Any]]:
    state = make_state(state_name)
    policy = build_capability_policy(state)
    stage_tools = set(STAGE_CONFIG[_prompt_stage_for_state(state)]["tools"])
    schemas: list[dict[str, Any]] = []
    for tool in get_all_tools(mode="mock"):
        command_name = TOOL_TO_COMMAND.get(tool.name)
        if command_name is not None:
            if tool.name in LEGACY_COMPATIBILITY_TOOLS or tool.name not in stage_tools:
                continue
            capability = policy.get(command_name)
            if not capability.enabled:
                continue
            schema = tool_contract_for_llm(tool)
            schema["description"] = (
                f"{str(schema.get('description', '')).rstrip()}"
                f"{_TOOL_MATCH_NOTES.get(tool.name, '')}"
                f"{_STRICT_DIRECT_REQUEST_TOOL_NOTE}"
            ).strip()
            schema["requires_confirmation"] = (
                capability.requires_confirmation or capability.confirmation_required
            )
            schema["decision_boundary"] = capability.decision_boundary
            schemas.append(schema)
        elif tool.name in READ_ONLY_TOOLS:
            schema = tool_contract_for_llm(tool)
            schema["description"] = (
                f"{str(schema.get('description', '')).rstrip()}"
                f"{_TOOL_MATCH_NOTES.get(tool.name, '')}"
                f"{_STRICT_DIRECT_REQUEST_TOOL_NOTE}"
            ).strip()
            schema["requires_confirmation"] = False
            schema["decision_boundary"] = None
            schemas.append(schema)
    schemas.insert(0, model_response_tool_contract())
    return schemas


def _prompt_stage_for_state(state: Any) -> PipelineStage:
    """Map the typed eval snapshot to the product prompt's workflow stage."""
    if state.training.finished_run_count > 0:
        return PipelineStage.TRAINED
    if state.training.is_running:
        return PipelineStage.TRAINING
    if state.dataset.available:
        return PipelineStage.DATASET_READY
    if state.epoch.available:
        return PipelineStage.EPOCH_READY
    if state.preprocessed.available:
        return PipelineStage.PREPROCESSED
    if state.raw.loaded:
        return PipelineStage.DATA_LOADED
    return PipelineStage.EMPTY


def _tool_schema_map() -> dict[str, dict[str, Any]]:
    return {tool.name: tool.parameters for tool in get_all_tools(mode="mock")}


def _prediction_verifier() -> VerificationLayer:
    """Return local-eval verification without host filesystem path checks."""
    return VerificationLayer(
        validators=[PlaceholderArgumentValidator()],
        tool_schemas=_tool_schema_map(),
    )


def _prediction_tool_calls(
    case: EvalCase,
    parsed: list[tuple[str, dict[str, Any]]],
) -> list[PredictedToolCall]:
    return [
        PredictedToolCall(
            tool_name=name,
            arguments=_normalized_prediction_arguments(name, params),
        )
        for name, params in _normalized_parsed_tool_calls(case, parsed)
    ][:1]


def _normalized_parsed_tool_calls(
    case: EvalCase,
    parsed: list[tuple[str, dict[str, Any]]],
) -> list[tuple[str, dict[str, Any]]]:
    latest_user_text = case.user_turns[-1] if case.user_turns else ""
    return [
        normalize_tool_call(name, params, latest_user_text=latest_user_text)
        for name, params in parsed
    ]


def _normalized_prediction_arguments(
    tool_name: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    normalized = dict(params)
    if tool_name == "configure_dataset_split":
        normalized.setdefault("val_ratio", 0.2)
    return normalized


def _inferred_case_intent(case: EvalCase) -> str:
    latest = infer_intent(case.user_turns[-1].lower()) if case.user_turns else "unknown"
    if latest != "unknown":
        return latest
    return infer_intent(" ".join(case.user_turns).lower())


def _intent_adjusted_verification_message(intent: str, message: str) -> str:
    label = path_label_for_intent(intent)
    lower = message.lower()
    if intent == "ask_clarification":
        return "Please tell me which workflow step or input you want to use."
    if label is None:
        return message
    if "actual path" in lower or "absolute path" in lower:
        return f"Required {label} must be an actual path provided by the user."
    if "missing required parameter" in lower or "required input" in lower:
        return f"Required {label} is missing."
    return message


def _mentions_policy_reason(text: str, policy_reason: str) -> bool:
    lower = text.lower()
    for reason in policy_reason.split(";"):
        reason_text = reason.strip().lower()
        if reason_text and reason_text in lower:
            return True
    return False


def _blocked_requested_intent_reason(state_name: str, intent: str) -> str:
    command_name = command_for_intent(intent)
    if command_name is None:
        return ""
    capability = build_capability_policy(make_state(state_name)).get(command_name)
    if capability.enabled:
        return ""
    return "; ".join(capability.reasons)


def _schema_verification(
    verifier: VerificationLayer,
    parsed: list[tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    return [
        {
            "tool_name": name,
            "is_valid": result.is_valid,
            "error_message": result.error_message,
        }
        for name, params in parsed
        for result in [verifier.verify_tool_call((name, params))]
    ]


def _verification_missing_input_fields(
    tool_name: str,
    params: dict[str, Any],
    message: str,
) -> tuple[str, ...]:
    """Derive host-known missing field ids from schema and verifier evidence."""
    schema = _tool_schema_map().get(tool_name) or {}
    required = tuple(
        field
        for field in schema.get("required", [])
        if isinstance(field, str) and field not in params
    )
    if required:
        return required
    if tool_name == "preview_interpretation" and "remap target" in message.lower():
        return ("eeg_file_remap",)
    if "path" not in message.lower():
        return ()
    properties = schema.get("properties") or {}
    return tuple(
        field
        for field in properties
        if isinstance(field, str)
        and "path" in field
        and (field in params or field in schema.get("required", []))
    )


def _blocked_reason_for_tool(state_name: str, tool_name: str) -> str:
    command_name = TOOL_TO_COMMAND.get(tool_name)
    if command_name is None:
        return "" if tool_name in READ_ONLY_TOOLS else "Tool is not available."
    capability = build_capability_policy(make_state(state_name)).get(command_name)
    if capability.enabled:
        return ""
    return "; ".join(capability.reasons)


def _confirmation_required_for_tool(state_name: str, tool_name: str) -> bool:
    command_name = TOOL_TO_COMMAND.get(tool_name)
    if command_name is None:
        return False
    capability = build_capability_policy(make_state(state_name)).get(command_name)
    return capability.requires_confirmation or capability.confirmation_required


def _failure_taxonomy(scores: list[Any]) -> dict[str, int]:
    taxonomy: dict[str, int] = {}
    for score in scores:
        for failure in score.failures:
            key = failure.split(" expected ", maxsplit=1)[0]
            taxonomy[key] = taxonomy.get(key, 0) + 1
    return taxonomy


def _recovery_taxonomy(case_runs: list[dict[str, Any]]) -> dict[str, int]:
    """Count final strict-envelope outcomes across all case repeats."""
    taxonomy: dict[str, int] = {}
    for case_run in case_runs:
        for run in case_run.get("runs", []):
            key = str(run.get("recovery_taxonomy") or "unknown")
            taxonomy[key] = taxonomy.get(key, 0) + 1
    return taxonomy


def _safe_suffix(model_id: str) -> str:
    return model_id.replace("/", "_").replace("-", "_").lower()


def _resolve_model(args: argparse.Namespace) -> str:
    if args.model:
        return str(args.model)
    if args.model_role == "primary":
        return default_local_model_id()
    if args.model_role == "fallback":
        return fallback_local_model_id()
    config = LLMConfig.load_from_file() or LLMConfig()
    return config.model_name


def build_local_eval_resource_preflight(
    *,
    model_id: str,
    model_role: str,
    eval_gate: str = "candidate",
    repeat_count: int,
    case_ids: list[str] | None,
    case_limit: int | None,
    cache_dir: str | None = None,
    cache_usage_bytes_value: int | None = None,
    available_disk_bytes_value: int | None = None,
    gpu_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return disk/cache/VRAM preflight metadata for a local eval run."""
    config = LLMConfig.load_from_file() or LLMConfig()
    resolved_cache_dir = cache_dir or config.cache_dir
    cache_bytes = (
        cache_usage_bytes_value
        if cache_usage_bytes_value is not None
        else cache_usage_bytes(resolved_cache_dir)
    )
    disk_bytes = (
        available_disk_bytes_value
        if available_disk_bytes_value is not None
        else available_disk_bytes(resolved_cache_dir)
    )
    selected_cases = len(
        _select_cases(
            build_eval_cases(),
            case_ids=case_ids,
            case_limit=case_limit,
        ),
    )
    full_suite = case_ids is None and case_limit is None
    full_local_gate = full_suite and repeat_count >= FULL_LOCAL_GATE_REPEAT_COUNT
    spec = local_model_spec(model_id)
    estimated_vram_gb = spec.estimated_vram_gb if spec is not None else None
    gpu = gpu_snapshot if gpu_snapshot is not None else _collect_gpu_memory_snapshot()
    pressure = _resource_pressure(gpu, estimated_vram_gb)
    normalized_eval_gate = eval_gate.lower()
    release_gate = normalized_eval_gate in RELEASE_LOCAL_EVAL_GATES
    gate_mismatch = full_local_gate and not release_gate
    resource_blocked = full_local_gate and pressure == "high"
    ok = not gate_mismatch and not resource_blocked
    gate = (
        f"{normalized_eval_gate} full local"
        if full_local_gate
        else f"{normalized_eval_gate} local subset"
    )
    if gate_mismatch and resource_blocked:
        message = (
            "full local x3 is a release/thesis gate, and VRAM is nearly full; "
            "refusing to start local eval. Pass --eval-gate release or "
            "--eval-gate thesis only when refreshing a formal benchmark claim, "
            "and free GPU memory before rerunning."
        )
    elif gate_mismatch:
        message = (
            "full local x3 is a release/thesis gate; pass --eval-gate release "
            "or --eval-gate thesis only when refreshing a formal benchmark "
            "claim. Routine changes should use deterministic changed cases or "
            "a primary subset."
        )
    elif resource_blocked:
        message = (
            "VRAM is nearly full; refusing to start a full local x3 eval. "
            "Run deterministic or changed-case eval first, or free GPU memory "
            "before release/thesis local eval."
        )
    elif ok:
        message = (
            "Resource preflight passed for this eval gate."
            if pressure != "high"
            else "GPU memory is under high pressure; run only changed cases or a "
            "small primary subset until memory is freed."
        )
    else:
        message = "Resource preflight failed."

    return {
        "ok": ok,
        "message": message,
        "gate": gate,
        "eval_gate": normalized_eval_gate,
        "model_id": model_id,
        "model_role": model_role,
        "repeat_count": repeat_count,
        "selected_cases": selected_cases,
        "full_suite": full_suite,
        "full_local_gate": full_local_gate,
        "resource_pressure": pressure,
        "cache_dir": resolved_cache_dir,
        "cache_usage_bytes": cache_bytes,
        "cache_usage": format_bytes(cache_bytes),
        "available_disk_bytes": disk_bytes,
        "available_disk": format_bytes(disk_bytes),
        "estimated_vram_gb": estimated_vram_gb,
        "gpu": gpu,
    }


def _collect_gpu_memory_snapshot() -> dict[str, Any]:
    """Read current GPU memory from nvidia-smi without making it mandatory."""
    command = [
        "nvidia-smi",
        "--query-gpu=index,name,memory.total,memory.used,memory.free",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(  # noqa: S603 - fixed nvidia-smi command, no shell.
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "reason": str(exc)}
    if completed.returncode != 0:
        return {
            "available": False,
            "reason": (completed.stderr or completed.stdout).strip(),
        }
    first_line = next(
        (line.strip() for line in completed.stdout.splitlines() if line.strip()),
        "",
    )
    if not first_line:
        return {"available": False, "reason": "nvidia-smi returned no GPU rows."}
    parts = [part.strip() for part in first_line.split(",", maxsplit=4)]
    if len(parts) != 5:
        return {
            "available": False,
            "reason": f"Unexpected nvidia-smi row: {first_line}",
        }
    try:
        index = int(parts[0])
        total_mib = int(parts[2])
        used_mib = int(parts[3])
        free_mib = int(parts[4])
    except ValueError:
        return {
            "available": False,
            "reason": f"Unexpected nvidia-smi row: {first_line}",
        }
    return {
        "available": True,
        "index": index,
        "name": parts[1],
        "total_mib": total_mib,
        "used_mib": used_mib,
        "free_mib": free_mib,
    }


def _resource_pressure(
    gpu: dict[str, Any],
    estimated_vram_gb: float | None,
) -> str:
    if not gpu.get("available"):
        return "unknown"
    total_mib = _int_or_zero(gpu.get("total_mib"))
    used_mib = _int_or_zero(gpu.get("used_mib"))
    free_mib = _int_or_zero(gpu.get("free_mib"))
    if total_mib <= 0:
        return "unknown"
    estimated_floor = int((estimated_vram_gb or 0.0) * 1024 * 0.25)
    free_threshold = max(VRAM_PRESSURE_FREE_MIB, estimated_floor)
    if free_mib < free_threshold or used_mib / total_mib >= VRAM_PRESSURE_USED_RATIO:
        return "high"
    return "normal"


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def write_resource_preflight_artifact(
    preflight: dict[str, Any],
    output_dir: Path,
) -> tuple[Path, Path]:
    """Persist a resource preflight result when local eval is blocked."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "resource_preflight.json"
    md_path = output_dir / "resource_preflight.md"
    json_path.write_text(_compact_json(preflight), encoding="utf-8")
    gpu = preflight.get("gpu") or {}
    lines = [
        "# Local Tool-Call Eval Resource Preflight",
        "",
        f"- ok: `{preflight.get('ok')}`",
        f"- gate: `{preflight.get('gate')}`",
        f"- eval gate: `{preflight.get('eval_gate')}`",
        f"- model: `{preflight.get('model_id')}`",
        f"- repeat count: `{preflight.get('repeat_count')}`",
        f"- selected cases: `{preflight.get('selected_cases')}`",
        f"- resource pressure: `{preflight.get('resource_pressure')}`",
        f"- cache usage: `{preflight.get('cache_usage')}`",
        f"- available disk: `{preflight.get('available_disk')}`",
        f"- estimated VRAM: `{preflight.get('estimated_vram_gb')}` GB",
        f"- GPU: `{gpu.get('name', 'unknown')}`",
        f"- VRAM used/free/total MiB: `{gpu.get('used_mib', 'n/a')}` / "
        f"`{gpu.get('free_mib', 'n/a')}` / `{gpu.get('total_mib', 'n/a')}`",
        f"- message: {preflight.get('message')}",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def _strict_cli_gate_requested(args: argparse.Namespace) -> bool:
    if args.report_only:
        return False
    return bool(args.strict or args.eval_gate in RELEASE_LOCAL_EVAL_GATES)


def _resolve_case_suite_ids(
    *,
    case_suite: str,
    case_ids: list[str] | None,
) -> list[str] | None:
    """Resolve a named benchmark partition without changing case truth."""
    if case_suite == "all":
        return case_ids
    if case_ids:
        raise ValueError("--case-suite cannot be combined with --case-id")
    return list(PHI4_DECISION_CASE_SUITES[case_suite])


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None, help="Explicit supported model id.")
    parser.add_argument(
        "--model-role",
        choices=("configured", "primary", "fallback"),
        default="configured",
        help="Model role to evaluate when --model is not provided.",
    )
    parser.add_argument(
        "--eval-gate",
        choices=("fast", "candidate", "release", "thesis"),
        default="candidate",
        help=(
            "Validation gate for this local eval. Full suite repeat>=3 requires "
            "release or thesis."
        ),
    )
    parser.add_argument("--repeat-count", type=int, default=3)
    parser.add_argument("--case-limit", type=int, default=None)
    parser.add_argument("--case-id", action="append", default=None)
    parser.add_argument(
        "--case-suite",
        choices=("all", "development", "held-out"),
        default="all",
        help=(
            "Run all cases, the fixed 12-case Phi-4 development partition, or "
            "the disjoint 7-case held-out/paraphrase partition."
        ),
    )
    parser.add_argument("--max-new-tokens", type=int, default=160)
    exit_mode = parser.add_mutually_exclusive_group()
    exit_mode.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Use raw-model case results as a hard gate and return exit code 1 "
            "when any case fails. Release/thesis gates are strict by default."
        ),
    )
    exit_mode.add_argument(
        "--report-only",
        action="store_true",
        help=(
            "Always return exit code 0 after writing a completed eval report, "
            "even when cases fail. Resource-preflight failures still return 2."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/agent_evals",
        help="Directory for local eval artifacts.",
    )
    args = parser.parse_args(argv)
    try:
        case_ids = _resolve_case_suite_ids(
            case_suite=args.case_suite,
            case_ids=args.case_id,
        )
    except ValueError as exc:
        parser.error(str(exc))
    model_id = _resolve_model(args)
    resource_preflight = build_local_eval_resource_preflight(
        model_id=model_id,
        model_role=args.model_role,
        eval_gate=args.eval_gate,
        repeat_count=args.repeat_count,
        case_ids=case_ids,
        case_limit=args.case_limit,
    )
    if not resource_preflight["ok"]:
        json_path, md_path = write_resource_preflight_artifact(
            resource_preflight,
            Path(args.output_dir),
        )
        print(resource_preflight["message"])
        print(f"Wrote {json_path}")
        print(f"Wrote {md_path}")
        return RESOURCE_PREFLIGHT_FAILURE_EXIT_CODE

    result = run_local_eval(
        model_id=model_id,
        repeat_count=args.repeat_count,
        case_ids=case_ids,
        case_limit=args.case_limit,
        max_new_tokens=args.max_new_tokens,
        resource_preflight=resource_preflight,
    )
    result = {**result, "case_suite": args.case_suite}
    cli_gate = build_local_eval_cli_gate(
        result,
        strict=_strict_cli_gate_requested(args),
    )
    result = {**result, "cli_gate": cli_gate}
    json_path, md_path = write_local_artifacts(result, Path(args.output_dir))
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    if not cli_gate["passed"]:
        label = "Strict gate failed" if cli_gate["mode"] == "strict" else "Report only"
        print(
            f"{label}: {cli_gate['failed_cases']} of "
            f"{cli_gate['total_cases']} raw-model cases failed."
        )
    return int(cli_gate["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
