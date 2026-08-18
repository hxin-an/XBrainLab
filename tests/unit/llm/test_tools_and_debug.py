"""Coverage tests for llm/tools/__init__.py, backend_resolver.py, and debug modules."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

EXPECTED_AGENT_TOOL_NAMES = {
    "apply_bandpass_filter",
    "apply_notch_filter",
    "clear_training_history",
    "compute_saliency",
    "configure_dataset_split",
    "configure_training",
    "create_epochs",
    "import_eeg_data",
    "normalize_data",
    "reset_preprocessing",
    "resample_data",
    "select_channels",
    "select_model",
    "set_montage",
    "set_reference",
    "start_training",
    "stop_training",
    "switch_panel",
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


# --- tool_debug_mode.py ---
class TestToolDebugMode:
    def test_load_valid_script(self, tmp_path):
        import json

        from XBrainLab.debug.tool_debug_mode import DebugToolCall, ToolDebugMode

        script = {
            "schema_version": "xbrainlab.assistant_walkthrough.v1",
            "profile_id": "contract",
            "title": "Contract walkthrough",
            "calls": [
                {
                    "id": "open-training",
                    "tool": "switch_panel",
                    "params": {"panel_name": "training"},
                    "instruction": "Open Training",
                    "expected_outcomes": ["completed"],
                },
            ],
        }
        p = tmp_path / "test_script.json"
        p.write_text(json.dumps(script))

        dbg = ToolDebugMode(str(p))
        assert len(dbg.calls) == 1
        assert not dbg.is_complete

        call1 = dbg.begin_call()
        assert call1 == DebugToolCall(
            step_id="open-training",
            tool="switch_panel",
            params={"panel_name": "training"},
            instruction="Open Training",
            expected_outcomes=("completed",),
        )
        assert dbg.index == 0
        assert dbg.is_waiting
        assert dbg.begin_call() is None

        assert dbg.complete_pending("completed") is True
        assert dbg.index == 1
        assert dbg.is_complete

    def test_missing_file(self, tmp_path):
        import pytest

        from XBrainLab.debug.tool_debug_mode import ToolDebugMode

        with pytest.raises(ValueError, match="not found"):
            ToolDebugMode(str(tmp_path / "nonexistent.json"))

    def test_invalid_json(self, tmp_path):
        import pytest

        from XBrainLab.debug.tool_debug_mode import ToolDebugMode

        p = tmp_path / "bad.json"
        p.write_text("not json")
        with pytest.raises(ValueError, match="valid JSON"):
            ToolDebugMode(str(p))

    def test_terminal_mismatch_stops_profile_without_consuming(self, tmp_path):
        import json

        from XBrainLab.debug.tool_debug_mode import ToolDebugMode

        p = tmp_path / "mismatch.json"
        p.write_text(
            json.dumps(
                {
                    "schema_version": "xbrainlab.assistant_walkthrough.v1",
                    "profile_id": "mismatch",
                    "title": "Mismatch",
                    "calls": [
                        {
                            "id": "open",
                            "tool": "switch_panel",
                            "params": {"panel_name": "dataset"},
                            "instruction": "Open Dataset",
                            "expected_outcomes": ["completed"],
                        }
                    ],
                }
            )
        )
        dbg = ToolDebugMode(str(p))
        assert dbg.begin_call() is not None
        assert dbg.complete_pending("panel_navigation_failed") is False
        assert dbg.index == 0
        assert "panel_navigation_failed" in dbg.failure
        assert "relaunch" in dbg.failure.casefold()
        assert not dbg.can_dispatch
        assert dbg.begin_call() is None
        assert not dbg.is_complete


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
        assert len(state) == 4
        assert state[0] is not None
        assert state[1] is not None
        assert state[2] is not None
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
