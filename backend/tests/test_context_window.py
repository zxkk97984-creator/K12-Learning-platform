"""T20 §20a 上下文窗口 + §20b usage 口径（纯单元测试，无 DB）。

验证：
- 有摘要：发送摘要边界之后的最近消息，不与摘要重叠（不摘要后发全量）；
- 无摘要：使用最近窗口并标记 early_context_unavailable；
- 预算截取：超预算时截断但保留最近一轮（不丢当前问题）；
- usage：有真实 usage 用真实值；无则标 estimated，不把字符数冒充 token。
"""

from app.modules.conversation.context_window import (
    build_input_window,
    estimate_tokens,
)
from app.modules.conversation.service import _usage_report

from app.ai.base import AIProvider


def _history(n: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        rows.append({"role": role, "content": f"消息 {i} " + "字" * 40})
    return rows


class _FakeProvider(AIProvider):
    provider = "fake"
    model = "fake-model"

    async def stream_chat(self, history, system_prompt):
        yield ""
        return


def test_with_summary_sends_only_messages_after_boundary() -> None:
    history = _history(10)
    window = build_input_window(
        summary="这是摘要",
        summary_message_count=7,
        summary_version=2,
        history=history,
        token_budget=100000,
    )
    # 摘要覆盖了前 7 条，仅发送下标 >= 7 的最近 3 条。
    assert window.summary_message_count == 7
    assert len(window.messages) == 3
    assert window.messages[0]["content"] == history[7]["content"]
    assert window.messages[-1]["content"] == history[-1]["content"]
    # 摘要本身不在 messages 中（由调用方并入 system prompt）。
    assert all("摘要" not in m["content"] for m in window.messages)


def test_without_summary_uses_recent_window_and_marks_early_unavailable() -> None:
    history = _history(5)
    window = build_input_window(
        summary=None,
        summary_message_count=0,
        summary_version=None,
        history=history,
        token_budget=100000,
    )
    assert window.summary_message_count == 0
    assert len(window.messages) == 5
    assert window.early_context_unavailable is False


def test_no_summary_with_budget_drops_early_but_keeps_last_round() -> None:
    history = _history(20)
    window = build_input_window(
        summary=None,
        summary_message_count=0,
        summary_version=None,
        history=history,
        token_budget=200,  # 很小，必然截断
    )
    assert window.truncated is True
    assert window.early_context_unavailable is True
    assert len(window.messages) == 1
    assert window.messages[0]["content"] == history[-1]["content"]


def test_summary_with_budget_keeps_current_question() -> None:
    history = _history(40)
    window = build_input_window(
        summary="很长的摘要",
        summary_message_count=35,
        summary_version=1,
        history=history,
        token_budget=80,
    )
    # 保留最后一条（当前问题），截断标记为真。
    assert len(window.messages) >= 1
    assert window.messages[-1]["content"] == history[-1]["content"]
    assert window.truncated is True


def test_usage_prefers_real_tokens_when_available() -> None:
    provider = _FakeProvider()
    provider.last_usage = {"prompt_tokens": 1200, "completion_tokens": 300}
    usage = _usage_report(provider, _history(6), "输出文本")
    assert usage["estimated"] is False
    assert usage["input_tokens"] == 1200
    assert usage["output_tokens"] == 300


def test_usage_marks_estimated_when_unavailable_and_never_calls_chars_tokens() -> None:
    provider = _FakeProvider()  # last_usage 为 None
    usage = _usage_report(provider, _history(6), "输出文本")
    assert usage["estimated"] is True
    assert usage["estimate_method"] == "chars_to_tokens"
    # 明确区分：不使用"input_tokens/output_tokens"冒充真实 token。
    assert "input_tokens" not in usage
    assert "input_estimate" in usage
    assert usage["output_estimate"] > 0


def test_estimate_tokens_is_pure_character_based() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == int(4 * 0.6)
