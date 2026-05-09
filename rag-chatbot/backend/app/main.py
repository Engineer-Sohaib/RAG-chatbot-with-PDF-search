"""
AI Document Search Chatbot - FastAPI Backend
Architecture: RAG (Retrieval-Augmented Generation) pipeline
- PDF ingestion → chunking → embedding → vector store
- Query → semantic search → LLM context injection → response
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.api import documents, chat, health
from app.core.config import settings
from app.core.rate_limiter import RateLimiter

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── App lifecycle ─────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise and tear down shared resources."""
    logger.info("🚀 Starting AI Document Search Chatbot backend...")
    logger.info(f"   Vector store: {settings.VECTOR_STORE_TYPE}")
    logger.info(f"   Embedding model: {settings.EMBEDDING_MODEL}")
    logger.info(f"   LLM model: {settings.LLM_MODEL}")
    yield
    logger.info("🛑 Shutting down backend...")


# ── App instance ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="AI Document Search Chatbot",
    description="RAG-powered chatbot for intelligent PDF document search",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# ── Middleware ────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# Only enforce trusted hosts in production
if settings.ENVIRONMENT == "production":
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)

rate_limiter = RateLimiter(
    requests_per_minute=settings.RATE_LIMIT_PER_MINUTE,
    requests_per_hour=settings.RATE_LIMIT_PER_HOUR,
)


@app.middleware("http")
async def add_request_timing(request: Request, call_next):
    """Log request timing and enforce rate limits."""
    start = time.perf_counter()
    client_ip = request.client.host if request.client else "unknown"

    # Rate limiting (skip for health checks)
    if not request.url.path.startswith("/api/health"):
        allowed, reason = rate_limiter.is_allowed(client_ip)
        if not allowed:
            logger.warning(f"Rate limit exceeded for {client_ip}: {reason}")
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded. {reason}"},
                headers={"Retry-After": "60"},
            )

    response = await call_next(request)
    duration = (time.perf_counter() - start) * 1000
    logger.info(
        f"{request.method} {request.url.path} → {response.status_code} [{duration:.1f}ms] {client_ip}"
    )
    response.headers["X-Process-Time-Ms"] = f"{duration:.1f}"
    return response


# ── Global exception handler ──────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again."},
    )


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router, prefix="/api", tags=["Health"])
app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
