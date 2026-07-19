from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from scripts.dev.inspect_local_assistant_runtime import (
    classify_runtime,
    render_markdown,
    run_prompt_smoke,
    run_structured_output_smoke,
)
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.model_catalog import (
    MIN_MODEL_WEIGHT_BYTES,
    local_model_spec,
)


def _create_hf_cache(cache_dir: Path, repo_id: str) -> None:
    spec = local_model_spec(repo_id)
    assert spec is not None
    model_root = cache_dir / f"models--{repo_id.replace('/', '--')}"
    snapshot_dir = model_root / "snapshots" / spec.revision
    blobs_dir = model_root / "blobs"
    snapshot_dir.mkdir(parents=True)
    blobs_dir.mkdir(parents=True)
    (model_root / "refs").mkdir(parents=True)
    (model_root / "refs" / "main").write_text(spec.revision, encoding="utf-8")
    (blobs_dir / "cached-artifact").write_text("cached", encoding="utf-8")

    for filename in ("config.json", "tokenizer_config.json"):
        (snapshot_dir / filename).write_text("{}", encoding="utf-8")
    (snapshot_dir / "model.safetensors.index.json").write_text(
        '{"weight_map":{"layer":"model-00001-of-00001.safetensors"}}',
        encoding="utf-8",
    )
    with (snapshot_dir / "model-00001-of-00001.safetensors").open("wb") as stream:
        stream.truncate(MIN_MODEL_WEIGHT_BYTES)


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


def test_prompt_smoke_always_closes_loaded_engine():
    config = LLMConfig()
    config.apply_runtime_selection("local", ui_active_mode="local")

    with (
        patch.object(LLMConfig, "local_backend_ready", return_value=True),
        patch("scripts.dev.inspect_local_assistant_runtime.LLMEngine") as engine_type,
    ):
        engine_type.return_value.generate_stream.return_value = iter(["READY"])

        result = run_prompt_smoke(config)

    assert result["status"] == "passed"
    engine_type.return_value.close.assert_called_once_with()


def test_structured_smoke_closes_engine_when_generation_fails():
    config = LLMConfig()
    config.apply_runtime_selection("local", ui_active_mode="local")

    with (
        patch.object(LLMConfig, "local_backend_ready", return_value=True),
        patch("scripts.dev.inspect_local_assistant_runtime.LLMEngine") as engine_type,
    ):
        engine_type.return_value.generate_stream.side_effect = RuntimeError("failed")

        result = run_structured_output_smoke(config)

    assert result["status"] == "failed"
    engine_type.return_value.close.assert_called_once_with()


def test_structured_smoke_accepts_only_the_product_tool_envelope():
    config = LLMConfig()
    config.apply_runtime_selection("local", ui_active_mode="local")

    with (
        patch.object(LLMConfig, "local_backend_ready", return_value=True),
        patch("scripts.dev.inspect_local_assistant_runtime.LLMEngine") as engine_type,
    ):
        engine_type.return_value.generate_stream.return_value = iter(
            ['{"tool_name":"query_state","parameters":{}}']
        )

        result = run_structured_output_smoke(config)

    assert result["status"] == "passed"
    engine_type.return_value.close.assert_called_once_with()


def test_structured_smoke_rejects_legacy_arguments_and_code_fences():
    config = LLMConfig()
    config.apply_runtime_selection("local", ui_active_mode="local")

    for response in (
        '{"tool_name":"get_state","arguments":{}}',
        '```json\n{"tool_name":"query_state","parameters":{}}\n```',
    ):
        with (
            patch.object(LLMConfig, "local_backend_ready", return_value=True),
            patch(
                "scripts.dev.inspect_local_assistant_runtime.LLMEngine"
            ) as engine_type,
        ):
            engine_type.return_value.generate_stream.return_value = iter([response])

            result = run_structured_output_smoke(config)

        assert result["status"] == "failed"
        assert result["failure_type"] == "output_format"
        engine_type.return_value.close.assert_called_once_with()
