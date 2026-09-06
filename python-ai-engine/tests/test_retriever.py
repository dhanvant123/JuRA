"""
tests/test_retriever.py

Tests for retriever.py, run against REAL chunked/ingested data -- but
using test-double injections for the two things this test environment
can't reach: a real Qdrant server, and a real downloaded embedding model
(network access to huggingface.co isn't available in every environment
this suite might run in). The fake model below is a deterministic
bag-of-words embedding, NOT random -- similar text produces similar
vectors, so these tests can meaningfully check that a query actually
retrieves the RIGHT chunk, not just that the code runs without crashing.

Run with: pytest tests/test_retriever.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pytest
from qdrant_client import QdrantClient

from app.config.settings import settings


class _FakeTokenizer:
    def __call__(self, text, truncation=False):
        return {"input_ids": text.split() * 2}


def _fake_embed(text: str) -> np.ndarray:
    """Deterministic bag-of-words vector: same text -> same vector,
    overlapping vocabulary -> similar (higher cosine similarity)
    vectors. Not a real embedding model, but real ENOUGH to test that
    retrieval logic actually favors semantically-overlapping text over
    unrelated text, unlike a purely random fake would."""
    vec = np.zeros(settings.EMBEDDING_DIMENSION)
    for word in text.lower().split():
        vec[hash(word) % settings.EMBEDDING_DIMENSION] += 1.0
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


class _FakeModel:
    max_seq_length = 300
    tokenizer = _FakeTokenizer()

    def encode(self, texts, batch_size, show_progress_bar, convert_to_numpy):
        return np.array([_fake_embed(t) for t in texts])


@pytest.fixture(scope="module")
def ingested_constitution():
    """Ingest the real Constitution once per test module, into a fresh
    in-memory Qdrant instance, using the fake model above."""
    from app.vectorstore import qdrant_service
    from app.embeddings import embedding_service

    qdrant_service._client = QdrantClient(":memory:")
    embedding_service._model = _FakeModel()

    from app.ingestion.ingestion_service import ingest_all, DOCUMENT_REGISTRY

    entry = next(e for e in DOCUMENT_REGISTRY if e.document_id == "constitution_2026")
    if not entry.path.exists():
        pytest.skip(f"{entry.path} not present -- skipping retriever tests")

    ingest_all([entry])
    return qdrant_service


def test_retrieve_finds_semantically_relevant_chunk(ingested_constitution):
    """The real test that matters: does a query about a specific right
    actually retrieve the article about that right, not a random one?"""
    from app.retrieval.retriever import retrieve

    results = retrieve("protection of life and personal liberty", limit=3)
    assert results, "expected at least one result"
    top_articles = [r.metadata.article for r in results]
    assert "21" in top_articles, (
        f"expected Article 21 (Protection of life and personal liberty) "
        f"among top 3 results for a closely-matching query, got "
        f"articles: {top_articles}"
    )


def test_retrieve_respects_limit(ingested_constitution):
    from app.retrieval.retriever import retrieve

    results = retrieve("the president of india", limit=1)
    assert len(results) == 1


def test_retrieve_empty_query_returns_empty_list(ingested_constitution):
    from app.retrieval.retriever import retrieve

    assert retrieve("") == []
    assert retrieve("   ") == []


def test_retrieve_legal_status_filter_excludes_others(ingested_constitution):
    """The Constitution is entirely LegalStatus.CURRENT -- filtering by
    REPEALED should return nothing, proving the filter is actually
    reaching Qdrant, not being silently ignored."""
    from app.retrieval.retriever import retrieve
    from app.models.chunk import LegalStatus

    results = retrieve("the president of india", limit=5, legal_status=LegalStatus.REPEALED)
    assert results == []


def test_retrieve_returns_real_chunk_objects(ingested_constitution):
    from app.retrieval.retriever import retrieve
    from app.models.chunk import Chunk

    results = retrieve("fundamental rights", limit=1)
    assert results
    assert isinstance(results[0], Chunk)
    assert results[0].text  # real text, not empty
    assert results[0].metadata.document_id == "constitution_2026"