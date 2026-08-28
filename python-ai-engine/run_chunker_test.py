"""
run_chunker_test.py

Runs the real pipeline (cleaner -> chunker) on test_output.txt and writes
every produced chunk to stored_chunks2.txt.

chunk_document() is the only PUBLIC entry point (no leading underscore) --
every other function in chunker.py (_clean_title, _context_before,
_structural_index, split_by_size, detect_body_start_page, etc.) is an
internal helper that chunk_document() already calls for you, as part of
its normal work. So calling chunk_document() once *does* exercise every
function in the file -- this script just makes that visible: it wraps
each function with a counter before calling chunk_document(), then prints
a call-count table so you can see every one of them actually fire.
"""

import re
import functools
from collections import Counter

from app.ingestion.text_cleaner import clean_text, remove_repeated_lines
from app.ingestion import chunker
from app.ingestion.chunker import chunk_document
from app.models.document import Document
from app.models.chunk import DocumentType, LegalStatus

OUTPUT_FILE = "stored_chunks2.txt"

# ---------------------------------------------------------------
# Step 1: instrument every function defined in chunker.py so we can
# prove each one actually gets called, and how many times.
# ---------------------------------------------------------------
call_counts: Counter = Counter()

for name in dir(chunker):
    obj = getattr(chunker, name)
    # Only wrap things that are actually functions DEFINED in this module
    # (skip imports like `re`, classes like Chunk/Document, compiled regex
    # patterns, etc.)
    if callable(obj) and getattr(obj, "__module__", None) == chunker.__name__ \
            and not isinstance(obj, type):

        def make_wrapper(fn, fn_name):
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                call_counts[fn_name] += 1
                return fn(*args, **kwargs)
            return wrapper

        setattr(chunker, name, make_wrapper(obj, name))

# Re-bind chunk_document AFTER wrapping, so we call the wrapped version,
# and so that when chunk_document's own code calls e.g. _clean_title(...),
# it's calling the wrapped version too (module-level lookup at call time).
chunk_document = chunker.chunk_document


# ---------------------------------------------------------------
# Step 2: load + clean the test PDF's text (same as verify3.py --
# faithful pipeline order: per-page clean, then cross-page dedupe).
# ---------------------------------------------------------------
raw = open("test_output.txt", encoding="utf-8").read()
raw_secs = re.split(r"=+ PAGE \d+ RAW =+", raw)
raw_pages = [re.split(r"-+ PAGE \d+ CLEANED -+", s)[0].strip("\n") for s in raw_secs[1:]]

cleaned = [clean_text(p) for p in raw_pages]
cleaned = remove_repeated_lines(cleaned)

print(f"Parsed {len(cleaned)} cleaned pages from test_output.txt")

doc = Document(
    document_id="constitution_2026",
    title="The Constitution of India",
    document_type=DocumentType.CONSTITUTION,
    legal_status=LegalStatus.CURRENT,
    file_path="legal-data/constitution/constitution_2026.pdf",
    source="Legislative Department",
    source_url=None,
)

# ---------------------------------------------------------------
# Step 3: run the real pipeline entry point. This alone drives every
# helper in chunker.py, because chunk_document() calls them internally.
# ---------------------------------------------------------------
chunks = chunk_document(doc, cleaned)
print(f"chunk_document() produced {len(chunks)} chunks")

# ---------------------------------------------------------------
# Step 4: write every chunk out to stored_chunks2.txt.
# ---------------------------------------------------------------
output_lines = []
output_lines.append(f"Total chunks: {len(chunks)}\n")

for i, c in enumerate(chunks):
    m = c.metadata
    output_lines.append(f"\n{'='*20} CHUNK {i} id={c.id} {'='*20}")
    output_lines.append(
        f"part={m.part!r} part_title={m.part_title!r} "
        f"chapter={m.chapter!r} chapter_title={m.chapter_title!r} "
        f"article={m.article!r} article_title={m.article_title!r} "
        f"section={m.section!r} section_title={m.section_title!r} "
        f"page={m.page} char_count={len(c.text)}"
    )
    output_lines.append(f"{'-'*20} TEXT {'-'*20}")
    output_lines.append(c.text)

with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
    out.write("\n".join(output_lines))

print(f"Wrote all chunks to {OUTPUT_FILE}")

# ---------------------------------------------------------------
# Step 5: prove every function in chunker.py fired, with a call-count
# table -- including chunk_document itself (its own count was captured
# by the wrapper when we called it in Step 3, no manual bump needed).
# ---------------------------------------------------------------
print("\n=== chunker.py function call counts ===")
all_fn_names = [
    name for name in dir(chunker)
    if callable(getattr(chunker, name))
    and getattr(getattr(chunker, name), "__module__", None) == chunker.__name__
    and not isinstance(getattr(chunker, name), type)
]
never_called = []
for name in sorted(all_fn_names):
    n = call_counts.get(name, 0)
    print(f"  {name:<32} called {n:>5} time(s)")
    if n == 0:
        never_called.append(name)

if never_called:
    print(f"\n⚠ These functions never fired: {never_called}")
else:
    print("\n✔ Every function in chunker.py fired at least once.")