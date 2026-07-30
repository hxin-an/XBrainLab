from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path
from unittest.mock import patch

import pytest

from XBrainLab.llm.core.model_catalog import (
    MAX_TOTAL_MODEL_CACHE_GB,
    LocalModelSpec,
    allowed_local_model_ids,
    default_local_model_id,
    disallowed_cache_candidates,
    local_model_policy_error,
    local_model_spec,
    model_cache_complete,
    plan_model_download,
)

PRIMARY_MODEL_ID = "ibm-granite/granite-3.3-2b-instruct"
PRIMARY_MODEL_REVISION = (
    "707f574c62054322f6b5b04b6d075f0a8f05e0f0"  # pragma: allowlist secret
)
RETIRED_MODEL_IDS = (
    "microsoft/Phi-4-mini-instruct",
    "microsoft/Phi-3.5-mini-instruct",
)
VALID_TEST_WEIGHT_BYTES = 300_000_000


def _write_complete_project_cache(model_root: Path) -> None:
    model_root.mkdir(parents=True)
    (model_root / "config.json").write_text("{}", encoding="utf-8")
    (model_root / "tokenizer_config.json").write_text("{}", encoding="utf-8")
    with (model_root / "model.safetensors").open("wb") as stream:
        stream.truncate(VALID_TEST_WEIGHT_BYTES)


def _write_complete_hf_cache(
    cache_dir: Path,
    repo_id: str,
    *,
    revision: str = PRIMARY_MODEL_REVISION,
    create_blobs: bool = False,
    create_main_ref: bool = False,
    weight_bytes: int = VALID_TEST_WEIGHT_BYTES,
) -> Path:
    model_root = cache_dir / f"models--{repo_id.replace('/', '--')}"
    snapshot = model_root / "snapshots" / revision
    snapshot.mkdir(parents=True)
    if create_blobs:
        blobs = model_root / "blobs"
        blobs.mkdir()
        (blobs / "config-blob").write_text("{}", encoding="utf-8")
    if create_main_ref:
        refs = model_root / "refs"
        refs.mkdir()
        (refs / "main").write_text(revision, encoding="utf-8")
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    (snapshot / "tokenizer_config.json").write_text("{}", encoding="utf-8")
    with (snapshot / "model.safetensors").open("wb") as stream:
        stream.truncate(weight_bytes)
    return model_root


def test_catalog_excludes_chinese_model_providers():
    allowed = allowed_local_model_ids()
    assert default_local_model_id() == PRIMARY_MODEL_ID
    assert all("Qwen" not in model_id for model_id in allowed)
    assert local_model_policy_error("Qwen/Qwen2.5-7B-Instruct") is not None
    deepseek_error = local_model_policy_error("deepseek-ai/deepseek-llm-7b-chat")
    assert deepseek_error is not None
    assert "Chinese model providers" in deepseek_error


def test_catalog_pins_supported_models_to_immutable_revisions() -> None:
    primary = local_model_spec(PRIMARY_MODEL_ID)

    assert primary is not None
    assert primary.revision == PRIMARY_MODEL_REVISION
    assert len(primary.revision) == 40


def test_primary_granite_catalog_metadata_is_truthful() -> None:
    primary = local_model_spec(PRIMARY_MODEL_ID)

    assert allowed_local_model_ids()[0] == PRIMARY_MODEL_ID
    assert primary is not None
    assert primary.label == "Granite 3.3 2B Instruct (Primary)"
    assert primary.provider == "IBM"
    assert primary.role == "primary"
    assert primary.license == "Apache-2.0"
    assert primary.parameters == "2.5B (2B class)"
    assert primary.context_tokens == 128_000
    assert primary.runtime_context_tokens == 8_192
    assert primary.estimated_download_gb == pytest.approx(5.08)
    assert primary.estimated_download_gb < 10.0
    assert primary.quantization.startswith("BF16 safetensors")
    assert "trust_remote_code" not in {field.name for field in fields(LocalModelSpec)}
    assert primary.supports_system_role is True
    assert primary.preferred_cuda_dtype == "bfloat16"
    assert primary.source_url == (
        "https://huggingface.co/ibm-granite/granite-3.3-2b-instruct"
    )


def test_product_catalog_contains_exact_granite_only() -> None:
    assert allowed_local_model_ids() == [PRIMARY_MODEL_ID]

    for model_id in RETIRED_MODEL_IDS:
        assert local_model_spec(model_id) is None
        message = local_model_policy_error(model_id)
        assert message is not None
        assert "no longer available" in message
        assert PRIMARY_MODEL_ID in message
        assert "not changed" in message


def test_download_preflight_allows_primary_under_limits(tmp_path: Path):
    result = plan_model_download(
        PRIMARY_MODEL_ID,
        str(tmp_path / "models"),
    )

    assert result.ok is True
    assert result.estimated_download_bytes < result.max_single_model_bytes
    assert result.projected_cache_bytes < result.max_total_cache_bytes


def test_download_preflight_fails_closed_when_disk_capacity_is_unknown(
    tmp_path: Path,
) -> None:
    with patch(
        "XBrainLab.llm.core.model_catalog.available_disk_bytes",
        return_value=0,
    ):
        result = plan_model_download(
            PRIMARY_MODEL_ID,
            str(tmp_path / "models"),
        )

    assert result.ok is False
    assert "could not be verified" in result.message


def test_download_preflight_preserves_disk_reserve_after_download(
    tmp_path: Path,
) -> None:
    with patch(
        "XBrainLab.llm.core.model_catalog.available_disk_bytes",
        return_value=10_000_000_000,
    ):
        result = plan_model_download(
            PRIMARY_MODEL_ID,
            str(tmp_path / "models"),
        )

    assert result.ok is False
    assert "free after the download" in result.message


def test_download_preflight_allows_already_cached_model_without_increment(
    tmp_path: Path,
):
    cache_dir = tmp_path / "models"
    repo_id = PRIMARY_MODEL_ID
    cached_model = _write_complete_hf_cache(cache_dir, repo_id)

    result = plan_model_download(
        repo_id,
        str(cache_dir),
    )

    assert model_cache_complete(str(cache_dir), repo_id) is True
    assert cached_model.exists()
    assert result.ok is True
    assert result.estimated_download_bytes == 0
    assert result.projected_cache_bytes == result.current_cache_bytes
    assert "already cached" in result.message


def test_windows_style_snapshot_does_not_require_blobs_or_symlinks(
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "models"
    model_root = _write_complete_hf_cache(cache_dir, PRIMARY_MODEL_ID)

    assert not (model_root / "blobs").exists()
    assert model_cache_complete(str(cache_dir), PRIMARY_MODEL_ID) is True


def test_pinned_snapshot_is_discoverable_by_huggingface_local_cache_lookup(
    tmp_path: Path,
) -> None:
    from huggingface_hub import try_to_load_from_cache

    cache_dir = tmp_path / "models"
    model_root = _write_complete_hf_cache(cache_dir, PRIMARY_MODEL_ID)

    cached_config = try_to_load_from_cache(
        PRIMARY_MODEL_ID,
        "config.json",
        cache_dir=cache_dir,
        revision=PRIMARY_MODEL_REVISION,
    )

    assert cached_config == str(
        model_root / "snapshots" / PRIMARY_MODEL_REVISION / "config.json"
    )


def test_internal_hf_blob_symlinks_are_supported(tmp_path: Path) -> None:
    cache_dir = tmp_path / "models"
    model_root = cache_dir / f"models--{PRIMARY_MODEL_ID.replace('/', '--')}"
    snapshot = model_root / "snapshots" / PRIMARY_MODEL_REVISION
    blobs = model_root / "blobs"
    snapshot.mkdir(parents=True)
    blobs.mkdir()
    config_blob = blobs / "config"
    tokenizer_blob = blobs / "tokenizer"
    weight_blob = blobs / "weights"
    config_blob.write_text("{}", encoding="utf-8")
    tokenizer_blob.write_text("{}", encoding="utf-8")
    with weight_blob.open("wb") as stream:
        stream.truncate(VALID_TEST_WEIGHT_BYTES)
    try:
        (snapshot / "config.json").symlink_to(config_blob)
        (snapshot / "tokenizer_config.json").symlink_to(tokenizer_blob)
        (snapshot / "model.safetensors").symlink_to(weight_blob)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    assert model_cache_complete(str(cache_dir), PRIMARY_MODEL_ID) is True


def test_sharded_weights_require_every_indexed_artifact(tmp_path: Path) -> None:
    cache_dir = tmp_path / "models"
    snapshot = (
        cache_dir
        / f"models--{PRIMARY_MODEL_ID.replace('/', '--')}"
        / "snapshots"
        / PRIMARY_MODEL_REVISION
    )
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    (snapshot / "tokenizer_config.json").write_text("{}", encoding="utf-8")
    (snapshot / "model.safetensors.index.json").write_text(
        json.dumps(
            {
                "weight_map": {
                    "layer.0": "model-00001-of-00002.safetensors",
                    "layer.1": "model-00002-of-00002.safetensors",
                }
            }
        ),
        encoding="utf-8",
    )
    with (snapshot / "model-00001-of-00002.safetensors").open("wb") as stream:
        stream.truncate(150_000_000)

    assert model_cache_complete(str(cache_dir), PRIMARY_MODEL_ID) is False

    with (snapshot / "model-00002-of-00002.safetensors").open("wb") as stream:
        stream.truncate(150_000_000)

    assert model_cache_complete(str(cache_dir), PRIMARY_MODEL_ID) is True


def test_project_local_dir_layout_is_not_reported_as_runtime_cache(
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "models"
    _write_complete_project_cache(cache_dir / PRIMARY_MODEL_ID.replace("/", "_"))

    assert model_cache_complete(str(cache_dir), PRIMARY_MODEL_ID) is False


def test_tiny_weight_file_is_not_reported_as_complete(tmp_path: Path) -> None:
    cache_dir = tmp_path / "models"
    _write_complete_hf_cache(
        cache_dir,
        PRIMARY_MODEL_ID,
        create_blobs=True,
        create_main_ref=True,
        weight_bytes=1,
    )

    assert model_cache_complete(str(cache_dir), PRIMARY_MODEL_ID) is False


def test_corrupt_model_metadata_is_not_reported_as_complete(tmp_path: Path) -> None:
    cache_dir = tmp_path / "models"
    model_root = _write_complete_hf_cache(cache_dir, PRIMARY_MODEL_ID)
    snapshot = model_root / "snapshots" / PRIMARY_MODEL_REVISION
    (snapshot / "config.json").write_text("{not-json", encoding="utf-8")

    assert model_cache_complete(str(cache_dir), PRIMARY_MODEL_ID) is False


def test_weight_symlink_outside_cache_is_not_reported_as_complete(
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "models"
    model_root = _write_complete_hf_cache(
        cache_dir,
        PRIMARY_MODEL_ID,
        create_blobs=True,
        create_main_ref=True,
    )
    snapshot = model_root / "snapshots" / PRIMARY_MODEL_REVISION
    weight = snapshot / "model.safetensors"
    weight.unlink()
    outside_weight = tmp_path / "outside.safetensors"
    with outside_weight.open("wb") as stream:
        stream.truncate(VALID_TEST_WEIGHT_BYTES)
    try:
        weight.symlink_to(outside_weight)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    assert model_cache_complete(str(cache_dir), PRIMARY_MODEL_ID) is False


@pytest.mark.parametrize(
    "partial_layout",
    (
        "empty",
        "config-only",
        "lock",
        "missing-shard",
        "hf-no-ref",
        "hf-wrong-revision",
    ),
)
def test_partial_cache_never_bypasses_download_estimate(
    tmp_path: Path,
    partial_layout: str,
) -> None:
    repo_id = PRIMARY_MODEL_ID
    cache_dir = tmp_path / "models"
    project_root = cache_dir / repo_id.replace("/", "_")
    hf_root = cache_dir / f"models--{repo_id.replace('/', '--')}"

    if partial_layout == "empty":
        project_root.mkdir(parents=True)
    elif partial_layout == "config-only":
        project_root.mkdir(parents=True)
        (project_root / "config.json").write_text("{}", encoding="utf-8")
    elif partial_layout == "lock":
        _write_complete_project_cache(project_root)
        (project_root / "model.safetensors.lock").write_text(
            "active",
            encoding="utf-8",
        )
    elif partial_layout == "missing-shard":
        project_root.mkdir(parents=True)
        (project_root / "config.json").write_text("{}", encoding="utf-8")
        (project_root / "tokenizer_config.json").write_text("{}", encoding="utf-8")
        (project_root / "model.safetensors.index.json").write_text(
            json.dumps({"weight_map": {"layer": "missing-00001.safetensors"}}),
            encoding="utf-8",
        )
    else:
        revision = "partial-revision"
        snapshot = hf_root / "snapshots" / revision
        snapshot.mkdir(parents=True)
        (snapshot / "config.json").write_text("{}", encoding="utf-8")
        (snapshot / "tokenizer_config.json").write_text("{}", encoding="utf-8")
        with (snapshot / "model.safetensors").open("wb") as stream:
            stream.truncate(VALID_TEST_WEIGHT_BYTES)
        if partial_layout == "hf-no-ref":
            (hf_root / "blobs").mkdir()
            (hf_root / "blobs" / "weights").write_bytes(b"weights")
        else:
            (hf_root / "refs").mkdir()
            (hf_root / "refs" / "main").write_text(revision, encoding="utf-8")

    result = plan_model_download(repo_id, str(cache_dir))

    assert model_cache_complete(str(cache_dir), repo_id) is False
    assert result.estimated_download_bytes > 0
    assert result.projected_cache_bytes > result.current_cache_bytes
    assert "already cached" not in result.message


def test_large_partial_cache_cannot_bypass_total_limit(tmp_path: Path) -> None:
    repo_id = PRIMARY_MODEL_ID
    cache_dir = tmp_path / "models"
    partial = cache_dir / repo_id.replace("/", "_")
    partial.mkdir(parents=True)
    (partial / "config.json").write_text("{}", encoding="utf-8")
    with (partial / "model.safetensors.incomplete").open("wb") as stream:
        stream.truncate(15_000_000_000)

    result = plan_model_download(repo_id, str(cache_dir))

    assert result.estimated_download_bytes > 0
    assert result.ok is False
    assert result.projected_cache_bytes > int(MAX_TOTAL_MODEL_CACHE_GB * 1_000_000_000)


def test_download_preflight_blocks_total_cache_over_limit(tmp_path: Path):
    cache_dir = tmp_path / "models"
    blocked_cache = cache_dir / "models--Qwen--Qwen2.5-7B-Instruct"
    blocked_cache.mkdir(parents=True)
    # Simulate an existing 15GB blocked model cache without writing huge data.
    with open(blocked_cache / "weights.safetensors", "wb") as f:
        f.truncate(15_000_000_000)

    result = plan_model_download(
        PRIMARY_MODEL_ID,
        str(cache_dir),
    )

    assert result.ok is False
    assert result.projected_cache_bytes > int(MAX_TOTAL_MODEL_CACHE_GB * 1_000_000_000)
    assert str(blocked_cache) in result.cleanup_candidates
    assert disallowed_cache_candidates(str(cache_dir)) == [str(blocked_cache)]


def test_cache_scan_error_fails_closed_instead_of_assuming_zero(
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "models"
    cache_dir.mkdir()

    with patch(
        "XBrainLab.llm.core.model_catalog.os.walk",
        side_effect=PermissionError("cache subtree is unreadable"),
    ):
        result = plan_model_download(PRIMARY_MODEL_ID, str(cache_dir))

    assert result.ok is False
    assert result.current_cache_bytes == 0
    assert "could not be verified" in result.message
