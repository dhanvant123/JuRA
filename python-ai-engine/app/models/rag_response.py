"""
app/models/rag_response.py

Defines what a final ANSWER looks like -- the thing rag_service.py
returns after retrieval + LLM generation have both finished.

Why this exists as its own model instead of just returning a plain string:

Per Step 12 of the original plan, citations must come from the retrieved
chunk metadata -- NOT from the LLM inventing them. If rag_service.py just
returned a string of text, there'd be nothing forcing that rule. By making
"citations" a required, structured field (a list of real Chunk objects),
it's impossible to accidentally ship an answer with no traceable source,
or with a citation the LLM made up on its own.

This is also the exact shape that main.py (the future FastAPI endpoint)
will send back to Spring Boot as JSON.
"""

from pydantic import BaseModel, Field

from app.models.chunk import Chunk


class Citation(BaseModel):
    """
    A single, user-facing citation -- a trimmed-down view of a Chunk,
    showing only what's needed to display "where this came from"
    without dumping the full chunk text/vector into the response.
    """

    document_title: str = Field(..., description="e.g. 'Constitution of India'")
    article_or_section: str = Field(
        ..., description="e.g. 'Article 21' or 'Section 103' -- whichever applies"
    )
    page: int
    source: str = Field(..., description="e.g. 'Legislative Department', 'India Code'")
    source_url: str | None = None


class RagResponse(BaseModel):
    """
    The complete answer returned to whoever asked the question --
    whether that's a CLI script (search.py) during testing, or later
    Spring Boot calling the real FastAPI endpoint.
    """

    query: str = Field(..., description="The original question the user asked.")

    answer: str = Field(
        ..., description="The LLM-generated answer, built ONLY from retrieved chunks."
    )

    citations: list[Citation] = Field(
        ...,
        description=(
            "Real sources the answer was built from. Built directly from "
            "the Chunk objects retrieval returned -- never invented by the LLM."
        ),
    )

    # Keeping the raw retrieved chunks too (not just the trimmed Citations)
    # is useful for debugging: if an answer looks wrong, you can inspect
    # exactly what text the LLM was given, not just the final citation labels.
    retrieved_chunks: list[Chunk] = Field(
        default_factory=list,
        description="The full Chunk objects used as context, kept for debugging/inspection.",
    )