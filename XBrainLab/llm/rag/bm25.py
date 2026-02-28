"""Lightweight BM25 scorer for hybrid RAG retrieval.

Implements Okapi BM25 scoring without external dependencies beyond the
Python standard library.  Designed to complement the Qdrant semantic
retriever with keyword-based scoring for improved exact-match recall.

Reference:
    Robertson, S. & Zaragoza, H. (2009). *The Probabilistic Relevance
    Framework: BM25 and Beyond*. Foundations and Trends in IR, 3(4).
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from pathlib import Path

logger = logging.getLogger(__name__)

# ── BM25 hyper-parameters (Okapi defaults) ──────────────────
_K1 = 1.5
_B = 0.75


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer.

    Lowercases the text, splits on non-alphanumeric characters, and
    discards tokens shorter than 2 characters.
    """
    return [t for t in re.split(r"[^a-z0-9_]+", text.lower()) if len(t) >= 2]


class BM25Index:
    """In-memory BM25 index over a collection of documents.

    Each document is stored as ``(doc_id, text, metadata)`` where
    *text* is the content used for scoring and *metadata* is passed
    through unmodified.

    Attributes:
        doc_count: Number of indexed documents.
        avg_dl: Average document length (in tokens).
    """

    def __init__(self):
        self._docs: list[tuple[str, str, dict]] = []  # (id, text, metadata)
        self._tf: list[Counter] = []  # per-doc term freq
        self._df: Counter = Counter()  # document freq
        self._dl: list[int] = []  # doc lengths
        self.avg_dl: float = 0.0
        self.doc_count: int = 0

    # ── Build ────────────────────────────────────────────────

    def add_document(self, doc_id: str, text: str, metadata: dict | None = None):
        """Adds a single document to the index.

        Args:
            doc_id: Unique identifier for the document.
            text: The searchable content.
            metadata: Arbitrary metadata attached to this document.
        """
        tokens = _tokenize(text)
        tf = Counter(tokens)
        self._docs.append((doc_id, text, metadata or {}))
        self._tf.append(tf)
        self._dl.append(len(tokens))
        for term in tf:
            self._df[term] += 1
        self.doc_count = len(self._docs)
        self.avg_dl = sum(self._dl) / self.doc_count if self.doc_count else 0

    def build_from_json(self, json_path: str | Path):
        """Bulk-loads documents from a gold-set JSON file.

        Expected format: a JSON array of objects each containing an
        ``input`` field (content) and optional ``id``, ``category``,
        ``expected_tool_calls`` fields (metadata).

        Args:
            json_path: Path to the JSON file.
        """
        path = Path(json_path)
        if not path.exists():
            logger.warning("BM25 build: file not found: %s", path)
            return

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        for item in data:
            content = item.get("input", "")
            if not content:
                continue
            doc_id = str(item.get("id", len(self._docs)))
            metadata = {
                "id": item.get("id"),
                "category": item.get("category"),
                "tool_calls": json.dumps(item.get("expected_tool_calls", [])),
                "input": content,
            }
            self.add_document(doc_id, content, metadata)

        logger.info("BM25 index built: %d documents", self.doc_count)

    # ── Query ────────────────────────────────────────────────

    def query(self, text: str, k: int = 3) -> list[tuple[float, str, str, dict]]:
        """Scores all documents against the query and returns top-*k*.

        Args:
            text: The query text.
            k: Maximum number of results.

        Returns:
            A list of ``(score, doc_id, doc_text, metadata)`` tuples
            sorted by descending BM25 score.
        """
        if not self._docs:
            return []

        q_tokens = _tokenize(text)
        if not q_tokens:
            return []

        scores: list[tuple[float, int]] = []
        n = self.doc_count

        for idx in range(n):
            score = 0.0
            dl = self._dl[idx]
            tf_map = self._tf[idx]
            for term in q_tokens:
                if term not in tf_map:
                    continue
                tf_val = tf_map[term]
                df_val = self._df.get(term, 0)
                # IDF (with floor to avoid negative for very common terms)
                idf = max(math.log((n - df_val + 0.5) / (df_val + 0.5) + 1.0), 0.0)
                # BM25 TF component
                numerator = tf_val * (_K1 + 1)
                denominator = tf_val + _K1 * (1 - _B + _B * dl / self.avg_dl)
                score += idf * numerator / denominator
            if score > 0:
                scores.append((score, idx))

        scores.sort(key=lambda x: x[0], reverse=True)
        results = []
        for s, idx in scores[:k]:
            doc_id, doc_text, meta = self._docs[idx]
            results.append((s, doc_id, doc_text, meta))
        return results
