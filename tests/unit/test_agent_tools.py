import os
from unittest.mock import MagicMock

from XBrainLab.backend.application.results import ChangedState, CommandResult
from XBrainLab.llm.tools import application_surface
from XBrainLab.llm.tools.application_surface import (
    ToolAvailability,
    ToolAvailabilityContext,
)
from XBrainLab.llm.tools.real.dataset_real import RealLoadDataTool
from XBrainLab.llm.tools.result_contract import ToolResult


def _command_result(
    *,
    message: str,
    diagnostics: dict[str, object],
) -> CommandResult:
    return CommandResult.success_result(
        command_name="load_data",
        message=message,
        state={},
        changed_state=ChangedState(raw_changed=True),
        diagnostics=diagnostics,
    )


def _install_canonical_runtime(monkeypatch, result: CommandResult):
    availability = ToolAvailability(
        tool_name="load_data",
        enabled=True,
        command_name="load_data",
    )
    context = ToolAvailabilityContext(
        availability=availability,
        state={"raw": {"count": 0}},
        generation=7,
    )
    get_context = MagicMock(return_value=context)
    runtime = MagicMock()
    runtime.execute.return_value = result
    runtime_provider = MagicMock(return_value=runtime)
    monkeypatch.setattr(application_surface, "get_application_context", get_context)
    monkeypatch.setattr(
        application_surface,
        "application_tool_runtime",
        runtime_provider,
    )
    return runtime, get_context, runtime_provider


def _assert_structured_load_result(
    result: ToolResult,
    *,
    message: str,
    success_count: int,
) -> None:
    assert result.ok is True
    assert result.message == message
    assert result.command_name == "load_data"
    assert result.error_type == "none"
    assert result.recoverable is True
    assert result.state == {}
    assert result.capability is not None
    assert result.capability["tool_name"] == "load_data"
    assert result.diagnostics == {"success_count": success_count, "errors": []}
    assert result.changed_state["raw_changed"] is True
    assert isinstance(result.payload, dict)
    assert result.payload["command_name"] == "load_data"
    assert result.payload["diagnostics"] == result.diagnostics


class TestRealLoadDataTool:
    def test_directory_expansion(self, monkeypatch):
        """Directory expansion belongs to the canonical ApplicationSurface."""
        monkeypatch.setattr(
            application_surface.os.path,
            "isdir",
            lambda path: path in {"dir_path", "dir_path/subdir"},
        )
        monkeypatch.setattr(
            application_surface.os,
            "listdir",
            lambda _path: ["file2.gdf", "subdir", "file1.set"],
        )
        valid_files = {
            os.path.join("dir_path", "file1.set"),
            os.path.join("dir_path", "file2.gdf"),
        }
        monkeypatch.setattr(
            application_surface.os.path,
            "isfile",
            lambda path: path in valid_files,
        )
        command_result = _command_result(
            message="Loaded 2 file(s).",
            diagnostics={"success_count": 2, "errors": []},
        )
        runtime, get_context, runtime_provider = _install_canonical_runtime(
            monkeypatch,
            command_result,
        )
        study = object()

        result = RealLoadDataTool().execute(study, paths=["dir_path"])

        command = runtime.execute.call_args.args[0]
        assert command.paths == [
            os.path.join("dir_path", "file1.set"),
            os.path.join("dir_path", "file2.gdf"),
        ]
        assert command.allow_append is True
        assert command.resource_preflight_confirmed is False
        assert command.resource_preflight_token is None
        _assert_structured_load_result(
            result,
            message="Loaded 2 file(s).",
            success_count=2,
        )
        get_context.assert_called_once_with(study, "load_data", runtime=runtime)
        runtime_provider.assert_called_once_with(study)

    def test_mixed_paths_expansion(self, monkeypatch):
        """File and directory inputs retain order through canonical translation."""
        monkeypatch.setattr(
            application_surface.os.path,
            "isdir",
            lambda path: path == "dir_path",
        )
        monkeypatch.setattr(
            application_surface.os,
            "listdir",
            lambda _path: ["b.gdf", "a.gdf"],
        )
        monkeypatch.setattr(
            application_surface.os.path,
            "isfile",
            lambda path: path
            in {
                os.path.join("dir_path", "a.gdf"),
                os.path.join("dir_path", "b.gdf"),
            },
        )
        command_result = _command_result(
            message="Loaded 3 file(s).",
            diagnostics={"success_count": 3, "errors": []},
        )
        runtime, get_context, runtime_provider = _install_canonical_runtime(
            monkeypatch,
            command_result,
        )
        study = object()

        result = RealLoadDataTool().execute(
            study,
            paths=["standalone.edf", "dir_path"],
            allow_append=False,
        )

        command = runtime.execute.call_args.args[0]
        assert command.paths == [
            "standalone.edf",
            os.path.join("dir_path", "a.gdf"),
            os.path.join("dir_path", "b.gdf"),
        ]
        assert command.allow_append is False
        _assert_structured_load_result(
            result,
            message="Loaded 3 file(s).",
            success_count=3,
        )
        get_context.assert_called_once_with(study, "load_data", runtime=runtime)
        runtime_provider.assert_called_once_with(study)
