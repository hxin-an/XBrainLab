"""Local assistant model catalog and download policy.

This module is intentionally small and deterministic: product code should not
scatter model allow/block lists across the UI, downloader, and runtime checks.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

BYTES_PER_GB = 1_000_000_000
MAX_SINGLE_MODEL_DOWNLOAD_GB = 10.0
MAX_TOTAL_MODEL_CACHE_GB = 20.0

PRIMARY_LOCAL_MODEL_ID = "microsoft/Phi-4-mini-instruct"
FALLBACK_LOCAL_MODEL_ID = "microsoft/Phi-3.5-mini-instruct"

DISALLOWED_LOCAL_MODEL_PREFIXES = (
    "Qwen/",
    "deepseek-ai/",
    "THUDM/",
    "zai-org/",
    "01-ai/",
    "internlm/",
    "baichuan-inc/",
    "moonshotai/",
    "MiniMaxAI/",
    "alibaba-pai/",
    "Alibaba-NLP/",
    "tencent/",
    "TencentARC/",
)


@dataclass(frozen=True)
class LocalModelSpec:
    """A supported local model entry."""

    repo_id: str
    label: str
    provider: str
    role: str
    license: str
    parameters: str
    context_tokens: int
    estimated_download_gb: float
    estimated_vram_gb: float
    quantization: str
    trust_remote_code: bool = False
    attn_implementation: str | None = None
    source_url: str = ""
    notes: str = ""


@dataclass(frozen=True)
class DownloadPreflightResult:
    """Result of checking whether a model download is allowed."""

    ok: bool
    model_id: str
    message: str
    cache_dir: str
    estimated_download_bytes: int
    current_cache_bytes: int
    projected_cache_bytes: int
    max_single_model_bytes: int
    max_total_cache_bytes: int
    available_disk_bytes: int
    cleanup_candidates: tuple[str, ...] = ()


LOCAL_MODEL_SPECS: tuple[LocalModelSpec, ...] = (
    LocalModelSpec(
        repo_id=PRIMARY_LOCAL_MODEL_ID,
        label="Phi-4 Mini Instruct (Primary)",
        provider="Microsoft",
        role="primary",
        license="MIT",
        parameters="3.8B",
        context_tokens=128_000,
        estimated_download_gb=7.69,
        estimated_vram_gb=9.0,
        quantization=(
            "BF16 safetensors; optional runtime 4-bit if bitsandbytes is installed"
        ),
        trust_remote_code=True,
        attn_implementation="eager",
        source_url="https://huggingface.co/microsoft/Phi-4-mini-instruct",
        notes=(
            "Non-Chinese model with documented tool-enabled prompt format, "
            "multilingual support including Chinese, and download size under 10GB."
        ),
    ),
    LocalModelSpec(
        repo_id=FALLBACK_LOCAL_MODEL_ID,
        label="Phi-3.5 Mini Instruct (Fallback)",
        provider="Microsoft",
        role="fallback",
        license="MIT",
        parameters="3.8B",
        context_tokens=128_000,
        estimated_download_gb=7.64,
        estimated_vram_gb=8.5,
        quantization=(
            "BF16 safetensors; optional runtime 4-bit if bitsandbytes is installed"
        ),
        trust_remote_code=True,
        attn_implementation="eager",
        source_url="https://huggingface.co/microsoft/Phi-3.5-mini-instruct",
        notes="Smaller stable fallback from the same non-Chinese provider family.",
    ),
)

_SPECS_BY_ID = {spec.repo_id: spec for spec in LOCAL_MODEL_SPECS}


def allowed_local_model_ids() -> list[str]:
    """Return supported model IDs in UI priority order."""
    return [spec.repo_id for spec in LOCAL_MODEL_SPECS]


def default_local_model_id() -> str:
    """Return the product default local model ID."""
    return PRIMARY_LOCAL_MODEL_ID


def fallback_local_model_id() -> str:
    """Return the product fallback local model ID."""
    return FALLBACK_LOCAL_MODEL_ID


def local_model_spec(repo_id: str | None) -> LocalModelSpec | None:
    """Return metadata for a supported local model."""
    return _SPECS_BY_ID.get(str(repo_id or ""))


def is_disallowed_local_model(repo_id: str | None) -> bool:
    """Return ``True`` when a model is blocked by product policy."""
    model_id = str(repo_id or "")
    return any(
        model_id.startswith(prefix) for prefix in DISALLOWED_LOCAL_MODEL_PREFIXES
    )


def local_model_policy_error(repo_id: str | None) -> str | None:
    """Return a user-facing reason when a model cannot be used."""
    model_id = str(repo_id or "").strip()
    if not model_id:
        return "No local model is configured."
    if is_disallowed_local_model(model_id):
        return (
            f"Local model {model_id} is blocked by policy. XBrainLab local "
            "runtime must not use Chinese model providers."
        )
    if local_model_spec(model_id) is None:
        supported = ", ".join(allowed_local_model_ids())
        return (
            f"Local model {model_id} is not in the supported product catalog. "
            f"Supported models: {supported}."
        )
    return None


def safe_model_cache_name(repo_id: str) -> str:
    """Return the local-dir cache name used by the downloader."""
    return repo_id.replace("/", "_")


def hf_model_cache_name(repo_id: str) -> str:
    """Return the Hugging Face cache root name for a repo ID."""
    return f"models--{repo_id.replace('/', '--')}"


def model_cache_candidates(cache_dir: str, repo_id: str) -> list[str]:
    """Return supported cache layouts for a model."""
    return [
        os.path.join(cache_dir, safe_model_cache_name(repo_id)),
        os.path.join(cache_dir, hf_model_cache_name(repo_id)),
    ]


def model_cache_exists(cache_dir: str, repo_id: str) -> bool:
    """Return whether a supported local cache layout already exists."""
    return any(
        Path(path).exists() for path in model_cache_candidates(cache_dir, repo_id)
    )


def _directory_size_bytes(path: Path) -> int:
    """Return recursive directory size, ignoring files that disappear mid-scan."""
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0

    total = 0
    seen: set[tuple[int, int]] = set()
    for root, _, files in os.walk(path):
        for filename in files:
            file_path = Path(root) / filename
            try:
                if file_path.is_symlink():
                    total += file_path.lstat().st_size
                    continue

                stat = file_path.stat()
                inode_key = (stat.st_dev, stat.st_ino)
                if inode_key in seen:
                    continue
                seen.add(inode_key)
                total += stat.st_size
            except OSError:
                continue
    return total


def cache_usage_bytes(cache_dir: str) -> int:
    """Return total bytes currently used by the local model cache directory."""
    return _directory_size_bytes(Path(cache_dir))


def disallowed_cache_candidates(cache_dir: str) -> list[str]:
    """Return existing cache paths that belong to blocked model providers."""
    root = Path(cache_dir)
    if not root.exists():
        return []

    candidates: list[str] = []
    for child in root.iterdir():
        name = child.name
        normalized = name.removeprefix("models--").replace("--", "/").replace("_", "/")
        if is_disallowed_local_model(normalized):
            candidates.append(str(child))
    return candidates


def _bytes_from_gb(value: float) -> int:
    return int(value * BYTES_PER_GB)


def format_bytes(num_bytes: int) -> str:
    """Return a compact human-readable byte count."""
    return f"{num_bytes / BYTES_PER_GB:.2f} GB"


def available_disk_bytes(path: str) -> int:
    """Return available bytes on the filesystem containing ``path``."""
    current = Path(path)
    while not current.exists() and current != current.parent:
        current = current.parent
    try:
        return shutil.disk_usage(current).free
    except OSError:
        return 0


def plan_model_download(
    repo_id: str,
    cache_dir: str,
    *,
    max_single_model_gb: float = MAX_SINGLE_MODEL_DOWNLOAD_GB,
    max_total_cache_gb: float = MAX_TOTAL_MODEL_CACHE_GB,
) -> DownloadPreflightResult:
    """Check product download limits before starting a model download."""
    policy_error = local_model_policy_error(repo_id)
    current_bytes = cache_usage_bytes(cache_dir)
    max_single_bytes = _bytes_from_gb(max_single_model_gb)
    max_total_bytes = _bytes_from_gb(max_total_cache_gb)
    free_bytes = available_disk_bytes(cache_dir)
    cleanup = tuple(disallowed_cache_candidates(cache_dir))

    if policy_error is not None:
        return DownloadPreflightResult(
            ok=False,
            model_id=repo_id,
            message=policy_error,
            cache_dir=cache_dir,
            estimated_download_bytes=0,
            current_cache_bytes=current_bytes,
            projected_cache_bytes=current_bytes,
            max_single_model_bytes=max_single_bytes,
            max_total_cache_bytes=max_total_bytes,
            available_disk_bytes=free_bytes,
            cleanup_candidates=cleanup,
        )

    spec = local_model_spec(repo_id)
    if spec is None:
        return DownloadPreflightResult(
            ok=False,
            model_id=repo_id,
            message=f"Local model {repo_id} is not in the supported product catalog.",
            cache_dir=cache_dir,
            estimated_download_bytes=0,
            current_cache_bytes=current_bytes,
            projected_cache_bytes=current_bytes,
            max_single_model_bytes=max_single_bytes,
            max_total_cache_bytes=max_total_bytes,
            available_disk_bytes=free_bytes,
            cleanup_candidates=cleanup,
        )
    estimated_bytes = _bytes_from_gb(spec.estimated_download_gb)
    if model_cache_exists(cache_dir, repo_id):
        return DownloadPreflightResult(
            ok=True,
            model_id=repo_id,
            message=(
                f"Model {repo_id} is already cached; no download is required. "
                f"Current cache usage is {format_bytes(current_bytes)}."
            ),
            cache_dir=cache_dir,
            estimated_download_bytes=0,
            current_cache_bytes=current_bytes,
            projected_cache_bytes=current_bytes,
            max_single_model_bytes=max_single_bytes,
            max_total_cache_bytes=max_total_bytes,
            available_disk_bytes=free_bytes,
            cleanup_candidates=cleanup,
        )

    if estimated_bytes > max_single_bytes:
        return DownloadPreflightResult(
            ok=False,
            model_id=repo_id,
            message=(
                f"Estimated download for {repo_id} is "
                f"{spec.estimated_download_gb:.2f} GB, "
                f"above the {max_single_model_gb:.2f} GB per-model limit."
            ),
            cache_dir=cache_dir,
            estimated_download_bytes=estimated_bytes,
            current_cache_bytes=current_bytes,
            projected_cache_bytes=current_bytes + estimated_bytes,
            max_single_model_bytes=max_single_bytes,
            max_total_cache_bytes=max_total_bytes,
            available_disk_bytes=free_bytes,
            cleanup_candidates=cleanup,
        )

    if free_bytes and estimated_bytes > free_bytes:
        return DownloadPreflightResult(
            ok=False,
            model_id=repo_id,
            message=(
                f"Estimated download for {repo_id} is "
                f"{spec.estimated_download_gb:.2f} GB, "
                f"but only {format_bytes(free_bytes)} is available on the cache disk."
            ),
            cache_dir=cache_dir,
            estimated_download_bytes=estimated_bytes,
            current_cache_bytes=current_bytes,
            projected_cache_bytes=current_bytes + estimated_bytes,
            max_single_model_bytes=max_single_bytes,
            max_total_cache_bytes=max_total_bytes,
            available_disk_bytes=free_bytes,
            cleanup_candidates=cleanup,
        )

    projected_bytes = current_bytes + estimated_bytes
    if projected_bytes > max_total_bytes:
        cleanup_hint = (
            " Remove blocked or unused model caches first."
            if cleanup
            else " Remove unused model caches first."
        )
        return DownloadPreflightResult(
            ok=False,
            model_id=repo_id,
            message=(
                f"Downloading {repo_id} would raise local model cache usage to "
                f"{format_bytes(projected_bytes)}, above the "
                f"{max_total_cache_gb:.2f} GB total cache limit.{cleanup_hint}"
            ),
            cache_dir=cache_dir,
            estimated_download_bytes=estimated_bytes,
            current_cache_bytes=current_bytes,
            projected_cache_bytes=projected_bytes,
            max_single_model_bytes=max_single_bytes,
            max_total_cache_bytes=max_total_bytes,
            available_disk_bytes=free_bytes,
            cleanup_candidates=cleanup,
        )

    return DownloadPreflightResult(
        ok=True,
        model_id=repo_id,
        message=(
            f"Download allowed for {repo_id}: estimated "
            f"{spec.estimated_download_gb:.2f} GB; "
            f"projected cache {format_bytes(projected_bytes)}."
        ),
        cache_dir=cache_dir,
        estimated_download_bytes=estimated_bytes,
        current_cache_bytes=current_bytes,
        projected_cache_bytes=projected_bytes,
        max_single_model_bytes=max_single_bytes,
        max_total_cache_bytes=max_total_bytes,
        available_disk_bytes=free_bytes,
        cleanup_candidates=cleanup,
    )
