"""Phase 2 Identity/Student 补充测试：认证 / 档案 / 偏好 / 权限 / 信封。

沿用现有策略：真实 PostgreSQL + TestClient；conftest 设 ENVIRONMENT=test
使 engine 使用 NullPool（TestClient 每请求独立事件循环）。
测试使用独立测试账号（test_student / test_admin），不污染 seed 的 xiaoming。
"""

import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.infrastructure.database.models import StudentPreference, StudentProfile, User
from app.infrastructure.database.session import async_session
from app.main import app
from app.modules.identity.security import hash_password


def _ensure_user(
    username: str,
    password: str,
    user_type: str,
    grade: int = 7,
    with_preference: bool = True,
) -> None:
    async def run() -> None:
        async with async_session() as session:
            result = await session.execute(select(User).where(User.username == username))
            user = result.scalar_one_or_none()
            if user is None:
                user = User(
                    username=username,
                    password_hash=hash_password(password),
                    user_type=user_type,
                )
                session.add(user)
                await session.flush()
            if user_type == "STUDENT":
                profile_result = await session.execute(
                    select(StudentProfile).where(StudentProfile.user_id == user.user_id)
                )
                profile = profile_result.scalar_one_or_none()
                if profile is None:
                    profile = StudentProfile(
                        user_id=user.user_id,
                        nickname=f"测试{username}",
                        grade=grade,
                        language="zh-CN",
                    )
                    session.add(profile)
                    await session.flush()
                pref_result = await session.execute(
                    select(StudentPreference).where(
                        StudentPreference.student_id == profile.student_id
                    )
                )
                if pref_result.scalar_one_or_none() is None and with_preference:
                    session.add(
                        StudentPreference(
                            student_id=profile.student_id,
                            preferred_explanation_style="EXAMPLE_BASED",
                            preferred_difficulty="MEDIUM",
                            preferred_session_length="SHORT",
                        )
                    )
            await session.commit()

    asyncio.run(run())


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def student_token(client: TestClient) -> str:
    _ensure_user("test_student", "testpass", "STUDENT", grade=7)
    response = client.post(
        "/api/v1/auth/login", json={"username": "test_student", "password": "testpass"}
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


@pytest.fixture(scope="module")
def admin_token(client: TestClient) -> str:
    _ensure_user("test_admin", "adminpass", "ADMIN")
    response = client.post(
        "/api/v1/auth/login", json={"username": "test_admin", "password": "adminpass"}
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestAuth:
    def test_login_unknown_username_401(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/auth/login", json={"username": "nobody", "password": "x"}
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"

    def test_invalid_token_401(self, client: TestClient) -> None:
        response = client.get("/api/v1/me", headers=auth_headers("not-a-jwt"))
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHENTICATED"

    def test_error_envelope_shape(self, client: TestClient) -> None:
        response = client.get("/api/v1/me", headers=auth_headers("not-a-jwt"))
        body = response.json()
        assert "error" in body
        assert body["error"]["code"] == "UNAUTHENTICATED"
        assert isinstance(body["error"]["message"], str)
        assert "details" in body["error"]


class TestProfile:
    def test_get_me_returns_derived_stage(self, client: TestClient, student_token: str) -> None:
        response = client.get("/api/v1/me", headers=auth_headers(student_token))
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["grade"] == 7
        assert data["stage"] == "JUNIOR"
        assert data["language"] == "zh-CN"
        assert "student_id" in data
        assert "current_teacher_role_id" in data

    def test_patch_me_nickname(self, client: TestClient, student_token: str) -> None:
        response = client.patch(
            "/api/v1/me", headers=auth_headers(student_token), json={"nickname": "测试昵称"}
        )
        assert response.status_code == 200
        assert response.json()["data"]["nickname"] == "测试昵称"
        # 还原
        client.patch(
            "/api/v1/me", headers=auth_headers(student_token), json={"nickname": "测试test_student"}
        )

    @pytest.mark.parametrize("grade", [1, 12])
    def test_patch_me_grade_boundary_valid(
        self, client: TestClient, student_token: str, grade: int
    ) -> None:
        response = client.patch(
            "/api/v1/me", headers=auth_headers(student_token), json={"grade": grade}
        )
        assert response.status_code == 200
        assert response.json()["data"]["grade"] == grade
        client.patch("/api/v1/me", headers=auth_headers(student_token), json={"grade": 7})

    def test_patch_me_grade_zero_422(self, client: TestClient, student_token: str) -> None:
        response = client.patch(
            "/api/v1/me", headers=auth_headers(student_token), json={"grade": 0}
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_patch_me_current_teacher_role_id_accepted_without_fk(
        self, client: TestClient, student_token: str
    ) -> None:
        # teacher_roles 表 Phase 11 才建：本字段只存值、不校验 FK
        role_id = str(uuid4())
        response = client.patch(
            "/api/v1/me", headers=auth_headers(student_token), json={"current_teacher_role_id": role_id}
        )
        assert response.status_code == 200
        assert response.json()["data"]["current_teacher_role_id"] == role_id
        client.patch(
            "/api/v1/me", headers=auth_headers(student_token), json={"current_teacher_role_id": None}
        )


class TestPreferences:
    def test_get_preferences_autocreate_defaults(self, client: TestClient) -> None:
        # 回归：无 preference 记录的学生首次访问不 500，返回默认值（Fix：3 枚举默认）
        _ensure_user("test_no_pref", "nopass", "STUDENT", grade=9, with_preference=False)
        response = client.post(
            "/api/v1/auth/login", json={"username": "test_no_pref", "password": "nopass"}
        )
        assert response.status_code == 200
        token = response.json()["data"]["access_token"]
        pref_response = client.get("/api/v1/me/preferences", headers=auth_headers(token))
        assert pref_response.status_code == 200
        data = pref_response.json()["data"]
        assert data["preferred_explanation_style"] == "EXAMPLE_BASED"
        assert data["preferred_difficulty"] == "MEDIUM"
        assert data["preferred_session_length"] == "SHORT"
        assert data["daily_learning_minutes"] == 30

    def test_get_preferences_defaults(self, client: TestClient, student_token: str) -> None:
        response = client.get("/api/v1/me/preferences", headers=auth_headers(student_token))
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["preferred_explanation_style"] == "EXAMPLE_BASED"
        assert data["preferred_difficulty"] == "MEDIUM"
        assert data["preferred_session_length"] == "SHORT"
        assert data["daily_learning_minutes"] == 30
        assert data["voice_preference"]["volume"] == 0.8

    def test_patch_preferences_invalid_style_422(
        self, client: TestClient, student_token: str
    ) -> None:
        response = client.patch(
            "/api/v1/me/preferences",
            headers=auth_headers(student_token),
            json={"preferred_explanation_style": "NOT_A_STYLE"},
        )
        assert response.status_code == 422

    def test_patch_preferences_invalid_voice_422(
        self, client: TestClient, student_token: str
    ) -> None:
        response = client.patch(
            "/api/v1/me/preferences",
            headers=auth_headers(student_token),
            json={"voice_preference": {"input_enabled": True, "volume": 5}},
        )
        assert response.status_code == 422

    def test_patch_preferences_negative_minutes_422(
        self, client: TestClient, student_token: str
    ) -> None:
        response = client.patch(
            "/api/v1/me/preferences",
            headers=auth_headers(student_token),
            json={"daily_learning_minutes": -1},
        )
        assert response.status_code == 422

    def test_patch_preferences_valid_difficulty(
        self, client: TestClient, student_token: str
    ) -> None:
        response = client.patch(
            "/api/v1/me/preferences",
            headers=auth_headers(student_token),
            json={"preferred_difficulty": "HARD"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["preferred_difficulty"] == "HARD"
        client.patch(
            "/api/v1/me/preferences",
            headers=auth_headers(student_token),
            json={"preferred_difficulty": "MEDIUM"},
        )


class TestPermissions:
    def test_admin_me_403(self, client: TestClient, admin_token: str) -> None:
        response = client.get("/api/v1/me", headers=auth_headers(admin_token))
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"
