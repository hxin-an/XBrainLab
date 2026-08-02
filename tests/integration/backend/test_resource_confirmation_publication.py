"""Resource confirmation must preserve one actionable application generation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import mne
import numpy as np
import pytest
import torch

from XBrainLab.backend.application import (
    data_compatibility_service,
    data_interpretation_service,
    training_service,
)
from XBrainLab.backend.application.commands import (
    ApplyInterpretationCommand,
    Command,
    LoadDataCommand,
    PreviewInterpretationCommand,
    ReloadInterpretationRecipeCommand,
    ScanSourceCommand,
    TrainCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.backend.application.data_interpretation_recipe import ImportRecipe
from XBrainLab.backend.application.resource_guard import (
    ResourceConfirmationRequiredError,
    ResourcePreflightResult,
)
from XBrainLab.backend.application.results import ErrorType
from XBrainLab.backend.application.service import ApplicationService
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import (
    ModelHolder,
    Trainer,
    TrainingEvaluation,
    TrainingOption,
)


@dataclass(frozen=True)
class _ConfirmationScenario:
    service: ApplicationService
    command: Command
    execution_observed: Callable[[], bool]


def _write_raw_fif(path: Path) -> Path:
    info = mne.create_info(["C3", "C4"], sfreq=128.0, ch_types="eeg")
    raw = mne.io.RawArray(np.zeros((2, 256), dtype=np.float64), info)
    raw.save(path, overwrite=True, verbose="ERROR")
    return path.resolve()


def _warning_import_preflight(paths: list[str]) -> ResourcePreflightResult:
    resolved = [Path(path).expanduser().resolve() for path in paths]
    return ResourcePreflightResult(
        issues=(),
        warnings=("Import is near the available RAM limit.",),
        unknowns=(),
        diagnostics={
            "risk_level": "warning",
            "message": "Import is near the available RAM limit.",
            "files": [
                {
                    "path": str(path),
                    "file_bytes": path.stat().st_size,
                }
                for path in resolved
            ],
        },
    )


def _warning_training_preflight(
    _datasets: Any,
    _training_option: Any,
    _model_holder: Any,
) -> ResourcePreflightResult:
    return ResourcePreflightResult(
        issues=(),
        warnings=("Training may use most available memory.",),
        unknowns=(),
        diagnostics={
            "risk_level": "warning",
            "estimated_gpu_batch_working_set_bytes": 4_096,
            "available_vram_bytes": 8_192,
        },
    )


def _prepare_preview(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> _ConfirmationScenario:
    eeg_path = _write_raw_fif(tmp_path / "preview_raw.fif")
    service = ApplicationService(Study())
    scanned = service.execute(ScanSourceCommand(source_path=str(eeg_path)))
    assert scanned.ok
    scan_id = str(scanned.diagnostics["scan_result"]["scan_id"])
    monkeypatch.setattr(
        data_interpretation_service,
        "check_import_resource_preflight",
        _warning_import_preflight,
    )
    return _ConfirmationScenario(
        service=service,
        command=PreviewInterpretationCommand(
            scan_id=scan_id,
            choices={"skip_labels": True},
        ),
        execution_observed=lambda: service.get_state().interpretation.has_preview,
    )


def _prepare_reload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> _ConfirmationScenario:
    eeg_path = _write_raw_fif(tmp_path / "reload_raw.fif")
    recipe_path = tmp_path / "import-recipe.json"
    ImportRecipe(
        recipe_id="recipe-resource-confirmation",
        interpretation_id="interpretation-resource-confirmation",
        source_path=str(eeg_path),
        source_kind="file",
        selected_eeg_files=[str(eeg_path)],
        skip_labels=True,
    ).write_json(str(recipe_path))
    service = ApplicationService(Study())
    monkeypatch.setattr(
        data_interpretation_service,
        "check_import_resource_preflight",
        _warning_import_preflight,
    )
    return _ConfirmationScenario(
        service=service,
        command=ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path)),
        execution_observed=lambda: service.get_state().interpretation.has_preview,
    )


def _prepare_apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> _ConfirmationScenario:
    eeg_path = _write_raw_fif(tmp_path / "apply_raw.fif")
    service = ApplicationService(Study())
    scanned = service.execute(ScanSourceCommand(source_path=str(eeg_path)))
    assert scanned.ok
    previewed = service.execute(
        PreviewInterpretationCommand(choices={"skip_labels": True})
    )
    assert previewed.ok
    candidate_id = str(previewed.diagnostics["candidate"]["candidate_id"])
    validated = service.execute(
        ValidateInterpretationCommand(candidate_id=candidate_id)
    )
    assert validated.ok
    monkeypatch.setattr(
        data_interpretation_service,
        "check_import_resource_preflight",
        _warning_import_preflight,
    )
    return _ConfirmationScenario(
        service=service,
        command=ApplyInterpretationCommand(
            candidate_id=candidate_id,
            confirmed=True,
        ),
        execution_observed=lambda: service.get_state().raw.loaded,
    )


def _prepare_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> _ConfirmationScenario:
    eeg_path = _write_raw_fif(tmp_path / "load_raw.fif")
    service = ApplicationService(Study())
    monkeypatch.setattr(
        data_compatibility_service,
        "check_import_resource_preflight",
        _warning_import_preflight,
    )
    return _ConfirmationScenario(
        service=service,
        command=LoadDataCommand(paths=[str(eeg_path)]),
        execution_observed=lambda: service.get_state().raw.loaded,
    )


def _prepare_train(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> _ConfirmationScenario:
    eeg_path = _write_raw_fif(tmp_path / "train_raw.fif")
    service = ApplicationService(Study())
    loaded = service.execute(LoadDataCommand(paths=[str(eeg_path)]))
    assert loaded.ok
    cast(Any, service.study.data_manager).datasets = [
        SimpleNamespace(train_mask=[True], val_mask=[], test_mask=[])
    ]
    service.study.set_model_holder(ModelHolder(int, {}))
    service.study.set_training_option(
        TrainingOption(
            output_dir=str(tmp_path / "training-output"),
            optim=torch.optim.Adam,
            optim_params={},
            use_cpu=True,
            gpu_idx=None,
            epoch=1,
            bs=1,
            lr=0.001,
            checkpoint_epoch=0,
            evaluation_option=TrainingEvaluation.LAST_EPOCH,
            repeat_num=1,
        )
    )

    def start_with_runtime_identity(
        *,
        append: bool = True,
        interactive: bool = True,
    ) -> int:
        del append, interactive
        trainer = Trainer([])
        trainer.run(interact=False)
        service.study.training_manager.trainer = trainer
        return 1

    start_training = MagicMock(side_effect=start_with_runtime_identity)
    service.training.start_training = start_training
    monkeypatch.setattr(
        training_service,
        "check_training_resource_preflight",
        _warning_training_preflight,
    )
    service.get_state()
    return _ConfirmationScenario(
        service=service,
        command=TrainCommand(confirmed=True),
        execution_observed=lambda: start_training.call_count == 1,
    )


@pytest.fixture(
    params=("preview", "reload", "apply", "load_data", "train"),
)
def resource_confirmation_scenario(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> _ConfirmationScenario:
    factory = {
        "preview": _prepare_preview,
        "reload": _prepare_reload,
        "apply": _prepare_apply,
        "load_data": _prepare_load,
        "train": _prepare_train,
    }[str(request.param)]
    return factory(tmp_path, monkeypatch)


def test_resource_confirmation_is_a_generation_preserving_control_flow(
    resource_confirmation_scenario: _ConfirmationScenario,
) -> None:
    scenario = resource_confirmation_scenario
    before = scenario.service.get_view_publication()

    challenged = scenario.service.execute(scenario.command)
    after_challenge = scenario.service.get_view_publication()

    assert challenged.failed
    assert challenged.error_type is ErrorType.CONFIRMATION_REQUIRED
    assert challenged.state.last_error == before.state.last_error
    assert challenged.changed_state.any_changed() is False
    assert challenged.diagnostics["control_flow_outcome"] is True
    assert challenged.diagnostics["state_preserved"] is True
    assert after_challenge.generation == before.generation
    assert after_challenge.state == before.state
    assert after_challenge.usable is True
    assert scenario.execution_observed() is False

    challenge_id = challenged.diagnostics["resource_preflight"][
        "confirmation_challenge"
    ]["challenge_id"]
    approved = replace(
        scenario.command,
        resource_preflight_confirmed=True,
        resource_preflight_token=challenge_id,
    )

    accepted = scenario.service.execute(approved)

    assert accepted.ok
    assert (
        accepted.diagnostics["resource_preflight"]["confirmation_receipt_reused"]
        is True
    )
    assert scenario.execution_observed() is True


def test_resource_confirmation_preserves_a_previous_real_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = _write_raw_fif(tmp_path / "prior-error_raw.fif")
    service = ApplicationService(Study())
    failed = service.execute(LoadDataCommand(paths=[]))
    assert failed.error_type is ErrorType.PRECONDITION
    before = service.get_view_publication()
    assert before.state.last_error is not None
    monkeypatch.setattr(
        data_compatibility_service,
        "check_import_resource_preflight",
        _warning_import_preflight,
    )

    challenged = service.execute(LoadDataCommand(paths=[str(eeg_path)]))
    after = service.get_view_publication()

    assert challenged.error_type is ErrorType.CONFIRMATION_REQUIRED
    assert challenged.state.last_error == before.state.last_error
    assert after.generation == before.generation
    assert after.state.last_error == before.state.last_error


def test_confirmation_cannot_hide_an_unexpected_domain_mutation(
    tmp_path: Path,
) -> None:
    eeg_path = _write_raw_fif(tmp_path / "mutated-before-confirmation_raw.fif")
    service = ApplicationService(Study())
    before = service.get_view_publication()

    def mutate_then_require_confirmation(_command: Command) -> str:
        count, errors = service.dataset.import_files([str(eeg_path)])
        assert count == 1
        assert errors == []
        raise ResourceConfirmationRequiredError(
            _warning_import_preflight([str(eeg_path)])
        )

    service._command_handlers[LoadDataCommand(paths=[]).name] = (
        mutate_then_require_confirmation
    )

    result = service.execute(LoadDataCommand(paths=[str(eeg_path)]))
    after = service.get_view_publication()

    assert result.error_type is ErrorType.CONFIRMATION_REQUIRED
    assert result.state.raw.loaded is True
    assert result.state.last_error is not None
    assert result.changed_state.raw_changed is True
    assert result.changed_state.error_changed is True
    assert after.generation > before.generation
    assert after.state == result.state


def test_real_handler_failure_still_updates_error_and_publication() -> None:
    service = ApplicationService(Study())
    before = service.get_view_publication()

    result = service.execute(LoadDataCommand(paths=[]))
    after = service.get_view_publication()

    assert result.error_type is ErrorType.PRECONDITION
    assert result.state.last_error is not None
    assert result.state.last_error.error_type == ErrorType.PRECONDITION.value
    assert result.changed_state.error_changed is True
    assert after.generation > before.generation
    assert after.state == result.state
