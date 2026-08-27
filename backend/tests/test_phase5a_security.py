"""Phase 5-A 验收测试：账号状态、严格后台鉴权、限流、可观测性、幂等过期、
SSE 幂等重放与并发序号。
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import app.modules.admin.service as admin_service_module
from app.config import settings
from app.infrastructure.database.models import (
    Conversation,
    Admin,
    IdempotencyKey,
    Message,
    StudentProfile,
    TeacherRole,
    User,
)
from app.infrastructure.database.session import async_session
from app.main import app
from app.modules.identity.security import hash_password


def _ensure_user(username: str, *, password: str = "p5-pass", user_type: str = "STUDENT", status: str = "ACTIVE") -> str:
    async def run() -> str:
        async with async_session() as session:
            user = (
                await session.execute(select(User).where(User.username == username))
            ).scalar_one_or_none()
            if user is None:
                user = User(
                    username=username,
                    password_hash=hash_password(password),
                    user_type=user_type,
                    status=status,
                )
                session.add(user)
                await session.flush()
            else:
                user.status = status
                user.user_type = user_type
            if user_type == "ADMIN":
                profile = (
                    await session.execute(
                        select(StudentProfile).where(StudentProfile.user_id == user.user_id)
                    )
                ).scalar_one_or_none()
                if profile is None:
                    session.add(StudentProfile(user_id=user.user_id, nickname="P5 管理员", grade=9))
            await session.commit()
            return str(user.user_id)

    asyncio.run(run())


def _set_status(username: str, status: str) -> None:
    async def run() -> None:
        async with async_session() as s:
            user = (await s.execute(select(User).where(User.username == username))).scalar_one()
            user.status = status
            await s.commit()

    asyncio.run(run())


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


class TestAccountStatus:
    def test_login_rejects_disabled_account_without_token(self, client: TestClient):
        _ensure_user("p5_disabled", status="DISABLED")
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "p5_disabled", "password": "p5-pass"},
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "ACCOUNT_DISABLED"
        assert "access_token" not in resp.json().get("data", {})

    def test_disabled_user_token_is_rejected_on_every_api(self, client: TestClient):
        # 先以 ACTIVE 登录取 token，再禁用
        username = f"p5_toggle_{uuid4().hex[:6]}"
        _ensure_user(username, password="toggle-pass")
        client2 = TestClient(app)
        token = client2.post(
            "/api/v1/auth/login", json={"username": username, "password": "toggle-pass"}
        ).json()["data"]["access_token"]

        _set_status(username, "DISABLED")
        resp = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "ACCOUNT_DISABLED"


class TestStrictAdminAuthz:
    def test_admin_without_row_gets_403_admin_profile_required(self, client: TestClient):
        username = f"p5_noRow_{uuid4().hex[:6]}"
        _ensure_user(username, user_type="ADMIN")
        token = client.post(
            "/api/v1/auth/login", json={"username": username, "password": "p5-pass"}
        ).json()["data"]["access_token"]
        resp = client.get("/api/v1/me/admin", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "ADMIN_PROFILE_REQUIRED"

        # 同一 token 访问既有管理端点同样被拒（无 legacy 放行）
        resp2 = client.get("/api/v1/admin/stats", headers={"Authorization": f"Bearer {token}"})
        assert resp2.status_code == 403

    def test_student_cannot_access_me_admin(self, client: TestClient):
        username = f"p5_stu_{uuid4().hex[:6]}"
        _ensure_user(username)
        token = client.post(
            "/api/v1/auth/login", json={"username": username, "password": "p5-pass"}
        ).json()["data"]["access_token"]
        resp = client.get("/api/v1/me/admin", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code in (403,)
        assert resp.json()["error"]["code"] in {"ADMIN_ONLY", "FORBIDDEN"}

    def test_seeded_admin_passes_me_admin(self):
        """seed 创建的 admin 行应能直接通过 require_admin。"""
        from app.scripts.seed import seed as _seed  # noqa: F401  确保存在
        asyncio.run(_seed())
        client = TestClient(app)
        token = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
        ).json()["data"]["access_token"]
        resp = client.get("/api/v1/me/admin", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["display_name"]
        assert data["role_level"]


class TestRateLimit:
    def test_memory_rate_limiter_enforces_window(self):
        from app.infrastructure.rate_limit import rate_limiter

        key = f"unit-{uuid4()}"
        assert rate_limiter.check(key, limit=2, window_seconds=60).allowed
        assert rate_limiter.check(key, limit=2, window_seconds=60).allowed
        blocked = rate_limiter.check(key, limit=2, window_seconds=60)
        assert not blocked.allowed and blocked.retry_after >= 1

    def test_login_rate_limited_returns_standard_envelope(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "rate_limit_login_per_minute", 1)
        username = f"p5_rl_{uuid4().hex[:6]}"
        _ensure_user(username)

        first = client.post("/api/v1/auth/login", json={"username": username, "password": "wrong"})
        assert first.status_code in (200, 401)  # 第一次允许通过（凭据错误也计数）

        second = client.post("/api/v1/auth/login", json={"username": username, "password": "wrong"})
        assert second.status_code == 429
        body = second.json()["error"]
        assert body["code"] == "RATE_LIMITED"
        assert second.headers.get("Retry-After")


class TestObservability:
    def test_request_id_header_present_and_error_carries_it(self, client: TestClient):
        ok_resp = client.get("/health", headers={"X-Request-ID": "req-fixed-1"})
        assert ok_resp.headers["X-Request-ID"] == "req-fixed-1"

        err = client.get("/api/v1/me")  # 无 token → 401
        assert err.status_code == 401
        rid = err.headers.get("X-Request-ID")
        assert rid, "错误响应必须携带 request_id"
        err_body = err.json()["error"]
        assert isinstance(err_body, dict)

    def test_access_log_never_contains_authorization_or_token(self, client: TestClient, caplog):
        import logging as _logging

        secret = "Bearer super-secret-token-value"
        with caplog.at_level(_logging.INFO, logger="shuangling.access"):
            client.get("/health", headers={"Authorization": secret})
        access_records = [r for r in caplog.records if r.name == "shuangling.access"]
        assert access_records, "应产出访问日志"
        for record in access_records:
            dumped = json.dumps(record.__dict__.get("http", {}), ensure_ascii=False)
            assert "super-secret-token-value" not in dumped
            assert "Authorization" not in dumped
            assert "authorization" not in dumped

    def test_metrics_endpoint_exposes_counters(self, client: TestClient):
        client.get("/health")  # 至少产生一次采样
        resp = client.get("/metrics")
        assert resp.status_code == 200
        text = resp.text
        assert "http_requests_total" in text
        assert 'status="200"' in text
        assert 'env="test"' in text or 'env="' in text


class TestIdempotencyExpiry:
    def test_expired_key_is_not_replayed(self, monkeypatch: pytest.MonkeyPatch):
        actor_id = uuid4()
        key = f"exp-{uuid4()}"

        async def scenario():
            async with async_session() as session:
                # 直接插入一条已过期的幂等记录
                session.add(
                    IdempotencyKey(
                        idempotency_id=uuid4(),
                        actor_id=actor_id,
                        actor_type="ADMIN",
                        key=key,
                        request_hash="hash-old",
                        response={"stale": True},
                        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
                    )
                )
                await session.commit()

                service = admin_service_module.IdempotencyService()
                calls = {"n": 0}

                async def handler():
                    calls["n"] += 1
                    return {"fresh": calls["n"]}

                result, replayed = await service.execute(
                    session,
                    actor_id=actor_id,
                    actor_type="ADMIN",
                    key=key,
                    request_hash="hash-new",
                    handler=handler,
                )
                await session.commit()
                return result, replayed, calls["n"]

        result, replayed, calls = asyncio.run(scenario())
        assert replayed is False
        assert calls == 1
        assert result == {"fresh": 1}


class TestSSEMessageIdempotency:
    @pytest.fixture(scope="class")
    def conversation_env(self):
        owner = f"p5_sse_{uuid4().hex[:6]}"
        _ensure_user(owner, password="sse-pass")

        async def make_conv():
            async with async_session() as s:
                user = (
                    await s.execute(select(User).where(User.username == owner))
                ).scalar_one()
                profile = (
                    await s.execute(
                        select(StudentProfile).where(StudentProfile.user_id == user.user_id)
                    )
                ).scalar_one_or_none()
                if profile is None:
                    profile = StudentProfile(
                        user_id=user.user_id, nickname="replay", grade=8
                    )
                    s.add(profile)
                    await s.flush()
                role_id = uuid4()
                s.add(
                    TeacherRole(
                        role_id=role_id,
                        name=f"风格-{owner}",
                        tone="温和",
                        teaching_style="启发式",
                        persona={"base_persona": "t"},
                        sprite_manifest={},
                        grade_rules={},
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await s.flush()
                conv = Conversation(
                    student_id=profile.student_id,
                    teacher_role_id=role_id,
                    title="replay",
                    channel="TEXT",
                    status="ACTIVE",
                    current_page_context={},
                    recent_messages=[],
                )
                s.add(conv)
                await s.commit()
                return str(conv.conversation_id)

        cid = asyncio.run(make_conv())
        client = TestClient(app)
        token = client.post(
            "/api/v1/auth/login", json={"username": owner, "password": "sse-pass"}
        ).json()["data"]["access_token"]
        return client, token, cid

    @staticmethod
    def parse_sse(raw: str) -> list[dict]:
        events = []
        for frame in raw.split("\n\n"):
            if not frame.strip() or frame.lstrip().startswith(":"):
                continue
            name = None
            data_lines = []
            for line in frame.splitlines():
                if line.startswith("event: "):
                    name = line[7:]
                elif line.startswith("data: "):
                    data_lines.append(line[6:])
            if name and data_lines:
                events.append({"event": name, "data": json.loads("\n".join(data_lines))})
        return events

    def test_duplicate_key_returns_replay_and_single_student_message(
        self, conversation_env
    ):
        client, token, cid = conversation_env
        key = f"idem-{uuid4()}"

        def send():
            return client.post(
                f"/api/v1/conversations/{cid}/messages",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "text/event-stream",
                    "Idempotency-Key": key,
                },
                json={"content": "给我出题"},
            )

        first = send()
        assert first.status_code == 200
        events1 = self.parse_sse(first.text)
        done1 = next(e for e in events1 if e["event"] == "text.done")
        content1 = done1["data"]["content"]

        async def student_rows():
            async with async_session() as s:
                rows = (
                    await s.execute(
                        select(Message).where(
                            Message.conversation_id == UUID(cid),
                            Message.role == "STUDENT",
                        )
                    )
                ).scalars().all()
                return rows

        rows_after_first = asyncio.run(student_rows())
        matched_first = [
            row
            for row in rows_after_first
            if (row.metadata_ or {}).get("idempotency_key") == key
        ]
        assert len(matched_first) == 1, "首次请求应写入带 key 的学生消息"
        student_sequence = matched_first[0].sequence

        second = send()
        assert second.status_code == 200
        events2 = self.parse_sse(second.text)
        done2 = next(e for e in events2 if e["event"] == "text.done")

        # 可消费的重放：恢复原教师正文
        assert done2["data"]["content"] == content1

        # 不新增第二条学生消息
        rows_after_second = asyncio.run(student_rows())
        matched_second = [
            row
            for row in rows_after_second
            if (row.metadata_ or {}).get("idempotency_key") == key
        ]
        assert len(matched_second) == 1
        assert matched_second[0].sequence == student_sequence


class TestConcurrentSequences:
    def test_concurrent_messages_have_unique_sequences(self, client: TestClient):
        owner = f"p5_seq_{uuid4().hex[:6]}"
        _ensure_user(owner, password="seq-pass")

        async def make_conv():
            async with async_session() as s:
                user = (
                    await s.execute(select(User).where(User.username == owner))
                ).scalar_one()
                profile = (
                    await s.execute(
                        select(StudentProfile).where(StudentProfile.user_id == user.user_id)
                    )
                ).scalar_one_or_none()
                if profile is None:
                    profile = StudentProfile(user_id=user.user_id, nickname='seq', grade=8)
                    s.add(profile)
                    await s.flush()
                conv = Conversation(
                    student_id=profile.student_id,
                    title="seq",
                    channel="TEXT",
                    status="ACTIVE",
                    current_page_context={},
                    recent_messages=[],
                )
                s.add(conv)
                await s.commit()
                return str(conv.conversation_id), str(user.user_id)

        cid, sid = asyncio.run(make_conv())

        async def fire_parallel():
            async def one(idx: int) -> int:
                async with async_session() as session:
                    svc = __import__(
                        "app.modules.conversation.service",
                        fromlist=["ConversationService"],
                    ).ConversationService()
                    stream = await svc.send_message(
                        session,
                        UUID(sid),
                        UUID(cid),
                        __import__(
                            "app.modules.conversation.schemas", fromlist=["SendMessageRequest"]
                        ).SendMessageRequest(content=f"并发消息 {idx}"),
                        idempotency_key=f"seq-{idx}",
                    )
                    async for _frame in stream:
                        pass
                    return idx

            results = await asyncio.gather(one(0), one(1))
            async with async_session() as s:
                rows = (
                    await s.execute(
                        select(Message)
                        .where(
                            Message.conversation_id == UUID(cid),
                            Message.role == "STUDENT",
                        )
                        .order_by(Message.sequence.asc())
                    )
                ).scalars().all()
                seqs = [r.sequence for r in rows]
                return seqs, len(rows)

        seqs, count = asyncio.run(fire_parallel())
        assert count == 2
        assert len(set(seqs)) == 2, f"并发学生消息 sequence 不得重复：{seqs}"


class TestGlobalApiRateLimit:
    def test_api_limit_returns_429_with_headers(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        from app.infrastructure.rate_limit import rate_limiter

        # 隔离：清空共享的进程内桶，避免其他用例消耗同一 IP 配额
        rate_limiter._memory._hits.clear()
        monkeypatch.setattr(settings, "rate_limit_enabled", True)
        monkeypatch.setattr(settings, "rate_limit_api_per_minute", 2)

        # 前两次允许（/health 与 /api/v1/ping 都计入 api 桶，但 /health 被排除）
        r1 = client.get("/api/v1/ping", headers={"X-Request-ID": "rl-1"})
        r2 = client.get("/api/v1/ping", headers={"X-Request-ID": "rl-2"})
        assert r1.status_code == 200
        assert r2.status_code == 200

        third = client.get("/api/v1/ping", headers={"X-Request-ID": "rl-3"})
        assert third.status_code == 429
        assert third.json()["error"]["code"] == "RATE_LIMITED"
        assert int(third.headers["Retry-After"]) >= 1
        assert third.headers["X-Request-ID"] == "rl-3"

        # 探活与监控端点不受限
        assert client.get("/health").status_code == 200
        assert client.get("/metrics").status_code == 200

    def test_disabled_switch_turns_limiting_off(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "rate_limit_enabled", False)
        monkeypatch.setattr(settings, "rate_limit_api_per_minute", 1)
        for _ in range(5):
            resp = client.get("/api/v1/ping")
            assert resp.status_code == 200

    def test_login_path_excluded_from_global_bucket(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        """登录接口只受 login 维度限流：全局桶打满不影响它。"""
        monkeypatch.setattr(settings, "rate_limit_enabled", True)
        # 先把全局桶打满（用同一 client IP）
        for _ in range(3):
            client.get("/api/v1/ping")
        username = f"p5_rl_excl_{uuid4().hex[:6]}"
        _ensure_user(username)
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": "p5-pass"},
        )
        assert resp.status_code in (200, 401), "登录不应被全局限流拦截"

    def test_memory_window_sweep_and_capacity(self):
        from app.infrastructure.rate_limit import _MemoryWindow

        window = _MemoryWindow()
        window.MAX_TRACKED_KEYS = 50
        for i in range(500):
            window.check(f"k-{i}", limit=10**6, window_seconds=60)
        # 显式触发一次全表清扫 + 容量淘汰
        window._sweep(window_seconds=60)
        assert len(window._hits) <= 50, f"容量上限应生效，实际 {len(window._hits)}"
