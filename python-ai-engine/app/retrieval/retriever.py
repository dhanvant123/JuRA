"""
app/retrieval/retriever.py

Step 10 of the pipeline, per the original plan: verify retrieval quality
with ZERO LLM involvement before adding rag_service.py. This file is
exactly that boundary -- it takes a plain text query and returns real
Chunk objects, and nothing here ever imports or calls an LLM.

Deliberately thin: embed_query() (embedding_service.py) and search()
(qdrant_service.py) already do all the real work and are already
individually verified. This file's only job is composing the two calls
in the right order, plus the query-time filtering options a real user
question needs (e.g. "only CURRENT law", "only the Constitution").
"""

from app.embeddings.embedding_service import embed_query
from app.vectorstore.qdrant_service import search
from app.models.chunk import Chunk, DocumentType, LegalStatus


def retrieve(
    query: str,
    limit: int = 5,
    document_type: DocumentType | None = None,
    legal_status: LegalStatus | None = None,
) -> list[Chunk]:
    """Embed `query` and return the `limit` most similar chunks.

    document_type / legal_status are optional query-time filters, passed
    straight through to qdrant_service.search() -- e.g. a user asking
    "what does current law say about X" can be answered with
    legal_status=LegalStatus.CURRENT, excluding CrPC/IPC chunks entirely
    rather than retrieving them and hoping the LLM ignores them.

    Returns [] if the query is empty/whitespace-only, rather than
    embedding an empty string and searching with a meaningless vector --
    an empty query is a caller bug, not a "no results" search outcome,
    but returning [] here (instead of raising) keeps this function
    simple; the caller (rag_service.py) is where deciding how to respond
    to an empty question belongs.
    """
    query = query.strip()
    if not query:
        return []

    query_vector = embed_query(query)
    return search(
        query_vector,
        limit=limit,
        document_type=document_type,
        legal_status=legal_status,
    )