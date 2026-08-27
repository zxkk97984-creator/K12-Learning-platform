import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.envelope import error_response, ok
from app.config import settings
from app.infrastructure.metrics_registry import metrics_registry
from app.infrastructure.rate_limit import rate_limiter
from app.infrastructure.observability import setup_access_logging
from app.modules.admin.router import router as admin_router
from app.modules.content.router import router as content_router
from app.modules.conversation.router import router as conversation_router
from app.modules.identity.router import router as identity_router
from app.modules.knowledge.router import router as knowledge_router
from app.modules.learning.router import router as learning_router
from app.modules.memory.router import router as memory_router
from app.modules.quiz.router import router as quiz_router
from app.modules.recommendation.router import router as recommendation_router
from app.modules.voice.ws import router as voice_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 2-B 接入数据库连接池；当前无任何外部依赖
    yield


setup_access_logging()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def request_observability_middleware(request: Request, call_next):
    """生成/透传 X-Request-ID，写回响应头，采集指标并输出访问日志。"""
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id

    # Phase 5-A 整改 1：普通 /api/v1 请求按 client IP 全局限流。
    # 排除：/auth/login（自带更严格的 ip+username 维度限流，避免双重计数）、
    # /health 与 /metrics（探活与监控抓取不限制）。
    path = request.url.path
    if (
        settings.rate_limit_enabled
        and path.startswith("/api/v1")
        and not path.endswith("/auth/login")
        and path not in ("/metrics", "/health")
    ):
        client_ip = request.client.host if request.client else "unknown"
        verdict = rate_limiter.check(
            f"api:{client_ip}",
            limit=settings.rate_limit_api_per_minute,
            window_seconds=60,
        )
        if not verdict.allowed:
            resp = error_response(429, "RATE_LIMITED", "too many requests, retry later")
            resp.headers["Retry-After"] = str(verdict.retry_after)
            resp.headers["X-Request-ID"] = request_id
            return resp

    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - started) * 1000, 2)

    response.headers["X-Request-ID"] = request_id
    metrics_registry.observe(
        method=request.method, status=response.status_code, duration_ms=duration_ms
    )

    logging.getLogger("shuangling.access").info(
        "access",
        extra={
            "http": {
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "request_id": request_id,
                # 绝不记录 Authorization/密码/正文；仅安全元数据
                "user_id": getattr(request.state, "user_id", None),
            }
        },
    )
    return response


app.include_router(identity_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(content_router, prefix="/api/v1")
app.include_router(knowledge_router, prefix="/api/v1")
app.include_router(learning_router, prefix="/api/v1")
app.include_router(conversation_router, prefix="/api/v1")
app.include_router(memory_router, prefix="/api/v1")
app.include_router(quiz_router, prefix="/api/v1")
app.include_router(recommendation_router, prefix="/api/v1")
app.include_router(voice_router)


def _error_body_with_request_id(request: Request, status_code: int, code: str, message: str, details=None, extra_headers=None):
    body = error_response(status_code, code, message, details)
    request_id = getattr(request.state, "request_id", None) or str(uuid4())
    body.headers["X-Request-ID"] = request_id
    for key, value in (extra_headers or {}).items():
        body.headers[key] = value
    return body


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        return _error_body_with_request_id(
            request,
            exc.status_code,
            exc.detail["code"],
            exc.detail["message"],
            exc.detail.get("details"),
            extra_headers=getattr(exc, "headers", None),
        )
    return _error_body_with_request_id(request, exc.status_code, "HTTP_ERROR", str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return _error_body_with_request_id(
        request,
        422,
        "VALIDATION_ERROR",
        "request validation failed",
        details={"errors": exc.errors()},
    )


@app.get("/metrics", include_in_schema=False)
async def prometheus_metrics() -> Response:
    return Response(
        content=metrics_registry.render(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """健康检查：不依赖数据库。"""
    return {"status": "ok"}


@app.get(f"{settings.api_v1_prefix}/ping")
async def ping() -> dict[str, Any]:
    """版本前缀占位：证明 /api/v1 前缀可用（0-D Base URL 约定）。"""
    return ok({"pong": True})
