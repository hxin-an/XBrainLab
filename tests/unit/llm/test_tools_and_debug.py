"""Coverage tests for llm/tools/__init__.py, backend_resolver.py, and debug modules."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

EXPECTED_AGENT_TOOL_NAMES = {
    "apply_bandpass_filter",
    "apply_interpretation",
    "apply_notch_filter",
    "apply_standard_preprocess",
    "attach_labels",
    "clear_dataset",
    "configure_training",
    "epoch_data",
    "evaluate",
    "generate_dataset",
    "get_dataset_info",
    "list_files",
    "load_data",
    "normalize_data",
    "preview_interpretation",
    "query_state",
    "reload_interpretation_recipe",
    "reset_preprocess",
    "resample_data",
    "saliency",
    "save_interpretation_recipe",
    "scan_source",
    "select_channels",
    "set_model",
    "set_montage",
    "set_reference",
    "start_training",
    "stop_training",
    "switch_panel",
    "validate_interpretation",
    "visualize",
}


# --- llm/tools/__init__.py ---
class TestGetAllTools:
    def test_mock_mode(self):
        from XBrainLab.llm.tools import get_all_tools

        tools = get_all_tools("mock")
        names = {tool.name for tool in tools}
        assert names == EXPECTED_AGENT_TOOL_NAMES
        assert len(tools) == len(EXPECTED_AGENT_TOOL_NAMES)

    def test_real_mode(self):
        from XBrainLab.llm.tools import get_all_tools

        tools = get_all_tools("real")
        names = {tool.name for tool in tools}
        assert names == EXPECTED_AGENT_TOOL_NAMES
        assert len(tools) == len(EXPECTED_AGENT_TOOL_NAMES)

    def test_unknown_mode_raises(self):
        from XBrainLab.llm.tools import get_all_tools

        with pytest.raises(ValueError, match="Unknown tool mode"):
            get_all_tools("bad")


# --- backend_resolver.py ---
class TestBackendResolver:
    def test_get_model_class(self):
        from XBrainLab.backend.model_base.EEGNet import EEGNet
        from XBrainLab.backend.model_base.SCCNet import SCCNet
        from XBrainLab.llm.tools.real.backend_resolver import (
            BackendRegistryCompat as ToolRegistry,
        )

        assert ToolRegistry.get_model_class("EEGNet") is EEGNet
        assert ToolRegistry.get_model_class("sccnet") is SCCNet
        assert ToolRegistry.get_model_class("unknown") is None

    def test_get_preprocessor_class(self):
        from XBrainLab.backend.preprocessor.filtering import Filtering
        from XBrainLab.llm.tools.real.backend_resolver import (
            BackendRegistryCompat as ToolRegistry,
        )

        assert ToolRegistry.get_preprocessor_class("bandpass") is Filtering
        assert ToolRegistry.get_preprocessor_class("unknown") is None

    def test_get_optimizer_class(self):
        import torch

        from XBrainLab.llm.tools.real.backend_resolver import (
            BackendRegistryCompat as ToolRegistry,
        )

        assert ToolRegistry.get_optimizer_class("adam") is torch.optim.Adam
        assert ToolRegistry.get_optimizer_class("sgd") is torch.optim.SGD
        assert ToolRegistry.get_optimizer_class("adamw") is torch.optim.AdamW
        # Fallback returns Adam
        assert ToolRegistry.get_optimizer_class("unknown") is torch.optim.Adam


# --- tool_executor.py ---
class TestToolExecutor:
    def test_execute_unknown_tool(self):
        from XBrainLab.debug.tool_executor import ToolExecutor
        from XBrainLab.llm.tools.application_surface import ToolCommandResult

        executor = ToolExecutor(study=MagicMock())
        result = executor.execute("nonexistent_tool", {})
        assert isinstance(result, ToolCommandResult)
        assert result.ok is False
        assert result.error_type == "input"
        assert result.tool_name == "unknown_debug_tool"
        assert result.message == "The requested debug tool is unavailable."

    def test_execute_success(self, tmp_path):
        from XBrainLab.debug.tool_executor import ToolExecutor
        from XBrainLab.llm.tools.application_surface import ToolCommandResult

        executor = ToolExecutor(study=MagicMock())
        result = executor.execute(
            "list_files",
            {"directory": str(tmp_path)},
            authorization_text=f"List files in `{tmp_path}`.",
        )

        assert isinstance(result, ToolCommandResult)
        assert result.ok is True
        assert result.raw_result == []

    def test_execute_exception(self, tmp_path):
        from XBrainLab.debug.tool_executor import ToolExecutor
        from XBrainLab.llm.tools.application_surface import ToolCommandResult

        executor = ToolExecutor(study=MagicMock())
        with patch(
            "XBrainLab.debug.tool_executor.RealListFilesTool.execute",
            side_effect=RuntimeError(
                "/home/alice/private/subject-17/events.tsv "
                "alice@example.test token=hf_super_secret"
            ),
        ):
            result = executor.execute(
                "list_files",
                {"directory": str(tmp_path)},
                authorization_text=f"List files in `{tmp_path}`.",
            )
            assert isinstance(result, ToolCommandResult)
            assert result.ok is False
            assert result.error_type == "runtime"
            assert result.message == (
                "The assistant tool could not complete the action. "
                "Refresh application state before retrying."
            )
            assert result.error_code == "unexpected_tool_failure"
            assert result.recovery_action == "refresh_application_state"
            assert result.raw_result is None
            assert result.diagnostics["incident_id"]
            serialized = repr(result.to_payload())
            assert "/home/alice/private" not in serialized
            assert "alice@example.test" not in serialized
            assert "hf_super_secret" not in serialized

    def test_partial_training_debug_call_fails_without_backend_mutation(self):
        from XBrainLab.backend.application import get_application_service
        from XBrainLab.backend.study import Study
        from XBrainLab.debug.tool_executor import ToolExecutor
        from XBrainLab.llm.tools.application_surface import ToolCommandResult

        study = Study()
        service = get_application_service(study)
        before = service.get_state().training

        result = ToolExecutor(study).execute(
            "configure_training",
            {"model_name": "EEGNet", "epoch": 10},
        )

        assert isinstance(result, ToolCommandResult)
        assert result.ok is False
        assert result.error_type == "input"
        assert service.get_state().training == before

    def test_complete_training_debug_call_accepts_learning_rate_one(self):
        from XBrainLab.backend.application import get_application_service
        from XBrainLab.backend.study import Study
        from XBrainLab.debug.tool_executor import ToolExecutor
        from XBrainLab.llm.tools.application_surface import ToolCommandResult

        study = Study()
        result = ToolExecutor(study).execute(
            "configure_training",
            {
                "model_name": "EEGNet",
                "epoch": 2,
                "batch_size": 4,
                "learning_rate": 1,
            },
        )

        assert isinstance(result, ToolCommandResult)
        assert result.ok is True
        training = get_application_service(study).get_state().training
        assert training.model_name == "EEGNet"
        assert training.training_option["epoch"] == 2
        assert training.training_option["batch_size"] == 4
        assert training.training_option["learning_rate"] == 1.0


# --- tool_debug_mode.py ---
class TestToolDebugMode:
    def test_load_valid_script(self, tmp_path):
        import json

        from XBrainLab.debug.tool_debug_mode import DebugToolCall, ToolDebugMode

        script = {
            "calls": [
                {
                    "tool": "t1",
                    "params": {"a": 1},
                    "confirmed": True,
                    "authorization_text": "Host selected the input path.",
                },
                {"tool": "t2"},
            ]
        }
        p = tmp_path / "test_script.json"
        p.write_text(json.dumps(script))

        dbg = ToolDebugMode(str(p))
        assert len(dbg.calls) == 2
        assert not dbg.is_complete

        call1 = dbg.next_call()
        assert call1 == DebugToolCall(
            tool="t1",
            params={"a": 1},
            confirmed=True,
            authorization_text="Host selected the input path.",
        )

        call2 = dbg.next_call()
        assert call2 == DebugToolCall(
            tool="t2",
            params={},
            confirmed=False,
            authorization_text="",
        )

        assert dbg.next_call() is None
        assert dbg.is_complete

    def test_missing_file(self, tmp_path):
        from XBrainLab.debug.tool_debug_mode import ToolDebugMode

        dbg = ToolDebugMode(str(tmp_path / "nonexistent.json"))
        assert len(dbg.calls) == 0
        assert dbg.is_complete

    def test_invalid_json(self, tmp_path):
        from XBrainLab.debug.tool_debug_mode import ToolDebugMode

        p = tmp_path / "bad.json"
        p.write_text("not json")
        dbg = ToolDebugMode(str(p))
        assert len(dbg.calls) == 0


# --- visualization/base.py ---
class TestVisualizer:
    """Tests for Visualizer ??constructed via normal __init__ (not __new__)."""

    @staticmethod
    def _make_visualizer(**overrides):
        from XBrainLab.backend.visualization.base import Visualizer

        defaults = {"eval_record": MagicMock(), "epoch_data": MagicMock()}
        defaults.update(overrides)
        return Visualizer(**defaults)

    def test_get_saliency_gradient(self):
        v = self._make_visualizer()
        eval_record = cast(Any, v.eval_record)
        eval_record.gradient = {0: "g"}
        assert v.get_saliency("Gradient", 0) == "g"

    def test_get_saliency_gradient_input(self):
        v = self._make_visualizer()
        eval_record = cast(Any, v.eval_record)
        eval_record.gradient_input = {0: "gi"}
        assert v.get_saliency("Gradient * Input", 0) == "gi"

    def test_get_saliency_smoothgrad(self):
        v = self._make_visualizer()
        eval_record = cast(Any, v.eval_record)
        eval_record.smoothgrad = {0: "sg"}
        assert v.get_saliency("SmoothGrad", 0) == "sg"

    def test_get_saliency_smoothgrad_sq(self):
        v = self._make_visualizer()
        eval_record = cast(Any, v.eval_record)
        eval_record.smoothgrad_sq = {0: "sgs"}
        assert v.get_saliency("SmoothGrad_Squared", 0) == "sgs"

    def test_get_saliency_vargrad(self):
        v = self._make_visualizer()
        eval_record = cast(Any, v.eval_record)
        eval_record.vargrad = {0: "vg"}
        assert v.get_saliency("VarGrad", 0) == "vg"

    def test_get_saliency_unknown(self):
        v = self._make_visualizer()
        with pytest.raises(NotImplementedError):
            v.get_saliency("Unknown", 0)

    def test_get_saliency_none(self):
        v = self._make_visualizer()
        with pytest.raises(ValueError):
            v.get_saliency(cast(str, None), 0)

    def test_get_plt_releases_figure_when_rendering_fails(self):
        v = self._make_visualizer()
        with pytest.raises(NotImplementedError):
            v.get_plt()
        assert v.fig is None


# --- seed.py ---
class TestSeed:
    def test_set_seed_with_value(self):
        from XBrainLab.backend.utils.seed import set_seed

        result = set_seed(42)
        assert result == 42

    def test_set_seed_auto(self):
        from XBrainLab.backend.utils.seed import set_seed

        result = set_seed(None)
        assert isinstance(result, int)

    def test_set_seed_deterministic(self):
        from XBrainLab.backend.utils.seed import set_seed

        result = set_seed(42, deterministic=True)
        assert result == 42

    def test_get_and_set_random_state(self):
        from XBrainLab.backend.utils.seed import get_random_state, set_random_state

        state = get_random_state()
        assert len(state) == 3
        set_random_state(state)


# --- logger.py ---
class TestLogger:
    def test_setup_logger_default(self, tmp_path):
        from XBrainLab.backend.utils.logger import setup_logger

        log_file = str(tmp_path / "test.log")
        lgr = setup_logger("test_logger_cov", log_file)
        assert lgr.name == "test_logger_cov"
        lgr.info("test message")
        # Second call returns same logger (early return)
        lgr2 = setup_logger("test_logger_cov", log_file)
        assert lgr is lgr2

    def test_safe_rotating_handler_permission_error(self, tmp_path):
        import logging

        from XBrainLab.backend.utils.logger import setup_logger

        log_file = str(tmp_path / "rotate.log")
        lgr = setup_logger("test_rotate_cov", log_file, level=logging.DEBUG)
        # Find the SafeRotatingFileHandler and trigger doRollover
        for h in lgr.handlers:
            if hasattr(h, "doRollover"):
                handler = cast(Any, h)
                # Simulate PermissionError during rollover
                with patch.object(
                    type(handler).__bases__[0],
                    "doRollover",
                    side_effect=PermissionError("locked"),
                ):
                    handler.stream = None
                    handler.doRollover()
                break
