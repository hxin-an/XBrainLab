from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.dev.inspect_local_assistant_runtime import (
    classify_runtime,
    main,
    render_markdown,
    run_prompt_smoke,
    run_structured_output_smoke,
)
from scripts.dev.sensitive_path_redaction import contains_sensitive_path
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
    assert "primary local model" in rendered


def test_runtime_cli_outputs_redacted_cache_identity(
    tmp_path: Path,
    capsys,
) -> None:
    config = LLMConfig()
    config.cache_dir = str(tmp_path / "private-model-cache")

    with patch.object(LLMConfig, "load_from_file", return_value=config):
        exit_code = main(["--format", "json"])

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert exit_code == 0
    assert config.cache_dir not in output
    assert "cache_dir" not in payload
    assert payload["cache_identity"]["redacted"] is True
    assert payload["cache_identity"]["path_sha256"]


@pytest.mark.parametrize(
    "cache_alias",
    [
        "/mnt/d/XBrainLabCache/models",
        "D:/XBrainLabCache/models",
        "D:\\XBrainLabCache\\models",
        json.dumps("D:\\XBrainLabCache\\models")[1:-1],
        "\\\\wsl.localhost\\Ubuntu\\mnt\\d\\XBrainLabCache\\models",
        "\\\\wsl$\\Ubuntu\\mnt\\d\\XBrainLabCache\\models",
    ],
    ids=("wsl", "windows-slash", "windows", "json", "unc-localhost", "unc-dollar"),
)
def test_runtime_cli_redacts_cache_aliases_from_nested_diagnostics(
    cache_alias: str,
    capsys,
) -> None:
    canonical = "/mnt/d/XBrainLabCache/models"
    config = LLMConfig(cache_dir=canonical)
    classified = {
        "cache_dir": canonical,
        "cache_candidates": [],
        "disallowed_cache_candidates": [],
        "classification": "missing-cache",
        "message": f"Cache unavailable at {cache_alias}",
        "details": {"error": cache_alias},
    }

    with (
        patch.object(LLMConfig, "load_from_file", return_value=config),
        patch(
            "scripts.dev.inspect_local_assistant_runtime.classify_runtime",
            return_value=classified,
        ),
    ):
        exit_code = main(["--format", "json"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert (
        contains_sensitive_path(
            output,
            {canonical: "<redacted:model-cache>"},
        )
        is False
    )
    assert output.count("<redacted:model-cache>") >= 2


def test_runtime_markdown_does_not_expose_cache_path(tmp_path: Path) -> None:
    config = LLMConfig()
    config.cache_dir = str(tmp_path / "private-model-cache")

    rendered = render_markdown(classify_runtime(config))

    assert config.cache_dir not in rendered
    assert "cache identity" in rendered


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
            [
                '{"workflow_stage":"unavailable",'
                '"tool_name":"switch_panel",'
                '"parameters":{"panel_name":"dataset"}}'
            ]
        )

        result = run_structured_output_smoke(config)

    assert result["status"] == "passed"
    engine_type.return_value.close.assert_called_once_with()


@pytest.mark.parametrize(
    "response",
    [
        ('{"workflow_stage":"unavailable","tool_name":"query_state","parameters":{}}'),
        (
            '{"workflow_stage":"empty",'
            '"tool_name":"switch_panel",'
            '"parameters":{"panel_name":"dataset"}}'
        ),
        (
            '{"workflow_stage":"unavailable",'
            '"tool_name":"switch_panel",'
            '"parameters":{"panel_name":"dashboard"}}'
        ),
        (
            '{"workflow_stage":"unavailable",'
            '"tool_name":"switch_panel",'
            '"parameters":{"panel_name":"dataset","extra":true}}'
        ),
    ],
    ids=("retired-tool", "wrong-stage", "invalid-panel", "extra-parameter"),
)
def test_structured_smoke_rejects_non_target_tool_call(response: str):
    config = LLMConfig()
    config.apply_runtime_selection("local", ui_active_mode="local")

    with (
        patch.object(LLMConfig, "local_backend_ready", return_value=True),
        patch("scripts.dev.inspect_local_assistant_runtime.LLMEngine") as engine_type,
    ):
        engine_type.return_value.generate_stream.return_value = iter([response])

        result = run_structured_output_smoke(config)

    assert result["status"] == "failed"
    assert result["failure_type"] == "target_contract"
    engine_type.return_value.close.assert_called_once_with()


def test_structured_smoke_rejects_legacy_arguments_and_code_fences():
    config = LLMConfig()
    config.apply_runtime_selection("local", ui_active_mode="local")

    for response in (
        '{"tool_name":"get_state","arguments":{}}',
        (
            '```json\n{"workflow_stage":"unavailable",'
            '"tool_name":"switch_panel",'
            '"parameters":{"panel_name":"dataset"}}\n```'
        ),
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


def test_json_main_suppresses_product_info_logs(capsys):
    config = LLMConfig()
    runtime = {"classification": "gpu-ready"}
    logger = logging.getLogger("XBrainLab.LLM")
    handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(handler)
    original_level = logger.level
    logger.setLevel(logging.INFO)

    def _prompt_smoke(_config):
        logger.info("runtime detail that must not corrupt JSON")
        return {"status": "passed", "message": "ok", "response": "READY"}

    try:
        with (
            patch.object(LLMConfig, "load_from_file", return_value=config),
            patch(
                "scripts.dev.inspect_local_assistant_runtime.classify_runtime",
                return_value=runtime,
            ),
            patch(
                "scripts.dev.inspect_local_assistant_runtime.run_prompt_smoke",
                side_effect=_prompt_smoke,
            ),
        ):
            exit_code = main(["--format", "json", "--prompt-smoke", "--strict"])
    finally:
        logger.removeHandler(handler)
        logger.setLevel(original_level)

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["prompt_smoke"]["status"] == "passed"


def test_strict_main_fails_when_requested_smoke_fails(capsys):
    config = LLMConfig()

    with (
        patch.object(LLMConfig, "load_from_file", return_value=config),
        patch(
            "scripts.dev.inspect_local_assistant_runtime.classify_runtime",
            return_value={"classification": "gpu-ready"},
        ),
        patch(
            "scripts.dev.inspect_local_assistant_runtime.run_structured_output_smoke",
            return_value={"status": "failed", "message": "bad", "response": ""},
        ),
    ):
        exit_code = main(["--format", "json", "--structured-smoke", "--strict"])

    assert exit_code == 1
    assert (
        json.loads(capsys.readouterr().out)["structured_output_smoke"]["status"]
        == "failed"
    )
