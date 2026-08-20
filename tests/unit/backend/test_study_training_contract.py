"""Unit-level Study training configuration compatibility contracts."""

import ast
from pathlib import Path
from typing import Any, cast

import torch

from XBrainLab import Study
from XBrainLab.backend.training import TrainingEvaluation, TrainingOption

_TRAINING_OUTPUT_TEST_PATHS = (
    "tests/integration/pipeline/test_study_training_facade.py",
    "tests/integration/pipeline/test_trainer_model_integration.py",
    "tests/integration/pipeline/test_real_data_command_spine.py",
    "tests/unit/ui/test_training_result_presentation.py",
    "tests/unit/backend/test_study_training_contract.py",
)


def _ui_text(value: str) -> Any:
    """Represent text-field values passed through runtime validation."""
    return cast(Any, value)


def _training_option(tmp_path) -> TrainingOption:
    return TrainingOption(
        output_dir=str(tmp_path / "training-output"),
        optim=torch.optim.Adam,
        optim_params={},
        use_cpu=True,
        gpu_idx=None,
        epoch=_ui_text("5"),
        bs=_ui_text("4"),
        lr=_ui_text("0.001"),
        checkpoint_epoch=_ui_text("1"),
        evaluation_option=TrainingEvaluation.VAL_ACC,
        repeat_num=_ui_text("1"),
    )


def test_study_exposes_training_option_property_not_training_setting():
    """Study's lower-level compatibility property is training_option."""
    study = Study()

    assert study.training_option is None
    assert not hasattr(study, "training_setting")


def test_study_set_training_option_updates_training_manager(tmp_path):
    """Study.set_training_option remains a domain compatibility contract."""
    study = Study()
    option = _training_option(tmp_path)

    study.set_training_option(option)

    published = study.training_option
    manager_published = study.training_manager.training_option
    assert published is not None
    assert manager_published is not None
    assert published is not option
    assert manager_published is not option
    assert published.epoch == option.epoch
    assert manager_published.epoch == option.epoch
    assert option.epoch == 5
    assert option.lr == 0.001
    assert option.optim == torch.optim.Adam


def test_training_output_paths_are_scoped_to_pytest_tmp_path():
    repo_root = Path(__file__).resolve().parents[3]
    violations = []

    for relative_path in _TRAINING_OUTPUT_TEST_PATHS:
        tree = ast.parse((repo_root / relative_path).read_text(encoding="utf-8"))
        output_dir_values = [
            keyword.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            for keyword in node.keywords
            if keyword.arg == "output_dir"
        ]
        output_dir_values.extend(
            value
            for node in ast.walk(tree)
            if isinstance(node, ast.Dict)
            for key, value in zip(node.keys, node.values, strict=True)
            if isinstance(key, ast.Constant) and key.value == "output_dir"
        )

        if not output_dir_values:
            violations.append(f"{relative_path}: no output_dir assignment inspected")
            continue

        violations.extend(
            f"{relative_path}:{value.lineno}"
            for value in output_dir_values
            if not any(
                isinstance(node, ast.Name) and node.id == "tmp_path"
                for node in ast.walk(value)
            )
        )

    assert not violations, (
        "Training tests must scope every output_dir to pytest tmp_path:\n"
        + "\n".join(violations)
    )
