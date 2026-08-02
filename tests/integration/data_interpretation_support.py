"""Shared real Data Interpretation setup for integration tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from XBrainLab.backend.application import (
    ApplyInterpretationCommand,
    PreviewInterpretationCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
    get_application_service,
)
from XBrainLab.backend.application.results import CommandResult
from XBrainLab.backend.study import Study

GRAZ_2A_CLASS_MAP = {
    "769": "left hand",
    "770": "right hand",
    "771": "feet",
    "772": "tongue",
}


def import_recording_through_interpretation(
    study: Study,
    path: str | Path,
    *,
    class_map: dict[str, str] | None = None,
) -> CommandResult:
    """Import one real recording through the supported application workflow."""
    source_path = str(Path(path).resolve())
    choices: dict[str, Any] = {"selected_eeg_files": [source_path]}
    if class_map:
        choices.update(
            {
                "label_carrier": "embedded_events",
                "class_map": dict(class_map),
            }
        )
    else:
        choices["skip_labels"] = True

    service = get_application_service(study)
    commands = (
        ScanSourceCommand(source_path=source_path, source_hint="file"),
        PreviewInterpretationCommand(choices=choices),
        ValidateInterpretationCommand(),
        ApplyInterpretationCommand(confirmed=True),
    )
    result: CommandResult | None = None
    for command in commands:
        result = service.execute(command)
        assert result.ok, result.message
    assert result is not None
    return result
