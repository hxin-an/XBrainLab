"""Security-sensitive configuration for local retrieval augmentation."""

from __future__ import annotations

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

    # Changing the pinned embedding invalidates old vectors by construction.
    COLLECTION_NAME = f"gold_set_examples_{EMBEDDING_REVISION[:12]}"

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
        """Return the immutable offline-only SentenceTransformer arguments."""
        return {
            "model_name": cls.EMBEDDING_MODEL,
            "cache_folder": cls.get_embedding_cache_path(),
            "model_kwargs": {
                "revision": cls.EMBEDDING_REVISION,
                "local_files_only": True,
                "trust_remote_code": False,
            },
        }
