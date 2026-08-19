"""Phase 10 Admin API tests (admins + idempotency + books/content)."""

import asyncio
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text, select

from app.infrastructure.database.models import (
    Admin,
    StudentProfile,
    User,
)
from app.infrastructure.database.session import async_session
from app.main import app
from app.modules.identity.security import hash_password


ADMIN_NAME = "test_admin_user"
ADMIN_PASSWORD = "adminpass"
STUDENT_NAME = "test_admin_student"
STUDENT_PASSWORD = "studentpass"


def _ensure_admin() -> UUID:
    async def run() -> UUID:
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
                admin = Admin(
                    user_id=user.user_id,
                    display_name="测试管理员",
                    role_level="SUPERVISOR",
                    enabled=True,
                )
                session.add(admin)
                await session.flush()
            await session.commit()
            return admin.admin_id

    return asyncio.run(run())


def _ensure_student() -> None:
    async def run() -> None:
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
                session.add(
                    StudentProfile(
                        user_id=user.user_id,
                        nickname="管理员测试学生",
                        grade=8,
                        language="zh-CN",
                    )
                )
            await session.commit()

    asyncio.run(run())


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


BOOK_BODY = {
    "title": f"管理端测试书-{uuid4()}",
    "grade_min": 7,
    "grade_max": 9,
    "difficulty": "MEDIUM",
    "estimated_minutes": 30,
    "tags": ["测试"],
}


class TestAdminAPI:
    def test_stats_returns_reasonable_counts(
        self, client: TestClient, admin_token: str
    ) -> None:
        response = client.get("/api/v1/admin/stats", headers=headers(admin_token))
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["books_total"] >= 0
        assert data["students_total"] >= 1

    def test_create_book_requires_idempotency_and_replays(
        self, client: TestClient, admin_token: str
    ) -> None:
        body = dict(BOOK_BODY, title=f"幂等测试书-{uuid4()}")
        missing = client.post(
            "/api/v1/admin/books",
            headers=headers(admin_token),
            json=body,
        )
        assert missing.status_code == 422

        key = f"book-{uuid4()}"
        created = client.post(
            "/api/v1/admin/books",
            headers=headers(admin_token, **{"Idempotency-Key": key}),
            json=body,
        )
        assert created.status_code == 201
        book_id = created.json()["data"]["book_id"]
        assert created.json()["data"]["created_by"]

        replay = client.post(
            "/api/v1/admin/books",
            headers=headers(admin_token, **{"Idempotency-Key": key}),
            json=body,
        )
        assert replay.status_code == 200
        assert replay.json()["data"]["book_id"] == book_id

        conflict = client.post(
            "/api/v1/admin/books",
            headers=headers(admin_token, **{"Idempotency-Key": key}),
            json=dict(body, title="不同标题"),
        )
        assert conflict.status_code == 409

    def test_publish_requires_chapter_and_content_crud(
        self, client: TestClient, admin_token: str
    ) -> None:
        created = client.post(
            "/api/v1/admin/books",
            headers=headers(admin_token, **{"Idempotency-Key": f"crud-{uuid4()}"}),
            json=dict(BOOK_BODY, title=f"发布测试书-{uuid4()}"),
        )
        assert created.status_code == 201
        book_id = created.json()["data"]["book_id"]

        invalid_publish = client.patch(
            f"/api/v1/admin/books/{book_id}",
            headers=headers(admin_token, **{"Idempotency-Key": f"pub-{uuid4()}"}),
            json={"status": "PUBLISHED"},
        )
        assert invalid_publish.status_code == 422

        chapter = client.post(
            f"/api/v1/admin/books/{book_id}/chapters",
            headers=headers(admin_token, **{"Idempotency-Key": f"ch-{uuid4()}"}),
            json={"title": "第一章"},
        )
        assert chapter.status_code == 201
        chapter_id = chapter.json()["data"]["chapter_id"]

        block = client.post(
            f"/api/v1/admin/chapters/{chapter_id}/content-blocks",
            headers=headers(admin_token, **{"Idempotency-Key": f"blk-{uuid4()}"}),
            json={
                "block_type": "PARAGRAPH",
                "content": {"text": "正文"},
            },
        )
        assert block.status_code == 201
        block_id = block.json()["data"]["block_id"]

        patched_block = client.patch(
            f"/api/v1/admin/content-blocks/{block_id}",
            headers=headers(admin_token, **{"Idempotency-Key": f"pblk-{uuid4()}"}),
            json={"content": {"text": "更新正文"}},
        )
        assert patched_block.status_code == 200

        published = client.patch(
            f"/api/v1/admin/books/{book_id}",
            headers=headers(admin_token, **{"Idempotency-Key": f"pub2-{uuid4()}"}),
            json={"status": "PUBLISHED"},
        )
        assert published.status_code == 200
        assert published.json()["data"]["status"] == "PUBLISHED"

        listed = client.get(
            "/api/v1/admin/books?status=PUBLISHED",
            headers=headers(admin_token),
        )
        assert any(row["book_id"] == book_id for row in listed.json()["data"])

    def test_knowledge_point_crud(
        self, client: TestClient, admin_token: str
    ) -> None:
        point = client.post(
            "/api/v1/admin/knowledge-points",
            headers=headers(admin_token, **{"Idempotency-Key": f"kp-{uuid4()}"}),
            json={"name": f"管理端知识点-{uuid4()}"},
        )
        assert point.status_code == 201
        point_id = point.json()["data"]["knowledge_point_id"]

        updated = client.patch(
            f"/api/v1/admin/knowledge-points/{point_id}",
            headers=headers(admin_token, **{"Idempotency-Key": f"pkp-{uuid4()}"}),
            json={"topic": "测试"},
        )
        assert updated.status_code == 200
        assert updated.json()["data"]["slug"]

    def test_admin_only_and_authentication(
        self,
        client: TestClient,
        student_token: str,
    ) -> None:
        forbidden = client.get(
            "/api/v1/admin/stats",
            headers=headers(student_token),
        )
        assert forbidden.status_code == 403
        assert forbidden.json()["error"]["code"] == "ADMIN_ONLY"

        assert client.get("/api/v1/admin/stats").status_code == 401

    def test_deferred_fks_are_present(self) -> None:
        async def run() -> set[str]:
            async with async_session() as session:
                rows = (
                    await session.execute(
                        text(
                            "SELECT conname FROM pg_constraint "
                            "WHERE conname IN "
                            "('fk_books_created_by_admin','fk_knowledge_resources_uploaded_by_admin')"
                        )
                    )
                ).scalars().all()
                return set(rows)

        constraints = asyncio.run(run())
        assert "fk_books_created_by_admin" in constraints
        assert "fk_knowledge_resources_uploaded_by_admin" in constraints

    def test_knowledge_upload_reprocess_and_metadata_patch(
        self,
        client: TestClient,
        admin_token: str,
    ) -> None:
        content = "# 上传测试\n\n这是一段用于验证上传管线的知识内容。".encode("utf-8")
        uploaded = client.post(
            "/api/v1/admin/knowledge/resources",
            headers=headers(admin_token, **{"Idempotency-Key": f"upload-{uuid4()}"}),
            files={"file": ("upload-test.md", content, "text/markdown")},
            data={
                "source_name": "上传测试资源",
                "source_url": "https://test.shuangling.local/upload-test",
                "license": "CC-BY-4.0",
                "copyright_status": "测试",
            },
        )
        assert uploaded.status_code == 201
        data = uploaded.json()["data"]
        assert data["status"] == "READY"
        resource_id = data["resource_id"]

        listed = client.get(
            "/api/v1/knowledge/resources?status=READY",
            headers=headers(admin_token),
        )
        assert any(row["resource_id"] == resource_id for row in listed.json()["data"])

        patched = client.patch(
            f"/api/v1/admin/knowledge/resources/{resource_id}",
            headers=headers(
                admin_token, **{"Idempotency-Key": f"patch-resource-{uuid4()}"}
            ),
            json={"source_name": "上传测试资源（已更新）"},
        )
        assert patched.status_code == 200
        assert patched.json()["data"]["source_name"] == "上传测试资源（已更新）"

        reprocessed = client.post(
            f"/api/v1/admin/knowledge/resources/{resource_id}/reprocess",
            headers=headers(
                admin_token, **{"Idempotency-Key": f"reprocess-{uuid4()}"}
            ),
        )
        assert reprocessed.status_code == 200
        assert reprocessed.json()["data"]["status"] == "READY"

        pdf = client.post(
            "/api/v1/admin/knowledge/resources",
            headers=headers(admin_token, **{"Idempotency-Key": "upload-pdf-1"}),
            files={"file": ("book.pdf", b"%PDF-1.4", "application/pdf")},
            data={
                "source_name": "PDF 测试",
                "source_url": "https://test.shuangling.local/book.pdf",
                "license": "CC-BY-4.0",
                "copyright_status": "测试",
            },
        )
        assert pdf.status_code == 422
        assert pdf.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"

        missing_key = client.post(
            "/api/v1/admin/knowledge/resources",
            headers=headers(admin_token),
            files={"file": ("upload-test.md", content, "text/markdown")},
            data={
                "source_name": "无幂等键",
                "source_url": "https://test.shuangling.local/no-key",
                "license": "CC-BY-4.0",
                "copyright_status": "测试",
            },
        )
        assert missing_key.status_code == 422

    def test_get_missing_book_returns_404(
        self, client: TestClient, admin_token: str
    ) -> None:
        response = client.get(
            f"/api/v1/admin/books/{uuid4()}",
            headers=headers(admin_token),
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "BOOK_NOT_FOUND"

    def test_patch_missing_content_returns_404(
        self, client: TestClient, admin_token: str
    ) -> None:
        chapter = client.patch(
            f"/api/v1/admin/chapters/{uuid4()}",
            headers=headers(admin_token, **{"Idempotency-Key": f"ch404-{uuid4()}"}),
            json={"title": "不存在"},
        )
        assert chapter.status_code == 404
        assert chapter.json()["error"]["code"] == "CHAPTER_NOT_FOUND"

        block = client.patch(
            f"/api/v1/admin/content-blocks/{uuid4()}",
            headers=headers(admin_token, **{"Idempotency-Key": f"blk404-{uuid4()}"}),
            json={"content": {"text": "x"}},
        )
        assert block.status_code == 404
        assert block.json()["error"]["code"] == "CONTENT_BLOCK_NOT_FOUND"

        point = client.patch(
            f"/api/v1/admin/knowledge-points/{uuid4()}",
            headers=headers(admin_token, **{"Idempotency-Key": f"kp404-{uuid4()}"}),
            json={"topic": "x"},
        )
        assert point.status_code == 404
        assert point.json()["error"]["code"] == "KNOWLEDGE_POINT_NOT_FOUND"

    def test_publish_grade_range_and_archive_transitions(
        self, client: TestClient, admin_token: str
    ) -> None:
        created = client.post(
            "/api/v1/admin/books",
            headers=headers(admin_token, **{"Idempotency-Key": f"grade-{uuid4()}"}),
            json=dict(BOOK_BODY, title=f"发布边界书-{uuid4()}"),
        )
        book_id = created.json()["data"]["book_id"]

        invalid_grade = client.patch(
            f"/api/v1/admin/books/{book_id}",
            headers=headers(admin_token, **{"Idempotency-Key": f"badgrade-{uuid4()}"}),
            json={"grade_min": 9, "grade_max": 7, "status": "PUBLISHED"},
        )
        assert invalid_grade.status_code == 422

        chapter = client.post(
            f"/api/v1/admin/books/{book_id}/chapters",
            headers=headers(admin_token, **{"Idempotency-Key": f"chgrade-{uuid4()}"}),
            json={"title": "章"},
        )
        assert chapter.status_code == 201

        archived = client.patch(
            f"/api/v1/admin/books/{book_id}",
            headers=headers(admin_token, **{"Idempotency-Key": f"arch-{uuid4()}"}),
            json={"status": "ARCHIVED"},
        )
        assert archived.status_code == 200

        reactivate = client.patch(
            f"/api/v1/admin/books/{book_id}",
            headers=headers(admin_token, **{"Idempotency-Key": f"react-{uuid4()}"}),
            json={"status": "DRAFT"},
        )
        assert reactivate.status_code == 409
        assert reactivate.json()["error"]["code"] == "BOOK_INVALID_STATUS"

    def test_patch_book_idempotency_boundaries(
        self, client: TestClient, admin_token: str
    ) -> None:
        created = client.post(
            "/api/v1/admin/books",
            headers=headers(admin_token, **{"Idempotency-Key": f"pidem-{uuid4()}"}),
            json=dict(BOOK_BODY, title=f"PATCH 幂等书-{uuid4()}"),
        )
        book_id = created.json()["data"]["book_id"]
        key = f"patch-key-{uuid4()}"
        body = {"title": "PATCH 幂等标题"}

        missing = client.patch(
            f"/api/v1/admin/books/{book_id}",
            headers=headers(admin_token),
            json=body,
        )
        assert missing.status_code == 422

        first = client.patch(
            f"/api/v1/admin/books/{book_id}",
            headers=headers(admin_token, **{"Idempotency-Key": key}),
            json=body,
        )
        assert first.status_code == 200

        replay = client.patch(
            f"/api/v1/admin/books/{book_id}",
            headers=headers(admin_token, **{"Idempotency-Key": key}),
            json=body,
        )
        assert replay.status_code == 200
        assert replay.json()["data"]["title"] == "PATCH 幂等标题"

        conflict = client.patch(
            f"/api/v1/admin/books/{book_id}",
            headers=headers(admin_token, **{"Idempotency-Key": key}),
            json={"title": "冲突标题"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    def test_reprocess_missing_resource_404(
        self, client: TestClient, admin_token: str
    ) -> None:
        response = client.post(
            f"/api/v1/admin/knowledge/resources/{uuid4()}/reprocess",
            headers=headers(admin_token, **{"Idempotency-Key": f"re404-{uuid4()}"}),
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"

    def test_upload_unknown_extension_422(
        self, client: TestClient, admin_token: str
    ) -> None:
        response = client.post(
            "/api/v1/admin/knowledge/resources",
            headers=headers(admin_token, **{"Idempotency-Key": f"docx-{uuid4()}"}),
            files={"file": ("notes.docx", b"x", "application/octet-stream")},
            data={
                "source_name": "DOCX",
                "source_url": "https://test.shuangling.local/docx",
                "license": "CC-BY-4.0",
                "copyright_status": "测试",
            },
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"

    def test_student_cannot_upload(
        self, client: TestClient, student_token: str
    ) -> None:
        response = client.post(
            "/api/v1/admin/knowledge/resources",
            headers=headers(student_token, **{"Idempotency-Key": f"stu-{uuid4()}"}),
            files={"file": ("x.md", b"# x", "text/markdown")},
            data={
                "source_name": "学生",
                "source_url": "https://test.shuangling.local/stu",
                "license": "CC-BY-4.0",
                "copyright_status": "测试",
            },
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "ADMIN_ONLY"

    def test_stats_change_after_new_book_and_resource(
        self, client: TestClient, admin_token: str
    ) -> None:
        before = client.get("/api/v1/admin/stats", headers=headers(admin_token)).json()[
            "data"
        ]
        created = client.post(
            "/api/v1/admin/books",
            headers=headers(admin_token, **{"Idempotency-Key": f"statbook-{uuid4()}"}),
            json=dict(BOOK_BODY, title=f"统计书-{uuid4()}"),
        )
        assert created.status_code == 201
        uploaded = client.post(
            "/api/v1/admin/knowledge/resources",
            headers=headers(admin_token, **{"Idempotency-Key": f"statres-{uuid4()}"}),
            files={
                "file": (
                    "stats.md",
                    "# 统计\n\n内容".encode("utf-8"),
                    "text/markdown",
                )
            },
            data={
                "source_name": "统计资源",
                "source_url": f"https://test.shuangling.local/stats-{uuid4()}",
                "license": "CC-BY-4.0",
                "copyright_status": "测试",
            },
        )
        assert uploaded.status_code == 201
        after = client.get("/api/v1/admin/stats", headers=headers(admin_token)).json()[
            "data"
        ]
        assert after["books_total"] == before["books_total"] + 1
        assert after["resources_total"] == before["resources_total"] + 1

    def test_upload_replay_returns_same_resource(
        self, client: TestClient, admin_token: str
    ) -> None:
        key = f"upload-replay-{uuid4()}"
        content = b"# replay\n\ncontent"
        source_url = f"https://test.shuangling.local/replay-{uuid4()}"
        first = client.post(
            "/api/v1/admin/knowledge/resources",
            headers=headers(admin_token, **{"Idempotency-Key": key}),
            files={"file": ("replay.md", content, "text/markdown")},
            data={
                "source_name": "上传重放",
                "source_url": source_url,
                "license": "CC-BY-4.0",
                "copyright_status": "测试",
            },
        )
        assert first.status_code == 201
        replay = client.post(
            "/api/v1/admin/knowledge/resources",
            headers=headers(admin_token, **{"Idempotency-Key": key}),
            files={"file": ("replay.md", content, "text/markdown")},
            data={
                "source_name": "上传重放",
                "source_url": source_url,
                "license": "CC-BY-4.0",
                "copyright_status": "测试",
            },
        )
        assert replay.status_code == 200
        assert replay.json()["data"]["resource_id"] == first.json()["data"]["resource_id"]

    def test_create_book_invalid_grade_422(
        self, client: TestClient, admin_token: str
    ) -> None:
        response = client.post(
            "/api/v1/admin/books",
            headers=headers(admin_token, **{"Idempotency-Key": f"badgrade-{uuid4()}"}),
            json={
                "title": "非法年级书",
                "grade_min": 9,
                "grade_max": 7,
                "difficulty": "MEDIUM",
                "estimated_minutes": 30,
            },
        )
        assert response.status_code == 422

    def test_create_chapter_missing_book_404(
        self, client: TestClient, admin_token: str
    ) -> None:
        response = client.post(
            f"/api/v1/admin/books/{uuid4()}/chapters",
            headers=headers(admin_token, **{"Idempotency-Key": f"chbook-{uuid4()}"}),
            json={"title": "章"},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "BOOK_NOT_FOUND"

    def test_create_content_block_missing_chapter_404(
        self, client: TestClient, admin_token: str
    ) -> None:
        response = client.post(
            f"/api/v1/admin/chapters/{uuid4()}/content-blocks",
            headers=headers(admin_token, **{"Idempotency-Key": f"blkchapter-{uuid4()}"}),
            json={"block_type": "PARAGRAPH", "content": {"text": "x"}},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CHAPTER_NOT_FOUND"

    def test_create_knowledge_point_duplicate_slug_409(
        self, client: TestClient, admin_token: str
    ) -> None:
        name = f"重复知识点-{uuid4()}"
        first = client.post(
            "/api/v1/admin/knowledge-points",
            headers=headers(admin_token, **{"Idempotency-Key": f"kpq-{uuid4()}"}),
            json={"name": name},
        )
        assert first.status_code == 201
        duplicate = client.post(
            "/api/v1/admin/knowledge-points",
            headers=headers(admin_token, **{"Idempotency-Key": f"kpq2-{uuid4()}"}),
            json={"name": name},
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "KNOWLEDGE_POINT_SLUG_EXISTS"

    def test_create_content_missing_idempotency_422(
        self, client: TestClient, admin_token: str
    ) -> None:
        created = client.post(
            "/api/v1/admin/books",
            headers=headers(admin_token, **{"Idempotency-Key": f"nokey-{uuid4()}"}),
            json=dict(BOOK_BODY, title=f"缺幂等键书-{uuid4()}"),
        )
        book_id = created.json()["data"]["book_id"]
        response = client.post(
            f"/api/v1/admin/books/{book_id}/chapters",
            headers=headers(admin_token),
            json={"title": "章"},
        )
        assert response.status_code == 422
