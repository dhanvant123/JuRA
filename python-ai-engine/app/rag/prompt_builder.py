"""
app/rag/prompt_builder.py

Turns (query, retrieved chunks) into the two things rag_service.py needs
from this file: the prompt string to send to the LLM, and the Citation
objects for the final RagResponse.

Zero network calls -- no LLM client, no Qdrant client. Pure string/data
assembly, which is why it's testable without mocking anything external.
"""

from app.models.chunk import Chunk
from app.models.rag_response import Citation


SYSTEM_INSTRUCTIONS = (
    "You are a legal research assistant answering questions about Indian "
    "law. Answer ONLY using the numbered CONTEXT sections below -- do not "
    "use outside knowledge, and do not invent section numbers, article "
    "numbers, or citations not present in the CONTEXT. If the CONTEXT "
    "does not contain enough information to answer, say so explicitly "
    "instead of guessing. When you rely on a specific CONTEXT section, "
    "refer to it by its [N] marker so the answer can be traced back to a "
    "real source."
)


def _label_for_chunk(chunk: Chunk) -> str:
    """
    Short, human-readable label for one chunk's source -- e.g.
    "Article 21" or "Section 103. Murder" -- used both inside the prompt's
    CONTEXT block and in the final Citation, so the two always agree.
    """
    m = chunk.metadata
    if m.article:
        return f"Article {m.article}"
    if m.section:
        title = f". {m.section_title}" if m.section_title else ""
        return f"Section {m.section}{title}"
    return "Unlabelled provision"


def build_prompt(query: str, chunks: list[Chunk]) -> str:
    """
    Assembles the full prompt: system instructions, every retrieved
    chunk as a numbered CONTEXT block, then the user's question.

    Numbering the chunks [1], [2], [3]... (rather than just concatenating
    their text) is what lets the LLM point back at a SPECIFIC source in
    its answer instead of vaguely gesturing at "the context" as a whole --
    this is what makes the "cite your source" instruction enforceable.
    """
    if not chunks:
        context_block = "(No relevant provisions were found.)"
    else:
        context_parts = []
        for i, chunk in enumerate(chunks, start=1):
            label = _label_for_chunk(chunk)
            context_parts.append(
                f"[{i}] {chunk.metadata.document_title}, {label} "
                f"(page {chunk.metadata.page}):\n{chunk.text}"
            )
        context_block = "\n\n".join(context_parts)

    return (
        f"{SYSTEM_INSTRUCTIONS}\n\n"
        f"CONTEXT:\n{context_block}\n\n"
        f"QUESTION: {query}\n\n"
        f"ANSWER:"
    )


def build_citations(chunks: list[Chunk]) -> list[Citation]:
    """
    Converts retrieved Chunk objects into the trimmed-down Citation
    objects RagResponse requires. This is the ONLY place citations get
    built -- straight from real chunk metadata, never from anything the
    LLM said (see rag_response.py's own docstring for why that matters).
    """
    citations = []
    for chunk in chunks:
        m = chunk.metadata
        citations.append(
            Citation(
                document_title=m.document_title,
                article_or_section=_label_for_chunk(chunk),
                page=m.page,
                source=m.source,
                source_url=m.source_url,
            )
        )
    return citations