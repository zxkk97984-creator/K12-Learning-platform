from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.envelope import error_response, ok
from app.config import settings
from app.modules.identity.router import router as identity_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 2-B 接入数据库连接池；当前无任何外部依赖
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(identity_router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    """健康检查：不依赖数据库（2-B 前 DB 未起）。"""
    return {"status": "ok"}


@app.get(f"{settings.api_v1_prefix}/ping")
async def ping() -> dict[str, Any]:
    """版本前缀占位：证明 /api/v1 前缀可用（0-D Base URL 约定）。"""
    return ok({"pong": True})


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_request: Request, exc: StarletteHTTPException):
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        return error_response(
            exc.status_code,
            exc.detail["code"],
            exc.detail["message"],
            exc.detail.get("details"),
        )
    return error_response(exc.status_code, "HTTP_ERROR", str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError):
    return error_response(
        422,
        "VALIDATION_ERROR",
        "request validation failed",
        details={"errors": exc.errors()},
    )
