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

# The end of numbered ARTICLES/SECTIONS and the start of SCHEDULES/FORMS.
# Originally Constitution-only; confirmed needed for the Acts too once tested
# against a real CrPC file end to end. CrPC's Second Schedule prints 118
# "FORM NO. N.—Title" entries (warrant/summons templates) right after the
# last real Section (484). Nothing in UNIT_PATTERN matches "FORM NO. 1"
# (it starts with the word FORM, not a digit), so without this boundary all
# 118 Form entries -- and the whole Schedule -- get silently absorbed into
# Section 484's chunk: its section_title gets corrupted to "Repeal and
# savings. THE FIRST SCHEDULE" and its text balloons with mislabeled Form
# text. VERIFIED against the real crpc.pdf.
#
# Two heading shapes both need to trigger this boundary:
#   Constitution style: ordinal + "SCHEDULE" ALONE on its own line, subject
#     (if any) on the NEXT line -- "FIRST SCHEDULE" then a blank/next line.
#   Act style: ordinal + "SCHEDULE" WITH an inline subtitle on the SAME
#     line -- "THE FIRST SCHEDULE.–CLASSIFICATION OF OFFENCES." (CrPC).
# `\b.*$` (instead of `\s*$`) accepts an optional inline subtitle while
# still matching a bare heading line with nothing after it.
#
# Schedules deserve their own structure-aware handling eventually; until
# then, cutting the document off here is far better than silently
# mislabeling Schedule/Form content as the last real Section.
_SCHEDULE_BOUNDARY = re.compile(
    r"^(?:\d+\[)?(?:THE\s+)?"
    r"(?:FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH|EIGHTH|NINTH|TENTH|ELEVENTH|TWELFTH)"
    r"\s+SCHEDULE\b.*$",
    re.MULTILINE,
)

# Some Acts print forms without ever heading them "SCHEDULE" first (or the
# heading is worded differently than the twelve ordinals above cover) --
# this catches the form listing itself as a fallback boundary.
_FORM_BOUNDARY = re.compile(r"^(?:\d+\[)?FORM\s+NO\.?\s*\d+", re.MULTILINE)


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


# Any numbered line at all, dash or not -- deliberately BROADER than
# UNIT_PATTERN. Used only to measure density (see detect_body_start_page),
# never to identify a real unit on its own.
_NUMBERED_LINE = re.compile(r"^\s*(?:\d+\[)?\d{1,3}[A-Z]{0,4}\.\s", re.MULTILINE)

# A page with this many or more numbered-looking lines is almost certainly
# still inside a table of contents ("Arrangement of Sections"), which lists
# dozens of entries per page. VERIFIED against 4 real PDFs (not assumed):
# true body-start pages measured 3-16 numbered lines (IPC's early "General
# Explanations" sections are unusually dense, short definitional entries --
# a naive low threshold like 8 wrongly rejected IPC's real page 14); ToC
# pages measured 20-47 in every document tested. 18 sits cleanly in the gap.
_TOC_DENSITY_THRESHOLD = 18


def detect_body_start_page(pages_cleaned_text: list[str]) -> int:
    """Figure out which page the REAL legal body starts on, so we skip front
    matter (title page, abbreviations, the "arrangement of articles/sections"
    table of contents).

    Two signals are combined, because neither is reliable alone (both proven
    by testing against real PDFs, not assumed):

      1. A body-style unit heading (number + title + dash) must be present
         on the page -- a ToC lists units as a bare number + title with NO
         dash ("52.\\nThe President of India."), while the body prints
         "52. The President of India.—There shall...".

      2. The page must NOT be numbered-line DENSE (see _TOC_DENSITY_THRESHOLD).
         Signal 1 alone is not enough: BNSS and CrPC's real "Arrangement of
         Sections" tables of contents include lettered sub-groupings
         ("B.—Warrant of arrest") immediately after a numbered entry, and our
         title-wrapping logic accidentally accepts that letter's dash as a
         body separator -- e.g. "71. Service of summons on witness. \\nB.—"
         looks exactly like a real body-style match. VERIFIED: this made
         detect_body_start_page land on page 5 of BNSS (18 pages too early)
         and page 2 of CrPC, both still deep inside the ToC, producing dozens
         of chunks built from ToC fragments mislabeled as real Sections.
         Requiring LOW density on top of signal 1 rules this out: the false
         match's page (18-44 numbered lines, still ToC-dense) is rejected,
         and scanning continues until a page that is BOTH a real match AND
         sparse (0-4 numbered lines) is found -- which VERIFIED lands
         correctly on BNS page 16, BNSS page 18, and CrPC page 21.

    Returns the 0-based page index where body content starts, or 0 if no
    such page is found anywhere (don't skip anything).
    """
    for i, page_text in enumerate(pages_cleaned_text):
        if not UNIT_PATTERN.search(page_text):
            continue
        if len(_NUMBERED_LINE.findall(page_text)) >= _TOC_DENSITY_THRESHOLD:
            continue
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


# A top-level lettered sub-clause, e.g. "(a) ", "(b) ", ... "(z) ", possibly
# continuing "(za) ", "(zb) " past z for lists with more than 26 items
# (defensive -- not verified against a real Act needing this; every real
# Definitions section checked so far stopped at 'z').
#
# Deliberately does NOT match arbitrary two-letter combinations like "(ii)"
# or "(iii)" -- those are lowercase ROMAN NUMERALS marking a nested
# sub-point INSIDE one real clause (VERIFIED on real BNSS Section 2: clause
# "(j) 'High Court' means—" contains its own internal "(i)... (ii)..."
# sub-cases), not a new top-level clause. Real continuation past 'z' in
# Indian legal drafting always starts with the literal letter 'z' itself
# ("za", "zb", ...), so restricting two-letter matches to that shape
# excludes roman numerals at the regex level, rather than relying on
# sequence validation alone to catch them.
_LETTERED_CLAUSE = re.compile(r"^\(([a-z]|z[a-z])\)\s", re.MULTILINE)

# A top-level NUMBERED sub-clause, e.g. "(1) ", "(2) ", ... VERIFIED needed
# separately from the lettered pattern: the Constitution's real Article 366
# ("Definitions") enumerates with numbers, not letters -- "(1) 'agricultural
# income' means...", "(2) 'an Anglo-Indian' means...". Deliberately NOT
# applied everywhere the way the lettered pattern is (see
# split_by_numbered_clauses' docstring for why).
_NUMBERED_CLAUSE = re.compile(r"^\((\d{1,3})\)\s", re.MULTILINE)

# A unit's title suggesting it's a Definitions-style list, not ordinary
# continuous prose. Checked case-insensitively.
_DEFINITIONS_TITLE = re.compile(r"definition", re.IGNORECASE)


def _letter_index(letters: str) -> int:
    """'a'->0, 'b'->1, ..., 'z'->25, 'za'->26, 'zb'->27, ... -- turns a
    clause letter into a plain integer so consecutive clauses can be
    compared with simple +1 arithmetic."""
    if len(letters) == 1:
        return ord(letters) - ord("a")
    return 26 + (ord(letters[1]) - ord("a"))


def _find_top_level_clauses(text: str) -> list[re.Match]:
    """Walk every "(letter)" match in TEXT ORDER, keeping only ones that
    move FORWARD through the alphabet from the last accepted one --
    tolerating GAPS, not requiring the exact next letter.

    Gaps are real and legitimate: VERIFIED on the real Constitution,
    Article 19's freedoms list goes (a), (b), (c), (d), (e), (g) -- letter
    (f) ("to acquire, hold and dispose of property") was repealed by the
    44th Amendment in 1978 and no longer appears. Requiring the exact next
    letter would reject (g) (since it's not the expected "(f)") and
    everything after it, losing clause-based splitting for the rest of the
    list. Requiring only FORWARD movement (idx > last accepted idx, not
    idx == exactly one more) correctly accepts (g) as the next real clause
    after the gap.
    """
    accepted: list[re.Match] = []
    last_idx = -1
    for m in _LETTERED_CLAUSE.finditer(text):
        idx = _letter_index(m.group(1))
        if idx > last_idx:
            accepted.append(m)
            last_idx = idx
    return accepted


def _find_top_level_numbered_clauses(text: str) -> list[re.Match]:
    """Same forward-only-tolerating-gaps logic as _find_top_level_clauses,
    but for NUMBERED sub-clauses (1), (2), (3), ... A numbered sub-point
    nested inside one clause won't accidentally match here since it would
    need to be LESS than the last accepted number, not just a different
    one (mirrors how nested lettered sub-points are excluded)."""
    accepted: list[re.Match] = []
    last_num = 0
    for m in _NUMBERED_CLAUSE.finditer(text):
        n = int(m.group(1))
        if n > last_num:
            accepted.append(m)
            last_num = n
    return accepted


def _pack_clauses(
    text: str, clause_matches: list[re.Match], max_chars: int, overlap_chars: int | None
) -> list[str]:
    """Shared packing logic for both lettered and numbered clause
    splitting: slice TEXT at each accepted clause boundary, merge the
    lead-in before the first real clause into it, then greedily pack whole
    clauses together up to max_chars -- never cutting INSIDE a single
    clause unless that one clause alone exceeds max_chars (falls back to
    split_by_size() for just that one clause)."""
    if overlap_chars is None:
        overlap_chars = int(max_chars * 0.2)
    if overlap_chars > max_chars * 0.2:
        overlap_chars = int(max_chars * 0.2)

    boundaries = [0] + [m.start() for m in clause_matches] + [len(text)]
    pieces_raw = [
        text[boundaries[i]:boundaries[i + 1]].strip()
        for i in range(len(boundaries) - 1)
    ]
    lead_in, clauses = pieces_raw[0], pieces_raw[1:]
    if lead_in:
        clauses[0] = f"{lead_in}\n{clauses[0]}"

    packed: list[str] = []
    current = ""
    for clause in clauses:
        if len(clause) > max_chars:
            if current.strip():
                packed.append(current.strip())
            packed.extend(split_by_size(clause, max_chars, overlap_chars))
            current = ""
            continue
        if current and len(current) + len(clause) + 1 > max_chars:
            packed.append(current.strip())
            current = clause
        else:
            current = f"{current}\n{clause}" if current else clause

    if current.strip():
        packed.append(current.strip())

    return packed


# Dedicated budget for PACKING lettered clauses together, deliberately much
# smaller than MAX_CHUNK_CHARS. VERIFIED against real BNSS Section 2: real
# individual clause lengths ranged 55-552 chars (avg 230). At this budget,
# almost every real clause fits as its OWN topically-focused chunk (the
# longest one, 552 chars, still fits with margin); only the shortest
# clauses (under ~100 chars) get paired with a neighbor. Reusing the large
# prose body_budget (~1450 chars) here would defeat the whole point of
# clause-splitting -- it would still pack 6-8 unrelated definitions into
# one chunk, just without ever cutting one in half.
_CLAUSE_CHUNK_BUDGET = 600


def split_by_size(text: str, max_chars: int, overlap_chars: int | None = None) -> list[str]:
    """Fallback splitter for a single unit whose text exceeds max_chars
    (e.g. BNS Section 2, the huge definitions section).

    Per the plan: structure-aware chunking FIRST, size limit only as a
    FALLBACK. Splits on paragraph breaks where possible so we don't cut a
    sentence in half, hard-cutting only a paragraph that is itself too long.

    OVERLAP, restored: an earlier version of this function had no overlap
    between forced sub-chunks, then gained it (verified, tested against real
    stranded-clause cases), then lost it again in a later rewrite that added
    the header-budget logic -- unclear whether that was deliberate. Splitting
    BETWEEN two different sections is a real legal boundary and needs no
    overlap; splitting ONE section into pieces because it's too long is an
    artificial cut, and a clause reference right at that cut point (e.g.
    "clause (a) above") can end up stranded in only one piece. Overlap
    repeats a small amount of trailing text from one chunk at the start of
    the next so nothing is orphaned.

    overlap_chars defaults to 20% of max_chars if not given, and is capped
    at 20% even if passed larger -- confirmed by testing that overlap set
    too close to max_chars can silently degrade to near-zero real overlap.
    """
    if max_chars < 1:
        max_chars = 1
    if overlap_chars is None:
        overlap_chars = int(max_chars * 0.2)
    if overlap_chars > max_chars * 0.2:
        overlap_chars = int(max_chars * 0.2)

    if len(text) <= max_chars:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if current and len(current) + len(para) + 2 > max_chars:
            finished = current.strip()
            if finished:
                chunks.append(finished)
            # Seed the next chunk with the tail of the one just closed, so
            # a clause/reference right at this artificial cut isn't stranded.
            overlap_text = current[-overlap_chars:]
            current = f"{overlap_text}\n\n{para}"
        else:
            current = f"{current}\n\n{para}" if current else para

        # A single paragraph longer than max_chars has no smaller natural
        # boundary -- hard-cut it, carrying overlap forward here too.
        while len(current) > max_chars:
            piece = current[:max_chars].strip()
            # A cut landing inside a run of whitespace can strip down to an
            # empty piece -- don't store a useless empty chunk.
            if piece:
                chunks.append(piece)
            raw_overlap = current[max_chars - overlap_chars:max_chars]
            overlap_text = raw_overlap.strip()
            current = overlap_text + current[max_chars:]

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

    # Cut off SCHEDULES/FORMS for EVERY document type, not just the
    # Constitution: everything from the first Schedule/Form boundary onward
    # is tables/templates, not numbered Articles or Sections, and would
    # otherwise get mangled into (or silently absorbed by) the last real
    # unit. VERIFIED on the real crpc.pdf: without this, CrPC's Second
    # Schedule (118 "FORM NO. N.—..." entries) got absorbed into Section
    # 484's chunk, corrupting its section_title to "Repeal and savings. THE
    # FIRST SCHEDULE" and filling its text with mislabeled Form content.
    boundary_positions = [
        m.start() for m in (
            _SCHEDULE_BOUNDARY.search(joined_text),
            _FORM_BOUNDARY.search(joined_text),
        ) if m
    ]
    if boundary_positions:
        joined_text = joined_text[: min(boundary_positions)]

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
    #   * BACKWARD-jumping numbers, now checked for EVERY document type, not
    #     just the Constitution. Real numbers only ever move FORWARD (1, 2,
    #     3, ...; letter-suffixed insertions keep the same base, e.g. 41,
    #     41A, 41B). A match whose base number jumps BACKWARDS is never a
    #     real unit -- it's a bottom-of-page footnote, a schedule paragraph
    #     reusing a low number, or (VERIFIED on the real crpc.pdf) a State
    #     Amendment annexure re-quoting an old section's original text
    #     verbatim near the end of the document (a genuine "44. Amendment of
    #     Act 45 of 1860.—..." reappeared, positioned AFTER Section 484, deep
    #     inside a state-amendment table -- this filter now correctly drops
    #     it as backward, instead of it becoming a bogus final chunk).
    #
    #     This is only safe to apply broadly because detect_body_start_page()
    #     now excludes the table of contents for Acts too (see its
    #     docstring) -- applying this filter BEFORE that fix was tried and
    #     found unsafe: a ToC's coincidental false matches are themselves
    #     numerically INCREASING (they list entries in order), so real body
    #     content starting back at Section 1 would have been wrongly
    #     rejected as "backward" relative to them.
    #
    # A dropped region just stays inside the preceding real unit's text (see
    # unit_end below), so no genuine article/section text is lost -- a
    # skipped footnote, stub, or annex re-quote lingers only as minor inline
    # noise on the previous chunk.
    accepted: list[tuple[re.Match, str]] = []
    max_base = -1
    for m in raw_matches:
        if _is_repealed_stub(m.group(2)):
            continue
        num = _normalize_constitution_number(m.group(1)) if is_constitution else m.group(1)
        base = _base_number(num)
        if base < max_base:
            continue
        max_base = base
        accepted.append((m, num))

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
        clause_budget = min(body_budget, _CLAUSE_CHUNK_BUDGET)

        # Decide lettered vs numbered vs neither by comparing how many REAL
        # top-level clauses each pattern actually finds, rather than always
        # trying lettered first unconditionally.
        #
        # BUG FOUND AND FIXED: the original design tried lettered clauses
        # first, always -- reasoning that lowercase-letter enumeration
        # "essentially never" appears as just steps of one coherent idea.
        # VERIFIED WRONG against the real Constitution: Article 366
        # ("Definitions") is primarily a NUMBERED list of 20 top-level
        # definitions -- (1), (2), (3), ... -- but ONE of those numbered
        # definitions, (29A) (the well-known "tax on deemed sales of
        # goods" clause), itself contains its OWN nested lettered
        # sub-list, (a) through (e). Trying lettered first found those 6
        # nested letters, wrongly treated them as the article's PRIMARY
        # structure, and crushed all 20 real top-level definitions into
        # one oversized "lead-in" blob that then got crudely hard-cut --
        # worse than plain size-based splitting would have been, since it
        # lost real clause alignment for the actual definitions AND
        # mis-split the nested (29A) sub-list out of its own context.
        #
        # Fix: compute both, use whichever finds MORE real top-level
        # clauses (ties favor lettered, preserving the original
        # reasoning when neither pattern clearly dominates). VERIFIED:
        # Article 366 -> 20 numbered vs 6 lettered -> numbered wins,
        # correct. BNSS Section 2 -> 0 numbered vs 26 lettered -> lettered
        # wins, correct. A unit needs a minimum of 3 clauses under EITHER
        # pattern to be treated as clause-shaped at all -- otherwise it's
        # ordinary continuous prose and falls through to split_by_size.
        lettered_matches = _find_top_level_clauses(unit_text)
        numbered_matches = (
            _find_top_level_numbered_clauses(unit_text)
            if title and _DEFINITIONS_TITLE.search(title)
            else []
        )

        if len(numbered_matches) >= 3 and len(numbered_matches) > len(lettered_matches):
            sub_texts = _pack_clauses(unit_text, numbered_matches, clause_budget, None)
        elif len(lettered_matches) >= 3:
            sub_texts = _pack_clauses(unit_text, lettered_matches, clause_budget, None)
        else:
            sub_texts = None

        if sub_texts is None:
            sub_texts = split_by_size(unit_text, body_budget)

        for sub_idx, sub_text in enumerate(sub_texts):
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