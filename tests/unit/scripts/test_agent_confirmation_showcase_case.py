"""Focused showcase contract for a complete training-setting intent."""

from __future__ import annotations

from pathlib import Path

from scripts.dev.agent_toolcall_showcase.cases import SHOWCASE_CASES
from scripts.dev.agent_toolcall_showcase.runner import ShowcaseRunner
from scripts.dev.agent_toolcall_showcase.selector import DeterministicSelector


def _complete_training_case():
    return next(
        case
        for case in SHOWCASE_CASES
        if case.case_id == "settings.complete_training_approved"
    )


def test_complete_training_case_has_one_full_intent_contract() -> None:
    case = _complete_training_case()

    assert case.tool_name == "configure_training"
    assert case.preparation == "training_configured"
    assert case.confirmation == "approve"
    assert case.params == {
        "model_name": "braindecode.deep4net",
        "epoch": 5,
        "batch_size": 16,
        "learning_rate": 0.0005,
    }


def test_complete_training_case_approves_and_publishes_exact_values(
    tmp_path: Path,
) -> None:
    case = _complete_training_case()

    payload = ShowcaseRunner(
        output_dir=tmp_path / "showcase",
        selector=DeterministicSelector(),
    ).run([case])
    result = payload["cases"][0]

    assert result["pass"] is True, result["failures"]
    assert result["exposed_tool_schema_names"] == ["configure_training"]
    assert result["selected_tool"] == "configure_training"
    assert result["selected_parameters"] == case.params
    assert result["confirmation"]["kind"] == "setting_change"
    assert result["confirmation"]["resolution"] == "approved"
    assert result["confirmation"]["correlation_valid"] is True
    assert dict(result["confirmation"]["parameter_rows"]) == {
        "Batch size": "16",
        "Device": "cpu",
        "Epoch": "5",
        "Evaluation option": "last_epoch",
        "Learning rate": "0.0005",
        "Model name": "braindecode.deep4net",
        "Optimizer": "adam",
        "Repeat": "1",
        "Save checkpoints every": "0",
    }
    assert result["command_result"]["ok"] is True
    assert result["changed_state"]["training_changed"] is True

    before = result["state_before"]["training"]
    after = result["state_after"]["training"]
    assert before["model_name"] == "EEGNet (XBrainLab)"
    assert before["training_option"]["epoch"] == 1
    assert before["training_option"]["batch_size"] == 4
    assert before["training_option"]["learning_rate"] == 0.001
    assert after["model_name"] == "Deep4Net (Braindecode)"
    assert after["training_option"]["epoch"] == case.params["epoch"]
    assert after["training_option"]["batch_size"] == case.params["batch_size"]
    assert after["training_option"]["learning_rate"] == case.params["learning_rate"]
