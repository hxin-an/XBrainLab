"""Security-sensitive configuration for local retrieval augmentation."""

from __future__ import annotations

import hashlib
import json
import os
import platform
from collections.abc import Mapping
from pathlib import Path


class RAGConfig:
    """Pinned embedding identity and per-user local storage boundaries."""

    CACHE_DIR_ENV = "XBRAINLAB_RAG_CACHE_DIR"

    EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_REVISION = (
        "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"  # pragma: allowlist secret
    )
    EMBEDDING_LICENSE = "Apache-2.0"
    EMBEDDING_SOURCE_URL = (
        "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2"
    )
    EMBEDDING_ESTIMATED_DOWNLOAD_GB = 0.10

    GOLD_SET_SHA256 = "b123eefe00fe99c9a026f3ee60d1924e73eeef6f0d1bf143d34a733c9b17efc3"
    INDEX_SCHEMA_VERSION = 1
    VECTOR_SIZE = 384

    # Changing either the pinned embedding or bundled corpus invalidates old
    # vectors by construction.
    COLLECTION_NAME = (
        f"gold_set_examples_{EMBEDDING_REVISION[:12]}_{GOLD_SET_SHA256[:12]}"
    )

    SIMILARITY_THRESHOLD = 0.7
    TOP_K = 3
    MAX_EXAMPLE_CONTENT_CHARS = 768
    MAX_CONTEXT_CHARS = 4_096

    _REQUIRED_SNAPSHOT_FILES = (
        "config.json",
        "modules.json",
        "tokenizer_config.json",
        "1_Pooling/config.json",
    )
    _WEIGHT_FILES = ("model.safetensors", "pytorch_model.bin")

    @classmethod
    def get_cache_root(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        system_name: str | None = None,
        home: str | Path | None = None,
    ) -> Path:
        """Return the per-user RAG cache root without creating it."""
        env = os.environ if environ is None else environ
        user_home = Path.home() if home is None else Path(home).expanduser()
        explicit = str(env.get(cls.CACHE_DIR_ENV, "")).strip()
        if explicit:
            explicit_path = Path(explicit).expanduser()
            root = (
                explicit_path
                if explicit_path.is_absolute()
                else user_home / explicit_path
            )
            return root.resolve(strict=False)

        current_system = system_name or platform.system()
        if current_system == "Windows":
            local_app_data = str(env.get("LOCALAPPDATA", "")).strip()
            local_path = Path(local_app_data).expanduser()
            base = (
                local_path
                if local_app_data and local_path.is_absolute()
                else user_home / "AppData" / "Local"
            )
            return (base / "XBrainLab" / "cache" / "rag").resolve(strict=False)

        if current_system == "Darwin":
            return (user_home / "Library" / "Caches" / "XBrainLab" / "rag").resolve(
                strict=False
            )

        xdg_cache_home = str(env.get("XDG_CACHE_HOME", "")).strip()
        xdg_path = Path(xdg_cache_home).expanduser()
        base = (
            xdg_path
            if xdg_cache_home and xdg_path.is_absolute()
            else user_home / ".cache"
        )
        return (base / "xbrainlab" / "rag").resolve(strict=False)

    @classmethod
    def get_embedding_cache_path(cls) -> str:
        """Return the Hugging Face cache used only for the pinned embedder."""
        return str(cls.get_cache_root() / "models")

    @classmethod
    def get_storage_path(cls) -> str:
        """Return and create the per-user Qdrant vector storage path."""
        path = cls.get_cache_root() / "vectors"
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    @classmethod
    def get_index_manifest_path(cls) -> Path:
        """Return the local manifest that proves vector-index provenance."""
        return cls.get_cache_root() / "vectors" / "index-manifest.json"

    @staticmethod
    def get_gold_set_path() -> Path:
        """Return the bundled, reviewed tool-call example corpus."""
        return Path(__file__).resolve().parent / "data" / "gold_set.json"

    @classmethod
    def gold_set_integrity_ok(cls) -> bool:
        """Return whether the bundled corpus matches its reviewed digest."""
        try:
            digest = hashlib.sha256(cls.get_gold_set_path().read_bytes()).hexdigest()
        except OSError:
            return False
        return digest == cls.GOLD_SET_SHA256

    @classmethod
    def expected_index_manifest(
        cls,
        document_count: int,
        *,
        point_ids: list[str],
    ) -> dict[str, object]:
        """Build the exact identity expected for one local vector index."""
        point_ids_sha256 = hashlib.sha256(
            json.dumps(
                sorted(str(point_id) for point_id in point_ids),
                ensure_ascii=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return {
            "schema_version": cls.INDEX_SCHEMA_VERSION,
            "collection_name": cls.COLLECTION_NAME,
            "embedding_model": cls.EMBEDDING_MODEL,
            "embedding_revision": cls.EMBEDDING_REVISION,
            "corpus_sha256": cls.GOLD_SET_SHA256,
            "document_count": int(document_count),
            "point_ids_sha256": point_ids_sha256,
            "vector_size": cls.VECTOR_SIZE,
        }

    @classmethod
    def embedding_snapshot_path(
        cls,
        cache_dir: str | Path | None = None,
    ) -> Path:
        """Return the only immutable embedding snapshot accepted at runtime."""
        root = Path(cache_dir or cls.get_embedding_cache_path()).expanduser()
        repo_cache_name = f"models--{cls.EMBEDDING_MODEL.replace('/', '--')}"
        return (
            root.resolve(strict=False)
            / repo_cache_name
            / "snapshots"
            / cls.EMBEDDING_REVISION
        )

    @classmethod
    def embedding_cache_ready(
        cls,
        cache_dir: str | Path | None = None,
    ) -> bool:
        """Return true only for a complete pinned snapshot inside its cache."""
        root = Path(cache_dir or cls.get_embedding_cache_path()).expanduser()
        snapshot = cls.embedding_snapshot_path(root)
        try:
            resolved_root = root.resolve(strict=True)
            resolved_snapshot = snapshot.resolve(strict=True)
            resolved_snapshot.relative_to(resolved_root)
        except (FileNotFoundError, OSError, ValueError):
            return False

        required_paths = [
            snapshot / relative_name for relative_name in cls._REQUIRED_SNAPSHOT_FILES
        ]
        if not all(cls._safe_file(path, resolved_root) for path in required_paths):
            return False
        return any(
            cls._safe_file(snapshot / weight_name, resolved_root)
            for weight_name in cls._WEIGHT_FILES
        )

    @staticmethod
    def _safe_file(path: Path, resolved_root: Path) -> bool:
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(resolved_root)
        except (FileNotFoundError, OSError, ValueError):
            return False
        return resolved.is_file()

    @classmethod
    def embedding_constructor_kwargs(cls) -> dict[str, object]:
        """Return arguments that load only the verified local snapshot.

        The installed SentenceTransformer API does not accept
        ``local_files_only``. Network resolution is avoided by passing the
        contained, immutable snapshot directory rather than a repository ID.
        """
        cache_path = cls.get_embedding_cache_path()
        return {
            "model_name": str(cls.embedding_snapshot_path(cache_path)),
            "cache_folder": cache_path,
            "model_kwargs": {
                "trust_remote_code": False,
            },
        }
