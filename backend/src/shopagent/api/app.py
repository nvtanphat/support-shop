"""FastAPI main application setup and middleware configuration."""

from __future__ import annotations

from contextlib import asynccontextmanager
import uuid
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shopagent.api.routers import actions, auth, conversations, customer, guest, health, staff
from shopagent.core.config import get_settings
from shopagent.core.errors import AppError


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifespan."""
    # Startup actions
    yield
    # Shutdown actions


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
    app.include_router(staff.router)

    return app


app = create_app()
