"""Fixed comparison subsets reuse the product runner without changing old cases."""

import json

import pytest

from scripts.dev import run_stable_assistant_model_eval as runner


@pytest.mark.parametrize(
    ("profile", "count"),
    [("core", 20), ("english", 6), ("recovery", 8), ("r3-comparison", 34)],
)
def test_profiles_have_fixed_unique_membership(profile, count):
    cases = runner.load_eval_profile(profile)
    assert len(cases) == len({case.case_id for case in cases}) == count
    if profile == "core":
        assert cases == runner.load_single_turn_cases()
    if profile == "r3-comparison":
        assert cases == (
            *runner.load_single_turn_cases(),
            *runner.load_eval_profile("english"),
            *runner.load_eval_profile("recovery"),
        )


def test_unknown_profile_does_not_fall_back_to_core():
    with pytest.raises(ValueError, match="profile"):
        runner.load_eval_profile("unknown")


@pytest.mark.parametrize("profile", ["english", "recovery"])
def test_comparison_manifest_corruption_fails_closed(profile, tmp_path, monkeypatch):
    name = "DEFAULT_ENGLISH_CASES" if profile == "english" else "DEFAULT_RECOVERY_CASES"
    changed = tmp_path / "changed.json"
    changed.write_bytes(getattr(runner, name).read_bytes() + b" ")
    monkeypatch.setattr(runner, name, changed)
    with pytest.raises(ValueError, match="manifest changed"):
        runner.load_eval_profile(profile)


def test_english_replies_score_only_tool_decision_and_never_host_rescue():
    cases = runner.load_eval_profile("english")
    registry = runner.target_tool_registry()
    for case in cases[2:]:
        # The approved scope excludes prose quality, including this poor answer.
        good = runner.evaluate_case_trajectory(
            case,
            registry,
            lambda _: '{"tool_name":"respond_to_user","parameters":{"message":"Done."}}',
        )
        assert good.raw_score.passed
        assert good.post_recovery_score.passed
        wrong = runner.evaluate_case_trajectory(
            case,
            registry,
            lambda _: '{"tool_name":"apply_notch_filter","parameters":{"freq":50}}',
        )
        assert not wrong.raw_score.passed
        assert not wrong.post_recovery_score.passed
        assert len(wrong.attempts) == 1


def test_recovery_cases_publish_expected_action_without_oracle_in_request():
    registry = runner.target_tool_registry()
    cases = runner.load_eval_profile("recovery")
    assert [case.case_id for case in cases] == [
        "TEST-A02-01-V0",
        "TEST-A02-01-V1",
        "TEST-A02-02-V1",
        "TEST-A03-01-V1",
        "TEST-A04-02-V1",
        "TEST-A12-02-V0",
        "TEST-A15-02-V0",
        "TEST-A15-02-V1",
    ]
    for case in cases:
        messages, publication, _ = runner._case_projection(case, registry)
        assert publication.permits(case.expected_tool)
        assert case.user_input in messages[-1]["content"]
        assert "source_sha256" not in str(messages)
        assert "expected_tool" not in str(messages)
        response = json.dumps(
            {"tool_name": case.expected_tool, "parameters": case.expected_parameters}
        )
        assert runner.score_model_response(case, response, registry).passed


def test_cli_profiles_and_breadth_are_mutually_exclusive():
    with pytest.raises(SystemExit) as failure:
        runner.main(["--profile", "english", "--breadth"])
    assert failure.value.code == 2


@pytest.mark.parametrize(
    ("argv", "count"),
    [
        ([], 20),
        (["--breadth"], 74),
        (["--profile", "r3-comparison"], 34),
        (["--profile", "english"], 6),
        (["--profile", "recovery"], 8),
    ],
)
def test_cli_passes_the_selected_cases_to_existing_runner(
    argv, count, monkeypatch, capsys
):
    from XBrainLab.llm.core.config import LLMConfig

    monkeypatch.setattr(LLMConfig, "load_from_file", lambda: LLMConfig(device="cpu"))
    received = []

    def evaluate(_config, cases, **_kwargs):
        received.extend(cases)
        return {"case_summaries": {"total": {"complete": True}}}

    monkeypatch.setattr(runner, "run_eval", evaluate)
    assert runner.main(argv) == 0
    assert len(received) == count
    report = json.loads(capsys.readouterr().out)
    assert report["invocation"]["argv"] == argv


def test_comparison_report_identifies_actual_cases_without_certifying_core(monkeypatch):
    from XBrainLab.llm.core.config import LLMConfig

    class Engine:
        def __init__(self, _config):
            pass

        def load_model(self):
            pass

        def generate_stream(self, _messages, **_kwargs):
            yield '{"tool_name":"respond_to_user","parameters":{"message":"Done."}}'

        def close(self):
            return True

    monkeypatch.setattr(runner, "LLMEngine", Engine)
    cases = runner.load_eval_profile("english")
    report = runner.run_eval(LLMConfig(device="cpu"), cases, rag_mode="off")
    assert report["case_set_identity"]["case_ids"] == [case.case_id for case in cases]
    assert report["case_set_identity"]["case_count"] == 6
    assert len(report["case_set_identity"]["cases_sha256"]) == 64
    assert not report["candidate_gate"]["fixed_twenty_complete"]
    assert report["case_summaries"]["total"]["post_recovery_passed"] == 4
    assert all(
        row["score_scope"].startswith("tool_decision_only") for row in report["results"]
    )
