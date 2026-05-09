"""Health check endpoints for load balancers and uptime monitors."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    vector_store: str
    llm_model: str


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Liveness probe — always returns 200 if the process is running."""
    return HealthResponse(
        status="ok",
        version="1.0.0",
        environment=settings.ENVIRONMENT,
        vector_store=settings.VECTOR_STORE_TYPE,
        llm_model=settings.LLM_MODEL,
    )
