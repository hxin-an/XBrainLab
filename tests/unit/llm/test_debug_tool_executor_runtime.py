"""Standalone debug-tool execution must obey the canonical agent boundary."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.backend.application import (
    ChangedState,
    CommandResult,
    QueryStateCommand,
    build_capability_policy,
    get_application_service,
)
from XBrainLab.backend.application.view_publication import ApplicationViewPublication
from XBrainLab.backend.study import Study
from XBrainLab.debug.tool_executor import ToolExecutor
from XBrainLab.llm.action_contracts import (
    AGENT_ACTION_CONTRACTS,
    AgentExecutionKind,
)
from XBrainLab.llm.tools import get_all_tools
from XBrainLab.llm.tools.application_surface import (
    APPLICATION_COMMAND_TOOLS,
    ToolCommandResult,
)
from XBrainLab.llm.tools.result_contract import UiRequest, UiRequestKind

MAPPED_DEBUG_TOOLS = sorted(
    set(ToolExecutor.TOOL_MAP).intersection(APPLICATION_COMMAND_TOOLS)
)


def test_debug_executor_surface_matches_all_canonical_real_tools() -> None:
    canonical_real_tools = [tool.name for tool in get_all_tools("real")]

    assert len(canonical_real_tools) == 31
    assert len(canonical_real_tools) == len(set(canonical_real_tools))
    assert set(ToolExecutor.TOOL_MAP) == set(canonical_real_tools)


def _complete_training_params() -> dict[str, object]:
    return {
        "model_name": "EEGNet",
        "epoch": 2,
        "batch_size": 4,
        "learning_rate": 0.001,
    }


def _headless_success_expectation(tool_name: str) -> dict[str, object]:
    contract = AGENT_ACTION_CONTRACTS.contract_for(tool_name)
    assert contract is not None
    if contract.execution_kind is AgentExecutionKind.UI_REQUEST:
        request_kind = (
            UiRequestKind.CONFIRM_MONTAGE
            if tool_name == "set_montage"
            else UiRequestKind.SWITCH_PANEL
        )
        return {"ok": True, "ui_request_kind": request_kind.value}
    expected: dict[str, object] = {
        "ok": True,
        "state": {"pipeline_stage": "empty"},
    }
    if contract.execution_kind is AgentExecutionKind.APPLICATION_COMMAND:
        assert contract.capability_command is not None
        expected["command_name"] = contract.capability_command.value
    return expected


def _headless_success_result(tool_name: str) -> ToolCommandResult | UiRequest:
    contract = AGENT_ACTION_CONTRACTS.contract_for(tool_name)
    assert contract is not None
    if contract.execution_kind is AgentExecutionKind.UI_REQUEST:
        request_kind = (
            UiRequestKind.CONFIRM_MONTAGE
            if tool_name == "set_montage"
            else UiRequestKind.SWITCH_PANEL
        )
        return UiRequest(request_kind)
    return ToolCommandResult(
        ok=True,
        tool_name=tool_name,
        command_name=(
            contract.capability_command.value
            if contract.capability_command is not None
            else None
        ),
        message="Completed.",
        state={"pipeline_stage": "empty"},
    )


def _dataset_info_runtime() -> MagicMock:
    publication = get_application_service(Study()).get_view_publication()
    state = replace(
        publication.state,
        raw=replace(
            publication.state.raw,
            loaded=True,
            count=1,
            files=["injected-runtime.edf"],
            event_total=7,
            unique_events=["target"],
        ),
        active_dataset=replace(
            publication.state.active_dataset,
            has_raw_data=True,
        ),
    )
    runtime = MagicMock()
    runtime.get_view_publication.return_value = ApplicationViewPublication(
        generation=23,
        state=state,
        capabilities=build_capability_policy(state),
    )
    runtime.execute.return_value = CommandResult.success_result(
        command_name="query_state",
        message="Dataset summary ready.",
        state=state,
        changed_state=ChangedState(),
        diagnostics={
            "count": 1,
            "files": ["injected-runtime.edf"],
            "total": 7,
            "unique_count": 1,
        },
    )
    return runtime


def test_mapped_debug_command_uses_application_runtime_exactly_once() -> None:
    study = Study()
    service = get_application_service(study)
    executor = ToolExecutor(study)

    with (
        patch.object(service, "execute", wraps=service.execute) as execute,
        patch(
            "XBrainLab.debug.tool_executor.RealConfigureTrainingTool.execute",
            side_effect=AssertionError("mapped adapter execution is forbidden"),
        ) as direct_execute,
    ):
        result = executor.execute(
            "configure_training",
            _complete_training_params(),
        )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is True
    assert result.command_name == "configure_training"
    assert result.state is not None
    assert result.changed_state
    assert result.changed_state["training_changed"] is True
    execute.assert_called_once()
    direct_execute.assert_not_called()
    evidence = executor.last_execution_evidence
    assert evidence is not None
    assert evidence.dispatch_count == 1
    assert evidence.adapter_invocation_count == 0
    assert evidence.ui_adapter_invocation_count == 0
    assert evidence.runtime_command_invocation_count == 1
    assert evidence.publication_read_count == 1


def test_explicit_headless_runtime_executes_mapped_command_exactly_once() -> None:
    service = get_application_service(Study())
    runtime = MagicMock()
    runtime.get_view_publication.side_effect = service.get_view_publication
    runtime.execute.side_effect = service.execute

    with patch(
        "XBrainLab.debug.tool_executor.RealConfigureTrainingTool.execute",
        side_effect=AssertionError("mapped adapter execution is forbidden"),
    ) as direct_execute:
        result = ToolExecutor(
            object(),
            application_runtime=runtime,
        ).execute(
            "configure_training",
            _complete_training_params(),
        )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is True
    assert result.state is not None
    assert result.changed_state["training_changed"] is True
    runtime.execute.assert_called_once()
    direct_execute.assert_not_called()


def test_explicit_runtime_reaches_backend_backed_read_only_adapter() -> None:
    runtime = _dataset_info_runtime()

    result = ToolExecutor(
        object(),
        application_runtime=runtime,
    ).execute("get_dataset_info", {})

    assert isinstance(result, ToolCommandResult)
    assert result.ok is True
    assert result.message == (
        "Loaded 1 files:\ninjected-runtime.edf\nEvents: 7 (Unique: 1)"
    )
    assert result.raw_result["status"] == "ok"
    assert result.raw_result["command_name"] == "query_state"
    assert result.raw_result["changed_state"]["state_unknown"] is False
    diagnostics = result.raw_result["diagnostics"]
    assert diagnostics["count"] == 1
    assert diagnostics["total"] == 7
    assert diagnostics["unique_count"] == 1
    assert diagnostics["files"][0].startswith("file (.edf) [REDACTED_PATH]")
    assert "injected-runtime.edf" not in diagnostics["files"][0]
    assert result.state is not None
    runtime.execute.assert_called_once()
    assert isinstance(runtime.execute.call_args.args[0], QueryStateCommand)


def test_mapped_debug_command_fails_closed_without_application_runtime() -> None:
    with patch(
        "XBrainLab.debug.tool_executor.RealConfigureTrainingTool.execute",
    ) as direct_execute:
        result = ToolExecutor(object()).execute(
            "configure_training",
            _complete_training_params(),
        )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.error_type == "contract"
    assert result.error_code == "application_tool_runtime_required"
    direct_execute.assert_not_called()


@pytest.mark.parametrize("tool_name", MAPPED_DEBUG_TOOLS)
def test_every_mapped_debug_tool_fails_admission_without_direct_execution(
    tool_name: str,
) -> None:
    tool_class = ToolExecutor.TOOL_MAP[tool_name]

    with patch.object(tool_class, "execute") as direct_execute:
        result = ToolExecutor(object()).execute(tool_name, {})

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.error_type in {
        "contract",
        "input",
        "confirmation_required",
    }
    if result.error_type == "contract":
        assert result.error_code == "application_tool_runtime_required"
    direct_execute.assert_not_called()


def test_debug_schema_failure_does_not_execute_mapped_adapter_or_backend() -> None:
    study = Study()
    service = get_application_service(study)

    with (
        patch.object(service, "execute", wraps=service.execute) as execute,
        patch(
            "XBrainLab.debug.tool_executor.RealConfigureTrainingTool.execute",
        ) as direct_execute,
    ):
        result = ToolExecutor(study).execute(
            "configure_training",
            {"model_name": "EEGNet", "epoch": 2},
        )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.error_type == "input"
    assert result.state is not None
    execute.assert_not_called()
    direct_execute.assert_not_called()


def test_debug_confirmation_boundary_blocks_destructive_command() -> None:
    study = Study()
    service = get_application_service(study)
    executor = ToolExecutor(study)

    with (
        patch.object(service, "execute", wraps=service.execute) as execute,
        patch(
            "XBrainLab.debug.tool_executor.RealClearDatasetTool.execute",
        ) as direct_execute,
    ):
        result = executor.execute("clear_dataset", {})

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.error_type == "confirmation_required"
    execute.assert_not_called()
    direct_execute.assert_not_called()
    evidence = executor.last_execution_evidence
    assert evidence is not None
    assert evidence.dispatch_count == 1
    assert evidence.adapter_invocation_count == 0
    assert evidence.ui_adapter_invocation_count == 0
    assert evidence.runtime_command_invocation_count == 0
    assert evidence.publication_read_count == 1


def test_unknown_debug_tool_redacts_public_result_and_log(caplog) -> None:
    private_path = "/home/alice/private/subject-17"
    private_token = "token=hf_super_secret"  # noqa: S105
    tool_name = f"unknown_{private_path} {private_token}"

    with caplog.at_level("ERROR"):
        result = ToolExecutor(object()).execute(tool_name, {})

    assert isinstance(result, ToolCommandResult)
    public_output = f"{result!r}\n{caplog.text}"
    assert private_path not in public_output
    assert private_token not in public_output
    assert "hf_super_secret" not in public_output
    assert result.tool_name == "unknown_debug_tool"
    assert result.message == "The requested debug tool is unavailable."


def test_apply_interpretation_cannot_smuggle_schema_declared_confirmation() -> None:
    study = Study()
    service = get_application_service(study)

    with (
        patch.object(service, "execute", wraps=service.execute) as execute,
        patch(
            "XBrainLab.debug.tool_executor.RealApplyInterpretationTool.execute",
        ) as direct_execute,
    ):
        result = ToolExecutor(study).execute(
            "apply_interpretation",
            {"candidate_id": "candidate-1", "confirmed": True},
        )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.error_type == "input"
    assert result.diagnostics["policy"] == "host_confirmation_parameter"
    execute.assert_not_called()
    direct_execute.assert_not_called()


def test_explicit_debug_confirmation_executes_destructive_command_once() -> None:
    study = Study()
    service = get_application_service(study)

    with (
        patch.object(service, "execute", wraps=service.execute) as execute,
        patch(
            "XBrainLab.debug.tool_executor.RealClearDatasetTool.execute",
        ) as direct_execute,
    ):
        result = ToolExecutor(study).execute(
            "clear_dataset",
            {},
            confirmed=True,
        )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is True
    execute.assert_called_once()
    direct_execute.assert_not_called()


@pytest.mark.parametrize("untyped_confirmation", ["true", 1, object()])
def test_untyped_debug_confirmation_cannot_bypass_destructive_gate(
    untyped_confirmation,
) -> None:
    study = Study()
    service = get_application_service(study)

    with patch.object(service, "execute", wraps=service.execute) as execute:
        result = ToolExecutor(study).execute(
            "clear_dataset",
            {},
            confirmed=cast(Any, untyped_confirmation),
        )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.error_type == "confirmation_required"
    execute.assert_not_called()


def test_debug_path_policy_blocks_unattributed_direct_file_access(tmp_path) -> None:
    with patch(
        "XBrainLab.debug.tool_executor.RealListFilesTool.execute",
    ) as direct_execute:
        result = ToolExecutor(object()).execute(
            "list_files",
            {"directory": str(tmp_path)},
        )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.error_type == "input"
    assert result.diagnostics["policy"] == "path_provenance"
    direct_execute.assert_not_called()


def test_debug_path_policy_blocks_unattributed_mapped_file_access(tmp_path) -> None:
    study = Study()
    service = get_application_service(study)
    eeg_path = tmp_path / "unattributed.gdf"
    eeg_path.write_text("fixture", encoding="utf-8")

    with (
        patch.object(service, "execute", wraps=service.execute) as execute,
        patch(
            "XBrainLab.debug.tool_executor.RealLoadDataTool.execute",
        ) as direct_execute,
    ):
        result = ToolExecutor(study).execute(
            "load_data",
            {"paths": [str(eeg_path)]},
        )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.error_type == "input"
    assert result.diagnostics["policy"] == "path_provenance"
    execute.assert_not_called()
    direct_execute.assert_not_called()


def test_authorized_read_only_debug_tool_retains_direct_execution(tmp_path) -> None:
    fixture = tmp_path / "sample.gdf"
    fixture.write_text("fixture", encoding="utf-8")
    executor = ToolExecutor(object())

    with patch(
        "XBrainLab.debug.tool_executor.RealListFilesTool.execute",
        wraps=ToolExecutor.TOOL_MAP["list_files"]().execute,
    ) as direct_execute:
        result = executor.execute(
            "list_files",
            {"directory": str(tmp_path), "pattern": "*.gdf"},
            authorization_text=f"List files in `{tmp_path}`.",
        )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is True
    assert result.raw_result == ["sample.gdf"]
    direct_execute.assert_called_once()
    evidence = executor.last_execution_evidence
    assert evidence is not None
    assert evidence.dispatch_count == 1
    assert evidence.adapter_invocation_count == 1
    assert evidence.ui_adapter_invocation_count == 0
    assert evidence.runtime_command_invocation_count == 0
    assert evidence.publication_read_count == 0


def test_ui_debug_tool_records_exact_ui_adapter_invocation() -> None:
    executor = ToolExecutor(object())

    result = executor.execute(
        "switch_panel",
        {"panel_name": "visualization", "view_mode": "saliency_map"},
    )

    assert isinstance(result, UiRequest)
    evidence = executor.last_execution_evidence
    assert evidence is not None
    assert evidence.dispatch_count == 1
    assert evidence.adapter_invocation_count == 1
    assert evidence.ui_adapter_invocation_count == 1
    assert evidence.runtime_command_invocation_count == 0
    assert evidence.publication_read_count == 0


def test_debug_info_log_records_parameter_count_without_names_or_private_values(
    tmp_path,
    caplog,
    capture_product_logs,
) -> None:
    private_directory = tmp_path / "private-subject-data"
    private_directory.mkdir()

    with capture_product_logs(
        logging.INFO,
        logger_name="XBrainLab.debug.tool_executor",
    ):
        result = ToolExecutor(object()).execute(
            "list_files",
            {
                "directory": str(private_directory),
                "pattern": "subject-secret-*.edf",
            },
            authorization_text=f"List files in `{private_directory}`.",
        )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is True
    messages = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("Admitting debug tool")
    ]
    assert any("list_files" in message for message in messages)
    assert any("parameter count: 2" in message for message in messages)
    assert all("directory" not in message for message in messages)
    assert all("pattern" not in message for message in messages)
    assert all(str(private_directory) not in message for message in messages)
    assert all("subject-secret" not in message for message in messages)


def test_unclassified_debug_tool_cannot_gain_direct_execution() -> None:
    direct_execute = MagicMock()

    class _UnclassifiedTool(ToolExecutor.TOOL_MAP["list_files"]):
        @property
        def name(self) -> str:
            return "unsafe_mutation"

        execute = direct_execute

    with patch.dict(
        ToolExecutor.TOOL_MAP,
        {"unsafe_mutation": _UnclassifiedTool},
    ):
        result = ToolExecutor(object()).execute("unsafe_mutation", {})

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.error_type == "contract"
    assert result.recoverable is False
    direct_execute.assert_not_called()


def test_trusted_external_headless_script_covers_full_executor_surface(
    tmp_path,
    monkeypatch,
) -> None:
    from scripts.dev import verify_all_tools_headless

    script_path = tmp_path / "debug.json"
    expected_tools = sorted(ToolExecutor.TOOL_MAP)
    scripted_tools = expected_tools
    script_path.write_text(
        json.dumps(
            {
                "calls": [
                    {
                        "tool": tool_name,
                        "params": {},
                        "expected": _headless_success_expectation(tool_name),
                    }
                    for tool_name in scripted_tools
                ]
            }
        ),
        encoding="utf-8",
    )
    captured: dict[str, object] = {"tool_names": []}

    class _Executor:
        def __init__(self, study) -> None:
            captured["study"] = study

        def execute(
            self,
            tool_name,
            params,
            *,
            authorization_text,
        ) -> ToolCommandResult | UiRequest:
            cast_names = captured["tool_names"]
            assert isinstance(cast_names, list)
            cast_names.append(tool_name)
            assert params == {}
            assert authorization_text
            return _headless_success_result(tool_name)

    study = object()
    monkeypatch.setattr(verify_all_tools_headless, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(verify_all_tools_headless, "Study", lambda: study)
    monkeypatch.setattr(verify_all_tools_headless, "ToolExecutor", _Executor)

    assert (
        verify_all_tools_headless.verify_all_tools_script(
            str(script_path),
            trust_external_script=True,
        )
        is False
    )
    assert captured["study"] is study
    captured_tool_names = captured["tool_names"]
    assert isinstance(captured_tool_names, list)
    assert captured_tool_names == scripted_tools
    assert len(captured_tool_names) == 31
    assert all(
        captured_tool_names.count(tool_name) == 1 for tool_name in expected_tools
    )


def test_external_headless_script_is_refused_without_trusted_opt_in(
    tmp_path,
    monkeypatch,
) -> None:
    from scripts.dev import verify_all_tools_headless

    script_path = tmp_path / "external.json"
    script_path.write_text(
        json.dumps(
            {
                "calls": [
                    {"tool": tool_name, "params": {}}
                    for tool_name in sorted(ToolExecutor.TOOL_MAP)
                ]
            }
        ),
        encoding="utf-8",
    )
    study = MagicMock()
    monkeypatch.setattr(verify_all_tools_headless, "Study", study)

    assert verify_all_tools_headless.verify_all_tools_script(str(script_path)) is False
    study.assert_not_called()


@pytest.mark.parametrize(
    "calls",
    [
        pytest.param([], id="empty"),
        pytest.param(
            [{"tool": "list_files", "params": {}}],
            id="partial",
        ),
        pytest.param(
            [
                {"tool": "list_files", "params": {}}
                for _ in range(len(ToolExecutor.TOOL_MAP))
            ],
            id="duplicate-cannot-mask-partial",
        ),
        pytest.param(
            [
                *[
                    {"tool": tool_name, "params": {}}
                    for tool_name in sorted(ToolExecutor.TOOL_MAP)
                ],
                {"tool": "unknown_debug_tool", "params": {}},
            ],
            id="unknown",
        ),
    ],
)
def test_headless_script_rejects_incomplete_or_unknown_surface_before_execution(
    calls,
    tmp_path,
    monkeypatch,
) -> None:
    from scripts.dev import verify_all_tools_headless

    script_path = tmp_path / "invalid.json"
    script_path.write_text(json.dumps({"calls": calls}), encoding="utf-8")
    study = MagicMock()
    monkeypatch.setattr(verify_all_tools_headless, "Study", study)

    assert (
        verify_all_tools_headless.verify_all_tools_script(
            str(script_path),
            trust_external_script=True,
        )
        is False
    )
    study.assert_not_called()


def test_headless_script_rejects_duplicate_even_when_all_31_names_are_present(
    tmp_path,
    monkeypatch,
) -> None:
    from scripts.dev import verify_all_tools_headless

    calls = [
        {
            "tool": tool_name,
            "params": {},
            "expected": _headless_success_expectation(tool_name),
        }
        for tool_name in sorted(ToolExecutor.TOOL_MAP)
    ]
    calls.append(dict(calls[0]))
    script_path = tmp_path / "duplicate.json"
    script_path.write_text(json.dumps({"calls": calls}), encoding="utf-8")
    study = MagicMock()
    monkeypatch.setattr(verify_all_tools_headless, "Study", study)

    assert (
        verify_all_tools_headless.verify_all_tools_script(
            str(script_path),
            trust_external_script=True,
        )
        is False
    )
    study.assert_not_called()


def test_default_canonical_script_authorizes_declared_paths(
    tmp_path,
    monkeypatch,
) -> None:
    from scripts.dev import verify_all_tools_headless

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    script_path = tmp_path / "scripts" / "agent" / "debug" / "all_tools.json"
    script_path.parent.mkdir(parents=True)
    expected_tools = sorted(ToolExecutor.TOOL_MAP)
    script_path.write_text(
        json.dumps(
            {
                "calls": [
                    {
                        "tool": tool_name,
                        "params": (
                            {"directory": "data"} if tool_name == "list_files" else {}
                        ),
                        "expected": _headless_success_expectation(tool_name),
                    }
                    for tool_name in expected_tools
                ]
            }
        ),
        encoding="utf-8",
    )
    captured_authorization: dict[str, str] = {}

    class _Executor:
        def __init__(self, _study) -> None:
            pass

        def execute(
            self,
            tool_name,
            params,
            *,
            authorization_text,
        ) -> ToolCommandResult | UiRequest:
            if tool_name == "list_files":
                assert params == {"directory": str(data_dir)}
                captured_authorization["text"] = authorization_text
            return _headless_success_result(tool_name)

    monkeypatch.setattr(verify_all_tools_headless, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(verify_all_tools_headless, "Study", object)
    monkeypatch.setattr(verify_all_tools_headless, "ToolExecutor", _Executor)

    assert verify_all_tools_headless.verify_all_tools_script() is False
    prefix = "Canonical repository debug script call: "
    authorization_text = captured_authorization["text"]
    assert authorization_text.startswith(prefix)
    authorization = json.loads(authorization_text.removeprefix(prefix))
    assert authorization["params"]["directory"] == str(data_dir)


@pytest.mark.parametrize(
    ("changed_state", "diagnostics", "flag_name"),
    [
        ({"state_unknown": True}, {}, "changed_state.state_unknown"),
        ({"raw_changed": True}, {}, "changed_state.raw_changed"),
        ({}, {"refresh_required": True}, "diagnostics.refresh_required"),
        ({}, {"view_stale": True}, "diagnostics.view_stale"),
        ({}, {"policy_override": True}, "diagnostics.policy_override"),
        ({}, {"path_authorized": True}, "diagnostics.path_authorized"),
        ({}, {"confirmation_skipped": True}, "diagnostics.confirmation_skipped"),
        ({}, {"state_reliable": True}, "diagnostics.state_reliable"),
        ({}, {"safety_bypass": True}, "diagnostics.safety_bypass"),
        ({}, {"reliability_override": True}, "diagnostics.reliability_override"),
        ({}, {"authorization_skipped": True}, "diagnostics.authorization_skipped"),
    ],
)
def test_headless_matcher_rejects_unexpected_truthy_safety_flags(
    changed_state,
    diagnostics,
    flag_name,
) -> None:
    from scripts.dev import verify_all_tools_headless

    call = verify_all_tools_headless._VerifiedCall(
        tool_name="query_state",
        params={},
        confirmed=False,
        expected_ok=True,
        expected_error_type=None,
        expected_command_name="query_state",
        expected_changed_state={},
        expected_state={},
        expected_raw_result_contains=(),
        expected_ui_request_kind=None,
        expected_ui_params={},
    )
    result = ToolCommandResult(
        ok=True,
        tool_name="query_state",
        command_name="query_state",
        message="State ready.",
        changed_state=changed_state,
        diagnostics=diagnostics,
    )

    mismatches = verify_all_tools_headless._matches_expected(call, result)

    assert any(flag_name in mismatch for mismatch in mismatches)


def test_headless_matcher_allows_explicit_expected_safety_diagnostic() -> None:
    from scripts.dev import verify_all_tools_headless

    call = verify_all_tools_headless._VerifiedCall(
        tool_name="query_state",
        params={},
        confirmed=False,
        expected_ok=True,
        expected_error_type=None,
        expected_command_name="query_state",
        expected_changed_state={},
        expected_state={},
        expected_raw_result_contains=(),
        expected_ui_request_kind=None,
        expected_ui_params={},
        expected_diagnostics={"state_reliable": True},
    )
    result = ToolCommandResult(
        ok=True,
        tool_name="query_state",
        command_name="query_state",
        message="State ready.",
        diagnostics={"state_reliable": True},
    )

    assert verify_all_tools_headless._matches_expected(call, result) == []


def test_headless_matcher_does_not_reject_legitimate_diagnostic_metrics() -> None:
    from scripts.dev import verify_all_tools_headless

    call = verify_all_tools_headless._VerifiedCall(
        tool_name="query_state",
        params={},
        confirmed=False,
        expected_ok=True,
        expected_error_type=None,
        expected_command_name="query_state",
        expected_changed_state={},
        expected_state={},
        expected_raw_result_contains=(),
        expected_ui_request_kind=None,
        expected_ui_params={},
    )
    result = ToolCommandResult(
        ok=True,
        tool_name="query_state",
        command_name="query_state",
        message="State ready.",
        diagnostics={
            "path_count": 3,
            "policy_latency_ms": 11,
            "confirmation_duration_ms": 2,
        },
    )

    assert verify_all_tools_headless._matches_expected(call, result) == []
