"""
app/ingestion/chunker.py

Step 4 + 5 of the pipeline: clean, structured text -> a list of Chunk
objects, split along REAL legal structure (Part/Chapter/Article/Section)
rather than blindly every N characters.

This is the highest-stakes file in the whole pipeline: get this wrong,
and every citation built later is wrong. So the detection here is grounded
in the ACTUAL text our extractor produces (verified against the real
constitution_2026.pdf output), not in how the documents "should" look:

    PART <roman>                          e.g. "PART V"        (subject on NEXT line: "THE UNION")
    CHAPTER <roman>.<dash><SUBJECT>        e.g. "CHAPTER I.⎯THE EXECUTIVE"
    <number>[<letter>]. <Title><dash><body> e.g. "52. The President of India.—There shall..."

Key realities this file handles (each one previously dropped data):

  1. The Constitution does NOT print the word "Article". An article is just
     a number: "52. The President of India.—...". So a unit is detected by
     its NUMBER, and whether that number is an ARTICLE or a SECTION is decided
     by the document's type, not by the word next to it.

  2. Article/section numbers can carry a LETTER SUFFIX: 21A, 239AA, 243ZG.
     The number pattern must allow that suffix or ~49 constitutional articles
     vanish into the previous chunk.

  3. Titles can contain a period ("...pardons, etc., and to...") and can wrap
     across lines. The title runs up to the em/en dash that starts the body,
     NOT up to the first period.

  4. The SUBJECT of a Part/Chapter/Article/Section is captured and stored --
     in metadata AND prepended into the chunk text -- because that subject is
     often the most searchable phrase for the vector DB, and later sub-chunks
     (after the size-split) would otherwise carry no identity at all.

Two document "shapes" exist in our corpus, and one shared chunker handles both:
    1. The Constitution: Part -> (Chapter ->) Article
    2. The Acts (BNS/BNSS/BSA/CrPC/IPC): (Part ->) Chapter -> Section
"""

import re

from app.models.chunk import Chunk, ChunkMetadata, DocumentType
from app.models.document import Document
from app.config.settings import settings


# ---------------------------------------------------------------
# REGEX PATTERNS -- each detects the START of a structural unit.
# Compiled once at module level so they're reused, not rebuilt on
# every call. re.MULTILINE makes ^ match at the start of each line.
# ---------------------------------------------------------------

_ROMAN = r"[IVXLCDM]+"

# A PART numeral may carry a LETTER SUFFIX in the Constitution: amendments
# inserted whole Parts *between* existing ones -- Part IVA (Fundamental
# Duties), Part IXA (Municipalities), Part IXB (Co-operative Societies) --
# rather than renumber everything after them. A bare [IVXLCDM]+ stops at the
# 'A'/'B' and would collapse IVA->IV, IXA->IX->IXB, silently merging three
# distinct Parts. The trailing [A-Z]{0,2} keeps them distinct. (It only ever
# grabs letters *glued* to the numeral; real Part titles sit on the next
# line, so nothing is over-captured from the title.)
_PART_NUM = r"[IVXLCDM]+[A-Z]{0,2}"

# Leading amendment-insertion marker: an inserted Part/Chapter/Article prints
# a superscript footnote number and bracket before it, e.g. "1[PART IX",
# "2[21A.". Every structural pattern tolerates this optional "N[" prefix; when
# present it MUST end in "[", so it never mis-bites a plain "PART V" or "52.".
_MARKER = r"(?:\d+\[)?"

# The dashes that separate a heading from its body. Our extractor emits:
#   — EM DASH        -> the overwhelmingly common body separator (2000+)
#   – EN DASH        -> occasional variant
# (A plain hyphen "-" is deliberately NOT accepted as a unit separator:
#  it collides with hyphenated words like "Vice-President" and would cause
#  false splits. Chapter titles additionally use ⎯, handled separately.)
_BODY_DASH = "—–"

# "PART V" or "1[PART IX" (numeral, optional letter suffix -- the subject sits
# on the FOLLOWING line, so it's pulled out separately by _title_after_part(),
# not by this pattern).
PART_PATTERN = re.compile(rf"^{_MARKER}PART\s+({_PART_NUM})\b", re.MULTILINE)

# "CHAPTER I.⎯THE EXECUTIVE" (or "1[CHAPTER ...") -- numeral, then the
# separator run ("." + ⎯ / dash / spaces), then the SUBJECT on the same line.
CHAPTER_PATTERN = re.compile(
    rf"^{_MARKER}CHAPTER\s+({_ROMAN})\s*[.⎯—–-]*\s*(.*)$",
    re.MULTILINE,
)

# A numbered unit heading (article in the Constitution, section in an Act).
# CRUCIAL distinction confirmed against the real PDF:
#   BODY:     "52. The President of India.—There shall be a President..."
#             -> the title STARTS on the number's line (and may then wrap).
#   CONTENTS: "52.\nThe President of India."
#             -> the number is ALONE on its line; the title is on the next.
# So we require title text to BEGIN on the number's own line: number, then
# space(s), then a non-space char. That single constraint excludes the whole
# table of contents (which otherwise leaked in as a garbage "Article 1" chunk).
#
# Leading amendment marker: inserted articles print a superscript footnote
# number and bracket before the number, e.g. "2[21A. Right to education.—".
# Without tolerating that "N[" prefix, ~dozens of *current* articles (21A,
# 239, 239AA, 371J, ...) are missed. The (?:\d+\[)? prefix is optional but,
# when present, MUST end in "[", so it never mis-bites a plain number like
# "52." (there is no "[" there, so it matches zero and group(1) reads "52").
#   group(1) = number WITH optional letter suffix (21, 21A, 239AA, 243ZG);
#              bounded to <=3 digits + <=4 letters so a stray "17160." can't match.
#   group(2) = title.
#
# THE TITLE MUST BE TEMPERED, or two things break (both observed on the real
# PDF). A page's bottom-of-page FOOTNOTES look exactly like article headings:
# "1. Subs. by the Constitution (Seventh Amendment) Act, 1956, s. 27, ...".
# That footnote has no em dash of its own, so with a naive DOTALL capture its
# "title" wanders 200 chars across the blank line and the "1[PART IVA" heading
# until it hits the FIRST dash it can find -- the one after the *next real
# article's* title ("51A. Fundamental duties.—") -- registering the footnote
# as a bogus "Article 1" AND swallowing Article 51A whole. Article 243 and
# 243P (each sitting right after such a footnote + Part heading) vanished the
# same way.
#   Fix: the title may wrap across ordinary continuation lines, but the three
#   negative lookaheads forbid it from crossing (a) a blank line, (b) a
#   Part/Chapter heading, or (c) the next numbered-unit line. So a footnote
#   with no nearby dash simply fails to match (no bogus article), and no
#   heading can ever reach past its own unit into the following one. Real
#   wrapped titles (Article 72, 368) are unaffected -- they wrap over plain
#   continuation lines with no blank line or heading in between.
_TITLE_BODY = (
    r"\S(?:"
    r"(?!\n[ \t]*\n)"                                   # (a) not a blank line
    r"(?!\n[ \t]*(?:\d+\[)?(?:PART|CHAPTER)\b)"          # (b) not a Part/Chapter heading
    r"(?!\n[ \t]*(?:\d+\[)?\d{1,3}[A-Z]{0,4}\.[ \t])"    # (c) not the next numbered unit
    r".){0,200}?"
)
UNIT_PATTERN = re.compile(
    rf"^(?:\d+\[)?(\d{{1,3}}[A-Z]{{0,4}})\.[ \t]+({_TITLE_BODY})[ \t]*[{_BODY_DASH}]",
    re.MULTILINE | re.DOTALL,
)

# The leading "N[" insertion marker, stripped off a unit's body text so the
# stored chunk starts cleanly at the article/section number.
_LEADING_MARKER = re.compile(r"^\s*\d+\[")

# The Constitution's last article is 395 ("Repeals"); nothing is numbered
# higher (later insertions all use letter suffixes on lower numbers, e.g.
# 243ZT, 371J). So a Constitution "article" whose NUMERIC part exceeds 395 is
# never real -- it's a footnote superscript glued onto the number by the
# extractor ("7" + "31D" -> "731D"). See _normalize_constitution_number().
CONSTITUTION_MAX_ARTICLE = 395

# The end of the ARTICLES and the start of the SCHEDULES. After Article 395 the
# Constitution prints twelve Schedules (state lists, legislative lists, the
# anti-defection rules, ...) whose structure is NOT Part/Chapter/Article -- it's
# tables and numbered paragraphs that restart at 1 on every schedule. Fed to an
# article chunker they become hundreds of bogus "articles" (enclave boundary
# rows, schedule paragraphs) with nonsensical Part/Chapter context. So for the
# Constitution we stop chunking at the first standalone Schedule heading. The
# body form is "1[FIRST SCHEDULE" (no "THE"); in-text references are title-case
# ("...the First Schedule..."), and the trailing \s*$ keeps this matching only a
# heading line, never a sentence. (Schedules deserve their own structure-aware
# handling; that's a separate, not-yet-built step -- see module docstring.)
_SCHEDULE_BOUNDARY = re.compile(
    r"^(?:\d+\[)?(?:THE\s+)?"
    r"(?:FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH|EIGHTH|NINTH|TENTH|ELEVENTH|TWELFTH)"
    r"\s+SCHEDULE\s*$",
    re.MULTILINE,
)


def _base_number(number: str) -> int:
    """The integer part of a unit number, ignoring any letter suffix:
    "243" -> 243, "243ZG" -> 243, "21A" -> 21. Used to enforce that real
    article numbers only ever move FORWARD (see chunk_document)."""
    m = re.match(r"\d+", number)
    return int(m.group(0)) if m else -1


# ---------------------------------------------------------------
# Small text helpers
# ---------------------------------------------------------------

def _clean_title(raw: str | None) -> str | None:
    """Collapse internal whitespace/newlines and trim markup from a captured
    title, so "Name and territory\nof the Union." becomes "Name and territory
    of the Union", "1[TEMPORARY, TRANSITIONAL AND" becomes "TEMPORARY,
    TRANSITIONAL AND", and "[Saving of laws ... activities.]" becomes "Saving
    of laws ... activities"."""
    if not raw:
        return None
    title = re.sub(r"\s+", " ", raw).strip()
    title = re.sub(r"^\d+\[", "", title)   # drop a leading "N[" amendment marker
    title = title.strip("[]").strip()      # drop wrapping insertion brackets
    title = title.rstrip(".—–- ").strip()
    return title or None


def _normalize_constitution_number(number: str) -> str:
    """Repair a Constitution article number that the extractor garbled by
    gluing a leading footnote superscript onto it ("7" + "31D" -> "731D").

    No real article's numeric part exceeds CONSTITUTION_MAX_ARTICLE, so while
    the number is out of range we peel one leading digit at a time (the glued
    superscript) until it lands back in range, then re-attach the letter
    suffix: "731D" -> "31D". A number already in range is returned unchanged.
    This only ever fires on impossible (>395) numbers, so it can't alter a
    genuine article."""
    m = re.match(r"(\d+)([A-Z]*)$", number)
    if not m:
        return number
    digits, letters = m.group(1), m.group(2)
    while int(digits) > CONSTITUTION_MAX_ARTICLE and len(digits) > 1:
        digits = digits[1:]
    return str(int(digits)) + letters


def _is_repealed_stub(title: str | None) -> bool:
    """True if a unit heading is really an OMITTED/REPEALED stub, not live law.

    When a provision is repealed, the text keeps a placeholder printed as the
    number, then its former title wrapped in SQUARE BRACKETS, then the repeal
    note, e.g.:
        "242. [Coorg.].—Omitted by the Constitution (Seventh Amendment) ..."
        "31. [Compulsory acquisition of property.].—Rep. by the Constitution
         (Forty-fourth Amendment) Act, 1978 ..."
    The bracketed title is the reliable structural signal: a LIVE provision's
    title is never bracketed (the amendment-INSERTION marker "N[" sits BEFORE
    the number -- "1[257A." -- never after the dot). group(2) here is the title
    only, so a leading "[" means "repealed stub".

    These carry no current legal text, so they are skipped -- and, just as
    importantly, they must NOT advance the article-number high-water mark. One
    of them, the Article 132A stub, is printed OUT of numeric position (as a
    footnote under Article 32). Counted as an article it shoves the high-water
    mark to 132 and every real article from 33..132 (including 51A) then looks
    like a "backward" jump and is wrongly dropped. Skipping the stub outright
    removes both the bogus chunk and the poison."""
    return bool(title and title.lstrip().startswith("["))


def _looks_like_heading(line: str) -> bool:
    """True if a line is itself a structural marker (so it should NOT be
    mistaken for a Part's subject line). Tolerates a leading "N[" amendment
    marker, e.g. "1[PART IX"."""
    s = re.sub(r"^\s*\d+\[", "", line.strip())
    return bool(
        re.match(r"^PART\s+" + _ROMAN, s)
        or re.match(r"^CHAPTER\s+" + _ROMAN, s)
        or re.match(r"^\d+[A-Z]*\.", s)
    )


def _title_after_part(text: str, part_match: re.Match) -> str | None:
    """A Part's subject is printed on the line(s) AFTER "PART V", e.g.
        PART V
        THE UNION
    Return that subject (skipping blank lines), or None if the next
    meaningful line is itself another heading (some Parts jump straight
    into a Chapter)."""
    rest_lines = text[part_match.end():].split("\n")
    for line in rest_lines:
        s = line.strip()
        if not s:
            continue
        if _looks_like_heading(s):
            return None
        return _clean_title(s)
    return None


def _structural_index(text: str) -> tuple[list[tuple[int, str, str | None]],
                                          list[tuple[int, str, str | None]]]:
    """Build sorted lists of (offset, numeral, title) for every PART and
    every CHAPTER in `text`. Computed ONCE, then reused for every unit
    (instead of re-scanning the whole prefix per unit, which was O(n^2))."""
    parts = [
        (m.start(), m.group(1), _title_after_part(text, m))
        for m in PART_PATTERN.finditer(text)
    ]
    chapters = [
        (m.start(), m.group(1), _clean_title(m.group(2)))
        for m in CHAPTER_PATTERN.finditer(text)
    ]
    return parts, chapters


def _context_before(
    offset: int,
    parts: list[tuple[int, str, str | None]],
    chapters: list[tuple[int, str, str | None]],
):
    """Return the (part, part_title, chapter, chapter_title) in force at
    `offset` -- i.e. the most recent Part before it, and the most recent
    Chapter before it THAT ALSO comes after that Part.

    The "after that Part" clause is what stops a chapter from an earlier
    Part leaking onto the articles of a later, chapter-less Part."""
    part = part_title = chapter = chapter_title = None
    part_offset = -1

    for off, numeral, title in parts:
        if off < offset:
            part, part_title, part_offset = numeral, title, off
        else:
            break

    for off, numeral, title in chapters:
        if off < offset and off > part_offset:
            chapter, chapter_title = numeral, title
        elif off >= offset:
            break

    return part, part_title, chapter, chapter_title


def detect_body_start_page(pages_cleaned_text: list[str]) -> int:
    """Figure out which page the REAL legal body starts on, so we skip front
    matter (title page, abbreviations, the "arrangement of articles/sections"
    table of contents).

    Insight grounded in the real extraction: a TABLE OF CONTENTS lists units
    as a bare number followed by its title with NO body dash
    ("52.\\nThe President of India."), whereas the BODY prints the unit with a
    body dash before the text ("52. The President of India.—There shall...").
    So the first page carrying a *body-style* unit heading (number + title +
    dash) is our body start. This is far more reliable than "the 2nd page
    with any marker", which for the Constitution landed 25 pages deep inside
    the contents.

    Returns the 0-based page index where body content starts, or 0 if no
    body-style heading is found anywhere (don't skip anything).

    NOTE: an Act whose "ARRANGEMENT OF SECTIONS" contents also uses em dashes
    could trip this. We can only directly verify the Constitution today;
    revisit for the Acts once one is processed end to end.
    """
    for i, page_text in enumerate(pages_cleaned_text):
        if UNIT_PATTERN.search(page_text):
            return i
    return 0


def _make_chunk_id(document_id: str, *parts: str) -> str:
    """Build a DETERMINISTIC chunk id -- same input always yields the same id,
    which is what makes re-ingestion idempotent (upsert, not duplicate).

    Example: _make_chunk_id("bns_2023", "IV", "103", "0")
             -> "bns_2023__IV__103__0"
    Empty parts are dropped so a chapter-less Constitution article doesn't
    produce "__" gaps."""
    safe = [document_id] + [p.replace(" ", "_") for p in parts if p]
    return "__".join(safe)


def _build_context_header(md: ChunkMetadata) -> str:
    """Compose the human-readable structural header that gets prepended into
    the chunk TEXT (not just the metadata). Two reasons this lives in the text:
      1. The vector search embeds the text, so "Part V The Union / Chapter I
         The Executive / Article 52 The President of India" becomes searchable.
      2. After a large unit is size-split, sub-chunks 2..n keep their identity
         instead of being anonymous fragments.
    """
    lines: list[str] = []
    if md.part:
        # md.part already carries the "Part " prefix; only the subject is added.
        lines.append(md.part + (f" — {md.part_title}" if md.part_title else ""))
    if md.chapter:
        lines.append(md.chapter + (f" — {md.chapter_title}" if md.chapter_title else ""))
    if md.article:
        lines.append(f"Article {md.article}" + (f" — {md.article_title}" if md.article_title else ""))
    if md.section:
        lines.append(f"Section {md.section}" + (f" — {md.section_title}" if md.section_title else ""))
    return "\n".join(lines)


def split_by_size(text: str, max_chars: int) -> list[str]:
    """Fallback splitter for a single unit whose text exceeds max_chars
    (e.g. BNS Section 2, the huge definitions section).

    Per the plan: structure-aware chunking FIRST, size limit only as a
    FALLBACK. Splits on paragraph breaks where possible so we don't cut a
    sentence in half, hard-cutting only a paragraph that is itself too long."""
    if max_chars < 1:
        max_chars = 1
    if len(text) <= max_chars:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if current and len(current) + len(para) + 2 > max_chars:
            chunks.append(current.strip())
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para

        # A single paragraph longer than max_chars has no smaller natural
        # boundary -- hard-cut it.
        while len(current) > max_chars:
            chunks.append(current[:max_chars].strip())
            current = current[max_chars:]

    if current.strip():
        chunks.append(current.strip())

    return chunks


def chunk_document(document: Document, pages_cleaned_text: list[str]) -> list[Chunk]:
    """THE main function. Takes a Document (metadata about the source PDF) plus
    its cleaned, page-by-page text, and returns a list of fully-formed Chunk
    objects -- every one carrying complete metadata AND a structural header in
    its text.

    Steps:
      1. Skip front-matter pages (detect_body_start_page).
      2. Join the remaining pages, remembering each page's char offset so a
         chunk can report the real PDF page it came from.
      3. For the Constitution, cut off the Schedules (a non-article structure).
      4. Index every Part/Chapter (with subjects) once.
      5. Take each UNIT_PATTERN match, but keep only real units -- drop
         backward-jumping numbers (footnotes / schedule paragraphs). Each kept
         unit's text runs to the next kept unit (or end of the article body).
      6. Attach the in-force Part/Chapter to each unit.
      7. Label the unit number as an ARTICLE (Constitution) or SECTION (Acts)
         based on the document type.
      8. Size-split the unit's text if needed, reserving room for the header.
    """

    start_index = detect_body_start_page(pages_cleaned_text)
    body_pages = pages_cleaned_text[start_index:]

    # Build the joined text and record where each page begins, so we can map
    # any character offset back to its original 1-based PDF page number.
    joined_text = ""
    page_start_offsets: list[tuple[int, int]] = []  # (char_offset, page_number)
    for i, page_text in enumerate(body_pages):
        real_page_number = start_index + i + 1
        page_start_offsets.append((len(joined_text), real_page_number))
        joined_text += page_text + "\n"

    def page_number_for_offset(offset: int) -> int:
        page_number = page_start_offsets[0][1] if page_start_offsets else 1
        for page_offset, page_num in page_start_offsets:
            if page_offset <= offset:
                page_number = page_num
            else:
                break
        return page_number

    # Is this the Constitution (numbers are Articles) or an Act (Sections)?
    doc_type = getattr(document.document_type, "value", document.document_type)
    is_constitution = doc_type == DocumentType.CONSTITUTION.value

    # For the Constitution, cut the SCHEDULES off the end: everything from the
    # first standalone Schedule heading onward is tables and numbered paragraphs,
    # not articles, and would otherwise be mangled into hundreds of bogus units
    # (state lists, enclave boundary rows) carrying nonsensical Part/Chapter
    # context. Article 395 is the last real article; the Schedules follow it.
    if is_constitution:
        boundary = _SCHEDULE_BOUNDARY.search(joined_text)
        if boundary:
            joined_text = joined_text[: boundary.start()]

    parts_index, chapters_index = _structural_index(joined_text)
    raw_matches = list(UNIT_PATTERN.finditer(joined_text))

    if not raw_matches:
        # No recognizable structure -- fail loudly rather than silently
        # returning nothing, so the problem is noticed during ingestion.
        raise ValueError(
            f"No numbered Article/Section headings found in document "
            f"'{document.document_id}'. Check that its structure matches our "
            f"confirmed patterns, or that detect_body_start_page() isn't "
            f"skipping too much."
        )

    # Keep only the matches that are REAL, live units. Two things get dropped:
    #
    #   * OMITTED/REPEALED stubs (title in square brackets, "242. [Coorg.].—
    #     Omitted by ...") -- no current legal text, and one of them (the
    #     Article 132A stub, printed out of position under Article 32) would
    #     otherwise poison the forward-only check below. See _is_repealed_stub().
    #
    #   * BACKWARD-jumping numbers (Constitution only). Real article numbers
    #     only ever move FORWARD (1, 2, 3, ... 395; letter-suffixed insertions
    #     keep the same base, e.g. 243, 243A, 243B). A match whose base number
    #     jumps BACKWARDS is never a real article -- it's a bottom-of-page
    #     footnote ("3. Ins. by the Constitution ... Act, 2019 ...") or a
    #     schedule paragraph reusing a low number.
    #
    # A dropped region just stays inside the preceding real unit's text (see
    # unit_end below), so no genuine article text is lost -- a skipped footnote
    # or stub lingers only as minor inline noise on the previous chunk.
    if is_constitution:
        accepted: list[tuple[re.Match, str]] = []
        max_base = -1
        for m in raw_matches:
            if _is_repealed_stub(m.group(2)):
                continue
            num = _normalize_constitution_number(m.group(1))
            base = _base_number(num)
            if base < max_base:
                continue
            max_base = base
            accepted.append((m, num))
    else:
        accepted = [
            (m, m.group(1)) for m in raw_matches if not _is_repealed_stub(m.group(2))
        ]

    chunks: list[Chunk] = []
    seen_ids: set[str] = set()

    for idx, (match, number) in enumerate(accepted):
        unit_start = match.start()
        unit_end = (
            accepted[idx + 1][0].start()
            if idx + 1 < len(accepted)
            else len(joined_text)
        )
        unit_text = joined_text[unit_start:unit_end].strip()
        # Drop a leading "N[" amendment-insertion marker so the chunk body
        # starts cleanly at the article/section number.
        unit_text = _LEADING_MARKER.sub("", unit_text, count=1).strip()
        unit_page = page_number_for_offset(unit_start)

        title = _clean_title(match.group(2))
        part, part_title, chapter, chapter_title = _context_before(
            unit_start, parts_index, chapters_index
        )

        if is_constitution:
            article, article_title, section, section_title = number, title, None, None
        else:
            article, article_title, section, section_title = None, None, number, title

        # Build the header once (identical across this unit's sub-chunks), then
        # size-split the BODY so header + body stays within MAX_CHUNK_CHARS.
        base_metadata = dict(
            document_id=document.document_id,
            document_title=document.title,
            document_type=document.document_type,
            legal_status=document.legal_status,
            part=f"Part {part}" if part else None,
            part_title=part_title,
            article=article,
            article_title=article_title,
            chapter=f"Chapter {chapter}" if chapter else None,
            chapter_title=chapter_title,
            section=section,
            section_title=section_title,
            page=unit_page,
            source=document.source,
            source_url=document.source_url,
        )
        header = _build_context_header(ChunkMetadata(**base_metadata))
        body_budget = settings.MAX_CHUNK_CHARS - len(header) - 2

        for sub_idx, sub_text in enumerate(split_by_size(unit_text, body_budget)):
            chunk_text = f"{header}\n\n{sub_text}" if header else sub_text
            chunk_id = _make_chunk_id(
                document.document_id,
                part or "",
                chapter or "",
                number,
                str(sub_idx),
            )
            # Guard the idempotency contract: if the same (part/chapter/number)
            # legitimately recurs (e.g. a repealed number reused, or a garbled
            # duplicate), disambiguate so one chunk never silently overwrites
            # another in Qdrant. Stays deterministic for a given input.
            if chunk_id in seen_ids:
                chunk_id = f"{chunk_id}__dup{len(seen_ids)}"
            seen_ids.add(chunk_id)
            chunks.append(
                Chunk(id=chunk_id, text=chunk_text, metadata=ChunkMetadata(**base_metadata))
            )

    return chunks

