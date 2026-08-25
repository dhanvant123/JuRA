"""
app/ingestion/text_cleaner.py

Step 3 of the pipeline: raw extracted text -> clean text.

PDF extraction (Step 2) often produces messy output:
    - words broken across a line break with a hyphen:
          "CONSTI-\nTUTION OF\nINDIA"
    - repeated headers/footers on every single page
          (e.g. "THE CONSTITUTION OF INDIA" printed at the top of every page)
    - inconsistent whitespace: multiple blank lines, trailing spaces

If we chunk on DIRTY text, the legal content itself gets corrupted --
e.g. "CONSTITUTION" might literally end up split into two separate
words in the stored chunk. This file's only job is to fix that BEFORE
chunker.py ever sees the text.

This file does NOT know about legal structure (Part/Article/Chapter/
Section) -- that's chunker.py's job. It only removes noise.
"""

import re


def fix_hyphenated_line_breaks(text: str) -> str:
    r"""
    Fixes words that got split across a line break with a hyphen, e.g.:
        "CONSTI-\nTUTION"  ->  "CONSTITUTION"

    re.sub(pattern, replacement, text) finds every match of `pattern`
    inside `text` and replaces it with `replacement`.

    Pattern breakdown: r"(\w+)-\n(\w+)"
        \w+   -> one or more "word characters" (letters/digits/underscore)
        -     -> a literal hyphen
        \n    -> a literal newline (line break)
        \w+   -> one or more word characters again

    The parentheses () create "capture groups" -- we can refer back to
    what they matched using \1 and \2 in the replacement string.
    So \1\2 means: "the text before the hyphen, directly followed by
    the text after the hyphen, with the hyphen and line break removed."
    """
    return re.sub(r"(\w+)-\n(\w+)", r"\1\2", text)


def collapse_excess_whitespace(text: str) -> str:
    r"""
    Collapses multiple blank lines and repeated spaces down to a single
    space/newline, so the text isn't full of unnecessary gaps.

    re.sub(r"\n{3,}", "\n\n", text):
        \n{3,} means "3 or more newlines in a row" -- collapsed down
        to just 2 (i.e. one blank line, which is fine to keep for
        readability, but not 5 blank lines in a row).

    re.sub(r"[ \t]+", " ", text):
        [ \t]+ means "one or more spaces or tabs in a row" -- collapsed
        down to a single space.
    """
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text


def remove_repeated_lines(pages_text: list[str]) -> list[str]:
    """
    Detects lines that appear on MOST pages (like a running header/footer,
    e.g. "THE CONSTITUTION OF INDIA" printed at the top of every page)
    and removes them.

    Why this needs ALL pages at once, not one page at a time:
    a single page can't tell you "this line repeats" -- you only know
    a line is a header/footer by comparing it across many pages.

    Args:
        pages_text: a list of raw page text strings (one per page).

    Returns:
        The same list, with repeated header/footer lines stripped out
        of every page.
    """

    # Step 1: count how many pages each distinct line appears on.
    line_counts: dict[str, int] = {}

    for page in pages_text:
        # .strip() removes leading/trailing whitespace so "Page 1 "
        # and "Page 1" count as the same line.
        # set(...) removes duplicate lines WITHIN one page, so a line
        # repeated twice on the same page only counts once for this page.
        lines_on_this_page = set(line.strip() for line in page.split("\n") if line.strip())

        for line in lines_on_this_page:
            line_counts[line] = line_counts.get(line, 0) + 1

    total_pages = len(pages_text)

    # A line appearing on more than 60% of pages is almost certainly
    # a header/footer, not actual legal content -- real legal text
    # (like a specific Article) won't repeat identically across most
    # of the document.
    threshold = max(2, int(total_pages * 0.6))

    repeated_lines = {line for line, count in line_counts.items() if count >= threshold}

    # Step 2: rebuild each page's text, skipping any line identified
    # as a repeated header/footer.
    cleaned_pages = []
    for page in pages_text:
        kept_lines = [
            line for line in page.split("\n") if line.strip() not in repeated_lines
        ]
        cleaned_pages.append("\n".join(kept_lines))

    return cleaned_pages


def strip_hindi_text(text: str) -> str:
    r"""
    Removes Hindi (Devanagari script) text, keeping only the English
    portions. Several of our source PDFs (e.g. the Constitution) are
    bilingual, printing Hindi and English side by side. Our embedding
    model is primarily trained on English, so leaving Hindi text mixed
    into chunks would produce poor-quality embeddings and pollute
    search results.

    How this works: every Unicode character has a numeric "code point".
    All Devanagari characters (the script Hindi is written in) fall
    within a specific, well-defined range: U+0900 to U+097F.
    "U+0900" is Unicode notation for the number 0x0900 (hexadecimal).

    re.sub(r"[\u0900-\u097F]+", "", text):
        [\u0900-\u097F] means "any single character whose code point
        falls in this range" -- i.e. any Devanagari character.
        The + means "one or more in a row".
        We replace any such run of Devanagari characters with "" --
        i.e. delete it entirely.

    KNOWN ISSUE THIS FIXES: deleting only the Devanagari characters
    left behind stranded English punctuation/numbers that were
    originally SURROUNDING the Hindi text, e.g. a Hindi date phrase
    would become a garbled leftover like "[1 , 2026 ]" if we only
    deleted the Hindi words themselves.

    The fix: after removing Devanagari characters, also collapse any
    resulting run of "orphaned" punctuation -- a comma or bracket that
    now has nothing meaningful next to it because its Hindi neighbour
    is gone. We do this by collapsing repeated spaces/commas that are
    a direct symptom of the deletion, then letting the caller's later
    whitespace-collapsing step finish the cleanup.
    """
    text = re.sub(r"[\u0900-\u097F]+", "", text)

    # Clean up common leftover patterns after Hindi removal:
    # a comma with nothing before it but whitespace, e.g. "[1 , 2026"
    text = re.sub(r"\s+,", ",", text)
    # multiple spaces left behind where Hindi words used to sit
    text = re.sub(r"[ \t]{2,}", " ", text)

    return text


def strip_amendment_annotations(text: str) -> str:
    r"""
    Removes inline amendment-history markup found in OLDER Acts like the
    IPC (1860) and CrPC (1973). Unlike the brand-new 2023 Acts (BNS,
    BNSS, BSA), these older documents have decades of amendments noted
    directly inside the legal text using bracket/asterisk/superscript-
    number conventions, e.g.:

        "shall 3*[extend to the whole of India 4*[except the State of
        Jammu and Kashmir]]"

    Left in place, this markup would corrupt the actual legal text --
    e.g. a chunk might read "...extend to the whole of India 4*[except
    the State of Jammu..." instead of clean, readable legal text.

    This is a BEST-EFFORT cleaner. We have not yet been able to fully
    inspect a real IPC/CrPC PDF page by page (fetch attempts timed
    out), so this pattern is based on secondary evidence (search
    snippets) rather than direct inspection. Expect to revisit and
    refine this once we can process a real IPC/CrPC file end to end.

    Pattern breakdown: r"\d+\*\[([^\[\]]*)\]"
        \d+     -> one or more digits (the footnote/amendment number)
        \*      -> a literal asterisk (escaped with \ because * is a
                    special regex character meaning "repeat")
        \[      -> a literal opening square bracket (escaped, since [
                    normally starts a character class in regex)
        ([^\[\]]*)  -> a capture group: any characters that are NOT
                    another [ or ] -- i.e. the actual text INSIDE the
                    brackets, which we want to KEEP
        \]      -> a literal closing square bracket

    Replacement: r"\1" means "keep just what was inside the brackets,
    drop the digit/asterisk/bracket markup around it."

    Note: this only handles ONE level of brackets. The real example
    above has NESTED brackets ("[...4*[...]]"), which this simple
    pattern won't fully untangle. We run it multiple times (see the
    while loop) to catch nested cases one layer at a time.
    """
    # Keep applying the pattern until no more matches are found --
    # this handles nested brackets by peeling off one layer per pass.
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"\d+\*\[([^\[\]]*)\]", r"\1", text)

    # Also strip standalone footnote reference markers like a bare
    # trailing digit+asterisk with no brackets, e.g. "India.5*"
    text = re.sub(r"\d+\*", "", text)

    return text


def clean_text(text: str) -> str:
    """
    The main entry point for cleaning a SINGLE page's text.
    Runs the per-page fixes in order.

    Order matters here: we strip Hindi and amendment annotations
    BEFORE fixing hyphenation/whitespace, so that removing those
    chunks of text doesn't leave behind broken spacing that the
    later steps then have to clean up too.

    Note: remove_repeated_lines() is deliberately NOT called here,
    because it needs ALL pages at once to detect what's repeated.
    It's called separately, on the full list of pages, by
    ingestion_service.py.

    Note: skipping front-matter pages (title page, abbreviations list,
    "ARRANGEMENT OF SECTIONS" table of contents) is NOT done here --
    that's a decision about WHICH PAGES to process at all, which
    belongs in chunker.py / ingestion_service.py, not in this
    per-page text cleaner.
    """
    text = strip_hindi_text(text)
    text = strip_amendment_annotations(text)
    text = fix_hyphenated_line_breaks(text)
    text = collapse_excess_whitespace(text)
    return text.strip()