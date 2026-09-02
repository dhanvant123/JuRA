"""
scripts/ingest_documents.py

Standalone CLI script: run the real batch ingestion pipeline
(ingestion_service.ingest_all) from the command line. Thin on purpose --
ingestion_service.py already has all the real logic and is already
independently tested; this script's only job is exposing it as
something runnable without opening a Python shell.

Usage:
    python scripts/ingest_documents.py                # ingest everything in the registry
    python scripts/ingest_documents.py --only bns_2023 crpc_1973   # ingest specific documents
    python scripts/ingest_documents.py --list          # list registered documents, don't ingest
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingestion.ingestion_service import ingest_all, DOCUMENT_REGISTRY


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the JuRA batch ingestion pipeline.")
    parser.add_argument(
        "--only", nargs="+", default=None, metavar="DOCUMENT_ID",
        help="Only ingest these document_ids instead of the full registry.",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List registered documents and exit, without ingesting anything.",
    )
    args = parser.parse_args()

    if args.list:
        for entry in DOCUMENT_REGISTRY:
            print(f"{entry.document_id}\t{entry.title}\t{entry.path}")
        return

    entries = DOCUMENT_REGISTRY
    if args.only:
        known_ids = {e.document_id for e in DOCUMENT_REGISTRY}
        unknown = set(args.only) - known_ids
        if unknown:
            print(f"ERROR: unknown document_id(s): {sorted(unknown)}", file=sys.stderr)
            print(f"Known ids: {sorted(known_ids)}", file=sys.stderr)
            sys.exit(1)
        entries = [e for e in DOCUMENT_REGISTRY if e.document_id in args.only]

    results = ingest_all(entries)

    failed = {k: v for k, v in results.items() if isinstance(v, str)}
    if failed:
        print(f"\n{len(failed)} document(s) FAILED:", file=sys.stderr)
        for doc_id, error in failed.items():
            print(f"  {doc_id}: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()