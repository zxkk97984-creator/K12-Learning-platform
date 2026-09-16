"""长对话输入窗口（T20 §20a）：摘要 + 摘要边界之后的最近完整消息，按预算截取。

原则：
- 摘要已覆盖到的消息边界（message_covered_count）之后的最近消息才随本次请求发送，
  未摘要的早期消息绝不"摘要后又发全量"（避免与摘要重复、控制输入长度/成本）；
- 有摘要时发送 = [system prompt 含摘要] + [边界后最近消息]，按 token 预算取舍，
  始终保留最近一轮（学生的当前问题）；
- 无摘要时使用最近窗口，并在返回中明确"较早上下文可能不可用"；
- 只做纯计算（不触发 I/O），便于单元测试。

估算方法：以"字符数估算 token"用于截取预算（非实际 token 计费口径），
实际 token 由 provider 返回的 usage 为准（见 T20 §20b）。
"""

from dataclasses import dataclass, field
from typing import Any

# 每字符估算 token 的保守系数：中文约 1 字 ≈ 1 token，英文约 4 字符 ≈ 1 token。
# 仅用于窗口截取预算，不做计费口径。
CHARS_TOKENS_ESTIMATE = 0.6


def estimate_tokens(text: str) -> int:
    """粗略估算文本 token 数（字符数 × 系数），仅用于窗口预算截取。"""
    if not text:
        return 0
    return int(len(text) * CHARS_TOKENS_ESTIMATE)


@dataclass
class WindowedChat:
    """一次请求实际发送给 model 的对话轮次（不含摘要；摘要由调用方并入 system prompt）。

    summary_message_count: 摘要覆盖到的消息条数（其之前的消息已折叠进摘要）。
    truncated: 是否因预算截断而丢弃了部分最近消息（保留最近一轮）。
    early_context_unavailable: 无摘要时较早上下文可能不可用，如实标记。
    """

    messages: list[dict[str, str]] = field(default_factory=list)
    summary_message_count: int = 0
    truncated: bool = False
    early_context_unavailable: bool = False


def build_input_window(
    *,
    summary: str | None,
    summary_message_count: int,
    summary_version: int | None,
    history: list[dict[str, str]],
    token_budget: int,
) -> WindowedChat:
    """返回应发送给 model 的对话轮次（不含摘要本身）。

    - history 为按时间升序的完整消息列表；
    - summary_message_count 为摘要已覆盖的消息条数（其下标 < 该值的消息不再发送）；
    - 摘要与最近消息不重叠：仅返回下标 >= summary_message_count 的消息；
    - 按 token_budget 从旧到新取舍，始终保留最后一条（学生的当前问题）；
    - 无摘要且 history 超预算时，用最近窗口并标记 early_context_unavailable=True。
    """
    if summary is not None and summary.strip() and summary_message_count > 0:
        recent = history[summary_message_count:]
    else:
        recent = history
        summary_message_count = 0

    acc = 0
    kept: list[dict[str, str]] = []
    truncated = False
    for item in recent:
        acc += estimate_tokens(str(item.get("content", "")))
        kept.append(item)
        if acc > token_budget:
            truncated = True
            break
    if len(kept) < len(recent) and recent:
        # 预算装不下：丢弃较早消息，保留最近一轮（含当前问题）。
        kept = recent[-1:]

    return WindowedChat(
        messages=[
            {"role": item.get("role", "user"), "content": str(item.get("content", ""))}
            for item in kept
        ],
        summary_message_count=summary_message_count,
        truncated=truncated,
        early_context_unavailable=(summary is None and truncated),
    )
