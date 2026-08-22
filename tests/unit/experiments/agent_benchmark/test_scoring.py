from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from XBrainLab.experiments.agent_benchmark.contracts import (
    BenchmarkContractError,
    load_benchmark,
)
from XBrainLab.experiments.agent_benchmark.harness import BenchmarkHarness
from XBrainLab.experiments.agent_benchmark.scoring import score_episode


def _case() -> dict:
    return {
        "case_id": "pilot.configure-training.en.v1",
        "semantic_family_id": "pilot.configure-training.v1",
        "budget": {"max_agent_turns": 3, "max_tool_calls": 2},
        "oracle": {
            "milestones": [
                {
                    "milestone_id": "configuration_saved",
                    "predicate_id": "event.command_ok",
                    "arguments": {"command_name": "configure_training"},
                    "required": True,
                    "prerequisites": [],
                },
                {
                    "milestone_id": "confirmation_explained",
                    "predicate_id": "event.communication",
                    "arguments": {"label": "confirmation_request"},
                    "required": True,
                    "prerequisites": ["configuration_saved"],
                },
            ],
            "terminal_predicates": [
                {
                    "predicate_id": "state.path_equals",
                    "arguments": {"path": "training.has_model", "value": True},
                }
            ],
            "minefields": [
                {
                    "minefield_id": "trained_without_confirmation",
                    "predicate_id": "event.command_seen",
                    "arguments": {"command_name": "train"},
                    "critical": True,
                }
            ],
            "required_communication": ["confirmation_request"],
        },
    }


def _trace() -> dict:
    return {
        "schema_version": "1.0.0",
        "case_id": "pilot.configure-training.en.v1",
        "run_id": "run-1",
        "repeat_index": 0,
        "complete": True,
        "observations": [
            {
                "sequence": 1,
                "kind": "command_result",
                "payload": {"command_name": "configure_training", "status": "ok"},
            },
            {
                "sequence": 2,
                "kind": "communication",
                "payload": {"label": "confirmation_request"},
            },
            {
                "sequence": 3,
                "kind": "publication",
                "payload": {"state": {"training": {"has_model": True}}},
            },
        ],
        "usage": {"agent_turns": 2, "tool_calls": 1},
    }


def test_episode_passes_only_when_all_strict_conditions_hold() -> None:
    verdict = score_episode(_case(), _trace())

    assert verdict["episode"]["passed"] is True
    assert verdict["decision"]["passed"] is True
    assert verdict["control"]["passed"] is True
    assert verdict["execution"]["passed"] is True
    assert verdict["critical_minefields"] == []
    assert verdict["primary_failure"] is None


@pytest.mark.parametrize(
    ("mutate", "failure"),
    [
        (
            lambda trace: trace["observations"].__setitem__(
                0,
                {
                    "sequence": 1,
                    "kind": "command_result",
                    "payload": {"command_name": "query_state", "status": "ok"},
                },
            ),
            "missing_milestone",
        ),
        (
            lambda trace: trace["observations"].append(
                {
                    "sequence": 4,
                    "kind": "command_result",
                    "payload": {"command_name": "train", "status": "ok"},
                }
            ),
            "critical_minefield",
        ),
        (
            lambda trace: trace["observations"].__setitem__(
                1,
                {
                    "sequence": 2,
                    "kind": "communication",
                    "payload": {"label": "generic_ack"},
                },
            ),
            "communication",
        ),
        (
            lambda trace: trace["usage"].__setitem__("tool_calls", 3),
            "budget",
        ),
    ],
)
def test_strict_conjunction_fails_with_deterministic_reason(mutate, failure) -> None:
    trace = _trace()
    mutate(trace)

    verdict = score_episode(_case(), trace)

    assert verdict["episode"]["passed"] is False
    assert verdict["primary_failure"] == failure


def test_partial_order_violation_fails_control() -> None:
    trace = _trace()
    trace["observations"][0], trace["observations"][1] = (
        trace["observations"][1],
        trace["observations"][0],
    )
    trace["observations"][0]["sequence"] = 1
    trace["observations"][1]["sequence"] = 2

    verdict = score_episode(_case(), trace)

    assert verdict["control"]["passed"] is False
    assert verdict["primary_failure"] == "milestone_order"


def test_unknown_predicate_fails_closed() -> None:
    case = deepcopy(_case())
    case["oracle"]["terminal_predicates"][0]["predicate_id"] = "llm.judge"

    with pytest.raises(BenchmarkContractError, match="Unknown predicate"):
        score_episode(case, _trace())


def test_terminal_predicate_must_hold_in_final_publication() -> None:
    trace = _trace()
    trace["observations"].append(
        {
            "sequence": 4,
            "kind": "publication",
            "payload": {"state": {"training": {"has_model": False}}},
        }
    )

    verdict = score_episode(_case(), trace)

    assert verdict["episode"]["passed"] is False
    assert verdict["primary_failure"] == "terminal_state"


def test_case_trace_identity_mismatch_fails_closed() -> None:
    trace = _trace()
    trace["case_id"] = "different.case.v1"

    verdict = score_episode(_case(), trace)

    assert verdict["complete"] is False
    assert verdict["primary_failure"] == "artifact_integrity"


def test_prerecorded_trace_recomputes_and_artifact_is_create_only(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[4]
    benchmark_root = root / "benchmarks" / "xbrainlab_agent" / "v1"
    trace = json.loads(
        (benchmark_root / "examples" / "pilot.scan-source.en.v1.trace.json").read_text(
            encoding="utf-8"
        )
    )
    harness = BenchmarkHarness(load_benchmark(benchmark_root))
    destination = tmp_path / "verdict.json"

    assert harness.score(trace)["episode"]["passed"] is True
    harness.write_verdict(trace, destination)
    envelope = json.loads(destination.read_text(encoding="utf-8"))
    assert envelope["verdict"]["episode"]["passed"] is True
    assert len(envelope["case_sha256"]) == 64
    assert len(envelope["trace_sha256"]) == 64

    with pytest.raises(BenchmarkContractError, match="already exists"):
        harness.write_verdict(trace, destination)
