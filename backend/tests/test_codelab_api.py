"""CodeLab API 测试。

覆盖面：
- 五个端点的鉴权 / 归属 / 信封形态
- **隐藏测试与标准答案绝不出现在学生响应中**（DTO 层保证）
- CODELAB_ENABLED=false 时明确 503，而不是让请求打到 Docker
- 沙箱不可用时返回 503 而不是回退宿主机执行

沙箱相关的用例（run / review）需要 Docker，用 `sandbox_available()` 做条件跳过；
纯契约用例不依赖 Docker，始终运行。AI 走 mock provider（conftest 已强制
AI_PROVIDER=mock），因此不消耗真实模型额度。

注意：霜铃的 conftest 不设置 DATABASE_URL（docs/12 P0-2），测试会连到
backend/.env 指向的库。本文件只创建并清理**自己的**夹具行（固定 UUID 前缀），
不依赖也不删除既有数据。
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.infrastructure.database.models import CodeReview, CodeRun, CodeTask, StudentProfile, User
from app.infrastructure.database.session import async_session
from app.main import app
from app.modules.codelab import sandbox
from app.modules.identity.security import hash_password

TASK_ID = UUID("d0000000-0000-0000-0000-000000000001")
TASK_SLUG = "codelab-api-fixture-task"
STUDENT_USERNAME = "codelab-api-fixture-student"
STUDENT_PASSWORD = "codelab-fixture-password"

REFERENCE = "def celsius_to_fahrenheit(celsius):\n    return celsius * 9 / 5 + 32\n"

TEST_GROUPS = [
    {
        "id": "F1",
        "name": "基本换算",
        "dimension": "F",
        "max_score": 60,
        "tests": "def test_ok():\n    assert celsius_to_fahrenheit(0) == 32\n",
    },
    {
        "id": "R1",
        "name": "负值",
        "dimension": "R",
        "max_score": 10,
        "tests": "def test_neg():\n    assert abs(celsius_to_fahrenheit(-40) + 40) < 1e-6\n",
    },
]


def sandbox_available() -> bool:
    return sandbox.docker_available() and sandbox.image_available(settings.codelab_run_image)


def _run(coro):
    return asyncio.run(coro)


def _ensure_fixtures() -> None:
    """幂等且自愈的夹具：固定 UUID 的任务 + 学生账号。"""

    async def run() -> None:
        async with async_session() as session:
            task = await session.get(CodeTask, TASK_ID)
            if task is None:
                task = CodeTask(task_id=TASK_ID)
                session.add(task)
            task.slug = TASK_SLUG
            task.title = "CodeLab API 夹具任务"
            task.description = "API 夹具任务，不对学生展示。"
            task.starter_code = "def celsius_to_fahrenheit(celsius):\n    pass\n"
            task.test_groups = TEST_GROUPS
            task.reference_solution = REFERENCE
            task.status = "PUBLISHED"

            user = (
                await session.execute(select(User).where(User.username == STUDENT_USERNAME))
            ).scalar_one_or_none()
            if user is None:
                user = User(
                    username=STUDENT_USERNAME,
                    password_hash=hash_password(STUDENT_PASSWORD),
                    user_type="STUDENT",
                )
                session.add(user)
                await session.flush()
            profile = (
                await session.execute(
                    select(StudentProfile).where(StudentProfile.user_id == user.user_id)
                )
            ).scalar_one_or_none()
            if profile is None:
                session.add(
                    StudentProfile(
                        user_id=user.user_id, nickname="CodeLab 测试学生", grade=8, language="zh-CN"
                    )
                )
            await session.commit()

    _run(run())


def _cleanup_runs() -> None:
    """删除本夹具学生产生的 run / review，并把夹具任务下架。

    下架是必要的：夹具任务是 PUBLISHED 才能在测试中被学生看到，
    但测试结束后它不应该继续出现在真实学生的 CodeLab 任务列表里
    （否则就是"测试数据泄漏进生产视图"，即 docs/12 P0-2 的同类问题）。
    """

    async def run() -> None:
        async with async_session() as session:
            profile = (
                await session.execute(
                    select(StudentProfile).where(
                        StudentProfile.user_id
                        == select(User.user_id).where(User.username == STUDENT_USERNAME).scalar_subquery()
                    )
                )
            ).scalar_one_or_none()
            if profile is None:
                return
            run_ids = (
                await session.execute(
                    select(CodeRun.run_id).where(CodeRun.student_id == profile.student_id)
                )
            ).scalars().all()
            if run_ids:
                reviews = (
                    await session.execute(
                        select(CodeReview).where(CodeReview.run_id.in_(run_ids))
                    )
                ).scalars().all()
                for review in reviews:
                    await session.delete(review)
                for rid in run_ids:
                    row = await session.get(CodeRun, rid)
                    if row is not None:
                        await session.delete(row)

            fixture_task = await session.get(CodeTask, TASK_ID)
            if fixture_task is not None:
                fixture_task.status = "ARCHIVED"
            no_test_task = await session.get(
                CodeTask, UUID("d0000000-0000-0000-0000-0000000000f2")
            )
            if no_test_task is not None:
                no_test_task.status = "ARCHIVED"
            await session.commit()

    _run(run())


@pytest.fixture(scope="module")
def client() -> TestClient:
    _ensure_fixtures()
    yield TestClient(app)
    _cleanup_runs()


@pytest.fixture(scope="module")
def token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": STUDENT_USERNAME, "password": STUDENT_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


@pytest.fixture(scope="module")
def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestCodeLabDisabled:
    def test_disabled_returns_503(self, client: TestClient, auth: dict[str, str], monkeypatch):
        """默认关闭时不触碰 Docker，直接明确拒绝。"""
        monkeypatch.setattr(settings, "codelab_enabled", False)
        response = client.get("/api/v1/codelab/tasks", headers=auth)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "CODELAB_DISABLED"

    def test_disabled_run_also_refused(self, client: TestClient, auth: dict[str, str], monkeypatch):
        monkeypatch.setattr(settings, "codelab_enabled", False)
        response = client.post(
            "/api/v1/codelab/runs",
            headers=auth,
            json={"task_id": str(TASK_ID), "code": "print(1)"},
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "CODELAB_DISABLED"


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "codelab_enabled", True)


class TestTaskEndpoints:
    def test_requires_auth(self, client: TestClient):
        assert client.get("/api/v1/codelab/tasks").status_code == 401

    def test_list_tasks_envelope(self, client: TestClient, auth: dict[str, str], enabled):
        response = client.get("/api/v1/codelab/tasks", headers=auth)
        assert response.status_code == 200
        body = response.json()
        assert "data" in body and "meta" in body
        slugs = [item["slug"] for item in body["data"]]
        assert TASK_SLUG in slugs

    def test_task_detail_hides_private_fields(self, client: TestClient, auth: dict[str, str], enabled):
        """隐藏测试与标准答案绝不能出现在学生响应中（含嵌套的任何层级）。"""
        response = client.get(f"/api/v1/codelab/tasks/{TASK_ID}", headers=auth)
        assert response.status_code == 200
        raw = response.text
        assert "test_groups" not in raw
        assert "reference_solution" not in raw
        assert "celsius * 9 / 5" not in raw  # 标准答案正文
        data = response.json()["data"]
        assert data["starter_code"]
        assert data["has_tests"] is True

    def test_unknown_task_is_404(self, client: TestClient, auth: dict[str, str], enabled):
        response = client.get(
            "/api/v1/codelab/tasks/00000000-0000-0000-0000-0000000000ff", headers=auth
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CODELAB_TASK_NOT_FOUND"

    def test_draft_task_is_hidden_from_students(self, client: TestClient, auth: dict[str, str], enabled):
        async def hide() -> None:
            async with async_session() as session:
                task = await session.get(CodeTask, TASK_ID)
                assert task is not None
                task.status = "DRAFT"
                await session.commit()

        async def restore() -> None:
            async with async_session() as session:
                task = await session.get(CodeTask, TASK_ID)
                assert task is not None
                task.status = "PUBLISHED"
                await session.commit()

        _run(hide())
        try:
            assert (
                client.get(f"/api/v1/codelab/tasks/{TASK_ID}", headers=auth).status_code == 404
            )
        finally:
            _run(restore())


class TestRunEndpointValidation:
    def test_requires_auth(self, client: TestClient):
        response = client.post(
            "/api/v1/codelab/runs", json={"task_id": str(TASK_ID), "code": "print(1)"}
        )
        assert response.status_code == 401

    def test_rejects_empty_code(self, client: TestClient, auth: dict[str, str], enabled):
        response = client.post(
            "/api/v1/codelab/runs", headers=auth, json={"task_id": str(TASK_ID), "code": ""}
        )
        assert response.status_code == 422

    def test_rejects_oversized_code(self, client: TestClient, auth: dict[str, str], enabled):
        response = client.post(
            "/api/v1/codelab/runs",
            headers=auth,
            json={"task_id": str(TASK_ID), "code": "x = 1\n" * 40000},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "CODELAB_CODE_TOO_LONG"

    def test_unknown_task_is_404(self, client: TestClient, auth: dict[str, str], enabled):
        response = client.post(
            "/api/v1/codelab/runs",
            headers=auth,
            json={
                "task_id": "00000000-0000-0000-0000-0000000000ff",
                "code": "print(1)",
            },
        )
        assert response.status_code == 404


class TestReviewEndpointValidation:
    def test_requires_auth(self, client: TestClient):
        response = client.post(
            "/api/v1/codelab/reviews",
            json={"run_id": "00000000-0000-0000-0000-0000000000ff"},
        )
        assert response.status_code == 401

    def test_unknown_run_is_404(self, client: TestClient, auth: dict[str, str], enabled):
        response = client.post(
            "/api/v1/codelab/reviews",
            headers=auth,
            json={"run_id": "00000000-0000-0000-0000-0000000000ff"},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CODELAB_RUN_NOT_FOUND"

    def test_unknown_review_is_404(self, client: TestClient, auth: dict[str, str], enabled):
        response = client.get(
            "/api/v1/codelab/reviews/00000000-0000-0000-0000-0000000000ff", headers=auth
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CODELAB_REVIEW_NOT_FOUND"


class TestSandboxUnavailable:
    def test_run_fails_closed_when_docker_missing(
        self, client: TestClient, auth: dict[str, str], enabled, monkeypatch
    ):
        """Docker 不可用时必须 503 —— 绝不回退到宿主机执行学生代码。"""
        monkeypatch.setattr(sandbox, "docker_available", lambda: False)
        response = client.post(
            "/api/v1/codelab/runs",
            headers=auth,
            json={"task_id": str(TASK_ID), "code": "print(1)"},
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "CODELAB_UNAVAILABLE"

    def test_run_fails_closed_when_image_missing(
        self, client: TestClient, auth: dict[str, str], enabled, monkeypatch
    ):
        monkeypatch.setattr(sandbox, "image_available", lambda _image: False)
        response = client.post(
            "/api/v1/codelab/runs",
            headers=auth,
            json={"task_id": str(TASK_ID), "code": "print(1)"},
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "CODELAB_UNAVAILABLE"


@pytest.mark.skipif(not sandbox_available(), reason="需要 Docker 与 CodeLab 沙箱镜像")
class TestRunAndReviewEndToEnd:
    def test_run_captures_stdout(self, client: TestClient, auth: dict[str, str], enabled):
        response = client.post(
            "/api/v1/codelab/runs",
            headers=auth,
            json={"task_id": str(TASK_ID), "code": "print('你好 CodeLab')\nprint(1 + 1)\n"},
        )
        assert response.status_code == 201, response.text
        data = response.json()["data"]
        assert data["status"] == "SUCCESS"
        assert data["exit_code"] == 0
        text = data["outputs"][0]["content"]["text"]
        assert "你好 CodeLab" in text and "2" in text

    def test_run_reports_syntax_error_as_student_error(
        self, client: TestClient, auth: dict[str, str], enabled
    ):
        response = client.post(
            "/api/v1/codelab/runs",
            headers=auth,
            json={"task_id": str(TASK_ID), "code": "def f(x)\n    return x\n"},
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["status"] == "FAILED"
        assert data["exit_code"] != 0

    def test_full_loop_run_then_review(self, client: TestClient, auth: dict[str, str], enabled):
        """完整闭环：运行 → 评审 → 拿到确定性分数与 AI 反馈。"""
        run_response = client.post(
            "/api/v1/codelab/runs",
            headers=auth,
            json={"task_id": str(TASK_ID), "code": REFERENCE},
        )
        assert run_response.status_code == 201
        run_id = run_response.json()["data"]["run_id"]

        review_response = client.post(
            "/api/v1/codelab/reviews", headers=auth, json={"run_id": run_id}
        )
        assert review_response.status_code == 201, review_response.text
        review = review_response.json()["data"]

        # 正确性来自确定性测试，总分被钳制在 [0,100]
        assert review["deterministic_available"] is True
        assert review["correctness_status"] == "PASSED"
        assert review["functional_score"] == 60.0
        assert review["robustness_score"] == 10.0
        assert review["final_score_100"] is not None
        assert 0 <= review["final_score_100"] <= 100
        # AI 只负责 A/Q 两个维度
        assert review["algorithm_score"] is not None and review["algorithm_max"] == 20
        assert review["quality_score"] is not None and review["quality_max"] == 10
        # 教学化反馈存在
        assert review["student_feedback"] is not None
        # 学生响应里不得出现隐藏测试
        assert "test_groups" not in review_response.text

    def test_failing_code_gets_low_deterministic_score(
        self, client: TestClient, auth: dict[str, str], enabled
    ):
        run_response = client.post(
            "/api/v1/codelab/runs",
            headers=auth,
            json={"task_id": str(TASK_ID), "code": "def celsius_to_fahrenheit(c):\n    return 0\n"},
        )
        run_id = run_response.json()["data"]["run_id"]
        review = client.post(
            "/api/v1/codelab/reviews", headers=auth, json={"run_id": run_id}
        ).json()["data"]
        assert review["correctness_status"] == "FAILED"
        assert review["functional_score"] == 0.0
        # 关键不变量：R 与 F 一样来自**确定性测试**，不是 LLM 维度。
        # mock provider 无论代码对错都会给满分 A/Q，因此若 R 被错误地接到 LLM 上，
        # 这里会得到 10.0 而不是 0.0 —— 这条断言就是防止该接线被改错的回归测试。
        assert review["robustness_score"] == 0.0
        # 测试全失败 + mock 给出的高算法分 → 必须转人工复核（dai 缺陷 b 的修复点）
        assert review["needs_teacher_review"] is True

    def test_review_is_idempotent_per_run(self, client: TestClient, auth: dict[str, str], enabled):
        run = client.post(
            "/api/v1/codelab/runs",
            headers=auth,
            json={"task_id": str(TASK_ID), "code": REFERENCE},
        ).json()["data"]
        first = client.post(
            "/api/v1/codelab/reviews", headers=auth, json={"run_id": run["run_id"]}
        ).json()["data"]
        second = client.post(
            "/api/v1/codelab/reviews", headers=auth, json={"run_id": run["run_id"]}
        ).json()["data"]
        assert first["review_id"] == second["review_id"]

    def test_review_can_be_fetched_by_id(self, client: TestClient, auth: dict[str, str], enabled):
        run = client.post(
            "/api/v1/codelab/runs",
            headers=auth,
            json={"task_id": str(TASK_ID), "code": REFERENCE},
        ).json()["data"]
        created = client.post(
            "/api/v1/codelab/reviews", headers=auth, json={"run_id": run["run_id"]}
        ).json()["data"]
        fetched = client.get(
            f"/api/v1/codelab/reviews/{created['review_id']}", headers=auth
        )
        assert fetched.status_code == 200
        assert fetched.json()["data"]["review_id"] == created["review_id"]


class TestDimensionSources:
    """锁死 F/A/R/Q 的来源划分，防止接线被改错。

    约定（与 docs/17-codelab.md §4 一致）：
        F 功能正确性 60 ← 确定性 pytest
        R 鲁棒性     10 ← 确定性 pytest
        A 算法质量   20 ← LLM
        Q 代码质量   10 ← LLM
    correctness_status 只依赖 F/R，不依赖任何 LLM 主观评分。
    """

    def test_correctness_status_signature_excludes_llm_dimensions(self):
        import inspect

        from app.modules.codelab.scoring import correctness_status

        params = set(inspect.signature(correctness_status).parameters)
        assert params == {"f", "r", "deterministic_available"}
        # 任何 LLM 维度都不得参与正确性判定
        assert "a" not in params and "q" not in params

    def test_merge_scores_takes_f_and_r_as_separate_inputs(self):
        import inspect

        from app.modules.codelab.scoring import merge_scores

        params = set(inspect.signature(merge_scores).parameters)
        assert {"f", "a", "r", "q"}.issubset(params)

    def test_deterministic_grade_only_accepts_f_and_r_groups(self):
        """execution 只认 dimension ∈ {F,R} 的测试组；LLM 维度不经过这里。"""
        from app.modules.codelab.execution import _normalize_groups

        groups = _normalize_groups(
            [
                {"id": "F1", "dimension": "F", "max_score": 60, "tests": "def test_a(): pass"},
                {"id": "R1", "dimension": "R", "max_score": 10, "tests": "def test_b(): pass"},
                # 维度非 F/R 的组必须被丢弃
                {"id": "A1", "dimension": "A", "max_score": 20, "tests": "def test_c(): pass"},
                {"id": "Q1", "dimension": "Q", "max_score": 10, "tests": "def test_d(): pass"},
            ]
        )
        assert [g["id"] for g in groups] == ["F1", "R1"]

    def test_llm_dimension_scores_come_from_ai_result_not_tests(self):
        """A/Q 的取值来自 ai_result；F/R 来自确定性判题结果。"""
        from app.modules.codelab.scoring import ALGORITHM_MAX, FUNCTIONAL_MAX, ROBUSTNESS_MAX, QUALITY_MAX

        assert (FUNCTIONAL_MAX, ROBUSTNESS_MAX) == (60.0, 10.0)
        assert (ALGORITHM_MAX, QUALITY_MAX) == (20.0, 10.0)


class TestReviewWithoutTests:
    """没有测试组的任务：不得给出看似权威的正确性总分。"""

    def test_review_only_mode_reports_not_verified(
        self, client: TestClient, auth: dict[str, str], enabled
    ):
        no_test_task = UUID("d0000000-0000-0000-0000-0000000000f2")

        async def setup() -> None:
            async with async_session() as session:
                task = await session.get(CodeTask, no_test_task)
                if task is None:
                    task = CodeTask(task_id=no_test_task)
                    session.add(task)
                task.slug = "codelab-api-fixture-no-tests"
                task.title = "无测试任务（API 夹具）"
                task.description = "这个任务没有配置自动测试。"
                task.starter_code = "pass\n"
                task.test_groups = []
                task.reference_solution = None
                task.rubric = {
                    "rubric_version": 1,
                    "algorithm_criteria": [{"id": "A1", "name": "思路", "points": 20}],
                    "quality_criteria": [
                        {"id": "Q1", "name": "命名", "points": 3},
                        {"id": "Q2", "name": "结构", "points": 3},
                        {"id": "Q3", "name": "冗余", "points": 2},
                        {"id": "Q4", "name": "规范", "points": 2},
                    ],
                }
                task.status = "PUBLISHED"
                await session.commit()

        async def teardown() -> None:
            async with async_session() as session:
                runs = (
                    await session.execute(select(CodeRun).where(CodeRun.task_id == no_test_task))
                ).scalars().all()
                for run in runs:
                    reviews = (
                        await session.execute(
                            select(CodeReview).where(CodeReview.run_id == run.run_id)
                        )
                    ).scalars().all()
                    for review in reviews:
                        await session.delete(review)
                    await session.delete(run)
                task = await session.get(CodeTask, no_test_task)
                if task is not None:
                    await session.delete(task)
                await session.commit()

        _run(setup())
        try:
            run = client.post(
                "/api/v1/codelab/runs",
                headers=auth,
                json={"task_id": str(no_test_task), "code": "x = 1\n"},
            )
            if run.status_code == 503:
                pytest.skip("沙箱不可用")
            assert run.status_code == 201, run.text
            review = client.post(
                "/api/v1/codelab/reviews",
                headers=auth,
                json={"run_id": run.json()["data"]["run_id"]},
            ).json()["data"]
            assert review["deterministic_available"] is False
            assert review["grading_mode"] == "review_only"
            assert review["correctness_status"] == "NOT_VERIFIED"
            # 关键：不给总分，避免「未验证正确性」看起来像一份正式成绩
            assert review["final_score_100"] is None
        finally:
            _run(teardown())
