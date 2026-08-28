"""
test_embedding.py

Standalone, manually-run script: takes a chunk-text file that was already
produced by run_chunker_test.py (e.g. stored_chunks.txt, stored_chunks2.txt),
re-reads its chunks, embeds each chunk's text via
app/embeddings/embedding_service.py, and saves the resulting vectors under
whatever output name YOU choose (e.g. "embedded_chunk1").

YOU control both ends of this:
    - which chunk file to read       (positional arg 1, or typed at a prompt)
    - what to name the output file   (positional arg 2, or typed at a prompt)

This does NOT re-run the chunker or touch Qdrant -- it's a narrow,
throwaway tool for manually checking "does embedding actually work on my
real chunks, and what do the vectors look like", the same spirit as
run_chunker_test.py / verify3.py.

Output format: JSON Lines (one JSON object per chunk per line) -- easy to
skim with `head`, easy to load back with json.loads() line by line, and
doesn't require holding the whole file as one giant JSON array in memory.
Each line looks like:
    {"index": 0, "id": "constitution_2026__...", "meta_line": "part=... article=...",
     "model": "sentence-transformers/all-MiniLM-L6-v2", "vector_dim": 384,
     "vector": [0.0123, -0.0456, ...]}
"""

import re
import sys
import json
from pathlib import Path

from app.embeddings.embedding_service import embed_texts
from app.config.settings import settings

# The exact delimiter format run_chunker_test.py writes -- see its Step 4.
_CHUNK_HEADER = re.compile(r"^=+ CHUNK (\d+) id=(\S+) =+$", re.MULTILINE)
_TEXT_MARKER = re.compile(r"^-+ TEXT -+$", re.MULTILINE)


def parse_chunk_file(path: Path) -> list[dict]:
    """Re-read a stored_chunks*.txt file back into a list of
    {index, id, meta_line, text} dicts, one per chunk."""
    content = path.read_text(encoding="utf-8")
    matches = list(_CHUNK_HEADER.finditer(content))
    if not matches:
        raise ValueError(
            f"No '==== CHUNK N id=... ====' headers found in {path}. "
            f"Is this a file produced by run_chunker_test.py?"
        )

    parsed = []
    for i, m in enumerate(matches):
        block_start = m.end()
        block_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        block = content[block_start:block_end]

        text_marker = _TEXT_MARKER.search(block)
        if text_marker:
            meta_line = block[: text_marker.start()].strip()
            text = block[text_marker.end():].strip("\n").strip()
        else:
            # No TEXT delimiter found -- treat the whole block as text and
            # leave meta_line empty rather than silently dropping the chunk.
            meta_line = ""
            text = block.strip()

        parsed.append(
            {
                "index": int(m.group(1)),
                "id": m.group(2),
                "meta_line": meta_line,
                "text": text,
            }
        )
    return parsed


def resolve_paths() -> tuple[Path, Path]:
    """Get the input chunk file and output name, from CLI args if given,
    otherwise by prompting interactively."""
    if len(sys.argv) >= 3:
        input_arg, output_arg = sys.argv[1], sys.argv[2]
    else:
        input_arg = input(
            "Chunk text file to embed (e.g. stored_chunks2.txt): "
        ).strip()
        output_arg = input(
            "Name to save the embeddings as (e.g. embedded_chunk1): "
        ).strip()

    input_path = Path(input_arg)
    if not input_path.exists():
        raise FileNotFoundError(
            f"'{input_path}' not found. Run this script from python-ai-engine/ "
            f"(same folder the chunk file was written to)."
        )

    output_path = Path(output_arg)
    if output_path.suffix == "":
        output_path = output_path.with_suffix(".jsonl")

    return input_path, output_path


def main() -> None:
    input_path, output_path = resolve_paths()

    parsed_chunks = parse_chunk_file(input_path)
    print(f"Read {len(parsed_chunks)} chunks from {input_path}")

    texts = [c["text"] for c in parsed_chunks]
    print(f"Embedding with model '{settings.EMBEDDING_MODEL_NAME}' "
          f"(this loads the model on first call -- may take a moment)...")
    vectors = embed_texts(texts, show_progress=True)

    with open(output_path, "w", encoding="utf-8") as out:
        for chunk, vector in zip(parsed_chunks, vectors):
            record = {
                "index": chunk["index"],
                "id": chunk["id"],
                "meta_line": chunk["meta_line"],
                "model": settings.EMBEDDING_MODEL_NAME,
                "vector_dim": len(vector),
                "vector": vector,
            }
            out.write(json.dumps(record) + "\n")

    print(f"Wrote {len(parsed_chunks)} embeddings to {output_path}")
    print(f"Vector dimension: {len(vectors[0]) if vectors else 0} "
          f"(settings.EMBEDDING_DIMENSION = {settings.EMBEDDING_DIMENSION})")


if __name__ == "__main__":
    main()