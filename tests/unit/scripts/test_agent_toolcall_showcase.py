from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from scripts.dev.agent_toolcall_showcase import cli
from scripts.dev.agent_toolcall_showcase.cases import (
    SHOWCASE_CASES,
    filter_cases,
)
from scripts.dev.agent_toolcall_showcase.report import (
    render_stdout,
    sanitize_payload,
)
from scripts.dev.agent_toolcall_showcase.runner import (
    DIAGNOSTIC_DISCLAIMER,
    SCHEMA_VERSION,
    ShowcaseContractError,
    ShowcaseRunner,
    current_source_commit,
    current_source_fingerprint,
    require_source_stability,
    resumable_passed_cases,
    resume_case_matches,
    showcase_limitations,
    terminal_outcome_present,
)
from scripts.dev.agent_toolcall_showcase.selector import DeterministicSelector
from XBrainLab.llm.tools.application_surface import (
    AssistantSettingConfirmation,
    AuthoritativeConfirmationParameter,
)
from XBrainLab.llm.tools.authorized_paths import authorize_existing_path


def _case(case_id: str):
    return next(case for case in SHOWCASE_CASES if case.case_id == case_id)


def _missing_terminal_payload(case_id: str) -> dict[str, Any]:
    case = _case(case_id)
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "product_showcase_diagnostic",
        "disclaimer": DIAGNOSTIC_DISCLAIMER,
        "run": {
            "status": "passed",
            "mode": "deterministic",
            "duration_ms": 1.0,
            "case_count": 1,
        },
        "summary": {
            "status": "passed",
            "total": 1,
            "passed": 1,
            "failed": 0,
            "missing_terminal_outcomes": 0,
        },
        "generated_data": {"written": False, "downloaded": False},
        "limitations": [DIAGNOSTIC_DISCLAIMER],
        "cases": [
            {
                "case_id": case.case_id,
                "case_identity": case.identity(),
                "area": case.area,
                "prompt": case.prompt,
                "selected_tool": case.tool_name,
                "terminal": {},
                "failures": [],
                "pass": True,
            }
        ],
    }


def _deterministic_selector_metadata() -> dict[str, Any]:
    return {
        "mode": "deterministic",
        "selector_id": "deterministic_case_selector",
        "selector_version": 1,
        "model_owned": False,
        "description": "Human-readable prose is not selector identity.",
    }


def test_showcase_limitations_match_the_actual_selector_mode() -> None:
    deterministic = showcase_limitations("deterministic")
    granite = showcase_limitations("real_granite")

    assert any("Deterministic mode" in item for item in deterministic)
    assert not any("Real Granite mode" in item for item in deterministic)
    assert any("Real Granite mode" in item for item in granite)
    assert not any("Deterministic mode" in item for item in granite)


def test_showcase_rejects_source_drift_during_a_run() -> None:
    require_source_stability(
        start_commit="commit-a",
        start_fingerprint="fingerprint-a",
        end_commit="commit-a",
        end_fingerprint="fingerprint-a",
    )

    with pytest.raises(ShowcaseContractError, match="source changed during the run"):
        require_source_stability(
            start_commit="commit-a",
            start_fingerprint="fingerprint-a",
            end_commit="commit-a",
            end_fingerprint="fingerprint-b",
        )

    with pytest.raises(ShowcaseContractError, match="source changed during the run"):
        require_source_stability(
            start_commit="commit-a",
            start_fingerprint="fingerprint-a",
            end_commit="commit-b",
            end_fingerprint="fingerprint-a",
        )


def _granite_selector_metadata() -> dict[str, Any]:
    return {
        "mode": "real_granite",
        "selector_id": "ibm_granite_product_runtime",
        "selector_version": 1,
        "model_owned": True,
        "model_id": "ibm-granite/granite-3.3-2b-instruct",
        "revision": "revision-a",
        "device": "cuda",
        "offline": True,
        "silent_fallback": False,
    }


def _resumable_command_case(case_id: str) -> dict[str, Any]:
    case = _case(case_id)
    return {
        "case_id": case.case_id,
        "case_identity": case.identity(),
        "prompt_identity": case.prompt_identity(),
        "selected_tool": case.tool_name,
        "selected_parameters": dict(case.params),
        "verification": {
            "status": "verified",
            "coordinator_action": "execute",
            "valid": True,
        },
        "confirmation": None,
        "handoff": None,
        "command_result": {"ok": True, "error_type": "none"},
        "changed_state": dict.fromkeys(case.expected_changed_state, True),
        "retry": None,
        "terminal": {"kind": "command_result", "status": "ok"},
        "duration_ms": 1.0,
        "failures": [],
        "pass": True,
    }


def _resume_payload(
    case_result: dict[str, Any],
    *,
    commit: str = "source-commit-a",
    source_fingerprint: str = "source-fingerprint-a",
    selector: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = selector or _deterministic_selector_metadata()
    return {
        "schema_version": SCHEMA_VERSION,
        "run": {
            "status": "passed",
            "mode": metadata["mode"],
            "commit": commit,
            "source_fingerprint": source_fingerprint,
            "selector": metadata,
        },
        "summary": {"status": "passed"},
        "cases": [case_result],
    }


def test_catalog_filter_alias_area_and_list_output(capsys) -> None:
    case_ids = {case.case_id for case in SHOWCASE_CASES}
    assert len(case_ids) == len(SHOWCASE_CASES)
    assert {
        "settings.complete_training_approved",
        "training.start_cancelled",
        "safety.stale_revision",
        "recovery.runtime_error_retry",
    } <= case_ids
    assert {case.area for case in SHOWCASE_CASES} >= {
        "data import/navigation",
        "preprocess",
        "epoch",
        "split",
        "model/training settings",
        "start/stop training",
        "evaluation and saliency",
    }
    assert [case.case_id for case in filter_cases(["navigation.open_preprocess"])] == [
        "navigation.list_source_folder"
    ]
    assert all(
        case.area == "evaluation and saliency"
        for case in cli._selected_cases(
            case_patterns=[],
            area_patterns=["evaluation"],
        )
    )

    assert cli.main(["--list-cases", "--case", "navigation.open_preprocess"]) == 0
    output = capsys.readouterr().out
    assert "navigation.list_source_folder" in output
    assert "not a thesis benchmark" in output


def test_redaction_preserves_all_cases_and_stdout_defaults_to_compact_trace() -> None:
    payload = {
        "disclaimer": DIAGNOSTIC_DISCLAIMER,
        "run": {"status": "passed", "mode": "deterministic", "duration_ms": 2.0},
        "summary": {
            "status": "passed",
            "total": 18,
            "passed": 18,
            "failed": 0,
            "missing_terminal_outcomes": 0,
        },
        "cases": [
            {
                "case_id": f"case-{index}",
                "area": "test",
                "prompt": "Read /home/private/person/recording.edf",
                "api_key": "sk-this-must-not-appear",  # pragma: allowlist secret
                "diagnostic": (
                    "Traceback (most recent call last):\n"
                    "  File /home/private/source.py, line 1\n"
                    "RuntimeError: private failure"
                ),
                "selected_tool": "query_state",
                "terminal": {"kind": "command_result", "status": "ok"},
                "duration_ms": 1.0,
                "pass": True,
            }
            for index in range(18)
        ],
    }

    sanitized = sanitize_payload(payload)
    encoded = json.dumps(sanitized)
    assert len(sanitized["cases"]) == 18
    assert "/home/private" not in encoded
    assert "sk-this-must-not-appear" not in encoded
    assert "Traceback" not in encoded
    assert "[REDACTED_STACK]" in encoded

    concise = render_stdout(sanitized, include_details=False)
    detailed = render_stdout(sanitized, include_details=True)
    assert "[PASS] case-0" in concise
    assert "## case-0" not in concise
    assert "## case-0" in detailed


def test_safe_parameter_projection_is_field_aware_for_host_wrappers(
    tmp_path: Path,
) -> None:
    private_dir = tmp_path / "private-subject"
    private_dir.mkdir()
    source = private_dir / "recording.edf"
    source.write_text("fixture", encoding="utf-8")
    authorized_source = authorize_existing_path(
        source,
        authorized_root=tmp_path,
        expected_kind="file",
    )
    confirmation = AssistantSettingConfirmation(
        tool_name="set_model",
        params_fingerprint="opaque-fingerprint-must-not-flow",
        publication_generation=17,
    )

    sanitized = sanitize_payload(
        {
            "selected_parameters": {
                "source_path": authorized_source,
                "output_directory": AuthoritativeConfirmationParameter(
                    str(private_dir / "training-output")
                ),
                "checkpoint_policy": AuthoritativeConfirmationParameter(
                    "Every 5 epochs"
                ),
                "assistant_setting_confirmation": confirmation,
            }
        }
    )
    encoded = json.dumps(sanitized, sort_keys=True)

    assert "[UNSUPPORTED_VALUE]" not in encoded
    assert str(tmp_path) not in encoded
    assert "private-subject" not in encoded
    assert "recording.edf" not in encoded
    assert "opaque-fingerprint-must-not-flow" not in encoded
    assert "Every 5 epochs" in encoded
    assert sanitized["selected_parameters"]["assistant_setting_confirmation"] == {
        "kind": "approved_confirmation",
        "tool_name": "set_model",
        "publication_generation": 17,
    }


def test_concise_stdout_exposes_the_tool_decision_and_execution_path() -> None:
    payload = {
        "disclaimer": DIAGNOSTIC_DISCLAIMER,
        "run": {"status": "passed", "mode": "deterministic", "duration_ms": 8.0},
        "summary": {
            "status": "passed",
            "total": 3,
            "passed": 3,
            "failed": 0,
            "missing_terminal_outcomes": 0,
        },
        "cases": [
            {
                "case_id": "preprocess.standard",
                "title": "Apply standard preprocessing",
                "prompt": "Apply a 4 to 40 Hz bandpass.",
                "admission": {"action": "execute"},
                "exposed_tool_schema_names": ["apply_standard_preprocess"],
                "selection": {"owner": "deterministic_case_selector"},
                "selected_tool": "apply_standard_preprocess",
                "selected_parameters": {"l_freq": 4.0, "h_freq": 40.0},
                "verification": {
                    "status": "verified",
                    "coordinator_action": "execute",
                    "valid": True,
                },
                "confirmation": None,
                "retry": None,
                "command_result": {
                    "ok": True,
                    "error_type": "none",
                    "message": "Preprocessing completed.",
                },
                "terminal": {"kind": "command_result", "status": "ok"},
                "duration_ms": 4.5,
                "pass": True,
            },
            {
                "case_id": "blocked.preprocess_without_data",
                "title": "Block preprocessing before import",
                "prompt": "Preprocess now.",
                "admission": {"action": "blocked"},
                "exposed_tool_schema_names": [],
                "selection": {"owner": None},
                "selected_tool": "apply_standard_preprocess",
                "selected_parameters": {"l_freq": 4.0},
                "verification": {
                    "status": "request_admission_blocked",
                    "coordinator_action": "capability_blocked",
                    "valid": False,
                },
                "confirmation": None,
                "retry": None,
                "command_result": {
                    "ok": False,
                    "error_type": "precondition",
                    "message": "Load data before preprocessing.",
                },
                "terminal": {"kind": "command_result", "status": "failed"},
                "duration_ms": 1.5,
                "pass": True,
            },
            {
                "case_id": "recovery.runtime_error_retry",
                "title": "Retry a recoverable runtime error",
                "prompt": "Show workflow state.",
                "admission": {"action": "execute_read_only"},
                "exposed_tool_schema_names": [],
                "selection": {"owner": None},
                "selected_tool": "query_state",
                "selected_parameters": {"query": "state"},
                "verification": {"status": "host_admitted_read_only", "valid": True},
                "confirmation": None,
                "retry": {
                    "continued": True,
                    "attempts": [
                        {"attempt": 1, "success": False},
                        {"attempt": 2, "success": True},
                    ],
                },
                "command_result": {
                    "ok": True,
                    "error_type": None,
                    "message": "Workflow state is available.",
                },
                "terminal": {"kind": "command_result", "status": "ok"},
                "duration_ms": 2.0,
                "pass": True,
            },
        ],
    }

    concise = render_stdout(payload, include_details=False)
    assert "intent=Apply standard preprocessing" in concise
    assert "prompt=Apply a 4 to 40 Hz bandpass." in concise
    assert 'exposed=["apply_standard_preprocess"]' in concise
    assert (
        'selected=apply_standard_preprocess({"h_freq": 40.0, "l_freq": 4.0})' in concise
    )
    assert "via=deterministic_case_selector" in concise
    assert "outcome=executed:ok -> command_result:ok" in concise
    assert "result=ok: Preprocessing completed." in concise
    assert "exposed=[]" in concise
    assert "via=request_admission (not model-selected)" in concise
    assert "outcome=blocked:precondition -> command_result:failed" in concise
    assert "outcome=retry[failed -> ok] -> command_result:ok" in concise
    assert "via=host_retry_fixture (not model-selected)" in concise

    detailed = render_stdout(payload, include_details=True)
    assert '- Retry: `{"attempts": ["failed", "ok"], "continued": true}`' in detailed
    assert "- Duration: `2.0ms`" in detailed


def test_missing_terminal_outcome_is_not_success_and_cli_exits_nonzero(
    monkeypatch,
    tmp_path: Path,
) -> None:
    case_id = "navigation.list_source_folder"
    payload = _missing_terminal_payload(case_id)
    assert terminal_outcome_present(payload["cases"][0]) is False

    class MissingTerminalRunner:
        def __init__(self, *, output_dir: Path, selector: Any) -> None:
            del output_dir
            self.selector = selector

        def run(self, cases, **kwargs):
            del cases, kwargs
            self.selector.close()
            return payload

    monkeypatch.setattr(cli, "ShowcaseRunner", MissingTerminalRunner)
    json_path = tmp_path / "failed.json"
    markdown_path = tmp_path / "failed.md"
    exit_code = cli.main(
        [
            "--case",
            case_id,
            "--json-out",
            str(json_path),
            "--markdown-out",
            str(markdown_path),
        ]
    )

    assert exit_code == 1
    artifact = json.loads(json_path.read_text())
    assert artifact["summary"]["status"] == "failed"
    assert artifact["summary"]["missing_terminal_outcomes"] == 1
    assert artifact["cases"][0]["pass"] is False
    assert any(
        "Missing authoritative terminal outcome" in failure
        for failure in artifact["cases"][0]["failures"]
    )


def test_resume_requires_exact_prompt_and_case_identity_and_current_semantics(
    tmp_path: Path,
) -> None:
    case = _case("navigation.list_source_folder")
    prior = _resumable_command_case(case.case_id)
    payload = _resume_payload(prior)

    retained = resumable_passed_cases(
        payload,
        expected_cases=[case],
        expected_source_commit="source-commit-a",
        expected_source_fingerprint="source-fingerprint-a",
        expected_selector=_deterministic_selector_metadata(),
    )
    assert set(retained) == {case.case_id}
    assert resume_case_matches(case, retained[case.case_id]) is True
    assert (
        resume_case_matches(
            replace(case, prompt="A changed prompt must invalidate resume."),
            retained[case.case_id],
        )
        is False
    )
    changed_prompt_identity = dict(prior)
    changed_prompt_identity["prompt_identity"] = "stale-prompt"
    assert not resume_case_matches(case, changed_prompt_identity)

    arbitrary = deepcopy(prior)
    arbitrary.update(
        {
            "unreviewed_key": "INJECTED RESUME PROSE",
            "user_visible_presentation": "INJECTED RESUME PROSE",
            "failures": ["INJECTED RESUME PROSE"],
        }
    )
    arbitrary["selection"] = {
        "owner": "deterministic_case_selector",
        "raw_output": "INJECTED RESUME PROSE",
    }
    arbitrary["selected_parameters"] = {"directory": "INJECTED RESUME PROSE"}
    arbitrary["command_result"]["message"] = "INJECTED RESUME PROSE"
    retained = resumable_passed_cases(
        _resume_payload(arbitrary),
        expected_cases=[case],
        expected_source_commit="source-commit-a",
        expected_source_fingerprint="source-fingerprint-a",
        expected_selector=_deterministic_selector_metadata(),
    )
    retained_case = retained[case.case_id]
    assert retained_case["_resume_identity"] == {
        "source_commit": "source-commit-a",
        "source_fingerprint": "source-fingerprint-a",
        "selector": {
            "mode": "deterministic",
            "selector_id": "deterministic_case_selector",
            "selector_version": 1,
            "model_owned": False,
        },
    }
    assert "unreviewed_key" not in retained_case
    assert "user_visible_presentation" not in retained_case
    assert "failures" not in retained_case
    assert "raw_output" not in retained_case.get("selection", {})
    assert "message" not in retained_case["command_result"]
    assert "INJECTED RESUME PROSE" not in json.dumps(retained_case)

    retained_for_run = deepcopy(retained)
    retained_for_run[case.case_id]["_resume_identity"].update(
        {
            "source_commit": current_source_commit(),
            "source_fingerprint": current_source_fingerprint(),
        }
    )
    resumed_artifact = ShowcaseRunner(
        output_dir=tmp_path / "resume-showcase",
        selector=DeterministicSelector(),
    ).run([case], retained_cases=retained_for_run)
    current_case = resumed_artifact["cases"][0]
    assert current_case["reused_from_resume"] is True
    assert "INJECTED RESUME PROSE" not in json.dumps(resumed_artifact)
    assert current_case["prompt"] == case.rendered_prompt(
        str((tmp_path / "resume-showcase/runtime/showcase_raw.fif").resolve())
    )
    assert "_resume_identity" not in current_case


def test_resume_fails_closed_across_source_selector_and_granite_identity() -> None:
    case = _case("navigation.list_source_folder")
    prior = _resumable_command_case(case.case_id)
    deterministic = _deterministic_selector_metadata()
    payload = _resume_payload(prior, selector=deterministic)

    with pytest.raises(ShowcaseContractError, match="source commit"):
        resumable_passed_cases(
            payload,
            expected_cases=[case],
            expected_source_commit="source-commit-b",
            expected_source_fingerprint="source-fingerprint-a",
            expected_selector=deterministic,
        )

    with pytest.raises(ShowcaseContractError, match="source fingerprint"):
        resumable_passed_cases(
            payload,
            expected_cases=[case],
            expected_source_commit="source-commit-a",
            expected_source_fingerprint="source-fingerprint-b",
            expected_selector=deterministic,
        )

    changed_selector = {**deterministic, "selector_version": 2}
    with pytest.raises(ShowcaseContractError, match="selector identity"):
        resumable_passed_cases(
            payload,
            expected_cases=[case],
            expected_source_commit="source-commit-a",
            expected_source_fingerprint="source-fingerprint-a",
            expected_selector=changed_selector,
        )

    granite = _granite_selector_metadata()
    granite_payload = _resume_payload(prior, selector=granite)
    for field, changed_value in (
        ("model_id", "different/model"),
        ("revision", "revision-b"),
    ):
        changed_granite = {**granite, field: changed_value}
        with pytest.raises(ShowcaseContractError, match="selector identity"):
            resumable_passed_cases(
                granite_payload,
                expected_cases=[case],
                expected_source_commit="source-commit-a",
                expected_source_fingerprint="source-fingerprint-a",
                expected_selector=changed_granite,
            )


def test_cli_reports_safe_actionable_resume_identity_failure(
    capsys,
    tmp_path: Path,
) -> None:
    case = _case("navigation.list_source_folder")
    resume_path = tmp_path / "stale-resume.json"
    resume_path.write_text(
        json.dumps(
            _resume_payload(
                _resumable_command_case(case.case_id),
                commit="stale-source-commit",
            )
        ),
        encoding="utf-8",
    )

    assert cli.main(["--case", case.case_id, "--resume", str(resume_path)]) == 2
    output = capsys.readouterr().out
    assert "source commit" in output.casefold()
    assert "[UNSUPPORTED_VALUE]" not in output


def test_real_granite_initialization_failure_never_falls_back(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def fail_granite(*, model_cache_dir=None):
        del model_cache_dir
        raise RuntimeError("Pinned Granite cache is unavailable at /home/private/model")

    monkeypatch.setattr(cli, "GraniteSelector", fail_granite)
    json_path = tmp_path / "granite-failed.json"
    markdown_path = tmp_path / "granite-failed.md"
    exit_code = cli.main(
        [
            "--real-granite",
            "--case",
            "navigation.list_source_folder",
            "--json-out",
            str(json_path),
            "--markdown-out",
            str(markdown_path),
        ]
    )

    artifact = json.loads(json_path.read_text())
    rendered = json_path.read_text() + markdown_path.read_text()
    assert exit_code == 1
    assert artifact["run"]["mode"] == "real_granite"
    assert artifact["summary"]["failed"] == 1
    assert artifact["cases"][0]["selection"]["owner"] == ("ibm_granite_product_runtime")
    assert "deterministic_case_selector" not in rendered
    assert "/home/private" not in rendered


def test_split_case_uses_confirmation_and_saves_deferred_specification(
    tmp_path: Path,
) -> None:
    case = _case("split.generate_trial")

    payload = ShowcaseRunner(
        output_dir=tmp_path / "showcase",
        selector=DeterministicSelector(),
    ).run([case])
    result = payload["cases"][0]

    assert result["pass"] is True, result["failures"]
    assert case.confirmation == "approve"
    assert result["confirmation"]["kind"] == "setting_change"
    assert result["confirmation"]["resolution"] == "approved"
    assert result["confirmation"]["correlation_valid"] is True
    dataset = result["state_after"]["dataset"]
    assert dataset["split_spec_saved"] is True
    assert dataset["split_materialized"] is False
    assert dataset["available"] is False


def test_real_boundaries_cover_success_block_confirmation_stale_and_retry(
    tmp_path: Path,
) -> None:
    selected = [
        _case("navigation.list_source_folder"),
        _case("blocked.preprocess_without_data"),
        _case("settings.model_approved"),
        _case("training.start_cancelled"),
        _case("safety.stale_revision"),
        _case("recovery.runtime_error_retry"),
    ]

    payload = ShowcaseRunner(
        output_dir=tmp_path / "showcase",
        selector=DeterministicSelector(),
    ).run(selected)
    results = {item["case_id"]: item for item in payload["cases"]}

    assert payload["summary"] == {
        "status": "passed",
        "total": 6,
        "passed": 6,
        "failed": 0,
        "missing_terminal_outcomes": 0,
    }
    assert results["navigation.list_source_folder"]["command_result"]["ok"] is True
    assert (
        results["blocked.preprocess_without_data"]["command_result"]["error_type"]
        == "precondition"
    )
    assert results["training.start_cancelled"]["confirmation"]["resolution"] == (
        "cancelled"
    )
    assert results["safety.stale_revision"]["command_result"]["error_type"] == (
        "stale_publication"
    )
    attempts = results["recovery.runtime_error_retry"]["retry"]["attempts"]
    assert [attempt["success"] for attempt in attempts] == [False, True]

    for case in selected:
        assert resume_case_matches(case, results[case.case_id]) is True

    invalid_model_confirmation = deepcopy(results["settings.model_approved"])
    invalid_model_confirmation["confirmation"] = None
    assert not resume_case_matches(
        _case("settings.model_approved"),
        invalid_model_confirmation,
    )

    uncorrelated_model_confirmation = deepcopy(results["settings.model_approved"])
    uncorrelated_model_confirmation["confirmation"]["correlation_valid"] = False
    assert not resume_case_matches(
        _case("settings.model_approved"),
        uncorrelated_model_confirmation,
    )

    fake_cancellation = deepcopy(results["training.start_cancelled"])
    fake_cancellation["confirmation"]["resolution"] = "approved"
    assert not resume_case_matches(
        _case("training.start_cancelled"),
        fake_cancellation,
    )

    fake_block = deepcopy(results["blocked.preprocess_without_data"])
    fake_block["command_result"]["ok"] = True
    assert not resume_case_matches(
        _case("blocked.preprocess_without_data"),
        fake_block,
    )

    fake_stale = deepcopy(results["safety.stale_revision"])
    fake_stale["verification"]["coordinator_action"] = "execute"
    assert not resume_case_matches(_case("safety.stale_revision"), fake_stale)

    fake_retry = deepcopy(results["recovery.runtime_error_retry"])
    fake_retry["retry"]["continued"] = False
    assert not resume_case_matches(
        _case("recovery.runtime_error_retry"),
        fake_retry,
    )
