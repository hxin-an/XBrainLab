"""Prepare isolated research vectors around the existing pinned embedding cache.

Links share files, not read-only ACLs. This helper never writes shared embeddings,
loads a model, changes environment variables, or certifies runtime readiness.
The runner passes the returned environment to its owned process and separately
requires successful initialization/retrieval; degraded RAG is not an on result.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

from XBrainLab.llm.rag.config import RAGConfig

_SCHEMA = "xbrainlab.assistant_pilot_rag_cache.v1"
_MAX_FILES = 128
_MAX_BYTES = 512 * 1024 * 1024


def _linked(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        return (
            os.name == "nt"
            and getattr(path.lstat(), "st_reparse_tag", None)
            == stat.IO_REPARSE_TAG_MOUNT_POINT
        )
    except FileNotFoundError:
        return False


def _identity(root: Path) -> tuple[str, list[dict]]:
    """Hash the bounded complete snapshot, including symlinked HF blob files."""
    if not RAGConfig.embedding_cache_ready(root):
        raise ValueError("Pinned embedding snapshot is incomplete or escapes its cache")
    if not RAGConfig.gold_set_integrity_ok():
        raise ValueError("Bundled RAG corpus identity mismatch")
    snapshot = RAGConfig.embedding_snapshot_path(root).resolve(strict=True)
    files, total = [], 0
    pending = [snapshot]
    seen_entries = 0
    while pending:
        directory = pending.pop()
        for path in sorted(directory.iterdir()):
            seen_entries += 1
            if seen_entries > _MAX_FILES:
                raise ValueError("Embedding snapshot entry limit exceeded")
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(root):
                raise ValueError("Embedding snapshot file escapes its cache")
            if path.is_dir():
                if _linked(path):
                    raise ValueError(
                        "Embedding snapshot directory links are unsupported"
                    )
                pending.append(path)
                continue
            if not resolved.is_file():
                raise ValueError("Embedding snapshot contains a non-regular file")
            size = resolved.stat().st_size
            total += size
            if size <= 0 or total > _MAX_BYTES:
                raise ValueError("Embedding snapshot size limit exceeded")
            digest = hashlib.sha256()
            read = 0
            with resolved.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    read += len(chunk)
                    if read > size:
                        raise ValueError("Embedding snapshot changed while hashing")
                    digest.update(chunk)
            if read != size:
                raise ValueError("Embedding snapshot changed while hashing")
            files.append(
                {
                    "path": path.relative_to(snapshot).as_posix(),
                    "bytes": size,
                    "sha256": digest.hexdigest(),
                }
            )
    files.sort(key=lambda item: item["path"])
    digest = hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    )
    return digest.hexdigest(), files


def _link_directory(source: Path, destination: Path) -> None:
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(source), str(destination))
    else:
        destination.symlink_to(source, target_is_directory=True)


def prepare_rag_cache(
    destination: Path,
    *,
    embedding_cache: Path,
    expected_embedding_sha256: str | None = None,
) -> dict:
    """Create one fresh run cache; preserve any partial result on failure.

    ``embedding_cache`` is the existing directory containing the pinned HF repo,
    not its parent RAG cache. No source snapshot or shared vectors are copied.
    An optional frozen digest rejects a different source before writing anything.
    """
    destination, source = Path(destination), Path(embedding_cache)
    if not destination.is_absolute() or not source.is_absolute():
        raise ValueError("RAG preparation requires absolute paths")
    source = source.resolve(strict=True)
    destination = destination.parent.resolve(strict=True) / destination.name
    if source.is_relative_to(destination) or destination.is_relative_to(source):
        raise ValueError("Run cache and shared embedding paths overlap")
    if destination.exists() or _linked(destination):
        raise FileExistsError(destination)
    identity, files = _identity(source)
    if expected_embedding_sha256 is not None and expected_embedding_sha256 != identity:
        raise ValueError("Embedding snapshot identity mismatch")
    destination.mkdir()
    _link_directory(source, destination / "models")
    (destination / "vectors").mkdir()
    evidence = {
        "schema": _SCHEMA,
        "cache_root": str(destination),
        "shared_embedding_cache": str(source),
        "embedding_model": RAGConfig.EMBEDDING_MODEL,
        "embedding_revision": RAGConfig.EMBEDDING_REVISION,
        "embedding_sha256": identity,
        "embedding_files": files,
        "corpus_sha256": RAGConfig.GOLD_SET_SHA256,
        "environment": {RAGConfig.CACHE_DIR_ENV: str(destination)},
        "runtime_ready": False,
    }
    verify_rag_cache(evidence)
    return evidence


def verify_rag_cache(evidence: dict) -> bool:
    """Fail closed on linkage/content drift; success means storage only, not RAG ready."""
    if (
        evidence.get("schema") != _SCHEMA
        or evidence.get("embedding_model") != RAGConfig.EMBEDDING_MODEL
        or evidence.get("embedding_revision") != RAGConfig.EMBEDDING_REVISION
        or evidence.get("corpus_sha256") != RAGConfig.GOLD_SET_SHA256
    ):
        raise ValueError("RAG cache evidence identity mismatch")
    root = Path(evidence["cache_root"])
    source = Path(evidence["shared_embedding_cache"]).resolve(strict=True)
    if not root.is_absolute() or _linked(root) or root.resolve(strict=True) != root:
        raise ValueError("Run cache root identity changed")
    models, vectors = root / "models", root / "vectors"
    if not _linked(models) or models.resolve(strict=True) != source:
        raise ValueError("Shared embedding link identity changed")
    if (
        _linked(vectors)
        or not vectors.is_dir()
        or vectors.resolve(strict=True) != vectors
    ):
        raise ValueError("Run vectors must remain an isolated physical directory")
    if evidence.get("environment") != {RAGConfig.CACHE_DIR_ENV: str(root)}:
        raise ValueError("Run RAG environment identity changed")
    identity, files = _identity(source)
    if identity != evidence.get("embedding_sha256") or files != evidence.get(
        "embedding_files"
    ):
        raise ValueError("Embedding snapshot identity changed")
    if not RAGConfig.embedding_cache_ready(models):
        raise ValueError("Linked embedding snapshot is not ready")
    return True
