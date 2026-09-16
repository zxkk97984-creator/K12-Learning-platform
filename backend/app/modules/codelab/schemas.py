"""CodeLab DTO 定义。

**DTO 分层是本模块的安全边界之一**：`CodeTaskDTO` 刻意不包含
`test_groups`（隐藏测试）与 `reference_solution`（标准答案）两个字段。
学生端所有响应都用这些 DTO 构造，因此私有数据在类型层面就无法外泄 ——
比「记得在序列化时删掉某字段」可靠得多。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ═══════════════════════════════════════════════════════════════
# 任务
# ═══════════════════════════════════════════════════════════════


class CodeTaskListItemDTO(BaseModel):
    """任务列表项（学生视角）。"""

    model_config = ConfigDict(from_attributes=True)

    task_id: UUID
    slug: str
    title: str
    description: str
    has_tests: bool = Field(description="是否配置了自动测试；决定评审是否给出总分")
    status: str


class CodeTaskDTO(BaseModel):
    """任务详情（学生视角）。

    刻意**不含** test_groups / reference_solution。starter_code 与 description
    是学生编写代码所必需的。
    """

    model_config = ConfigDict(from_attributes=True)

    task_id: UUID
    slug: str
    title: str
    description: str
    starter_code: str
    has_tests: bool
    status: str


# ═══════════════════════════════════════════════════════════════
# 运行
# ═══════════════════════════════════════════════════════════════


class CreateCodeRunRequest(BaseModel):
    task_id: UUID
    code: str = Field(min_length=1)


class CodeOutputDTO(BaseModel):
    """沙箱输出条目。msg_type ∈ {stream, error, display_data}。

    契约沿用 dai / Jupyter IOPub 的形状，前端据此分类渲染：
      stream        → content.name ∈ {stdout, stderr} + content.text
      error         → content.text 为 traceback
      display_data  → content.data["image/png"] 为 base64
    """

    msg_type: str
    content: dict[str, Any] = Field(default_factory=dict)


class CodeRunDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: UUID
    task_id: UUID
    status: str
    outputs: list[CodeOutputDTO] = Field(default_factory=list)
    execution_time_ms: int | None = None
    exit_code: int | None = None
    error: str | None = None
    created_at: datetime


# ═══════════════════════════════════════════════════════════════
# AI 评审
# ═══════════════════════════════════════════════════════════════


class CreateCodeReviewRequest(BaseModel):
    run_id: UUID


class DimensionItemDTO(BaseModel):
    """单条评分项（含证据与行号，供前端定位到代码）。"""

    dimension: str
    criterion_id: str
    criterion: str
    level: str
    evidence: str
    code_lines: list[int] = Field(default_factory=list)
    deduction_reason: str | None = None


class StudentFeedbackDTO(BaseModel):
    strengths: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    code_suggestions: list[dict[str, str]] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)


class CodeReviewDTO(BaseModel):
    """AI 评审结果（学生视角）。

    语义约定（对应「确定性判题高于 AI 主观评分」）：
    - `deterministic_available=False` 时 `final_score_100` 必为 None，
      `correctness_status` 必为 NOT_VERIFIED，前端必须据此显示「未验证正确性」。
    - `correctness_status` 只由自动测试得出，`algorithm_score` / `quality_score`
      是 LLM 对**算法与代码质量**的评价，不代表功能是否正确。
    """

    review_id: UUID
    run_id: UUID
    status: str
    grading_mode: str
    deterministic_available: bool
    correctness_status: str

    functional_score: float | None = None
    robustness_score: float | None = None
    algorithm_score: float | None = None
    quality_score: float | None = None

    functional_max: float
    robustness_max: float
    algorithm_max: float
    quality_max: float

    final_score_100: float | None = None
    groups: list[dict[str, Any]] = Field(default_factory=list)
    items: list[DimensionItemDTO] = Field(default_factory=list)
    student_feedback: StudentFeedbackDTO | None = None
    needs_teacher_review: bool = False
    review_reason: str | None = None
    validation_errors: list[str] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime
    updated_at: datetime
