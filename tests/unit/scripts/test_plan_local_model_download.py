from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import patch

from scripts.dev.plan_local_model_download import build_plan, render_markdown
from XBrainLab.llm.core.config import LLMConfig


def test_build_plan_reports_primary_model(tmp_path: Path):
    config = LLMConfig()
    config.cache_dir = str(tmp_path / "models")
    config.model_name = LLMConfig.default_local_model_id()

    with patch.object(LLMConfig, "load_from_file", return_value=config):
        plan = build_plan()

    assert plan["ok"] is True
    assert plan["model_id"] == "ibm-granite/granite-4.0-micro"
    assert plan["primary_model"] == "ibm-granite/granite-4.0-micro"
    assert plan["allowed_models"] == [
        "ibm-granite/granite-4.0-micro",
        "ibm-granite/granite-3.3-2b-instruct",
    ]
    assert "Qwen" not in "\n".join(cast(list[str], plan["allowed_models"]))


def test_build_plan_blocks_policy_disallowed_model(tmp_path: Path):
    config = LLMConfig()
    config.cache_dir = str(tmp_path / "models")

    with patch.object(LLMConfig, "load_from_file", return_value=config):
        plan = build_plan("Qwen/Qwen2.5-7B-Instruct")

    assert plan["ok"] is False
    assert "Chinese model providers" in cast(str, plan["message"])


def test_render_markdown_includes_cache_and_source(tmp_path: Path):
    config = LLMConfig()
    config.cache_dir = str(tmp_path / "models")

    with patch.object(LLMConfig, "load_from_file", return_value=config):
        plan = build_plan()

    rendered = render_markdown(plan)

    assert "Local Model Download Preflight" in rendered
    assert "cache directory" in rendered
    assert "automatic fallback: `disabled`" in rendered
    assert "huggingface.co/ibm-granite/granite-4.0-micro" in rendered
