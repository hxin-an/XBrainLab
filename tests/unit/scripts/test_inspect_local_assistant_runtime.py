from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from scripts.dev.inspect_local_assistant_runtime import (
    _extract_json_object,
    classify_runtime,
    render_markdown,
    run_prompt_smoke,
    run_structured_output_smoke,
)
from XBrainLab.llm.core.config import LLMConfig


def _create_hf_cache(cache_dir: Path, repo_id: str) -> None:
    model_root = cache_dir / f"models--{repo_id.replace('/', '--')}"
    snapshot_dir = model_root / "snapshots" / "test-revision"
    snapshot_dir.mkdir(parents=True)
    (model_root / "refs").mkdir(parents=True)
    (model_root / "refs" / "main").write_text("test-revision", encoding="utf-8")

    for filename in (
        "config.json",
        "tokenizer_config.json",
        "model.safetensors.index.json",
        "model-00001-of-00001.safetensors",
    ):
        (snapshot_dir / filename).write_text("{}", encoding="utf-8")


def test_classify_runtime_reports_cpu_fallback(tmp_path: Path):
    config = LLMConfig()
    config.inference_mode = "local"
    config.active_mode = "local"
    config.device = "cuda"
    config.cache_dir = str(tmp_path / "models")
    config.load_in_4bit = True
    _create_hf_cache(Path(config.cache_dir), config.model_name)

    with (
        patch(
            "XBrainLab.llm.core.config.importlib.util.find_spec",
            return_value=object(),
        ),
        patch.object(
            LLMConfig,
            "local_backend_cpu_fallback_reason",
            return_value="no kernel image",
        ),
    ):
        result = classify_runtime(config)

    assert result["classification"] == "cpu-fallback"
    assert result["has_local_cache"] is True
    assert result["effective_load_in_4bit"] is False
    assert result["gpu_fallback_reason"] == "no kernel image"


def test_classify_runtime_reports_missing_cache(tmp_path: Path):
    config = LLMConfig()
    config.inference_mode = "local"
    config.active_mode = "local"
    config.device = "cpu"
    config.cache_dir = str(tmp_path / "models")
    config.load_in_4bit = False

    with patch(
        "XBrainLab.llm.core.config.importlib.util.find_spec",
        return_value=object(),
    ):
        result = classify_runtime(config)

    assert result["classification"] == "missing-cache"
    assert result["has_local_cache"] is False


def test_render_markdown_includes_classification(tmp_path: Path):
    config = LLMConfig()
    config.inference_mode = "gemini"
    config.active_mode = "gemini"

    result = classify_runtime(config)
    rendered = render_markdown(result)

    assert "classification" in rendered
    assert "current backend mode" in rendered
    assert "inspected backend mode" in rendered


def test_prompt_smoke_skips_when_local_runtime_unavailable(tmp_path: Path):
    config = LLMConfig()
    config.inference_mode = "local"
    config.active_mode = "local"
    config.cache_dir = str(tmp_path / "models")

    result = run_prompt_smoke(config)

    assert result["status"] == "skipped"
    assert "Local runtime unavailable" in result["message"]


def test_structured_smoke_skips_when_local_runtime_unavailable(tmp_path: Path):
    config = LLMConfig()
    config.inference_mode = "local"
    config.active_mode = "local"
    config.cache_dir = str(tmp_path / "models")

    result = run_structured_output_smoke(config)

    assert result["status"] == "skipped"
    assert "Local runtime unavailable" in result["message"]


def test_extract_json_object_accepts_code_fence():
    parsed = _extract_json_object(
        '```json\n{"tool_name":"get_state","arguments":{}}\n```'
    )

    assert parsed == {"tool_name": "get_state", "arguments": {}}
