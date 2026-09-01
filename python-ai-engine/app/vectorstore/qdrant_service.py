"""
app/vectorstore/qdrant_service.py

Step 7 of the pipeline: store embedded Chunks in Qdrant, and search them
back out. This is the ONLY file that talks to Qdrant directly -- same
"one file owns this concern" pattern as embedding_service.py owning the
embedding model, so the connection details (host/port/collection name)
and the point-ID scheme below are never duplicated or drifted between
ingestion and retrieval.

REAL PROBLEM FOUND AND FIXED WHILE BUILDING THIS: Qdrant point IDs must be
either an unsigned integer or a valid UUID -- confirmed directly against a
real qdrant-client (1.19.0) instance, which raised
    ValueError: Point id bns_2023__IV__103__0 is not a valid UUID
when handed chunker.py's actual deterministic string IDs
("bns_2023__IV__103__0") directly. Those readable string IDs are exactly
what makes re-ingestion idempotent (chunk.py's whole design), so this file
can't just discard them -- it converts each one into a deterministic UUID
via uuid5 (confirmed: the SAME input string always produces the SAME UUID,
so idempotency is fully preserved) and keeps the original readable string
in the payload (under "chunk_id") for debugging/citation, since the UUID
itself carries no human-readable meaning.
"""

import uuid

from qdrant_client import QdrantClient, models

from app.config.settings import settings
from app.models.chunk import Chunk, ChunkMetadata, DocumentType, LegalStatus

# Fixed namespace for turning a chunk_id STRING into a deterministic UUID
# (uuid.uuid5(namespace, name) -- same namespace + same name ALWAYS produces
# the same UUID, which is exactly what idempotent upsert needs). This must
# NEVER change once real data has been ingested: changing it would silently
# generate a whole new set of UUIDs for the same chunk_ids, breaking upsert
# and creating duplicates instead of updates. Generated once with
# uuid.uuid4() and hardcoded here -- not regenerated at import time.
_ID_NAMESPACE = uuid.UUID("a47ac10b-58cc-4372-a567-0e02b2c3d479")


def _point_id(chunk_id: str) -> str:
    """Turn a chunker.py chunk_id ("bns_2023__IV__103__0") into a Qdrant-
    legal point ID. VERIFIED deterministic: the same chunk_id string always
    produces the same UUID, so re-ingesting the same document upserts
    (overwrites) the existing point instead of creating a duplicate --
    preserving the exact idempotency guarantee chunk.py's ID scheme was
    built for, just re-expressed in a shape Qdrant will actually accept."""
    return str(uuid.uuid5(_ID_NAMESPACE, chunk_id))


# ---------------------------------------------------------------
# Lazy singleton client, same pattern as embedding_service._get_model():
# importing this module should be instant; connecting to Qdrant only
# happens on first real use.
# ---------------------------------------------------------------
_client: QdrantClient | None = None


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
    return _client


def ensure_collection() -> None:
    """Create settings.QDRANT_COLLECTION_NAME if it doesn't already exist,
    sized to settings.EMBEDDING_DIMENSION. Safe to call every time
    ingestion runs -- checks existence first rather than trying to create
    and catching an AlreadyExists error, so repeated runs are silent and
    cheap, not warning-spammy.

    Distance metric is COSINE, not because settings.py declares it
    (nothing does -- this is a real, undocumented choice made here) but
    because sentence-transformers models, including the
    all-MiniLM-L6-v2 configured in settings.py, are trained and evaluated
    using cosine similarity. Using a different metric (dot product,
    Euclidean) here would silently produce worse rankings without any
    error -- the same class of silent-mismatch risk settings.py's own
    comment warns about for the embedding model choice itself.
    """
    client = _get_client()
    if client.collection_exists(settings.QDRANT_COLLECTION_NAME):
        return
    client.create_collection(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        vectors_config=models.VectorParams(
            size=settings.EMBEDDING_DIMENSION,
            distance=models.Distance.COSINE,
        ),
    )


def upsert_chunks(chunks: list[Chunk]) -> int:
    """Store a batch of EMBEDDED chunks in Qdrant. Idempotent: re-running
    this on the same chunks overwrites the existing points (same chunk_id
    -> same deterministic UUID -> same point), never creates duplicates.

    Fails LOUDLY, before touching Qdrant at all, if any chunk hasn't been
    embedded yet (chunk.vector is still None) -- same "catch it at the
    source" philosophy chunker.py uses for missing structure and
    embedding_service.py uses for a wrong vector dimension. Silently
    skipping un-embedded chunks would mean a chunk that LOOKS ingested
    (no error raised) is actually unsearchable, discovered only much later
    when a real query fails to find it.

    Returns the number of points written.
    """
    if not chunks:
        return 0

    missing_vectors = [c.id for c in chunks if c.vector is None]
    if missing_vectors:
        raise ValueError(
            f"{len(missing_vectors)} chunk(s) have no vector yet -- call "
            f"embed_chunks() before upsert_chunks(). First missing id: "
            f"{missing_vectors[0]!r}"
        )

    ensure_collection()
    client = _get_client()

    points = [
        models.PointStruct(
            id=_point_id(chunk.id),
            vector=chunk.vector,
            payload={
                # The original readable chunk_id, kept for debugging and
                # for citations -- the UUID itself carries no meaning.
                "chunk_id": chunk.id,
                "text": chunk.text,
                **chunk.metadata.model_dump(),
            },
        )
        for chunk in chunks
    ]

    client.upsert(collection_name=settings.QDRANT_COLLECTION_NAME, points=points)
    return len(points)


def _payload_to_chunk(payload: dict) -> Chunk:
    """Reconstruct a Chunk object from a Qdrant point's payload -- the
    inverse of the payload built in upsert_chunks(). Keeps retriever.py
    (not yet built) working with the same Chunk type everywhere else in
    the pipeline already uses, rather than leaking raw Qdrant payload
    dicts out of this file."""
    payload = dict(payload)  # don't mutate the caller's dict
    chunk_id = payload.pop("chunk_id")
    text = payload.pop("text")
    return Chunk(id=chunk_id, text=text, metadata=ChunkMetadata(**payload))


def search(
    query_vector: list[float],
    limit: int = 5,
    document_type: DocumentType | None = None,
    legal_status: LegalStatus | None = None,
) -> list[Chunk]:
    """Search for the `limit` chunks most similar to query_vector.

    document_type / legal_status are OPTIONAL Qdrant-side filters --
    e.g. legal_status=LegalStatus.CURRENT to exclude CrPC/IPC chunks from
    an answer about current law, without the caller needing to fetch
    extra results and filter them out in Python afterward.

    Returns real Chunk objects (see _payload_to_chunk), not raw Qdrant
    search results -- so retriever.py and rag_service.py never need to
    know Qdrant's response shape at all.
    """
    client = _get_client()

    must: list[models.FieldCondition] = []
    if document_type is not None:
        must.append(
            models.FieldCondition(
                key="document_type", match=models.MatchValue(value=document_type.value)
            )
        )
    if legal_status is not None:
        must.append(
            models.FieldCondition(
                key="legal_status", match=models.MatchValue(value=legal_status.value)
            )
        )
    query_filter = models.Filter(must=must) if must else None

    results = client.query_points(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        query=query_vector,
        limit=limit,
        query_filter=query_filter,
        with_payload=True,
    )

    return [_payload_to_chunk(point.payload) for point in results.points]