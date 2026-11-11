"""Health and readiness check endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.api.deps import get_db_session

router = APIRouter(tags=["Operations"])


@router.get("/healthz")
async def health_check():
    """Liveness probe."""
    return {"status": "ok"}


@router.get("/readyz")
async def readiness_check(session: AsyncSession = Depends(get_db_session)):
    """Readiness probe verifying DB connection."""
    try:
        await session.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@router.get("/version")
async def version_info():
    """Application version and metadata."""
    return {
        "version": "1.0.0",
        "service": "shop-support-agent",
        "environment": "simulated",
    }
