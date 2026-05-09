"""
Centralised configuration — all secrets and tunables live here.
Values are read from environment variables (or a .env file via python-dotenv).
"""

from functools import lru_cache
from typing import List, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── App ───────────────────────────────────────────────────────────────────
    ENVIRONMENT: Literal["development", "production", "test"] = "development"
    APP_NAME: str = "AI Document Search Chatbot"
    SECRET_KEY: str = Field(default="change-me-in-production", min_length=16)

    # ── OpenAI ────────────────────────────────────────────────────────────────
    OPENAI_API_KEY: str = Field(..., description="Your OpenAI API key")
    LLM_MODEL: str = "gpt-4o-mini"           # Cost-effective; swap to gpt-4o for better quality
    EMBEDDING_MODEL: str = "text-embedding-3-small"  # 1536 dims, fast, cheap
    LLM_TEMPERATURE: float = 0.0             # 0 = deterministic / factual answers
    LLM_MAX_TOKENS: int = 1024

    # ── Vector store ──────────────────────────────────────────────────────────
    # Set VECTOR_STORE_TYPE="pinecone" and provide Pinecone creds for cloud persistence.
    # Default is "faiss" (local, no extra infra needed).
    VECTOR_STORE_TYPE: Literal["faiss", "pinecone"] = "faiss"
    FAISS_INDEX_PATH: str = "./data/faiss_index"

    # Pinecone (only required when VECTOR_STORE_TYPE="pinecone")
    PINECONE_API_KEY: str = ""
    PINECONE_ENVIRONMENT: str = ""           # e.g. "us-east-1-aws"
    PINECONE_INDEX_NAME: str = "rag-chatbot"

    # ── Document processing ───────────────────────────────────────────────────
    CHUNK_SIZE: int = 1000          # Characters per chunk
    CHUNK_OVERLAP: int = 200        # Overlap keeps context across chunk boundaries
    MAX_RETRIEVAL_CHUNKS: int = 5   # k nearest neighbours returned per query
    MAX_FILE_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: List[str] = [".pdf"]

    # ── Storage ───────────────────────────────────────────────────────────────
    UPLOAD_DIR: str = "./data/uploads"
    MAX_STORED_DOCUMENTS: int = 100

    # ── Rate limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 20
    RATE_LIMIT_PER_HOUR: int = 200

    # ── CORS / Security ───────────────────────────────────────────────────────
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "https://your-app.vercel.app",   # ← Replace with your Vercel URL
    ]
    ALLOWED_HOSTS: List[str] = ["*"]

    # ── Session ───────────────────────────────────────────────────────────────
    MAX_CHAT_HISTORY_TURNS: int = 10   # Older messages are summarised to save tokens

    @field_validator("OPENAI_API_KEY")
    @classmethod
    def openai_key_must_be_set(cls, v: str) -> str:
        if not v or v.startswith("sk-your"):
            raise ValueError("OPENAI_API_KEY must be a real API key")
        return v

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    model_config = {"env_file": ".env", "case_sensitive": True}


@lru_cache
def get_settings() -> Settings:
    """Cached singleton — cheap to call anywhere."""
    return Settings()


settings = get_settings()
