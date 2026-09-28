"""Stable-v2 local-model selection evaluation contracts."""

import hashlib
import io
import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.dev.run_stable_assistant_model_eval import (
    BOUNDED_BASELINE_MODEL_ID,
    BOUNDED_BASELINE_MODEL_REVISION,
    DEFAULT_CASES,
    DEFAULT_CHALLENGES,
    DEFAULT_CLARIFICATION_CASES,
    DEFAULT_PRECISION_CASES,
    FROZEN_CASE_FILE_SHA256,
    CaseTrajectoryResult,
    GenerationTraceRecorder,
    ModelGenerationAttempt,
    TargetEvalScore,
    _bounded_baseline_gate,
    _build_recovery_case_messages,
    _build_report,
    _capture_audit_request,
    _capture_integrity_report,
    _evaluation_generation_policy,
    _experiment_identity,
    _ProductRAGCaseMessages,
    _stable_eval_config,
    _trajectory_payload,
    admit_clarification_receipt,
    build_case_messages,
    evaluate_case_trajectory,
    evaluate_clarification_trajectory,
    evaluate_discriminated_clarification_trajectory,
    load_challenge_cases,
    load_clarification_cases,
    load_precision_cases,
    load_target_cases,
    report_bounded_baseline_passed,
    report_candidate_passed,
    run_eval,
    score_challenge_response,
    score_missing_parameter_host_guard,
    score_model_response,
    score_positive_parameter_host_guard,
    score_precision_response,
    score_raw_precision_response,
    target_tool_registry,
)
from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS
from XBrainLab.llm.agent.strict_envelope_recovery import (
    DEFAULT_STRICT_ENVELOPE_RECOVERY_POLICY,
)
from XBrainLab.llm.core.backends.local import LocalBackend
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.model_catalog import local_model_spec
from XBrainLab.llm.rag.config import RAGConfig
from XBrainLab.llm.tools import get_all_tools

EVALUATOR_POSITIVE_CASES = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "dev"
    / "stable_assistant_positive_cases.json"
)
EVALUATOR_POSITIVE_CASES_SHA256 = (
    "5d60662ce3f43e36c346dbda238a23f7"  # pragma: allowlist secret
    "b22377c04043e1833a77296931546577"  # pragma: allowlist secret
)


def _model_response(tool_name, parameters, *, turn="U1", mode="replace"):
    """Author a new-contract model fixture; runtime never adapts old envelopes."""
    if tool_name == "respond_to_user":
        action = parameters.get("pending_action")
        return json.dumps(
            {
                "decision": "clarify" if action else "reply",
                "mode": (
                    {
                        "replace": "new_request",
                        "continue": "update_pending",
                        "cancel": "cancel_pending",
                    }[mode]
                    if action
                    else None
                ),
                "action": (action if action else None),
                "changes": {},
                "message": parameters.get("message", ""),
            }
        )
    return json.dumps(
        {
            "decision": "execute",
            "message": None,
            "mode": {
                "replace": "new_request",
                "continue": "update_pending",
                "cancel": "cancel_pending",
            }[mode],
            "action": tool_name,
            "changes": {
                name: {
                    "value": value,
                    "source_turn": turn,
                    "quote": value if isinstance(value, str) else json.dumps(value),
                }
                for name, value in parameters.items()
            },
        }
    )


class _ImmediateProductRAGLifecycle:
    """Controlled callback double for the product lifecycle boundary."""

    def __init__(self, context: str, *, error: str = "") -> None:
        self.context = context
        self.error = error
        self.requests: list[tuple[int, str, frozenset[str] | None]] = []

    def retrieve(self, turn_id, query, callback, *, allowed_tool_names=None):
        self.requests.append((turn_id, query, allowed_tool_names))
        callback(turn_id, query, self.context, self.error)
        return True

    def cancel_retrieval(self, _turn_id):
        return True


def test_product_rag_case_messages_use_assembler_tool_projection_and_context() -> None:
    case = load_target_cases(DEFAULT_CASES)[0]
    lifecycle = _ImmediateProductRAGLifecycle(
        '{"schema":"xbrainlab.untrusted_context.v1","trust":"untrusted","items":[]}'
    )
    builder = _ProductRAGCaseMessages(target_tool_registry(), lifecycle)  # type: ignore[arg-type]

    messages = builder.messages(case)
    evidence = builder.evidence_for(case)

    assert lifecycle.requests == [
        (1, case.user_input, frozenset(evidence.allowed_tool_names))
    ]
    assert case.expected_tool in evidence.allowed_tool_names
    assert evidence.protocol == "product_process_rag.v1"
    assert evidence.status == "retrieved"
    assert evidence.context_sha256 is not None
    assert any("xbrainlab.untrusted_context.v1" in row["content"] for row in messages)


def test_product_rag_cache_reuses_only_the_same_case_turn_query() -> None:
    case = load_target_cases(DEFAULT_CASES)[0]
    follow_up = replace(case, user_input="Please repeat that request.")
    lifecycle = _ImmediateProductRAGLifecycle("")
    builder = _ProductRAGCaseMessages(target_tool_registry(), lifecycle)  # type: ignore[arg-type]

    builder.messages(case)
    builder.messages(case)
    builder.messages(follow_up)

    assert [(turn_id, query) for turn_id, query, _tools in lifecycle.requests] == [
        (1, case.user_input),
        (2, follow_up.user_input),
    ]
    assert builder.evidence_for(case).sequence == 1
    assert builder.evidence_for(follow_up).sequence == 2
    assert [
        evidence.sequence for evidence in builder.evidence_for_case(case.case_id)
    ] == [1, 2]


@pytest.mark.parametrize("suffix", ["supplement", "correction"])
def test_contextual_rag_model_messages_keep_derived_prior_and_actual_u2(suffix):
    from scripts.dev.assistant_pilot_case import audit_initial_input
    from XBrainLab.llm.agent.context_encoding import (
        UntrustedContextItem,
        UntrustedContextSource,
        decode_untrusted_context,
        encode_untrusted_context,
    )

    corpus = json.loads(RAGConfig.get_gold_set_path().read_text())
    row = next(
        row for row in corpus if row["id"] == f"apply_bandpass_filter_{suffix}_01"
    )
    context = encode_untrusted_context(
        [
            UntrustedContextItem(
                item_type="rag_example",
                source=UntrustedContextSource(
                    kind="xbrainlab_bundled_gold_set",
                    id=row["id"],
                    category=row["category"],
                ),
                data={
                    key: row[key]
                    for key in ("input", "expected_proposal", "prior_turn")
                },
            )
        ],
        max_chars=4096,
        max_items=1,
        max_string_chars=768,
    )
    case = next(
        case
        for case in load_target_cases(DEFAULT_CASES)
        if case.expected_tool == "apply_bandpass_filter"
    )
    builder = _ProductRAGCaseMessages(
        target_tool_registry(), _ImmediateProductRAGLifecycle(context)
    )
    messages = builder.messages(case)
    examples = [
        item
        for message in messages
        for item in decode_untrusted_context(message["content"]) or ()
        if item.item_type == "rag_example"
    ]
    assert len(examples) == 1
    actual = examples[0].data
    assert actual["input"] == row["input"]
    assert actual["expected_proposal"] == row["expected_proposal"]
    assert "prior_turn" not in actual
    assert actual["context"]["current_user"] == {"id": "U2", "text": row["input"]}
    pending = actual["context"]["pending_request"]
    assert (
        pending["parameters"]["low_freq"]
        == row["prior_turn"]["expected_proposal"]["changes"]["low_freq"]
    )
    assert pending["user_sources"] == {"U1": row["prior_turn"]["input"]}
    assert builder.evidence_for(case).assembled_context_item_ids == (row["id"],)
    # The case's real U1 remains separate from the example's derived U1/U2.
    audit = audit_initial_input(
        {"input": case.user_input},
        {},
        {"generations": [{"request": {"messages": messages}}]},
    )
    assert audit["issues"] == []
    assert audit["untrusted_rag_example_count"] == 1


def test_product_rag_error_discards_context_but_healthy_empty_is_distinct() -> None:
    case = load_target_cases(DEFAULT_CASES)[0]
    encoded_context = (
        '{"schema":"xbrainlab.untrusted_context.v1","trust":"untrusted",'
        '"items":[{"type":"rag_example","source":{"kind":"test","id":"drop-me"},'
        '"data":{"input":"do not inject"}}]}'
    )
    failed = _ProductRAGCaseMessages(
        target_tool_registry(),
        _ImmediateProductRAGLifecycle(encoded_context, error="retrieval failed"),  # type: ignore[arg-type]
    )
    healthy_empty = _ProductRAGCaseMessages(
        target_tool_registry(),
        _ImmediateProductRAGLifecycle(""),  # type: ignore[arg-type]
    )

    failed_messages = failed.messages(case)
    failed_evidence = failed.evidence_for(case)
    healthy_empty.messages(case)

    assert failed_evidence.status == "degraded"
    assert failed_evidence.context_item_ids == ()
    assert failed_evidence.context_sha256 is None
    assert "drop-me" not in json.dumps(failed_messages)
    assert healthy_empty.evidence_for(case).status == "empty"


def _complete_v14_case_summaries() -> dict[str, dict[str, object]]:
    return {
        "core": {
            "expected_case_count": 50,
            "case_count": 50,
            "passed_count": 36,
            "failed_count": 14,
            "complete": True,
            "passed": False,
        },
        "precision": {
            "expected_case_count": 24,
            "case_count": 24,
            "passed_count": 24,
            "failed_count": 0,
            "complete": True,
            "passed": True,
        },
        "clarification": {
            "expected_case_count": 7,
            "case_count": 7,
            "passed_count": 7,
            "failed_count": 0,
            "complete": True,
            "passed": True,
        },
        "total": {
            "expected_case_count": 81,
            "case_count": 81,
            "complete": True,
        },
    }


def _bounded_baseline_report() -> dict[str, object]:
    corpus_paths = {
        "positive": DEFAULT_CASES,
        "challenge": DEFAULT_CHALLENGES,
        "precision": DEFAULT_PRECISION_CASES,
        "clarification": DEFAULT_CLARIFICATION_CASES,
    }
    results = [
        {
            "suite": suite,
            "case": {"case_id": row["id"]},
            "score": {
                "passed": suite != "challenge"
                and row["id"]
                not in {
                    "select_channels_before_data_en",
                    "ambiguous_en",
                    "generic_filter_selection",
                }
            },
        }
        for suite, path in corpus_paths.items()
        for row in json.loads(path.read_text(encoding="utf-8"))
    ]
    return {
        "schema_version": "xbrainlab.stable_assistant_model_eval.v16",
        "model": {
            "id": BOUNDED_BASELINE_MODEL_ID,
            "revision": BOUNDED_BASELINE_MODEL_REVISION,
            "backend": "local",
            "deterministic": True,
        },
        "results": results,
        "case_summaries": {
            "total": {"expected_case_count": 81, "case_count": 81, "complete": True}
        },
        "candidate_gate": {
            "host_safety": {
                "explicit_parameter_origin": {"required": 10, "passed": 10},
                "missing_parameter_origin": {"required": 5, "passed": 5},
            }
        },
        "experiment_identity": dict(FROZEN_CASE_FILE_SHA256),
    }


def _write_runtime_capture_session(
    root: Path,
    session_id: str,
    *,
    model_id: str,
    generation_policy: dict[str, object],
    raw_output: str,
    sequence_count: int,
    raw_sha256: str | None = None,
) -> None:
    """Write a lower-engine capture fixture matching the LocalBackend schema."""
    spec = local_model_spec(model_id)
    assert spec is not None
    raw_bytes = raw_output.encode("utf-8")
    options = {
        name: generation_policy[name]
        for name in ("max_new_tokens", "do_sample", "temperature", "top_p")
    }
    for sequence in range(1, sequence_count + 1):
        directory = root / session_id / str(sequence)
        directory.mkdir(parents=True)
        prompt = f"private prompt {sequence}"
        prompt_bytes = prompt.encode("utf-8")
        (directory / "prompt.txt").write_bytes(prompt_bytes)
        (directory / "raw-output.txt").write_bytes(raw_bytes)
        (directory / "metadata.json").write_text(
            json.dumps(
                {
                    "model": {"id": spec.repo_id, "revision": spec.revision},
                    "options": options,
                    "session_id": session_id,
                    "sequence": sequence,
                    "prompt_bytes": len(prompt_bytes),
                    "prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
                    "raw_output_bytes": len(raw_bytes),
                    "raw_output_sha256": raw_sha256
                    or hashlib.sha256(raw_bytes).hexdigest(),
                    "status": "completed",
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )


def test_eval_config_uses_fixed_product_model_without_mutating_user_settings() -> None:
    user_config = LLMConfig(
        model_name="microsoft/Phi-4-mini-instruct",
        cache_dir="/tmp/xbrainlab-model-cache",
        device="cpu",
        local_model_enabled=False,
    )

    eval_config = _stable_eval_config(user_config, device="cuda")

    assert eval_config is user_config
    assert eval_config.model_name == LLMConfig.default_local_model_id()
    assert eval_config.cache_dir == "/tmp/xbrainlab-model-cache"
    assert eval_config.device == "cuda"
    assert eval_config.local_model_enabled is True
    assert eval_config.assistant_runtime_selection().backend_mode == "local"


def test_evaluator_default_positive_cases_are_script_owned_and_english() -> None:
    assert DEFAULT_CASES.resolve() == EVALUATOR_POSITIVE_CASES.resolve()
    assert DEFAULT_CASES.resolve() != RAGConfig.get_gold_set_path().resolve()

    fixture_bytes = DEFAULT_CASES.read_bytes()
    payload = json.loads(fixture_bytes)

    assert hashlib.sha256(fixture_bytes).hexdigest() == EVALUATOR_POSITIVE_CASES_SHA256
    assert len(payload) == 36
    assert all(item["input"].isascii() for item in payload)


def test_target_cases_cover_each_approved_tool_twice() -> None:
    cases = load_target_cases(DEFAULT_CASES)

    counts = {
        tool_name: sum(case.expected_tool == tool_name for case in cases)
        for tool_name in AGENT_ACTION_CONTRACTS.model_tool_names()
    }

    assert len(cases) == 36
    assert set(counts) == AGENT_ACTION_CONTRACTS.model_tool_names()
    assert set(counts.values()) == {2}


def test_evaluator_uses_product_tool_definitions_without_a_second_registry() -> None:
    actual = target_tool_registry().get_all_tools()
    expected = get_all_tools()

    assert [
        (
            type(tool),
            tool.name,
            tool.description,
            tool.parameters,
            tool.requires_confirmation,
        )
        for tool in actual
    ] == [
        (
            type(tool),
            tool.name,
            tool.description,
            tool.parameters,
            tool.requires_confirmation,
        )
        for tool in expected
    ]


def test_each_positive_case_is_callable_from_its_production_fixture() -> None:
    """The positive gate may not score a tool omitted by backend publication."""
    registry = target_tool_registry()

    for case in load_target_cases(DEFAULT_CASES):
        messages = build_case_messages(case, registry)

        assert f'"name": "{case.expected_tool}"' in messages[0]["content"]


def test_target_case_loader_rejects_duplicate_normalized_inputs(tmp_path: Path) -> None:
    payload = json.loads(DEFAULT_CASES.read_text(encoding="utf-8"))
    payload[1]["input"] = payload[0]["input"].upper()
    cases_path = tmp_path / "duplicate-input.json"
    cases_path.write_text(json.dumps(payload), encoding="utf-8")

    try:
        load_target_cases(cases_path)
    except ValueError as exc:
        assert "duplicates a normalized user input" in str(exc)
    else:  # pragma: no cover - assertion branch documents the required rejection
        raise AssertionError("Duplicate normalized inputs must be rejected.")


def test_challenge_cases_extend_positive_matrix_to_exact_50_case_gate() -> None:
    cases = load_challenge_cases(DEFAULT_CHALLENGES)

    assert len(cases) == 14
    assert len({case.case_id for case in cases}) == 14
    assert {case.category for case in cases} == {
        "ambiguous",
        "general",
        "missing_parameter",
        "multi_action",
        "out_of_stage",
    }
    assert len(load_target_cases(DEFAULT_CASES)) + len(cases) == 50


def test_precision_cases_cover_tools_and_english_no_action_categories() -> None:
    cases = load_precision_cases(DEFAULT_PRECISION_CASES)

    assert len(cases) == 24
    assert {case.requested_tool for case in cases if case.requested_tool} == (
        AGENT_ACTION_CONTRACTS.model_tool_names()
    )
    assert {case.category for case in cases} == {
        "ambiguous",
        "general",
        "missing_parameter",
        "multi_action",
        "negated",
        "out_of_stage",
    }
    assert sum(case.category == "general" for case in cases) == 2
    assert sum(case.category == "ambiguous" for case in cases) == 2
    assert sum(case.category == "multi_action" for case in cases) == 2


def test_clarification_cases_cover_each_direct_parameter_tool_once() -> None:
    precision_cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    cases = load_clarification_cases(
        DEFAULT_CLARIFICATION_CASES,
        precision_cases=precision_cases,
    )

    direct_cases = [case for case in cases if case.trajectory_kind == "direct"]
    assert len(cases) == 7
    assert {case.expected_tool for case in direct_cases} == {
        "apply_bandpass_filter",
        "apply_notch_filter",
        "resample_data",
        "set_reference",
        "normalize_data",
    }
    assert {case.source_case_id for case in direct_cases} == {
        case.case_id for case in precision_cases if case.category == "missing_parameter"
    }
    assert {
        case.trajectory_kind for case in cases if case.trajectory_kind != "direct"
    } == {
        "generic_filter_selection",
        "partial_bandpass_accumulation",
    }


def test_active_assistant_evidence_cases_are_english_only() -> None:
    precision_cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    clarification_cases = load_clarification_cases(
        DEFAULT_CLARIFICATION_CASES,
        precision_cases=precision_cases,
    )
    inputs = [
        *(case.user_input for case in load_target_cases(DEFAULT_CASES)),
        *(case.user_input for case in load_challenge_cases(DEFAULT_CHALLENGES)),
        *(case.user_input for case in precision_cases),
        *(case.reply for case in clarification_cases),
        *(turn for case in clarification_cases for turn in case.turns),
    ]

    assert all(text.isascii() for text in inputs)


def test_run_eval_admits_direct_receipts_from_full_final_response_not_score_preview(
    monkeypatch,
) -> None:
    long_question = "What resampling rate should I use? " + ("x" * 1_100)
    response = (
        '{"tool_name":"respond_to_user",'
        f'"parameters":{{"message":{json.dumps(long_question)},'
        '"pending_action":"resample_data","missing_inputs":["rate"]}}'
    )
    score = TargetEvalScore(
        False,
        "parameter_origin",
        response[:1_000],
        "respond_to_user",
        {"message": "Please provide the required value."},
        "Model-proposed parameters are not user-proven.",
    )
    trajectory = CaseTrajectoryResult(
        raw_score=score,
        post_recovery_score=score,
        final_score=score,
        final_response=response,
        attempts=(
            ModelGenerationAttempt(
                attempt_number=1,
                response_preview=response,
                envelope_status="no_tool",
                recovery_action="accept",
                taxonomy="respond",
                recovery_attempts_after=0,
            ),
        ),
    )
    direct_receipt_trajectory = CaseTrajectoryResult(
        raw_score=replace(score, passed=True, failure_type="none"),
        post_recovery_score=replace(score, passed=True, failure_type="none"),
        final_score=replace(score, passed=True, failure_type="none"),
        final_response="",
        attempts=(),
    )
    config = _stable_eval_config(LLMConfig(), device="cpu")
    monkeypatch.setattr(config, "local_backend_ready", lambda _model_id: True)
    precision_cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    clarification_cases = load_clarification_cases(
        DEFAULT_CLARIFICATION_CASES,
        precision_cases=precision_cases,
    )
    engine = MagicMock()

    with (
        patch(
            "scripts.dev.run_stable_assistant_model_eval.LLMEngine",
            return_value=engine,
        ),
        patch(
            "scripts.dev.run_stable_assistant_model_eval.evaluate_case_trajectory",
            return_value=trajectory,
        ),
        patch(
            "scripts.dev.run_stable_assistant_model_eval."
            "evaluate_clarification_trajectory",
            return_value=direct_receipt_trajectory,
        ),
        patch(
            "scripts.dev.run_stable_assistant_model_eval."
            "evaluate_discriminated_clarification_trajectory",
            return_value=trajectory,
        ),
        patch(
            "scripts.dev.run_stable_assistant_model_eval.admit_clarification_receipt",
            return_value=MagicMock(receipt_origin="host_parameter_origin"),
        ) as admit_receipt,
    ):
        report = run_eval(
            config,
            (),
            precision_cases=precision_cases,
            clarification_cases=clarification_cases,
        )

    assert len(admit_receipt.call_args_list) == 5
    assert {call.args[1] for call in admit_receipt.call_args_list} == {response}
    assert len(response) > 1_000
    direct_rows = [
        row
        for row in report["results"]
        if row["suite"] == "clarification" and row["source_case"] is not None
    ]
    assert len(direct_rows) == 5
    assert {row["receipt_admission"]["origin"] for row in direct_rows} == {
        "host_parameter_origin"
    }
    assert all(row["source_raw_model_score"]["passed"] is False for row in direct_rows)
    assert all(
        row["source_raw_model_score"] == row["first_generation_score"]
        for row in direct_rows
    )
    assert all(
        row["followup_model_generation"] == {"occurred": False, "attempt_count": 0}
        for row in direct_rows
    )
    assert response not in json.dumps(report)


def test_run_eval_records_every_lower_engine_generation_in_global_order(
    monkeypatch,
) -> None:
    """The report trace is runner-owned, not a reconstruction of policy attempts."""
    raw_response = ' {"decision":"reply","message":"I need more information.","mode":null,"action":null,"changes":{}}\n'
    config = _stable_eval_config(LLMConfig(), device="cpu")
    monkeypatch.setattr(config, "local_backend_ready", lambda _model_id: True)
    precision_cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    clarification_cases = load_clarification_cases(
        DEFAULT_CLARIFICATION_CASES,
        precision_cases=precision_cases,
    )
    engine = MagicMock()
    engine.generate_stream.side_effect = lambda *_args, **_kwargs: iter((raw_response,))

    with patch(
        "scripts.dev.run_stable_assistant_model_eval.LLMEngine",
        return_value=engine,
    ):
        report = run_eval(
            config,
            (),
            precision_cases=precision_cases,
            clarification_cases=clarification_cases,
        )

    trace = report["generation_trace"]
    assert report["generation_attempt_count"] == engine.generate_stream.call_count
    assert report["generation_attempt_count"] > len(precision_cases)
    assert [entry["global_call_index"] for entry in trace] == list(
        range(1, len(trace) + 1)
    )
    assert all(
        entry["raw_output_bytes"] == len(raw_response.encode("utf-8"))
        for entry in trace
    )
    assert all(
        entry["raw_output_sha256"]
        == hashlib.sha256(raw_response.encode("utf-8")).hexdigest()
        for entry in trace
    )
    for row in report["results"]:
        assert row["trajectory"]["actual_generation_call_indices"] == [
            entry["global_call_index"]
            for entry in trace
            if entry["case_id"] == row["case"]["case_id"]
        ]


def test_run_eval_without_capture_does_not_probe_capture_filesystem(
    monkeypatch,
) -> None:
    config = _stable_eval_config(LLMConfig(), device="cpu")
    monkeypatch.setattr(config, "local_backend_ready", lambda _model_id: True)
    monkeypatch.delenv("XBRAINLAB_ASSISTANT_PROMPT_CAPTURE_DIR", raising=False)
    precision_cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    clarification_cases = load_clarification_cases(
        DEFAULT_CLARIFICATION_CASES,
        precision_cases=precision_cases,
    )
    engine = MagicMock()
    engine.generate_stream.side_effect = lambda *_args, **_kwargs: iter(
        (
            '{"decision":"reply","message":"I need more information.","mode":null,"action":null,"changes":{}}',
        )
    )

    with (
        patch(
            "scripts.dev.run_stable_assistant_model_eval.LLMEngine",
            return_value=engine,
        ),
        patch(
            "scripts.dev.run_stable_assistant_model_eval.Path.exists",
            side_effect=AssertionError("capture path probe"),
        ),
        patch(
            "scripts.dev.run_stable_assistant_model_eval.Path.iterdir",
            side_effect=AssertionError("capture directory listing"),
        ),
    ):
        report = run_eval(
            config,
            (),
            precision_cases=precision_cases,
            clarification_cases=clarification_cases,
        )

    capture_integrity = report["candidate_gate"]["capture_integrity"]["evidence"]
    assert capture_integrity["requested"] is False
    assert capture_integrity["status"] == "not_requested"
    assert capture_integrity["failure_codes"] == []


def test_run_eval_validates_opt_in_capture_with_dynamic_trace_and_redacted_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    capture_root = tmp_path / "private-capture-root"
    (capture_root / "previous-session").mkdir(parents=True)
    monkeypatch.setenv("XBRAINLAB_ASSISTANT_PROMPT_CAPTURE_DIR", str(capture_root))
    config = _stable_eval_config(LLMConfig(), device="cpu")
    monkeypatch.setattr(config, "local_backend_ready", lambda _model_id: True)
    precision_cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    clarification_cases = load_clarification_cases(
        DEFAULT_CLARIFICATION_CASES,
        precision_cases=precision_cases,
    )
    raw_output = ' {"decision":"reply","message":"I need more information.","mode":null,"action":null,"changes":{}}\n'
    engine = MagicMock()
    engine.generate_stream.side_effect = lambda *_args, **_kwargs: iter((raw_output,))
    checkpoint_reports: list[dict[str, object]] = []

    def finish_capture() -> None:
        _write_runtime_capture_session(
            capture_root,
            "new-session",
            model_id=config.assistant_runtime_selection().model_id,
            generation_policy=_evaluation_generation_policy(config),
            raw_output=raw_output,
            sequence_count=engine.generate_stream.call_count,
        )

    engine.close.side_effect = finish_capture
    with (
        patch(
            "scripts.dev.run_stable_assistant_model_eval.LLMEngine",
            return_value=engine,
        ),
        patch(
            "scripts.dev.run_stable_assistant_model_eval._write_report",
            side_effect=lambda _path, payload: checkpoint_reports.append(payload),
        ),
    ):
        report = run_eval(
            config,
            (),
            precision_cases=precision_cases,
            clarification_cases=clarification_cases,
            checkpoint_path=tmp_path / "checkpoint.json",
        )

    audit = report["candidate_gate"]["capture_integrity"]["evidence"]
    assert audit["requested"] is True
    assert audit["status"] == "verified"
    assert audit["artifact_count"] == report["generation_attempt_count"]
    assert audit["session_id_sha256"] == hashlib.sha256(b"new-session").hexdigest()
    assert all(audit["checks"].values())
    assert audit["failure_codes"] == []
    rendered = json.dumps(audit)
    assert str(capture_root) not in rendered
    assert "previous-session" not in rendered
    assert "new-session" not in rendered
    assert "private prompt" not in rendered
    assert checkpoint_reports
    assert all(
        item["candidate_gate"]["capture_integrity"]["evidence"]
        == {
            "requested": True,
            "status": "incomplete",
            "artifact_count": 0,
            "session_id_sha256": None,
            "checks": {},
            "failure_codes": [],
        }
        for item in checkpoint_reports
    )


def test_run_eval_capture_mismatch_or_ambiguous_session_fails_candidate_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    capture_root = tmp_path / "private-capture-root"
    monkeypatch.setenv("XBRAINLAB_ASSISTANT_PROMPT_CAPTURE_DIR", str(capture_root))
    config = _stable_eval_config(LLMConfig(), device="cpu")
    monkeypatch.setattr(config, "local_backend_ready", lambda _model_id: True)
    precision_cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    clarification_cases = load_clarification_cases(
        DEFAULT_CLARIFICATION_CASES,
        precision_cases=precision_cases,
    )
    raw_output = '{"decision":"reply","message":"I need more information.","mode":null,"action":null,"changes":{}}'
    engine = MagicMock()
    engine.generate_stream.side_effect = lambda *_args, **_kwargs: iter((raw_output,))

    def finish_capture() -> None:
        kwargs = {
            "model_id": config.assistant_runtime_selection().model_id,
            "generation_policy": _evaluation_generation_policy(config),
            "raw_output": raw_output,
            "sequence_count": engine.generate_stream.call_count,
        }
        _write_runtime_capture_session(capture_root, "first-session", **kwargs)
        _write_runtime_capture_session(capture_root, "second-session", **kwargs)

    engine.close.side_effect = finish_capture
    with patch(
        "scripts.dev.run_stable_assistant_model_eval.LLMEngine",
        return_value=engine,
    ):
        report = run_eval(
            config,
            (),
            precision_cases=precision_cases,
            clarification_cases=clarification_cases,
        )

    audit = report["candidate_gate"]["capture_integrity"]["evidence"]
    assert audit["status"] == "failed"
    assert audit["failure_codes"] == ["new_session_ambiguity"]
    assert report["candidate_gate"]["capture_integrity"]["passed"] is False
    rendered = json.dumps(audit)
    assert str(capture_root) not in rendered
    assert "first-session" not in rendered
    assert "second-session" not in rendered


def test_capture_audit_reports_raw_hash_mismatch_without_disclosing_content(
    tmp_path: Path,
    monkeypatch,
) -> None:
    capture_root = tmp_path / "private-capture-root"
    monkeypatch.setenv("XBRAINLAB_ASSISTANT_PROMPT_CAPTURE_DIR", str(capture_root))
    request = _capture_audit_request()
    config = _stable_eval_config(LLMConfig(), device="cpu")
    raw_output = "private raw output"
    recorder = GenerationTraceRecorder()
    recorder.record(raw_output, case_id="case", turn_purpose="first_turn")
    _write_runtime_capture_session(
        capture_root,
        "new-session",
        model_id=config.assistant_runtime_selection().model_id,
        generation_policy=_evaluation_generation_policy(config),
        raw_output=raw_output,
        sequence_count=1,
        raw_sha256="0" * 64,
    )

    audit = _capture_integrity_report(
        request,
        recorder.entries,
        model_id=config.assistant_runtime_selection().model_id,
        generation_policy=_evaluation_generation_policy(config),
    )

    assert audit["status"] == "failed"
    assert "capture_content_hash_mismatch" in audit["failure_codes"]
    assert "capture_trace_raw_mismatch" in audit["failure_codes"]
    rendered = json.dumps(audit)
    assert str(capture_root) not in rendered
    assert raw_output not in rendered


def test_clarification_prompt_and_score_use_product_request_boundary() -> None:
    registry = target_tool_registry()
    sources = load_precision_cases(DEFAULT_PRECISION_CASES)
    case = next(
        item
        for item in load_clarification_cases(
            DEFAULT_CLARIFICATION_CASES,
            precision_cases=sources,
        )
        if item.expected_tool == "resample_data"
    )
    source = next(item for item in sources if item.case_id == case.source_case_id)
    admission = admit_clarification_receipt(
        source,
        json.dumps(
            {
                "decision": "clarify",
                "mode": "new_request",
                "action": "resample_data",
                "changes": {},
                "message": "What resampling rate should I use?",
            }
        ),
        expected_tool=case.expected_tool,
        registry=registry,
    )
    assert admission is not None
    generated = []

    def generate(messages):
        generated.append(messages)
        return json.dumps(
            {
                "decision": "execute",
                "message": None,
                "mode": "update_pending",
                "action": "resample_data",
                "changes": {
                    "rate": {"value": 128, "source_turn": "U2", "quote": "128 Hz"},
                },
            }
        )

    recorder = GenerationTraceRecorder()
    trajectory = evaluate_clarification_trajectory(
        case,
        source,
        admission=admission,
        registry=registry,
        generate_response=generate,
        generation_recorder=recorder,
    )
    assert len(generated) == len(recorder.entries) == 1
    assert json.loads(generated[0][-1]["content"])["current_user"] == {
        "id": "U2",
        "text": "128 Hz",
    }
    assert "pending_request" in str(generated[0])
    assert source.user_input in str(generated[0])
    assert trajectory.final_score.passed
    assert admission.harness._observed_decision.params == {"rate": 128}
    assert trajectory.product_terminal["execution_boundary_reached"]
    assert trajectory.product_terminal["execution_suppressed"]


def test_clarification_admission_rejects_incomplete_tool_call_fixture() -> None:
    registry = target_tool_registry()
    source = next(
        case
        for case in load_precision_cases(DEFAULT_PRECISION_CASES)
        if case.case_id == "missing_resample_en"
    )

    admission = admit_clarification_receipt(
        source,
        (
            '{"decision":"execute","message":null,"mode":"new_request","action":"resample_data","changes":{}}'
        ),
        expected_tool="resample_data",
        registry=registry,
    )

    assert admission is None


def test_clarification_admission_never_synthesizes_requests_from_guessed_values() -> (
    None
):
    registry = target_tool_registry()
    cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    invented_parameters = {
        "apply_bandpass_filter": {"low_freq": 1, "high_freq": 40},
        "apply_notch_filter": {"freq": 50},
        "resample_data": {"rate": 128},
        "set_reference": {"method": "average"},
        "normalize_data": {"method": "z-score"},
    }

    for source in (case for case in cases if case.category == "missing_parameter"):
        response = _model_response(
            source.requested_tool, invented_parameters[source.requested_tool]
        )
        admission = admit_clarification_receipt(
            source,
            response,
            expected_tool=source.requested_tool,
            registry=registry,
        )

        assert admission is None


def test_clarification_admission_keeps_model_typed_origin_and_never_synthesizes() -> (
    None
):
    registry = target_tool_registry()
    source = next(
        case
        for case in load_precision_cases(DEFAULT_PRECISION_CASES)
        if case.case_id == "missing_resample_en"
    )
    typed = '{"decision":"clarify","message":"What resampling rate should I use?","mode":"new_request","action":"resample_data","changes":{}}'

    admission = admit_clarification_receipt(
        source, typed, expected_tool="resample_data", registry=registry
    )
    missing = admit_clarification_receipt(
        source,
        '{"decision":"execute","message":null,"mode":"new_request","action":"resample_data","changes":{}}',
        expected_tool="resample_data",
        registry=registry,
    )

    assert admission is not None
    assert admission.receipt_origin == "model_typed"
    assert missing is None


def test_clarification_admission_accepts_a_long_legal_typed_response() -> None:
    registry = target_tool_registry()
    source = next(
        item
        for item in load_precision_cases(DEFAULT_PRECISION_CASES)
        if item.case_id == "missing_resample_en"
    )
    response = _model_response(
        "respond_to_user",
        {
            "message": "rate? " + "x" * 1_100,
            "pending_action": "resample_data",
        },
    )

    admission = admit_clarification_receipt(
        source,
        response,
        expected_tool="resample_data",
        registry=registry,
    )

    assert len(response) > 1_000
    assert admission is not None
    assert admission.receipt.command_name == "resample_data"


@pytest.mark.parametrize("malformed", [False, True])
def test_clarification_records_actual_followup_and_recovery_generations(
    malformed,
) -> None:
    registry, source, case, admission = _resample_clarification_fixture()
    valid = _model_response("resample_data", {"rate": 128}, turn="U2", mode="continue")
    responses = iter(["broken JSON", valid] if malformed else [valid])
    recorder = GenerationTraceRecorder()
    result = evaluate_clarification_trajectory(
        case,
        source,
        admission=admission,
        registry=registry,
        generate_response=lambda messages: next(responses),
        generation_recorder=recorder,
    )
    assert len(recorder.entries) == (2 if malformed else 1)
    assert result.raw_score.passed is (not malformed)
    assert result.final_score.passed
    assert [entry.turn_purpose for entry in recorder.entries] == (
        ["clarification_proposal", "format_retry"]
        if malformed
        else ["clarification_proposal"]
    )


def _resample_clarification_fixture():
    registry = target_tool_registry()
    sources = load_precision_cases(DEFAULT_PRECISION_CASES)
    case = next(
        item
        for item in load_clarification_cases(
            DEFAULT_CLARIFICATION_CASES,
            precision_cases=sources,
        )
        if item.expected_tool == "resample_data"
    )
    source = next(item for item in sources if item.case_id == case.source_case_id)
    admission = admit_clarification_receipt(
        source,
        _model_response(
            "respond_to_user",
            {
                "message": "What resampling rate should I use?",
                "pending_action": "resample_data",
            },
        ),
        expected_tool=case.expected_tool,
        registry=registry,
    )
    assert admission is not None
    return registry, source, case, admission


def test_first_turn_invalid_typed_precision_rows_replay_controller_recovery() -> None:
    registry = target_tool_registry()
    cases = {
        case.case_id: case for case in load_precision_cases(DEFAULT_PRECISION_CASES)
    }
    scenarios = (
        (
            "set_montage_after_epochs_en",
            "set_montage",
            "montage_name",
            "I can't set a montage after EEG epochs have been created.",
        ),
        (
            "split_before_epochs_en",
            "configure_dataset_split",
            "test_size",
            "I can't configure a dataset split until EEG epochs are available.",
        ),
    )

    for case_id, pending_action, missing_input, safe_message in scenarios:
        case = cases[case_id]
        invalid_typed = (
            f'{{"tool_name":"respond_to_user",'
            f'"parameters":{{"message":"I need one value first.",'
            f'"pending_action":"{pending_action}",'
            f'"missing_inputs":["{missing_input}"]}}}}'
        )
        repaired = _model_response("respond_to_user", {"message": safe_message})
        responses = iter((invalid_typed, repaired))
        generated_messages: list[list[dict[str, str]]] = []
        recorder = GenerationTraceRecorder()

        def generate(
            messages: list[dict[str, str]],
            _responses: Iterator[str] = responses,
            _generated_messages: list[list[dict[str, str]]] = generated_messages,
        ) -> str:
            _generated_messages.append(messages)
            return next(_responses)

        trajectory = evaluate_case_trajectory(
            case,
            registry,
            generate,
            generation_recorder=recorder,
        )

        assert trajectory.attempts[0].recovery_action == "retry_format"
        assert [entry.turn_purpose for entry in recorder.entries] == [
            "first_turn",
            "format_retry",
        ]
        assert any(
            "FORMAT CORRECTION REQUIRED" in message["content"]
            for message in generated_messages[1]
        )
        assert trajectory.final_score.passed is True
        assert trajectory.host_admission is not None
        assert trajectory.product_terminal is not None
        assert trajectory.product_terminal["kind"] == "respond"
        assert trajectory.product_terminal["confirmation_observed"] is False
        assert trajectory.product_terminal["execution_boundary_reached"] is False
        assert trajectory.product_terminal["gui_handoff_reached"] is False
        assert trajectory.product_terminal["application_service_called"] is False
        assert trajectory.product_terminal["tool_executor_called"] is False
        assert trajectory.product_terminal["state_mutation_observed"] is False


def test_first_turn_invalid_typed_precision_exhaustion_has_failure_type() -> None:
    registry = target_tool_registry()
    case = next(
        item
        for item in load_precision_cases(DEFAULT_PRECISION_CASES)
        if item.case_id == "set_montage_after_epochs_en"
    )
    invalid_typed = '{"decision":"clarify","request":{},"message":"Need a value"}'

    recorder = GenerationTraceRecorder()
    trajectory = evaluate_case_trajectory(
        case,
        registry,
        lambda _messages: invalid_typed,
        generation_recorder=recorder,
    )

    assert len(trajectory.attempts) == (
        DEFAULT_STRICT_ENVELOPE_RECOVERY_POLICY.max_recovery_attempts + 1
    )
    assert trajectory.attempts[-1].recovery_action == "exhausted"
    assert trajectory.final_score.passed is False
    assert trajectory.final_score.failure_type != "none"
    assert trajectory.product_terminal is not None
    assert trajectory.product_terminal["kind"] == "format_recovery_exhausted"
    assert trajectory.product_terminal["confirmation_observed"] is False
    assert trajectory.product_terminal["execution_boundary_reached"] is False
    assert trajectory.product_terminal["gui_handoff_reached"] is False
    assert trajectory.product_terminal["application_service_called"] is False
    assert trajectory.product_terminal["tool_executor_called"] is False
    assert trajectory.product_terminal["state_mutation_observed"] is False
    assert [entry.turn_purpose for entry in recorder.entries] == [
        "first_turn",
        *(
            ["format_retry"]
            * DEFAULT_STRICT_ENVELOPE_RECOVERY_POLICY.max_recovery_attempts
        ),
    ]


def test_explicit_clarification_cancellation_uses_model_and_clears_request() -> None:
    registry, source, case, admission = _resample_clarification_fixture()
    recorder = GenerationTraceRecorder()
    generate = MagicMock(
        return_value=json.dumps(
            {
                "decision": "reply",
                "mode": "cancel_pending",
                "action": None,
                "changes": {},
                "message": "The pending request is cancelled.",
            }
        )
    )
    result = evaluate_clarification_trajectory(
        replace(case, reply="cancel"),
        source,
        admission=admission,
        registry=registry,
        generate_response=generate,
        generation_recorder=recorder,
    )
    generate.assert_called_once()
    assert len(recorder.entries) == 1
    assert admission.harness.pending_interactions.request is None
    assert not result.final_score.passed  # Original case oracle requires execution.
    assert not result.product_terminal["execution_boundary_reached"]


def test_synthetic_clarification_continuation_passes_messages_to_generator() -> None:
    registry = target_tool_registry()
    precision_cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    case = next(
        item
        for item in load_clarification_cases(
            DEFAULT_CLARIFICATION_CASES,
            precision_cases=precision_cases,
        )
        if item.expected_tool == "resample_data"
    )
    source = next(
        item for item in precision_cases if item.case_id == case.source_case_id
    )
    first_response = '{"decision":"clarify","message":"What resampling rate should I use?","mode":"new_request","action":"resample_data","changes":{}}'
    admission = admit_clarification_receipt(
        source,
        first_response,
        expected_tool=case.expected_tool,
        registry=registry,
    )
    assert admission is not None
    received: list[list[dict[str, str]]] = []

    trajectory = evaluate_clarification_trajectory(
        replace(case, reply="I do not know the rate."),
        source,
        admission=admission,
        registry=registry,
        generate_response=lambda messages: (
            received.append(messages)
            or '{"decision":"reply","message":"Please provide the resampling rate.","mode":null,"action":null,"changes":{}}'
        ),
    )

    assert received and isinstance(received[0], list)
    assert (
        json.loads(received[0][-1]["content"])["current_user"]["text"]
        == "I do not know the rate."
    )
    assert trajectory.attempts


@pytest.mark.parametrize(
    "kind", ["generic_filter_selection", "partial_bandpass_accumulation"]
)
@pytest.mark.parametrize("invalid_final_source", [False, True])
def test_discriminated_clarification_trajectories_use_each_actual_user_turn(
    kind,
    invalid_final_source,
) -> None:
    registry = target_tool_registry()
    sources = load_precision_cases(DEFAULT_PRECISION_CASES)
    case = next(
        item
        for item in load_clarification_cases(
            DEFAULT_CLARIFICATION_CASES,
            precision_cases=sources,
        )
        if item.trajectory_kind == kind
    )
    generic = kind == "generic_filter_selection"
    responses = [
        json.dumps(
            {
                "decision": "clarify",
                "mode": "new_request",
                "action": None if generic else case.expected_tool,
                "changes": {},
                "message": "Which filter?" if generic else "What lower cutoff?",
            }
        ),
        json.dumps(
            {
                "decision": "clarify",
                "mode": "update_pending",
                "action": case.expected_tool,
                "changes": {}
                if generic
                else {"low_freq": {"value": 12, "source_turn": "U2", "quote": "12 Hz"}},
                "message": "What low and high cutoffs?"
                if generic
                else "What upper cutoff?",
            }
        ),
        _model_response(
            case.expected_tool,
            case.expected_parameters if generic else {"high_freq": 128},
            turn="U9" if invalid_final_source else "U3",
            mode="continue",
        ),
    ]
    generated = []

    def generate(messages):
        generated.append(messages)
        return responses[len(generated) - 1]

    recorder = GenerationTraceRecorder()
    rag = _ProductRAGCaseMessages(registry, _ImmediateProductRAGLifecycle(""))
    result = evaluate_discriminated_clarification_trajectory(
        case,
        registry,
        generate,
        generation_recorder=recorder,
        product_rag_messages=rag,
    )
    assert result.final_score.passed is not invalid_final_source
    assert len(result.attempts) == len(recorder.entries) == 3
    assert [
        json.loads(messages[-1]["content"])["current_user"]["text"]
        for messages in generated
    ] == list(case.turns)
    assert [
        json.loads(messages[-1]["content"])["current_user"]["id"]
        for messages in generated
    ] == ["U1", "U2", "U3"]
    assert len(rag.evidence_for_case(case.case_id)) == 3
    assert (
        result.product_terminal["execution_boundary_reached"]
        is not invalid_final_source
    )
    assert [turn["user_turn_id"] for turn in result.turn_observations] == [
        "U1",
        "U2",
        "U3",
    ]
    updates = [
        turn["host_admission"]["request_update"] for turn in result.turn_observations
    ]
    assert all(update["accepted"] for update in updates[:2])
    assert updates[0]["parameters"] == {}
    assert updates[1]["parameters"] == ({} if generic else {"low_freq": 12})
    if invalid_final_source:
        assert updates[2]["accepted"] is False
        assert updates[2]["error"]
        assert result.turn_observations[2]["raw_score"]["passed"]
        assert not result.turn_observations[2]["product_score"]["passed"]
    else:
        assert updates[2]["accepted"]
        assert updates[2]["parameters"] == case.expected_parameters
    if not generic:
        draft = json.loads(generated[-1][-1]["content"])["pending_request"]
        assert draft["parameters"]["low_freq"]["value"] == 12
        assert draft["user_sources"]["U2"] == "12 Hz"


def test_discriminated_clarification_does_not_continue_after_unexpected_execution() -> (
    None
):
    registry = target_tool_registry()
    sources = load_precision_cases(DEFAULT_PRECISION_CASES)
    case = next(
        item
        for item in load_clarification_cases(
            DEFAULT_CLARIFICATION_CASES,
            precision_cases=sources,
        )
        if item.trajectory_kind == "generic_filter_selection"
    )
    generate = MagicMock(
        return_value=_model_response(
            "apply_bandpass_filter", {"low_freq": 12, "high_freq": 40}
        )
    )
    result = evaluate_discriminated_clarification_trajectory(case, registry, generate)
    assert not result.final_score.passed
    generate.assert_called_once()


def test_generation_trace_preserves_pre_strip_raw_identity_and_bounds_preview() -> None:
    registry = target_tool_registry()
    case = next(
        item
        for item in load_precision_cases(DEFAULT_PRECISION_CASES)
        if item.case_id == "general_en"
    )
    raw_response = (
        " \n" + _model_response("respond_to_user", {"message": "x" * 1_100}) + "\n"
    )
    recorder = GenerationTraceRecorder()

    trajectory = evaluate_case_trajectory(
        case,
        registry,
        lambda _messages: raw_response,
        generation_recorder=recorder,
        trace_case_id=case.case_id,
    )

    assert trajectory.final_score.passed is True
    assert trajectory.final_response == raw_response.strip()
    assert len(recorder.entries) == 1
    entry = recorder.entries[0]
    assert entry.global_call_index == 1
    assert entry.case_id == case.case_id
    assert entry.turn_purpose == "first_turn"
    assert entry.raw_output_bytes == len(raw_response.encode("utf-8"))
    assert (
        entry.raw_output_sha256
        == hashlib.sha256(raw_response.encode("utf-8")).hexdigest()
    )
    assert entry.raw_output_preview == raw_response[:1_000]
    assert entry.raw_output_preview != trajectory.final_response[:1_000]
    assert trajectory.attempts[0].response_preview == trajectory.final_response[:1_000]


def test_generation_trace_records_each_format_retry_in_order() -> None:
    registry = target_tool_registry()
    case = next(
        item
        for item in load_precision_cases(DEFAULT_PRECISION_CASES)
        if item.case_id == "general_en"
    )
    responses = iter(
        (
            '{"tool_name":"respond_to_user",',
            (
                '{"decision":"reply","message":"I can explain the EEG workflow.","mode":null,"action":null,"changes":{}}'
            ),
        )
    )
    recorder = GenerationTraceRecorder()

    trajectory = evaluate_case_trajectory(
        case,
        registry,
        lambda _messages: next(responses),
        generation_recorder=recorder,
        trace_case_id=case.case_id,
    )

    assert trajectory.final_score.passed is True
    assert [entry.global_call_index for entry in recorder.entries] == [1, 2]
    assert [entry.turn_purpose for entry in recorder.entries] == [
        "first_turn",
        "format_retry",
    ]
    assert [entry.raw_output_sha256 for entry in recorder.entries] == [
        hashlib.sha256(response.encode("utf-8")).hexdigest()
        for response in (
            '{"tool_name":"respond_to_user",',
            (
                '{"decision":"reply","message":"I can explain the EEG workflow.","mode":null,"action":null,"changes":{}}'
            ),
        )
    ]


def test_trajectory_payload_separates_policy_from_actual_generation_calls() -> None:
    recorder = GenerationTraceRecorder()
    recorder.record("first", case_id="case", turn_purpose="first_turn")
    recorder.record("partial", case_id="case", turn_purpose="partial_reply")
    attempts = (
        ModelGenerationAttempt(
            attempt_number=1,
            response_preview="first",
            envelope_status="valid",
            recovery_action="accept_tool",
            taxonomy="first_attempt_tool",
            recovery_attempts_after=0,
        ),
    )

    payload = _trajectory_payload(attempts, recorder, case_id="case")

    assert set(payload) == {
        "policy_attempts",
        "format_recovery_attempts",
        "policy_terminal_action",
        "policy_terminal_taxonomy",
        "actual_generation_call_indices",
    }
    assert payload["actual_generation_call_indices"] == [1, 2]
    assert len(payload["policy_attempts"]) == 1
    assert payload["format_recovery_attempts"] == 0


def test_partial_bandpass_does_not_report_success_after_unresolved_first_turn() -> None:
    registry = target_tool_registry()
    sources = load_precision_cases(DEFAULT_PRECISION_CASES)
    case = next(
        item
        for item in load_clarification_cases(
            DEFAULT_CLARIFICATION_CASES,
            precision_cases=sources,
        )
        if item.trajectory_kind == "partial_bandpass_accumulation"
    )
    response = _model_response(
        "respond_to_user", {"message": "I cannot interpret this reply."}
    )
    generate = MagicMock(return_value=response)
    result = evaluate_discriminated_clarification_trajectory(case, registry, generate)
    assert not result.final_score.passed
    assert not result.product_terminal["execution_boundary_reached"]


def test_precision_scoring_uses_parser_and_host_attempt_outcome_not_keywords() -> None:
    registry = target_tool_registry()
    cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    missing = next(case for case in cases if case.case_id == "missing_bandpass_en")
    out_of_stage = next(
        case for case in cases if case.case_id == "start_before_setup_en"
    )
    general = next(case for case in cases if case.case_id == "general_en")

    direct_response = '{"decision":"reply","message":"Please provide the cutoff values.","mode":null,"action":null,"changes":{}}'
    false_completion = '{"decision":"reply","message":"The filter has been completed.","mode":null,"action":null,"changes":{}}'
    placeholder_response = '{"decision":"reply","message":"<concise response or one clarifying question>","mode":null,"action":null,"changes":{}}'
    model_default = '{"decision":"execute","message":null,"mode":"new_request","action":"apply_bandpass_filter","changes":{"low_freq":{"value":0.5,"source_turn":"U1","quote":"0.5"},"high_freq":{"value":45,"source_turn":"U1","quote":"45"}}}'
    blocked_start = '{"decision":"execute","message":null,"mode":"new_request","action":"start_training","changes":{}}'
    accidental_navigation = '{"decision":"execute","message":null,"mode":"new_request","action":"switch_panel","changes":{"panel_name":{"value":"training","source_turn":"U1","quote":"training"}}}'
    retired_stage_echo = (
        '{"workflow_stage":"data_loaded","tool_name":"start_training","parameters":{}}'
    )

    direct_score = score_precision_response(missing, direct_response, registry)
    guarded_score = score_precision_response(missing, model_default, registry)
    blocked_score = score_precision_response(out_of_stage, blocked_start, registry)

    assert direct_score.passed is True
    assert score_precision_response(missing, false_completion, registry).passed is False
    assert (
        score_precision_response(missing, placeholder_response, registry).passed
        is False
    )
    assert guarded_score.passed is True
    assert blocked_score.passed is True
    assert (
        score_precision_response(general, accidental_navigation, registry).passed
        is False
    )
    assert (
        score_precision_response(out_of_stage, retired_stage_echo, registry).passed
        is False
    )
    assert direct_score.product_outcome is not None
    assert direct_score.product_outcome.disposition == "respond"
    assert guarded_score.product_outcome is not None
    assert guarded_score.product_outcome.disposition == "respond"
    assert guarded_score.product_outcome.message
    assert blocked_score.product_outcome is not None
    assert blocked_score.product_outcome.disposition == "blocked"
    assert blocked_score.product_outcome.message
    for score in (direct_score, guarded_score, blocked_score):
        outcome = score.product_outcome
        assert outcome is not None
        assert outcome.confirmation_requested is False
        assert outcome.gui_handoff_permitted is False
        assert outcome.application_service_permitted is False
        assert outcome.tool_executor_permitted is False
        assert outcome.state_mutation_permitted is False


def test_multi_object_precision_uses_choose_one_without_retry_or_side_effect() -> None:
    registry = target_tool_registry()
    case = next(
        item
        for item in load_precision_cases(DEFAULT_PRECISION_CASES)
        if item.case_id == "multi_en"
    )
    response = (
        '{"tool_name":"apply_bandpass_filter",'
        '"parameters":{"low_freq":4,"high_freq":38}}'
        '{"tool_name":"resample_data",'
        '"parameters":{"rate":128}}'
    )
    calls = 0

    def generate(_messages: list[dict[str, str]]) -> str:
        nonlocal calls
        calls += 1
        return response

    trajectory = evaluate_case_trajectory(case, registry, generate)

    assert calls == 1
    assert trajectory.raw_score.passed is False
    assert trajectory.final_score.passed is True
    assert trajectory.attempts[0].envelope_status == "multiple_objects"
    assert trajectory.attempts[0].recovery_action == "choose_one"
    outcome = trajectory.final_score.product_outcome
    assert outcome is not None
    assert outcome.disposition == "choose_one"
    assert trajectory.product_terminal is not None
    assert trajectory.product_terminal["kind"] == "choose_one"
    assert outcome.message == (
        "I can do one action at a time. Please tell me which action to do first."
    )
    assert outcome.confirmation_requested is False
    assert outcome.gui_handoff_permitted is False
    assert outcome.application_service_permitted is False
    assert outcome.tool_executor_permitted is False
    assert outcome.state_mutation_permitted is False


def test_import_precision_score_does_not_restore_host_intent_rescue() -> None:
    registry = target_tool_registry()
    cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    negated_import = next(item for item in cases if item.case_id == "negated_import_en")
    epochs_before_data = next(
        item for item in cases if item.case_id == "epochs_before_data_en"
    )
    import_response = '{"decision":"execute","message":null,"mode":"new_request","action":"import_eeg_data","changes":{}}'

    product_score = score_precision_response(
        negated_import,
        import_response,
        registry,
    )

    assert (
        score_raw_precision_response(
            negated_import,
            import_response,
            registry,
        ).passed
        is False
    )
    assert product_score.passed is False
    assert product_score.product_outcome is not None
    assert product_score.product_outcome.disposition == "execute"
    assert product_score.product_outcome.confirmation_requested is False
    assert product_score.product_outcome.gui_handoff_permitted is True
    assert product_score.product_outcome.application_service_permitted is True
    assert product_score.product_outcome.tool_executor_permitted is True
    assert product_score.product_outcome.state_mutation_permitted is True
    assert (
        score_precision_response(epochs_before_data, import_response, registry).passed
        is False
    )


def test_raw_missing_parameter_score_requires_the_exact_missing_fields() -> None:
    registry = target_tool_registry()
    case = next(
        item
        for item in load_precision_cases(DEFAULT_PRECISION_CASES)
        if item.case_id == "missing_bandpass_en"
    )
    incomplete_question = '{"decision":"reply","message":"Which bandpass filter should I apply?","mode":null,"action":null,"changes":{}}'
    exact_question = '{"decision":"reply","message":"What low and high bandpass cutoffs should I use?","mode":null,"action":null,"changes":{}}'
    invented_default = '{"decision":"execute","message":null,"mode":"new_request","action":"apply_bandpass_filter","changes":{"low_freq":{"value":1,"source_turn":"U1","quote":"1"},"high_freq":{"value":40,"source_turn":"U1","quote":"40"}}}'

    assert (
        score_raw_precision_response(case, incomplete_question, registry).passed
        is False
    )
    assert score_raw_precision_response(case, exact_question, registry).passed is True
    assert score_precision_response(case, invented_default, registry).passed is True
    assert (
        score_raw_precision_response(case, invented_default, registry).passed is False
    )


def test_raw_model_gate_keeps_challenge_diagnostics_out_of_its_pass_decision() -> None:
    results = [
        {
            "suite": "positive",
            "score": {"passed": True},
            "first_generation_score": {"passed": True, "failure_type": "none"},
        }
        for _ in range(36)
    ]
    results.extend(
        {
            "suite": "challenge",
            "score": {"passed": False},
            "first_generation_score": {
                "passed": index >= 4,
                "failure_type": "response_content" if index < 4 else "none",
            },
        }
        for index in range(14)
    )

    report = _build_report(
        model_id="ibm-granite/granite-4.0-micro",
        results=results,
        expected_case_count=50,
        complete=True,
    )

    assert report["candidate_gate"]["raw_model"]["challenge_decision"] == {
        "required": 14,
        "critical_failures": 0,
        "wording_failures": 4,
        "max_wording_failures": 3,
        "unclassified_failures": 0,
    }
    assert report["candidate_gate"]["raw_model"]["passed"] is True


def test_format_recovery_never_repairs_the_first_generation_raw_model_gate() -> None:
    results = [
        {
            "suite": "positive",
            "score": {"passed": True},
            "first_generation_score": {"passed": True, "failure_type": "none"},
            "post_recovery_score": {"passed": True, "failure_type": "none"},
            **(
                {"parameter_origin_guard": {"applicable": True, "passed": True}}
                if index < 10
                else {}
            ),
        }
        for index in range(36)
    ]
    results.extend(
        {
            "suite": "challenge",
            "score": {"passed": False},
            "first_generation_score": {"passed": True, "failure_type": "none"},
            "post_recovery_score": {"passed": True, "failure_type": "none"},
            **(
                {"host_guard": {"applicable": True, "passed": True}}
                if index < 5
                else {}
            ),
        }
        for index in range(14)
    )
    results.extend(
        {
            "suite": "precision",
            "score": {"passed": True},
            "first_generation_score": {"passed": True, "failure_type": "none"},
            "post_recovery_score": {"passed": True, "failure_type": "none"},
        }
        for _ in range(24)
    )
    results.extend(
        {
            "suite": "clarification",
            "score": {"passed": True},
            "first_generation_score": {
                "passed": index != 0,
                "failure_type": "none" if index else "output_format",
            },
            "post_recovery_score": {"passed": True, "failure_type": "none"},
        }
        for index in range(7)
    )

    report = _build_report(
        model_id="ibm-granite/granite-4.0-micro",
        results=results,
        expected_case_count=50,
        complete=True,
    )

    assert report["first_generation_summary"]["clarification"] == {
        "case_count": 7,
        "passed_count": 6,
        "failed_count": 1,
    }
    assert report["post_recovery_summary"]["clarification"]["passed_count"] == 7
    assert report["candidate_gate"]["raw_model"]["clarification_continuation"] == {
        "required": 7,
        "passed": 6,
    }
    assert report["candidate_gate"]["raw_model"]["passed"] is True


def test_trajectory_retries_format_error_with_product_policy_and_scores_final() -> None:
    registry = target_tool_registry()
    case = next(
        case
        for case in load_precision_cases(DEFAULT_PRECISION_CASES)
        if case.case_id == "general_en"
    )
    responses = iter(
        (
            '{"tool_name":"respond_to_user",',
            (
                '{"decision":"reply","message":"I can explain the EEG workflow; which part would you like to understand?","mode":null,"action":null,"changes":{}}'
            ),
        )
    )
    generated_messages: list[list[dict[str, str]]] = []

    def generate(messages: list[dict[str, str]]) -> str:
        generated_messages.append(messages)
        return next(responses)

    trajectory = evaluate_case_trajectory(case, registry, generate)

    assert trajectory.raw_score.passed is False
    assert trajectory.post_recovery_score.passed is True
    assert trajectory.final_score.passed is True
    assert json.loads(trajectory.final_response)["decision"] == "reply"
    assert [attempt.recovery_action for attempt in trajectory.attempts] == [
        "retry_format",
        "accept_no_tool",
    ]
    assert [attempt.taxonomy for attempt in trajectory.attempts] == [
        "format_error_retry",
        "recovered_plain_text",
    ]
    assert len(generated_messages) == 2
    assert "FORMAT CORRECTION REQUIRED" in generated_messages[1][0]["content"]
    assert "FORMAT CORRECTION REQUIRED" not in generated_messages[1][1]["content"]
    assert json.loads(generated_messages[1][-1]["content"])["current_user"] == {
        "id": "U1",
        "text": case.user_input,
    }


def test_trajectory_exhaustion_is_visible_safe_failure_after_one_repair() -> None:
    registry = target_tool_registry()
    case = next(
        case
        for case in load_precision_cases(DEFAULT_PRECISION_CASES)
        if case.case_id == "multi_en"
    )
    generated_messages: list[list[dict[str, str]]] = []

    def generate(messages: list[dict[str, str]]) -> str:
        generated_messages.append(messages)
        return "not one JSON object"

    trajectory = evaluate_case_trajectory(case, registry, generate)

    assert trajectory.raw_score.passed is False
    assert trajectory.final_score.passed is False
    assert trajectory.final_score.failure_type == "output_format"
    assert len(generated_messages) == 2
    assert generated_messages[1][0]["content"].count("FORMAT CORRECTION REQUIRED") == 1
    assert "FORMAT CORRECTION REQUIRED" not in generated_messages[1][1]["content"]
    assert [attempt.recovery_action for attempt in trajectory.attempts] == [
        "retry_format",
        "exhausted",
    ]
    outcome = trajectory.final_score.product_outcome
    assert outcome is not None
    assert outcome.disposition == "format_recovery_exhausted"
    assert trajectory.product_terminal is not None
    assert trajectory.product_terminal["kind"] == "format_recovery_exhausted"
    assert outcome.message
    assert outcome.confirmation_requested is False
    assert outcome.gui_handoff_permitted is False
    assert outcome.application_service_permitted is False
    assert outcome.tool_executor_permitted is False
    assert outcome.state_mutation_permitted is False


def test_trajectory_retries_retired_three_field_envelope_like_product_controller() -> (
    None
):
    registry = target_tool_registry()
    case = next(
        case
        for case in load_precision_cases(DEFAULT_PRECISION_CASES)
        if case.case_id == "general_en"
    )
    responses = iter(
        (
            (
                '{"workflow_stage":"empty","tool_name":"respond_to_user",'
                '"parameters":{"message":"How can I help?"}}'
            ),
            (
                '{"decision":"reply","message":"How can I help with your EEG workflow?","mode":null,"action":null,"changes":{}}'
            ),
        )
    )

    trajectory = evaluate_case_trajectory(
        case,
        registry,
        lambda _messages: next(responses),
    )

    assert trajectory.raw_score.failure_type == "output_format"
    assert trajectory.final_score.passed is True
    assert not hasattr(trajectory.attempts[0], "workflow_stage")
    assert trajectory.attempts[0].envelope_status == "format_error"
    assert trajectory.attempts[0].recovery_action == "retry_format"


def test_trajectory_does_not_turn_recovered_unsafe_action_into_a_pass() -> None:
    registry = target_tool_registry()
    case = next(
        case
        for case in load_precision_cases(DEFAULT_PRECISION_CASES)
        if case.case_id == "general_en"
    )
    responses = iter(
        (
            "not one JSON object",
            (
                '{"decision":"execute","message":null,"mode":"new_request","action":"switch_panel","changes":{"panel_name":{"value":"training","source_turn":"U1","quote":"training"}}}'
            ),
        )
    )

    trajectory = evaluate_case_trajectory(
        case,
        registry,
        lambda _messages: next(responses),
    )

    assert trajectory.raw_score.passed is False
    assert trajectory.final_score.passed is False
    assert trajectory.final_score.parsed_tool == "switch_panel"
    assert trajectory.final_score.product_outcome is not None
    assert trajectory.final_score.product_outcome.disposition in {
        "respond",
    }
    assert trajectory.product_terminal["execution_boundary_reached"] is False


def test_evaluation_uses_product_structured_generation_budget_not_legacy_128_cap() -> (
    None
):
    config = LLMConfig(max_new_tokens=384, do_sample=True)

    policy = _evaluation_generation_policy(config)

    assert policy == {
        "profile": "structured_decision",
        "max_new_tokens": 384,
        "do_sample": False,
        "temperature": None,
        "top_p": None,
        "max_format_recovery_attempts": 1,
    }

    config.max_new_tokens = 1_024
    assert _evaluation_generation_policy(config)["max_new_tokens"] == 512


def test_report_separates_raw_model_host_safety_and_product_outcomes() -> None:
    core_results = (
        [
            {
                "suite": "positive",
                "score": {"passed": True},
                "first_generation_score": {"passed": True, "failure_type": "none"},
                **(
                    {"parameter_origin_guard": {"applicable": True, "passed": True}}
                    if index < 10
                    else {}
                ),
            }
            for index in range(36)
        ]
        + [
            {
                "suite": "challenge",
                "score": {"passed": False},
                "first_generation_score": {"passed": True, "failure_type": "none"},
                "host_guard": {"applicable": True, "passed": True},
            }
            for _ in range(5)
        ]
        + [
            {
                "suite": "challenge",
                "score": {"passed": False},
                "first_generation_score": {"passed": True, "failure_type": "none"},
            }
            for _ in range(9)
        ]
    )
    report = _build_report(
        model_id="ibm-granite/granite-3.3-2b-instruct",
        results=[
            *core_results,
            *[
                {
                    "suite": "precision",
                    "first_generation_score": {"passed": True, "failure_type": "none"},
                    "score": {"passed": True},
                }
                for index in range(24)
            ],
            *[
                {
                    "suite": "clarification",
                    "first_generation_score": {"passed": True, "failure_type": "none"},
                    "score": {"passed": True},
                    **(
                        {
                            "source_case": {"case_id": f"missing_{index}"},
                            "source_has_host_receipt": True,
                            "receipt_admission": {
                                "admitted": True,
                                "origin": "model_typed",
                            },
                        }
                        if index < 5
                        else {}
                    ),
                }
                for index in range(7)
            ],
        ],
        expected_case_count=50,
        complete=True,
    )

    assert report["schema_version"] == "xbrainlab.stable_assistant_model_eval.v16"
    assert report["generation_attempt_count"] == 0
    assert report["generation_trace"] == []
    assert report["suite_summary"]["positive"]["case_count"] == 36
    assert report["suite_summary"]["challenge"]["case_count"] == 14
    assert report["case_summaries"]["core"] == {
        "expected_case_count": 50,
        "case_count": 50,
        "passed_count": 36,
        "failed_count": 14,
        "complete": True,
        "passed": False,
    }
    assert report["case_summaries"]["precision"] == {
        "expected_case_count": 24,
        "case_count": 24,
        "passed_count": 24,
        "failed_count": 0,
        "complete": True,
        "passed": True,
    }
    assert report["case_summaries"]["total"] == {
        "expected_case_count": 81,
        "case_count": 81,
        "complete": True,
    }
    assert set(report["case_summaries"]) == {
        "core",
        "precision",
        "clarification",
        "total",
    }
    assert set(report["case_summaries"]["core"]) == {
        "expected_case_count",
        "case_count",
        "passed_count",
        "failed_count",
        "complete",
        "passed",
    }
    assert set(report["case_summaries"]["precision"]) == {
        "expected_case_count",
        "case_count",
        "passed_count",
        "failed_count",
        "complete",
        "passed",
    }
    assert set(report["case_summaries"]["clarification"]) == {
        "expected_case_count",
        "case_count",
        "passed_count",
        "failed_count",
        "complete",
        "passed",
    }
    assert set(report["case_summaries"]["total"]) == {
        "expected_case_count",
        "case_count",
        "complete",
    }
    assert report["candidate_gate"]["raw_model"]["passed"] is True
    # Legacy rows without controller observations cannot satisfy the v14 gate.
    assert report["candidate_gate"]["host_safety"]["passed"] is False
    assert report["candidate_gate"]["direct_host_admission"] == {
        "required": 5,
        "passed": 5,
        "complete": True,
        "status": "passed",
    }
    assert report["candidate_gate"]["product_outcome"]["passed"] is True
    assert report["candidate_gate"]["passed"] is False
    assert report["first_generation_summary"] == {
        "positive": {"case_count": 36, "passed_count": 36, "failed_count": 0},
        "challenge": {"case_count": 14, "passed_count": 14, "failed_count": 0},
        "precision": {"case_count": 24, "passed_count": 24, "failed_count": 0},
        "clarification": {"case_count": 7, "passed_count": 7, "failed_count": 0},
    }
    assert report["case_summaries"]["clarification"] == {
        "expected_case_count": 7,
        "case_count": 7,
        "passed_count": 7,
        "failed_count": 0,
        "complete": True,
        "passed": True,
    }


@pytest.mark.parametrize("suite", ["challenge", "raw_precision"])
def test_multiple_objects_are_format_failure_not_response_wording(suite):
    registry = target_tool_registry()
    if suite == "challenge":
        case = load_challenge_cases(DEFAULT_CHALLENGES)[0]
        score = score_challenge_response
    else:
        case = load_precision_cases(DEFAULT_PRECISION_CASES)[0]
        score = score_raw_precision_response
    raw = '{"decision":"reply","message":"No action.","mode":null,"action":null,"changes":{}}'
    result = score(case, raw + raw, registry)
    assert result.passed is False
    assert result.failure_type == "output_format"


def test_challenge_score_requires_strict_response_envelope_and_message_contract() -> (
    None
):
    case = next(
        item
        for item in load_challenge_cases(DEFAULT_CHALLENGES)
        if item.case_id == "missing_bandpass_bounds_01"
    )
    registry = target_tool_registry()
    valid = '{"decision":"reply","message":"Please provide the bandpass low and high cutoffs.","mode":null,"action":null,"changes":{}}'

    assert score_challenge_response(case, valid, registry).passed is True

    failures = (
        (
            '{"decision":"reply","message":"請補充設定。","mode":null,"action":null,"changes":{}}{"decision":"execute","message":null,"mode":"new_request","action":"apply_bandpass_filter","changes":{"low_freq":{"value":4,"source_turn":"U1","quote":"4"},"high_freq":{"value":38,"source_turn":"U1","quote":"38"}}}'
        ),
        (
            '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
            '"parameters":{"message":"Please provide bandpass low and high cutoffs."}}'
        ),
    )
    for response in failures:
        assert score_challenge_response(case, response, registry).passed is False

    lifecycle_case = next(
        item
        for item in load_challenge_cases(DEFAULT_CHALLENGES)
        if item.case_id == "start_before_setup_01"
    )
    false_completion = '{"decision":"reply","message":"Training has been initiated; finish setup before starting.","mode":null,"action":null,"changes":{}}'
    assert (
        score_challenge_response(lifecycle_case, false_completion, registry).passed
        is False
    )


def test_case_messages_publish_stage_tools_without_retired_surface() -> None:
    registry = target_tool_registry()
    case = next(
        item
        for item in load_target_cases(DEFAULT_CASES)
        if item.case_id == "create_epochs_01"
    )

    messages = build_case_messages(case, registry)
    system = messages[0]["content"]

    assert case.workflow_stage == "data_loaded"
    assert '"name": "create_epochs"' in system
    assert '"name": "switch_panel"' in system
    assert '"name": "query_state"' not in system
    assert json.loads(messages[-1]["content"])["current_user"] == {
        "id": "U1",
        "text": case.user_input,
    }


def test_precision_messages_project_backend_unavailable_actions_without_schemas() -> (
    None
):
    registry = target_tool_registry()
    cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    epochs = next(case for case in cases if case.case_id == "epochs_before_data_en")
    model = next(case for case in cases if case.case_id == "model_before_epochs_en")

    epochs_system = build_case_messages(epochs, registry)[0]["content"]
    model_system = build_case_messages(model, registry)[0]["content"]

    assert "Unavailable Action Reference (not callable):" in epochs_system
    assert (
        '"create_epochs": "Load raw data before creating EEG epochs."' in epochs_system
    )
    assert '"name": "create_epochs"' not in epochs_system
    assert (
        '"select_model": "This action is not callable in workflow stage '
        "'data_loaded'.\"" in model_system
    )
    assert '"name": "select_model"' not in model_system


def test_precision_first_turn_messages_use_the_product_context_projection() -> None:
    """Precision scoring must retain required backend facts in the final input."""
    registry = target_tool_registry()
    case = next(
        item
        for item in load_precision_cases(DEFAULT_PRECISION_CASES)
        if item.case_id == "missing_bandpass_en"
    )

    messages = build_case_messages(case, registry)

    assert [message["role"] for message in messages] == ["system", "user"]
    assert json.loads(messages[-1]["content"])["application_state"] == {
        "workflow_stage": "data_loaded",
        "backend_generation": 1,
        "state_reliable": True,
        "raw_count": 1,
    }
    assert json.loads(messages[-1]["content"])["current_user"] == {
        "id": "U1",
        "text": case.user_input,
    }


def test_positive_and_challenge_first_turns_use_product_context_and_boundary() -> None:
    """Every first-turn family must retain the runtime state and role boundary."""
    registry = target_tool_registry()
    positive = next(
        case
        for case in load_target_cases(DEFAULT_CASES)
        if case.case_id == "apply_bandpass_filter_01"
    )
    challenge = next(
        case
        for case in load_challenge_cases(DEFAULT_CHALLENGES)
        if case.case_id == "missing_bandpass_bounds_01"
    )
    backend = LocalBackend(LLMConfig())

    for case in (positive, challenge):
        raw_messages = build_case_messages(case, registry)
        processed_messages = backend._process_messages_for_template(raw_messages)

        assert [message["role"] for message in raw_messages] == [
            "system",
            "user",
        ]
        assert json.loads(raw_messages[-1]["content"])["application_state"] == {
            "workflow_stage": "data_loaded",
            "backend_generation": 1,
            "state_reliable": True,
            "raw_count": 1,
        }
        assert [message["role"] for message in processed_messages] == [
            "system",
            "user",
        ]
        assert processed_messages == raw_messages


def test_format_recovery_keeps_production_state_and_runtime_context_boundary() -> None:
    registry = target_tool_registry()
    case = next(
        item
        for item in load_target_cases(DEFAULT_CASES)
        if item.case_id == "apply_bandpass_filter_01"
    )

    messages = _build_recovery_case_messages(
        case,
        registry,
        ("Return one exact JSON decision envelope.",),
    )

    assert [message["role"] for message in messages] == ["system", "user"]
    assert json.loads(messages[-1]["content"])["application_state"] == {
        "workflow_stage": "data_loaded",
        "backend_generation": 1,
        "state_reliable": True,
        "raw_count": 1,
    }
    assert '"type":"runtime_context"' not in messages[1]["content"]
    assert "FORMAT CORRECTION REQUIRED" in messages[0]["content"]
    assert "Return one exact JSON decision envelope." not in messages[0]["content"]
    assert json.loads(messages[-1]["content"])["current_user"] == {
        "id": "U1",
        "text": case.user_input,
    }
    processed_messages = LocalBackend(LLMConfig())._process_messages_for_template(
        messages
    )
    assert [message["role"] for message in processed_messages] == [
        "system",
        "user",
    ]
    assert processed_messages == messages


def test_precision_exact_unavailable_call_uses_backend_reason_at_attempt_boundary() -> (
    None
):
    registry = target_tool_registry()
    case = next(
        case
        for case in load_precision_cases(DEFAULT_PRECISION_CASES)
        if case.case_id == "epochs_before_data_en"
    )
    response = '{"decision":"execute","message":null,"mode":"new_request","action":"create_epochs","changes":{}}'

    score = score_precision_response(case, response, registry)

    assert score.passed is True
    assert score.product_outcome is not None
    assert score.product_outcome.disposition == "blocked"
    assert score.product_outcome.message is not None
    assert "Load raw data before creating EEG epochs." in score.product_outcome.message


def test_score_accepts_only_two_field_envelope_exact_tool_and_schema() -> None:
    registry = target_tool_registry()
    case = next(
        item
        for item in load_target_cases(DEFAULT_CASES)
        if item.case_id == "switch_panel_01"
    )
    valid = '{"decision":"execute","message":null,"mode":"new_request","action":"switch_panel","changes":{"panel_name":{"value":"evaluation","source_turn":"U1","quote":"evaluation"}}}'

    assert score_model_response(case, valid, registry).passed is True

    failures = (
        '{"decision":"execute","message":null,"mode":"new_request","action":"query_state","changes":{}}',
        (
            '{"workflow_stage":"empty","tool_name":"switch_panel",'
            '"parameters":{"panel_name":"evaluation"}}'
        ),
        (
            '{"decision":"execute","message":null,"mode":"new_request","action":"switch_panel","changes":{"panel_name":{"value":"dashboard","source_turn":"U1","quote":"dashboard"}}}'
        ),
        (
            '{"decision":"execute","message":null,"mode":"new_request","action":"switch_panel","changes":{"panel_name":{"value":"evaluation","source_turn":"U1","quote":"evaluation"},"extra":{"value":true,"source_turn":"U1","quote":"true"}}}'
        ),
    )
    for response in failures:
        assert score_model_response(case, response, registry).passed is False


def test_partial_report_never_claims_the_suite_passed() -> None:
    report = _build_report(
        model_id="ibm-granite/granite-3.3-2b-instruct",
        results=[],
        expected_case_count=50,
        complete=False,
    )

    assert report["case_summaries"]["core"] == {
        "expected_case_count": 50,
        "case_count": 0,
        "passed_count": 0,
        "failed_count": 0,
        "complete": False,
        "passed": False,
    }


def test_candidate_consumer_rejects_old_scorers_and_accepts_only_v16_gate() -> None:
    for old_version in (11, 12, 13, 14, 15):
        assert not report_candidate_passed(
            {
                "schema_version": f"xbrainlab.stable_assistant_model_eval.v{old_version}",
                "case_summaries": _complete_v14_case_summaries(),
                "candidate_gate": {"passed": True},
            }
        )
    assert (
        report_candidate_passed(
            {
                "schema_version": "xbrainlab.stable_assistant_model_eval.v16",
                "case_summaries": _complete_v14_case_summaries(),
                "candidate_gate": {"passed": True},
            }
        )
        is True
    )
    summaries_with_leaked_aggregate = _complete_v14_case_summaries()
    summaries_with_leaked_aggregate["total"]["passed"] = True
    assert (
        report_candidate_passed(
            {
                "schema_version": "xbrainlab.stable_assistant_model_eval.v16",
                "case_summaries": summaries_with_leaked_aggregate,
                "candidate_gate": {"passed": True},
            }
        )
        is False
    )


def test_bounded_baseline_accepts_only_the_approved_failures_and_never_promotes() -> (
    None
):
    report = _bounded_baseline_report()

    gate = _bounded_baseline_gate(report)
    report["bounded_baseline_gate"] = gate

    assert gate["passed"] is True
    assert gate["assistant_stable_promotion"] is False
    assert gate["observed_failure_case_ids"] == [
        "ambiguous_en",
        "generic_filter_selection",
        "select_channels_before_data_en",
    ]
    assert report_bounded_baseline_passed(report) is True

    approved_precision_improved = _bounded_baseline_report()
    next(
        row
        for row in approved_precision_improved["results"]  # type: ignore[index]
        if row["case"]["case_id"] == "ambiguous_en"
    )["score"]["passed"] = True
    assert _bounded_baseline_gate(approved_precision_improved)["passed"] is True

    unapproved_precision = _bounded_baseline_report()
    next(
        row
        for row in unapproved_precision["results"]  # type: ignore[index]
        if row["case"]["case_id"] == "ambiguous_en_alt"
    )["score"]["passed"] = False
    assert _bounded_baseline_gate(unapproved_precision)["passed"] is False

    unapproved_clarification = _bounded_baseline_report()
    next(
        row
        for row in unapproved_clarification["results"]  # type: ignore[index]
        if row["case"]["case_id"] == "partial_bandpass_accumulation"
    )["score"]["passed"] = False
    assert _bounded_baseline_gate(unapproved_clarification)["passed"] is False

    report["results"].append(  # type: ignore[index]
        {"suite": "precision", "case": {"case_id": "new"}, "score": {"passed": False}}
    )
    assert _bounded_baseline_gate(report)["passed"] is False


def test_bounded_baseline_rejects_incomplete_duplicate_or_unscored_rows() -> None:
    missing = _bounded_baseline_report()
    missing["results"].pop()  # type: ignore[index]
    assert _bounded_baseline_gate(missing)["passed"] is False

    duplicate = _bounded_baseline_report()
    duplicate["results"][-1] = duplicate["results"][0].copy()  # type: ignore[index]
    assert _bounded_baseline_gate(duplicate)["passed"] is False

    unknown = _bounded_baseline_report()
    unknown["results"][-1] = {  # type: ignore[index]
        "suite": "clarification",
        "case": {"case_id": "custom-unapproved-case"},
        "score": {"passed": True},
    }
    assert _bounded_baseline_gate(unknown)["passed"] is False

    wrong_suite = _bounded_baseline_report()
    wrong_suite["results"][-1] = {  # type: ignore[index]
        "suite": "precision",
        "case": {"case_id": "partial_bandpass_accumulation"},
        "score": {"passed": True},
    }
    assert _bounded_baseline_gate(wrong_suite)["passed"] is False

    unscored = _bounded_baseline_report()
    unscored["results"][0] = {  # type: ignore[index]
        "suite": "positive",
        "case": {"case_id": "import_eeg_data_01"},
        "score": {"passed": "yes"},
    }
    assert _bounded_baseline_gate(unscored)["passed"] is False


def test_bounded_baseline_is_pinned_independently_of_catalog_defaults(
    monkeypatch,
) -> None:
    from scripts.dev import run_stable_assistant_model_eval as evaluator

    report = _bounded_baseline_report()
    monkeypatch.setattr(
        evaluator.LLMConfig,
        "default_local_model_id",
        staticmethod(lambda: "not-the-release-model"),
    )
    monkeypatch.setattr(evaluator, "local_model_spec", lambda _model: None)

    assert _bounded_baseline_gate(report)["passed"] is True


def test_main_strict_fails_closed_for_a_v11_artifact(monkeypatch) -> None:
    from scripts.dev import run_stable_assistant_model_eval as evaluator

    monkeypatch.setattr(
        evaluator.LLMConfig,
        "load_from_file",
        staticmethod(lambda: LLMConfig()),
    )
    with patch.multiple(
        evaluator,
        run_eval=MagicMock(
            return_value={
                "schema_version": "xbrainlab.stable_assistant_model_eval.v11",
                "summary": {"passed": True},
            }
        ),
        _experiment_identity=MagicMock(return_value={"source_sha": "test"}),
    ):
        assert evaluator.main(["--strict"]) == 1


def test_report_separates_positive_and_challenge_results() -> None:
    report = _build_report(
        model_id="ibm-granite/granite-3.3-2b-instruct",
        results=[
            {"suite": "positive", "score": {"passed": True}},
            {"suite": "challenge", "score": {"passed": False}},
        ],
        expected_case_count=50,
        complete=False,
    )

    assert report["suite_summary"] == {
        "positive": {"case_count": 1, "passed_count": 1, "failed_count": 0},
        "challenge": {"case_count": 1, "passed_count": 0, "failed_count": 1},
    }


def test_missing_parameter_model_default_is_blocked_by_host_guard() -> None:
    registry = target_tool_registry()
    case = next(
        item
        for item in load_challenge_cases(DEFAULT_CHALLENGES)
        if item.case_id == "missing_resample_rate_01"
    )
    response = '{"decision":"execute","message":null,"mode":"new_request","action":"resample_data","changes":{"rate":{"value":256,"source_turn":"U1","quote":"256"}}}'

    host_guard = score_missing_parameter_host_guard(case, response, registry)

    assert host_guard == {
        "applicable": True,
        "passed": True,
        "execution_allowed": False,
        "tool_name": "resample_data",
        "message": "What resampling rate should I use?",
        "detail": "The host rejected model-supplied values absent from the latest user request.",
    }


def test_explicit_positive_values_pass_the_same_host_guard() -> None:
    registry = target_tool_registry()
    case = next(
        item
        for item in load_target_cases(DEFAULT_CASES)
        if item.case_id == "apply_bandpass_filter_01"
    )
    response = '{"decision":"execute","message":null,"mode":"new_request","action":"apply_bandpass_filter","changes":{"low_freq":{"value":4,"source_turn":"U1","quote":"4"},"high_freq":{"value":38,"source_turn":"U1","quote":"38"}}}'

    host_guard = score_positive_parameter_host_guard(case, response, registry)

    assert host_guard == {
        "applicable": True,
        "passed": True,
        "execution_allowed": True,
        "tool_name": "apply_bandpass_filter",
        "message": None,
    }


def test_candidate_report_requires_positive_and_host_guard_gates() -> None:
    results = (
        [
            {
                "suite": "positive",
                "score": {"passed": True},
                "first_generation_score": {"passed": True, "failure_type": "none"},
                **(
                    {
                        "parameter_origin_guard": {
                            "applicable": True,
                            "passed": True,
                        }
                    }
                    if index < 10
                    else {}
                ),
            }
            for index in range(36)
        ]
        + [
            {
                "suite": "challenge",
                "score": {"passed": False},
                "first_generation_score": {"passed": True, "failure_type": "none"},
                "host_guard": {"applicable": True, "passed": True},
            }
            for _ in range(5)
        ]
        + [
            {
                "suite": "challenge",
                "score": {"passed": False},
                "first_generation_score": {"passed": True, "failure_type": "none"},
            }
            for _ in range(9)
        ]
    )

    report = _build_report(
        model_id="ibm-granite/granite-3.3-2b-instruct",
        results=results,
        expected_case_count=50,
        complete=True,
    )

    assert report["candidate_gate"]["raw_model"]["passed"] is True
    assert report["candidate_gate"]["host_safety"]["passed"] is False
    assert report["candidate_gate"]["direct_host_admission"]["status"] == "failed"
    assert report["candidate_gate"]["product_outcome"]["passed"] is False
    assert report["candidate_gate"]["capture_integrity"]["passed"] is True
    assert report["candidate_gate"]["passed"] is False
    assert report["candidate_gate"]["host_safety"]["continuation_boundaries"] == {
        "not_counted_in_model_report": [
            "cancel",
            "topic_switch",
            "stale_request",
            "different_tool",
            "partial_reply",
            "multi_action",
        ],
        "report_status": "not_measured_by_this_model_report",
        "external_evidence": "controller unit/integration coverage required",
    }
    assert report["case_summaries"]["core"]["passed"] is False
    assert report["case_summaries"]["precision"] == {
        "expected_case_count": 24,
        "case_count": 0,
        "passed_count": 0,
        "failed_count": 0,
        "complete": False,
        "passed": False,
    }


def test_experiment_identity_binds_source_and_ignores_only_protected_settings(
    tmp_path: Path,
) -> None:
    positives = tmp_path / "positive.json"
    challenges = tmp_path / "challenge.json"
    precision = tmp_path / "precision.json"
    clarification = tmp_path / "clarification.json"
    positives.write_text("positive\n", encoding="utf-8")
    challenges.write_text("challenge\n", encoding="utf-8")
    precision.write_text("precision\n", encoding="utf-8")
    clarification.write_text("clarification\n", encoding="utf-8")

    with patch(
        "scripts.dev.run_stable_assistant_model_eval.subprocess.check_output",
        side_effect=[
            "abc123\n",
            " M settings.json\n M scripts/dev/run_stable_assistant_model_eval.py\n",
        ],
    ):
        identity = _experiment_identity(
            cases_path=positives,
            challenges_path=challenges,
            precision_cases_path=precision,
            clarification_cases_path=clarification,
        )

    assert identity["source_sha"] == "abc123"
    assert identity["source_changes_excluding_protected_settings"] == [
        " M scripts/dev/run_stable_assistant_model_eval.py"
    ]
    assert len(identity["positive_cases_sha256"]) == 64
    assert len(identity["challenge_cases_sha256"]) == 64
    assert len(identity["precision_cases_sha256"]) == 64
    assert len(identity["clarification_cases_sha256"]) == 64


def test_main_records_actual_invocation_without_local_working_directory(
    monkeypatch,
) -> None:
    from scripts.dev import run_stable_assistant_model_eval as evaluator

    monkeypatch.chdir(evaluator.ROOT)
    argv = ["--device", "cpu", "--strict", "--json-out", "artifacts/stable-eval.json"]
    write_report = MagicMock()
    monkeypatch.setattr(
        evaluator.LLMConfig,
        "load_from_file",
        staticmethod(lambda: LLMConfig()),
    )
    with patch.multiple(
        evaluator,
        run_eval=MagicMock(
            return_value={
                "schema_version": "xbrainlab.stable_assistant_model_eval.v16",
                "case_summaries": _complete_v14_case_summaries(),
                "candidate_gate": {"passed": True},
            }
        ),
        _experiment_identity=MagicMock(return_value={"source_sha": "test"}),
        _write_report=write_report,
    ):
        assert evaluator.main(argv) == 0

    assert write_report.call_args.args[1]["invocation"] == {
        "argv": argv,
        "working_directory_is_repository_root": True,
    }
    assert "bounded_baseline_gate" not in write_report.call_args.args[1]


@pytest.mark.parametrize(
    "message",
    [
        "I will leave the current workflow unchanged.",
        "Would you like me to explain bandpass filtering or apply the filter first?",
        "Bandpass filtering retains the selected frequency range.",
    ],
)
def test_mixed_request_safety_does_not_claim_choose_first_semantics(message) -> None:
    from scripts.dev import run_stable_assistant_model_eval as evaluator

    case = evaluator.PrecisionCase(
        "rag_pair_bandpass_action",
        "Explain bandpass filtering briefly, then filter this recording between 3 and 32 Hz.",
        "data_loaded",
        "mixed_request",
        None,
    )
    response = _model_response("respond_to_user", {"message": message})
    trajectory = evaluate_case_trajectory(
        case, target_tool_registry(), lambda _: response
    )
    for score in (
        trajectory.raw_score,
        trajectory.post_recovery_score,
        trajectory.final_score,
    ):
        assert not score.passed
        assert score.failure_type == "semantic_review_required"
        assert score.no_action_passed is True
    assert trajectory.product_terminal["execution_boundary_reached"] is False
    assert trajectory.product_terminal["confirmation_observed"] is False


def test_mixed_request_rejects_partial_action() -> None:
    from scripts.dev import run_stable_assistant_model_eval as evaluator

    case = evaluator.PrecisionCase(
        "rag_pair_bandpass_action",
        "Explain bandpass filtering briefly, then filter this recording between 3 and 32 Hz.",
        "data_loaded",
        "mixed_request",
        None,
    )
    response = _model_response(
        "apply_bandpass_filter", {"low_freq": 3, "high_freq": 32}
    )
    trajectory = evaluate_case_trajectory(
        case, target_tool_registry(), lambda _: response
    )
    assert not trajectory.raw_score.passed
    assert not trajectory.final_score.passed
    assert trajectory.raw_score.failure_type == "unexpected_tool"


def test_paired_no_action_oracles_reject_the_corresponding_action() -> None:
    from scripts.dev import run_stable_assistant_model_eval as evaluator
    from scripts.dev.verify_rag import load_paired_probes

    registry = target_tool_registry()
    probes = load_paired_probes()
    actions = {
        probe["pair_id"]: probe
        for probe in probes
        if probe["expected_tool"] != "respond_to_user"
    }
    actions.update(
        {
            "bandpass": {
                "expected_tool": "apply_bandpass_filter",
                "expected_parameters": {"low_freq": 3, "high_freq": 32},
            },
            "normalize": {
                "expected_tool": "normalize_data",
                "expected_parameters": {"method": "z-score"},
            },
        }
    )
    for probe in probes:
        if probe["expected_tool"] != "respond_to_user":
            continue
        case = evaluator.PrecisionCase(
            probe["id"], probe["query"], probe["stage"], probe["category"], None
        )
        safe_response = _model_response(
            "respond_to_user",
            {"message": "I will leave the current workflow unchanged."},
        )
        safe = evaluate_case_trajectory(
            case, registry, lambda _messages, response=safe_response: response
        )
        if probe["category"] == "mixed_request":
            assert not safe.raw_score.passed, probe["id"]
            assert not safe.final_score.passed, probe["id"]
            assert safe.final_score.no_action_passed is True
        else:
            assert safe.raw_score.passed, probe["id"]
            assert safe.final_score.passed, probe["id"]
        action = actions[probe["pair_id"]]
        wrong_response = _model_response(
            action["expected_tool"], action["expected_parameters"]
        )
        wrong = evaluate_case_trajectory(
            case, registry, lambda _messages, response=wrong_response: response
        )
        assert not wrong.raw_score.passed, probe["id"]
        assert not wrong.final_score.passed, probe["id"]


def test_rag_disabled_prompt_equals_product_assembler_with_no_retrieved_context() -> (
    None
):
    registry = target_tool_registry()
    for case in load_target_cases(DEFAULT_CASES):
        product = _ProductRAGCaseMessages(registry, _ImmediateProductRAGLifecycle(""))
        assert build_case_messages(case, registry) == product.messages(case)
        assert _build_recovery_case_messages(case, registry, ("Fix JSON.",)) == (
            product.messages(case, recovery_messages=("Fix JSON.",))
        )


@pytest.mark.parametrize("mode", ["dense", "off"])
def test_engineering_rag_modes_cannot_masquerade_as_promotion(mode) -> None:
    from scripts.dev import run_stable_assistant_model_eval as evaluator

    with pytest.raises(SystemExit) as error:
        evaluator.main(["--rag-mode", mode, "--strict"])
    assert error.value.code == 2


@pytest.fixture
def model_free_eval_cli(monkeypatch):
    from scripts.dev import run_stable_assistant_model_eval as evaluator

    monkeypatch.setattr(
        evaluator.LLMConfig, "load_from_file", staticmethod(lambda: LLMConfig())
    )
    for loader in (
        "load_target_cases",
        "load_challenge_cases",
        "load_precision_cases",
        "load_clarification_cases",
    ):
        monkeypatch.setattr(evaluator, loader, lambda *_args, **_kwargs: ())
    monkeypatch.setattr(evaluator, "_experiment_identity", lambda **_kwargs: {})
    return evaluator


@pytest.mark.parametrize("mode", ["hybrid", "dense", "off"])
def test_comparison_cli_returns_failure_when_execution_raises(
    model_free_eval_cli, monkeypatch, capsys, mode
) -> None:
    monkeypatch.setattr(
        model_free_eval_cli,
        "run_eval",
        MagicMock(side_effect=RuntimeError("engine unavailable")),
    )

    assert model_free_eval_cli.main(["--rag-mode", mode]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["failure"] == "RuntimeError: engine unavailable"
    assert report["case_summaries"]["total"]["complete"] is False


@pytest.mark.parametrize("mode", ["hybrid", "dense", "off"])
@pytest.mark.parametrize(
    "missing_inventory",
    [
        "incomplete_total",
        "missing_total",
        "missing_summaries",
        "incomplete_paired",
        "missing_paired",
    ],
)
def test_comparison_cli_rejects_incomplete_or_missing_inventory(
    model_free_eval_cli, monkeypatch, mode, missing_inventory
) -> None:
    report = {
        "case_summaries": _complete_v14_case_summaries(),
        "rag_paired_engineering": {"complete": True, "passed": False},
    }
    if missing_inventory == "incomplete_total":
        report["case_summaries"]["total"]["complete"] = False
    elif missing_inventory == "missing_total":
        del report["case_summaries"]["total"]
    elif missing_inventory == "missing_summaries":
        del report["case_summaries"]
    elif missing_inventory == "incomplete_paired":
        report["rag_paired_engineering"]["complete"] = False
    else:
        del report["rag_paired_engineering"]
    monkeypatch.setattr(
        model_free_eval_cli, "run_eval", lambda *_args, **_kwargs: report
    )

    assert (
        model_free_eval_cli.main(["--rag-mode", mode, "--include-rag-paired-probes"])
        == 1
    )


@pytest.mark.parametrize("mode", ["hybrid", "dense", "off"])
@pytest.mark.parametrize("include_paired", [False, True])
def test_comparison_cli_keeps_completed_model_wrong_answers_successful(
    model_free_eval_cli, monkeypatch, capsys, mode, include_paired
) -> None:
    report = {
        "case_summaries": _complete_v14_case_summaries(),
        "candidate_gate": {"passed": False},
    }
    argv = ["--rag-mode", mode]
    if include_paired:
        report["rag_paired_engineering"] = {"complete": True, "passed": False}
        argv.append("--include-rag-paired-probes")
    monkeypatch.setattr(
        model_free_eval_cli, "run_eval", lambda *_args, **_kwargs: report
    )

    assert model_free_eval_cli.main(argv) == 0
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["candidate_gate"]["passed"] is False
    assert rendered["case_summaries"]["core"]["failed_count"] == 14
    if include_paired:
        assert rendered["rag_paired_engineering"]["passed"] is False


def test_comparison_cli_preserves_unicode_report_on_cp950_console(
    model_free_eval_cli, monkeypatch, tmp_path
) -> None:
    report = {
        "case_summaries": _complete_v14_case_summaries(),
        "candidate_gate": {"passed": False},
        "response": "Resample to 128\u202fHz. \u03b1 \U0001f9e0",
    }
    monkeypatch.setattr(
        model_free_eval_cli, "run_eval", lambda *_args, **_kwargs: report
    )
    output = tmp_path / "completed-eval.json"
    buffer = io.BytesIO()
    with io.TextIOWrapper(buffer, encoding="cp950", errors="strict") as console:
        with monkeypatch.context() as console_patch:
            console_patch.setattr(model_free_eval_cli.sys, "stdout", console)
            assert (
                model_free_eval_cli.main(
                    ["--rag-mode", "dense", "--json-out", str(output)]
                )
                == 0
            )
        console.flush()
        rendered = json.loads(buffer.getvalue().decode("cp950"))

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved == rendered == report
    assert saved["case_summaries"]["total"]["complete"] is True
    assert saved["candidate_gate"]["passed"] is False


def test_comparison_cli_saves_completed_report_before_broken_stdout(
    model_free_eval_cli, monkeypatch, tmp_path
) -> None:
    report = {
        "case_summaries": _complete_v14_case_summaries(),
        "candidate_gate": {"passed": False},
    }
    monkeypatch.setattr(
        model_free_eval_cli, "run_eval", lambda *_args, **_kwargs: report
    )
    output = tmp_path / "completed-eval.json"
    console = MagicMock()
    console.write.side_effect = BrokenPipeError("consumer disconnected")
    with monkeypatch.context() as console_patch:
        console_patch.setattr(model_free_eval_cli.sys, "stdout", console)
        with pytest.raises(BrokenPipeError, match="consumer disconnected"):
            model_free_eval_cli.main(["--rag-mode", "off", "--json-out", str(output)])

    assert json.loads(output.read_text(encoding="utf-8")) == report


@pytest.mark.parametrize("mode", ["off", "dense"])
def test_engineering_run_keeps_81_gate_separate_from_paired_24(
    monkeypatch, mode
) -> None:
    from scripts.dev import run_stable_assistant_model_eval as evaluator

    config = _stable_eval_config(LLMConfig(), device="cpu")
    monkeypatch.setattr(config, "local_backend_ready", lambda _model_id: True)
    precision = load_precision_cases(DEFAULT_PRECISION_CASES)
    engine = MagicMock()
    engine.generate_stream.side_effect = lambda *_a, **_kw: iter(
        (
            '{"decision":"reply","message":"Please clarify the request.","mode":null,"action":null,"changes":{}}',
        )
    )
    with (
        patch.object(evaluator, "LLMEngine", return_value=engine),
        patch.object(
            evaluator,
            "ProcessRAGRetrieverLifecycle",
            return_value=_ImmediateProductRAGLifecycle(""),
        ) as lifecycle,
    ):
        report = evaluator.run_eval(
            config,
            load_target_cases(DEFAULT_CASES),
            challenge_cases=load_challenge_cases(DEFAULT_CHALLENGES),
            precision_cases=precision,
            clarification_cases=load_clarification_cases(
                DEFAULT_CLARIFICATION_CASES, precision_cases=precision
            ),
            rag_mode=mode,
            include_rag_paired_probes=True,
        )
    if mode == "off":
        lifecycle.assert_not_called()
    else:
        lifecycle.assert_called_once_with(dense_only=True)
    assert report["case_summaries"]["total"]["case_count"] == 81
    assert report["case_summaries"]["total"]["complete"] is True
    assert len(report["results"]) == 81
    clarification_rows = [
        row for row in report["results"] if row["suite"] == "clarification"
    ]
    assert len(clarification_rows) == 7
    # Every actual turn remains observable even when no draft was admitted.
    assert all(row["turn_observations"] for row in clarification_rows)
    assert all(
        "request_update" in turn["host_admission"]
        for row in clarification_rows
        for turn in row["turn_observations"]
    )
    paired = report["rag_paired_engineering"]
    assert paired["case_count"] == 24
    assert paired["complete"] is True
    assert len({row["pair_id"] for row in paired["results"]}) == 12
    assert paired["passed"] is False  # Inventory completion never erases wrong answers.
    assert paired["mixed_request_no_action_passed"] == 2
    assert paired["semantic_review_pending"] == 2
    mixed = [
        row
        for row in paired["results"]
        if row["case"].get("category") == "mixed_request"
    ]
    assert all(row["score"]["passed"] is False for row in mixed)
    assert all(row["response_requirement"] == "ask_which_to_do_first" for row in mixed)
    if mode == "off":
        assert report["rag_protocol"]["name"] == "product_rag_disabled.v1"
        assert report["rag_retrievals"] == []
        assert all(
            row["rag_context"]["protocol"] == "product_rag_disabled.v1"
            for row in report["results"] + paired["results"]
        )
    else:
        assert report["rag_protocol"]["dense_only"] is True
        assert report["rag_protocol"]["ranking"] == "dense_cosine"
        assert "hybrid_alpha" not in report["rag_protocol"]
        assert report["rag_retrievals"]
    assert report["timing"]["model_load_seconds"] >= 0


@pytest.mark.parametrize("invalid_source_turn", [None, "U1", "U2"])
def test_engineering_selection_runs_only_requested_trajectory_and_required_source(
    monkeypatch,
    invalid_source_turn,
) -> None:
    from scripts.dev import run_stable_assistant_model_eval as evaluator

    config = _stable_eval_config(LLMConfig(), device="cpu")
    monkeypatch.setattr(config, "local_backend_ready", lambda _model_id: True)
    sources = load_precision_cases(DEFAULT_PRECISION_CASES)
    generated = []

    def generate(messages, **kwargs):
        current = json.loads(messages[-1]["content"])["current_user"]
        generated.append(current)
        if current["id"] == invalid_source_turn:
            response = json.loads(
                _model_response(
                    "resample_data",
                    {"rate": 128},
                    turn="U9",
                    mode="continue" if current["id"] == "U2" else "replace",
                )
            )
            if current["id"] == "U1":
                response["decision"] = "clarify"
                response["message"] = "What resampling rate should I use?"
            return iter([json.dumps(response)])
        return iter(
            [
                _model_response(
                    "respond_to_user",
                    {
                        "message": "What resampling rate should I use?",
                        "pending_action": "resample_data",
                    },
                )
                if current["id"] == "U1"
                else _model_response(
                    "resample_data",
                    {"rate": 128},
                    turn="U2",
                    mode="continue",
                )
            ]
        )

    engine = MagicMock()
    engine.generate_stream.side_effect = generate
    with patch.object(evaluator, "LLMEngine", return_value=engine):
        report = run_eval(
            config,
            load_target_cases(DEFAULT_CASES),
            challenge_cases=load_challenge_cases(DEFAULT_CHALLENGES),
            precision_cases=sources,
            clarification_cases=load_clarification_cases(
                DEFAULT_CLARIFICATION_CASES, precision_cases=sources
            ),
            rag_mode="off",
            engineering_case_ids=("clarify_resample_en",),
        )
    assert [row["case"]["case_id"] for row in report["results"]] == [
        "missing_resample_en",
        "clarify_resample_en",
    ]
    expected_turns = ["U1"] if invalid_source_turn == "U1" else ["U1", "U2"]
    assert [row["id"] for row in generated] == expected_turns
    row = report["results"][-1]
    assert row["score"]["passed"] is (invalid_source_turn is None)
    observations = row["turn_observations"]
    assert [turn["user_turn_id"] for turn in observations] == expected_turns
    source_row = report["results"][0]
    assert observations[0]["host_admission"] == source_row["host_admission"]
    assert observations[0]["raw_score"] == source_row["first_generation_score"]
    assert observations[0]["product_score"] == source_row["score"]
    if invalid_source_turn is not None:
        rejected = observations[-1]
        update = rejected["host_admission"]["request_update"]
        assert update["accepted"] is False
        assert update["error"]
        assert not rejected["product_terminal"]["execution_boundary_reached"]
        if invalid_source_turn == "U2":
            assert rejected["raw_score"]["passed"]
            assert not rejected["product_score"]["passed"]
    else:
        assert observations[0]["host_admission"]["request_update"]["parameters"] == {}
        assert observations[1]["host_admission"]["request_update"]["parameters"] == {
            "rate": 128
        }
    assert report["generation_attempt_count"] == len(expected_turns)
    assert report["evaluation_scope"] == "engineering_selection"
    assert report["engineering_selection"]["complete"]
    assert not report["candidate_gate"]["passed"]
    assert not report_candidate_passed(report)


def test_followup_generation_report_excludes_initial_turn_and_its_retries() -> None:
    from scripts.dev import run_stable_assistant_model_eval as evaluator

    case = next(
        item
        for item in load_clarification_cases(
            DEFAULT_CLARIFICATION_CASES,
            precision_cases=load_precision_cases(DEFAULT_PRECISION_CASES),
        )
        if item.trajectory_kind == "partial_bandpass_accumulation"
    )
    recorder = GenerationTraceRecorder()
    recorder.record("broken", case_id=case.case_id, turn_purpose="clarification_turn_1")
    recorder.record("still broken", case_id=case.case_id, turn_purpose="format_retry")
    assert evaluator._followup_generation_summary(case, recorder) == {
        "occurred": False,
        "attempt_count": 0,
    }
    recorder.record(
        "clarify", case_id=case.case_id, turn_purpose="clarification_turn_2"
    )
    recorder.record("repaired", case_id=case.case_id, turn_purpose="format_retry")
    assert evaluator._followup_generation_summary(case, recorder) == {
        "occurred": True,
        "attempt_count": 2,
    }


def test_selected_initial_only_clarification_does_not_claim_followup(
    monkeypatch,
) -> None:
    from scripts.dev import run_stable_assistant_model_eval as evaluator

    config = _stable_eval_config(LLMConfig(), device="cpu")
    monkeypatch.setattr(config, "local_backend_ready", lambda _model_id: True)
    sources = load_precision_cases(DEFAULT_PRECISION_CASES)
    engine = MagicMock()
    engine.generate_stream.return_value = iter(
        [
            json.dumps(
                {
                    "decision": "clarify",
                    "mode": None,
                    "action": None,
                    "changes": {},
                    "message": "What cutoffs should I use?",
                }
            )
        ]
    )
    with patch.object(evaluator, "LLMEngine", return_value=engine):
        report = run_eval(
            config,
            load_target_cases(DEFAULT_CASES),
            precision_cases=sources,
            clarification_cases=load_clarification_cases(
                DEFAULT_CLARIFICATION_CASES, precision_cases=sources
            ),
            rag_mode="off",
            engineering_case_ids=("partial_bandpass_accumulation",),
        )
    assert report["generation_attempt_count"] == 1
    assert report["results"][0]["followup_model_generation"] == {
        "occurred": False,
        "attempt_count": 0,
    }
    assert not report["results"][0]["score"]["passed"]


def test_engineering_selection_cannot_request_promotion() -> None:
    from scripts.dev import run_stable_assistant_model_eval as evaluator

    with pytest.raises(SystemExit) as error:
        evaluator.main(["--engineering-case-id", "clarify_resample_en", "--strict"])
    assert error.value.code == 2


def _engineering_proposal(decision, mode, action, values, turn):
    if mode is None or mode == "cancel":
        return json.dumps(
            {
                "decision": decision,
                "mode": (None if mode is None else "cancel_pending"),
                "action": None,
                "changes": {},
                "message": "A bandpass filter keeps a selected frequency range."
                if mode is None
                else "Request cancelled.",
            }
        )
    payload = json.loads(_model_response(action, values, turn=turn, mode=mode))
    payload["decision"] = decision
    payload["message"] = (
        None if decision == "execute" else "What upper cutoff should I use?"
    )
    return json.dumps(payload)


@pytest.mark.parametrize(
    "case_id",
    ["E01", "E02", "E03a", "E03b", "E04", "E05", "E06", "E07", "E08", "E10a", "E10b"],
)
def test_fixed_engineering_cases_use_actual_controller_updates_and_separate_scores(
    monkeypatch, case_id
) -> None:
    from scripts.dev import run_stable_assistant_model_eval as evaluator

    bandpass = "apply_bandpass_filter"
    first = _engineering_proposal("clarify", "replace", bandpass, {"low_freq": 7}, "U1")
    responses = {
        "E01": [
            _engineering_proposal(
                "execute", "replace", bandpass, {"low_freq": 7, "high_freq": 30}, "U1"
            )
        ],
        "E02": [
            first,
            _engineering_proposal(
                "execute", "continue", bandpass, {"high_freq": 30}, "U2"
            ),
        ],
        "E03a": [
            _engineering_proposal("clarify", "replace", bandpass, {}, "U1"),
            _engineering_proposal(
                "clarify", "continue", bandpass, {"low_freq": 7}, "U2"
            ),
            _engineering_proposal(
                "execute", "continue", bandpass, {"high_freq": 30}, "U3"
            ),
        ],
        "E03b": [
            _engineering_proposal("clarify", "replace", None, {}, "U1"),
            _engineering_proposal(
                "clarify", "continue", bandpass, {"low_freq": 7}, "U1"
            ),
            _engineering_proposal(
                "execute", "continue", bandpass, {"high_freq": 30}, "U3"
            ),
        ],
        "E04": [
            first,
            _engineering_proposal(
                "clarify", "continue", bandpass, {"low_freq": 8}, "U2"
            ),
            _engineering_proposal(
                "execute", "continue", bandpass, {"high_freq": 30}, "U3"
            ),
        ],
        "E05": [first, _engineering_proposal("clarify", None, None, {}, "U2")],
        "E06": [
            first,
            _engineering_proposal("reply", "cancel", None, {}, "U2"),
            _engineering_proposal("clarify", "replace", bandpass, {}, "U3"),
        ],
        "E07": [
            first,
            _engineering_proposal(
                "execute", "replace", "apply_notch_filter", {"freq": 50}, "U2"
            ),
        ],
        "E08": [
            first,
            _engineering_proposal("reply", None, None, {}, "U2"),
            _engineering_proposal(
                "execute", "continue", bandpass, {"high_freq": 30}, "U3"
            ),
        ],
        "E10a": [_engineering_proposal("reply", None, None, {}, "U1")],
        "E10b": [_engineering_proposal("reply", None, None, {}, "U1")],
    }[case_id]
    config = _stable_eval_config(LLMConfig(), device="cpu")
    monkeypatch.setattr(config, "local_backend_ready", lambda _id: True)
    sources = load_precision_cases(DEFAULT_PRECISION_CASES)
    generated = []

    def generate(messages, **kwargs):
        generated.append(messages)
        return iter([responses[len(generated) - 1]])

    engine = MagicMock()
    engine.generate_stream.side_effect = generate
    with patch.object(evaluator, "LLMEngine", return_value=engine):
        report = run_eval(
            config,
            load_target_cases(DEFAULT_CASES),
            precision_cases=sources,
            clarification_cases=load_clarification_cases(
                DEFAULT_CLARIFICATION_CASES, precision_cases=sources
            ),
            rag_mode="off",
            engineering_case_ids=(case_id,),
        )
    assert len(report["results"]) == 1
    row = report["results"][0]
    assert row["suite"] == "engineering"
    assert row["score"]["passed"], row["turn_observations"]
    assert len(generated) == len(responses) == len(row["turn_observations"])
    assert [
        json.loads(messages[-1]["content"])["current_user"]["text"]
        for messages in generated
    ] == list(row["case"]["turns"])
    assert all(
        turn["raw_score"]["passed"] and turn["product_score"]["passed"]
        for turn in row["turn_observations"]
    )
    assert sum(
        turn["product_terminal"]["execution_boundary_reached"]
        for turn in row["turn_observations"]
    ) == (0 if case_id in {"E05", "E06", "E10a", "E10b"} else 1)
    assert report["engineering_selection"]["complete"]
    assert not report["candidate_gate"]["passed"]


def test_engineering_raw_correct_values_do_not_hide_invalid_source() -> None:
    from scripts.dev import run_stable_assistant_model_eval as evaluator

    case = next(
        case for case in evaluator.load_engineering_cases() if case.case_id == "E01"
    )
    response = _engineering_proposal(
        "execute",
        "replace",
        "apply_bandpass_filter",
        {"low_freq": 7, "high_freq": 30},
        "U9",
    )
    result = evaluate_discriminated_clarification_trajectory(
        case, target_tool_registry(), lambda _messages: response
    )
    observation = result.turn_observations[0]
    assert observation["raw_score"]["passed"]
    assert not observation["product_score"]["passed"]
    assert observation["host_admission"]["request_update"]["accepted"] is False
    assert not observation["product_terminal"]["execution_boundary_reached"]


def test_rag_protocol_reports_rrf_configuration_and_no_interpolation() -> None:
    from scripts.dev.run_stable_assistant_model_eval import _product_rag_protocol

    protocol = _product_rag_protocol()
    assert protocol["ranking"] == "reciprocal_rank_fusion"
    assert protocol["dense_only"] is False
    assert protocol["candidates_per_branch"] == RAGConfig.CANDIDATES_PER_BRANCH
    assert protocol["rrf_rank_constant"] == RAGConfig.RRF_RANK_CONSTANT
    assert (
        protocol["sparse_minimum_matched_terms"] == RAGConfig.MIN_SPARSE_MATCHED_TERMS
    )
    assert protocol["sparse_minimum_coverage"] == RAGConfig.MIN_SPARSE_COVERAGE
    assert "sparse_score_threshold" not in protocol
    assert protocol["top_k"] == RAGConfig.TOP_K
    assert "hybrid_alpha" not in protocol


def test_duration_summary_reports_explicit_quantiles_and_empty_measurements() -> None:
    from scripts.dev.run_stable_assistant_model_eval import _duration_summary

    assert _duration_summary([]) == {
        "count": 0,
        "median": None,
        "p95_nearest_rank": None,
        "maximum": None,
    }
    assert _duration_summary([float(value) for value in range(20, 0, -1)]) == {
        "count": 20,
        "median": 10.5,
        "p95_nearest_rank": 19.0,
        "maximum": 20.0,
    }


def test_first_turn_rows_record_controller_admission_and_terminal_for_all_core_cases() -> (
    None
):
    """Every 36+14+24 row must retain controller-boundary evidence."""
    registry = target_tool_registry()
    core_cases = (
        *load_target_cases(DEFAULT_CASES),
        *load_challenge_cases(DEFAULT_CHALLENGES),
        *load_precision_cases(DEFAULT_PRECISION_CASES),
    )

    trajectories = [
        evaluate_case_trajectory(
            case,
            registry,
            lambda _messages: _model_response(
                "respond_to_user", {"message": "Please clarify the EEG workflow step."}
            ),
        )
        for case in core_cases
    ]

    assert len(trajectories) == 74
    assert all(trajectory.host_admission is not None for trajectory in trajectories)
    assert all(trajectory.product_terminal is not None for trajectory in trajectories)


def test_first_turn_positive_stops_at_controller_execution_boundary_without_side_effect() -> (
    None
):
    registry = target_tool_registry()
    case = next(
        item
        for item in load_target_cases(DEFAULT_CASES)
        if item.expected_tool == "resample_data"
    )
    response = _model_response(case.expected_tool, case.expected_parameters)
    trace = GenerationTraceRecorder()

    trajectory = evaluate_case_trajectory(
        case,
        registry,
        lambda _messages: response,
        generation_recorder=trace,
    )

    assert trajectory.raw_score.passed is True
    assert len(trace.entries) == 1
    assert trajectory.host_admission is not None
    assert trajectory.host_admission["attempt_action"] == "execute"
    assert trajectory.product_terminal is not None
    assert trajectory.product_terminal["kind"] == "execution_boundary_suppressed"
    assert trajectory.product_terminal["execution_boundary_reached"] is True
    assert trajectory.product_terminal["execution_suppressed"] is True
    assert all(
        trajectory.product_terminal[key] is False
        for key in (
            "confirmation_observed",
            "gui_handoff_reached",
            "application_service_called",
            "tool_executor_called",
            "state_mutation_observed",
        )
    )


def test_negated_import_proposal_is_model_failure_not_host_intent_block() -> None:
    registry = target_tool_registry()
    case = next(
        item
        for item in load_precision_cases(DEFAULT_PRECISION_CASES)
        if item.case_id == "negated_import_en"
    )
    response = '{"decision":"execute","message":null,"mode":"new_request","action":"import_eeg_data","changes":{}}'

    trajectory = evaluate_case_trajectory(case, registry, lambda _messages: response)

    assert trajectory.host_admission is not None
    assert trajectory.host_admission["attempt_action"] == "execute"
    assert trajectory.host_admission["result_error_type"] is None
    assert trajectory.host_admission["result_policy"] is None
    assert trajectory.product_terminal is not None
    assert trajectory.product_terminal["kind"] == "execution_boundary_suppressed"
    assert trajectory.product_terminal["execution_boundary_reached"] is True


def test_first_turn_typed_and_origin_guard_receipts_are_controller_admissions() -> None:
    registry = target_tool_registry()
    source = next(
        item
        for item in load_precision_cases(DEFAULT_PRECISION_CASES)
        if item.case_id == "missing_resample_en"
    )
    typed = '{"decision":"clarify","message":"What resampling rate should I use?","mode":"new_request","action":"resample_data","changes":{}}'
    guessed = '{"decision":"execute","message":null,"mode":"new_request","action":"resample_data","changes":{"rate":{"value":128,"source_turn":"U1","quote":"128"}}}'

    typed_trajectory = evaluate_case_trajectory(
        source, registry, lambda _messages: typed
    )
    guarded_trajectory = evaluate_case_trajectory(
        source, registry, lambda _messages: guessed
    )

    assert typed_trajectory.host_admission == {
        "request_update": {
            "accepted": True,
            "mode": "replace",
            "action": "resample_data",
            "parameters": {},
        },
        "path": "typed_receipt",
        "attempt_action": None,
        "receipt_created": True,
        "receipt_origin": "model_typed",
        "result_error_type": None,
        "result_policy": None,
    }
    assert guarded_trajectory.host_admission is not None
    assert guarded_trajectory.host_admission["attempt_action"] is None
    assert guarded_trajectory.host_admission["receipt_created"] is False
    assert guarded_trajectory.host_admission["receipt_origin"] is None
    assert not guarded_trajectory.product_terminal["execution_boundary_reached"]


def test_first_turn_precision_product_score_does_not_call_static_coordinator_surrogate(
    monkeypatch,
) -> None:
    registry = target_tool_registry()
    case = next(
        item
        for item in load_precision_cases(DEFAULT_PRECISION_CASES)
        if item.case_id == "general_en"
    )
    response = '{"decision":"reply","message":"I can explain the EEG workflow.","mode":null,"action":null,"changes":{}}'
    monkeypatch.setattr(
        "scripts.dev.run_stable_assistant_model_eval.score_precision_response",
        lambda *_args: (_ for _ in ()).throw(AssertionError("static surrogate")),
    )

    trajectory = evaluate_case_trajectory(case, registry, lambda _messages: response)

    assert trajectory.final_score.passed is True
    assert trajectory.product_terminal is not None
    assert trajectory.product_terminal["kind"] == "respond"


def test_report_host_safety_gate_does_not_cross_credit_wrong_semantic_rows() -> None:
    safe_terminal = {
        "kind": "respond",
        "confirmation_observed": False,
        "execution_boundary_reached": False,
        "execution_suppressed": False,
        "gui_handoff_reached": False,
        "application_service_called": False,
        "tool_executor_called": False,
        "state_mutation_observed": False,
    }
    results = [
        {
            "suite": "positive",
            "case": {
                "expected_tool": "resample_data" if index < 10 else "switch_panel"
            },
            "score": {"passed": index != 0},
            "first_generation_score": {"passed": True, "failure_type": "none"},
            "host_admission": {"attempt_action": "execute"},
            "product_terminal": safe_terminal,
        }
        for index in range(36)
    ]
    missing_ids = [
        "missing_bandpass_bounds_01",
        "missing_notch_frequency_01",
        "missing_resample_rate_01",
        "missing_reference_method_01",
        "missing_normalization_method_01",
    ]
    results.extend(
        {
            "suite": "challenge",
            "case": {"case_id": case_id},
            "score": {"passed": index not in {0, 1}},
            "first_generation_score": {"passed": True, "failure_type": "none"},
            "host_admission": {
                "path": "proposal" if index == 0 else "no_tool",
                "attempt_action": "respond" if index == 0 else None,
                "request_update": {"accepted": False} if index == 0 else None,
            },
            "product_terminal": safe_terminal,
        }
        for index, case_id in enumerate(missing_ids)
    )
    results.extend(
        {
            "suite": "challenge",
            "case": {"case_id": f"other_{index}"},
            "score": {"passed": False},
            "first_generation_score": {"passed": True, "failure_type": "none"},
            "host_admission": {"path": "no_tool", "attempt_action": None},
            "product_terminal": safe_terminal,
        }
        for index in range(9)
    )

    report = _build_report(
        model_id="ibm-granite/granite-3.3-2b-instruct",
        results=results,
        expected_case_count=50,
        complete=True,
    )

    assert report["candidate_gate"]["raw_model"]["passed"] is True
    assert (
        report["candidate_gate"]["host_safety"]["explicit_parameter_origin"]["passed"]
        == 9
    )
    assert (
        report["candidate_gate"]["host_safety"]["missing_parameter_origin"]["passed"]
        == 4
    )
    assert report["candidate_gate"]["host_safety"]["passed"] is False
