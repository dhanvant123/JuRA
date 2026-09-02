"""
app/ingestion/ingestion_service.py

Step 8 of the pipeline: the REAL orchestrator, tying every previously
built-and-tested piece together into one actual batch ingestion job --
pdf_loader -> text_cleaner -> chunker -> embedding_service -> qdrant_service.

Everything this file calls has already been individually verified against
real PDFs in earlier sessions; this file's only real job is the WIRING and
the DOCUMENT REGISTRY -- deciding which PDF is which document, with what
metadata, in what order.

REAL AMBIGUITY SURFACED WHILE BUILDING THIS: the original plan said
LegalStatus should be "auto-derived from which folder a document lives in"
(legal-data/current-laws/ vs legal-data/historical-laws/). That works
cleanly for current-laws/ (always CURRENT) but NOT for historical-laws/,
which contains BOTH CrPC (SUPERSEDED -- formally repealed by BNSS but still
referenced/citable during the transition) AND IPC (REPEALED -- fully
superseded by BNS, no transitional role). Folder alone can't distinguish
them. Rather than silently guessing one, this file keeps pure folder-based
auto-detection for the unambiguous cases (constitution/, current-laws/) and
uses a small explicit override map (_HISTORICAL_STATUS_OVERRIDES) for the
one folder that genuinely mixes two statuses.
"""

from dataclasses import dataclass
from pathlib import Path

from app.config.settings import settings
from app.ingestion.pdf_loader import load_pdf_pages
from app.ingestion.text_cleaner import clean_text, remove_repeated_lines
from app.ingestion.chunker import chunk_document
from app.embeddings.embedding_service import embed_chunks
from app.vectorstore.qdrant_service import upsert_chunks
from app.models.document import Document
from app.models.chunk import DocumentType, LegalStatus


@dataclass(frozen=True)
class DocumentEntry:
    """One row of the document registry below -- everything ingest_document()
    needs to know about a single source PDF that can't be reliably inferred
    from the file itself (a human still has to say what BNS's real title
    is; the PDF doesn't declare it in a machine-readable way)."""
    document_id: str
    title: str
    path: Path
    document_type: DocumentType
    source: str
    source_url: str | None = None


# Explicit override for historical-laws/ ONLY -- see module docstring for
# why this folder can't use pure auto-detection. Every filename here MUST
# be covered; ingest_document() raises loudly (not defaults silently) if a
# historical-laws/ file is missing from this map, since guessing a law's
# legal status wrong is exactly the kind of error the whole ChunkMetadata
# design (session 1) was built to prevent.
_HISTORICAL_STATUS_OVERRIDES: dict[str, LegalStatus] = {
    "crpc.pdf": LegalStatus.SUPERSEDED,
    "ipc.pdf": LegalStatus.REPEALED,
}


def _derive_legal_status(path: Path) -> LegalStatus:
    """Folder-based auto-detection, per the original plan -- except for
    historical-laws/, which needs the explicit override above."""
    if path.parent == settings.CURRENT_LAWS_DIR or path.parent == settings.CONSTITUTION_DIR:
        return LegalStatus.CURRENT
    if path.parent == settings.HISTORICAL_LAWS_DIR:
        if path.name not in _HISTORICAL_STATUS_OVERRIDES:
            raise ValueError(
                f"'{path.name}' is in historical-laws/ but has no entry in "
                f"_HISTORICAL_STATUS_OVERRIDES -- add one (SUPERSEDED or "
                f"REPEALED) rather than letting this default silently."
            )
        return _HISTORICAL_STATUS_OVERRIDES[path.name]
    raise ValueError(
        f"'{path}' isn't inside constitution/, current-laws/, or "
        f"historical-laws/ -- can't derive its legal_status."
    )


# THE REGISTRY: every document this project currently knows how to ingest.
# Title/document_type still need a human (title isn't reliably extractable
# from the PDF itself -- see DocumentEntry docstring); legal_status is
# derived automatically below, not hardcoded here, so it can never drift
# out of sync with which folder a file actually lives in.
def _entry(document_id: str, title: str, filename: str, folder: Path, doc_type: DocumentType) -> DocumentEntry:
    path = folder / filename
    return DocumentEntry(
        document_id=document_id, title=title, path=path, document_type=doc_type,
        source="India Code", source_url=None,
    )


DOCUMENT_REGISTRY: list[DocumentEntry] = [
    _entry("constitution_2026", "Constitution of India", "constitution_2026.pdf",
           settings.CONSTITUTION_DIR, DocumentType.CONSTITUTION),
    _entry("bns_2023", "Bharatiya Nyaya Sanhita, 2023", "bns_2023.pdf",
           settings.CURRENT_LAWS_DIR, DocumentType.ACT),
    _entry("bnss_2023", "Bharatiya Nagarik Suraksha Sanhita, 2023", "bnss_2023.pdf",
           settings.CURRENT_LAWS_DIR, DocumentType.ACT),
    _entry("bsa_2023", "Bharatiya Sakshya Adhiniyam, 2023", "bsa_2023.pdf",
           settings.CURRENT_LAWS_DIR, DocumentType.ACT),
    _entry("crpc_1973", "Code of Criminal Procedure, 1973", "crpc.pdf",
           settings.HISTORICAL_LAWS_DIR, DocumentType.CODE),
    _entry("ipc_1860", "Indian Penal Code, 1860", "ipc.pdf",
           settings.HISTORICAL_LAWS_DIR, DocumentType.CODE),
]


def ingest_document(entry: DocumentEntry) -> int:
    """Run the FULL pipeline for one document: load -> clean -> chunk ->
    embed -> store. Returns the number of chunks ingested.

    Deliberately does NOT catch exceptions -- every stage this calls
    (chunk_document, embed_texts, upsert_chunks) already fails loudly on
    its own real problems (no structure found, wrong vector dimension, an
    un-embedded chunk). Silently swallowing one of those here would defeat
    the whole point of them failing loudly in the first place.
    """
    if not entry.path.exists():
        raise FileNotFoundError(f"{entry.document_id}: no file at {entry.path}")

    legal_status = _derive_legal_status(entry.path)

    pages = load_pdf_pages(str(entry.path))
    cleaned_pages = remove_repeated_lines([clean_text(p.text) for p in pages])

    document = Document(
        document_id=entry.document_id,
        title=entry.title,
        document_type=entry.document_type,
        legal_status=legal_status,
        file_path=str(entry.path),
        source=entry.source,
        source_url=entry.source_url,
        total_pages=len(pages),
    )

    chunks = chunk_document(document, cleaned_pages)
    embed_chunks(chunks)
    return upsert_chunks(chunks)


def ingest_all(entries: list[DocumentEntry] | None = None) -> dict[str, int | str]:
    """Ingest every document in the registry (or a provided subset).

    UNLIKE ingest_document(), this DOES catch per-document failures --
    one malformed PDF shouldn't halt an entire batch run overnight. Each
    document's outcome (chunk count, or the error message) is reported
    individually so a partial failure is visible and specific, not a
    silent gap in Qdrant discovered days later.
    """
    if entries is None:
        entries = DOCUMENT_REGISTRY

    results: dict[str, int | str] = {}
    for entry in entries:
        try:
            count = ingest_document(entry)
            results[entry.document_id] = count
            print(f"OK  {entry.document_id}: {count} chunks ingested")
        except Exception as e:
            results[entry.document_id] = f"FAILED: {type(e).__name__}: {e}"
            print(f"FAIL {entry.document_id}: {type(e).__name__}: {e}")

    return results


if __name__ == "__main__":
    ingest_all()