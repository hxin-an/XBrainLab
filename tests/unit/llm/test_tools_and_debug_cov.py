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
    "resample_data",
    "saliency",
    "save_interpretation_recipe",
    "scan_source",
    "select_channels",
    "set_model",
    "set_montage",
    "set_reference",
    "start_training",
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

        executor = ToolExecutor(study=MagicMock())
        result = executor.execute("nonexistent_tool", {})
        assert "Error:" in result or "Unknown" in result

    def test_execute_success(self):
        from XBrainLab.debug.tool_executor import ToolExecutor

        executor = ToolExecutor(study=MagicMock())
        with patch.dict(
            ToolExecutor.TOOL_MAP,
            {
                "test_tool": MagicMock(
                    return_value=MagicMock(execute=MagicMock(return_value="ok"))
                )
            },
        ):
            result = executor.execute("test_tool", {"param": "value"})
            assert result == "ok"

    def test_execute_exception(self):
        from XBrainLab.debug.tool_executor import ToolExecutor

        mock_cls = MagicMock()
        mock_cls.return_value.execute.side_effect = RuntimeError("boom")
        executor = ToolExecutor(study=MagicMock())
        with patch.dict(ToolExecutor.TOOL_MAP, {"bad": mock_cls}):
            result = executor.execute("bad", {})
            assert "Error" in result


# --- tool_debug_mode.py ---
class TestToolDebugMode:
    def test_load_valid_script(self, tmp_path):
        import json

        from XBrainLab.debug.tool_debug_mode import DebugToolCall, ToolDebugMode

        script = {"calls": [{"tool": "t1", "params": {"a": 1}}, {"tool": "t2"}]}
        p = tmp_path / "test_script.json"
        p.write_text(json.dumps(script))

        dbg = ToolDebugMode(str(p))
        assert len(dbg.calls) == 2
        assert not dbg.is_complete

        call1 = dbg.next_call()
        assert call1 == DebugToolCall(tool="t1", params={"a": 1})

        call2 = dbg.next_call()
        assert call2 == DebugToolCall(tool="t2", params={})

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
        eval_record.get_gradient.return_value = "g"
        assert v.get_saliency("Gradient", 0) == "g"

    def test_get_saliency_gradient_input(self):
        v = self._make_visualizer()
        eval_record = cast(Any, v.eval_record)
        eval_record.get_gradient_input.return_value = "gi"
        assert v.get_saliency("Gradient * Input", 0) == "gi"

    def test_get_saliency_smoothgrad(self):
        v = self._make_visualizer()
        eval_record = cast(Any, v.eval_record)
        eval_record.get_smoothgrad.return_value = "sg"
        assert v.get_saliency("SmoothGrad", 0) == "sg"

    def test_get_saliency_smoothgrad_sq(self):
        v = self._make_visualizer()
        eval_record = cast(Any, v.eval_record)
        eval_record.get_smoothgrad_sq.return_value = "sgs"
        assert v.get_saliency("SmoothGrad_Squared", 0) == "sgs"

    def test_get_saliency_vargrad(self):
        v = self._make_visualizer()
        eval_record = cast(Any, v.eval_record)
        eval_record.get_vargrad.return_value = "vg"
        assert v.get_saliency("VarGrad", 0) == "vg"

    def test_get_saliency_unknown(self):
        v = self._make_visualizer()
        with pytest.raises(NotImplementedError):
            v.get_saliency("Unknown", 0)

    def test_get_saliency_none(self):
        v = self._make_visualizer()
        with pytest.raises(ValueError):
            v.get_saliency(cast(str, None), 0)

    def test_get_plt_creates_figure(self):
        from matplotlib.figure import Figure

        v = self._make_visualizer()
        with pytest.raises(NotImplementedError):
            v.get_plt()
        assert isinstance(v.fig, Figure)
        import matplotlib.pyplot as plt

        plt.close("all")


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
