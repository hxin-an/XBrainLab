"""Retrieval-Augmented Generation (RAG) sub-package.

Provides configuration, indexing, and retrieval components for
augmenting LLM prompts with semantically similar gold-set examples.
"""

from .config import RAGConfig
from .indexer import RAGIndexer
from .retriever import RAGRetriever

__all__ = ["RAGConfig", "RAGIndexer", "RAGRetriever"]
