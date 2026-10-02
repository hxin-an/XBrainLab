"""Synthetic TEST population: fixed winner, single factors and rotated repeats."""

from collections import Counter
from copy import deepcopy

import pytest

from scripts.dev import assistant_experiment_config as protocol
from scripts.dev import run_assistant_pilot as runner
from tests.unit.scripts.test_run_assistant_dev import experiment_config


def test_config(tmp_path):
    config = experiment_config(tmp_path, "TEST")
    config["models"] = [config["models"][1]]
    return config


test_config.__test__ = False


def test_bank():
    cases = []
    for category, families in (("Action", 36), ("Clarification", 12), ("No-call", 18)):
        for family in range(families):
            family_id = f"TEST-{category}-{family:02}"
            cases.extend(
                {
                    "case_id": f"{family_id}-V{variant}",
                    "family_id": family_id,
                    "split": "TEST",
                    "decision": category,
                    "fixture_id": family_id,
                }
                for variant in range(2)
            )
    return {
        "source": {"sha256": "synthetic"},
        "cases": cases,
        "fixtures": {case["fixture_id"]: {} for case in cases},
    }


test_bank.__test__ = False


def test_test_schedule_is_1584_unique_jobs_in_twelve_rotated_sessions(tmp_path):
    config = test_config(tmp_path)
    selection = protocol.build_selection(test_bank(), config)
    jobs = protocol.build_jobs(selection, config)
    assert len(jobs) == len({job["id"] for job in jobs}) == 1584
    batches = runner.condition_batches(jobs)
    base = ["full", "rag-off", "tool-filter-off", "retry-off"]
    assert [batch["jobs"][0]["ablation"] for batch in batches] == [
        value for repeat in range(3) for value in base[repeat:] + base[:repeat]
    ]
    assert [batch["jobs"][0]["repeat"] for batch in batches] == [0] * 4 + [1] * 4 + [
        2
    ] * 4
    expected = {
        "full": (True, True, 1),
        "rag-off": (False, True, 1),
        "tool-filter-off": (True, False, 1),
        "retry-off": (True, True, 0),
    }
    for batch in batches:
        assert len(batch["jobs"]) == 132
        for job in batch["jobs"]:
            assert job["candidate_index"] == 5
            assert job["condition"] == "phi4-" + job["ablation"]
            assert (
                job["rag_enabled"],
                job["tool_filter_enabled"],
                job["max_format_recovery_attempts"],
            ) == expected[job["ablation"]]
    assert Counter(selection["counts"]) == Counter(
        {"Action": 72, "Clarification": 24, "No-call": 36}
    )


@pytest.mark.parametrize(
    "mutation", ["candidate", "model", "two-models", "subset", "smoke"]
)
def test_test_config_rejects_unfrozen_winner_or_scope(tmp_path, mutation):
    config = test_config(tmp_path)
    if mutation == "candidate":
        config["models"][0]["candidate_index"] = 4
    elif mutation == "model":
        config["models"][0]["alias"] = "granite4"
    elif mutation == "two-models":
        other = deepcopy(config["models"][0])
        other["alias"] = "granite4"
        config["models"].append(other)
    elif mutation == "subset":
        config["case_ids"] = ["TEST-Action-00-V0"]
    else:
        config["purpose"] = "engineering-smoke"
    with pytest.raises(ValueError):
        protocol.experiment_identity(config)


def test_test_population_and_derived_policy_cannot_be_relaxed(tmp_path):
    config = test_config(tmp_path)
    bank = test_bank()
    bank["cases"].pop()
    with pytest.raises(ValueError, match="population"):
        protocol.build_selection(bank, config)
    policy = protocol.experiment_identity(config)
    assert protocol.is_experiment_protocol(policy)
    policy["ablations"] = ["full"]
    assert not protocol.is_experiment_protocol(policy)
    with pytest.raises(ValueError):
        protocol.ablation_policy("full-with-extra-retry")
