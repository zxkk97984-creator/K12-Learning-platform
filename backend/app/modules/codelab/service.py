"""CodeLab 领域服务。

设计要点（每一条都有明确理由）：

1. **沙箱调用移出事件循环。** `docker run` 是阻塞调用，直接在 async 上下文里
   调用会把整个 API 卡住。统一经 `anyio.to_thread.run_sync` 执行，并用一个
   `threading.BoundedSemaphore` 限制并发容器数。用线程级信号量而不是 asyncio
   信号量，是因为后者绑定事件循环，而测试会创建多个循环。

2. **AI 评审同步完成，不依赖后台 Worker。** 霜铃的 Worker 启动链路有已知问题
   （docs/12 P1-2），不能让它成为「能不能用 CodeLab」的前提。评审请求本身是
   用户显式点击触发的，等待 10–60 秒是可接受的；失败也能立刻反馈给学生，
   不会留下永远无人处理的孤儿状态。

3. **Docker 不可用即失败，绝不回退宿主执行。** `ensure_available()` 抛出的
   `CodeLabUnavailableError` 一律转成 503。
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from uuid import UUID

import anyio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import get_ai_provider
from app.ai.json_utils import AIServiceError
from app.config import settings
from app.infrastructure.database.models import CodeReview, CodeRun, CodeTask
from app.modules.codelab import sandbox
from app.modules.codelab.execution import DeterministicGrade, grade_deterministic
from app.modules.codelab.prompts import build_grading_messages, build_rubric_messages
from app.modules.codelab.schemas import (
    CodeOutputDTO,
    CodeReviewDTO,
    CodeRunDTO,
    CodeTaskDTO,
    CodeTaskListItemDTO,
    DimensionItemDTO,
    StudentFeedbackDTO,
)
from app.modules.codelab.scoring import (
    ALGORITHM_MAX,
    FUNCTIONAL_MAX,
    QUALITY_MAX,
    ROBUSTNESS_MAX,
    correctness_status,
    detect_test_llm_contradiction,
    merge_scores,
)
from app.modules.codelab.static_analysis import analyze_python
from app.modules.codelab.validation import (
    extract_dimension_items,
    extract_student_feedback,
    validate_ai_output,
)

logger = logging.getLogger("shuangling.codelab")

_limiter_lock = threading.Lock()
_sandbox_limiter: threading.BoundedSemaphore | None = None

# 沙箱不可用时给学生的统一提示（不泄露内部路径/镜像细节）
_UNAVAILABLE_CODE = "CODELAB_UNAVAILABLE"


def _get_limiter() -> threading.BoundedSemaphore:
    global _sandbox_limiter
    if _sandbox_limiter is None:
        with _limiter_lock:
            if _sandbox_limiter is None:
                _sandbox_limiter = threading.BoundedSemaphore(settings.codelab_max_concurrent)
    return _sandbox_limiter


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


class _SandboxBusy(RuntimeError):
    """并发额度已满。"""


def _acquire_and_run(func, args, kwargs):
    """在线程内取额度并执行沙箱调用（额度用尽 → _SandboxBusy）。"""
    limiter = _get_limiter()
    if not limiter.acquire(timeout=30):
        raise _SandboxBusy()
    try:
        return func(*args, **kwargs)
    finally:
        limiter.release()


async def _in_sandbox(func, *args, **kwargs):
    """把阻塞的沙箱调用放到工作线程，并翻译可用性错误。"""
    try:
        return await anyio.to_thread.run_sync(
            lambda: _acquire_and_run(func, args, kwargs)
        )
    except _SandboxBusy as exc:
        raise _error(503, "CODELAB_BUSY", "当前编程任务较多，请稍后重试。") from exc
    except sandbox.CodeLabUnavailableError as exc:
        logger.warning("codelab sandbox unavailable: %s", exc)
        raise _error(503, _UNAVAILABLE_CODE, str(exc)) from exc


class CodeLabService:
    """CodeLab 的 Router/Service 边界；SQL 只出现在这一层。"""

    # ── 任务 ────────────────────────────────────────────────

    async def list_tasks(self, session: AsyncSession) -> list[CodeTaskListItemDTO]:
        rows = (
            await session.execute(
                select(CodeTask)
                .where(CodeTask.status == "PUBLISHED")
                .order_by(CodeTask.created_at.asc())
            )
        ).scalars().all()
        return [
            CodeTaskListItemDTO(
                task_id=row.task_id,
                slug=row.slug,
                title=row.title,
                description=row.description,
                has_tests=bool(row.test_groups),
                status=row.status,
            )
            for row in rows
        ]

    async def get_task(self, session: AsyncSession, task_id: UUID) -> CodeTaskDTO:
        task = await self._get_visible_task(session, task_id)
        return CodeTaskDTO(
            task_id=task.task_id,
            slug=task.slug,
            title=task.title,
            description=task.description,
            starter_code=task.starter_code,
            has_tests=bool(task.test_groups),
            status=task.status,
        )

    async def _get_visible_task(self, session: AsyncSession, task_id: UUID) -> CodeTask:
        task = await session.get(CodeTask, task_id)
        if task is None or task.status != "PUBLISHED":
            raise _error(404, "CODELAB_TASK_NOT_FOUND", "编程任务不存在或未发布")
        return task

    async def _get_owned_run(
        self, session: AsyncSession, student_id: UUID, run_id: UUID
    ) -> CodeRun:
        run = await session.get(CodeRun, run_id)
        # 越权与不存在返回同一个 404，不泄露「该 run 存在但不属于你」
        if run is None or run.student_id != student_id:
            raise _error(404, "CODELAB_RUN_NOT_FOUND", "运行记录不存在")
        return run

    # ── 运行 ────────────────────────────────────────────────

    async def create_run(
        self, session: AsyncSession, student_id: UUID, task_id: UUID, code: str
    ) -> CodeRunDTO:
        if len(code.encode("utf-8")) > settings.codelab_max_code_bytes:
            raise _error(
                422,
                "CODELAB_CODE_TOO_LONG",
                f"代码过长，最多 {settings.codelab_max_code_bytes} 字节",
            )
        await self._get_visible_task(session, task_id)

        # 必须是绝对路径：Docker 的 -v 不接受相对路径（会被当成命名卷）
        work_root = Path(settings.codelab_work_dir_resolved)
        host_work_root = Path(settings.codelab_host_work_dir_resolved)

        result = await _in_sandbox(
            sandbox.run_python,
            code=code,
            work_root=work_root,
            host_work_root=host_work_root,
            image=settings.codelab_run_image,
            timeout_seconds=settings.codelab_run_timeout_seconds,
            memory_limit_mb=settings.codelab_memory_limit_mb,
            cpu_limit=settings.codelab_cpu_limit,
            max_output_bytes=settings.codelab_max_output_bytes,
        )

        run = CodeRun(
            student_id=student_id,
            task_id=task_id,
            code=code,
            status=result.status,
            outputs=result.outputs,
            execution_time_ms=result.execution_time_ms,
            exit_code=result.exit_code,
            error=result.error,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return self._run_dto(run)

    @staticmethod
    def _run_dto(run: CodeRun) -> CodeRunDTO:
        return CodeRunDTO(
            run_id=run.run_id,
            task_id=run.task_id,
            status=run.status,
            outputs=[CodeOutputDTO(**item) for item in (run.outputs or [])],
            execution_time_ms=run.execution_time_ms,
            exit_code=run.exit_code,
            error=run.error,
            created_at=run.created_at,
        )

    # ── AI 评审 ─────────────────────────────────────────────

    async def create_review(
        self, session: AsyncSession, student_id: UUID, run_id: UUID
    ) -> CodeReviewDTO:
        run = await self._get_owned_run(session, student_id, run_id)

        existing = (
            await session.execute(select(CodeReview).where(CodeReview.run_id == run_id))
        ).scalar_one_or_none()
        # 同一 run 只评一次：已完成的直接返回，避免重复消耗模型额度
        if existing is not None and existing.status in ("COMPLETED", "REVIEW_REQUIRED"):
            return self._review_dto(existing)
        if existing is None:
            # grading_mode 是 NOT NULL：先给一个保守初值，_execute_review 里按
            # 是否配置了测试组改写为 tests / review_only。
            existing = CodeReview(
                run_id=run_id,
                status="RUNNING",
                grading_mode="review_only",
                correctness_status="NOT_VERIFIED",
            )
            session.add(existing)
            await session.commit()
            await session.refresh(existing)

        task = await session.get(CodeTask, run.task_id)
        try:
            await self._execute_review(session, existing, run, task)
        except HTTPException:
            raise
        except Exception as exc:  # pragma: no cover - 兜底，保证状态可回读
            logger.exception("codelab review failed", extra={"review_id": str(existing.review_id)})
            existing.status = "FAILED"
            existing.error = f"{type(exc).__name__}: {exc}"[:2000]
            await session.commit()
            raise _error(500, "CODELAB_REVIEW_FAILED", "AI 评审失败，请稍后重试") from exc

        await session.commit()
        await session.refresh(existing)
        return self._review_dto(existing)

    async def get_review(
        self, session: AsyncSession, student_id: UUID, review_id: UUID
    ) -> CodeReviewDTO:
        review = await session.get(CodeReview, review_id)
        if review is None:
            raise _error(404, "CODELAB_REVIEW_NOT_FOUND", "评审批次不存在")
        # 归属通过 run 校验
        await self._get_owned_run(session, student_id, review.run_id)
        return self._review_dto(review)

    async def _execute_review(
        self, session: AsyncSession, review: CodeReview, run: CodeRun, task: CodeTask | None
    ) -> None:
        code = run.code
        test_groups = list(getattr(task, "test_groups", None) or [])
        analysis = analyze_python(code)

        # ── 1) 确定性判题（F/R）—— 正确性的唯一来源 ──────────────
        grade: DeterministicGrade = await _in_sandbox(
            grade_deterministic,
            code,
            test_groups,
            work_root=Path(settings.codelab_work_dir_resolved),
            host_work_root=Path(settings.codelab_host_work_dir_resolved),
            judge_image=settings.codelab_judge_image,
            timeout_seconds=settings.codelab_judge_timeout_seconds,
            memory_limit_mb=settings.codelab_memory_limit_mb,
            cpu_limit=settings.codelab_cpu_limit,
        )
        deterministic_available = grade.available
        review.deterministic_available = deterministic_available
        review.grading_mode = "tests" if deterministic_available else "review_only"
        review.static_analysis = analysis
        review.deterministic_details = {
            "groups": grade.groups,
            "system_errors": grade.system_errors,
            "syntax_error": grade.syntax_error,
        }
        review.functional_score = grade.functional_score
        review.robustness_score = grade.robustness_score
        correctness = correctness_status(
            f=grade.functional_score,
            r=grade.robustness_score,
            deterministic_available=deterministic_available,
        )
        review.correctness_status = correctness

        # ── 2) Rubric（锁定后复用；生成失败则转人工，不编造分数）──
        rubric = dict(task.rubric) if task is not None and task.rubric else None
        provider = get_ai_provider()
        if rubric is None:
            if task is None:
                review.status = "FAILED"
                review.error = "任务已不存在，无法评审"
                return
            rubric = await provider.chat_json(
                build_rubric_messages(
                    title=task.title,
                    description=task.description,
                    reference_solution=task.reference_solution,
                ),
                operation="codelab_rubric",
            )
            task.rubric = rubric

        # ── 3) LLM 评分（A/Q）──────────────────────────────────
        deterministic_summary = {
            "available": deterministic_available,
            "functional_score": grade.functional_score,
            "robustness_score": grade.robustness_score,
            "groups": [
                {
                    "id": g["id"],
                    "name": g["name"],
                    "dimension": g["dimension"],
                    "score": g.get("score"),
                    "counts": g.get("counts"),
                }
                for g in grade.groups
            ],
            "syntax_error": grade.syntax_error,
        }
        ai_result = await provider.chat_json(
            build_grading_messages(
                rubric=rubric,
                task={
                    "title": getattr(task, "title", ""),
                    "description": getattr(task, "description", ""),
                },
                code=code,
                deterministic=deterministic_summary,
                static_analysis=analysis,
            ),
            operation="codelab_grading",
        )

        # ── 4) 校验 → 钳制 → 合并 ───────────────────────────────
        code_lines = list(range(1, len(code.splitlines()) + 1))
        validation_errors = validate_ai_output(rubric, ai_result, code_lines)

        algorithm = ai_result.get("algorithm") or {}
        quality = ai_result.get("code_quality") or {}
        merged = merge_scores(
            f=grade.functional_score,
            a=algorithm.get("dimension_score"),
            r=grade.robustness_score,
            q=quality.get("dimension_score"),
            deterministic_available=deterministic_available,
        )

        contradiction = detect_test_llm_contradiction(
            deterministic_available=deterministic_available,
            f=merged.f,
            r=merged.r,
            a=merged.a,
        )
        if contradiction:
            validation_errors.append(contradiction)

        needs_review = bool(ai_result.get("needs_teacher_review")) or bool(validation_errors)
        review.ai_result = ai_result
        review.student_feedback = extract_student_feedback(ai_result)
        review.validation_errors = validation_errors
        review.needs_teacher_review = needs_review
        review.review_reason = ai_result.get("review_reason") or (
            "自动校验未通过，" + contradiction if contradiction else None
        )
        review.algorithm_score = merged.a
        review.quality_score = merged.q
        review.final_score_100 = merged.final_score_100
        review.model_info = dict(provider.model_info)
        review.status = "REVIEW_REQUIRED" if needs_review else "COMPLETED"

    @staticmethod
    def _review_dto(review: CodeReview) -> CodeReviewDTO:
        feedback = review.student_feedback
        return CodeReviewDTO(
            review_id=review.review_id,
            run_id=review.run_id,
            status=review.status,
            grading_mode=review.grading_mode,
            deterministic_available=review.deterministic_available,
            correctness_status=review.correctness_status,
            functional_score=review.functional_score,
            robustness_score=review.robustness_score,
            algorithm_score=review.algorithm_score,
            quality_score=review.quality_score,
            functional_max=FUNCTIONAL_MAX,
            robustness_max=ROBUSTNESS_MAX,
            algorithm_max=ALGORITHM_MAX,
            quality_max=QUALITY_MAX,
            final_score_100=review.final_score_100,
            groups=list((review.deterministic_details or {}).get("groups") or []),
            items=[DimensionItemDTO(**item) for item in extract_dimension_items(review.ai_result or {})],
            student_feedback=StudentFeedbackDTO(**feedback) if feedback else None,
            needs_teacher_review=review.needs_teacher_review,
            review_reason=review.review_reason,
            validation_errors=list(review.validation_errors or []),
            error=review.error,
            created_at=review.created_at,
            updated_at=review.updated_at,
        )


service = CodeLabService()
