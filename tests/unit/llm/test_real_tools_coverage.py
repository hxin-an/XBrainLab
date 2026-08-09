"""Canonical-surface contracts for real preprocess and dataset tools."""

from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.backend.application import (
    ChangedState,
    CommandName,
    CommandResult,
    ErrorType,
)
from XBrainLab.llm.tools import application_surface
from XBrainLab.llm.tools.application_surface import (
    ToolAvailability,
    ToolAvailabilityContext,
)
from XBrainLab.llm.tools.result_contract import ToolResult, UiRequest


def _assert_canonical_result(
    result: ToolResult,
    *,
    tool_name: str,
    ok: bool,
    message: str,
    payload: object,
    error_type: str,
    state: dict | None = None,
    recoverable: bool = True,
    error_code: str | None = None,
    recovery_action: str | None = None,
) -> None:
    assert result.ok is ok
    assert result.message == message
    assert result.diagnostics == payload
    if result.payload is None:
        assert payload == {}
    else:
        assert isinstance(result.payload, dict)
        assert result.payload["status"] == ("ok" if ok else "failed")
        assert result.payload["command_name"] == (
            application_surface.TOOL_TO_COMMAND[tool_name].value
        )
        assert result.payload["diagnostics"] == payload
        assert isinstance(result.payload["state"], dict)
        assert isinstance(result.payload["changed_state"], dict)
    assert result.error_type == error_type
    assert result.recoverable is recoverable
    assert result.command_name == application_surface.TOOL_TO_COMMAND[tool_name].value
    assert result.capability is not None
    assert result.capability["tool_name"] == tool_name
    assert result.state == ({} if result.payload is not None else state)
    assert isinstance(result.changed_state, dict)
    assert result.error_code == error_code
    assert result.recovery_action == recovery_action


def _assert_safe_unexpected_result(
    result: ToolResult,
    *,
    tool_name: str,
) -> None:
    assert result.ok is False
    assert result.message == (
        "The assistant tool could not complete the action. "
        "Refresh application state before retrying."
    )
    assert result.payload is None
    assert result.error_type == "runtime"
    assert result.recoverable is False
    assert result.command_name == application_surface.TOOL_TO_COMMAND[tool_name].value
    assert result.error_code == "unexpected_tool_failure"
    assert result.recovery_action == "refresh_application_state"
    assert result.state is None
    assert result.capability is None
    assert result.changed_state["state_unknown"] is True
    assert result.diagnostics["incident_id"]


def _command_result(
    *,
    command_name: str,
    failed: bool = False,
    message: str = "ok",
    diagnostics: dict | None = None,
) -> CommandResult:
    if failed:
        return CommandResult.failure_result(
            command_name=command_name,
            message=message,
            state={},
            changed_state=ChangedState(),
            error_type=ErrorType.RUNTIME,
            recoverable=True,
            diagnostics=diagnostics,
        )
    return CommandResult.success_result(
        command_name=command_name,
        message=message,
        state={},
        changed_state=ChangedState(),
        diagnostics=diagnostics,
    )


def _install_canonical_runtime(
    monkeypatch,
    tool_name: str,
    result: CommandResult | None = None,
    *,
    side_effect: Exception | None = None,
) -> tuple[MagicMock, MagicMock, MagicMock]:
    command_name = application_surface.TOOL_TO_COMMAND[tool_name].value
    availability = ToolAvailability(
        tool_name=tool_name,
        enabled=True,
        command_name=command_name,
    )
    context = ToolAvailabilityContext(
        availability=availability,
        state={"canonical_snapshot": True},
        generation=11,
    )
    get_context = MagicMock(return_value=context)
    runtime = MagicMock()
    if side_effect is not None:
        runtime.execute.side_effect = side_effect
    else:
        runtime.execute.return_value = result or _command_result(
            command_name=command_name,
        )
    runtime_provider = MagicMock(return_value=runtime)
    monkeypatch.setattr(application_surface, "get_application_context", get_context)
    monkeypatch.setattr(
        application_surface,
        "application_tool_runtime",
        runtime_provider,
    )
    return runtime, get_context, runtime_provider


# --- Real Preprocess Tools ---


@pytest.mark.parametrize(
    ("class_name", "tool_name", "kwargs"),
    [
        (
            "RealBandPassFilterTool",
            "apply_bandpass_filter",
            {"low_freq": None, "high_freq": 40.0},
        ),
        (
            "RealBandPassFilterTool",
            "apply_bandpass_filter",
            {"low_freq": 4.0, "high_freq": None},
        ),
        ("RealNotchFilterTool", "apply_notch_filter", {"freq": None}),
        ("RealResampleTool", "resample_data", {"rate": None}),
        ("RealNormalizeTool", "normalize_data", {"method": None}),
        ("RealRereferenceTool", "set_reference", {"method": None}),
        ("RealChannelSelectionTool", "select_channels", {"channels": None}),
    ],
)
def test_missing_preprocess_inputs_use_canonical_surface_validation(
    monkeypatch,
    class_name: str,
    tool_name: str,
    kwargs: dict,
):
    from XBrainLab.llm.tools.real import preprocess_real

    runtime, get_context, runtime_provider = _install_canonical_runtime(
        monkeypatch,
        tool_name,
    )
    study = object()

    result = getattr(preprocess_real, class_name)().execute(study, **kwargs)

    _assert_canonical_result(
        result,
        tool_name=tool_name,
        ok=False,
        message="Required inputs are missing for this workflow command.",
        payload={},
        error_type="input",
        state={"canonical_snapshot": True},
    )
    runtime.execute.assert_not_called()
    get_context.assert_called_once_with(study, tool_name, runtime=runtime)
    runtime_provider.assert_called_once_with(study)


@pytest.mark.parametrize(
    ("class_name", "tool_name", "kwargs", "expected_command_fields"),
    [
        (
            "RealBandPassFilterTool",
            "apply_bandpass_filter",
            {"low_freq": 4.0, "high_freq": 40.0},
            {"low_freq": 4.0, "high_freq": 40.0},
        ),
        (
            "RealNotchFilterTool",
            "apply_notch_filter",
            {"freq": 50.0},
            {"notch_freq": 50.0},
        ),
        (
            "RealResampleTool",
            "resample_data",
            {"rate": 256},
            {"rate": 256},
        ),
        (
            "RealNormalizeTool",
            "normalize_data",
            {"method": "z-score"},
            {"method": "z-score"},
        ),
        (
            "RealRereferenceTool",
            "set_reference",
            {"method": "average"},
            {"method": "average"},
        ),
        (
            "RealChannelSelectionTool",
            "select_channels",
            {"channels": ["C3"]},
            {"channels": ["C3"]},
        ),
    ],
)
def test_preprocess_runtime_errors_cross_the_canonical_surface(
    monkeypatch,
    class_name: str,
    tool_name: str,
    kwargs: dict,
    expected_command_fields: dict,
):
    from XBrainLab.llm.tools.real import preprocess_real

    error = RuntimeError(f"{tool_name} exploded")
    runtime, get_context, runtime_provider = _install_canonical_runtime(
        monkeypatch,
        tool_name,
        side_effect=error,
    )
    study = object()

    result = getattr(preprocess_real, class_name)().execute(study, **kwargs)

    command = runtime.execute.call_args.args[0]
    for field, expected in expected_command_fields.items():
        assert getattr(command, field) == expected
    _assert_safe_unexpected_result(result, tool_name=tool_name)
    get_context.assert_called_once_with(study, tool_name, runtime=runtime)
    runtime_provider.assert_called_once_with(study)


class TestRealSetMontageValidation:
    def test_missing_montage_name(self):
        from XBrainLab.llm.tools.real.preprocess_real import RealSetMontageTool

        result = RealSetMontageTool().execute(study=MagicMock(), montage_name=None)
        assert isinstance(result, ToolResult)
        assert result.ok is False
        assert result.error_type == "input"
        assert "montage name" in result.message


class TestRealEpochDataError:
    def test_runtime_exception_uses_canonical_surface(self, monkeypatch):
        from XBrainLab.llm.tools.real.preprocess_real import RealEpochDataTool

        error = RuntimeError("bad epoch")
        runtime, get_context, runtime_provider = _install_canonical_runtime(
            monkeypatch,
            "epoch_data",
            side_effect=error,
        )
        study = object()

        result = RealEpochDataTool().execute(study=study, t_min=-0.1, t_max=1.0)

        command = runtime.execute.call_args.args[0]
        assert command.t_min == -0.1
        assert command.t_max == 1.0
        assert command.baseline is None
        assert command.event_ids is None
        _assert_safe_unexpected_result(result, tool_name="epoch_data")
        get_context.assert_called_once_with(study, "epoch_data", runtime=runtime)
        runtime_provider.assert_called_once_with(study)


class TestRealStandardPreprocessOptionalSteps:
    """Verify optional parameters are translated only by ApplicationSurface."""

    def test_all_optional_steps(self, monkeypatch):
        from XBrainLab.backend.application import PreprocessOperation
        from XBrainLab.llm.tools.real.preprocess_real import RealStandardPreprocessTool

        runtime, get_context, runtime_provider = _install_canonical_runtime(
            monkeypatch,
            "apply_standard_preprocess",
            _command_result(
                command_name=CommandName.PREPROCESS.value,
                message="Standard preprocessing applied.",
                diagnostics={"operations": 6},
            ),
        )
        study = object()

        result = RealStandardPreprocessTool().execute(
            study=study,
            l_freq=4.0,
            h_freq=40.0,
            notch_freq=50.0,
            resample_rate=256,
            rereference="average",
            normalize_method="z-score",
        )

        command = runtime.execute.call_args.args[0]
        assert command.operation == PreprocessOperation.STANDARD
        assert command.low_freq == 4.0
        assert command.high_freq == 40.0
        assert command.notch_freq == 50.0
        assert command.rate == 256
        assert command.method == "z-score"
        assert command.channels == ["average"]
        _assert_canonical_result(
            result,
            tool_name="apply_standard_preprocess",
            ok=True,
            message="Standard preprocessing applied.",
            payload={"operations": 6},
            error_type="none",
        )
        get_context.assert_called_once_with(
            study,
            "apply_standard_preprocess",
            runtime=runtime,
        )
        runtime_provider.assert_called_once_with(study)


# --- Real Dataset Tools ---


class TestRealListFilesValidation:
    def test_empty_directory(self):
        from XBrainLab.llm.tools.real.dataset_real import RealListFilesTool

        result = RealListFilesTool().execute(study=MagicMock(), directory=None)
        assert result.ok is False
        assert result.error_type == "input"

    @patch("XBrainLab.llm.tools.real.dataset_real.os.path.isdir", return_value=False)
    def test_nonexistent_directory(self, _mock):
        from XBrainLab.llm.tools.real.dataset_real import RealListFilesTool

        result = RealListFilesTool().execute(
            study=MagicMock(), directory="/nonexistent/path"
        )
        assert result.ok is False
        assert "does not exist" in result.message


class TestRealLoadDataValidation:
    _DENIAL = (
        "Direct assistant file loading is unavailable because the legacy loader "
        "cannot preserve an authorized filesystem identity through file parsing. "
        "Use scan_source and the Data Interpretation workflow instead."
    )

    @pytest.mark.parametrize("paths", [None, []])
    def test_empty_paths_use_canonical_surface_validation(self, monkeypatch, paths):
        from XBrainLab.llm.tools.real.dataset_real import RealLoadDataTool

        runtime, get_context, runtime_provider = _install_canonical_runtime(
            monkeypatch,
            "load_data",
        )
        study = object()

        result = RealLoadDataTool().execute(study=study, paths=paths)

        _assert_canonical_result(
            result,
            tool_name="load_data",
            ok=False,
            message=self._DENIAL,
            payload={},
            error_type="precondition",
            state={"canonical_snapshot": True},
            recoverable=False,
            error_code="assistant_direct_load_disabled",
            recovery_action=(
                "Use scan_source, preview_interpretation, "
                "validate_interpretation, and apply_interpretation."
            ),
        )
        runtime.execute.assert_not_called()
        get_context.assert_called_once_with(study, "load_data", runtime=runtime)
        runtime_provider.assert_called_once_with(study)

    def test_configured_runtime_success_cannot_bypass_direct_load_denial(
        self,
        monkeypatch,
    ):
        from XBrainLab.llm.tools.real.dataset_real import RealLoadDataTool

        runtime, get_context, runtime_provider = _install_canonical_runtime(
            monkeypatch,
            "load_data",
            _command_result(
                command_name=CommandName.LOAD_DATA.value,
                message="Loaded 2 file(s); 1 failed.",
                diagnostics={"success_count": 2, "errors": ["err1"]},
            ),
        )
        study = object()

        result = RealLoadDataTool().execute(
            study=study,
            paths=["/a.gdf", "/b.gdf"],
        )

        _assert_canonical_result(
            result,
            tool_name="load_data",
            ok=False,
            message=self._DENIAL,
            payload={},
            error_type="precondition",
            state={"canonical_snapshot": True},
            recoverable=False,
            error_code="assistant_direct_load_disabled",
            recovery_action=(
                "Use scan_source, preview_interpretation, "
                "validate_interpretation, and apply_interpretation."
            ),
        )
        runtime.execute.assert_not_called()
        get_context.assert_called_once_with(study, "load_data", runtime=runtime)
        runtime_provider.assert_called_once_with(study)


class TestRealAttachLabelsValidation:
    def test_missing_mapping_uses_canonical_surface_validation(self, monkeypatch):
        from XBrainLab.llm.tools.real.dataset_real import RealAttachLabelsTool

        runtime, get_context, runtime_provider = _install_canonical_runtime(
            monkeypatch,
            "attach_labels",
        )
        study = object()

        result = RealAttachLabelsTool().execute(study=study, mapping=None)

        _assert_canonical_result(
            result,
            tool_name="attach_labels",
            ok=False,
            message="Required inputs are missing for this workflow command.",
            payload={},
            error_type="input",
            state={"canonical_snapshot": True},
        )
        runtime.execute.assert_not_called()
        get_context.assert_called_once_with(study, "attach_labels", runtime=runtime)
        runtime_provider.assert_called_once_with(study)

    def test_no_labels_attached_preserves_canonical_result(self, monkeypatch):
        from XBrainLab.llm.tools.real.dataset_real import RealAttachLabelsTool

        runtime, get_context, runtime_provider = _install_canonical_runtime(
            monkeypatch,
            "attach_labels",
            _command_result(
                command_name=CommandName.ATTACH_LABELS.value,
                message="No labels attached.",
                diagnostics={"success_count": 0},
            ),
        )
        study = object()

        result = RealAttachLabelsTool().execute(study=study, mapping={"a": "b"})

        command = runtime.execute.call_args.args[0]
        assert command.mapping == {"a": "b"}
        assert command.label_paths == ["b"]
        _assert_canonical_result(
            result,
            tool_name="attach_labels",
            ok=True,
            message="No labels attached.",
            payload={"success_count": 0},
            error_type="none",
        )
        get_context.assert_called_once_with(study, "attach_labels", runtime=runtime)
        runtime_provider.assert_called_once_with(study)


class TestRealGetDatasetInfoEvents:
    def test_summary_with_events_uses_canonical_query(self, monkeypatch):
        from XBrainLab.llm.tools.real.dataset_real import RealGetDatasetInfoTool

        runtime, get_context, runtime_provider = _install_canonical_runtime(
            monkeypatch,
            "query_state",
            _command_result(
                command_name=CommandName.QUERY_STATE.value,
                message="Dataset summary.",
                diagnostics={
                    "count": 3,
                    "files": ["a.gdf", "b.gdf", "c.gdf"],
                    "total": 120,
                    "unique_count": 4,
                },
            ),
        )
        study = object()

        result = RealGetDatasetInfoTool().execute(study=study)

        command = runtime.execute.call_args.args[0]
        assert command.query == "data_summary"
        assert result.ok is True
        assert result.message == (
            "Loaded 3 files:\na.gdf\nb.gdf\nc.gdf\nEvents: 120 (Unique: 4)"
        )
        assert result.diagnostics == {
            "count": 3,
            "files": ["a.gdf", "b.gdf", "c.gdf"],
            "total": 120,
            "unique_count": 4,
        }
        assert isinstance(result.payload, dict)
        assert result.payload["status"] == "ok"
        assert result.payload["command_name"] == CommandName.QUERY_STATE.value
        public_files = result.payload["diagnostics"]["files"]
        assert len(public_files) == 3
        assert all("[REDACTED_PATH]" in value for value in public_files)
        assert all(
            raw_name not in public_files for raw_name in ("a.gdf", "b.gdf", "c.gdf")
        )
        assert result.error_type == "none"
        get_context.assert_called_once_with(study, "query_state", runtime=runtime)
        runtime_provider.assert_called_once_with(study)


class TestRealGenerateDatasetError:
    def test_generation_failure_preserves_canonical_result(self, monkeypatch):
        from XBrainLab.llm.tools.real.dataset_real import RealGenerateDatasetTool

        runtime, get_context, runtime_provider = _install_canonical_runtime(
            monkeypatch,
            "generate_dataset",
            _command_result(
                command_name=CommandName.GENERATE_DATASET.value,
                failed=True,
                message="Dataset generation failed.",
                diagnostics={"reason": "split unavailable"},
            ),
        )
        study = object()

        result = RealGenerateDatasetTool().execute(study=study)

        command = runtime.execute.call_args.args[0]
        assert command.test_ratio == 0.2
        assert command.val_ratio == 0.2
        assert command.split_strategy == "trial"
        assert command.training_mode == "individual"
        _assert_canonical_result(
            result,
            tool_name="generate_dataset",
            ok=False,
            message="Dataset generation failed.",
            payload={"reason": "split unavailable"},
            error_type="runtime",
        )
        get_context.assert_called_once_with(
            study,
            "generate_dataset",
            runtime=runtime,
        )
        runtime_provider.assert_called_once_with(study)


# --- Tool Registry ---


class TestToolRegistryOverwrite:
    def test_registration_replaces_the_tool_under_the_same_public_name(self):
        from XBrainLab.llm.tools.tool_registry import ToolRegistry

        reg = ToolRegistry()
        first = MagicMock(name="first_tool", name_for_mock="first_tool")
        second = MagicMock(name="second_tool", name_for_mock="second_tool")
        first.name = "shared_name"
        second.name = "shared_name"

        reg.register(first)
        reg.register(second)

        assert reg.get_tool("shared_name") is second
        assert reg.get_all_tools() == [second]


# --- UI Control Real ---


class TestRealSwitchPanelNoViewMode:
    def test_no_view_mode(self):
        from XBrainLab.llm.tools.real.ui_control_real import RealSwitchPanelTool

        tool = RealSwitchPanelTool()
        result = tool.execute(study=MagicMock(), panel_name="training", view_mode=None)
        assert isinstance(result, UiRequest)
        assert result.kind.value == "switch_panel"
        assert result.params == {"panel": "training", "view_mode": None}
