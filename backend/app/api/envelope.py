from typing import Any

from fastapi.responses import JSONResponse


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """成功信封：{ data, meta? }（0-D §1.3）。"""
    return {"data": data, "meta": meta or {}}


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    """错误信封：{ error: { code, message, details? } }（0-D §1.3/§1.4）。"""
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details}},
    )
