"""请求 ID、结构化访问日志与指标采集中间件（Phase 5-A）。

安全约束：日志绝不包含 Authorization/Cookie 头、密码字段、消息正文或密钥；
仅记录 method/path/status/duration_ms/request_id/user_id 等元数据。
"""

import time
from uuid import uuid4

from app.infrastructure.metrics_registry import metrics_registry

import logging

access_logger = logging.getLogger("shuangling.access")


class JSONAccessFormatter(logging.Formatter):
    """单行 JSON 访问日志；仅输出白名单元数据字段。"""

    def format(self, record: logging.LogRecord) -> str:
        payload = getattr(record, "http", None)
        if not isinstance(payload, dict):
            # 非 access 记录走标准格式，避免吞掉其他日志
            return super().format(record)
        allowed = {
            "method",
            "path",
            "status",
            "duration_ms",
            "request_id",
            "user_id",
        }
        safe = {k: v for k, v in payload.items() if k in allowed}
        import json as _json

        return _json.dumps(safe, ensure_ascii=False)


_configured = False


def setup_access_logging() -> None:
    """为 shuangling.access 挂载 StreamHandler + JSONFormatter（幂等）。"""
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JSONAccessFormatter())
    access_logger.addHandler(handler)
    access_logger.setLevel(logging.INFO)
    access_logger.propagate = False  # 不向 root 冒泡，避免重复/泄漏敏感字段
    _configured = True


