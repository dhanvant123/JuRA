"""
scripts/extract_pdf.py

Standalone CLI script: dump a single PDF's raw extracted text to a file,
for manual inspection -- the same job test_pipeline.py has been doing
ad hoc throughout earlier sessions, now formalized as a real, reusable
script instead of a one-off.

Usage:
    python scripts/extract_pdf.py legal-data/current-laws/bns_2023.pdf
    python scripts/extract_pdf.py legal-data/current-laws/bns_2023.pdf --out bns_raw.txt
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingestion.pdf_loader import load_pdf_pages


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump a PDF's raw extracted text for manual inspection.")
    parser.add_argument("pdf_path", type=Path, help="Path to the PDF file to extract.")
    parser.add_argument(
        "--out", type=Path, default=None,
        help="Output text file path (default: <pdf_name>_raw.txt in the current directory).",
    )
    args = parser.parse_args()

    if not args.pdf_path.exists():
        print(f"ERROR: no file at {args.pdf_path}", file=sys.stderr)
        sys.exit(1)

    out_path = args.out or Path(f"{args.pdf_path.stem}_raw.txt")

    pages = load_pdf_pages(str(args.pdf_path))

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"Source: {args.pdf_path}\n")
        f.write(f"Total pages extracted: {len(pages)}\n\n")
        for page in pages:
            f.write(f"{'=' * 20} PAGE {page.page_number} RAW {'=' * 20}\n")
            f.write(page.text)
            f.write("\n\n")

    print(f"{len(pages)} pages -> {out_path}")


if __name__ == "__main__":
    main()