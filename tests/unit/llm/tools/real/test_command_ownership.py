from pathlib import Path
from typing import Any

from tests.architecture_compliance import (
    check_mapped_real_tool_command_ownership,
)
from XBrainLab.backend.application import (
    ConfigureTrainingCommand,
    get_application_service,
)
from XBrainLab.backend.study import Study
from XBrainLab.llm.tools import execute_real_application_tool
from XBrainLab.llm.tools.application_surface import (
    authorize_assistant_setting_change,
    build_load_data_command,
)
from XBrainLab.llm.tools.real import (
    analysis_real,
    dataset_real,
    preprocess_real,
    training_real,
)
from XBrainLab.llm.tools.result_contract import ToolResult


def test_mapped_real_tools_delegate_command_ownership_to_application_surface() -> None:
    root = Path(__file__).resolve().parents[5]

    assert check_mapped_real_tool_command_ownership(root) == []


def test_load_data_adapter_delegates_but_canonical_builder_denies_direct_load(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "b.gdf").touch()
    (source_dir / "a.gdf").touch()
    delegated: dict[str, Any] = {}

    def _delegate(study: Any, tool_name: str, params: dict[str, Any]) -> ToolResult:
        delegated.update(
            {
                "study": study,
                "tool_name": tool_name,
                "params": params,
            }
        )
        return ToolResult(True, "delegated")

    monkeypatch.setattr(dataset_real, "execute_real_application_tool", _delegate)
    study = object()

    result = dataset_real.RealLoadDataTool().execute(
        study,
        paths=[str(source_dir)],
    )

    assert result.ok is True
    assert delegated == {
        "study": study,
        "tool_name": "load_data",
        "params": {
            "paths": [str(source_dir)],
            "allow_append": True,
            "resource_preflight_confirmed": False,
            "resource_preflight_token": None,
        },
    }

    command = build_load_data_command({"paths": [str(source_dir)]})
    assert command is None


def test_representative_real_adapters_delegate_raw_parameters(
    monkeypatch,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def _delegate(study: Any, tool_name: str, params: dict[str, Any]) -> ToolResult:
        calls.append((tool_name, params))
        return ToolResult(True, "delegated")

    monkeypatch.setattr(analysis_real, "execute_real_application_tool", _delegate)
    monkeypatch.setattr(preprocess_real, "execute_real_application_tool", _delegate)
    monkeypatch.setattr(training_real, "execute_real_application_tool", _delegate)
    study = object()

    analysis_real.RealSaliencyTool().execute(
        study,
        method="SmoothGrad",
        nt_samples=2,
        nt_samples_batch_size=1,
        stdevs=0.5,
    )
    preprocess_real.RealBandPassFilterTool().execute(
        study,
        low_freq=1,
        high_freq=40,
    )
    training_real.RealStartTrainingTool().execute(
        study,
        confirmed=True,
        append=False,
    )

    assert calls == [
        (
            "saliency",
            {
                "method": "SmoothGrad",
                "params": {
                    "nt_samples": 2,
                    "nt_samples_batch_size": 1,
                    "stdevs": 0.5,
                },
            },
        ),
        ("apply_bandpass_filter", {"low_freq": 1, "high_freq": 40}),
        (
            "start_training",
            {
                "append": False,
                "interactive": True,
                "confirmed": True,
                "resource_preflight_confirmed": False,
                "resource_preflight_token": None,
            },
        ),
    ]


def test_real_configure_training_preserves_backend_output_directory(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "backend-selected-output"
    study = Study()
    service = get_application_service(study)
    configured = service.execute(
        ConfigureTrainingCommand(
            model_name="EEGNet",
            epoch=3,
            batch_size=4,
            learning_rate=0.001,
            output_dir=str(output_dir),
        )
    )
    assert configured.ok is True

    params = authorize_assistant_setting_change(
        "configure_training",
        {
            "epoch": 5,
            "batch_size": 8,
            "learning_rate": 0.002,
        },
        publication_generation=service.get_view_publication().generation,
    )
    result = execute_real_application_tool(
        study,
        "configure_training",
        params,
    )

    assert result.ok is True
    state = service.get_state()
    assert state.training.training_option is not None
    assert state.training.training_option["output_dir"] == str(output_dir)


def test_real_configure_training_does_not_authorize_raw_output_directory(
    tmp_path: Path,
) -> None:
    study = Study()
    output_dir = tmp_path / "model-invented-output"

    result = training_real.RealConfigureTrainingTool().execute(
        study,
        model_name="EEGNet",
        epoch=3,
        batch_size=4,
        learning_rate=0.001,
        output_dir=str(output_dir),
    )

    assert result.ok is False
    assert result.error_type == "input"
    assert (
        get_application_service(study).get_state().training.has_training_option is False
    )
