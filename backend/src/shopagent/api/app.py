"""FastAPI main application setup and middleware configuration."""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shopagent.api.routers import (
    actions,
    auth,
    conversations,
    customer,
    guest,
    health,
    policies,
    staff,
)
from shopagent.core.config import get_settings
from shopagent.core.errors import AppError
from shopagent.rag.reranker import warm_up


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifespan with fail-fast health verification."""
    import logging

    from sqlalchemy import text

    from shopagent.agent.checkpoint import close_checkpointer, open_checkpointer
    from shopagent.agent.graph import get_agent_graph
    from shopagent.infra.db.session import get_engine

    logger = logging.getLogger("shopagent.startup")
    settings = get_settings()

    logger.info(
        "Khởi động ShopSupport AI API: env=%s, mode=%s, llm=%s",
        settings.ENVIRONMENT,
        settings.INTEGRATION_MODE,
        settings.LLM_PRIMARY_MODEL,
    )

    is_prod = settings.ENVIRONMENT.lower() in ("production", "prod")

    # Production fail-fast checks
    if is_prod:
        # 1. Secret validation
        if not settings.JWT_SECRET or settings.JWT_SECRET.startswith("dev_") or len(settings.JWT_SECRET) < 32:
            raise RuntimeError(
                "LỖI KHỞI ĐỘNG PRODUCTION: JWT_SECRET chưa được cấu hình an toàn (yêu cầu tối thiểu 32 ký tự ngẫu nhiên)."
            )

        # 2. Database connectivity
        try:
            engine = get_engine()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("Kết nối cơ sở dữ liệu xác nhận thành công.")
        except Exception as e:
            logger.critical("LỖI KHỞI ĐỘNG PRODUCTION: Không thể kết nối cơ sở dữ liệu: %s", e)
            raise RuntimeError(f"Database connection failed on startup: {e}") from e

    # Policy reranker: loaded at startup so the first policy question is fast and a missing model fails fast.
    try:
        if await asyncio.to_thread(warm_up):
            logger.info("Reranker chính sách đã nạp sẵn.")
    except Exception as e:
        logger.critical("Không nạp được reranker chính sách: %s", e)
        raise RuntimeError(f"Policy reranker failed to load on startup: {e}") from e

    # Checkpointer: opened inside the running loop (async Postgres pool) and wired into the graph.
    try:
        handle = await open_checkpointer()
        get_agent_graph(handle.saver)
        logger.info("LangGraph Checkpointer xác nhận sẵn sàng.")
    except Exception as e:
        logger.critical("Checkpointer khởi tạo thất bại: %s", e)
        raise RuntimeError(f"Checkpointer initialization failed on startup: {e}") from e

    yield

    # Shutdown actions
    await close_checkpointer()
    try:
        engine = get_engine()
        await engine.dispose()
        logger.info("Đã đóng kết nối database engine an toàn.")
    except Exception as e:
        logger.warning("Lỗi đóng database engine: %s", e)


def create_app() -> FastAPI:
    """Instantiate and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="ShopLab Customer Support AI Agent API",
        description="End-to-end AI Application: Policy RAG, Order Tracking, and Supervised Returns/Refunds",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS
    allowed_origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global standardized error handler
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": exc.error_code,
                    "message": str(exc),
                    "request_id": req_id,
                }
            },
        )

    # Register Routers
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(guest.router)
    app.include_router(conversations.router)
    app.include_router(actions.router)
    app.include_router(customer.router)
    app.include_router(policies.router)
    app.include_router(staff.router)

    return app


app = create_app()
