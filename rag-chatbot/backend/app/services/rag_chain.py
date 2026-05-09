"""
RAG Chain Service
──────────────────
Orchestrates the full retrieval-augmented generation pipeline:

  1. Embed user question
  2. Retrieve top-k relevant chunks from vector store
  3. Build a grounded prompt (system + retrieved context + chat history)
  4. Call LLM and parse structured response with source citations

Key design decisions:
  • Conversation history is trimmed to MAX_CHAT_HISTORY_TURNS to bound
    token usage.  A production system would summarise older turns instead
    of dropping them (see Enhancement notes in README).
  • The prompt explicitly instructs the model to cite page numbers and
    to say "I don't know" rather than hallucinate when context is absent.
  • Source chunks are deduplicated by (document_id, page_number) before
    being returned to the client.
"""

import logging
import time
from typing import List, Tuple

from langchain.schema import Document as LCDocument
from langchain_openai import ChatOpenAI
from langchain.schema.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
)

from app.core.config import settings
from app.models.schemas import ChatMessage, ChatRequest, ChatResponse, SourceChunk
from app.services.vector_store import get_vector_store

logger = logging.getLogger(__name__)

# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a precise, helpful document assistant. You answer questions \
strictly based on the provided document excerpts.

Rules:
1. Only use information from the DOCUMENT EXCERPTS below.
2. Always cite sources: mention the filename and page number for every claim.
   Format: (Source: <filename>, p.<page>)
3. If the excerpts do not contain enough information to answer, say:
   "I couldn't find sufficient information in the provided documents to answer that question."
4. Never invent facts, statistics, or quotes not present in the excerpts.
5. Be concise but thorough. Use bullet points for lists when appropriate.
6. If multiple documents contain relevant information, synthesise them clearly.
"""


# ── Helper: format chat history ───────────────────────────────────────────────

def _build_message_history(history: List[ChatMessage], max_turns: int) -> list:
    """Convert stored chat history to LangChain message objects (most recent N turns)."""
    # Keep only the last N turns to limit token usage
    trimmed = history[-(max_turns * 2):]  # each turn = 1 user + 1 assistant
    lc_msgs = []
    for msg in trimmed:
        if msg.role == "user":
            lc_msgs.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            lc_msgs.append(AIMessage(content=msg.content))
    return lc_msgs


def _format_context(chunks: List[Tuple[LCDocument, float]]) -> str:
    """Render retrieved chunks into a numbered context block for the prompt."""
    if not chunks:
        return "No relevant document excerpts found."

    lines = []
    for i, (doc, score) in enumerate(chunks, 1):
        meta = doc.metadata
        lines.append(
            f"[Excerpt {i}]\n"
            f"File: {meta.get('filename', 'unknown')}\n"
            f"Page: {meta.get('page_number', '?')}\n"
            f"Relevance: {score:.2f}\n"
            f"---\n{doc.page_content}\n"
        )
    return "\n".join(lines)


def _deduplicate_sources(chunks: List[Tuple[LCDocument, float]]) -> List[SourceChunk]:
    """Return unique (document_id, page_number) sources, highest relevance first."""
    seen = set()
    sources = []
    for doc, score in sorted(chunks, key=lambda x: x[1], reverse=True):
        meta = doc.metadata
        key = (meta.get("document_id", ""), meta.get("page_number", 0))
        if key not in seen:
            seen.add(key)
            sources.append(
                SourceChunk(
                    document_id=meta.get("document_id", ""),
                    filename=meta.get("filename", "unknown"),
                    page_number=meta.get("page_number", 0),
                    chunk_text=doc.page_content[:300] + ("…" if len(doc.page_content) > 300 else ""),
                    relevance_score=round(score, 4),
                )
            )
    return sources


# ── Main RAG service ──────────────────────────────────────────────────────────

class RAGChain:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
            openai_api_key=settings.OPENAI_API_KEY,
        )

    async def answer(self, request: ChatRequest) -> ChatResponse:
        t0 = time.perf_counter()

        # ── 1. Retrieve relevant chunks ───────────────────────────────────────
        vs = await get_vector_store()
        raw_chunks = await vs.similarity_search(
            query=request.question,
            document_ids=request.document_ids,
            k=settings.MAX_RETRIEVAL_CHUNKS,
        )
        logger.info(
            f"[{request.session_id}] Retrieved {len(raw_chunks)} chunks "
            f"for: '{request.question[:80]}'"
        )

        # ── 2. Build prompt messages ──────────────────────────────────────────
        context_text = _format_context(raw_chunks)
        history_msgs = _build_message_history(
            request.chat_history, settings.MAX_CHAT_HISTORY_TURNS
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            *history_msgs,
            HumanMessage(
                content=(
                    f"DOCUMENT EXCERPTS:\n{context_text}\n\n"
                    f"QUESTION: {request.question}"
                )
            ),
        ]

        # ── 3. Call LLM ───────────────────────────────────────────────────────
        response = await self.llm.ainvoke(messages)
        answer_text = response.content
        tokens = getattr(response, "usage_metadata", {})
        total_tokens = (
            tokens.get("total_tokens") if isinstance(tokens, dict) else None
        )

        # ── 4. Build response ─────────────────────────────────────────────────
        sources = _deduplicate_sources(raw_chunks)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        logger.info(
            f"[{request.session_id}] Answer generated in {elapsed_ms:.0f}ms "
            f"({total_tokens} tokens)"
        )

        return ChatResponse(
            session_id=request.session_id,
            answer=answer_text,
            sources=sources,
            model_used=settings.LLM_MODEL,
            tokens_used=total_tokens,
            processing_time_ms=round(elapsed_ms, 1),
        )


# ── Singleton factory ─────────────────────────────────────────────────────────
_chain: RAGChain | None = None


def get_rag_chain() -> RAGChain:
    global _chain
    if _chain is None:
        _chain = RAGChain()
    return _chain
