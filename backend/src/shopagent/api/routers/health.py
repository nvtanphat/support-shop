"""Health and readiness check endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.agent.checkpoint import get_default_checkpointer
from shopagent.api.deps import get_db_session
from shopagent.infra.db.tables import PolicyChunkModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Operations"])


@router.get("/healthz")
@router.get("/health")
async def health_check():
    """Liveness probe."""
    return {"status": "ok"}


@router.get("/readyz")
@router.get("/ready")
async def readiness_check(session: AsyncSession = Depends(get_db_session)):
    """Readiness probe verifying DB connection and persistent checkpointer."""
    checks: dict[str, str] = {}
    is_healthy = True

    # 1. Database check
    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = "connected"
    except Exception as e:
        logger.error("Readiness check DB connection failed: %s", e)
        checks["database"] = f"unhealthy: {e}"
        is_healthy = False

    # 2. Checkpointer check
    try:
        checkpointer = get_default_checkpointer()
        if checkpointer is not None:
            checks["checkpointer"] = "ready"
        else:
            checks["checkpointer"] = "not_initialized"
            is_healthy = False
    except Exception as e:
        logger.error("Readiness check checkpointer failed: %s", e)
        checks["checkpointer"] = f"unhealthy: {e}"
        is_healthy = False

    # 3. Policy index: policy lookups are impossible (and say so) until the indexer has run
    try:
        indexed = (await session.execute(select(func.count(PolicyChunkModel.id)))).scalar_one()
        checks["policy_index"] = f"{indexed} clauses" if indexed else "empty: run `shopagent index-policies`"
        is_healthy = is_healthy and indexed > 0
    except Exception as e:
        logger.error("Readiness check policy index failed: %s", e)
        checks["policy_index"] = f"unhealthy: {e}"
        is_healthy = False

    if not is_healthy:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy", "checks": checks},
        )

    return {"status": "ready", "checks": checks}


@router.get("/version")
async def version_info():
    """Application version and metadata."""
    return {
        "version": "1.0.0",
        "service": "shop-support-agent",
        "environment": "simulated",
    }
