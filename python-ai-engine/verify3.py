"""
End-to-end verification: RAW extraction -> clean_text (per page) ->
remove_repeated_lines (all pages) -> chunk_document. This exercises the
ACTUAL pipeline (cleaner + chunker together) on freshly-cleaned text, rather
than the stale pre-fix cleaned text stored in test_output.txt (which verify2
uses). Requires only test_output.txt (no PyMuPDF).
"""
import re
from collections import Counter
from app.ingestion.text_cleaner import clean_text, remove_repeated_lines
from app.ingestion.chunker import chunk_document
from app.models.document import Document
from app.models.chunk import DocumentType, LegalStatus

raw = open('test_output.txt', encoding='utf-8').read()
# Pull the RAW (untouched extraction) section of every page.
raw_secs = re.split(r'=+ PAGE \d+ RAW =+', raw)
raw_pages = [re.split(r'-+ PAGE \d+ CLEANED -+', s)[0].strip('\n') for s in raw_secs[1:]]

# Faithful pipeline order: per-page clean, then cross-page header/footer strip.
cleaned = [clean_text(p) for p in raw_pages]
cleaned = remove_repeated_lines(cleaned)

doc = Document(
    document_id='constitution_2026', title='The Constitution of India',
    document_type=DocumentType.CONSTITUTION, legal_status=LegalStatus.CURRENT,
    file_path='legal-data/constitution/constitution_2026.pdf',
    source='Legislative Department', source_url=None,
)
chunks = chunk_document(doc, cleaned)

def base(n):
    m = re.match(r'(\d+)', n); return int(m.group(1)) if m else -1

nums = [c.metadata.article for c in chunks if c.metadata.article]
distinct = sorted(set(nums), key=lambda n: (base(n), n))
print('total chunks:', len(chunks))
print('distinct articles:', len(distinct), '| range', base(distinct[0]), '..', base(distinct[-1]))
print('duplicate ids:', len(chunks) - len({c.id for c in chunks}))
print('missing article meta:', sum(1 for c in chunks if not c.metadata.article))
print('missing part meta:', sum(1 for c in chunks if not c.metadata.part))
print('over size (>1500):', sum(1 for c in chunks if len(c.text) > 1500))
print('impossible base (>395 or <1):', [a for a in distinct if base(a) > 395 or base(a) < 1])

# Every chunk must carry a structural header in its TEXT (objective: subject
# is searchable and survives size-splitting).
no_header = [c for c in chunks if 'Article' not in c.text.split('\n\n', 1)[0]]
print('chunks whose text lacks an Article header:', len(no_header))

# Spot-check the objectives on representative articles.
by = {}
for c in chunks:
    by.setdefault(c.metadata.article, c)
print('\n=== objective spot-check (number + subject + inherited Part/Chapter) ===')
for a in ['1', '21', '51A', '52', '124', '243', '243ZG', '356', '368', '395']:
    c = by.get(a)
    if not c:
        print('   %-6s <MISSING>' % a); continue
    m = c.metadata
    print('   art %-5s part=%-9s chap=%-9s title=%r' % (
        a, m.part, m.chapter, (m.article_title or '')[:40]))

print('\n31D (repealed stub) present?:', '31D' in by, '(should be False)')
