"""Local assistant model catalog and download policy.

This module is intentionally small and deterministic: product code should not
scatter model allow/block lists across the UI, downloader, and runtime checks.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

BYTES_PER_GB = 1_000_000_000
MAX_SINGLE_MODEL_DOWNLOAD_GB = 10.0
MAX_TOTAL_MODEL_CACHE_GB = 20.0
MIN_DISK_FREE_AFTER_DOWNLOAD_GB = 5.0
MIN_MODEL_WEIGHT_BYTES = 256_000_000
CACHE_SCAN_MAX_ENTRIES = 100_000
CACHE_SCAN_MAX_DEPTH = 64


class CacheScanCancellation(Protocol):
    """Minimal caller cancellation contract for bounded cache scans."""

    def is_set(self) -> bool: ...


PRIMARY_LOCAL_MODEL_ID = "ibm-granite/granite-3.3-2b-instruct"
PRIMARY_LOCAL_MODEL_REVISION = (
    "707f574c62054322f6b5b04b6d075f0a8f05e0f0"  # pragma: allowlist secret
)
RETIRED_LOCAL_MODEL_IDS = frozenset(
    {
        "microsoft/Phi-4-mini-instruct",
        "microsoft/Phi-3.5-mini-instruct",
    }
)

# Compatibility aliases remain exact Granite so old non-product callers cannot
# reintroduce a second product model through the former fallback API.
FALLBACK_LOCAL_MODEL_ID = PRIMARY_LOCAL_MODEL_ID
FALLBACK_LOCAL_MODEL_REVISION = PRIMARY_LOCAL_MODEL_REVISION

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
    revision: str
    label: str
    provider: str
    role: str
    license: str
    parameters: str
    context_tokens: int
    estimated_download_gb: float
    estimated_vram_gb: float
    quantization: str
    runtime_context_tokens: int = 8_192
    supports_system_role: bool = False
    preferred_cuda_dtype: str = "float16"
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


@dataclass(frozen=True)
class ModelCacheValidationResult:
    """Post-download validation for one immutable Hugging Face snapshot."""

    ok: bool
    model_id: str
    revision: str
    message: str
    snapshot_path: str | None
    model_cache_bytes: int
    total_cache_bytes: int
    available_disk_bytes: int


@dataclass(frozen=True)
class DownloadConsumptionResult:
    """Actual resource usage observed while a model download is active."""

    ok: bool
    public_message: str
    diagnostic_message: str
    model_cache_bytes: int
    total_cache_bytes: int
    available_disk_bytes: int


class CacheInspectionError(RuntimeError):
    """Raised when cache usage cannot be measured without guessing."""


LOCAL_MODEL_SPECS: tuple[LocalModelSpec, ...] = (
    LocalModelSpec(
        repo_id=PRIMARY_LOCAL_MODEL_ID,
        revision=PRIMARY_LOCAL_MODEL_REVISION,
        label="Granite 3.3 2B Instruct (Primary)",
        provider="IBM",
        role="primary",
        license="Apache-2.0",
        parameters="2.5B (2B class)",
        context_tokens=128_000,
        estimated_download_gb=5.08,
        estimated_vram_gb=6.0,
        quantization=(
            "BF16 safetensors; optional runtime 4-bit if bitsandbytes is installed"
        ),
        runtime_context_tokens=8_192,
        supports_system_role=True,
        preferred_cuda_dtype="bfloat16",
        source_url=("https://huggingface.co/ibm-granite/granite-3.3-2b-instruct"),
        notes=(
            "IBM Granite 3.3 instruction model with function-calling, multilingual, "
            "and 128K-context support; pinned BF16 weights remain under 10GB."
        ),
    ),
)

_SPECS_BY_ID = {spec.repo_id: spec for spec in LOCAL_MODEL_SPECS}


def allowed_local_model_ids() -> list[str]:
    """Return explicit supported choices with the product default first."""
    return [spec.repo_id for spec in LOCAL_MODEL_SPECS]


def legacy_local_model_ids() -> list[str]:
    """Return legacy product choices.

    Retired model IDs are recognized only to provide migration guidance and
    are not product choices.
    """
    return []


def default_local_model_id() -> str:
    """Return the product default local model ID."""
    return PRIMARY_LOCAL_MODEL_ID


def fallback_local_model_id() -> str:
    """Return exact Granite through the former fallback compatibility API."""
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
    if model_id in RETIRED_LOCAL_MODEL_IDS:
        return (
            f"Local model {model_id} is no longer available in XBrainLab. "
            f"Open Assistant Settings and select {PRIMARY_LOCAL_MODEL_ID}. "
            "The existing settings file was not changed."
        )
    if local_model_spec(model_id) is None:
        supported = ", ".join(allowed_local_model_ids())
        return (
            f"Local model {model_id} is not in the supported product catalog. "
            f"Supported models: {supported}."
        )
    return None


def safe_model_cache_name(repo_id: str) -> str:
    """Return the legacy local-dir name, retained for cleanup compatibility."""
    return repo_id.replace("/", "_")


def hf_model_cache_name(repo_id: str) -> str:
    """Return the Hugging Face cache root name for a repo ID."""
    return f"models--{repo_id.replace('/', '--')}"


def model_cache_candidates(cache_dir: str, repo_id: str) -> list[str]:
    """Return the runtime-supported Hugging Face cache root for a model."""
    return [os.path.join(cache_dir, hf_model_cache_name(repo_id))]


_REQUIRED_MODEL_METADATA = ("config.json", "tokenizer_config.json")
_WEIGHT_INDEX_NAMES = (
    "model.safetensors.index.json",
    "pytorch_model.bin.index.json",
)
_DIRECT_WEIGHT_NAMES = ("model.safetensors", "pytorch_model.bin")
_PARTIAL_SUFFIXES = (".incomplete", ".lock", ".partial", ".tmp")
_MAX_SMALL_MANIFEST_BYTES = 8 * 1024 * 1024


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _artifact_size(path: Path, *, cache_root: Path) -> int | None:
    """Return a file's size only when its resolved target stays in the cache."""
    try:
        resolved_root = cache_root.resolve(strict=True)
        resolved_path = path.resolve(strict=True)
        if not _path_is_within(resolved_path, resolved_root):
            return None
        if not resolved_path.is_file():
            return None
        size = resolved_path.stat().st_size
    except OSError:
        return None
    return size if size > 0 else None


def _tree_has_unsafe_symlink(root: Path, *, cache_root: Path) -> bool:
    try:
        resolved_cache = cache_root.resolve(strict=True)

        def _raise_walk_error(error: OSError) -> None:
            raise error

        for current_root, directories, files in os.walk(
            root,
            followlinks=False,
            onerror=_raise_walk_error,
        ):
            for name in (*directories, *files):
                candidate = Path(current_root) / name
                if not candidate.is_symlink():
                    continue
                target = candidate.resolve(strict=True)
                if not _path_is_within(target, resolved_cache):
                    return True
    except OSError:
        return True
    return False


def _contains_partial_markers(root: Path) -> bool:
    try:

        def _raise_walk_error(error: OSError) -> None:
            raise error

        for current_root, directories, files in os.walk(
            root,
            followlinks=False,
            onerror=_raise_walk_error,
        ):
            names = (*directories, *files)
            if any(name.lower().endswith(_PARTIAL_SUFFIXES) for name in names):
                return True
            # ``os.walk`` does not follow directory symlinks by default.
            if Path(current_root) == root and not names:
                return False
    except OSError:
        return True
    return False


def _safe_manifest_json(path: Path) -> dict[str, object] | None:
    try:
        size = path.stat().st_size
        if size <= 0 or size > _MAX_SMALL_MANIFEST_BYTES:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _safe_relative_artifact(root: Path, raw_name: object) -> Path | None:
    name = str(raw_name or "")
    if not name or os.path.isabs(name):
        return None
    candidate = root / name
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if ".." in Path(name).parts:
        return None
    return candidate


def _weight_artifacts_complete(root: Path, *, cache_root: Path) -> bool:
    for index_name in _WEIGHT_INDEX_NAMES:
        index_path = root / index_name
        if not index_path.exists():
            continue
        if _artifact_size(index_path, cache_root=cache_root) is None:
            return False
        manifest = _safe_manifest_json(index_path)
        if manifest is None:
            return False
        weight_map = manifest.get("weight_map")
        if not isinstance(weight_map, dict) or not weight_map:
            return False
        referenced = {
            _safe_relative_artifact(root, name) for name in weight_map.values()
        }
        if None in referenced:
            return False
        sizes = [
            _artifact_size(path, cache_root=cache_root)
            for path in referenced
            if path is not None
        ]
        return (
            all(size is not None for size in sizes)
            and sum(size or 0 for size in sizes) >= MIN_MODEL_WEIGHT_BYTES
        )

    try:
        weight_paths = [
            path for path in root.iterdir() if path.name.lower() in _DIRECT_WEIGHT_NAMES
        ]
    except OSError:
        return False
    if not weight_paths:
        return False
    sizes = [_artifact_size(path, cache_root=cache_root) for path in weight_paths]
    return (
        all(size is not None for size in sizes)
        and sum(size or 0 for size in sizes) >= MIN_MODEL_WEIGHT_BYTES
    )


def _model_artifacts_complete(root: Path, *, cache_root: Path) -> bool:
    try:
        resolved_cache = cache_root.resolve(strict=True)
        resolved_root = root.resolve(strict=True)
    except OSError:
        return False
    if (
        not root.is_dir()
        or not _path_is_within(resolved_root, resolved_cache)
        or _contains_partial_markers(root)
        or _tree_has_unsafe_symlink(root, cache_root=cache_root)
    ):
        return False
    if not all(
        _artifact_size(root / name, cache_root=cache_root) is not None
        for name in _REQUIRED_MODEL_METADATA
    ):
        return False
    if not all(
        _safe_manifest_json(root / name) is not None
        for name in _REQUIRED_MODEL_METADATA
    ):
        return False
    return _weight_artifacts_complete(root, cache_root=cache_root)


def model_snapshot_path(cache_dir: str, repo_id: str) -> Path | None:
    """Return the immutable snapshot path used by the local-only runtime."""
    spec = local_model_spec(repo_id)
    if spec is None:
        return None
    return Path(cache_dir) / hf_model_cache_name(repo_id) / "snapshots" / spec.revision


def model_cache_complete(cache_dir: str, repo_id: str) -> bool:
    """Return whether the pinned local-only Hugging Face snapshot is complete."""
    snapshot = model_snapshot_path(cache_dir, repo_id)
    if snapshot is None:
        return False
    return _model_artifacts_complete(snapshot, cache_root=Path(cache_dir))


def model_cache_exists(cache_dir: str, repo_id: str) -> bool:
    """Compatibility alias for complete, startup-usable cache truth."""
    return model_cache_complete(cache_dir, repo_id)


def _directory_size_bytes(
    path: Path,
    *,
    deadline: float | None = None,
    cancel_event: CacheScanCancellation | None = None,
    max_entries: int = CACHE_SCAN_MAX_ENTRIES,
    max_depth: int = CACHE_SCAN_MAX_DEPTH,
) -> int:
    """Return hardlink-aware size within explicit scan resource bounds."""
    if max_entries < 1 or max_depth < 0:
        raise CacheInspectionError("Cache scan limits must be positive.")

    def _check_budget() -> None:
        try:
            cancelled = cancel_event is not None and cancel_event.is_set()
        except Exception as exc:
            raise CacheInspectionError(
                "Cache scan cancellation state could not be verified."
            ) from exc
        if cancelled:
            raise CacheInspectionError("Cache scan was cancelled.")
        if deadline is not None and time.monotonic() >= deadline:
            raise CacheInspectionError("Cache scan exceeded its deadline.")

    def _raise_scan_limit(limit_name: str) -> None:
        raise CacheInspectionError(f"Cache scan exceeded its {limit_name} limit.")

    _check_budget()
    try:
        root_stat = path.lstat()
    except FileNotFoundError:
        return 0
    except OSError as exc:
        raise CacheInspectionError(
            f"Could not inspect cache path {path}: {exc}"
        ) from exc

    if stat.S_ISREG(root_stat.st_mode):
        return root_stat.st_size
    if stat.S_ISLNK(root_stat.st_mode):
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise CacheInspectionError(
                f"Could not resolve cache path {path}: {exc}"
            ) from exc
        return _directory_size_bytes(
            resolved,
            deadline=deadline,
            cancel_event=cancel_event,
            max_entries=max_entries,
            max_depth=max_depth,
        )
    if not stat.S_ISDIR(root_stat.st_mode):
        return 0

    total = 0
    entry_count = 0
    seen: set[tuple[int, int]] = set()
    pending: list[tuple[Path, int]] = [(path, 0)]
    try:
        while pending:
            _check_budget()
            directory, depth = pending.pop()
            child_directories: list[tuple[Path, int]] = []
            with os.scandir(directory) as entries:
                for entry in entries:
                    _check_budget()
                    entry_count += 1
                    if entry_count > max_entries:
                        _raise_scan_limit("entry")
                    entry_stat = entry.stat(follow_symlinks=False)
                    entry_path = Path(entry.path)
                    if stat.S_ISLNK(entry_stat.st_mode):
                        total += entry_stat.st_size
                        continue
                    if stat.S_ISDIR(entry_stat.st_mode):
                        if depth >= max_depth:
                            _raise_scan_limit("depth")
                        child_directories.append((entry_path, depth + 1))
                        continue
                    if not stat.S_ISREG(entry_stat.st_mode):
                        continue
                    inode_key = (entry_stat.st_dev, entry_stat.st_ino)
                    if entry_stat.st_ino and inode_key in seen:
                        continue
                    if entry_stat.st_ino:
                        seen.add(inode_key)
                    total += entry_stat.st_size
            pending.extend(reversed(child_directories))
    except CacheInspectionError:
        raise
    except OSError as exc:
        raise CacheInspectionError(
            f"Could not measure local model cache {path}: {exc}"
        ) from exc
    return total


def cache_usage_bytes(
    cache_dir: str,
    *,
    deadline: float | None = None,
    cancel_event: CacheScanCancellation | None = None,
    max_entries: int = CACHE_SCAN_MAX_ENTRIES,
    max_depth: int = CACHE_SCAN_MAX_DEPTH,
) -> int:
    """Return cache bytes while enforcing deadline, cancellation, and limits."""
    return _directory_size_bytes(
        Path(cache_dir),
        deadline=deadline,
        cancel_event=cancel_event,
        max_entries=max_entries,
        max_depth=max_depth,
    )


def disallowed_cache_candidates(cache_dir: str) -> list[str]:
    """Return existing cache paths that belong to blocked model providers."""
    root = Path(cache_dir)
    try:
        root.lstat()
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise CacheInspectionError(
            f"Could not inspect local model cache {root}: {exc}"
        ) from exc

    candidates: list[str] = []
    try:
        for child in root.iterdir():
            name = child.name
            normalized = (
                name.removeprefix("models--").replace("--", "/").replace("_", "/")
            )
            if is_disallowed_local_model(normalized):
                candidates.append(str(child))
    except OSError as exc:
        raise CacheInspectionError(
            f"Could not inspect local model cache {root}: {exc}"
        ) from exc
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


def inspect_model_download_consumption(
    repo_id: str,
    cache_dir: str,
    *,
    max_single_model_gb: float = MAX_SINGLE_MODEL_DOWNLOAD_GB,
    max_total_cache_gb: float = MAX_TOTAL_MODEL_CACHE_GB,
) -> DownloadConsumptionResult:
    """Measure active download consumption and fail closed on every limit."""
    max_single_bytes = _bytes_from_gb(max_single_model_gb)
    max_total_bytes = _bytes_from_gb(max_total_cache_gb)
    minimum_reserve = _bytes_from_gb(MIN_DISK_FREE_AFTER_DOWNLOAD_GB)
    model_bytes = 0
    total_bytes = 0
    free_bytes = available_disk_bytes(cache_dir)

    def _result(
        ok: bool,
        public_message: str = "",
        *,
        reason: str = "within_limits",
        diagnostic_detail: str = "",
    ) -> DownloadConsumptionResult:
        diagnostics = (
            f"{reason}: model_cache_bytes={model_bytes}; "
            f"total_cache_bytes={total_bytes}; "
            f"available_disk_bytes={free_bytes}; "
            f"max_single_model_bytes={max_single_bytes}; "
            f"max_total_cache_bytes={max_total_bytes}; "
            f"minimum_free_disk_bytes={minimum_reserve}"
        )
        if diagnostic_detail:
            diagnostics = f"{diagnostics}; detail={diagnostic_detail}"
        return DownloadConsumptionResult(
            ok=ok,
            public_message=public_message,
            diagnostic_message=diagnostics,
            model_cache_bytes=model_bytes,
            total_cache_bytes=total_bytes,
            available_disk_bytes=free_bytes,
        )

    try:
        model_bytes = sum(
            _directory_size_bytes(Path(path))
            for path in model_cache_candidates(cache_dir, repo_id)
        )
        total_bytes = cache_usage_bytes(cache_dir)
    except CacheInspectionError as exc:
        return _result(
            False,
            (
                "Model download stopped because cache usage could not be "
                "verified. Check cache permissions and try again."
            ),
            reason="cache_inspection_failed",
            diagnostic_detail=f"{type(exc).__name__}: {exc}",
        )

    if model_bytes > max_single_bytes:
        return _result(
            False,
            ("Model download stopped because the per-model cache limit was exceeded."),
            reason="single_model_limit_exceeded",
        )
    if total_bytes > max_total_bytes:
        return _result(
            False,
            "Model download stopped because the total cache limit was exceeded.",
            reason="total_cache_limit_exceeded",
        )
    if free_bytes <= 0:
        return _result(
            False,
            (
                "Model download stopped because free disk space could not be "
                "verified. Check the cache drive and try again."
            ),
            reason="free_disk_inspection_failed",
        )
    if free_bytes < minimum_reserve:
        return _result(
            False,
            (
                "Model download stopped because the required free disk reserve "
                "was not preserved."
            ),
            reason="free_disk_reserve_exceeded",
        )
    return _result(True)


def plan_model_download(
    repo_id: str,
    cache_dir: str,
    *,
    max_single_model_gb: float = MAX_SINGLE_MODEL_DOWNLOAD_GB,
    max_total_cache_gb: float = MAX_TOTAL_MODEL_CACHE_GB,
) -> DownloadPreflightResult:
    """Check product download limits before starting a model download."""
    policy_error = local_model_policy_error(repo_id)
    max_single_bytes = _bytes_from_gb(max_single_model_gb)
    max_total_bytes = _bytes_from_gb(max_total_cache_gb)
    free_bytes = available_disk_bytes(cache_dir)
    try:
        current_bytes = cache_usage_bytes(cache_dir)
        cleanup = tuple(disallowed_cache_candidates(cache_dir))
    except CacheInspectionError:
        return DownloadPreflightResult(
            ok=False,
            model_id=repo_id,
            message=(
                "Local model cache usage could not be verified. Check cache "
                "permissions and try again."
            ),
            cache_dir=cache_dir,
            estimated_download_bytes=0,
            current_cache_bytes=0,
            projected_cache_bytes=0,
            max_single_model_bytes=max_single_bytes,
            max_total_cache_bytes=max_total_bytes,
            available_disk_bytes=free_bytes,
        )

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
    try:
        target_cache_bytes = sum(
            _directory_size_bytes(Path(path))
            for path in model_cache_candidates(cache_dir, repo_id)
        )
    except CacheInspectionError:
        return DownloadPreflightResult(
            ok=False,
            model_id=repo_id,
            message=(
                f"The cache for {repo_id} could not be verified. Check cache "
                "permissions and try again."
            ),
            cache_dir=cache_dir,
            estimated_download_bytes=estimated_bytes,
            current_cache_bytes=current_bytes,
            projected_cache_bytes=current_bytes,
            max_single_model_bytes=max_single_bytes,
            max_total_cache_bytes=max_total_bytes,
            available_disk_bytes=free_bytes,
            cleanup_candidates=cleanup,
        )
    cache_complete = model_cache_complete(cache_dir, repo_id)

    if target_cache_bytes > max_single_bytes:
        return DownloadPreflightResult(
            ok=False,
            model_id=repo_id,
            message=(
                f"The cache for {repo_id} is larger than the "
                f"{max_single_model_gb:.2f} GB per-model limit. "
                "Remove it before installing the model again."
            ),
            cache_dir=cache_dir,
            estimated_download_bytes=0 if cache_complete else estimated_bytes,
            current_cache_bytes=current_bytes,
            projected_cache_bytes=(
                current_bytes if cache_complete else current_bytes + estimated_bytes
            ),
            max_single_model_bytes=max_single_bytes,
            max_total_cache_bytes=max_total_bytes,
            available_disk_bytes=free_bytes,
            cleanup_candidates=cleanup,
        )

    if current_bytes > max_total_bytes:
        return DownloadPreflightResult(
            ok=False,
            model_id=repo_id,
            message=(
                "The local model cache is already above the "
                f"{max_total_cache_gb:.2f} GB total limit. "
                "Remove unused model files before continuing."
            ),
            cache_dir=cache_dir,
            estimated_download_bytes=0 if cache_complete else estimated_bytes,
            current_cache_bytes=current_bytes,
            projected_cache_bytes=(
                current_bytes if cache_complete else current_bytes + estimated_bytes
            ),
            max_single_model_bytes=max_single_bytes,
            max_total_cache_bytes=max_total_bytes,
            available_disk_bytes=free_bytes,
            cleanup_candidates=cleanup,
        )

    if cache_complete:
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

    if free_bytes <= 0:
        return DownloadPreflightResult(
            ok=False,
            model_id=repo_id,
            message=(
                "Available disk space could not be verified. Check that the model "
                "cache drive is available and try again."
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

    minimum_free_after_download = _bytes_from_gb(MIN_DISK_FREE_AFTER_DOWNLOAD_GB)
    if estimated_bytes + minimum_free_after_download > free_bytes:
        return DownloadPreflightResult(
            ok=False,
            model_id=repo_id,
            message=(
                f"Estimated download for {repo_id} is "
                f"{spec.estimated_download_gb:.2f} GB, "
                f"but only {format_bytes(free_bytes)} is available on the cache disk. "
                f"Keep at least {MIN_DISK_FREE_AFTER_DOWNLOAD_GB:.2f} GB free after "
                "the download."
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


def validate_downloaded_model_cache(
    repo_id: str,
    cache_dir: str,
    downloaded_path: str,
    *,
    max_single_model_gb: float = MAX_SINGLE_MODEL_DOWNLOAD_GB,
    max_total_cache_gb: float = MAX_TOTAL_MODEL_CACHE_GB,
) -> ModelCacheValidationResult:
    """Verify immutable snapshot identity, artifacts, and actual resource limits."""
    spec = local_model_spec(repo_id)
    expected_snapshot = model_snapshot_path(cache_dir, repo_id)
    free_bytes = available_disk_bytes(cache_dir)
    revision = spec.revision if spec is not None else ""

    def _result(
        ok: bool,
        message: str,
        *,
        snapshot_path: str | None = None,
        model_cache_bytes: int = 0,
        total_cache_bytes: int = 0,
    ) -> ModelCacheValidationResult:
        return ModelCacheValidationResult(
            ok=ok,
            model_id=repo_id,
            revision=revision,
            message=message,
            snapshot_path=snapshot_path,
            model_cache_bytes=model_cache_bytes,
            total_cache_bytes=total_cache_bytes,
            available_disk_bytes=free_bytes,
        )

    policy_error = local_model_policy_error(repo_id)
    if policy_error is not None or spec is None or expected_snapshot is None:
        return _result(False, policy_error or f"Unsupported local model: {repo_id}.")

    cache_root = Path(cache_dir)
    returned_snapshot = Path(downloaded_path)
    try:
        resolved_cache = cache_root.resolve(strict=True)
        resolved_returned = returned_snapshot.resolve(strict=True)
    except OSError:
        return _result(
            False,
            "Downloaded model snapshot could not be found or resolved.",
        )
    resolved_expected = expected_snapshot.resolve(strict=False)

    if (
        not _path_is_within(resolved_expected, resolved_cache)
        or not _path_is_within(resolved_returned, resolved_cache)
        or resolved_returned != resolved_expected
    ):
        return _result(
            False,
            (
                "Downloaded model revision does not match the pinned local runtime "
                f"revision {spec.revision}."
            ),
        )

    if not model_cache_complete(cache_dir, repo_id):
        return _result(
            False,
            "Downloaded model snapshot is incomplete or contains unsafe artifacts.",
            snapshot_path=str(expected_snapshot),
        )

    model_root = Path(cache_dir) / hf_model_cache_name(repo_id)
    try:
        model_bytes = _directory_size_bytes(model_root)
        total_bytes = cache_usage_bytes(cache_dir)
    except CacheInspectionError:
        return _result(
            False,
            "Downloaded model cache size could not be verified.",
            snapshot_path=str(expected_snapshot),
        )

    max_single_bytes = _bytes_from_gb(max_single_model_gb)
    if model_bytes > max_single_bytes:
        return _result(
            False,
            (
                f"The downloaded cache for {repo_id} exceeds the "
                f"{max_single_model_gb:.2f} GB per-model limit."
            ),
            snapshot_path=str(expected_snapshot),
            model_cache_bytes=model_bytes,
            total_cache_bytes=total_bytes,
        )

    max_total_bytes = _bytes_from_gb(max_total_cache_gb)
    if total_bytes > max_total_bytes:
        return _result(
            False,
            (
                "The downloaded local model cache exceeds the "
                f"{max_total_cache_gb:.2f} GB total cache limit."
            ),
            snapshot_path=str(expected_snapshot),
            model_cache_bytes=model_bytes,
            total_cache_bytes=total_bytes,
        )

    minimum_reserve = _bytes_from_gb(MIN_DISK_FREE_AFTER_DOWNLOAD_GB)
    if free_bytes <= 0:
        return _result(
            False,
            "Free disk space could not be verified after model download.",
            snapshot_path=str(expected_snapshot),
            model_cache_bytes=model_bytes,
            total_cache_bytes=total_bytes,
        )
    if free_bytes < minimum_reserve:
        return _result(
            False,
            (
                "The model download did not preserve the required "
                f"{MIN_DISK_FREE_AFTER_DOWNLOAD_GB:.2f} GB free disk reserve."
            ),
            snapshot_path=str(expected_snapshot),
            model_cache_bytes=model_bytes,
            total_cache_bytes=total_bytes,
        )

    return _result(
        True,
        (
            f"Verified pinned model revision {spec.revision}; model cache "
            f"{format_bytes(model_bytes)}, total cache {format_bytes(total_bytes)}."
        ),
        snapshot_path=str(expected_snapshot),
        model_cache_bytes=model_bytes,
        total_cache_bytes=total_bytes,
    )
