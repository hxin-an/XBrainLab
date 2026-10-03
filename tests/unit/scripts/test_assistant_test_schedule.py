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


@pytest.mark.parametrize("alias", list(protocol.MODELS))
@pytest.mark.parametrize("candidate", range(1, 6))
def test_test_schedule_accepts_one_approved_frozen_winner(tmp_path, alias, candidate):
    config = test_config(tmp_path)
    original_policy = protocol.experiment_identity(config)
    config["models"][0].update(alias=alias, candidate_index=candidate)
    assert protocol.experiment_identity(config) == original_policy
    selection = protocol.build_selection(test_bank(), config)
    jobs = protocol.build_jobs(selection, config)
    assert len(jobs) == len({job["id"] for job in jobs}) == 1584
    sessions = Counter(protocol.job_condition_identity(job) for job in jobs)
    assert len(sessions) == 12
    assert set(sessions.values()) == {132}
    assert {job["candidate_index"] for job in jobs} == {candidate}
    assert {job["condition"] for job in jobs} == {
        f"{alias}-{ablation}" for ablation in protocol.TEST_ABLATIONS
    }
    assert len(runner.condition_batches(jobs)) == 12
    for ablation in protocol.TEST_ABLATIONS:
        assert runner.condition_spec(f"{alias}-{ablation}") == (
            protocol.MODELS[alias],
            protocol.ablation_policy(ablation)["rag_enabled"],
        )
    for job in jobs:
        for factor, value in protocol.ablation_policy(job["ablation"]).items():
            assert job[factor] == value


def test_test_condition_lookup_preserves_legacy_scope_and_rejects_unknowns():
    assert runner.select_conditions("all") == list(runner.CONDITIONS)
    assert len(runner.CONDITIONS) == 10
    for condition, expected in runner.CONDITIONS.items():
        assert runner.condition_spec(condition) == expected
    with pytest.raises(ValueError, match="Unknown"):
        runner.select_conditions("granite4-full")
    for condition in ("unapproved-full", "phi4-extra-retry", "granite4-full-extra"):
        with pytest.raises(KeyError):
            runner.condition_spec(condition)


@pytest.mark.parametrize("split", ["VALID", "TEST"])
def test_explicit_frozen_round_single_repeat_is_threaded_without_changing_defaults(
    tmp_path, split
):
    config = test_config(tmp_path)
    config["split"] = split
    original = protocol.experiment_identity(config)
    selection = {"case_ids": [f"{split}-A01-01-V0"]}
    legacy_jobs = protocol.build_jobs(selection, config)
    assert original["repeats"] == [0, 1, 2]
    assert all("prompt_profile" not in job for job in legacy_jobs)
    config.update(prompt_profile="frozen-dev-round", repeats=[0])
    policy = protocol.experiment_identity(config)
    assert policy == {**original, "repeats": [0]}
    assert protocol.is_experiment_protocol(policy)
    jobs = protocol.build_jobs(selection, config)
    assert len(jobs) == (4 if split == "TEST" else 1)
    assert {job["repeat"] for job in jobs} == {0}
    assert all(job["prompt_profile"] == "frozen-dev-round" for job in jobs)


@pytest.mark.parametrize(
    "field,value",
    [("prompt_profile", value) for value in (None, "", "unapproved")]
    + [
        ("repeats", value)
        for value in (None, [], [1], [0, 1], [False], [0, 0], [2, 1, 0])
    ],
)
def test_profile_and_repeat_opt_ins_reject_invalid_values(tmp_path, field, value):
    config = test_config(tmp_path)
    config[field] = value
    with pytest.raises(ValueError):
        protocol.experiment_identity(config)


@pytest.mark.parametrize(
    "purpose,field,value",
    [
        ("engineering-smoke", "prompt_profile", "frozen-dev-round"),
        ("engineering-smoke", "repeats", [0]),
        ("research", "repeats", [0]),
    ],
)
def test_profile_and_repeat_opt_ins_do_not_redefine_dev(
    tmp_path, purpose, field, value
):
    config = test_config(tmp_path)
    config.update(split="DEV", purpose=purpose)
    if purpose == "engineering-smoke":
        config["case_ids"] = ["DEV-A01-01-V0"]
    config[field] = value
    with pytest.raises(ValueError):
        protocol.experiment_identity(config)


@pytest.mark.parametrize(
    "mutation", ["candidate", "model", "two-models", "subset", "smoke"]
)
def test_test_config_rejects_unapproved_winner_or_scope(tmp_path, mutation):
    config = test_config(tmp_path)
    if mutation == "candidate":
        config["models"][0]["candidate_index"] = 6
    elif mutation == "model":
        config["models"][0]["alias"] = "unapproved-model"
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
