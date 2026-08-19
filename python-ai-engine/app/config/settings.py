"""
app/config/settings.py

Central place for all settings (paths, Qdrant connection, embedding model).

Why this file exists:
Every other module (pdf_loader, chunker, qdrant_service, embedding_service,
etc.) needs shared settings. Instead of hardcoding "localhost:6333" or a
folder path in five different files, we read it once here and import
`settings` everywhere else.

If you move to a different server, or switch embedding models later,
you change ONE file (or just the .env values) instead of hunting through
code scattered across the whole project.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# load_dotenv() reads the .env file in the project root and injects its
# key=value pairs into the environment, so os.getenv() below can see them.
# Without this line, .env would just sit there completely unused.
load_dotenv()


class Settings:
    # -------------------------------------------------------------
    # PATHS
    # -------------------------------------------------------------

    # Path(__file__) = path to THIS file (settings.py)
    # .resolve()     = turn it into a full absolute path (not relative)
    # .parent.parent.parent = go up three levels:
    #     app/config/settings.py -> app/config/ -> app/ -> python-ai-engine/
    # This gives us the project root no matter where the script is run from.
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent

    LEGAL_DATA_DIR: Path = BASE_DIR / "legal-data"
    CONSTITUTION_DIR: Path = LEGAL_DATA_DIR / "constitution"
    CURRENT_LAWS_DIR: Path = LEGAL_DATA_DIR / "current-laws"
    HISTORICAL_LAWS_DIR: Path = LEGAL_DATA_DIR / "historical-laws"

    # -------------------------------------------------------------
    # QDRANT CONNECTION
    # -------------------------------------------------------------

    # os.getenv("KEY", "default") reads an environment variable.
    # If it's not set (e.g. you forgot to add it to .env), it falls back
    # to the default value instead of crashing. Good for local dev.
    QDRANT_HOST: str = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", "6333"))

    # Every Qdrant "collection" is like a table. Naming it explicitly here
    # means ingest_documents.py and search_documents.py always agree on
    # which collection to write to / read from.
    QDRANT_COLLECTION_NAME: str = os.getenv("QDRANT_COLLECTION_NAME", "jura_legal_chunks")

    # -------------------------------------------------------------
    # EMBEDDING MODEL
    # -------------------------------------------------------------

    # IMPORTANT: whatever model we choose here must be used for BOTH
    # ingestion and querying. If they ever differ, similarity search
    # breaks silently -- the vectors won't be comparable to each other.
    EMBEDDING_MODEL_NAME: str = os.getenv(
        "EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2"
    )

    # This must match the output dimension of the model above.
    # all-MiniLM-L6-v2 outputs 384-dimensional vectors.
    # If we switch models later, this number MUST be updated too, or
    # Qdrant will reject the vectors (wrong shape) at insert time.
    EMBEDDING_DIMENSION: int = int(os.getenv("EMBEDDING_DIMENSION", "384"))

    # -------------------------------------------------------------
    # CHUNKING
    # -------------------------------------------------------------

    # Fallback max characters per chunk, used ONLY when a section/article
    # is too large to be one chunk (structure-first, size-limit-as-fallback,
    # per Step 5 of the original plan).
    MAX_CHUNK_CHARS: int = int(os.getenv("MAX_CHUNK_CHARS", "1500"))


# We create ONE instance of Settings and import THIS everywhere, instead
# of importing the class and instantiating it fresh in every file.
# This is a lightweight singleton pattern -- one shared settings object
# for the whole project.
settings = Settings()