"""
app/ingestion/pdf_loader.py

Step 2 of the pipeline: PDF -> raw text, kept PAGE BY PAGE.

Why page-by-page, not one giant string:
If we joined every page into one big blob of text right away, we'd lose
the ability to say "this text came from page 42" later. That page number
is what powers accurate citations (Step 12). So this file's only job is
extraction -- it does NOT clean text, does NOT chunk, does NOT touch
metadata. Keeping it this narrow makes it easy to test and trust on its
own before anything else in the pipeline depends on it.

Uses PyMuPDF (imported as `fitz`) -- chosen in the original plan for
being fast and giving reliable per-page text extraction.
"""

from pathlib import Path

import fitz  # this is PyMuPDF -- the package name and import name differ


class PageText:
    """
    A plain, simple container for one page's extracted text.

    We use a lightweight class here (not a Pydantic model like Chunk)
    because this is a very short-lived, internal intermediate value --
    it exists only between pdf_loader.py and text_cleaner.py/chunker.py.
    It never gets stored in Qdrant or sent over an API, so it doesn't
    need Pydantic's validation overhead. Chunk and Document DO get
    validated because they're the "final", persisted shapes.
    """

    def __init__(self, page_number: int, text: str):
        self.page_number = page_number
        self.text = text

    def __repr__(self):
        # This controls what you see when you print(some_page_text) --
        # makes debugging output readable instead of a memory address.
        preview = self.text[:50].replace("\n", " ")
        return f"PageText(page={self.page_number}, text='{preview}...')"


def load_pdf_pages(file_path: str | Path) -> list[PageText]:
    """
    Opens a PDF and returns its text, one PageText object per page.

    Args:
        file_path: path to the PDF file (string or Path object).

    Returns:
        A list of PageText objects, one per page, in page order.

    Raises:
        FileNotFoundError: if the given path doesn't actually exist.
        This is intentional -- we want ingestion to fail loudly and
        immediately if a PDF is missing, not silently skip it.
    """

    # Always convert to a Path object first. This lets us call
    # .exists() below regardless of whether the caller passed a
    # plain string or already a Path -- one consistent type internally.
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")

    # fitz.open() reads the PDF file from disk into memory as a
    # navigable "document" object we can loop over.
    pdf_document = fitz.open(file_path)

    pages: list[PageText] = []

    # enumerate(pdf_document, start=1) loops through every page AND
    # gives us a running count. start=1 means the first page is
    # page 1, not page 0 -- matching how humans actually refer to
    # PDF page numbers, which matters for citations later.
    for page_number, page in enumerate(pdf_document, start=1):
        # get_text() is PyMuPDF's method that pulls the plain text
        # content out of a single page.
        raw_text = page.get_text()

        pages.append(PageText(page_number=page_number, text=raw_text))

    # Always close the document after we're done reading it -- this
    # releases the file handle/memory PyMuPDF was holding. Forgetting
    # this is a common resource-leak bug when processing many files.
    pdf_document.close()

    return pages