"""
Vector Store Abstraction
────────────────────────
Supports two backends selectable via VECTOR_STORE_TYPE env var:

  • faiss  — local FAISS index (great for development / single-server prod)
  • pinecone — managed cloud vector DB (multi-instance / serverless friendly)

Both backends expose the same async interface so the rest of the app never
needs to know which backend is in use.

Design note: FAISS index is stored per-document in separate namespaced
sub-indices, then merged at query time.  This makes deletion O(1) (just
drop the sub-index file) rather than requiring a full rebuild.
"""

import logging
import os
import pickle
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from langchain.schema import Document as LCDocument
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

from app.core.config import settings

logger = logging.getLogger(__name__)


# ── Abstract base ─────────────────────────────────────────────────────────────

class VectorStoreBackend(ABC):
    @abstractmethod
    async def add_documents(self, document_id: str, docs: List[LCDocument]) -> None: ...

    @abstractmethod
    async def similarity_search(
        self,
        query: str,
        document_ids: List[str],
        k: int = settings.MAX_RETRIEVAL_CHUNKS,
    ) -> List[Tuple[LCDocument, float]]: ...

    @abstractmethod
    async def delete_document(self, document_id: str) -> None: ...


# ── FAISS backend ─────────────────────────────────────────────────────────────

class FAISSBackend(VectorStoreBackend):
    """
    One FAISS index per document stored under FAISS_INDEX_PATH/<document_id>.
    At query time we merge only the requested sub-indices, then search.
    This is memory-efficient for large document collections.
    """

    def __init__(self):
        self.index_dir = Path(settings.FAISS_INDEX_PATH)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.embeddings = OpenAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            openai_api_key=settings.OPENAI_API_KEY,
        )

    def _index_path(self, document_id: str) -> Path:
        return self.index_dir / document_id

    async def add_documents(self, document_id: str, docs: List[LCDocument]) -> None:
        idx = FAISS.from_documents(docs, self.embeddings)
        idx.save_local(str(self._index_path(document_id)))
        logger.info(f"FAISS: saved index for document {document_id}")

    async def similarity_search(
        self,
        query: str,
        document_ids: List[str],
        k: int = settings.MAX_RETRIEVAL_CHUNKS,
    ) -> List[Tuple[LCDocument, float]]:
        merged: Optional[FAISS] = None
        for doc_id in document_ids:
            p = self._index_path(doc_id)
            if not p.exists():
                logger.warning(f"FAISS: index not found for {doc_id}, skipping")
                continue
            idx = FAISS.load_local(
                str(p),
                self.embeddings,
                allow_dangerous_deserialization=True,
            )
            if merged is None:
                merged = idx
            else:
                merged.merge_from(idx)

        if merged is None:
            return []

        # similarity_search_with_score returns (doc, distance) — lower = closer
        results = merged.similarity_search_with_score(query, k=k)
        # Normalise to [0,1] relevance (1 = most relevant)
        normed = []
        for doc, score in results:
            # FAISS L2 distance: convert to a relevance-like score
            relevance = float(1 / (1 + score))
            normed.append((doc, relevance))
        return normed

    async def delete_document(self, document_id: str) -> None:
        import shutil
        p = self._index_path(document_id)
        if p.exists():
            shutil.rmtree(p)
            logger.info(f"FAISS: deleted index for {document_id}")


# ── Pinecone backend ──────────────────────────────────────────────────────────

class PineconeBackend(VectorStoreBackend):
    """
    Uses a single Pinecone index with document_id as a metadata filter.
    Requires: PINECONE_API_KEY, PINECONE_ENVIRONMENT, PINECONE_INDEX_NAME.

    Pinecone is preferred for production: managed, scalable, no local disk.
    """

    def __init__(self):
        try:
            from pinecone import Pinecone
            from langchain_pinecone import PineconeVectorStore
        except ImportError:
            raise ImportError("Install pinecone-client and langchain-pinecone for Pinecone support")

        self.embeddings = OpenAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            openai_api_key=settings.OPENAI_API_KEY,
        )
        pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        self.index = pc.Index(settings.PINECONE_INDEX_NAME)
        self._PineconeVectorStore = PineconeVectorStore
        logger.info(f"Pinecone: connected to index '{settings.PINECONE_INDEX_NAME}'")

    async def add_documents(self, document_id: str, docs: List[LCDocument]) -> None:
        self._PineconeVectorStore.from_documents(
            docs,
            self.embeddings,
            index_name=settings.PINECONE_INDEX_NAME,
        )
        logger.info(f"Pinecone: upserted {len(docs)} vectors for {document_id}")

    async def similarity_search(
        self,
        query: str,
        document_ids: List[str],
        k: int = settings.MAX_RETRIEVAL_CHUNKS,
    ) -> List[Tuple[LCDocument, float]]:
        vs = self._PineconeVectorStore(
            index=self.index,
            embedding=self.embeddings,
        )
        results = vs.similarity_search_with_score(
            query,
            k=k,
            filter={"document_id": {"$in": document_ids}},
        )
        return [(doc, float(score)) for doc, score in results]

    async def delete_document(self, document_id: str) -> None:
        # Delete all vectors with matching metadata (requires Pinecone metadata filtering)
        self.index.delete(filter={"document_id": {"$eq": document_id}})
        logger.info(f"Pinecone: deleted vectors for {document_id}")


# ── Singleton factory ─────────────────────────────────────────────────────────

_backend: Optional[VectorStoreBackend] = None


async def get_vector_store() -> VectorStoreBackend:
    global _backend
    if _backend is None:
        if settings.VECTOR_STORE_TYPE == "pinecone":
            _backend = PineconeBackend()
        else:
            _backend = FAISSBackend()
        logger.info(f"Vector store initialised: {settings.VECTOR_STORE_TYPE}")
    return _backend
