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


def embed_texts(
    texts: list[str],
    batch_size: int = 32,
    show_progress: bool = False,
) -> list[list[float]]:
    """Turn a list of raw strings into a list of embedding vectors, in the
    SAME order as `texts`. This is the low-level primitive both
    embed_chunks() (ingestion) and embed_query() (retrieval) build on, so
    there is exactly one code path that ever calls the model's .encode().

    Returns [] for [] rather than calling the model at all -- an empty
    ingestion batch is a normal, valid input, not an error.
    """
    if not texts:
        return []

    model = _get_model()
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=show_progress,
        convert_to_numpy=True,
    )

    # Fail loudly, immediately, rather than letting a wrong-shaped vector
    # travel all the way to Qdrant and get rejected there with a far more
    # confusing error. This is the same "catch it at the source" philosophy
    # chunk_document() uses for missing structure.
    if vectors.shape[1] != settings.EMBEDDING_DIMENSION:
        raise ValueError(
            f"Embedding model '{settings.EMBEDDING_MODEL_NAME}' produced "
            f"{vectors.shape[1]}-dim vectors, but settings.EMBEDDING_DIMENSION "
            f"is {settings.EMBEDDING_DIMENSION}. Update EMBEDDING_DIMENSION "
            f"in .env to match the model actually in use."
        )

    return vectors.tolist()


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