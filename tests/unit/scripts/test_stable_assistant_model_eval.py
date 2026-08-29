"""Stable-v2 local-model selection evaluation contracts."""

import hashlib
import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.dev.run_stable_assistant_model_eval import (
    DEFAULT_CASES,
    DEFAULT_CHALLENGES,
    DEFAULT_CLARIFICATION_CASES,
    DEFAULT_PRECISION_CASES,
    CaseTrajectoryResult,
    GenerationTraceRecorder,
    ModelGenerationAttempt,
    TargetEvalScore,
    _build_recovery_case_messages,
    _build_report,
    _capture_audit_request,
    _capture_integrity_report,
    _evaluation_generation_policy,
    _experiment_identity,
    _stable_eval_config,
    _trajectory_payload,
    admit_clarification_receipt,
    build_case_messages,
    build_clarification_messages,
    evaluate_case_trajectory,
    evaluate_clarification_trajectory,
    evaluate_discriminated_clarification_trajectory,
    load_challenge_cases,
    load_clarification_cases,
    load_precision_cases,
    load_target_cases,
    run_eval,
    score_challenge_response,
    score_missing_parameter_host_guard,
    score_model_response,
    score_positive_parameter_host_guard,
    score_precision_response,
    score_raw_precision_response,
    target_tool_registry,
)
from XBrainLab.chat_contract import MODEL_UNTRUSTED_CONTEXT_BOUNDARY_MESSAGE
from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS
from XBrainLab.llm.agent.strict_envelope_recovery import (
    DEFAULT_STRICT_ENVELOPE_RECOVERY_POLICY,
)
from XBrainLab.llm.core.backends.local import LocalBackend
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.model_catalog import local_model_spec
from XBrainLab.llm.rag.config import RAGConfig

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
        (directory / "prompt.txt").write_text(prompt, encoding="utf-8")
        (directory / "raw-output.txt").write_text(raw_output, encoding="utf-8")
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
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        f'"parameters":{{"message":{json.dumps(long_question)},'
        '"pending_action":"resample_data","missing_inputs":["rate"]}}'
    )
    score = TargetEvalScore(
        False,
        "parameter_origin",
        response[:1_000],
        "data_loaded",
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
                workflow_stage="data_loaded",
                recovery_action="accept",
                taxonomy="respond",
                recovery_attempts_after=0,
            ),
        ),
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
            return_value=trajectory,
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
    assert response not in json.dumps(report)


def test_run_eval_records_every_lower_engine_generation_in_global_order(
    monkeypatch,
) -> None:
    """The report trace is runner-owned, not a reconstruction of policy attempts."""
    raw_response = (
        ' \n{"workflow_stage":"empty","tool_name":"respond_to_user",'
        '"parameters":{"message":"I need more information."}}\n'
    )
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
            '{"workflow_stage":"empty","tool_name":"respond_to_user",'
            '"parameters":{"message":"I need more information."}}',
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

    assert report["capture_integrity"]["requested"] is False
    assert report["capture_integrity"]["status"] == "not_requested"
    assert report["capture_integrity"]["failure_codes"] == []


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
    raw_output = (
        ' {"workflow_stage":"empty","tool_name":"respond_to_user",'
        '"parameters":{"message":"I need more information."}}\n'
    )
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

    audit = report["capture_integrity"]
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
        item["capture_integrity"]
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
    raw_output = (
        '{"workflow_stage":"empty","tool_name":"respond_to_user",'
        '"parameters":{"message":"I need more information."}}'
    )
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

    audit = report["capture_integrity"]
    assert audit["status"] == "failed"
    assert audit["failure_codes"] == ["new_session_ambiguity"]
    assert report["candidate_gate"]["capture_integrity"] is False
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


def test_clarification_prompt_and_score_use_product_receipt_boundary() -> None:
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
    first_response = (
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"What resampling rate should I use?",'
        '"pending_action":"resample_data","missing_inputs":["rate"]}}'
    )
    admission = admit_clarification_receipt(
        source,
        first_response,
        expected_tool=case.expected_tool,
        registry=registry,
    )
    assert admission is not None
    receipt = admission.receipt
    messages, _prompt_publication, _backend_publication = build_clarification_messages(
        case,
        source,
        receipt=receipt,
        registry=registry,
    )

    assert messages[-1] == {"role": "user", "content": "128 Hz"}
    assert "tool_input_clarification" in messages[1]["content"]
    response = (
        '{"workflow_stage":"data_loaded","tool_name":"resample_data",'
        '"parameters":{"rate":128}}'
    )
    generated_messages: list[list[dict[str, str]]] = []

    def generate(messages: list[dict[str, str]]) -> str:
        generated_messages.append(messages)
        return response

    trajectory = evaluate_clarification_trajectory(
        case,
        source,
        admission=admission,
        registry=registry,
        generate_response=generate,
    )

    assert trajectory.final_score.passed is True
    assert len(generated_messages) == 1
    active_receipt = admission.harness.pending_interactions.active_tool_input
    assert active_receipt is not None
    assert dict(active_receipt.verified_parameters) == {"rate": 128}
    assert trajectory.receipt_origin == "model_typed"
    assert trajectory.final_score.product_outcome is not None
    assert trajectory.final_score.product_outcome.disposition == "execute_boundary"
    assert trajectory.final_score.product_outcome.tool_executor_permitted is True


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
            '{"workflow_stage":"data_loaded","tool_name":"resample_data",'
            '"parameters":{}}'
        ),
        expected_tool="resample_data",
        registry=registry,
    )

    assert admission is None


def test_clarification_admission_records_host_parameter_origin_for_all_direct_tools() -> (
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
        response = json.dumps(
            {
                "workflow_stage": source.workflow_stage,
                "tool_name": source.requested_tool,
                "parameters": invented_parameters[source.requested_tool],
            }
        )
        admission = admit_clarification_receipt(
            source,
            response,
            expected_tool=source.requested_tool,
            registry=registry,
        )

        assert admission is not None
        assert admission.receipt_origin == "host_parameter_origin"
        assert admission.harness.pending_interactions.tool_input == admission.receipt


def test_clarification_admission_keeps_model_typed_origin_and_never_synthesizes() -> (
    None
):
    registry = target_tool_registry()
    source = next(
        case
        for case in load_precision_cases(DEFAULT_PRECISION_CASES)
        if case.case_id == "missing_resample_en"
    )
    typed = (
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"What resampling rate should I use?",'
        '"pending_action":"resample_data","missing_inputs":["rate"]}}'
    )

    admission = admit_clarification_receipt(
        source, typed, expected_tool="resample_data", registry=registry
    )
    missing = admit_clarification_receipt(
        source,
        '{"workflow_stage":"data_loaded","tool_name":"resample_data","parameters":{}}',
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
    response = (
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        f'"parameters":{{"message":{json.dumps("rate? " + "x" * 1_100)},'
        '"pending_action":"resample_data","missing_inputs":["rate"]}}'
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


def test_clarification_trajectory_uses_product_format_recovery() -> None:
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
    responses = iter(
        (
            '{"workflow_stage":"data_loaded","tool_name":"resample_data",',
            (
                '{"workflow_stage":"data_loaded","tool_name":"resample_data",'
                '"parameters":{"rate":128}}'
            ),
        )
    )

    first_response = (
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"What resampling rate should I use?",'
        '"pending_action":"resample_data","missing_inputs":["rate"]}}'
    )
    admission = admit_clarification_receipt(
        source,
        first_response,
        expected_tool=case.expected_tool,
        registry=registry,
    )
    assert admission is not None
    recorder = GenerationTraceRecorder()
    trajectory = evaluate_clarification_trajectory(
        case,
        source,
        admission=admission,
        registry=registry,
        generate_response=lambda _messages: next(responses),
        generation_recorder=recorder,
    )

    assert trajectory.raw_score.passed is False
    assert trajectory.final_score.passed is True
    assert len(trajectory.attempts) == 2
    assert trajectory.attempts[0].recovery_action == "retry_format"
    assert [entry.turn_purpose for entry in recorder.entries] == [
        "clarification_proposal",
        "format_retry",
    ]


def test_invalid_typed_clarification_replays_controller_format_recovery() -> None:
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
    first_response = (
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"What resampling rate should I use?",'
        '"pending_action":"resample_data","missing_inputs":["rate"]}}'
    )
    admission = admit_clarification_receipt(
        source,
        first_response,
        expected_tool=case.expected_tool,
        registry=registry,
    )
    assert admission is not None
    invalid_typed_reply = (
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"What resampling rate should I use?",'
        '"pending_action":"resample_data","missing_inputs":["rate"]}}'
    )
    repaired_reply = (
        '{"workflow_stage":"data_loaded","tool_name":"resample_data",'
        '"parameters":{"rate":128}}'
    )
    responses = iter((invalid_typed_reply, repaired_reply))
    generated_messages: list[list[dict[str, str]]] = []
    recorder = GenerationTraceRecorder()

    def generate(messages: list[dict[str, str]]) -> str:
        generated_messages.append(messages)
        return next(responses)

    trajectory = evaluate_clarification_trajectory(
        case,
        source,
        admission=admission,
        registry=registry,
        generate_response=generate,
        generation_recorder=recorder,
    )

    assert trajectory.raw_score.passed is False
    assert trajectory.attempts[0].recovery_action == "retry_format"
    assert [entry.turn_purpose for entry in recorder.entries] == [
        "clarification_proposal",
        "format_retry",
    ]
    assert any(
        "FORMAT CORRECTION REQUIRED" in message["content"]
        for message in generated_messages[1]
    )
    assert trajectory.final_score.passed is True
    assert trajectory.product_terminal is not None
    assert trajectory.product_terminal["kind"] == "execution_boundary_suppressed"


def test_first_turn_invalid_typed_precision_rows_replay_controller_recovery() -> None:
    registry = target_tool_registry()
    cases = {
        case.case_id: case for case in load_precision_cases(DEFAULT_PRECISION_CASES)
    }
    scenarios = (
        (
            "set_montage_before_epochs_en",
            "set_montage",
            "montage_name",
            "I can't set a montage until EEG epochs are available.",
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
            '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
            f'"parameters":{{"message":"I need one value first.",'
            f'"pending_action":"{pending_action}",'
            f'"missing_inputs":["{missing_input}"]}}}}'
        )
        repaired = (
            '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
            f'"parameters":{{"message":"{safe_message}"}}}}'
        )
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
        if item.case_id == "set_montage_before_epochs_en"
    )
    invalid_typed = (
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"I need one value first.",'
        '"pending_action":"set_montage","missing_inputs":["montage_name"]}}'
    )
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


def test_clarification_collection_cancellation_or_correction_skips_generation() -> None:
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
    first_response = (
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"What resampling rate should I use?",'
        '"pending_action":"resample_data","missing_inputs":["rate"]}}'
    )

    for reply in ("cancel", "Actually 256 Hz"):
        admission = admit_clarification_receipt(
            source,
            first_response,
            expected_tool=case.expected_tool,
            registry=registry,
        )
        assert admission is not None
        recorder = GenerationTraceRecorder()
        generate = MagicMock(
            side_effect=AssertionError("Host-terminal clarification must not generate.")
        )
        trajectory = evaluate_clarification_trajectory(
            replace(case, reply=reply),
            source,
            admission=admission,
            registry=registry,
            generate_response=generate,
            generation_recorder=recorder,
        )

        assert trajectory.final_score.passed is False
        assert trajectory.final_score.failure_type == "clarification_collection"
        assert trajectory.raw_score.response == ""
        assert trajectory.attempts == ()
        assert recorder.entries == []
        generate.assert_not_called()
        assert admission.harness.pending_interactions.active_tool_input is None
        assert admission.harness.pending_interactions.tool_input is None
        outcome = trajectory.final_score.product_outcome
        assert outcome is not None
        assert outcome.tool_executor_permitted is False


def test_discriminated_clarification_trajectories_use_scripted_model_turns() -> None:
    registry = target_tool_registry()
    precision_cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    cases = load_clarification_cases(
        DEFAULT_CLARIFICATION_CASES,
        precision_cases=precision_cases,
    )
    generic = next(
        case for case in cases if case.trajectory_kind == "generic_filter_selection"
    )
    partial = next(
        case
        for case in cases
        if case.trajectory_kind == "partial_bandpass_accumulation"
    )
    generic_responses = iter(
        (
            '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
            '"parameters":{"message":"Should I apply a bandpass or notch filter?"}}',
            '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
            '"parameters":{"message":"What low and high cutoffs should I use?",'
            '"pending_action":"apply_bandpass_filter",'
            '"missing_inputs":["low_freq","high_freq"]}}',
            '{"workflow_stage":"data_loaded","tool_name":"apply_bandpass_filter",'
            '"parameters":{"low_freq":12,"high_freq":40}}',
        )
    )
    partial_responses = iter(
        (
            '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
            '"parameters":{"message":"What low and high cutoffs should I use?",'
            '"pending_action":"apply_bandpass_filter",'
            '"missing_inputs":["low_freq","high_freq"]}}',
            '{"workflow_stage":"data_loaded","tool_name":"apply_bandpass_filter",'
            '"parameters":{"high_freq":128}}',
        )
    )

    generic_result = evaluate_discriminated_clarification_trajectory(
        generic, registry, lambda _messages: next(generic_responses)
    )
    partial_result = evaluate_discriminated_clarification_trajectory(
        partial, registry, lambda _messages: next(partial_responses)
    )

    assert generic_result.final_score.passed is True
    assert partial_result.final_score.passed is True
    assert generic_result.final_score.product_outcome is not None
    assert partial_result.final_score.product_outcome is not None


def test_generic_clarification_uses_the_checked_in_second_turn() -> None:
    """The evaluated prompt must use the transcript persisted in the corpus."""
    registry = target_tool_registry()
    precision_cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    generic = next(
        case
        for case in load_clarification_cases(
            DEFAULT_CLARIFICATION_CASES,
            precision_cases=precision_cases,
        )
        if case.trajectory_kind == "generic_filter_selection"
    )
    responses = iter(
        (
            '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
            '"parameters":{"message":"Should I apply a bandpass or notch filter?"}}',
            '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
            '"parameters":{"message":"What low and high cutoffs should I use?",'
            '"pending_action":"apply_bandpass_filter",'
            '"missing_inputs":["low_freq","high_freq"]}}',
            '{"workflow_stage":"data_loaded","tool_name":"apply_bandpass_filter",'
            '"parameters":{"low_freq":12,"high_freq":40}}',
        )
    )
    generated_messages: list[list[dict[str, str]]] = []

    def generate(messages: list[dict[str, str]]) -> str:
        generated_messages.append(messages)
        return next(responses)

    result = evaluate_discriminated_clarification_trajectory(
        generic,
        registry,
        generate,
    )

    assert result.final_score.passed is True
    assert generated_messages[1][-1] == {
        "role": "user",
        "content": generic.turns[1],
    }
    assert generated_messages[2][-1] == {
        "role": "user",
        "content": generic.turns[2],
    }
    assert result.receipt_origin == "model_typed"


def test_generation_trace_preserves_pre_strip_raw_identity_and_bounds_preview() -> None:
    registry = target_tool_registry()
    case = next(
        item
        for item in load_precision_cases(DEFAULT_PRECISION_CASES)
        if item.case_id == "general_en"
    )
    raw_response = (
        " \n"
        + json.dumps(
            {
                "workflow_stage": "empty",
                "tool_name": "respond_to_user",
                "parameters": {"message": "x" * 1_100},
            }
        )
        + "\n"
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
            '{"workflow_stage":"empty","tool_name":"respond_to_user",',
            (
                '{"workflow_stage":"empty","tool_name":"respond_to_user",'
                '"parameters":{"message":"I can explain the EEG workflow."}}'
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
            '{"workflow_stage":"empty","tool_name":"respond_to_user",',
            (
                '{"workflow_stage":"empty","tool_name":"respond_to_user",'
                '"parameters":{"message":"I can explain the EEG workflow."}}'
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
            workflow_stage="data_loaded",
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


def test_partial_bandpass_reply_requeues_without_model_generation_before_final_proposal() -> (
    None
):
    registry = target_tool_registry()
    precision_cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    partial = next(
        case
        for case in load_clarification_cases(
            DEFAULT_CLARIFICATION_CASES,
            precision_cases=precision_cases,
        )
        if case.trajectory_kind == "partial_bandpass_accumulation"
    )
    responses = iter(
        (
            '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
            '"parameters":{"message":"What low and high cutoffs should I use?",'
            '"pending_action":"apply_bandpass_filter",'
            '"missing_inputs":["low_freq","high_freq"]}}',
            '{"workflow_stage":"data_loaded","tool_name":"apply_bandpass_filter",'
            '"parameters":{"high_freq":128}}',
        )
    )
    recorder = GenerationTraceRecorder()
    generated_messages: list[list[dict[str, str]]] = []

    def generate(messages: list[dict[str, str]]) -> str:
        generated_messages.append(messages)
        return next(responses)

    result = evaluate_discriminated_clarification_trajectory(
        partial,
        registry,
        generate,
        generation_recorder=recorder,
        trace_case_id=partial.case_id,
    )

    assert result.final_score.passed is True
    assert [messages[-1]["content"] for messages in generated_messages] == [
        partial.turns[0],
        partial.turns[2],
    ]
    assert [entry.global_call_index for entry in recorder.entries] == [1, 2]
    assert [entry.turn_purpose for entry in recorder.entries] == [
        "first_turn",
        "clarification_proposal",
    ]
    assert all(entry.turn_purpose != "partial_reply" for entry in recorder.entries)
    assert [entry.raw_output_sha256 for entry in recorder.entries] == [
        hashlib.sha256(response.encode("utf-8")).hexdigest()
        for response in (
            (
                '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
                '"parameters":{"message":"What low and high cutoffs should I use?",'
                '"pending_action":"apply_bandpass_filter",'
                '"missing_inputs":["low_freq","high_freq"]}}'
            ),
            (
                '{"workflow_stage":"data_loaded","tool_name":"apply_bandpass_filter",'
                '"parameters":{"high_freq":128}}'
            ),
        )
    ]


def test_precision_scoring_uses_parser_and_host_attempt_outcome_not_keywords() -> None:
    registry = target_tool_registry()
    cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    missing = next(case for case in cases if case.case_id == "missing_bandpass_en")
    out_of_stage = next(
        case for case in cases if case.case_id == "start_before_setup_en"
    )
    general = next(case for case in cases if case.case_id == "general_en")

    direct_response = (
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"Please provide the cutoff values."}}'
    )
    false_completion = (
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"The filter has been completed."}}'
    )
    placeholder_response = (
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"<concise response or one clarifying question>"}}'
    )
    model_default = (
        '{"workflow_stage":"data_loaded","tool_name":"apply_bandpass_filter",'
        '"parameters":{"low_freq":0.5,"high_freq":45}}'
    )
    blocked_start = (
        '{"workflow_stage":"data_loaded","tool_name":"start_training","parameters":{}}'
    )
    accidental_navigation = (
        '{"workflow_stage":"empty","tool_name":"switch_panel",'
        '"parameters":{"panel_name":"training"}}'
    )
    wrong_stage_block = (
        '{"workflow_stage":"training","tool_name":"start_training","parameters":{}}'
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
        score_precision_response(out_of_stage, wrong_stage_block, registry).passed
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
        '{"workflow_stage":"data_loaded","tool_name":"apply_bandpass_filter",'
        '"parameters":{"low_freq":4,"high_freq":38}}'
        '{"workflow_stage":"data_loaded","tool_name":"resample_data",'
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


def test_import_intent_block_requires_typed_positive_origin_proof() -> None:
    registry = target_tool_registry()
    cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    negated_import = next(item for item in cases if item.case_id == "negated_import_en")
    epochs_before_data = next(
        item for item in cases if item.case_id == "epochs_before_data_en"
    )
    import_response = (
        '{"workflow_stage":"empty","tool_name":"import_eeg_data","parameters":{}}'
    )

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
    assert product_score.passed is True
    assert product_score.product_outcome is not None
    assert product_score.product_outcome.disposition == "blocked"
    assert product_score.product_outcome.confirmation_requested is False
    assert product_score.product_outcome.gui_handoff_permitted is False
    assert product_score.product_outcome.application_service_permitted is False
    assert product_score.product_outcome.tool_executor_permitted is False
    assert product_score.product_outcome.state_mutation_permitted is False
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
    incomplete_question = (
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"Which bandpass filter should I apply?"}}'
    )
    exact_question = (
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"What low and high bandpass cutoffs should I use?"}}'
    )
    invented_default = (
        '{"workflow_stage":"data_loaded","tool_name":"apply_bandpass_filter",'
        '"parameters":{"low_freq":1,"high_freq":40}}'
    )

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

    assert report["raw_model_gate"]["challenge_decision"] == {
        "required": 14,
        "critical_failures": 0,
        "wording_failures": 4,
        "max_wording_failures": 3,
        "unclassified_failures": 0,
    }
    assert report["raw_model_gate"]["passed"] is True


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
    assert report["raw_model_gate"]["clarification_continuation"] == {
        "required": 7,
        "passed": 6,
    }
    assert report["raw_model_gate"]["passed"] is True


def test_trajectory_retries_format_error_with_product_policy_and_scores_final() -> None:
    registry = target_tool_registry()
    case = next(
        case
        for case in load_precision_cases(DEFAULT_PRECISION_CASES)
        if case.case_id == "general_en"
    )
    responses = iter(
        (
            '{"workflow_stage":"empty","tool_name":"respond_to_user",',
            (
                '{"workflow_stage":"empty","tool_name":"respond_to_user",'
                '"parameters":{"message":"I can explain the EEG workflow; '
                'which part would you like to understand?"}}'
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
    assert trajectory.final_response.endswith("}}")
    assert [attempt.recovery_action for attempt in trajectory.attempts] == [
        "retry_format",
        "accept_no_tool",
    ]
    assert [attempt.taxonomy for attempt in trajectory.attempts] == [
        "format_error_retry",
        "recovered_plain_text",
    ]
    assert len(generated_messages) == 2
    assert "FORMAT CORRECTION REQUIRED" in generated_messages[1][1]["content"]
    assert generated_messages[1][-1] == {
        "role": "user",
        "content": case.user_input,
    }


def test_trajectory_exhaustion_is_visible_safe_failure_after_two_retries() -> None:
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
    assert len(generated_messages) == 3
    assert generated_messages[2][1]["content"].count("FORMAT CORRECTION REQUIRED") == 2
    assert [attempt.recovery_action for attempt in trajectory.attempts] == [
        "retry_format",
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


def test_trajectory_retries_stage_mismatch_like_product_controller() -> None:
    registry = target_tool_registry()
    case = next(
        case
        for case in load_precision_cases(DEFAULT_PRECISION_CASES)
        if case.case_id == "general_en"
    )
    responses = iter(
        (
            (
                '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
                '"parameters":{"message":"How can I help?"}}'
            ),
            (
                '{"workflow_stage":"empty","tool_name":"respond_to_user",'
                '"parameters":{"message":"How can I help with your EEG workflow?"}}'
            ),
        )
    )

    trajectory = evaluate_case_trajectory(
        case,
        registry,
        lambda _messages: next(responses),
    )

    assert trajectory.raw_score.failure_type == "workflow_stage"
    assert trajectory.final_score.passed is True
    assert trajectory.attempts[0].workflow_stage == "data_loaded"
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
                '{"workflow_stage":"empty","tool_name":"switch_panel",'
                '"parameters":{"panel_name":"training"}}'
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
        "confirmation",
        "execution_boundary_suppressed",
    }


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
        "max_format_recovery_attempts": 2,
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
                                "origin": "host_parameter_origin",
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

    assert report["schema_version"] == "xbrainlab.stable_assistant_model_eval.v11"
    assert report["generation_attempt_count"] == 0
    assert report["generation_trace"] == []
    assert report["suite_summary"]["positive"]["case_count"] == 36
    assert report["suite_summary"]["challenge"]["case_count"] == 14
    assert report["summary"] == {
        "expected_case_count": 50,
        "case_count": 50,
        "passed_count": 36,
        "failed_count": 14,
        "complete": True,
        "passed": False,
    }
    assert report["precision_summary"] == {
        "expected_case_count": 24,
        "case_count": 24,
        "passed_count": 24,
        "failed_count": 0,
        "complete": True,
        "passed": True,
    }
    assert report["raw_model_gate"]["passed"] is True
    # Legacy rows without controller observations cannot satisfy the v11 gate.
    assert report["host_safety_gate"]["passed"] is False
    assert report["direct_host_admission_gate"] == {
        "required": 5,
        "passed": 5,
        "complete": True,
        "status": "passed",
    }
    assert report["product_outcome_gate"]["passed"] is True
    assert report["candidate_gate"]["passed"] is False
    assert report["first_generation_summary"] == {
        "positive": {"case_count": 36, "passed_count": 36, "failed_count": 0},
        "challenge": {"case_count": 14, "passed_count": 14, "failed_count": 0},
        "precision": {"case_count": 24, "passed_count": 24, "failed_count": 0},
        "clarification": {"case_count": 7, "passed_count": 7, "failed_count": 0},
    }
    assert report["clarification_summary"] == {
        "expected_case_count": 7,
        "case_count": 7,
        "passed_count": 7,
        "failed_count": 0,
        "complete": True,
        "passed": True,
    }


def test_challenge_score_requires_strict_response_envelope_and_message_contract() -> (
    None
):
    case = next(
        item
        for item in load_challenge_cases(DEFAULT_CHALLENGES)
        if item.case_id == "missing_bandpass_bounds_01"
    )
    registry = target_tool_registry()
    valid = (
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"Please provide the bandpass low and high cutoffs."}}'
    )

    assert score_challenge_response(case, valid, registry).passed is True

    failures = (
        (
            '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
            '"parameters":{"message":"請補充設定。"}}'
        ),
        (
            '{"workflow_stage":"data_loaded","tool_name":"apply_bandpass_filter",'
            '"parameters":{"low_freq":4,"high_freq":38}}'
        ),
        (
            '{"workflow_stage":"preprocessed","tool_name":"respond_to_user",'
            '"parameters":{"message":"請提供 bandpass 的 low 和 high 頻率。"}}'
        ),
    )
    for response in failures:
        assert score_challenge_response(case, response, registry).passed is False

    lifecycle_case = next(
        item
        for item in load_challenge_cases(DEFAULT_CHALLENGES)
        if item.case_id == "start_before_setup_01"
    )
    false_completion = (
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"Training has been initiated; finish setup '
        'before starting."}}'
    )
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
    assert messages[-1] == {"role": "user", "content": case.user_input}


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
    """Precision scoring must include the state card that production publishes."""
    registry = target_tool_registry()
    case = next(
        item
        for item in load_precision_cases(DEFAULT_PRECISION_CASES)
        if item.case_id == "missing_bandpass_en"
    )

    messages = build_case_messages(case, registry)

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert '"type":"state_card"' in messages[1]["content"]
    assert messages[-1] == {"role": "user", "content": case.user_input}


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
            "user",
        ]
        assert '"type":"state_card"' in raw_messages[1]["content"]
        assert [message["role"] for message in processed_messages] == [
            "system",
            "user",
            "assistant",
            "user",
        ]
        assert (
            processed_messages[2]["content"] == MODEL_UNTRUSTED_CONTEXT_BOUNDARY_MESSAGE
        )


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

    assert [message["role"] for message in messages] == ["system", "user", "user"]
    assert '"type":"state_card"' in messages[1]["content"]
    assert '"type":"runtime_context"' in messages[1]["content"]
    assert messages[-1] == {"role": "user", "content": case.user_input}
    processed_messages = LocalBackend(LLMConfig())._process_messages_for_template(
        messages
    )
    assert [message["role"] for message in processed_messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert processed_messages[2]["content"] == MODEL_UNTRUSTED_CONTEXT_BOUNDARY_MESSAGE


def test_precision_exact_unavailable_call_uses_backend_reason_at_attempt_boundary() -> (
    None
):
    registry = target_tool_registry()
    case = next(
        case
        for case in load_precision_cases(DEFAULT_PRECISION_CASES)
        if case.case_id == "epochs_before_data_en"
    )
    response = '{"workflow_stage":"empty","tool_name":"create_epochs","parameters":{}}'

    score = score_precision_response(case, response, registry)

    assert score.passed is True
    assert score.product_outcome is not None
    assert score.product_outcome.disposition == "blocked"
    assert score.product_outcome.message is not None
    assert "Load raw data before creating EEG epochs." in score.product_outcome.message


def test_score_accepts_only_exact_stage_tool_and_schema() -> None:
    registry = target_tool_registry()
    case = next(
        item
        for item in load_target_cases(DEFAULT_CASES)
        if item.case_id == "switch_panel_01"
    )
    valid = (
        '{"workflow_stage":"empty","tool_name":"switch_panel",'
        '"parameters":{"panel_name":"evaluation"}}'
    )

    assert score_model_response(case, valid, registry).passed is True

    failures = (
        '{"workflow_stage":"empty","tool_name":"query_state","parameters":{}}',
        (
            '{"workflow_stage":"trained","tool_name":"switch_panel",'
            '"parameters":{"panel_name":"evaluation"}}'
        ),
        (
            '{"workflow_stage":"empty","tool_name":"switch_panel",'
            '"parameters":{"panel_name":"dashboard"}}'
        ),
        (
            '{"workflow_stage":"empty","tool_name":"switch_panel",'
            '"parameters":{"panel_name":"evaluation","extra":true}}'
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

    assert report["summary"] == {
        "expected_case_count": 50,
        "case_count": 0,
        "passed_count": 0,
        "failed_count": 0,
        "complete": False,
        "passed": False,
    }


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
    response = (
        '{"workflow_stage":"data_loaded","tool_name":"resample_data",'
        '"parameters":{"rate":256}}'
    )

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
    response = (
        '{"workflow_stage":"data_loaded","tool_name":"apply_bandpass_filter",'
        '"parameters":{"low_freq":4,"high_freq":38}}'
    )

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

    assert report["candidate_gate"] == {
        "raw_model": True,
        "host_safety": False,
        "direct_host_admission": False,
        "product_outcome": False,
        "capture_integrity": True,
        "passed": False,
    }
    assert report["host_safety_gate"]["continuation_boundaries"] == {
        "not_counted_in_model_report": [
            "cancel",
            "topic_switch",
            "stale_receipt",
            "different_tool",
            "partial_reply",
            "multi_action",
        ],
        "report_status": "not_measured_by_this_model_report",
        "external_evidence": "controller unit/integration coverage required",
    }
    assert report["summary"]["passed"] is False
    assert report["precision_summary"] == {
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
        run_eval=MagicMock(return_value={"summary": {"passed": True}}),
        _experiment_identity=MagicMock(return_value={"source_sha": "test"}),
        _write_report=write_report,
    ):
        assert evaluator.main(argv) == 0

    assert write_report.call_args.args[1]["invocation"] == {
        "argv": argv,
        "working_directory_is_repository_root": True,
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
            lambda _messages, stage=case.workflow_stage: json.dumps(
                {
                    "workflow_stage": stage,
                    "tool_name": "respond_to_user",
                    "parameters": {"message": "Please clarify the EEG workflow step."},
                }
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
    response = json.dumps(
        {
            "workflow_stage": case.workflow_stage,
            "tool_name": case.expected_tool,
            "parameters": case.expected_parameters,
        }
    )
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


def test_first_turn_no_action_terminal_is_controller_observed_and_side_effect_free() -> (
    None
):
    registry = target_tool_registry()
    case = next(
        item
        for item in load_precision_cases(DEFAULT_PRECISION_CASES)
        if item.case_id == "negated_import_en"
    )
    response = (
        '{"workflow_stage":"empty","tool_name":"import_eeg_data","parameters":{}}'
    )

    trajectory = evaluate_case_trajectory(case, registry, lambda _messages: response)

    assert trajectory.host_admission is not None
    assert trajectory.host_admission["attempt_action"] == "intent_blocked"
    assert trajectory.host_admission["result_error_type"] == "intent_mismatch"
    assert (
        trajectory.host_admission["result_policy"] == "import_eeg_data_positive_origin"
    )
    assert trajectory.product_terminal is not None
    assert trajectory.product_terminal["kind"] == "blocked"
    assert all(
        trajectory.product_terminal[key] is False
        for key in (
            "confirmation_observed",
            "execution_boundary_reached",
            "gui_handoff_reached",
            "application_service_called",
            "tool_executor_called",
            "state_mutation_observed",
        )
    )


def test_first_turn_typed_and_origin_guard_receipts_are_controller_admissions() -> None:
    registry = target_tool_registry()
    source = next(
        item
        for item in load_precision_cases(DEFAULT_PRECISION_CASES)
        if item.case_id == "missing_resample_en"
    )
    typed = (
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"What resampling rate should I use?",'
        '"pending_action":"resample_data","missing_inputs":["rate"]}}'
    )
    guessed = (
        '{"workflow_stage":"data_loaded","tool_name":"resample_data",'
        '"parameters":{"rate":128}}'
    )

    typed_trajectory = evaluate_case_trajectory(
        source, registry, lambda _messages: typed
    )
    guarded_trajectory = evaluate_case_trajectory(
        source, registry, lambda _messages: guessed
    )

    assert typed_trajectory.host_admission == {
        "path": "typed_receipt",
        "attempt_action": None,
        "receipt_created": True,
        "receipt_origin": "model_typed",
        "result_error_type": None,
        "result_policy": None,
    }
    assert guarded_trajectory.host_admission is not None
    assert guarded_trajectory.host_admission["attempt_action"] == "respond"
    assert guarded_trajectory.host_admission["receipt_created"] is True
    assert (
        guarded_trajectory.host_admission["receipt_origin"] == "host_parameter_origin"
    )


def test_first_turn_precision_product_score_does_not_call_static_coordinator_surrogate(
    monkeypatch,
) -> None:
    registry = target_tool_registry()
    case = next(
        item
        for item in load_precision_cases(DEFAULT_PRECISION_CASES)
        if item.case_id == "general_en"
    )
    response = (
        '{"workflow_stage":"empty","tool_name":"respond_to_user",'
        '"parameters":{"message":"I can explain the EEG workflow."}}'
    )
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
                "receipt_origin": "host_parameter_origin" if index == 0 else None,
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

    assert report["raw_model_gate"]["passed"] is True
    assert report["host_safety_gate"]["explicit_parameter_origin"]["passed"] == 9
    assert report["host_safety_gate"]["missing_parameter_origin"]["passed"] == 4
    assert report["host_safety_gate"]["passed"] is False
