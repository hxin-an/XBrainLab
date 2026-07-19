"""Agent confirmation follows the ApplicationService publication generation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import mne
import numpy as np

from XBrainLab.backend.application import (
    data_compatibility_service,
    get_application_service,
)
from XBrainLab.backend.application.commands import ScanSourceCommand
from XBrainLab.backend.application.resource_guard import ResourcePreflightResult
from XBrainLab.backend.study import Study
from XBrainLab.llm.agent.confirmation import (
    AgentConfirmationResolution,
    AgentConfirmationResolutionStatus,
)
from XBrainLab.llm.agent.tool_attempt_coordinator import (
    ApplicationToolContextSource,
    ToolAttemptAction,
    ToolAttemptCoordinator,
    ToolAttemptDecision,
)
from XBrainLab.llm.tools.application_surface import (
    ToolCommandResult,
    execute_application_tool_command,
)


def _write_raw_fif(path: Path) -> Path:
    info = mne.create_info(["C3", "C4"], sfreq=128.0, ch_types="eeg")
    raw = mne.io.RawArray(np.zeros((2, 256), dtype=np.float64), info)
    raw.save(path, overwrite=True, verbose="ERROR")
    return path.resolve()


def _warning_preflight(paths: list[str]) -> ResourcePreflightResult:
    return ResourcePreflightResult(
        issues=(),
        warnings=("Import is near the available RAM limit.",),
        unknowns=(),
        diagnostics={
            "risk_level": "warning",
            "message": "Import is near the available RAM limit.",
            "files": [
                {
                    "path": str(Path(path).resolve()),
                    "file_bytes": Path(path).stat().st_size,
                }
                for path in paths
            ],
        },
    )


def _controller_with_real_context(study: Study):
    from XBrainLab.llm.agent.controller import LLMController

    with (
        patch("XBrainLab.llm.agent.controller.ToolRegistry"),
        patch("XBrainLab.llm.agent.controller.ContextAssembler"),
        patch("XBrainLab.llm.agent.controller.VerificationLayer"),
        patch("XBrainLab.llm.agent.controller.QThread"),
        patch("XBrainLab.llm.agent.controller.AgentWorker"),
        patch("XBrainLab.llm.agent.controller.AVAILABLE_TOOLS", []),
    ):
        return LLMController(study, rag_lifecycle=MagicMock())


def test_agent_resource_confirmation_survives_warning_but_not_domain_mutation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    eeg_path = _write_raw_fif(tmp_path / "agent-confirmation_raw.fif")
    study = Study()
    service = get_application_service(study)
    monkeypatch.setattr(
        data_compatibility_service,
        "check_import_resource_preflight",
        _warning_preflight,
    )
    context_source = ApplicationToolContextSource(study)
    context = context_source.get_context("load_data")
    assert context is not None
    assert context.generation is not None
    params = {"paths": [str(eeg_path)]}

    challenged = execute_application_tool_command(
        study,
        "load_data",
        params,
        availability=context.availability,
        state=context.state,
    )
    assert isinstance(challenged, ToolCommandResult)
    assert challenged.error_type == "confirmation_required"
    after_warning = context_source.get_context("load_data")
    assert after_warning is not None
    assert after_warning.generation == context.generation

    initial = ToolAttemptDecision(
        action=ToolAttemptAction.EXECUTE,
        command_name="load_data",
        params=params,
        context=context,
    )
    pending = ToolAttemptCoordinator.resource_confirmation(initial, challenged)
    assert pending is not None
    assert pending.action is ToolAttemptAction.CONFIRMATION_REQUIRED
    controller = _controller_with_real_context(study)
    request = controller._build_confirmation_request(pending, context)
    assert request.publication_generation is not None
    controller.pending_interactions.begin_confirmation(pending, request)
    controller._execute_tool_no_loop = MagicMock()
    controller._handle_tool_attempt_blocked = MagicMock()

    mutated = service.execute(ScanSourceCommand(source_path=str(eeg_path)))
    assert mutated.ok
    current = context_source.get_context("load_data")
    assert current is not None
    assert current.generation is not None
    assert current.generation > request.publication_generation

    controller.on_user_confirmation_resolved(
        AgentConfirmationResolution.for_request(
            request,
            status=AgentConfirmationResolutionStatus.APPROVED,
        )
    )

    controller._execute_tool_no_loop.assert_not_called()
    controller._handle_tool_attempt_blocked.assert_called_once()
    blocked = controller._handle_tool_attempt_blocked.call_args.args[1]
    assert isinstance(blocked, ToolCommandResult)
    assert blocked.error_type == "stale_confirmation"
    assert blocked.diagnostics == {
        "confirmed_generation": request.publication_generation,
        "current_generation": current.generation,
    }
