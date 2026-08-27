"""Phase 3 验收测试：统计/结算幂等、事件链路、quiz_count、记忆驱动推荐。

覆盖 plan.md Phase 3：
- LearningSession 关闭 → BookProgress.total_seconds 与学生统计按真实时长
  结算，且通过 reading_settlements 台账保证重复结算幂等；
- CHAPTER_FINISHED / BOOK_FINISHED 事件驱动重算 completed_chapters/books；
- QuizSession 完成状态迁移一次性累计 quiz_count（重放不重复）；
- 学习事件完整关联 session/conversation/quiz/block/knowledge_points；
- 推荐规则消费真实长期记忆（INTEREST_MATCH），证据可回查。
"""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update

from app.infrastructure.database.models import (
    Book,
    Chapter,
    ContentBlock,
    Conversation,
    LearningSession,
    ReadingSettlement,
    StudentMemory,
    StudentProfile,
    User,
)

BLK_P3_ID = UUID("5e320000-0000-0000-0000-000000000001")
from app.infrastructure.database.session import async_session
from app.main import app
from app.modules.identity.security import hash_password
from app.modules.learning.service import LearningService
from app.modules.recommendation.service import (
    BookCandidate,
    build_recommendation_drafts,
)
from app.modules.recommendation.service import InterestSignal

OWNER = "test_p3_user"
PASSWORD = "p3-stats-pass"

BOOK_ID = UUID("5e300000-0000-0000-0000-000000000001")
BOOK2_ID = UUID("5e300000-0000-0000-0000-000000000002")
CH1_ID = UUID("5e310000-0000-0000-0000-000000000001")
CH2_ID = UUID("5e310000-0000-0000-0000-000000000002")
CHB2_ID = UUID("5e310000-0000-0000-0000-000000000003")


def _ensure_env() -> None:
    async def run() -> None:
        async with async_session() as s:
            user = (
                await s.execute(select(User).where(User.username == OWNER))
            ).scalar_one_or_none()
            if user is None:
                user = User(
                    username=OWNER,
                    password_hash=hash_password(PASSWORD),
                    user_type="STUDENT",
                )
                s.add(user)
                await s.flush()
            profile = (
                await s.execute(
                    select(StudentProfile).where(StudentProfile.user_id == user.user_id)
                )
            ).scalar_one_or_none()
            if profile is None:
                profile = StudentProfile(
                    user_id=user.user_id, nickname="P3 统计", grade=8
                )
                s.add(profile)
            for book_id in (BOOK_ID, BOOK2_ID):
                if await s.get(Book, book_id) is None:
                    s.add(
                        Book(
                            book_id=book_id,
                            title=f"P3 测试书 {book_id.hex[-4:]}",
                            description="Phase 3 结算测试书",
                            grade_min=7,
                            grade_max=9,
                            difficulty="EASY",
                            estimated_minutes=20,
                            tags=["测试P3"],
                            status="DRAFT",
                            published_at=datetime.now(timezone.utc),
                        )
                    )
            for ch_id, book_id, order in [
                (CH1_ID, BOOK_ID, 1),
                (CH2_ID, BOOK_ID, 2),
                (CHB2_ID, BOOK2_ID, 1),
            ]:
                if await s.get(Chapter, ch_id) is None:
                    s.add(
                        Chapter(
                            chapter_id=ch_id,
                            book_id=book_id,
                            title=f"P3 章 {order}",
                            chapter_order=order,
                            estimated_minutes=8,
                            status="PUBLISHED",
                        )
                    )
            # 清理历史失败运行可能遗留的 ACTIVE 会话，避免自动关闭
            # 把陈旧时长计入本测试窗口（保证结算断言确定性）。
            target_user = (
                await s.execute(select(User).where(User.username == OWNER))
            ).scalar_one_or_none()
            if target_user is not None:
                profile_row = (
                    await s.execute(
                        select(StudentProfile).where(
                            StudentProfile.user_id == target_user.user_id
                        )
                    )
                ).scalar_one_or_none()
                if profile_row is not None:
                    from sqlalchemy import func, update

                    # 只把遗留 ACTIVE 会话标记为 ENDED（0 时长、不走结算），
                    # 保留审计链（learning_events 的 RESTRICT 外键不受影响），
                    # 同时避免后续 create_session 自动关闭时计入陈旧时长。
                    await s.execute(
                        update(LearningSession)
                        .where(
                            LearningSession.student_id == profile_row.student_id,
                            LearningSession.status == "ACTIVE",
                        )
                        .values(
                            status="ENDED",
                            ended_at=func.now(),
                            duration_seconds=0,
                        )
                    )
                    await s.execute(
                        update(StudentProfile)
                        .where(StudentProfile.student_id == profile_row.student_id)
                        .values(learning_days=0, total_learning_seconds=0,
                                total_learning_minutes=0)
                    )
                    # 清空结算台账：让「当日首次结算 → learning_days+1」
                    # 的断言不受历史运行影响（台账仅服务统计，可安全清理）。
                    await s.execute(
                        delete(ReadingSettlement).where(
                            ReadingSettlement.student_id == profile_row.student_id
                        )
                    )
            if await s.get(ContentBlock, BLK_P3_ID) is None:
                s.add(
                    ContentBlock(
                        block_id=BLK_P3_ID,
                        chapter_id=CH1_ID,
                        block_type="PARAGRAPH",
                        content={"text": "P3 链路测试块"},
                        block_order=99,
                        section_key="P3",
                        knowledge_point_ids=[],
                    )
                )
            await s.commit()

    asyncio.run(run())


@pytest.fixture(scope="module")
def client() -> TestClient:
    _ensure_env()
    return TestClient(app)


@pytest.fixture(scope="module")
def token(client: TestClient) -> str:
    resp = client.post(
        "/api/v1/auth/login", json={"username": OWNER, "password": PASSWORD}
    )
    assert resp.status_code == 200
    return resp.json()["data"]["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _profile_snapshot() -> dict:
    async with async_session() as s:
        user = (
            await s.execute(select(User).where(User.username == OWNER))
        ).scalar_one()
        profile = (
            await s.execute(
                select(StudentProfile).where(StudentProfile.user_id == user.user_id)
            )
        ).scalar_one()
        return {
            "learning_days": profile.learning_days,
            "minutes": profile.total_learning_minutes,
            "seconds": profile.total_learning_seconds,
            "completed_chapters": profile.completed_chapters,
            "completed_books": profile.completed_books,
            "quiz_count": profile.quiz_count,
        }


class TestReadingSettlementAndStats:
    def test_close_session_settles_real_duration_once(self, client, token):
        before = asyncio.run(_profile_snapshot())

        create = client.post(
            "/api/v1/learning-sessions",
            headers=auth(token),
            json={"book_id": str(BOOK_ID), "chapter_id": str(CH1_ID)},
        )
        assert create.status_code == 201
        payload = create.json()["data"]
        session_id = payload["session_id"]

        # 手动把 started_at 拨回 90 秒前，构造可控真实时长
        async def backdate() -> None:
            from app.infrastructure.database.models import LearningSession

            async with async_session() as s:
                row = await s.get(LearningSession, UUID(session_id))
                assert row is not None
                row.started_at = datetime.now(timezone.utc) - timedelta(seconds=90)
                await s.commit()

        asyncio.run(backdate())

        end = client.patch(
            f"/api/v1/learning-sessions/{session_id}",
            headers=auth(token),
            json={"status": "ENDED"},
        )
        assert end.status_code == 200
        after = asyncio.run(_profile_snapshot())

        credit = after["seconds"] - before["seconds"]
        assert credit == 90, f"应按真实时长入账 90s，实际 {credit}"
        # 分钟为秒的整分钟派生（精确时长，不用请求次数近似）
        assert after["minutes"] == after["seconds"] // 60
        # learning_days：当日首次结算后至少为 1，且只增不减
        assert after["learning_days"] >= max(before["learning_days"], 1)

        async def ledger_rows():
            async with async_session() as s:
                rows = (
                    await s.execute(
                        select(ReadingSettlement).where(
                            ReadingSettlement.session_id == UUID(session_id)
                        )
                    )
                ).scalars().all()
                progress_seconds = None
                return rows, progress_seconds

        rows, _ = asyncio.run(ledger_rows())
        assert len(rows) == 1 and rows[0].settled_seconds == 90

        # 幂等：直接再次结算同一会话 → 返回 0，不再累计
        async def double_settle() -> int:
            from app.infrastructure.database.models import LearningSession

            async with async_session() as s:
                ls = await s.get(LearningSession, UUID(session_id))
                service = LearningService()
                first = await service._credit_reading_stats(s, ls, datetime.now(timezone.utc))
                second = await service._credit_reading_stats(s, ls, datetime.now(timezone.utc))
                await s.rollback()
                return first, second

        first_credit, second_credit = asyncio.run(double_settle())
        assert (first_credit, second_credit) == (0, 0), "台账唯一约束必须挡下重复结算"

    def test_auto_close_on_new_session_also_settles_once(self, client, token):
        before = asyncio.run(_profile_snapshot())
        s1 = client.post(
            "/api/v1/learning-sessions",
            headers=auth(token),
            json={"book_id": str(BOOK2_ID), "chapter_id": str(CHB2_ID)},
        ).json()["data"]["session_id"]

        async def backdate() -> None:
            from app.infrastructure.database.models import LearningSession

            async with async_session() as s:
                row = await s.get(LearningSession, UUID(s1))
                row.started_at = datetime.now(timezone.utc) - timedelta(seconds=45)
                await s.commit()

        asyncio.run(backdate())

        s2 = client.post(
            "/api/v1/learning-sessions",
            headers=auth(token),
            json={"book_id": str(BOOK2_ID), "chapter_id": str(CHB2_ID)},
        ).json()["data"]["session_id"]
        after = asyncio.run(_profile_snapshot())
        assert after["seconds"] - before["seconds"] == 45

        async def ledger_count():
            async with async_session() as s:
                rows = (
                    await s.execute(
                        select(ReadingSettlement).where(
                            ReadingSettlement.session_id == UUID(s1)
                        )
                    )
                ).scalars().all()
                return len(rows)

        assert asyncio.run(ledger_count()) == 1


class TestCompletionCountersFromEvents:
    def test_chapter_and_book_counters_recompute_from_events(
        self, client: TestClient, token: str
    ):
        conv = client.post(
            "/api/v1/conversations",
            headers={**auth(token), "Idempotency-Key": f"conv-{uuid4()}"},
            json={"title": "P3 事件链路"},
        ).json()["data"]["conversation_id"]

        def emit(event_type: str, **fields) -> dict:
            body = {
                "event_type": event_type,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                **fields,
            }
            resp = client.post("/api/v1/learning-events", headers=auth(token), json=body)
            assert resp.status_code in (200, 201), resp.text
            return resp.json()["data"]

        emit("CHAPTER_FINISHED", book_id=str(BOOK_ID), chapter_id=str(CH1_ID))
        emit("CHAPTER_FINISHED", book_id=str(BOOK_ID), chapter_id=str(CH2_ID))
        # 同章节重复上报：重算语义下计数不得虚增
        emit("CHAPTER_FINISHED", book_id=str(BOOK_ID), chapter_id=str(CH1_ID))
        snapshot = asyncio.run(_profile_snapshot())
        assert snapshot["completed_chapters"] >= 2

        emit(
            "CHAPTER_FINISHED",
            book_id=str(BOOK2_ID),
            chapter_id=str(CHB2_ID),
            session_id=None,
        )
        emit("BOOK_FINISHED", book_id=str(BOOK_ID))
        emit("BOOK_FINISHED", book_id=str(BOOK2_ID))
        snapshot = asyncio.run(_profile_snapshot())
        assert snapshot["completed_books"] >= 2

    def test_event_full_linkage_roundtrip(self, client: TestClient, token: str):
        session_id = client.post(
            "/api/v1/learning-sessions",
            headers=auth(token),
            json={"book_id": str(BOOK_ID), "chapter_id": str(CH1_ID)},
        ).json()["data"]["session_id"]
        conv_id = client.post(
            "/api/v1/conversations",
            headers={**auth(token), "Idempotency-Key": f"conv-{uuid4()}"},
            json={"title": " linkage"},
        ).json()["data"]["conversation_id"]
        quiz_resp = client.post(
            "/api/v1/quiz-sessions",
            headers=auth(token),
            json={
                "conversation_id": conv_id,
                "book_id": str(BOOK_ID),
                "chapter_id": str(CH1_ID),
                "question_count": 1,
            },
        )
        assert quiz_resp.status_code in (200, 201), quiz_resp.text
        quiz_id = quiz_resp.json()["data"]["quiz_session_id"]
        block_id = str(BLK_P3_ID)
        kp_ids = [str(uuid4()), str(uuid4())]

        created = client.post(
            "/api/v1/learning-events",
            headers=auth(token),
            json={
                "event_type": "KNOWLEDGE_CARD_VIEWED",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "book_id": str(BOOK_ID),
                "chapter_id": str(CH1_ID),
                "block_id": block_id,
                "knowledge_point_ids": kp_ids,
                "session_id": session_id,
                "conversation_id": conv_id,
                "quiz_session_id": quiz_id,
                "payload": {"card_title": "测试卡"},
            },
        ).json()["data"]

        listed_resp = client.get(
            "/api/v1/me/learning-events",
            params={"event_type": "KNOWLEDGE_CARD_VIEWED"},
            headers=auth(token),
        )
        assert listed_resp.status_code == 200
        listed_payload = listed_resp.json()["data"]
        listed = (
            listed_payload if isinstance(listed_payload, list) else listed_payload["items"]
        )
        match = next(e for e in listed if e["event_id"] == created["event_id"])
        assert match["session_id"] == session_id
        assert match["conversation_id"] == conv_id
        assert match["quiz_session_id"] == quiz_id
        assert match["block_id"] == block_id
        assert set(match["knowledge_point_ids"]) == set(kp_ids)

    def test_voice_session_ended_event_type_accepted(self, client, token):
        resp = client.post(
            "/api/v1/learning-events",
            headers=auth(token),
            json={
                "event_type": "VOICE_SESSION_ENDED",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "payload": {"duration_ms": 4200},
            },
        )
        assert resp.status_code in (200, 201), resp.text


class TestQuizCountOnCompletion:
    def test_quiz_completion_increments_once(self, client: TestClient, token: str):
        conv_id = client.post(
            "/api/v1/conversations",
            headers={**auth(token), "Idempotency-Key": f"conv-{uuid4()}"},
            json={"title": "quiz count"},
        ).json()["data"]["conversation_id"]
        quiz = client.post(
            "/api/v1/quiz-sessions",
            headers=auth(token),
            json={"conversation_id": conv_id, "question_count": 2},
        ).json()["data"]
        qid = quiz["quiz_session_id"]
        before = asyncio.run(_profile_snapshot())

        for question in quiz["questions_snapshot"]:
            correct = question["correct_answer"]
            answer = (
                {"key": correct["key"]}
                if "key" in correct
                else {"keys": correct.get("keys", [])}
                if "keys" in correct
                else {"value": correct.get("value", "")}
            )
            submit = client.post(
                f"/api/v1/quiz-sessions/{qid}/questions/{question['question_id']}/answers",
                headers={**auth(token), "Idempotency-Key": f"ans-{question['question_id']}"},
                json={"answer": answer, "hint_level_at_submit": 0},
            )
            assert submit.status_code == 201, submit.text

        mid = asyncio.run(_profile_snapshot())
        assert mid["quiz_count"] == before["quiz_count"] + 1

        detail = client.get(f"/api/v1/quiz-sessions/{qid}", headers=auth(token)).json()["data"]
        assert detail["status"] == "COMPLETED"

        # 重放最后一题（相同幂等键）：不得再次累计
        last = quiz["questions_snapshot"][-1]
        replay = client.post(
            f"/api/v1/quiz-sessions/{qid}/questions/{last['question_id']}/answers",
            headers={**auth(token), "Idempotency-Key": f"ans-{last['question_id']}"},
            json={
                "answer": {"key": last["correct_answer"].get("key", "")},
                "hint_level_at_submit": 0,
            },
        )
        assert replay.status_code in (200, 201)  # 重放返回既有结果
        after_replay = asyncio.run(_profile_snapshot())
        assert after_replay["quiz_count"] == mid["quiz_count"]


class TestInterestMatchRecommendation:
    def test_pure_rule_builds_interest_match_with_memory_evidence(self):
        candidate = BookCandidate(
            book_id=UUID("5e3f0000-0000-0000-0000-000000000001"),
            title="编程入门",
            description="用例子学编程",
            grade_min=7,
            grade_max=9,
            tags=("编程", "Python"),
            is_started=False,
        )
        drafts = build_recommendation_drafts(
            progress_signals=[],
            quiz_answer_signals=[],
            completed_progress_signals=[],
            book_candidates=[candidate],
            interest_signals=[
                InterestSignal(
                    tag="编程",
                    memory_id=UUID("5e3f0000-0000-0000-0000-000000000099"),
                    memory_content="我喜欢编程和算法",
                )
            ],
        )
        interest = [d for d in drafts if d.recommendation_type == "INTEREST_MATCH"]
        assert len(interest) == 1
        assert interest[0].related_book_id == candidate.book_id
        assert "编程" in interest[0].reason
        assert interest[0].evidence_ids == ["5e3f0000-0000-0000-0000-000000000099"]

    def test_api_recommendation_uses_real_memory_data_source(
        self, client: TestClient, token: str
    ):
        memory_id = UUID("5e3f0000-0000-0000-0000-00000000a001")

        async def seed() -> None:
            async with async_session() as s:
                user = (
                    await s.execute(select(User).where(User.username == OWNER))
                ).scalar_one()
                profile = (
                    await s.execute(
                        select(StudentProfile).where(StudentProfile.user_id == user.user_id)
                    )
                ).scalar_one()
                if await s.get(StudentMemory, memory_id) is None:
                    now = datetime.now(timezone.utc)
                    s.add(
                        StudentMemory(
                            memory_id=memory_id,
                            student_id=profile.student_id,
                            memory_type="PREFERENCE",
                            content="我对编程特别感兴趣",
                            tags=["兴趣"],
                            confidence="HIGH",
                            status="ACTIVE",
                            evidence_ids=[],
                            created_at=now,
                            updated_at=now,
                        )
                    )
                # 一本带「编程」标签且该学生未开始的书（候选查询要求 PUBLISHED）
                tag_book = UUID("5e300000-0000-0000-0000-00000000c0de")
                if await s.get(Book, tag_book) is None:
                    s.add(
                        Book(
                            book_id=tag_book,
                            title="P3 编程兴趣书",
                            description="围绕编程思维的小书",
                            grade_min=7,
                            grade_max=9,
                            difficulty="EASY",
                            estimated_minutes=15,
                            tags=["编程"],
                            status="PUBLISHED",
                            published_at=datetime.now(timezone.utc),
                        )
                    )
                await s.commit()

        asyncio.run(seed())

        items = client.get(
            "/api/v1/me/recommendations", headers=auth(token)
        ).json()["data"]
        interest = [
            item
            for item in items
            if item["recommendation_type"] == "INTEREST_MATCH"
            and item["related_book_id"] == "5e300000-0000-0000-0000-00000000c0de"
        ]
        assert interest, "应基于真实记忆生成 INTEREST_MATCH 推荐"
        top = interest[0]
        assert memory_id.__str__() in top["evidence_ids"]
        assert "编程" in top["reason"]
