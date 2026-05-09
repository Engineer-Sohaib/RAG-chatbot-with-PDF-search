"""
Document Processing Service
────────────────────────────
Responsibilities:
1. Validate and persist uploaded PDF files
2. Extract text with page-level metadata (PyMuPDF / pdfplumber)
3. Chunk text with RecursiveCharacterTextSplitter (preserves paragraph boundaries)
4. Embed chunks and upsert into the vector store
5. Maintain a lightweight JSON document registry (swap for PostgreSQL in prod)

Key architectural decision: metadata is stored alongside every vector so that
retrieval results can immediately reference filename + page number without a
second DB lookup.
"""

import hashlib
import json
import logging
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF — fast, no Java dependency
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings

from app.core.config import settings
from app.models.schemas import DocumentMetadata
from app.services.vector_store import get_vector_store

logger = logging.getLogger(__name__)

# ── Document registry (JSON file — replace with DB in production) ──────────────
REGISTRY_PATH = Path(settings.UPLOAD_DIR) / "registry.json"


def _load_registry() -> Dict:
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text())
    return {}


def _save_registry(data: Dict) -> None:
    REGISTRY_PATH.write_text(json.dumps(data, indent=2, default=str))


# ── PDF utilities ─────────────────────────────────────────────────────────────

def extract_pages(pdf_path: str) -> List[Tuple[int, str]]:
    """Return list of (page_number, text) tuples. Page numbers are 1-indexed."""
    doc = fitz.open(pdf_path)
    pages = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")
        if text.strip():
            pages.append((page_num + 1, text))
    doc.close()
    return pages


def chunk_pages(
    pages: List[Tuple[int, str]],
    chunk_size: int = settings.CHUNK_SIZE,
    chunk_overlap: int = settings.CHUNK_OVERLAP,
) -> List[Dict]:
    """
    Split each page's text into overlapping chunks.
    Each chunk carries metadata: source_page, char_start.

    Using RecursiveCharacterTextSplitter so it tries to split on paragraph/
    sentence boundaries before falling back to arbitrary character positions.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = []
    for page_num, text in pages:
        sub_chunks = splitter.split_text(text)
        for idx, chunk_text in enumerate(sub_chunks):
            chunks.append(
                {
                    "text": chunk_text,
                    "page_number": page_num,
                    "chunk_index": idx,
                }
            )
    return chunks


# ── Main service ──────────────────────────────────────────────────────────────

class DocumentProcessor:
    def __init__(self):
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        self.embeddings = OpenAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            openai_api_key=settings.OPENAI_API_KEY,
        )

    async def process_upload(self, filename: str, file_bytes: bytes) -> DocumentMetadata:
        """
        Full ingestion pipeline:
          save → extract → chunk → embed → upsert → register
        Returns metadata once indexing is complete.
        """
        t0 = time.perf_counter()
        document_id = str(uuid4())

        # ── 1. Persist raw file ───────────────────────────────────────────────
        safe_name = Path(filename).name  # strip any path traversal
        file_path = Path(settings.UPLOAD_DIR) / f"{document_id}_{safe_name}"
        file_path.write_bytes(file_bytes)
        logger.info(f"[{document_id}] Saved {len(file_bytes):,} bytes → {file_path}")

        # ── 2. Extract text ───────────────────────────────────────────────────
        pages = extract_pages(str(file_path))
        if not pages:
            file_path.unlink(missing_ok=True)
            raise ValueError("PDF contains no extractable text (may be scanned image).")
        logger.info(f"[{document_id}] Extracted {len(pages)} pages")

        # ── 3. Chunk ──────────────────────────────────────────────────────────
        chunks = chunk_pages(pages)
        logger.info(f"[{document_id}] Generated {len(chunks)} chunks")

        # ── 4. Build LangChain Documents for vector store ─────────────────────
        from langchain.schema import Document as LCDocument

        lc_docs = [
            LCDocument(
                page_content=c["text"],
                metadata={
                    "document_id": document_id,
                    "filename": safe_name,
                    "page_number": c["page_number"],
                    "chunk_index": c["chunk_index"],
                },
            )
            for c in chunks
        ]

        # ── 5. Embed & upsert ─────────────────────────────────────────────────
        vs = await get_vector_store()
        await vs.add_documents(document_id, lc_docs)
        logger.info(f"[{document_id}] Upserted {len(lc_docs)} vectors")

        # ── 6. Register ───────────────────────────────────────────────────────
        meta = DocumentMetadata(
            document_id=document_id,
            filename=safe_name,
            file_size_bytes=len(file_bytes),
            page_count=len(pages),
            chunk_count=len(chunks),
            uploaded_at=datetime.utcnow(),
            status="ready",
        )
        registry = _load_registry()
        registry[document_id] = meta.model_dump()
        _save_registry(registry)

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(f"[{document_id}] Processing complete in {elapsed:.0f}ms")
        return meta

    async def delete_document(self, document_id: str) -> bool:
        """Remove vectors, file, and registry entry."""
        registry = _load_registry()
        if document_id not in registry:
            return False

        meta = registry[document_id]
        # Remove from vector store
        vs = await get_vector_store()
        await vs.delete_document(document_id)

        # Remove file
        file_path = Path(settings.UPLOAD_DIR) / f"{document_id}_{meta['filename']}"
        file_path.unlink(missing_ok=True)

        # Remove from registry
        del registry[document_id]
        _save_registry(registry)
        logger.info(f"Deleted document {document_id}")
        return True

    def list_documents(self) -> List[DocumentMetadata]:
        registry = _load_registry()
        return [DocumentMetadata(**v) for v in registry.values()]

    def get_document(self, document_id: str) -> Optional[DocumentMetadata]:
        registry = _load_registry()
        if document_id not in registry:
            return None
        return DocumentMetadata(**registry[document_id])


# ── Singleton factory ─────────────────────────────────────────────────────────
_processor: Optional[DocumentProcessor] = None


def get_document_processor() -> DocumentProcessor:
    global _processor
    if _processor is None:
        _processor = DocumentProcessor()
    return _processor
