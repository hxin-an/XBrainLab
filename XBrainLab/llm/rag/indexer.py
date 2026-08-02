"""RAG indexer for embedding and storing gold-set examples.

Loads gold-set JSON files, converts them into LangChain ``Document``
objects, and indexes their embeddings into a Qdrant vector store.
"""

import hashlib
import json
import logging
import os
import uuid
from collections.abc import Mapping
from contextlib import suppress
from typing import Any, Protocol

from .config import RAGConfig
from .example_policy import is_primary_workflow_example

try:
    from langchain.docstore.document import Document as _Document
    from langchain_community.embeddings import (
        HuggingFaceEmbeddings as _HuggingFaceEmbeddings,
    )
    from langchain_community.vectorstores import Qdrant as _Qdrant
    from qdrant_client import QdrantClient as _QdrantClient
    from qdrant_client.http import models as _rest
except ImportError:
    _Document = None
    _HuggingFaceEmbeddings = None
    _Qdrant = None
    _QdrantClient = None
    _rest = None

# Keep these runtime names patchable for dependency-isolation tests while
# preventing optional-import unions from leaking into the typed API.
Document: Any = _Document
HuggingFaceEmbeddings: Any = _HuggingFaceEmbeddings
Qdrant: Any = _Qdrant
QdrantClient: Any = _QdrantClient
rest: Any = _rest

logger = logging.getLogger(__name__)


class _DocumentLike(Protocol):
    page_content: str
    metadata: Mapping[str, object]


class RAGIndexer:
    """Handles indexing of gold-set examples into a Qdrant collection.

    Attributes:
        embeddings: The HuggingFace sentence-transformer embedding model.
        storage_path: Absolute path to the Qdrant on-disk storage.
        client: The ``QdrantClient`` instance.

    """

    def __init__(self, client=None, embeddings=None):
        """Initializes the RAGIndexer with embedding model and Qdrant client.

        Args:
            client: Optional existing ``QdrantClient``. If ``None``, a new
                one is created from ``RAGConfig``.
            embeddings: Optional existing ``HuggingFaceEmbeddings``. If
                ``None``, a new one is created from ``RAGConfig``.

        """
        if (embeddings is None and HuggingFaceEmbeddings is None) or (
            client is None and QdrantClient is None
        ):
            raise ImportError(
                "RAG dependencies not installed. "
                "Install with: pip install langchain-community qdrant-client"
            )
        self._owns_client = client is None
        if embeddings is None:
            if not RAGConfig.embedding_cache_ready():
                raise RuntimeError(
                    "Pinned RAG embedding cache is unavailable; RAG remains disabled."
                )
            self.embeddings = HuggingFaceEmbeddings(
                **RAGConfig.embedding_constructor_kwargs(),
            )
        else:
            self.embeddings = embeddings
        self.storage_path = RAGConfig.get_storage_path()

        # Initialize Client
        self.client = client or QdrantClient(path=self.storage_path)
        logger.info("Initialized Qdrant at %s", self.storage_path)

    def load_gold_set(self, json_path: str) -> list[_DocumentLike]:
        """Parses a gold-set JSON file into LangChain Documents.

        Each entry in the JSON array is expected to have an ``input``
        field (used as searchable content) and optional ``id``,
        ``category``, and ``expected_tool_calls`` fields (stored as
        metadata).

        Args:
            json_path: Path to the gold-set JSON file.

        Returns:
            A list of ``Document`` objects ready for indexing.

        Raises:
            Exception: If the JSON file cannot be read or parsed.

        """
        try:
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error("Failed to load gold set: %s", e)
            raise

        docs = []
        for item in data:
            # Content is what we search against (Subject's input)
            content = item.get("input", "")

            # Metadata contains the answer (Tool Calls)
            metadata = {
                "id": item.get("id"),
                "category": item.get("category"),
                "tool_calls": json.dumps(item.get("expected_tool_calls")),
            }

            if content and is_primary_workflow_example(metadata):
                docs.append(Document(page_content=content, metadata=metadata))

        logger.info("Loaded %s documents from %s", len(docs), json_path)
        return docs

    def index_data(self, docs: list[_DocumentLike]) -> bool:
        """Ensure the exact reviewed corpus is indexed once.

        A collection is reused only when its local manifest, persisted Qdrant
        metadata, exact point IDs, and payload digests match the pinned
        embedding/corpus identity. Stale or partial derived indexes are rebuilt
        with deterministic point identifiers.

        Args:
            docs: List of ``Document`` objects to embed and store.

        Raises:
            Exception: If indexing or post-write verification fails.

        """
        if not docs:
            logger.warning("No documents to index.")
            return False

        created_collection = False
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == RAGConfig.COLLECTION_NAME for c in collections)
            document_ids = self.document_ids(docs)
            expected_payload_digests = self._expected_payload_digests(docs)
            self._require_unique_document_identities(
                document_count=len(docs),
                payload_digests=expected_payload_digests,
            )
            expected_manifest = RAGConfig.expected_index_manifest(
                len(docs),
                point_ids=document_ids,
            )

            if exists and self._index_is_current(
                expected_manifest,
                expected_ids=document_ids,
                expected_payload_digests=expected_payload_digests,
            ):
                logger.info(
                    "Reusing verified RAG collection: %s",
                    RAGConfig.COLLECTION_NAME,
                )
                return False

            self._remove_manifest()
            if exists:
                logger.info(
                    "Replacing stale RAG collection: %s",
                    RAGConfig.COLLECTION_NAME,
                )
                self.client.delete_collection(collection_name=RAGConfig.COLLECTION_NAME)

            self.client.create_collection(
                collection_name=RAGConfig.COLLECTION_NAME,
                vectors_config=rest.VectorParams(
                    size=RAGConfig.VECTOR_SIZE,
                    distance=rest.Distance.COSINE,
                ),
                metadata=expected_manifest,
            )
            created_collection = True

            qdrant = Qdrant(
                client=self.client,
                collection_name=RAGConfig.COLLECTION_NAME,
                embeddings=self.embeddings,
            )
            qdrant.add_documents(docs, ids=document_ids)

            self._verify_indexed_identity(
                expected_manifest,
                expected_ids=document_ids,
                expected_payload_digests=expected_payload_digests,
            )
            self._write_manifest(expected_manifest)

        except Exception as e:
            self._remove_manifest()
            if created_collection:
                with suppress(Exception):
                    self.client.delete_collection(
                        collection_name=RAGConfig.COLLECTION_NAME
                    )
            logger.error("Indexing failed: %s", e)
            raise
        else:
            logger.info(
                "Successfully indexed %d documents to %s",
                len(docs),
                RAGConfig.COLLECTION_NAME,
            )
            return True

    def _verify_indexed_identity(
        self,
        expected_manifest: dict[str, object],
        *,
        expected_ids: list[str],
        expected_payload_digests: dict[str, str],
    ) -> None:
        collection = self.client.get_collection(RAGConfig.COLLECTION_NAME)
        collection_config = getattr(collection, "config", None)
        collection_metadata = getattr(collection_config, "metadata", None)
        if collection_metadata != expected_manifest:
            raise RuntimeError(
                "RAG index verification failed: collection provenance is stale."
            )

        indexed_count = int(
            self.client.count(
                collection_name=RAGConfig.COLLECTION_NAME,
                exact=True,
            ).count
        )
        if indexed_count != len(expected_ids):
            raise RuntimeError(
                "RAG index verification failed: "
                f"expected {len(expected_ids)} points, found {indexed_count}."
            )
        points = self.client.retrieve(
            collection_name=RAGConfig.COLLECTION_NAME,
            ids=expected_ids,
            with_payload=True,
            with_vectors=False,
        )
        actual_ids = {str(point.id) for point in points}
        if actual_ids != set(expected_ids):
            raise RuntimeError(
                "RAG index verification failed: collection point identity "
                "does not match the reviewed corpus."
            )
        for point in points:
            point_id = str(point.id)
            actual_digest = self._stored_payload_digest(point.payload)
            if actual_digest != expected_payload_digests.get(point_id):
                raise RuntimeError(
                    "RAG index verification failed: collection point content "
                    "does not match the reviewed corpus."
                )

    def _index_is_current(
        self,
        expected_manifest: dict[str, object],
        *,
        expected_ids: list[str],
        expected_payload_digests: dict[str, str],
    ) -> bool:
        manifest = self._read_manifest()
        if manifest != expected_manifest:
            return False
        try:
            self._verify_indexed_identity(
                expected_manifest,
                expected_ids=expected_ids,
                expected_payload_digests=expected_payload_digests,
            )
        except Exception:
            logger.debug("RAG point-identity verification failed", exc_info=True)
            return False
        return True

    @classmethod
    def document_ids(cls, docs: list[_DocumentLike]) -> list[str]:
        """Return stable point identities for the exact content and metadata."""
        return [
            str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{RAGConfig.COLLECTION_NAME}:{cls._document_payload_digest(doc)}",
                )
            )
            for doc in docs
        ]

    @classmethod
    def _expected_payload_digests(cls, docs: list[_DocumentLike]) -> dict[str, str]:
        return {
            point_id: cls._document_payload_digest(doc)
            for point_id, doc in zip(cls.document_ids(docs), docs, strict=True)
        }

    @staticmethod
    def _require_unique_document_identities(
        *,
        document_count: int,
        payload_digests: Mapping[str, str],
    ) -> None:
        if len(payload_digests) != document_count:
            raise RuntimeError(
                "RAG index verification failed: duplicate document identity."
            )

    @classmethod
    def _document_payload_digest(cls, doc: _DocumentLike) -> str:
        return cls._payload_digest(
            {
                "page_content": doc.page_content,
                "metadata": doc.metadata,
            }
        )

    @classmethod
    def _stored_payload_digest(cls, payload: object) -> str | None:
        if not isinstance(payload, Mapping):
            return None
        if set(payload) != {"page_content", "metadata"}:
            return None
        if not isinstance(payload.get("page_content"), str) or not isinstance(
            payload.get("metadata"), Mapping
        ):
            return None
        try:
            return cls._payload_digest(payload)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _payload_digest(payload: Mapping[str, object]) -> str:
        canonical = json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def _read_manifest() -> dict[str, object] | None:
        path = RAGConfig.get_index_manifest_path()
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _write_manifest(manifest: dict[str, object]) -> None:
        path = RAGConfig.get_index_manifest_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            temporary.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _remove_manifest() -> None:
        RAGConfig.get_index_manifest_path().unlink(missing_ok=True)

    def close(self):
        """Closes the Qdrant client connection and releases resources.

        Only closes the client if it was created internally (not passed in).
        """
        if self.client and self._owns_client:
            self.client.close()
