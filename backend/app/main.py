import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import collections, conversations, documents, settings
from app.core.config import get_settings
from app.core.errors import AppError, app_error_handler
from app.core.logging import configure_logging
from app.services.ingestion import mark_stale_documents_failed
from app.services.local_user import ensure_local_user
from app.services.model_provider import close_http_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    runtime_settings = get_settings()
    runtime_settings.validate_runtime_secrets()
    runtime_settings.upload_dir.mkdir(parents=True, exist_ok=True)
    ensure_local_user()
    if runtime_settings.ingestion_mode == "inline":
        # worker 模式下中断任务由 worker 的 reaper 重新入队，不能直接判失败。
        mark_stale_documents_failed()
    try:
        yield
    finally:
        close_http_client()


def create_app() -> FastAPI:
    runtime_settings = get_settings()
    app = FastAPI(
        title=runtime_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    allowed_origins = {
        origin.rstrip("/").lower() for origin in runtime_settings.cors_origin_list
    }

    @app.middleware("http")
    async def reject_untrusted_origin(request: Request, call_next):
        """本地单用户仍拒绝跨站写请求；命令行客户端通常不发送 Origin。"""
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/").lower() not in allowed_origins:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": {
                            "code": "ORIGIN_REJECTED",
                            "message": "请求来源不在允许列表中",
                        }
                    },
                )
        return await call_next(request)

    app.add_exception_handler(AppError, app_error_handler)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, __: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "VALIDATION_ERROR", "message": "请求参数不合法"}},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("未处理异常：%s", exc.__class__.__name__)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "系统内部错误，请稍后重试",
                }
            },
        )

    app.include_router(settings.router)
    app.include_router(collections.router)
    app.include_router(documents.router)
    app.include_router(conversations.router)

    @app.get("/api/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
