"""
Shared Pydantic models — used for request validation and response serialisation.
"""

from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


# ── Document models ───────────────────────────────────────────────────────────

class DocumentMetadata(BaseModel):
    document_id: str
    filename: str
    file_size_bytes: int
    page_count: int
    chunk_count: int
    uploaded_at: datetime
    status: str  # "processing" | "ready" | "error"


class DocumentListResponse(BaseModel):
    documents: List[DocumentMetadata]
    total: int


class DeleteDocumentResponse(BaseModel):
    document_id: str
    message: str


# ── Chat models ───────────────────────────────────────────────────────────────

class SourceChunk(BaseModel):
    """A retrieved document chunk cited in an answer."""
    document_id: str
    filename: str
    page_number: int
    chunk_text: str
    relevance_score: float


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatRequest(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    document_ids: List[str] = Field(
        ...,
        description="Which uploaded documents to search against",
        min_length=1,
    )
    question: str = Field(..., min_length=1, max_length=2000)
    chat_history: List[ChatMessage] = Field(default_factory=list)

    @field_validator("question")
    @classmethod
    def sanitise_question(cls, v: str) -> str:
        # Strip leading/trailing whitespace; basic XSS guard (no HTML)
        v = v.strip()
        if not v:
            raise ValueError("Question cannot be empty")
        return v


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    sources: List[SourceChunk]
    model_used: str
    tokens_used: Optional[int] = None
    processing_time_ms: float


# ── Upload models ─────────────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    document_id: str
    filename: str
    message: str
    chunk_count: int
    page_count: int
