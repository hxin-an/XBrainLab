"""State-lifecycle regressions for legacy raw-data compatibility commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import mne
import numpy as np
import pytest

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    ApplySmartParseCommand,
    PreviewInterpretationCommand,
    RemoveFilesCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    UpdateMetadataCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.study import Study


def _raw(path: Path) -> Raw:
    info = mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg")
    mne_raw = mne.io.RawArray(
        np.zeros((1, 200), dtype=np.float64),
        info,
        verbose="ERROR",
    )
    raw = Raw(str(path), mne_raw)
    raw.set_event(np.asarray([[50, 0, 1]], dtype=int), {"cue": 1})
    return raw


def _service_with_applied_interpretation(
    tmp_path: Path,
    *,
    file_count: int = 1,
) -> tuple[ApplicationService, list[Raw]]:
    source = tmp_path / "source"
    source.mkdir()
    paths = [source / f"subject-{index + 1:02d}.fif" for index in range(file_count)]
    for path in paths:
        path.write_bytes(b"scan-only fixture")
    raws = [_raw(path) for path in paths]
    raws_by_path = {raw.get_filepath(): raw for raw in raws}
    study = Study()
    service = ApplicationService(study)

    # Interpretation Apply prepares a detached replacement batch before it
    # commits the Study.  Supply real Raw holders at that public loader seam;
    # mocking the retired mutation API would bypass the two-phase contract.
    service.dataset._raw_factory_provider = lambda: MagicMock(
        load=lambda path: raws_by_path[str(path)]
    )
    assert service.execute(ScanSourceCommand(source_path=str(source))).ok
    assert service.execute(PreviewInterpretationCommand()).ok
    assert service.execute(ValidateInterpretationCommand()).ok
    applied = service.execute(ApplyInterpretationCommand(confirmed=True))
    assert applied.ok
    saved = service.execute(
        SaveInterpretationRecipeCommand(recipe_path=str(tmp_path / "recipe.json"))
    )
    assert saved.ok
    assert saved.state.interpretation.has_applied_interpretation
    assert saved.state.interpretation.has_recipe
    assert saved.state.interpretation.epoch_handoff
    return service, raws


@pytest.mark.parametrize(
    "mutation",
    [
        "remove",
        "metadata",
        "smart_parse",
    ],
)
def test_legacy_raw_mutation_invalidates_interpretation_recipe_and_epoch_handoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    service, raws = _service_with_applied_interpretation(
        tmp_path,
        file_count=2 if mutation == "remove" else 1,
    )
    original = raws[0]

    if mutation == "remove":
        command = RemoveFilesCommand(indices=[0])
    elif mutation == "metadata":
        command = UpdateMetadataCommand(index=0, subject="changed-subject")
    elif mutation == "smart_parse":
        command = ApplySmartParseCommand(
            results={original.get_filepath(): ("parsed-subject", "parsed-session")}
        )
    result = service.execute(command)

    assert result.ok, result.message
    assert result.diagnostics["interpretation_lifecycle"] == {
        "invalidated": True,
        "reason": "legacy_raw_mutation",
    }
    interpretation = result.state.interpretation
    assert interpretation.has_scan_result is False
    assert interpretation.has_candidate is False
    assert interpretation.has_preview is False
    assert interpretation.has_validation_decision is False
    assert interpretation.has_applied_interpretation is False
    assert interpretation.has_recipe is False
    assert interpretation.latest_interpretation_id is None
    assert interpretation.latest_recipe_id is None
    assert interpretation.recipe_path is None
    assert interpretation.epoch_handoff == {}


def test_legacy_raw_handler_failure_invalidates_interpretation_fail_closed(
    tmp_path: Path,
) -> None:
    service, _raws = _service_with_applied_interpretation(tmp_path)
    service.dataset_state.update_metadata_batch = MagicMock(
        side_effect=RuntimeError("metadata outcome is unknown")
    )

    result = service.execute(UpdateMetadataCommand(index=0, subject="changed"))

    assert result.failed
    assert result.state.interpretation.has_applied_interpretation is False
    assert result.state.interpretation.has_recipe is False
    assert result.state.interpretation.epoch_handoff == {}


def test_legacy_raw_precondition_failure_preserves_interpretation(
    tmp_path: Path,
) -> None:
    service, _raws = _service_with_applied_interpretation(tmp_path)

    result = service.execute(RemoveFilesCommand(indices=[99]))

    assert result.failed
    assert result.state.interpretation.has_applied_interpretation is True
    assert result.state.interpretation.has_recipe is True
    assert result.state.interpretation.epoch_handoff
