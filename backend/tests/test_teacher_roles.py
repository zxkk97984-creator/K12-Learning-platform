"""Phase 11 teacher role tests (student switch + admin CRUD + defaults)."""

import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.infrastructure.database.models import (
    Admin,
    ProfileInsight,
    StudentProfile,
    StudentMemory,
    TeacherRole,
    User,
)
from app.infrastructure.database.session import async_session
from app.main import app
from app.modules.identity.security import hash_password


ADMIN_NAME = "test_role_admin"
ADMIN_PASSWORD = "roleadmin"
STUDENT_NAME = "test_role_student"
STUDENT_PASSWORD = "rolestudent"


def _ensure_admin() -> None:
    async def run() -> None:
        async with async_session() as session:
            user = (
                await session.execute(select(User).where(User.username == ADMIN_NAME))
            ).scalar_one_or_none()
            if user is None:
                user = User(
                    username=ADMIN_NAME,
                    password_hash=hash_password(ADMIN_PASSWORD),
                    user_type="ADMIN",
                )
                session.add(user)
                await session.flush()
            admin = (
                await session.execute(
                    select(Admin).where(Admin.user_id == user.user_id)
                )
            ).scalar_one_or_none()
            if admin is None:
                session.add(
                    Admin(
                        user_id=user.user_id,
                        display_name="角色管理员",
                        role_level="SUPERVISOR",
                    )
                )
            await session.commit()

    asyncio.run(run())


def _ensure_student() -> UUID:
    async def run() -> UUID:
        async with async_session() as session:
            user = (
                await session.execute(select(User).where(User.username == STUDENT_NAME))
            ).scalar_one_or_none()
            if user is None:
                user = User(
                    username=STUDENT_NAME,
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
                profile = StudentProfile(
                    user_id=user.user_id,
                    nickname="角色学生",
                    grade=8,
                    language="zh-CN",
                )
                session.add(profile)
                await session.flush()
            await session.commit()
            return profile.student_id

    return asyncio.run(run())


@pytest.fixture(scope="module")
def client() -> TestClient:
    _ensure_admin()
    _ensure_student()
    return TestClient(app)


@pytest.fixture(scope="module")
def admin_token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": ADMIN_NAME, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


@pytest.fixture(scope="module")
def student_token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": STUDENT_NAME, "password": STUDENT_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def headers(token: str, **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", **extra}


def _role_body(name: str) -> dict:
    return {
        "name": name,
        "description": "测试角色",
        "persona": {"base_persona": "测试人格", "character_persona": name},
        "tone": "清晰",
        "teaching_style": "逻辑引导",
        "sprite_manifest": {"sheet_url": "", "grid_cols": 7, "grid_rows": 9, "states": {}},
        "grade_rules": {"primary": "x", "junior": "y", "senior": "z"},
    }


def _insert_student_artifacts(student_id: UUID) -> None:
    async def run() -> None:
        async with async_session() as session:
            now = datetime.now(timezone.utc)
            session.add(
                StudentMemory(
                    memory_id=uuid4(),
                    student_id=student_id,
                    memory_type="PREFERENCE",
                    content="角色切换前的记忆",
                    tags=[],
                    confidence="MEDIUM",
                    status="ACTIVE",
                    evidence_ids=[],
                    user_confirmed=False,
                )
            )
            session.add(
                ProfileInsight(
                    insight_id=uuid4(),
                    student_id=student_id,
                    insight_type="HABIT",
                    dimension="role_independent",
                    level="一般",
                    description="角色切换不应改变画像",
                    evidence_ids=[],
                    status="ACTIVE",
                    valid_from=now,
                    valid_until=None,
                    rule_version="test-v1",
                )
            )
            await session.commit()

    asyncio.run(run())


class CaptureProvider:
    provider = "capture"
    model = "capture"
    prompt = ""

    @property
    def model_info(self):
        return {"provider": self.provider, "model": self.model}

    async def stream_chat(self, history, system_prompt):
        self.prompt = system_prompt
        yield "好的"


class TestTeacherRoles:
    def test_student_list_and_switch_role(
        self, client: TestClient, student_token: str
    ) -> None:
        roles = client.get(
            "/api/v1/teacher-roles?enabled=true",
            headers=headers(student_token),
        )
        assert roles.status_code == 200
        data = roles.json()["data"]
        names = {row["name"] for row in data}
        assert "shuangling" in names
        assert "strict-mentor" in names
        assert all("persona" not in row for row in data)
        strict = next(row for row in data if row["name"] == "strict-mentor")

        patched = client.patch(
            "/api/v1/me",
            headers=headers(student_token),
            json={"current_teacher_role_id": strict["role_id"]},
        )
        assert patched.status_code == 200
        assert patched.json()["data"]["current_teacher_role_id"] == strict["role_id"]

        me = client.get("/api/v1/me", headers=headers(student_token))
        assert me.json()["data"]["current_teacher_role_id"] == strict["role_id"]

    def test_switch_missing_and_disabled_role(
        self, client: TestClient, student_token: str, admin_token: str
    ) -> None:
        missing = client.patch(
            "/api/v1/me",
            headers=headers(student_token),
            json={"current_teacher_role_id": str(uuid4())},
        )
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "ROLE_NOT_FOUND"

        name = f"disabled-role-{uuid4()}"
        created = client.post(
            "/api/v1/admin/teacher-roles",
            headers=headers(admin_token, **{"Idempotency-Key": f"role-{uuid4()}"}),
            json=_role_body(name),
        )
        assert created.status_code == 201
        role_id = created.json()["data"]["role_id"]
        disabled = client.patch(
            f"/api/v1/admin/teacher-roles/{role_id}",
            headers=headers(admin_token, **{"Idempotency-Key": f"dis-{uuid4()}"}),
            json={"enabled": False},
        )
        assert disabled.status_code == 200
        assert disabled.json()["data"]["version"] >= 2

        blocked = client.patch(
            "/api/v1/me",
            headers=headers(student_token),
            json={"current_teacher_role_id": role_id},
        )
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "ROLE_DISABLED"

    def test_admin_crud_and_name_conflict(
        self, client: TestClient, admin_token: str, student_token: str
    ) -> None:
        name = f"admin-role-{uuid4()}"
        created = client.post(
            "/api/v1/admin/teacher-roles",
            headers=headers(admin_token, **{"Idempotency-Key": f"crole-{uuid4()}"}),
            json=_role_body(name),
        )
        assert created.status_code == 201

        conflict = client.post(
            "/api/v1/admin/teacher-roles",
            headers=headers(admin_token, **{"Idempotency-Key": f"cconf-{uuid4()}"}),
            json=_role_body(name),
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "ROLE_NAME_CONFLICT"

        listed = client.get(
            "/api/v1/admin/teacher-roles", headers=headers(admin_token)
        )
        assert any(row["name"] == name for row in listed.json()["data"])

        forbidden = client.get(
            "/api/v1/admin/teacher-roles", headers=headers(student_token)
        )
        assert forbidden.status_code == 403

    def test_new_conversation_and_quiz_use_student_role(
        self, client: TestClient, student_token: str
    ) -> None:
        roles = client.get(
            "/api/v1/teacher-roles?enabled=true",
            headers=headers(student_token),
        ).json()["data"]
        strict = next(row for row in roles if row["name"] == "strict-mentor")
        client.patch(
            "/api/v1/me",
            headers=headers(student_token),
            json={"current_teacher_role_id": strict["role_id"]},
        )

        conversation = client.post(
            "/api/v1/conversations",
            headers=headers(student_token),
            json={"title": "角色会话"},
        )
        assert conversation.status_code == 201
        assert conversation.json()["data"]["teacher_role_id"] == strict["role_id"]
        conversation_id = conversation.json()["data"]["conversation_id"]

        quiz = client.post(
            "/api/v1/quiz-sessions",
            headers=headers(student_token),
            json={"conversation_id": conversation_id, "question_count": 1},
        )
        assert quiz.status_code == 201
        assert quiz.json()["data"]["teacher_role_id"] == strict["role_id"]

    def test_student_dto_omits_internal_config(
        self, client: TestClient, student_token: str
    ) -> None:
        roles = client.get(
            "/api/v1/teacher-roles?enabled=true",
            headers=headers(student_token),
        ).json()["data"]
        assert roles
        assert all("persona" not in row for row in roles)
        assert all("sprite_manifest" not in row for row in roles)
        assert all("grade_rules" not in row for row in roles)

    def test_set_null_and_repeat_switch(
        self, client: TestClient, student_token: str
    ) -> None:
        roles = client.get(
            "/api/v1/teacher-roles?enabled=true",
            headers=headers(student_token),
        ).json()["data"]
        strict = next(row for row in roles if row["name"] == "strict-mentor")
        for _ in range(2):
            response = client.patch(
                "/api/v1/me",
                headers=headers(student_token),
                json={"current_teacher_role_id": strict["role_id"]},
            )
            assert response.status_code == 200

        cleared = client.patch(
            "/api/v1/me",
            headers=headers(student_token),
            json={"current_teacher_role_id": None},
        )
        assert cleared.status_code == 200
        assert cleared.json()["data"]["current_teacher_role_id"] is None

    def test_disabled_role_excluded_from_student_list(
        self, client: TestClient, student_token: str, admin_token: str
    ) -> None:
        name = f"hidden-role-{uuid4()}"
        created = client.post(
            "/api/v1/admin/teacher-roles",
            headers=headers(admin_token, **{"Idempotency-Key": f"hide-{uuid4()}"}),
            json=_role_body(name),
        )
        role_id = created.json()["data"]["role_id"]
        client.patch(
            f"/api/v1/admin/teacher-roles/{role_id}",
            headers=headers(admin_token, **{"Idempotency-Key": f"hidep-{uuid4()}"}),
            json={"enabled": False},
        )

        roles = client.get(
            "/api/v1/teacher-roles?enabled=true",
            headers=headers(student_token),
        ).json()["data"]
        assert name not in {row["name"] for row in roles}

    def test_invalid_persona_type_rejected(
        self, client: TestClient, admin_token: str
    ) -> None:
        body = _role_body(f"bad-persona-{uuid4()}")
        body["persona"] = "not-a-dict"
        response = client.post(
            "/api/v1/admin/teacher-roles",
            headers=headers(admin_token, **{"Idempotency-Key": f"badp-{uuid4()}"}),
            json=body,
        )
        assert response.status_code == 422

    def test_default_role_used_when_current_null(
        self, client: TestClient, student_token: str
    ) -> None:
        client.patch(
            "/api/v1/me",
            headers=headers(student_token),
            json={"current_teacher_role_id": None},
        )
        conversation = client.post(
            "/api/v1/conversations",
            headers=headers(student_token),
            json={"title": "默认角色会话"},
        )
        assert conversation.status_code == 201
        assert (
            conversation.json()["data"]["teacher_role_id"]
            == "00000000-0000-0000-0000-000000000001"
        )

    def test_persona_injected_into_system_prompt(
        self,
        client: TestClient,
        student_token: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        roles = client.get(
            "/api/v1/teacher-roles?enabled=true",
            headers=headers(student_token),
        ).json()["data"]
        strict = next(row for row in roles if row["name"] == "strict-mentor")
        client.patch(
            "/api/v1/me",
            headers=headers(student_token),
            json={"current_teacher_role_id": strict["role_id"]},
        )
        provider = CaptureProvider()
        monkeypatch.setattr(
            "app.modules.conversation.service.get_ai_provider",
            lambda: provider,
        )
        conversation = client.post(
            "/api/v1/conversations",
            headers=headers(student_token),
            json={"title": "Persona 注入"},
        )
        conversation_id = conversation.json()["data"]["conversation_id"]
        response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=headers(student_token),
            json={"content": "测试"},
        )
        assert response.status_code == 200
        assert "【教师人格】" in provider.prompt
        assert "严谨理性的 K12 导师" in provider.prompt
        assert "严谨、清晰" in provider.prompt
        assert "强调逻辑与证据" in provider.prompt

    def test_switching_role_keeps_student_memories_and_insights(
        self, client: TestClient, student_token: str
    ) -> None:
        student_id = _ensure_student()
        _insert_student_artifacts(student_id)
        roles = client.get(
            "/api/v1/teacher-roles?enabled=true",
            headers=headers(student_token),
        ).json()["data"]
        strict = next(row for row in roles if row["name"] == "strict-mentor")
        client.patch(
            "/api/v1/me",
            headers=headers(student_token),
            json={"current_teacher_role_id": strict["role_id"]},
        )

        memories = client.get(
            "/api/v1/me/memories?status=ACTIVE",
            headers=headers(student_token),
        ).json()["data"]
        insights = client.get(
            "/api/v1/me/insights?status=ACTIVE",
            headers=headers(student_token),
        ).json()["data"]
        assert any(row["content"] == "角色切换前的记忆" for row in memories)
        assert any(row["dimension"] == "role_independent" for row in insights)

    def test_admin_patch_name_conflict_and_missing_role(
        self, client: TestClient, admin_token: str
    ) -> None:
        name_a = f"conflict-a-{uuid4()}"
        created_a = client.post(
            "/api/v1/admin/teacher-roles",
            headers=headers(admin_token, **{"Idempotency-Key": f"ca-{uuid4()}"}),
            json=_role_body(name_a),
        )
        role_a = created_a.json()["data"]["role_id"]
        name_b = f"conflict-b-{uuid4()}"
        created_b = client.post(
            "/api/v1/admin/teacher-roles",
            headers=headers(admin_token, **{"Idempotency-Key": f"cb-{uuid4()}"}),
            json=_role_body(name_b),
        )
        role_b = created_b.json()["data"]["role_id"]

        conflict = client.patch(
            f"/api/v1/admin/teacher-roles/{role_b}",
            headers=headers(admin_token, **{"Idempotency-Key": f"cnf-{uuid4()}"}),
            json={"name": name_a},
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "ROLE_NAME_CONFLICT"

        missing = client.patch(
            f"/api/v1/admin/teacher-roles/{uuid4()}",
            headers=headers(admin_token, **{"Idempotency-Key": f"miss-{uuid4()}"}),
            json={"enabled": False},
        )
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "ROLE_NOT_FOUND"

    def test_invalid_grade_rules_type_rejected(
        self, client: TestClient, admin_token: str
    ) -> None:
        body = _role_body(f"bad-grades-{uuid4()}")
        body["grade_rules"] = "not-dict"
        response = client.post(
            "/api/v1/admin/teacher-roles",
            headers=headers(admin_token, **{"Idempotency-Key": f"bg-{uuid4()}"}),
            json=body,
        )
        assert response.status_code == 422

    def test_create_role_missing_idempotency_422(
        self, client: TestClient, admin_token: str
    ) -> None:
        response = client.post(
            "/api/v1/admin/teacher-roles",
            headers=headers(admin_token),
            json=_role_body(f"no-key-{uuid4()}"),
        )
        assert response.status_code == 422
