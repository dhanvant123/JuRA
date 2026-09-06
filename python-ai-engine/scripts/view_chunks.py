"""
scripts/view_chunks.py

Standalone CLI script: browse what's actually stored in Qdrant, no
similarity search involved -- just paging through real stored chunks.
Complements the Qdrant dashboard (http://localhost:6333/dashboard,
available automatically since the Docker image ships one) with a
terminal-friendly view, and lets you filter by document_id which the
dashboard's default view doesn't do as directly.

Usage:
    python scripts/view_chunks.py                          # first 20 chunks, any document
    python scripts/view_chunks.py --document bns_2023       # only BNS chunks
    python scripts/view_chunks.py --limit 5 --full-text     # show complete chunk text, not a preview
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.vectorstore.qdrant_service import list_chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="Browse chunks stored in Qdrant.")
    parser.add_argument("--limit", type=int, default=20, help="Number of chunks to show (default: 20).")
    parser.add_argument("--document", default=None, dest="document_id", help="Only show chunks from this document_id.")
    parser.add_argument("--full-text", action="store_true", help="Show each chunk's complete text instead of a preview.")
    args = parser.parse_args()

    chunks, next_offset = list_chunks(limit=args.limit, document_id=args.document_id)

    if not chunks:
        print("No chunks found." + (f" (document_id={args.document_id!r})" if args.document_id else ""))
        return

    for i, chunk in enumerate(chunks, start=1):
        md = chunk.metadata
        unit = f"Article {md.article}" if md.article else f"Section {md.section}"
        title = md.article_title or md.section_title or ""
        print(f"\n[{i}] id={chunk.id}")
        print(f"    {md.document_title} -- {unit} ({title})")
        print(f"    part={md.part}  chapter={md.chapter}  page={md.page}  legal_status={md.legal_status}")
        if args.full_text:
            print(f"    text:\n{chunk.text}")
        else:
            preview = chunk.text.split("\n\n", 1)[-1][:200].replace("\n", " ")
            print(f"    text: {preview}...")

    print(f"\n{len(chunks)} chunk(s) shown.", end=" ")
    if next_offset is not None:
        print("More available -- increase --limit to see further ones.")
    else:
        print("This is all of them (for this filter).")


if __name__ == "__main__":
    main()