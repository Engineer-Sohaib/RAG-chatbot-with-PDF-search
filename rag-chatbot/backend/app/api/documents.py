"""
Documents API Router
─────────────────────
POST /api/documents/upload   — ingest a PDF
GET  /api/documents/         — list all indexed documents
DELETE /api/documents/{id}   — remove a document and its vectors
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status

from app.core.config import settings
from app.models.schemas import (
    DeleteDocumentResponse,
    DocumentListResponse,
    DocumentMetadata,
    UploadResponse,
)
from app.services.document_processor import get_document_processor, DocumentProcessor

logger = logging.getLogger(__name__)
router = APIRouter()


def _validate_upload(file: UploadFile) -> None:
    """Gate-check file before reading bytes into memory."""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Only {settings.ALLOWED_EXTENSIONS} files are supported.",
        )
    # Content-type check (defense-in-depth; can be spoofed)
    if file.content_type and "pdf" not in file.content_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File must be a PDF.",
        )


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    processor: DocumentProcessor = Depends(get_document_processor),
):
    """
    Upload and index a PDF document.
    File is read in full then validated for size; streaming would be needed
    for very large files but adds complexity not worth it at this scale.
    """
    _validate_upload(file)

    content = await file.read()

    # Size check after read (Content-Length header can be absent or spoofed)
    if len(content) > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {settings.MAX_FILE_SIZE_MB}MB limit.",
        )

    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # Check document cap
    existing = processor.list_documents()
    if len(existing) >= settings.MAX_STORED_DOCUMENTS:
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail=f"Maximum of {settings.MAX_STORED_DOCUMENTS} documents reached. Delete some first.",
        )

    try:
        meta = await processor.process_upload(file.filename or "document.pdf", content)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Upload failed for {file.filename}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process document. Ensure it contains readable text.",
        )

    return UploadResponse(
        document_id=meta.document_id,
        filename=meta.filename,
        message=f"Successfully indexed '{meta.filename}' — {meta.chunk_count} chunks across {meta.page_count} pages.",
        chunk_count=meta.chunk_count,
        page_count=meta.page_count,
    )


@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    processor: DocumentProcessor = Depends(get_document_processor),
):
    """Return all indexed documents."""
    docs = processor.list_documents()
    return DocumentListResponse(documents=docs, total=len(docs))


@router.get("/{document_id}", response_model=DocumentMetadata)
async def get_document(
    document_id: str,
    processor: DocumentProcessor = Depends(get_document_processor),
):
    """Return metadata for a single document."""
    doc = processor.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return doc


@router.delete("/{document_id}", response_model=DeleteDocumentResponse)
async def delete_document(
    document_id: str,
    processor: DocumentProcessor = Depends(get_document_processor),
):
    """Delete a document and remove its vectors from the store."""
    deleted = await processor.delete_document(document_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return DeleteDocumentResponse(
        document_id=document_id,
        message="Document and associated vectors deleted successfully.",
    )
