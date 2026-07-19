from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from XBrainLab.backend.application import get_application_service
from XBrainLab.backend.study import Study
from XBrainLab.llm.tools import (
    bind_real_tool_execution_context,
    execute_real_application_tool,
)
from XBrainLab.llm.tools.application_surface import (
    ToolCommandResult,
    normalize_tool_result,
)
from XBrainLab.llm.tools.real import (
    analysis_real,
    dataset_real,
    preprocess_real,
    training_real,
)
from XBrainLab.llm.tools.real.ui_control_real import RealSwitchPanelTool
from XBrainLab.llm.tools.result_contract import ToolResult, UiRequest, UiRequestKind

_MAPPED_TOOL_CASES = (
    (
        dataset_real,
        dataset_real.RealScanSourceTool(),
        {"source_path": "/data/session.gdf"},
        {
            "source_path": "/data/session.gdf",
            "source_hint": "auto",
            "label_sources": None,
        },
    ),
    (
        dataset_real,
        dataset_real.RealPreviewInterpretationTool(),
        {"scan_id": "scan-1", "choices": {"subject": "01"}},
        {
            "scan_id": "scan-1",
            "choices": {"subject": "01"},
            "resource_preflight_confirmed": False,
            "resource_preflight_token": None,
        },
    ),
    (
        dataset_real,
        dataset_real.RealValidateInterpretationTool(),
        {"candidate_id": "candidate-1"},
        {"candidate_id": "candidate-1"},
    ),
    (
        dataset_real,
        dataset_real.RealApplyInterpretationTool(),
        {"candidate_id": "candidate-1", "confirmed": True},
        {
            "candidate_id": "candidate-1",
            "confirmed": True,
            "resource_preflight_confirmed": False,
            "resource_preflight_token": None,
        },
    ),
    (
        dataset_real,
        dataset_real.RealSaveInterpretationRecipeTool(),
        {"recipe_path": "/tmp/recipe.json"},
        {"recipe_path": "/tmp/recipe.json"},
    ),
    (
        dataset_real,
        dataset_real.RealReloadInterpretationRecipeTool(),
        {"recipe_path": "/tmp/recipe.json"},
        {
            "recipe_path": "/tmp/recipe.json",
            "resource_preflight_confirmed": False,
            "resource_preflight_token": None,
        },
    ),
    (
        dataset_real,
        dataset_real.RealLoadDataTool(),
        {"paths": ["/data/session.gdf"]},
        {
            "paths": ["/data/session.gdf"],
            "allow_append": True,
            "resource_preflight_confirmed": False,
            "resource_preflight_token": None,
        },
    ),
    (
        dataset_real,
        dataset_real.RealAttachLabelsTool(),
        {"mapping": {"session.gdf": "/data/session.mat"}},
        {
            "mapping": {"session.gdf": "/data/session.mat"},
            "label_format": None,
            "resource_preflight_confirmed": False,
            "resource_preflight_token": None,
        },
    ),
    (
        dataset_real,
        dataset_real.RealClearDatasetTool(),
        {"confirmed": True},
        {"confirmed": True},
    ),
    (
        dataset_real,
        dataset_real.RealQueryStateTool(),
        {"query": "state"},
        {"query": "state"},
    ),
    (
        dataset_real,
        dataset_real.RealGenerateDatasetTool(),
        {},
        {
            "test_ratio": 0.2,
            "val_ratio": 0.2,
            "split_strategy": "trial",
            "training_mode": "individual",
        },
    ),
    (
        analysis_real,
        analysis_real.RealEvaluateTool(),
        {"target": "latest"},
        {"target": "latest"},
    ),
    (
        analysis_real,
        analysis_real.RealVisualizeTool(),
        {"view": "summary"},
        {"view": "summary"},
    ),
    (
        analysis_real,
        analysis_real.RealSaliencyTool(),
        {"method": "Gradient", "params": {"target": 1}},
        {"method": "Gradient", "params": {"target": 1}},
    ),
    (
        preprocess_real,
        preprocess_real.RealStandardPreprocessTool(),
        {},
        {
            "l_freq": 4,
            "h_freq": 40,
            "notch_freq": 50,
            "rereference": None,
            "resample_rate": None,
            "normalize_method": "z-score",
        },
    ),
    (
        preprocess_real,
        preprocess_real.RealResetPreprocessTool(),
        {"confirmed": True},
        {"confirmed": True},
    ),
    (
        preprocess_real,
        preprocess_real.RealBandPassFilterTool(),
        {"low_freq": 1, "high_freq": 40},
        {"low_freq": 1, "high_freq": 40},
    ),
    (
        preprocess_real,
        preprocess_real.RealNotchFilterTool(),
        {"freq": 50},
        {"freq": 50},
    ),
    (
        preprocess_real,
        preprocess_real.RealResampleTool(),
        {"rate": 128},
        {"rate": 128},
    ),
    (
        preprocess_real,
        preprocess_real.RealNormalizeTool(),
        {"method": "z-score"},
        {"method": "z-score"},
    ),
    (
        preprocess_real,
        preprocess_real.RealRereferenceTool(),
        {"method": "average"},
        {"method": "average"},
    ),
    (
        preprocess_real,
        preprocess_real.RealChannelSelectionTool(),
        {"channels": ["C3", "C4"]},
        {"channels": ["C3", "C4"]},
    ),
    (
        preprocess_real,
        preprocess_real.RealEpochDataTool(),
        {"t_min": 0, "t_max": 4, "event_id": ["left", "right"]},
        {
            "t_min": 0,
            "t_max": 4,
            "baseline": None,
            "event_id": ["left", "right"],
        },
    ),
    (
        training_real,
        training_real.RealSetModelTool(),
        {"model_name": "EEGNet"},
        {"model_name": "EEGNet"},
    ),
    (
        training_real,
        training_real.RealConfigureTrainingTool(),
        {"epoch": 3, "batch_size": 4, "learning_rate": 0.001},
        {
            "model_name": None,
            "epoch": 3,
            "batch_size": 4,
            "learning_rate": 0.001,
            "repeat": 1,
            "device": "cpu",
            "optimizer": "adam",
            "evaluation_option": "last_epoch",
            "save_checkpoints_every": 0,
        },
    ),
    (
        training_real,
        training_real.RealStartTrainingTool(),
        {"confirmed": True},
        {
            "append": True,
            "interactive": True,
            "confirmed": True,
            "resource_preflight_confirmed": False,
            "resource_preflight_token": None,
        },
    ),
    (
        training_real,
        training_real.RealStopTrainingTool(),
        {},
        {},
    ),
)


@pytest.mark.parametrize(
    ("module", "tool", "kwargs", "expected_params"),
    _MAPPED_TOOL_CASES,
    ids=lambda value: getattr(value, "name", None),
)
def test_mapped_real_tool_execute_is_a_thin_canonical_delegate(
    monkeypatch,
    module,
    tool,
    kwargs: dict[str, Any],
    expected_params: dict[str, Any],
) -> None:
    captured: dict[str, Any] = {}
    canonical_result = ToolResult(
        True,
        "Canonical result",
        payload={"operation_id": "op-1"},
    )

    def _delegate(study: Any, tool_name: str, params: dict[str, Any]) -> ToolResult:
        captured.update({"study": study, "tool_name": tool_name, "params": params})
        return canonical_result

    monkeypatch.setattr(module, "execute_real_application_tool", _delegate)
    study = object()

    result = tool.execute(study, **kwargs)

    assert result is canonical_result
    assert captured == {
        "study": study,
        "tool_name": tool.name,
        "params": expected_params,
    }


def test_direct_real_adapter_preserves_canonical_result_metadata() -> None:
    study = Study()

    direct_result = training_real.RealSetModelTool().execute(
        study,
        model_name="EEGNet",
    )
    normalized = normalize_tool_result(study, "set_model", direct_result)

    assert direct_result.command_name == "configure_training"
    assert direct_result.state is not None
    assert direct_result.state["training"]["model_name"] == "EEGNet"
    assert direct_result.capability is not None
    assert direct_result.changed_state["training_changed"] is True
    assert isinstance(direct_result.payload, dict)
    assert direct_result.payload["status"] == "ok"
    assert direct_result.payload["command_name"] == "configure_training"
    assert direct_result.payload["state"]["training"]["model_name"] == "EEGNet"
    assert direct_result.payload["changed_state"]["training_changed"] is True
    assert isinstance(normalized, ToolCommandResult)
    assert normalized.command_name == direct_result.command_name
    assert normalized.state == direct_result.state
    assert normalized.capability == direct_result.capability
    assert normalized.changed_state == direct_result.changed_state
    assert normalized.error_code == direct_result.error_code
    assert normalized.recovery_action == direct_result.recovery_action
    assert normalized.raw_result == direct_result.payload


def test_direct_adapter_recovers_authoritative_publication_after_post_execute_failure(
    monkeypatch,
) -> None:
    study = Study()
    service = get_application_service(study)
    execute_calls: list[object] = []

    class _Runtime:
        def get_view_publication(self):
            return service.get_view_publication()

        def execute(self, command):
            execute_calls.append(command)
            return service.execute(command)

    def _fail_after_execute(*_args, **_kwargs):
        raise RuntimeError("normalization failed after backend execution")

    monkeypatch.setattr(
        ToolCommandResult,
        "from_command_result",
        classmethod(_fail_after_execute),
    )
    runtime = _Runtime()

    result = execute_real_application_tool(
        bind_real_tool_execution_context(study, runtime),
        "set_model",
        {"model_name": "EEGNet"},
    )

    assert result.ok is False
    assert len(execute_calls) == 1
    assert result.state is not None
    assert result.state["training"]["model_name"] == "EEGNet"
    assert result.changed_state["state_unknown"] is False
    assert result.diagnostics["state_source"] == "authoritative_publication"
    assert result.diagnostics["publication_generation"] >= 1
    assert result.diagnostics["refresh_required"] is False


def test_direct_adapter_marks_state_unknown_when_publication_recovery_fails(
    monkeypatch,
) -> None:
    study = Study()
    service = get_application_service(study)
    publication_reads = 0

    class _Runtime:
        def get_view_publication(self):
            nonlocal publication_reads
            publication_reads += 1
            if publication_reads > 1:
                raise RuntimeError("publication unavailable")
            return service.get_view_publication()

        def execute(self, command):
            return service.execute(command)

    def _fail_after_execute(*_args, **_kwargs):
        raise RuntimeError("normalization failed after backend execution")

    monkeypatch.setattr(
        ToolCommandResult,
        "from_command_result",
        classmethod(_fail_after_execute),
    )

    result = execute_real_application_tool(
        bind_real_tool_execution_context(study, _Runtime()),
        "set_model",
        {"model_name": "EEGNet"},
    )

    assert result.ok is False
    assert result.state is None
    assert result.changed_state["state_unknown"] is True
    assert result.diagnostics["state_source"] == "unavailable"
    assert result.diagnostics["refresh_required"] is True


def test_get_dataset_info_uses_canonical_query_and_formats_read_only_result(
    monkeypatch,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def _delegate(study: Any, tool_name: str, params: dict[str, Any]) -> ToolResult:
        calls.append((tool_name, params))
        return ToolResult(
            True,
            "Dataset summary",
            payload={
                "count": 1,
                "files": ["session.gdf"],
                "total": 12,
                "unique_count": 2,
            },
        )

    monkeypatch.setattr(dataset_real, "execute_real_application_tool", _delegate)

    result = dataset_real.RealGetDatasetInfoTool().execute(object())

    assert result.ok is True
    assert result.message == ("Loaded 1 files:\nsession.gdf\nEvents: 12 (Unique: 2)")
    assert calls == [("query_state", {"query": "data_summary"})]


def test_list_files_remains_a_direct_read_only_tool(tmp_path: Path) -> None:
    (tmp_path / "session.gdf").touch()
    (tmp_path / "notes.txt").touch()

    result = dataset_real.RealListFilesTool().execute(
        object(),
        directory=str(tmp_path),
        pattern="*.gdf",
    )

    assert result.ok is True
    assert result.payload == ["session.gdf"]


def test_set_montage_remains_a_typed_ui_request(monkeypatch) -> None:
    def _delegate(study: Any, tool_name: str, params: dict[str, Any]) -> ToolResult:
        assert tool_name == "query_state"
        assert params == {"query": "preprocess_diagnostics"}
        return ToolResult(
            True,
            "Diagnostics",
            payload={
                "gdf_duplicate_channel_details": [
                    {"file": "A01T.gdf", "generated_bases": ["EEG"]}
                ]
            },
        )

    monkeypatch.setattr(preprocess_real, "execute_real_application_tool", _delegate)

    result = preprocess_real.RealSetMontageTool().execute(
        object(),
        montage_name="standard_1020",
    )

    assert isinstance(result, UiRequest)
    assert result.kind is UiRequestKind.CONFIRM_MONTAGE
    assert result.params["montage_name"] == "standard_1020"
    assert "A01T.gdf" in result.params["warning"]


def test_switch_panel_remains_a_typed_ui_request() -> None:
    result = RealSwitchPanelTool().execute(
        object(),
        panel_name="training",
        view_mode="history",
    )

    assert isinstance(result, UiRequest)
    assert result.kind is UiRequestKind.SWITCH_PANEL
    assert result.params == {"panel": "training", "view_mode": "history"}
