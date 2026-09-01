"""
app/ingestion/ingestion_service.py

Orchestrator: ties pdf_loader -> text_cleaner -> chunker (-> embedding_service)
together for ONE document, in the correct order.

Why this file exists separately from each step:
Each of pdf_loader.py, text_cleaner.py, and chunker.py is deliberately
narrow. Something still has to call them in the right ORDER with the
right glue -- e.g. clean_text() runs per-page, but remove_repeated_lines()
needs ALL pages at once (see text_cleaner.py's own note on this). That
glue is this file's only job.

Does NOT touch Qdrant. Storing chunks is qdrant_service.py's job, called
separately by scripts/ingest_documents.py -- "produce chunks" and "store
chunks" stay separate so you can re-run/inspect one without the other.
"""

from app.embeddings.embedding_service import embed_chunks
from app.ingestion.chunker import chunk_document
from app.ingestion.pdf_loader import load_pdf_pages
from app.ingestion.text_cleaner import clean_text, remove_repeated_lines
from app.models.chunk import Chunk
from app.models.document import Document


def ingest_document(document: Document, embed: bool = True) -> list[Chunk]:
    """
    Runs one Document (already describing which PDF, its type/status/etc)
    from raw PDF bytes to a list of Chunk objects.

    Args:
        document: document.file_path is read from here -- this function
            takes no separate path argument, since Document is already
            the single source of truth for "which file is this".
        embed: if True (default), fills in chunk.vector for every chunk
            before returning. Set False to get chunks fast without
            paying the embedding-model cost (e.g. for review-only runs
            like scripts/review_chunks.py, where vectors are irrelevant).

    Returns:
        The list of Chunk objects. document.total_pages and
        document.total_chunks are updated on the SAME object passed in
        (mutated in place), matching Document's own docstring that says
        these are filled in progressively as ingestion runs.
    """

    pages = load_pdf_pages(document.file_path)
    document.total_pages = len(pages)

    # Per-page cleaning first -- Hindi stripping, amendment annotations,
    # hyphenation, whitespace. Each of these only needs ONE page's text.
    cleaned_pages = [clean_text(page.text) for page in pages]

    # Repeated headers/footers can only be detected by comparing ALL
    # pages at once -- called here, separately, exactly as
    # text_cleaner.py's own docstring requires.
    cleaned_pages = remove_repeated_lines(cleaned_pages)

    chunks = chunk_document(document, cleaned_pages)
    document.total_chunks = len(chunks)

    if embed:
        chunks = embed_chunks(chunks)

    return chunks