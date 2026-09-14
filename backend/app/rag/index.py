"""Policy retrieval: a Chroma-backed index with a lexical fallback."""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from pathlib import Path
from typing import Protocol

from app.rag.chunking import PolicyChunk, load_policy_chunks

logger = logging.getLogger(__name__)

_TOKEN = re.compile(r"[a-z0-9$]+")
_STOPWORDS = frozenset(
    """a an and are as at be by do does for from how i if in into is it my of on or
    our that the their there this to was what when where which who will with you your"""
    .split()
)


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS]


class PolicyIndex(Protocol):
    """Everything the ``search_policy`` tool needs from a retriever."""

    def search(self, query: str, top_k: int) -> list[PolicyChunk]: ...


class KeywordPolicyIndex:
    """A small TF-IDF retriever with no third-party dependencies.

    The policy corpus is two short sections, so lexical scoring is accurate
    here and it lets the test suite exercise real retrieval offline, with no
    embedding model download and no network access.
    """

    def __init__(self, chunks: list[PolicyChunk]) -> None:
        self._chunks = chunks
        self._term_frequencies = [Counter(_tokenize(c.embedding_text)) for c in chunks]
        document_frequency: Counter[str] = Counter()
        for frequencies in self._term_frequencies:
            document_frequency.update(frequencies.keys())
        total = max(len(chunks), 1)
        self._idf = {
            term: math.log(1 + total / (1 + count))
            for term, count in document_frequency.items()
        }

    def search(self, query: str, top_k: int) -> list[PolicyChunk]:
        query_terms = _tokenize(query)
        scored: list[tuple[float, int]] = []
        for position, frequencies in enumerate(self._term_frequencies):
            length = sum(frequencies.values()) or 1
            score = sum(
                (frequencies[term] / length) * self._idf.get(term, 0.0)
                for term in query_terms
            )
            if score > 0:
                scored.append((score, position))

        if not scored:
            # No lexical overlap: hand back the corpus head rather than
            # nothing, so the model can still say "the policy does not
            # address this" from evidence instead of from silence.
            return self._chunks[:top_k]

        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        return [self._chunks[position] for _, position in scored[:top_k]]


class ChromaPolicyIndex:
    """Local Chroma collection using Chroma's on-device embedding model.

    Chroma's default embedding function runs a small ONNX sentence encoder
    locally, which satisfies the zero-cost constraint without pulling a deep
    learning framework into the image.
    """

    COLLECTION = "omnicare_policy"

    def __init__(self, chunks: list[PolicyChunk], persist_dir: Path) -> None:
        import chromadb  # imported lazily so the fallback needs no dependency

        self._by_section = {chunk.section_id: chunk for chunk in chunks}
        persist_dir.mkdir(parents=True, exist_ok=True)

        client = chromadb.PersistentClient(path=str(persist_dir))
        self._collection = client.get_or_create_collection(
            name=self.COLLECTION, metadata={"hnsw:space": "cosine"}
        )
        self._collection.upsert(
            ids=[chunk.section_id for chunk in chunks],
            documents=[chunk.embedding_text for chunk in chunks],
            metadatas=[
                {"section_id": chunk.section_id, "document": chunk.document}
                for chunk in chunks
            ],
        )

    def search(self, query: str, top_k: int) -> list[PolicyChunk]:
        result = self._collection.query(
            query_texts=[query], n_results=min(top_k, len(self._by_section))
        )
        ids = (result.get("ids") or [[]])[0]
        return [self._by_section[i] for i in ids if i in self._by_section]


def build_policy_index(
    policy_path: Path, *, backend: str, persist_dir: Path
) -> PolicyIndex:
    """Build the configured index, degrading to lexical search on failure.

    A missing embedding model or a read-only cache should downgrade retrieval
    quality, not take the whole service down, so a Chroma failure is logged
    and answered with the lexical index instead.
    """
    chunks = load_policy_chunks(policy_path)
    logger.info("Ingested %d policy section(s) from %s", len(chunks), policy_path.name)

    if backend == "keyword":
        return KeywordPolicyIndex(chunks)

    try:
        return ChromaPolicyIndex(chunks, persist_dir)
    except Exception as exc:  # pragma: no cover - depends on local environment
        logger.warning(
            "Chroma index unavailable (%s); falling back to lexical retrieval.", exc
        )
        return KeywordPolicyIndex(chunks)
