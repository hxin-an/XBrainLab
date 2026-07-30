"""Consent- and quota-gated downloader for the pinned RAG embedder."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from XBrainLab.llm.core.model_catalog import (
    BYTES_PER_GB,
    MAX_SINGLE_MODEL_DOWNLOAD_GB,
    MAX_TOTAL_MODEL_CACHE_GB,
    MIN_DISK_FREE_AFTER_DOWNLOAD_GB,
    CacheInspectionError,
    available_disk_bytes,
    cache_usage_bytes,
    format_bytes,
)

from .config import RAGConfig

try:
    from huggingface_hub import snapshot_download
except ImportError:
    snapshot_download = None  # type: ignore[assignment]


@dataclass(frozen=True)
class RAGEmbeddingDownloadPlan:
    """Pre-network resource admission for the pinned embedding snapshot."""

    ok: bool
    message: str
    cache_dir: str
    estimated_download_bytes: int
    current_cache_bytes: int
    projected_cache_bytes: int
    max_single_model_bytes: int
    max_total_cache_bytes: int
    minimum_free_after_download_bytes: int
    available_disk_bytes: int


@dataclass(frozen=True)
class RAGEmbeddingDownloadResult:
    """Terminal result for one explicit embedding download request."""

    ok: bool
    message: str
    snapshot_path: str | None = None
    downloaded: bool = False


def plan_rag_embedding_download(
    cache_dir: str | Path | None = None,
) -> RAGEmbeddingDownloadPlan:
    """Apply the local-model cache limits before any embedding download."""
    root = Path(cache_dir or RAGConfig.get_embedding_cache_path()).expanduser()
    normalized_cache = str(root.resolve(strict=False))
    estimated = int(RAGConfig.EMBEDDING_ESTIMATED_DOWNLOAD_GB * BYTES_PER_GB)
    max_single = int(MAX_SINGLE_MODEL_DOWNLOAD_GB * BYTES_PER_GB)
    max_total = int(MAX_TOTAL_MODEL_CACHE_GB * BYTES_PER_GB)
    minimum_free = int(MIN_DISK_FREE_AFTER_DOWNLOAD_GB * BYTES_PER_GB)
    free = available_disk_bytes(normalized_cache)
    try:
        current = cache_usage_bytes(normalized_cache)
        target = cache_usage_bytes(
            str(RAGConfig.embedding_snapshot_path(normalized_cache).parent.parent)
        )
    except CacheInspectionError:
        return _plan(
            ok=False,
            message=(
                "RAG embedding cache usage could not be verified. Check cache "
                "permissions and try again."
            ),
            cache_dir=normalized_cache,
            estimated=estimated,
            current=0,
            projected=0,
            max_single=max_single,
            max_total=max_total,
            minimum_free=minimum_free,
            free=free,
        )

    ready = RAGConfig.embedding_cache_ready(normalized_cache)
    required_download = 0 if ready else estimated
    projected = current + required_download

    if target > max_single:
        return _plan(
            ok=False,
            message=(
                "The pinned RAG embedding cache is already above the "
                f"{MAX_SINGLE_MODEL_DOWNLOAD_GB:.2f} GB per-artifact limit."
            ),
            cache_dir=normalized_cache,
            estimated=required_download,
            current=current,
            projected=projected,
            max_single=max_single,
            max_total=max_total,
            minimum_free=minimum_free,
            free=free,
        )
    if current > max_total:
        return _plan(
            ok=False,
            message=(
                "The RAG embedding cache is already above the "
                f"{MAX_TOTAL_MODEL_CACHE_GB:.2f} GB total cache limit."
            ),
            cache_dir=normalized_cache,
            estimated=required_download,
            current=current,
            projected=projected,
            max_single=max_single,
            max_total=max_total,
            minimum_free=minimum_free,
            free=free,
        )
    if ready:
        return _plan(
            ok=True,
            message="The pinned RAG embedding is already cached.",
            cache_dir=normalized_cache,
            estimated=0,
            current=current,
            projected=current,
            max_single=max_single,
            max_total=max_total,
            minimum_free=minimum_free,
            free=free,
        )
    if free <= 0:
        return _plan(
            ok=False,
            message=(
                "Available disk space could not be verified. Check that the RAG "
                "cache drive is available and try again."
            ),
            cache_dir=normalized_cache,
            estimated=estimated,
            current=current,
            projected=projected,
            max_single=max_single,
            max_total=max_total,
            minimum_free=minimum_free,
            free=free,
        )
    if estimated > max_single:
        return _plan(
            ok=False,
            message="The RAG embedding exceeds the per-artifact cache limit.",
            cache_dir=normalized_cache,
            estimated=estimated,
            current=current,
            projected=projected,
            max_single=max_single,
            max_total=max_total,
            minimum_free=minimum_free,
            free=free,
        )
    if projected > max_total:
        return _plan(
            ok=False,
            message=(
                f"The RAG embedding would raise cache usage to "
                f"{format_bytes(projected)}, above the total cache limit."
            ),
            cache_dir=normalized_cache,
            estimated=estimated,
            current=current,
            projected=projected,
            max_single=max_single,
            max_total=max_total,
            minimum_free=minimum_free,
            free=free,
        )
    if estimated + minimum_free > free:
        return _plan(
            ok=False,
            message=(
                "The RAG embedding download would not preserve the required "
                f"{MIN_DISK_FREE_AFTER_DOWNLOAD_GB:.2f} GB free-disk reserve."
            ),
            cache_dir=normalized_cache,
            estimated=estimated,
            current=current,
            projected=projected,
            max_single=max_single,
            max_total=max_total,
            minimum_free=minimum_free,
            free=free,
        )
    return _plan(
        ok=True,
        message=(
            "RAG embedding download allowed after explicit consent: estimated "
            f"{format_bytes(estimated)}."
        ),
        cache_dir=normalized_cache,
        estimated=estimated,
        current=current,
        projected=projected,
        max_single=max_single,
        max_total=max_total,
        minimum_free=minimum_free,
        free=free,
    )


def download_rag_embedding(
    *,
    user_consent: bool,
    cache_dir: str | Path | None = None,
) -> RAGEmbeddingDownloadResult:
    """Download the exact embedding only after explicit user admission."""
    plan = plan_rag_embedding_download(cache_dir)
    if not plan.ok:
        return RAGEmbeddingDownloadResult(False, plan.message)
    if plan.estimated_download_bytes == 0:
        return RAGEmbeddingDownloadResult(
            True,
            "The pinned RAG embedding is already cached.",
            snapshot_path=str(RAGConfig.embedding_snapshot_path(plan.cache_dir)),
        )
    if not user_consent:
        return RAGEmbeddingDownloadResult(
            False,
            "Explicit user consent is required before downloading the RAG embedding.",
        )
    if snapshot_download is None:
        return RAGEmbeddingDownloadResult(
            False,
            "The Hugging Face download dependency is unavailable.",
        )

    Path(plan.cache_dir).mkdir(parents=True, exist_ok=True)
    try:
        downloaded_path = snapshot_download(
            repo_id=RAGConfig.EMBEDDING_MODEL,
            revision=RAGConfig.EMBEDDING_REVISION,
            cache_dir=plan.cache_dir,
            resume_download=True,
        )
    except Exception as exc:
        return RAGEmbeddingDownloadResult(
            False,
            f"RAG embedding download failed: {type(exc).__name__}.",
        )

    expected = RAGConfig.embedding_snapshot_path(plan.cache_dir)
    try:
        returned = Path(downloaded_path).resolve(strict=True)
        expected_resolved = expected.resolve(strict=True)
    except (FileNotFoundError, OSError):
        return RAGEmbeddingDownloadResult(
            False,
            "The downloaded RAG embedding snapshot could not be verified.",
        )
    if returned != expected_resolved or not RAGConfig.embedding_cache_ready(
        plan.cache_dir
    ):
        return RAGEmbeddingDownloadResult(
            False,
            "The downloaded RAG embedding did not match the pinned snapshot.",
        )

    try:
        total_bytes = cache_usage_bytes(plan.cache_dir)
        embedding_bytes = cache_usage_bytes(
            str(expected.parent.parent),
        )
    except CacheInspectionError:
        return RAGEmbeddingDownloadResult(
            False,
            "The downloaded RAG embedding cache size could not be verified.",
        )
    if (
        embedding_bytes > plan.max_single_model_bytes
        or total_bytes > plan.max_total_cache_bytes
    ):
        return RAGEmbeddingDownloadResult(
            False,
            "The downloaded RAG embedding exceeded the configured cache quota.",
        )
    if available_disk_bytes(plan.cache_dir) < plan.minimum_free_after_download_bytes:
        return RAGEmbeddingDownloadResult(
            False,
            "The downloaded RAG embedding did not preserve the free-disk reserve.",
        )

    return RAGEmbeddingDownloadResult(
        True,
        "RAG embedding downloaded and verified.",
        snapshot_path=str(expected),
        downloaded=True,
    )


def _plan(
    *,
    ok: bool,
    message: str,
    cache_dir: str,
    estimated: int,
    current: int,
    projected: int,
    max_single: int,
    max_total: int,
    minimum_free: int,
    free: int,
) -> RAGEmbeddingDownloadPlan:
    return RAGEmbeddingDownloadPlan(
        ok=ok,
        message=message,
        cache_dir=cache_dir,
        estimated_download_bytes=estimated,
        current_cache_bytes=current,
        projected_cache_bytes=projected,
        max_single_model_bytes=max_single,
        max_total_cache_bytes=max_total,
        minimum_free_after_download_bytes=minimum_free,
        available_disk_bytes=free,
    )
