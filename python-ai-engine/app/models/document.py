"""
app/models/document.py

Defines what a "Document" IS — one whole source PDF (e.g. bns_2023.pdf)
BEFORE it has been broken into chunks.

Why this is separate from Chunk:
    Chunk    = one retrieval unit (a section, an article, a piece of text)
    Document = the whole source file that chunks are extracted FROM

ingestion_service.py needs to track things at the document level:
"which PDF am I processing right now, how many pages does it have,
how many chunks did it produce, is this law current or superseded".
Without this model, that information would just be loose variables
scattered inside a script instead of one clear, validated object.

This model also reuses DocumentType and LegalStatus from chunk.py —
we import them instead of redefining them, so a document and its
resulting chunks can never disagree about what type/status it is.
"""

from typing import Optional
from pydantic import BaseModel, Field

# Reusing the SAME enums from chunk.py (not redefining them here).
# This matters: if "ACT" was defined separately in both files, a typo
# in one place wouldn't be caught by Python at all -- they'd just be
# two different strings that happen to look similar. Importing the
# same Enum class guarantees Document and Chunk always agree.
from app.models.chunk import DocumentType, LegalStatus


class Document(BaseModel):
    """
    Represents one source legal document (one PDF file) as a whole,
    before/during the ingestion process.
    """

    document_id: str = Field(
        ...,
        description=(
            "Stable, machine-readable identifier, e.g. 'bns_2023'. "
            "This is the SAME value that every Chunk produced from this "
            "document will carry in its ChunkMetadata.document_id -- "
            "it's what links a chunk back to its source document."
        ),
    )

    title: str = Field(
        ..., description="Human-readable name, e.g. 'Bharatiya Nyaya Sanhita, 2023'."
    )

    document_type: DocumentType
    legal_status: LegalStatus

    file_path: str = Field(
        ...,
        description=(
            "Path to the actual PDF on disk, e.g. "
            "'legal-data/current-laws/bns_2023.pdf'. "
            "pdf_loader.py uses this to know which file to open."
        ),
    )

    source: str = Field(
        ..., description="Where this legal text is published, e.g. 'India Code'."
    )
    source_url: Optional[str] = None

    # These two are filled in progressively as ingestion runs --
    # they start as None and get updated once pdf_loader.py and
    # chunker.py have actually processed this document.
    total_pages: Optional[int] = Field(
        default=None,
        description="Set by pdf_loader.py once the PDF is opened and page count is known.",
    )
    total_chunks: Optional[int] = Field(
        default=None,
        description="Set by chunker.py once this document has been fully chunked.",
    )

    class Config:
        use_enum_values = True