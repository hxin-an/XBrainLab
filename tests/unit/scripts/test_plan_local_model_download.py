from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from scripts.dev.plan_local_model_download import build_plan, render_markdown
from XBrainLab.llm.core.config import LLMConfig


def test_build_plan_reports_primary_model(tmp_path: Path):
    config = LLMConfig()
    config.cache_dir = str(tmp_path / "models")
    config.model_name = "microsoft/Phi-4-mini-instruct"

    with patch.object(LLMConfig, "load_from_file", return_value=config):
        plan = build_plan()

    assert plan["ok"] is True
    assert plan["model_id"] == "microsoft/Phi-4-mini-instruct"
    assert plan["primary_model"] == "microsoft/Phi-4-mini-instruct"
    assert plan["fallback_model"] == "microsoft/Phi-3.5-mini-instruct"
    assert "Qwen" not in "\n".join(plan["allowed_models"])


def test_build_plan_blocks_policy_disallowed_model(tmp_path: Path):
    config = LLMConfig()
    config.cache_dir = str(tmp_path / "models")

    with patch.object(LLMConfig, "load_from_file", return_value=config):
        plan = build_plan("Qwen/Qwen2.5-7B-Instruct")

    assert plan["ok"] is False
    assert "Chinese model providers" in plan["message"]


def test_render_markdown_includes_cache_and_source(tmp_path: Path):
    config = LLMConfig()
    config.cache_dir = str(tmp_path / "models")

    with patch.object(LLMConfig, "load_from_file", return_value=config):
        plan = build_plan("microsoft/Phi-3.5-mini-instruct")

    rendered = render_markdown(plan)

    assert "Local Model Download Preflight" in rendered
    assert "cache directory" in rendered
    assert "huggingface.co/microsoft/Phi-3.5-mini-instruct" in rendered
