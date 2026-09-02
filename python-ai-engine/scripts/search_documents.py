"""
scripts/search_documents.py

Standalone CLI script: run a retrieval-only query from the command line,
with NO LLM involved -- exactly the "verify retrieval quality before
adding an LLM" step from the original plan (Step 10), now runnable
directly instead of only from a Python shell.

Usage:
    python scripts/search_documents.py "what is the punishment for murder"
    python scripts/search_documents.py "right to life" --limit 3 --status current
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.retrieval.retriever import retrieve
from app.models.chunk import LegalStatus, DocumentType


_STATUS_MAP = {"current": LegalStatus.CURRENT, "superseded": LegalStatus.SUPERSEDED, "repealed": LegalStatus.REPEALED}
_TYPE_MAP = {"constitution": DocumentType.CONSTITUTION, "act": DocumentType.ACT, "code": DocumentType.CODE}


def main() -> None:
    parser = argparse.ArgumentParser(description="Search ingested legal chunks, no LLM involved.")
    parser.add_argument("query", help="The question or phrase to search for.")
    parser.add_argument("--limit", type=int, default=5, help="Number of results to return (default: 5).")
    parser.add_argument("--status", choices=sorted(_STATUS_MAP), default=None, help="Filter by legal_status.")
    parser.add_argument("--type", choices=sorted(_TYPE_MAP), default=None, dest="doc_type", help="Filter by document_type.")
    args = parser.parse_args()

    results = retrieve(
        args.query,
        limit=args.limit,
        legal_status=_STATUS_MAP.get(args.status),
        document_type=_TYPE_MAP.get(args.doc_type),
    )

    if not results:
        print("No results found.")
        return

    for i, chunk in enumerate(results, start=1):
        md = chunk.metadata
        unit = f"Article {md.article}" if md.article else f"Section {md.section}"
        title = md.article_title or md.section_title or ""
        print(f"\n[{i}] {md.document_title} -- {unit} ({title})")
        print(f"    page {md.page}, legal_status={md.legal_status}")
        preview = chunk.text.split("\n\n", 1)[-1][:200].replace("\n", " ")
        print(f"    {preview}...")


if __name__ == "__main__":
    main()