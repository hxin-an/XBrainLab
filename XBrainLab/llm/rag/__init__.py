"""Retrieval-Augmented Generation (RAG) sub-package.

Provides configuration, indexing, and retrieval components for
augmenting LLM prompts with semantically similar gold-set examples.

Includes a lightweight BM25 scorer for hybrid (dense + sparse)
retrieval — see ``bm25.py`` and ``retriever.py``.
"""

from .bm25 import BM25Index
from .config import RAGConfig
from .indexer import RAGIndexer
from .retriever import RAGRetriever

__all__ = ["BM25Index", "RAGConfig", "RAGIndexer", "RAGRetriever"]
