"""
tests/test_cleaner.py

Unit tests for text_cleaner.py's individual functions, using small
synthetic strings that reproduce specific real patterns found in the
actual PDFs -- not full real-PDF regression tests (that's what
test_chunker.py's fixtures already exercise indirectly, since chunker
tests run on text that's already been through clean_text()).

Run with: pytest tests/test_cleaner.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingestion.text_cleaner import (
    fix_hyphenated_line_breaks,
    collapse_excess_whitespace,
    remove_repeated_lines,
    strip_hindi_text,
    strip_amendment_annotations,
    clean_text,
)


# ---------------------------------------------------------------
# fix_hyphenated_line_breaks
# ---------------------------------------------------------------

def test_hyphenated_compound_keeps_hyphen_not_fused():
    """Regression test: an earlier version FUSED 'Auditor-\\nGeneral'
    into 'AuditorGeneral', destroying a real compound word. Verified
    against all 42 real hyphen-break occurrences in the Constitution --
    every one was a genuine compound, never a true mid-word split."""
    assert fix_hyphenated_line_breaks("Auditor-\nGeneral") == "Auditor-General"
    assert fix_hyphenated_line_breaks("two-\nthirds") == "two-thirds"
    assert fix_hyphenated_line_breaks("sub-\nsection") == "sub-section"
    assert fix_hyphenated_line_breaks("Vice-\nPresident") == "Vice-President"


def test_no_hyphen_no_change():
    text = "This is ordinary text with no line-break hyphens at all."
    assert fix_hyphenated_line_breaks(text) == text


# ---------------------------------------------------------------
# collapse_excess_whitespace
# ---------------------------------------------------------------

def test_collapses_three_or_more_newlines_to_two():
    assert collapse_excess_whitespace("a\n\n\n\n\nb") == "a\n\nb"


def test_preserves_single_blank_line():
    """A single blank line (2 newlines) should NOT be collapsed further --
    only 3+ in a row are excessive."""
    assert collapse_excess_whitespace("a\n\nb") == "a\n\nb"


def test_collapses_repeated_spaces_and_tabs():
    assert collapse_excess_whitespace("a    b\t\tc") == "a b c"


# ---------------------------------------------------------------
# remove_repeated_lines
# ---------------------------------------------------------------

def test_removes_line_repeated_on_most_pages():
    pages = [
        "THE CONSTITUTION OF INDIA\nArticle 1 text here",
        "THE CONSTITUTION OF INDIA\nArticle 2 text here",
        "THE CONSTITUTION OF INDIA\nArticle 3 text here",
    ]
    cleaned = remove_repeated_lines(pages)
    assert all("THE CONSTITUTION OF INDIA" not in p for p in cleaned)
    assert "Article 1 text here" in cleaned[0]
    assert "Article 2 text here" in cleaned[1]


def test_keeps_line_appearing_on_only_one_page():
    pages = [
        "REPEATED HEADER\nUnique content on page one",
        "REPEATED HEADER\nDifferent unique content",
        "REPEATED HEADER\nMore unique content here",
    ]
    cleaned = remove_repeated_lines(pages)
    assert "Unique content on page one" in cleaned[0]
    assert "REPEATED HEADER" not in cleaned[0]


def test_two_page_document_uses_minimum_threshold():
    """Regression guard: threshold = max(2, int(total_pages * 0.6)).
    For a very short (e.g. 2-page) document, 60% would round down to
    something too permissive -- the max(2, ...) floor ensures a line
    must appear on ALL pages of a 2-page doc to count as repeated,
    not just one."""
    pages = ["HEADER\nPage one only content", "Page two content, no header"]
    cleaned = remove_repeated_lines(pages)
    # "HEADER" appears on only 1 of 2 pages -- below the threshold of 2 --
    # so it should NOT be treated as repeated and should survive.
    assert "HEADER" in cleaned[0]


# ---------------------------------------------------------------
# strip_hindi_text
# ---------------------------------------------------------------

def test_removes_devanagari_characters():
    text = "भारत का संविधान THE CONSTITUTION OF INDIA"
    result = strip_hindi_text(text)
    assert "भारत" not in result
    assert "THE CONSTITUTION OF INDIA" in result


def test_cleans_orphaned_punctuation_after_hindi_removal():
    """Regression test: deleting Hindi text left behind stranded
    punctuation like '[1 , 2026]' -- a comma with nothing meaningful
    before it once its Hindi neighbour is gone."""
    text = "[1 मई , 2026]"
    result = strip_hindi_text(text)
    assert "मई" not in result
    # the orphaned " ," should be cleaned to just ","
    assert " ," not in result


def test_english_only_text_unchanged_by_hindi_stripping():
    text = "No Hindi characters here at all."
    assert strip_hindi_text(text) == text


# ---------------------------------------------------------------
# strip_amendment_annotations
# ---------------------------------------------------------------

def test_strips_single_bracket_amendment_marker():
    text = "shall 3*[extend to the whole of India]"
    result = strip_amendment_annotations(text)
    assert result == "shall extend to the whole of India"


def test_strips_nested_bracket_amendment_markers():
    """The real documented example: nested brackets need multiple
    passes (the while loop) to fully unwrap, one layer per pass."""
    text = "shall 3*[extend to the whole of India 4*[except Jammu and Kashmir]]"
    result = strip_amendment_annotations(text)
    assert "3*[" not in result
    assert "4*[" not in result
    assert "extend to the whole of India" in result
    assert "except Jammu and Kashmir" in result


def test_strips_standalone_trailing_marker():
    text = "the whole of India.5*"
    result = strip_amendment_annotations(text)
    assert result == "the whole of India."


def test_plain_text_unaffected():
    text = "This has no amendment markup of any kind."
    assert strip_amendment_annotations(text) == text


# ---------------------------------------------------------------
# clean_text (the full per-page pipeline)
# ---------------------------------------------------------------

def test_clean_text_runs_all_steps_in_order():
    """Integration check: Hindi + amendment markup + hyphen break + excess
    whitespace, all in one page, all fixed together."""
    text = "भारत Auditor-\nGeneral shall 3*[extend to India]   with    spaces\n\n\n\nhere"
    result = clean_text(text)
    assert "भारत" not in result
    assert "Auditor-General" in result
    assert "extend to India" in result
    assert "3*[" not in result
    assert "   " not in result  # excess spaces collapsed
    assert "\n\n\n" not in result  # excess newlines collapsed


def test_clean_text_does_not_remove_repeated_lines():
    """remove_repeated_lines() needs ALL pages at once and is
    deliberately NOT called inside clean_text() (which only sees one
    page) -- it's invoked separately by ingestion_service.py. Checked via
    AST (real function calls only), not a substring match on the source
    text, since clean_text()'s own docstring explains this exact fact in
    English and would falsely trip a naive substring check."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(clean_text))
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "remove_repeated_lines" not in called_names