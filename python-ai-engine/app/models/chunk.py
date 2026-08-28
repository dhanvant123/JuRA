"""
app/models/chunk.py

Defines what a "Chunk" IS, as a validated Python object — not a loose dict.

Why this file exists:
Without this, chunker.py would just build plain dictionaries like:
    {"text": "...", "document_id": "bns_2023", "section": "103"}

That "works" until someone forgets a key, or misspells "sectoin", or passes
a page number as a string instead of an int. The bug then surfaces much
later — e.g. as a broken citation shown to a user — with no clear error
pointing back to where it went wrong.

By defining Chunk as a Pydantic model, every chunk gets VALIDATED the
moment it's created. If a required field is missing or the wrong type,
Python raises an error immediately, at the point of creation — which is
exactly where you want to be told about it.

This is the "noun" that flows through the whole pipeline:
    chunker.py        -> creates Chunk objects
    embedding_service  -> reads chunk.text, adds chunk.vector
    qdrant_service     -> reads chunk.id, chunk.vector, chunk.metadata to store
    retriever.py       -> returns a list[Chunk] as search results
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    """
    Restricts document_type to a known, fixed set of values instead of
    allowing any random string. str + Enum means it behaves like a string
    (easy to store/compare) but Python will reject anything not listed here.
    """
    CONSTITUTION = "CONSTITUTION"
    ACT = "ACT"          # e.g. BNS, BNSS, BSA
    CODE = "CODE"        # e.g. CrPC (historical)


class LegalStatus(str, Enum):
    """
    Tracks whether the law in this chunk is still in force.
    This directly addresses the constitution_2026 vs crpc_1973 problem:
    CrPC chunks get tagged SUPERSEDED so retrieval/rag_service can warn
    the user or deprioritize them instead of presenting them as current law.
    """
    CURRENT = "CURRENT"
    SUPERSEDED = "SUPERSEDED"
    REPEALED = "REPEALED"


class ChunkMetadata(BaseModel):
    """
    All the identifying information a chunk needs to carry so that,
    later, we can build a correct citation WITHOUT asking the LLM
    to invent one (per Step 12 of the plan).
    """

    document_id: str            # e.g. "bns_2023" — stable machine-readable id
    document_title: str         # e.g. "Bharatiya Nyaya Sanhita, 2023"
    document_type: DocumentType
    legal_status: LegalStatus

    # These are Optional because not every document has every field:
    # the Constitution has "part" + "article", Acts have "chapter" + "section".
    # Default value `None` means the field can be safely left unset.
    #
    # Each structural level now also has a *_title field holding its SUBJECT
    # (e.g. Part V's subject "THE UNION", Chapter I's subject "THE EXECUTIVE").
    # Capturing the subject -- not just the numeral -- is what lets a vector
    # search for "executive powers" find the right chapter, and lets citations
    # read "Part V (The Union), Article 52" instead of a bare "Part V".
    part: Optional[str] = None          # e.g. "Part III"  (Constitution)
    part_title: Optional[str] = None    # e.g. "Fundamental Rights"
    article: Optional[str] = None       # e.g. "21" / "21A" (Constitution)
    article_title: Optional[str] = None # e.g. "Protection of life and personal liberty"
    chapter: Optional[str] = None       # e.g. "Chapter IV" (Acts / Constitution)
    chapter_title: Optional[str] = None # e.g. "The Executive"
    section: Optional[str] = None       # e.g. "103"       (Acts)
    section_title: Optional[str] = None # e.g. "Punishment for murder"

    page: int                   # which PDF page this text came from
    source: str                  # e.g. "India Code", "Legislative Department"
    source_url: Optional[str] = None


class Chunk(BaseModel):
    """
    A single retrieval unit: one piece of legal text plus everything
    needed to identify, cite, and (later) embed it.
    """

    # Field(...) with "..." means this field is REQUIRED — Pydantic will
    # raise an error if it's missing, rather than silently defaulting.
    id: str = Field(
        ...,
        description=(
            "Deterministic ID, e.g. a hash of "
            "document_id + chapter + section + chunk_index. "
            "NOT a random UUID — must be the same every time this exact "
            "chunk is generated, so re-running ingestion overwrites "
            "(upserts) instead of duplicating. This is the idempotency "
            "mechanism agreed on in the original plan."
        ),
    )

    text: str = Field(..., description="The actual legal text content of this chunk.")

    metadata: ChunkMetadata

    # This stays empty until embedding_service.py fills it in.
    # It's Optional here because a freshly-chunked Chunk (before embedding)
    # is still a valid Chunk — just not embedded yet.
    vector: Optional[list[float]] = None

    class Config:
        # Allows us to use the Enum's .value (plain string) when this
        # model is converted to a dict/JSON, e.g. for sending to Qdrant
        # or returning via the future FastAPI endpoint.
        use_enum_values = True
