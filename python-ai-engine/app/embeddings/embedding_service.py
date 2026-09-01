"""
app/embeddings/embedding_service.py

Step 6 of the pipeline: turn Chunk TEXT into VECTORS.

This is the one place in the whole project that touches the embedding
model, on purpose -- per settings.py's own warning, ingestion (this file)
and querying (retriever.py, later) MUST use the exact same model, or
similarity search silently breaks (vectors from two different models
aren't comparable, but nothing raises an error -- search just quietly
returns nonsense). So both sides import EMBEDDING_MODEL_NAME from the one
shared `settings` object, and both sides should call the functions here
rather than instantiating SentenceTransformer themselves.
"""

from app.config.settings import settings
from app.models.chunk import Chunk

# ---------------------------------------------------------------
# Lazy singleton model loading.
#
# Two deliberate choices here:
#
#   1. LAZY (loaded on first actual use, not at import time). Loading a
#      sentence-transformers model pulls in torch and reads model weights
#      off disk/network -- slow, and unnecessary for any code that merely
#      imports this module without ever embedding anything (e.g. a test
#      that only exercises chunker.py). Importing embedding_service should
#      be instant; calling embed_texts() is what's allowed to be slow.
#
#   2. SINGLETON (loaded once, reused for every call). Re-loading the model
#      on every embed_texts() call would re-pay that same slow load cost
#      every time -- for a batch ingestion job calling this hundreds of
#      times, that's the difference between one load and hundreds.
# ---------------------------------------------------------------
_model = None


def _get_model():
    global _model
    if _model is None:
        # Imported lazily, in here, not at the top of the file, for the
        # same reason the load itself is lazy: a caller who only wants
        # embed_query() shouldn't be forced to have sentence-transformers
        # importable just to import this module.
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
    return _model


def _token_count(model, text: str) -> int:
    """Exact token count via the model's REAL tokenizer -- not a char/word
    estimate. This is what makes the splitting below correct regardless of
    how legal jargon happens to tokenize."""
    return len(model.tokenizer(text, truncation=False)["input_ids"])


def _split_for_model(model, text: str, max_tokens: int) -> list[str]:
    """Split `text` into pieces that EACH fit within max_tokens, guaranteed
    to reproduce every word of the original when concatenated -- unlike
    split_by_size() in chunker.py (which splits by CHARACTER count for a
    different purpose, storage chunk size), this splits by REAL TOKEN count,
    because that's the thing that actually determines truncation here.

    Greedy word-by-word packing: keep adding words to the current piece as
    long as it still fits; the moment adding the next word would overflow,
    close the piece off and start a new one with that word. This always
    terminates and never drops a word, because every word is tried in the
    current piece first and only ever deferred to the NEXT piece, never
    discarded outright.
    """
    words = text.split()
    if not words:
        return [text]

    pieces: list[str] = []
    current_words: list[str] = []

    for word in words:
        candidate = " ".join(current_words + [word])
        if current_words and _token_count(model, candidate) > max_tokens:
            pieces.append(" ".join(current_words))
            current_words = [word]
        else:
            current_words.append(word)

    if current_words:
        pieces.append(" ".join(current_words))

    return pieces


def embed_texts(
    texts: list[str],
    batch_size: int = 32,
    show_progress: bool = False,
) -> list[list[float]]:
    """Turn a list of raw strings into a list of embedding vectors, in the
    SAME order as `texts`. This is the low-level primitive both
    embed_chunks() (ingestion) and embed_query() (retrieval) build on, so
    there is exactly one code path that ever calls the model's .encode().

    ZERO DATA LOSS guarantee: sentence-transformers silently TRUNCATES any
    text longer than the model's max_seq_length -- confirmed against real
    BNSS chunks that this is a live risk, not theoretical (~1/3 of a real
    document's chunks sat close to or over the known 256 word-piece limit
    using a conservative word-count proxy). Rather than just warning about
    that, any text over the limit is split into token-safe pieces (via
    _split_for_model, using the model's REAL tokenizer, not an estimate),
    each piece is embedded, and the resulting vectors are MEAN-POOLED
    (averaged) into one final vector per original text. This is a standard
    technique for embedding text longer than a model's context window --
    every word gets tokenized and contributes to the result; nothing is
    ever silently dropped, regardless of chunk size or which model is
    configured in settings.

    Returns [] for [] rather than calling the model at all -- an empty
    ingestion batch is a normal, valid input, not an error.
    """
    if not texts:
        return []

    model = _get_model()

    # settings.EMBEDDING_MAX_TOKENS (256, pinned deliberately -- see
    # settings.py) is the authoritative limit, not just whatever the
    # library happens to report at runtime. Taking the SMALLER of the two
    # is a safety choice: if a future sentence-transformers version ever
    # reports a different max_seq_length for this same model, we still
    # never exceed the length this model is actually verified to perform
    # well at.
    reported_max = getattr(model, "max_seq_length", None)
    max_len = min(reported_max, settings.EMBEDDING_MAX_TOKENS) if reported_max else settings.EMBEDDING_MAX_TOKENS
    # transformers' tokenizer adds its own special tokens ([CLS]/[SEP]) on
    # top of whatever _token_count measures per plain call, so packing
    # pieces right up to the exact limit could still occasionally overflow
    # by a couple of tokens once those get added back in during the real
    # encode() call.
    safe_max = max_len - 2

    # Two groups: texts that fit as-is (the common case -- keep these
    # batched together in ONE encode() call for speed), and texts that need
    # splitting (handled separately, each contributing multiple pieces that
    # get mean-pooled back into one vector per original text).
    normal_indices, normal_texts = [], []
    oversized_indices, oversized_pieces_per_text = [], []

    for i, t in enumerate(texts):
        if _token_count(model, t) <= safe_max:
            normal_indices.append(i)
            normal_texts.append(t)
        else:
            pieces = _split_for_model(model, t, safe_max)
            oversized_indices.append(i)
            oversized_pieces_per_text.append(pieces)
            print(
                f"NOTE: text at index {i} exceeded this model's "
                f"max_seq_length ({max_len} tokens) -- split into "
                f"{len(pieces)} pieces and mean-pooled into one vector "
                f"instead of being truncated. text[:80]={t[:80]!r}"
            )

    results: list[list[float] | None] = [None] * len(texts)

    if normal_texts:
        normal_vectors = model.encode(
            normal_texts, batch_size=batch_size, show_progress_bar=show_progress,
            convert_to_numpy=True,
        )
        _assert_dimension(normal_vectors)
        for idx, vec in zip(normal_indices, normal_vectors):
            results[idx] = vec.tolist()

    if oversized_pieces_per_text:
        # Flatten every piece from every oversized text into one batched
        # call too, then group the resulting vectors back per original
        # text using how many pieces each one contributed.
        all_pieces = [p for pieces in oversized_pieces_per_text for p in pieces]
        piece_vectors = model.encode(
            all_pieces, batch_size=batch_size, show_progress_bar=show_progress,
            convert_to_numpy=True,
        )
        _assert_dimension(piece_vectors)

        cursor = 0
        for idx, pieces in zip(oversized_indices, oversized_pieces_per_text):
            n = len(pieces)
            this_text_vectors = piece_vectors[cursor:cursor + n]
            cursor += n
            # Mean pooling: element-wise average across all of this text's
            # piece-vectors -- every piece contributed equally, so no part
            # of the original text is weighted out of the final vector.
            results[idx] = this_text_vectors.mean(axis=0).tolist()

    return results


def _assert_dimension(vectors) -> None:
    """Fail loudly, immediately, rather than letting a wrong-shaped vector
    travel all the way to Qdrant and get rejected there with a far more
    confusing error. Same 'catch it at the source' philosophy
    chunk_document() uses for missing structure."""
    if vectors.shape[1] != settings.EMBEDDING_DIMENSION:
        raise ValueError(
            f"Embedding model '{settings.EMBEDDING_MODEL_NAME}' produced "
            f"{vectors.shape[1]}-dim vectors, but settings.EMBEDDING_DIMENSION "
            f"is {settings.EMBEDDING_DIMENSION}. Update EMBEDDING_DIMENSION "
            f"in .env to match the model actually in use."
        )


def embed_chunks(
    chunks: list[Chunk],
    batch_size: int = 32,
    show_progress: bool = False,
) -> list[Chunk]:
    """Embed every chunk's .text and fill in its .vector field IN PLACE
    (and return the same list back, for convenient chaining).

    Batches all chunk texts into ONE call to embed_texts() rather than
    embedding chunk-by-chunk in a loop -- sentence-transformers is far
    more efficient batched, and for a full document (hundreds of chunks)
    that's a meaningful speed difference.
    """
    if not chunks:
        return []

    texts = [c.text for c in chunks]
    vectors = embed_texts(texts, batch_size=batch_size, show_progress=show_progress)

    for chunk, vector in zip(chunks, vectors):
        chunk.vector = vector

    return chunks


def embed_query(text: str) -> list[float]:
    """Embed a single user query string, at request time (retriever.py).
    Thin wrapper over embed_texts() so callers never have to remember to
    wrap/unwrap a one-element list themselves."""
    return embed_texts([text])[0]