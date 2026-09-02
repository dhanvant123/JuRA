"""
tests/test_chunker.py

Regression tests for chunker.py, run against the REAL PDFs in legal-data/
-- not synthetic strings. Every test here locks in a specific bug that was
found and fixed by testing against real documents across many sessions;
if any of these ever fail again, a real regression has been reintroduced,
not a hypothetical one.

Run with: pytest tests/test_chunker.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app.ingestion.pdf_loader import load_pdf_pages
from app.ingestion.text_cleaner import clean_text, remove_repeated_lines
from app.ingestion.chunker import chunk_document
from app.models.document import Document
from app.models.chunk import DocumentType, LegalStatus
from app.config.settings import settings


# ---------------------------------------------------------------
# Shared fixtures: load + chunk each real document ONCE per test session
# (not once per test) -- chunking a 400-page PDF repeatedly for every
# assertion would make this suite slow for no benefit.
# ---------------------------------------------------------------

def _chunk_real_pdf(document_id, title, filename, folder, doc_type, legal_status):
    path = folder / filename
    if not path.exists():
        pytest.skip(f"{path} not present -- skipping tests that need it")
    pages = load_pdf_pages(str(path))
    cleaned = remove_repeated_lines([clean_text(p.text) for p in pages])
    doc = Document(
        document_id=document_id, title=title, document_type=doc_type,
        legal_status=legal_status, file_path=str(path), source="India Code",
        total_pages=len(pages),
    )
    return chunk_document(doc, cleaned)


@pytest.fixture(scope="session")
def constitution_chunks():
    return _chunk_real_pdf(
        "constitution_2026", "Constitution of India", "constitution_2026.pdf",
        settings.CONSTITUTION_DIR, DocumentType.CONSTITUTION, LegalStatus.CURRENT,
    )


@pytest.fixture(scope="session")
def bns_chunks():
    return _chunk_real_pdf(
        "bns_2023", "Bharatiya Nyaya Sanhita, 2023", "bns_2023.pdf",
        settings.CURRENT_LAWS_DIR, DocumentType.ACT, LegalStatus.CURRENT,
    )


@pytest.fixture(scope="session")
def bnss_chunks():
    return _chunk_real_pdf(
        "bnss_2023", "Bharatiya Nagarik Suraksha Sanhita, 2023", "bnss_2023.pdf",
        settings.CURRENT_LAWS_DIR, DocumentType.ACT, LegalStatus.CURRENT,
    )


@pytest.fixture(scope="session")
def crpc_chunks():
    return _chunk_real_pdf(
        "crpc_1973", "Code of Criminal Procedure, 1973", "crpc.pdf",
        settings.HISTORICAL_LAWS_DIR, DocumentType.CODE, LegalStatus.SUPERSEDED,
    )


@pytest.fixture(scope="session")
def ipc_chunks():
    return _chunk_real_pdf(
        "ipc_1860", "Indian Penal Code, 1860", "ipc.pdf",
        settings.HISTORICAL_LAWS_DIR, DocumentType.CODE, LegalStatus.REPEALED,
    )


# ---------------------------------------------------------------
# Universal invariants: must hold for EVERY document, checked once per
# document via parametrization rather than duplicating each assertion
# six times.
# ---------------------------------------------------------------

ALL_DOCS = ["constitution_chunks", "bns_chunks", "bnss_chunks", "crpc_chunks", "ipc_chunks"]


@pytest.mark.parametrize("fixture_name", ALL_DOCS)
def test_no_duplicate_chunk_ids(fixture_name, request):
    chunks = request.getfixturevalue(fixture_name)
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids)), (
        f"{fixture_name}: found duplicate chunk ids -- this means the "
        f"seen_ids collision guard in chunk_document() failed, and a real "
        f"chunk would silently overwrite another in Qdrant."
    )


@pytest.mark.parametrize("fixture_name", ALL_DOCS)
def test_no_chunk_exceeds_max_chars(fixture_name, request):
    chunks = request.getfixturevalue(fixture_name)
    oversized = [c for c in chunks if len(c.text) > settings.MAX_CHUNK_CHARS]
    assert not oversized, (
        f"{fixture_name}: {len(oversized)} chunk(s) exceed "
        f"MAX_CHUNK_CHARS={settings.MAX_CHUNK_CHARS} -- split_by_size() or "
        f"the clause packers failed to respect the budget. First "
        f"offender: {oversized[0].id if oversized else None}"
    )


@pytest.mark.parametrize("fixture_name", ALL_DOCS)
def test_every_chunk_has_section_or_article(fixture_name, request):
    chunks = request.getfixturevalue(fixture_name)
    unlabeled = [c for c in chunks if not c.metadata.section and not c.metadata.article]
    assert not unlabeled, (
        f"{fixture_name}: {len(unlabeled)} chunk(s) have neither section "
        f"nor article set -- every real unit must be labeled one or the "
        f"other. First offender: {unlabeled[0].id if unlabeled else None}"
    )


@pytest.mark.parametrize("fixture_name", ALL_DOCS)
def test_no_form_text_leaked_into_chunks(fixture_name, request):
    chunks = request.getfixturevalue(fixture_name)
    leaked = [c for c in chunks if "FORM NO." in c.text]
    assert not leaked, (
        f"{fixture_name}: {len(leaked)} chunk(s) contain 'FORM NO.' text -- "
        f"the Schedule/Form boundary failed to exclude a Schedule's Form "
        f"listing, which will corrupt whichever real Section/Article it "
        f"got absorbed into."
    )


@pytest.mark.parametrize("fixture_name", ALL_DOCS)
def test_chunks_start_at_unit_one(fixture_name, request):
    """Regression test for the detect_body_start_page bug where BNSS/CrPC/
    IPC's tables of contents were mistaken for real body content, causing
    ingestion to start at Section 71/36/115 instead of Section 1."""
    chunks = request.getfixturevalue(fixture_name)
    numbers = [
        int("".join(ch for ch in (c.metadata.section or c.metadata.article) if ch.isdigit()))
        for c in chunks if c.metadata.section or c.metadata.article
    ]
    assert min(numbers) == 1, (
        f"{fixture_name}: lowest unit number found is {min(numbers)}, not 1 "
        f"-- detect_body_start_page() likely mistook part of the table of "
        f"contents for real body content again."
    )


# ---------------------------------------------------------------
# Constitution-specific regressions
# ---------------------------------------------------------------

def test_constitution_uses_article_not_section(constitution_chunks):
    assert all(c.metadata.article for c in constitution_chunks if c.metadata.section is None), \
        "every Constitution chunk without a section should have an article"
    assert not any(c.metadata.section for c in constitution_chunks), \
        "Constitution chunks should never have .section set -- only .article"


def test_article_31d_repealed_stub_excluded(constitution_chunks):
    """Article 31D was inserted by the 42nd Amendment and omitted by the
    43rd -- it must NOT appear as a real chunk (see _is_repealed_stub)."""
    assert not any(c.metadata.article == "31D" for c in constitution_chunks)


def test_article_19_survives_repealed_letter_gap(constitution_chunks):
    """Regression test: Article 19's freedoms list goes (a)...(e),(g) --
    letter (f) was repealed by the 44th Amendment. The clause splitter
    must not stop accepting clauses at the gap (see _find_top_level_clauses'
    forward-only-tolerating-gaps design)."""
    a19 = [c for c in constitution_chunks if c.metadata.article == "19"]
    full_text = " ".join(c.text for c in a19)
    assert "(g) to practise any profession" in full_text, (
        "Article 19's clause (g) should still be present and correctly "
        "split, even though (f) was repealed and is absent from the "
        "real text."
    )


def test_article_366_uses_numbered_not_lettered_split(constitution_chunks):
    """Regression test: Article 366 ('Definitions') is primarily a
    NUMBERED list, but definition (29A) has its own nested LETTERED
    sub-list (a)-(e). The lettered-vs-numbered priority comparison must
    pick numbered here, not let the nested letters win."""
    a366 = [c for c in constitution_chunks if c.metadata.article == "366"]
    assert len(a366) > 1, "Article 366 is long enough that it must be split"
    # If the bug regressed, pieces would be suspiciously uniform
    # (~652 chars each, plain hard-cut) instead of clause-aligned varied sizes.
    sizes = sorted(len(c.text) for c in a366)
    assert sizes[-1] - sizes[0] > 100, (
        "Article 366's piece sizes look suspiciously uniform -- this is "
        "the exact signature of the lettered-clause-priority bug "
        "(nested (29A) sub-list wrongly winning over the real top-level "
        "numbered definitions)."
    )


def test_schedules_excluded_from_constitution(constitution_chunks):
    """Article 395 ('Repeals') is the real last article; the twelve
    Schedules that follow it are a different structure and must be cut
    off, not chunked as bogus articles."""
    numbers = [int("".join(ch for ch in c.metadata.article if ch.isdigit()))
               for c in constitution_chunks]
    assert max(numbers) <= 395, (
        f"found an article numbered above 395 ({max(numbers)}) -- the "
        f"Schedule boundary failed to cut off Schedule content."
    )


# ---------------------------------------------------------------
# Act-specific regressions
# ---------------------------------------------------------------

def test_crpc_section_484_not_corrupted_by_forms(crpc_chunks):
    """Regression test: CrPC's Second Schedule (118 'FORM NO. N' entries)
    used to get absorbed into Section 484's chunk, corrupting its title
    to 'Repeal and savings. THE FIRST SCHEDULE'."""
    sec484 = [c for c in crpc_chunks if c.metadata.section == "484"]
    assert sec484, "Section 484 should exist"
    assert sec484[0].metadata.section_title == "Repeal and savings", (
        f"Section 484's title is {sec484[0].metadata.section_title!r}, "
        f"expected exactly 'Repeal and savings' -- Form/Schedule content "
        f"may have leaked into it again."
    )


def test_crpc_late_duplicate_section_44_dropped(crpc_chunks):
    """Regression test: a Kerala State Amendment annexure re-quotes
    Section 409's original text verbatim near the end of the document.
    The forward-only filter should drop backward-jumping re-quotes like
    this rather than let them silently overwrite or duplicate."""
    sec44 = [c for c in crpc_chunks if c.metadata.section == "44"]
    assert len(sec44) == 1, (
        f"found {len(sec44)} chunks for Section 44, expected exactly 1 -- "
        f"either a real duplicate slipped through, or (less likely) a "
        f"legitimate second Section 44 exists that this test doesn't "
        f"know about."
    )


def test_bnss_section_2_definitions_split_by_clause(bnss_chunks):
    """Regression test: BNSS Section 2 (Definitions) used to bundle 6-8
    unrelated definitions into one 1450-char chunk. It should now be
    split at real lettered clause boundaries into smaller, more
    topically-focused pieces."""
    sec2 = [c for c in bnss_chunks if c.metadata.section == "2"]
    assert len(sec2) > 3, (
        f"Section 2 only produced {len(sec2)} chunks -- expected several, "
        f"since it's a long list of individually short definitions."
    )
    assert all(len(c.text) < 800 for c in sec2), (
        "Section 2's chunks are larger than expected for clause-based "
        "splitting -- may have fallen back to plain character splitting."
    )


def test_overlap_present_in_plain_size_split():
    """Regression test: split_by_size() lost its overlap logic in an
    earlier rewrite, then had it restored. Tested directly against the
    function (not a real document) because clause-based splitting
    (_pack_clauses) deliberately has NO overlap between pieces -- each
    clause boundary is a real, natural breakpoint, same reasoning as
    "splitting between two different sections needs no overlap". Only
    split_by_size()'s hard character cuts are artificial and need
    overlap to avoid stranding a clause reference at the cut point.
    """
    from app.ingestion.chunker import split_by_size

    long_text = ("Clause reference (a) above applies here. " * 50) + \
        "UNIQUE_MARKER_TEXT " + ("more filler text follows here. " * 50)
    pieces = split_by_size(long_text, 400)

    assert len(pieces) >= 2, "test text should be long enough to force a split"
    for i in range(len(pieces) - 1):
        tail = pieces[i][-60:]
        head = pieces[i + 1][:150]
        assert any(tail[j:j + 15] in head for j in range(0, len(tail) - 15, 5)), (
            f"no shared text found between piece {i} and piece {i+1} -- "
            f"overlap may have been lost again."
        )