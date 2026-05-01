from __future__ import annotations

from pathlib import Path

from XBrainLab.llm.core.model_catalog import (
    MAX_TOTAL_MODEL_CACHE_GB,
    allowed_local_model_ids,
    default_local_model_id,
    disallowed_cache_candidates,
    local_model_policy_error,
    plan_model_download,
)


def test_catalog_excludes_chinese_model_providers():
    allowed = allowed_local_model_ids()
    assert default_local_model_id() == "microsoft/Phi-4-mini-instruct"
    assert all("Qwen" not in model_id for model_id in allowed)
    assert local_model_policy_error("Qwen/Qwen2.5-7B-Instruct") is not None
    assert "Chinese model providers" in local_model_policy_error(
        "deepseek-ai/deepseek-llm-7b-chat"
    )


def test_download_preflight_allows_primary_under_limits(tmp_path: Path):
    result = plan_model_download(
        "microsoft/Phi-4-mini-instruct",
        str(tmp_path / "models"),
    )

    assert result.ok is True
    assert result.estimated_download_bytes < result.max_single_model_bytes
    assert result.projected_cache_bytes < result.max_total_cache_bytes


def test_download_preflight_allows_already_cached_model_without_increment(
    tmp_path: Path,
):
    cache_dir = tmp_path / "models"
    cached_model = cache_dir / "models--microsoft--Phi-4-mini-instruct"
    cached_model.mkdir(parents=True)
    (cached_model / "config.json").write_text("{}", encoding="utf-8")

    result = plan_model_download(
        "microsoft/Phi-4-mini-instruct",
        str(cache_dir),
    )

    assert result.ok is True
    assert result.estimated_download_bytes == 0
    assert result.projected_cache_bytes == result.current_cache_bytes
    assert "already cached" in result.message


def test_download_preflight_blocks_total_cache_over_limit(tmp_path: Path):
    cache_dir = tmp_path / "models"
    blocked_cache = cache_dir / "models--Qwen--Qwen2.5-7B-Instruct"
    blocked_cache.mkdir(parents=True)
    # Simulate an existing 15GB blocked model cache without writing huge data.
    with open(blocked_cache / "weights.safetensors", "wb") as f:
        f.truncate(15_000_000_000)

    result = plan_model_download(
        "microsoft/Phi-4-mini-instruct",
        str(cache_dir),
    )

    assert result.ok is False
    assert result.projected_cache_bytes > int(MAX_TOTAL_MODEL_CACHE_GB * 1_000_000_000)
    assert str(blocked_cache) in result.cleanup_candidates
    assert disallowed_cache_candidates(str(cache_dir)) == [str(blocked_cache)]
