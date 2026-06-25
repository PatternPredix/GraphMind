"""Application configuration loaded from environment variables / .env file."""
import os

from dotenv import load_dotenv

# Load backend/.env regardless of the process working directory, so the same
# database and secret are used whether the server is launched from the repo
# root, the backend folder, or via an installer-generated service.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_BACKEND_DIR, ".env"))


def _default_sqlite_path() -> str:
    """A stable, absolute SQLite path next to the backend folder."""
    return "sqlite:///" + os.path.join(_BACKEND_DIR, "annotation.db")


class Settings:
    # Database. Use PostgreSQL in production, e.g.:
    #   postgresql+psycopg2://annotator:secret@localhost:5432/annotation
    # Falls back to a local SQLite file for zero-setup development.
    DATABASE_URL: str = os.getenv("DATABASE_URL", _default_sqlite_path())

    # Auth
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "720"))
    ALGORITHM: str = "HS256"

    # First registered user becomes admin; afterwards only admins create users
    # unless open registration is enabled.
    ALLOW_OPEN_REGISTRATION: bool = os.getenv("ALLOW_OPEN_REGISTRATION", "false").lower() == "true"

    # Directory where trained models are stored, per project.
    MODELS_DIR: str = os.getenv("MODELS_DIR", os.path.join(_BACKEND_DIR, "trained_models"))

    # Default minimum number of human annotations per entity/relation type
    # before the Auto-Annotate button unlocks (overridable per project).
    DEFAULT_AUTO_ANNOTATE_THRESHOLD: int = int(os.getenv("DEFAULT_AUTO_ANNOTATE_THRESHOLD", "20"))

    # Hugging Face model used for relation extraction fine-tuning.
    RE_BASE_MODEL: str = os.getenv("RE_BASE_MODEL", "distilbert-base-uncased")

    # spaCy base config for NER training ("blank:en" trains from scratch;
    # set to an installed pipeline name to start from pretrained vectors).
    NER_BASE_MODEL: str = os.getenv("NER_BASE_MODEL", "blank:en")
    NER_TRAINING_ITERATIONS: int = int(os.getenv("NER_TRAINING_ITERATIONS", "30"))

    # Sentence-embedding model used for embedding-based relation rules
    # (a BERT-family bi-encoder; not an LLM). Runs on CPU/MPS/CUDA.
    EMBEDDING_MODEL: str = os.getenv(
        "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
    )
    # Default cosine-similarity threshold for relation rules (overridable per rule).
    DEFAULT_RELATION_RULE_THRESHOLD: float = float(
        os.getenv("DEFAULT_RELATION_RULE_THRESHOLD", "0.55")
    )


settings = Settings()
