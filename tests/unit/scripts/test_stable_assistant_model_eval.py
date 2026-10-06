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
    GenerationTraceRecorder,
    ModelGenerationAttempt,
    _build_recovery_case_messages,
    _capture_audit_request,
    _capture_integrity_report,
    _evaluation_generation_policy,
    _ProductRAGCaseMessages,
    _stable_eval_config,
    _trajectory_payload,
    build_case_messages,
    evaluate_case_trajectory,
    load_challenge_cases,
    load_precision_cases,
    load_target_cases,
    run_eval,
    score_challenge_response,
    score_model_response,
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


def _model_response(tool_name, parameters):
    if tool_name == "respond_to_user":
        parameters = {"message": parameters["message"]}
    return json.dumps({"tool_name": tool_name, "parameters": parameters})


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


def test_active_assistant_evidence_cases_are_english_only() -> None:
    precision_cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    inputs = [
        *(case.user_input for case in load_target_cases(DEFAULT_CASES)),
        *(case.user_input for case in load_challenge_cases(DEFAULT_CHALLENGES)),
        *(case.user_input for case in precision_cases),
    ]

    assert all(text.isascii() for text in inputs)


def test_run_eval_records_every_lower_engine_generation_in_global_order(
    monkeypatch,
) -> None:
    """The report trace is runner-owned, not a reconstruction of policy attempts."""
    raw_response = ' {"tool_name":"respond_to_user","parameters":{"message":"I need more information."}}\n'
    config = _stable_eval_config(LLMConfig(), device="cpu")
    monkeypatch.setattr(config, "local_backend_ready", lambda _model_id: True)
    precision_cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    engine = MagicMock()
    engine.generate_stream.side_effect = lambda *_args, **_kwargs: iter((raw_response,))

    with patch(
        "scripts.dev.run_stable_assistant_model_eval.LLMEngine",
        return_value=engine,
    ):
        report = run_eval(
            config,
            precision_cases,
        )

    trace = report["generation_trace"]
    assert len(report["generation_trace"]) == engine.generate_stream.call_count
    assert len(report["generation_trace"]) == len(precision_cases)
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
    engine = MagicMock()
    engine.generate_stream.side_effect = lambda *_args, **_kwargs: iter(
        (
            '{"tool_name":"respond_to_user","parameters":{"message":"I need more information."}}',
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
            precision_cases,
        )

    capture_integrity = report["capture_integrity"]
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
    raw_output = ' {"tool_name":"respond_to_user","parameters":{"message":"I need more information."}}\n'
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
            precision_cases,
            checkpoint_path=tmp_path / "checkpoint.json",
        )

    audit = report["capture_integrity"]
    assert audit["requested"] is True
    assert audit["status"] == "verified"
    assert audit["artifact_count"] == len(report["generation_trace"])
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
        item["capture_integrity"]["status"] != "verified" for item in checkpoint_reports
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
    raw_output = '{"tool_name":"respond_to_user","parameters":{"message":"I need more information."}}'
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
            precision_cases,
        )

    audit = report["capture_integrity"]
    assert audit["status"] == "failed"
    assert audit["failure_codes"] == ["new_session_ambiguity"]
    assert report["candidate_gate"]["capture_verified"] is False
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
                '{"tool_name":"respond_to_user","parameters":{"message":"I can explain the EEG workflow."}}'
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
                '{"tool_name":"respond_to_user","parameters":{"message":"I can explain the EEG workflow."}}'
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


def test_precision_scoring_uses_parser_and_host_attempt_outcome_not_keywords() -> None:
    registry = target_tool_registry()
    cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    missing = next(case for case in cases if case.case_id == "missing_bandpass_en")
    out_of_stage = next(
        case for case in cases if case.case_id == "start_before_setup_en"
    )
    general = next(case for case in cases if case.case_id == "general_en")

    direct_response = '{"tool_name":"respond_to_user","parameters":{"message":"Please provide the cutoff values."}}'
    false_completion = '{"tool_name":"respond_to_user","parameters":{"message":"The filter has been completed."}}'
    placeholder_response = '{"tool_name":"respond_to_user","parameters":{"message":"<concise response or one clarifying question>"}}'
    model_default = '{"tool_name":"apply_bandpass_filter","parameters":{"low_freq":0.5,"high_freq":45}}'
    blocked_start = '{"tool_name":"start_training","parameters":{}}'
    accidental_navigation = (
        '{"tool_name":"switch_panel","parameters":{"panel_name":"training"}}'
    )
    retired_stage_echo = (
        '{"workflow_stage":"data_loaded","tool_name":"start_training","parameters":{}}'
    )

    direct_score = score_precision_response(missing, direct_response, registry)
    invented_score = score_precision_response(missing, model_default, registry)
    blocked_score = score_precision_response(out_of_stage, blocked_start, registry)

    assert direct_score.passed is True
    assert score_precision_response(missing, false_completion, registry).passed is False
    assert (
        score_precision_response(missing, placeholder_response, registry).passed
        is False
    )
    assert invented_score.passed is False
    assert invented_score.failure_type == "unexpected_tool"
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
    # Host validates numeric arguments, not their literal presence in the prompt.
    # An executable proposal must not become a correct missing-parameter answer.
    invented_outcome = invented_score.product_outcome
    assert invented_outcome is not None
    assert invented_outcome.disposition == "execute"
    assert invented_outcome.confirmation_requested is False
    assert invented_outcome.gui_handoff_permitted is True
    assert invented_outcome.application_service_permitted is True
    assert invented_outcome.tool_executor_permitted is True
    assert invented_outcome.state_mutation_permitted is True
    assert blocked_score.product_outcome is not None
    assert blocked_score.product_outcome.disposition == "blocked"
    assert blocked_score.product_outcome.message
    for score in (direct_score, blocked_score):
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
    assert trajectory.final_score.passed is False
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
    import_response = '{"tool_name":"import_eeg_data","parameters":{}}'

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
    incomplete_question = '{"tool_name":"respond_to_user","parameters":{"message":"Which bandpass filter should I apply?"}}'
    exact_question = '{"tool_name":"respond_to_user","parameters":{"message":"What low and high bandpass cutoffs should I use?"}}'
    invented_default = '{"tool_name":"apply_bandpass_filter","parameters":{"low_freq":1,"high_freq":40}}'

    assert (
        score_raw_precision_response(case, incomplete_question, registry).passed
        is False
    )
    assert score_raw_precision_response(case, exact_question, registry).passed is True
    assert score_precision_response(case, invented_default, registry).passed is False
    assert (
        score_raw_precision_response(case, invented_default, registry).passed is False
    )


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
                '{"tool_name":"respond_to_user","parameters":{"message":"I can explain the EEG workflow; which part would you like to understand?"}}'
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
    assert json.loads(trajectory.final_response)["tool_name"] == "respond_to_user"
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
                '{"tool_name":"respond_to_user","parameters":{"message":"How can I help with your EEG workflow?"}}'
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
            ('{"tool_name":"switch_panel","parameters":{"panel_name":"training"}}'),
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
        "execution_boundary_suppressed",
    }
    assert trajectory.product_terminal["execution_boundary_reached"] is True
    assert trajectory.product_terminal["execution_suppressed"] is True


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


@pytest.mark.parametrize("suite", ["challenge", "raw_precision"])
def test_multiple_objects_are_format_failure_not_response_wording(suite):
    registry = target_tool_registry()
    if suite == "challenge":
        case = load_challenge_cases(DEFAULT_CHALLENGES)[0]
        score = score_challenge_response
    else:
        case = load_precision_cases(DEFAULT_PRECISION_CASES)[0]
        score = score_raw_precision_response
    raw = '{"tool_name":"respond_to_user","parameters":{"message":"No action."}}'
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
    valid = '{"tool_name":"respond_to_user","parameters":{"message":"Please provide the bandpass low and high cutoffs."}}'

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
    false_completion = '{"tool_name":"respond_to_user","parameters":{"message":"Training has been initiated; finish setup before starting."}}'
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
    response = '{"tool_name":"create_epochs","parameters":{}}'

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
    valid = '{"tool_name":"switch_panel","parameters":{"panel_name":"evaluation"}}'

    assert score_model_response(case, valid, registry).passed is True

    failures = (
        '{"tool_name":"query_state","parameters":{}}',
        (
            '{"workflow_stage":"empty","tool_name":"switch_panel",'
            '"parameters":{"panel_name":"evaluation"}}'
        ),
        ('{"tool_name":"switch_panel","parameters":{"panel_name":"dashboard"}}'),
        (
            '{"tool_name":"switch_panel","parameters":{"panel_name":"evaluation","extra":true}}'
        ),
    )
    for response in failures:
        assert score_model_response(case, response, registry).passed is False


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
    ):
        assert evaluator.main(["--strict"]) == 1


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
        _write_report=write_report,
    ):
        assert evaluator.main(argv) == 1  # Historical v16 cannot pass current strict.

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
        "load_single_turn_cases",
    ):
        monkeypatch.setattr(evaluator, loader, lambda *_args, **_kwargs: ())
    monkeypatch.setattr(
        evaluator.subprocess,
        "check_output",
        lambda args, **kwargs: "head" if "rev-parse" in args else "",
    )
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
    assert report["candidate_gate"]["passed"] is False


@pytest.mark.parametrize("mode", ["hybrid", "dense", "off"])
@pytest.mark.parametrize(
    "missing_inventory",
    [
        "incomplete_total",
        "missing_total",
        "missing_summaries",
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

    assert model_free_eval_cli.main(["--rag-mode", mode]) == 1


@pytest.mark.parametrize("mode", ["hybrid", "dense", "off"])
def test_comparison_cli_keeps_completed_model_wrong_answers_successful(
    model_free_eval_cli, monkeypatch, capsys, mode
) -> None:
    report = {
        "case_summaries": _complete_v14_case_summaries(),
        "candidate_gate": {"passed": False},
    }
    argv = ["--rag-mode", mode]
    monkeypatch.setattr(
        model_free_eval_cli, "run_eval", lambda *_args, **_kwargs: report
    )

    assert model_free_eval_cli.main(argv) == 0
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["candidate_gate"]["passed"] is False
    assert rendered["case_summaries"]["core"]["failed_count"] == 14


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
    response = '{"tool_name":"import_eeg_data","parameters":{}}'

    trajectory = evaluate_case_trajectory(case, registry, lambda _messages: response)

    assert trajectory.host_admission is not None
    assert trajectory.host_admission["attempt_action"] == "execute"
    assert trajectory.host_admission["result_error_type"] is None
    assert trajectory.host_admission["result_policy"] is None
    assert trajectory.product_terminal is not None
    assert trajectory.product_terminal["kind"] == "execution_boundary_suppressed"
    assert trajectory.product_terminal["execution_boundary_reached"] is True


def test_first_turn_precision_product_score_does_not_call_static_coordinator_surrogate(
    monkeypatch,
) -> None:
    registry = target_tool_registry()
    case = next(
        item
        for item in load_precision_cases(DEFAULT_PRECISION_CASES)
        if item.case_id == "general_en"
    )
    response = '{"tool_name":"respond_to_user","parameters":{"message":"I can explain the EEG workflow."}}'
    monkeypatch.setattr(
        "scripts.dev.run_stable_assistant_model_eval.score_precision_response",
        lambda *_args: (_ for _ in ()).throw(AssertionError("static surrogate")),
    )

    trajectory = evaluate_case_trajectory(case, registry, lambda _messages: response)

    assert trajectory.final_score.passed is True
    assert trajectory.product_terminal is not None
    assert trajectory.product_terminal["kind"] == "respond"
