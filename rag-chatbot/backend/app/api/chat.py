"""
Chat API Router
────────────────
POST /api/chat/query — answer a natural-language question against indexed docs
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.schemas import ChatRequest, ChatResponse
from app.services.rag_chain import RAGChain, get_rag_chain
from app.services.document_processor import get_document_processor, DocumentProcessor

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/query", response_model=ChatResponse)
async def query_documents(
    request: ChatRequest,
    chain: RAGChain = Depends(get_rag_chain),
    processor: DocumentProcessor = Depends(get_document_processor),
):
    """
    Answer a natural-language question about one or more uploaded documents.

    The caller must supply:
      - session_id  : used for logging / future caching
      - document_ids: which indexed docs to search
      - question    : the user's query (max 2 000 chars)
      - chat_history: previous turns in this session (optional)
    """
    # Validate that requested documents exist
    for doc_id in request.document_ids:
        doc = processor.get_document(doc_id)
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{doc_id}' not found. Upload it first.",
            )
        if doc.status != "ready":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Document '{doc_id}' is still processing. Try again shortly.",
            )

    try:
        response = await chain.answer(request)
    except Exception as e:
        logger.error(f"RAG chain error for session {request.session_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate an answer. Please try again.",
        )

    return response
