"""结构化 JSON 输出的公共工具。

从 dai-experiment-platform `app/services/ai_client.py` 移植（逐字保留行为）：
- `extract_json_object` —— 容忍 markdown fence 与前后缀说明文字
- `sanitize_ai_error` —— 错误文本脱敏，绝不让 Bearer / sk- 凭证进入日志或响应
- `normalize_chat_endpoint` —— base_url → /v1/chat/completions
- `AIServiceError` —— 带 retryable 标记的结构化异常
- `OPERATION_MAX_TOKENS` —— **fail-closed** 的每操作 completion 预算表：
  未登记的操作直接拒绝调用，保证每次 AI 调用都有明确上限。

这些函数零领域耦合，是 dai 中被验证得最充分的代码之一。
"""

from __future__ import annotations

import json
import re

# ═══════════════════════════════════════════════════════════════
# 每操作 completion 预算（max_tokens）—— fail-closed 注册表
#
# dai 的实测经验（ai_client.py:20-31）：deepseek-v4-flash 是 reasoning 模型，
# reasoning_content 与最终 content 共用 max_tokens；预算必须给两者同时留空间，
# 否则会出现「推理耗尽 token、content 为空」。1500 实测不足，8000 可用。
# 新增操作必须在此登记，否则 chat_json 会直接抛错。
# ═══════════════════════════════════════════════════════════════

OPERATION_MAX_TOKENS: dict[str, int] = {
    "codelab_grading": 8000,       # 单份代码的 A/Q 评分 + 学生反馈
    "codelab_rubric": 8000,        # Rubric 生成（每个任务一次，之后缓存复用）
}

_RETRYABLE_HTTP_STATUS = {429, 500, 502, 503, 504}
_NON_RETRYABLE_HTTP_STATUS = {401, 403}


class AIServiceError(RuntimeError):
    """AI 服务异常，含可重试标记（dai ai_client.py:34-40）。"""

    def __init__(self, code: str, message: str, *, retryable: bool):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def is_retryable_status(status_code: int) -> bool:
    return status_code in _RETRYABLE_HTTP_STATUS


def is_non_retryable_status(status_code: int) -> bool:
    return status_code in _NON_RETRYABLE_HTTP_STATUS


def sanitize_ai_error(text: str) -> str:
    """删除错误文本中的 Bearer token 和疑似 API Key（dai ai_client.py:43-52）。"""
    text = re.sub(r"Bearer\s+\S+", "Bearer ***", text)
    text = re.sub(r"sk-[a-zA-Z0-9]+", "sk-***", text)
    if len(text) > 1000:
        text = text[:1000]
    return text


def normalize_chat_endpoint(base_url: str) -> str:
    """规范化聊天补全端点（dai ai_client.py:55-60）。"""
    url = base_url.rstrip("/")
    # 霜铃的 .env 里 AI_BASE_URL 可能是 https://api.deepseek.com（无 /v1）
    # 或已带 /v1 的网关地址，两种都要能拼对。
    if url.endswith("/v1"):
        return f"{url}/chat/completions"
    return f"{url}/v1/chat/completions"


def extract_json_object(text: str) -> dict:
    """从文本中提取 JSON 对象——支持 markdown fence 和纯 JSON（dai ai_client.py:63-74）。"""
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        text = brace_match.group(0)
    return json.loads(text)
