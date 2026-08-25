"""
Throwaway test script -- dumps the FULL document (all pages, raw and
cleaned) to a file, so we can properly inspect everything instead of
just page 1.
"""

from app.ingestion.pdf_loader import load_pdf_pages
from app.ingestion.text_cleaner import clean_text
import re

# Change this path to whichever PDF you want to test
PDF_PATH = "legal-data/constitution/constitution_2026.pdf"

pages = load_pdf_pages(PDF_PATH)

output_lines = []
output_lines.append(f"Total pages extracted: {len(pages)}\n")

total_hindi_remaining = 0

# Loop through EVERY page, not just the first one
for page in pages:
    cleaned = clean_text(page.text)

    output_lines.append(f"\n{'='*20} PAGE {page.page_number} RAW {'='*20}")
    output_lines.append(page.text)
    output_lines.append(f"\n{'-'*20} PAGE {page.page_number} CLEANED {'-'*20}")
    output_lines.append(cleaned)

    hindi_here = re.findall(r"[\u0900-\u097F]", cleaned)
    total_hindi_remaining += len(hindi_here)

output_lines.append(f"\n\nTOTAL Devanagari characters remaining after cleaning (all pages): {total_hindi_remaining}")

with open("test_output.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(output_lines))

print(f"Done. Wrote {len(pages)} pages to test_output.txt")