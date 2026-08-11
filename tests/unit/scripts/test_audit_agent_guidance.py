from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import yaml

from scripts.dev import audit_agent_guidance
from scripts.dev.audit_agent_guidance import (
    ROUTING_OUTPUT_SCHEMA,
    EvalRecord,
    RoutingCase,
    _error_from_jsonl,
    _usage_from_jsonl,
    acceptance_summary,
    build_codex_command,
    run_variant,
    score_human_review,
    score_variant,
)


def test_codex_command_pins_model_config_and_read_only_boundary(tmp_path: Path) -> None:
    command = build_codex_command(
        repo_root=tmp_path,
        model="gpt-5.6-sol",
        reasoning_effort="xhigh",
        schema_path=tmp_path / "schema.json",
        final_path=tmp_path / "final.json",
        prompt="route only",
    )

    assert command[:2] == ["codex", "exec"]
    assert command[2:4] == ["--model", "gpt-5.6-sol"]
    assert "--ignore-user-config" in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert "--ephemeral" in command
    assert "--json" in command
    assert 'model_reasoning_effort="xhigh"' in command
    assert 'approval_policy="never"' in command
    assert "--output-schema" in command
    assert "--output-last-message" in command


def test_usage_parser_takes_final_cumulative_token_values() -> None:
    events = (
        '{"usage": {"input_tokens": 100, "output_tokens": 5}}\n'
        '{"usage": {"input_tokens": 140, "output_tokens": 12}}\n'
    )

    assert _usage_from_jsonl(events) == (140, 12)


def test_response_schema_uses_only_supported_array_contract() -> None:
    secondary = ROUTING_OUTPUT_SCHEMA["properties"]["secondary_skills"]

    assert "uniqueItems" not in secondary


def test_jsonl_error_parser_reports_api_failure_instead_of_stderr_notice() -> None:
    events = (
        '{"type":"error","message":"invalid_json_schema: uniqueItems is not permitted"}\n'
        '{"type":"turn.failed","error":{"message":"request failed"}}\n'
    )

    assert _error_from_jsonl(events) == (
        "invalid_json_schema: uniqueItems is not permitted"
    )


def test_variant_preflight_stops_before_parallel_fanout(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[str, int]] = []

    async def failed_case(**kwargs: object) -> EvalRecord:
        case = kwargs["case"]
        assert isinstance(case, RoutingCase)
        repeat = kwargs["repeat"]
        assert isinstance(repeat, int)
        calls.append((case.id, repeat))
        return EvalRecord(
            variant="baseline",
            run_fingerprint="test",
            case_id=case.id,
            repeat=repeat,
            returncode=1,
            elapsed_seconds=0.1,
            input_tokens=None,
            output_tokens=None,
            response=None,
            error="invalid schema",
        )

    monkeypatch.setattr(audit_agent_guidance, "_git_sha", lambda _root: "abc")
    monkeypatch.setattr(
        audit_agent_guidance,
        "_guidance_digest",
        lambda _root: "digest",
    )
    monkeypatch.setattr(audit_agent_guidance, "_run_case", failed_case)
    cases = (
        RoutingCase("first", "one", "positive", None, (), (), "current_truth"),
        RoutingCase("second", "two", "positive", None, (), (), "current_truth"),
    )

    with pytest.raises(RuntimeError, match="baseline preflight failed: invalid schema"):
        asyncio.run(
            run_variant(
                variant="baseline",
                repo_root=tmp_path,
                cases=cases,
                output_dir=tmp_path / "output",
                repeats=3,
                max_concurrency=3,
                model="gpt-5.6-sol",
                reasoning_effort="xhigh",
                timeout_seconds=30,
            )
        )

    assert calls == [("first", 1)]


def test_variant_fails_before_next_variant_when_any_record_is_invalid(
    tmp_path: Path,
    monkeypatch,
) -> None:
    async def run_case(**kwargs: object) -> EvalRecord:
        case = kwargs["case"]
        assert isinstance(case, RoutingCase)
        error = "timed out" if case.id == "second" else None
        return EvalRecord(
            variant="baseline",
            run_fingerprint="test",
            case_id=case.id,
            repeat=1,
            returncode=1 if error else 0,
            elapsed_seconds=0.1,
            input_tokens=None if error else 10,
            output_tokens=None if error else 2,
            response=None
            if error
            else {
                "primary_skill": None,
                "secondary_skills": [],
                "authority_class": "current_truth",
                "reason": "no skill",
            },
            error=error,
        )

    monkeypatch.setattr(audit_agent_guidance, "_git_sha", lambda _root: "abc")
    monkeypatch.setattr(
        audit_agent_guidance,
        "_guidance_digest",
        lambda _root: "digest",
    )
    monkeypatch.setattr(audit_agent_guidance, "_run_case", run_case)
    cases = (
        RoutingCase("first", "one", "positive", None, (), (), "current_truth"),
        RoutingCase("second", "two", "positive", None, (), (), "current_truth"),
    )

    with pytest.raises(RuntimeError, match="baseline produced 1 invalid record"):
        asyncio.run(
            run_variant(
                variant="baseline",
                repo_root=tmp_path,
                cases=cases,
                output_dir=tmp_path / "output",
                repeats=1,
                max_concurrency=2,
                model="gpt-5.6-sol",
                reasoning_effort="xhigh",
                timeout_seconds=30,
            )
        )


def test_case_runner_closes_stdin_and_excludes_queue_wait_from_latency(
    tmp_path: Path,
    monkeypatch,
) -> None:
    clock = {"value": 0.0}
    captured: dict[str, object] = {}

    class DelayedSemaphore:
        async def __aenter__(self) -> None:
            clock["value"] = 100.0

        async def __aexit__(self, *_args: object) -> None:
            return None

    class CompletedProcess:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return b'{"usage":{"input_tokens":10,"output_tokens":2}}\n', b""

    async def create_process(*command: str, **kwargs: object) -> CompletedProcess:
        captured["stdin"] = kwargs.get("stdin")
        final_path = Path(command[command.index("--output-last-message") + 1])
        final_path.write_text(
            json.dumps(
                {
                    "primary_skill": None,
                    "secondary_skills": [],
                    "authority_class": "current_truth",
                    "reason": "no skill needed",
                }
            ),
            encoding="utf-8",
        )
        return CompletedProcess()

    monkeypatch.setattr(
        audit_agent_guidance.asyncio,
        "create_subprocess_exec",
        create_process,
    )
    monkeypatch.setattr(
        audit_agent_guidance.time,
        "monotonic",
        lambda: clock["value"],
    )
    schema_path = tmp_path / "schema.json"
    schema_path.write_text("{}", encoding="utf-8")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    case = RoutingCase(
        id="stdin-contract",
        prompt="read current truth",
        category="negative",
        expected_primary=None,
        allowed_secondary=(),
        forbidden_skills=(),
        expected_authority_class="current_truth",
    )

    record = asyncio.run(
        audit_agent_guidance._run_case(
            semaphore=DelayedSemaphore(),
            variant="candidate",
            run_fingerprint="test",
            case=case,
            repeat=1,
            repo_root=tmp_path,
            output_dir=output_dir,
            schema_path=schema_path,
            model="gpt-5.6-sol",
            reasoning_effort="xhigh",
            timeout_seconds=30,
        )
    )

    assert captured["stdin"] is asyncio.subprocess.DEVNULL
    assert record.elapsed_seconds == 0.0
    assert record.error is None


def test_case_runner_retries_matching_failed_record(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    record_path = output_dir / "retry-case-r1.record.json"
    record_path.write_text(
        json.dumps(
            {
                "variant": "candidate",
                "run_fingerprint": "test",
                "case_id": "retry-case",
                "repeat": 1,
                "returncode": 1,
                "elapsed_seconds": 30.0,
                "input_tokens": None,
                "output_tokens": None,
                "response": None,
                "error": "timed out",
            }
        ),
        encoding="utf-8",
    )
    launched = {"value": False}

    class CompletedProcess:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return b'{"usage":{"input_tokens":10,"output_tokens":2}}\n', b""

    async def create_process(*command: str, **_kwargs: object) -> CompletedProcess:
        launched["value"] = True
        final_path = Path(command[command.index("--output-last-message") + 1])
        final_path.write_text(
            json.dumps(
                {
                    "primary_skill": None,
                    "secondary_skills": [],
                    "authority_class": "current_truth",
                    "reason": "retried",
                }
            ),
            encoding="utf-8",
        )
        return CompletedProcess()

    monkeypatch.setattr(
        audit_agent_guidance.asyncio,
        "create_subprocess_exec",
        create_process,
    )
    case = RoutingCase(
        "retry-case",
        "read truth",
        "negative",
        None,
        (),
        (),
        "current_truth",
    )

    record = asyncio.run(
        audit_agent_guidance._run_case(
            semaphore=asyncio.Semaphore(1),
            variant="candidate",
            run_fingerprint="test",
            case=case,
            repeat=1,
            repo_root=tmp_path,
            output_dir=output_dir,
            schema_path=tmp_path / "schema.json",
            model="gpt-5.6-sol",
            reasoning_effort="xhigh",
            timeout_seconds=30,
        )
    )

    assert launched["value"] is True
    assert record.error is None


def test_variant_scoring_enforces_primary_secondary_forbidden_and_authority() -> None:
    cases = (
        RoutingCase(
            id="positive",
            prompt="review code",
            category="positive",
            expected_primary="code-reviewer",
            allowed_secondary=("architecture-reviewer",),
            forbidden_skills=("mcp-adapter-reviewer",),
            expected_authority_class="skill_trigger",
        ),
        RoutingCase(
            id="negative",
            prompt="read current status",
            category="negative",
            expected_primary=None,
            allowed_secondary=(),
            forbidden_skills=("mcp-adapter-reviewer",),
            expected_authority_class="current_truth",
        ),
    )
    records = (
        EvalRecord(
            variant="candidate",
            run_fingerprint="test",
            case_id="positive",
            repeat=1,
            returncode=0,
            elapsed_seconds=2.0,
            input_tokens=100,
            output_tokens=10,
            response={
                "primary_skill": "code-reviewer",
                "secondary_skills": ["architecture-reviewer"],
                "authority_class": "skill_trigger",
                "reason": "diff review",
            },
            error=None,
        ),
        EvalRecord(
            variant="candidate",
            run_fingerprint="test",
            case_id="negative",
            repeat=1,
            returncode=0,
            elapsed_seconds=4.0,
            input_tokens=120,
            output_tokens=8,
            response={
                "primary_skill": "mcp-adapter-reviewer",
                "secondary_skills": [],
                "authority_class": "current_truth",
                "reason": "incorrect incidental trigger",
            },
            error=None,
        ),
    )

    score = score_variant(cases, records)

    assert score["primary_accuracy"] == 0.5
    assert score["false_positive_rate"] == 1.0
    assert score["forbidden_skill_accuracy"] == 0.5
    assert score["authority_accuracy"] == 1.0
    assert score["median_input_tokens"] == 110.0
    assert score["median_latency_seconds"] == 3.0


def test_acceptance_summary_requires_efficiency_and_routing_thresholds() -> None:
    baseline = {
        "median_input_tokens": 1000,
        "median_latency_seconds": 10,
    }
    candidate = {
        "primary_accuracy": 0.96,
        "false_positive_rate": 0.04,
        "overlap_primary_accuracy": 0.92,
        "mcp_explicit_accuracy": 1.0,
        "mcp_incidental_rate": 0.0,
        "authority_accuracy": 1.0,
        "average_selected_skills_single_scope": 1.1,
        "median_input_tokens": 790,
        "median_latency_seconds": 11,
    }

    summary = acceptance_summary(baseline, candidate)

    assert summary["automatic_pass"] is True
    assert summary["token_reduction"] == 0.21
    assert summary["latency_change"] == 0.1
    assert summary["human_review_required"]["sample_size"] == 12


def test_invalid_null_response_fails_primary_accuracy() -> None:
    case = RoutingCase(
        id="null-case",
        prompt="read current truth",
        category="negative",
        expected_primary=None,
        allowed_secondary=(),
        forbidden_skills=(),
        expected_authority_class="current_truth",
    )
    record = EvalRecord(
        variant="candidate",
        run_fingerprint="test",
        case_id=case.id,
        repeat=1,
        returncode=1,
        elapsed_seconds=1.0,
        input_tokens=None,
        output_tokens=None,
        response=None,
        error="failed",
    )

    score = score_variant((case,), (record,))

    assert score["valid_response_rate"] == 0.0
    assert score["primary_accuracy"] == 0.0


def test_blind_human_review_scores_agreement_and_updates_summary(
    tmp_path: Path,
) -> None:
    samples = [
        {
            "case_id": f"case-{index}",
            "A_pass": True,
            "B_pass": False,
        }
        for index in range(12)
    ]
    keys = [
        {
            "case_id": f"case-{index}",
            "A_auto_pass": True,
            "B_auto_pass": False,
        }
        for index in range(12)
    ]
    sample_path = tmp_path / "sample.yaml"
    key_path = tmp_path / "key.json"
    summary_path = tmp_path / "summary.json"
    sample_path.write_text(
        yaml.safe_dump({"samples": samples}),
        encoding="utf-8",
    )
    key_path.write_text(json.dumps({"key": keys}), encoding="utf-8")
    summary_path.write_text(
        json.dumps({"acceptance": {"automatic_pass": True}}),
        encoding="utf-8",
    )

    result = score_human_review(
        sample_path=sample_path,
        key_path=key_path,
        summary_path=summary_path,
    )

    assert result["agreement"] == 1.0
    assert result["pass"] is True
    updated = json.loads(summary_path.read_text(encoding="utf-8"))
    assert updated["acceptance"]["overall_pass"] is True
