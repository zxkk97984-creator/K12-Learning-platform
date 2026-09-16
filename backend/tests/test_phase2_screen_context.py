"""Phase 2 验收测试：ScreenContext 全链路、当前章节 Quiz、TeacherContext。

覆盖 plan.md Phase 2 验收标准：
- screen_context 持久化到 conversation.current_page_context，且新快照整体
  替换旧上下文（离开 Reader 后不再携带旧章节的服务端语义）；
- quiz intent 从页面上下文取 book/chapter；mock 模式下题目由本章真实内容
  确定性生成（非训练数据题库）、多题型、可判分、来源可追溯；
- 无效章节时显式报错（tool.result error），不静默给无关题；
- 多题完成流程与 result_summary；
- TeacherContext 包含档案/偏好/记忆/画像/最近学习/最近测验/当前章节。
"""

import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.infrastructure.database.models import (
    Book,
    Chapter,
    ContentBlock,
    Conversation,
    KnowledgePoint,
    LearningEvent,
    ProfileInsight,
    QuizSession,
    StudentPreference,
    StudentProfile,
    User,
)
from app.infrastructure.database.session import async_session
from app.main import app
from app.modules.conversation.teacher_context import (
    build_teacher_context,
    teacher_usage_note,
)
from app.modules.identity.security import hash_password

OWNER = "test_p2_ctx_user"
PASSWORD = "p2-context-pass"

BOOK_ID = UUID("5e200000-0000-0000-0000-000000000001")
CH1_ID = UUID("5e210000-0000-0000-0000-000000000001")
CH2_ID = UUID("5e220000-0000-0000-0000-000000000001")
KP_OWN_1 = UUID("5e230000-0000-0000-0000-000000000001")
KP_OWN_2 = UUID("5e230000-0000-0000-0000-000000000002")
KP_FOREIGN_1 = UUID("5e230000-0000-0000-0000-000000000003")
KP_FOREIGN_2 = UUID("5e230000-0000-0000-0000-000000000004")
KP_FOREIGN_3 = UUID("5e230000-0000-0000-0000-000000000005")

OWN_TEXT_1 = "机器学习通过大量例子发现可重复的规律。"
OWN_TEXT_2 = "标签是我们希望机器学会的答案。"
BLK1_ID = UUID("5e240000-0000-0000-0000-000000000001")
BLK2_ID = UUID("5e240000-0000-0000-0000-000000000002")


def _ensure_env() -> None:
    async def run() -> None:
        async with async_session() as session:
            user = (
                await session.execute(select(User).where(User.username == OWNER))
            ).scalar_one_or_none()
            if user is None:
                user = User(
                    username=OWNER,
                    password_hash=hash_password(PASSWORD),
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
                        nickname="Phase2 测试",
                        grade=7,
                        language="zh-CN",
                    )
                )

            if await session.get(Book, BOOK_ID) is None:
                # PUBLISHED：测验关联测试需要可从学生路径出题（T03 可见性守卫）。
                session.add(
                    Book(
                        book_id=BOOK_ID,
                        title="Phase2 测试书",
                        description="仅用于测验关联测试",
                        grade_min=7,
                        grade_max=9,
                        difficulty="MEDIUM",
                        estimated_minutes=30,
                        tags=["测试"],
                        status="PUBLISHED",
                        published_at=datetime.now(timezone.utc),
                    )
                )
            else:
                # 库中可能残留历史 DRAFT 状态，强制恢复为 PUBLISHED 以满足出题可见性。
                book = await session.get(Book, BOOK_ID)
                book.status = "PUBLISHED"
                book.published_at = book.published_at or datetime.now(timezone.utc)
            for chapter_id, order, title in [
                (CH1_ID, 1, "规律是怎么发现的"),
                (CH2_ID, 2, "另一章"),
            ]:
                if await session.get(Chapter, chapter_id) is None:
                    session.add(
                        Chapter(
                            chapter_id=chapter_id,
                            book_id=BOOK_ID,
                            title=title,
                            chapter_order=order,
                            estimated_minutes=10,
                            status="PUBLISHED",
                        )
                    )
            kps = {
                "ml-p2": ("机器学习", "通过例子发现规律的方法"),
                "label-p2": ("标签", "希望机器学会的答案"),
                "pixel-p2": ("像素", "图像的最小单位"),
                "variable-p2": ("变量", "存放数据的容器"),
                "loop-p2": ("循环", "重复执行的结构"),
            }
            # 按 slug 幂等：共享开发库中可能残留旧命名空间行，复用其主键。
            kp_ids: dict[str, UUID] = {}
            for slug, (name, description) in kps.items():
                row = (
                    await session.execute(
                        select(KnowledgePoint).where(KnowledgePoint.slug == slug)
                    )
                ).scalar_one_or_none()
                if row is None:
                    row = KnowledgePoint(
                        knowledge_point_id=UUID(f"5e230000-0000-0000-0000-{abs(hash(slug)) % 10**12:012d}"),
                        name=name,
                        slug=slug,
                        description=description,
                        topic="AI 基础",
                    )
                    session.add(row)
                kp_ids[slug] = row.knowledge_point_id

            blocks_spec = [
                (
                    BLK1_ID,
                    CH1_ID,
                    1,
                    {"text": OWN_TEXT_1},
                    [str(kp_ids["ml-p2"])],
                    "第一节",
                ),
                (
                    BLK2_ID,
                    CH1_ID,
                    2,
                    {"text": OWN_TEXT_2},
                    [str(kp_ids["label-p2"])],
                    "第二节",
                ),
                (
                    UUID("5e240000-0000-0000-0000-000000000003"),
                    CH2_ID,
                    1,
                    {"text": "这一段属于其他章节，讲的是完全不同的内容。"},
                    [],
                    "外章",
                ),
            ]
            for block_id, ch_id, block_order, content, ids, section in blocks_spec:
                if await session.get(ContentBlock, block_id) is None:
                    session.add(
                        ContentBlock(
                            block_id=block_id,
                            chapter_id=ch_id,
                            block_type="PARAGRAPH",
                            content=content,
                            block_order=block_order,
                            section_key=section,
                            knowledge_point_ids=ids,
                        )
                    )
            await session.commit()

    asyncio.run(run())


@pytest.fixture(scope="module")
def client() -> TestClient:
    _ensure_env()
    return TestClient(app)


@pytest.fixture(scope="module")
def token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": OWNER, "password": PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "text/event-stream"}


def create_conversation(client: TestClient, token: str) -> str:
    response = client.post(
        "/api/v1/conversations",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": f"conv-{uuid4()}"},
        json={"title": "Phase2 上下文会话"},
    )
    assert response.status_code == 201
    return response.json()["data"]["conversation_id"]


def parse_sse(raw: str) -> list[dict]:
    events: list[dict] = []
    for frame in raw.split("\n\n"):
        if not frame.strip() or frame.lstrip().startswith(":"):
            continue
        event_name = None
        data_lines: list[str] = []
        for line in frame.splitlines():
            if line.startswith("event: "):
                event_name = line[7:]
            elif line.startswith("data: "):
                data_lines.append(line[6:])
        if event_name is not None and data_lines:
            events.append({"event": event_name, "data": json.loads("\n".join(data_lines))})
    return events


READER_CONTEXT = {
    "route": f"/learn/{BOOK_ID}/{CH1_ID}",
    "pageType": "chapter_reader",
    "bookId": str(BOOK_ID),
    "chapterId": str(CH1_ID),
    "chapterTitle": "规律是怎么发现的",
    "visibleSection": "第一节",
}


class TestScreenContextPersistence:
    def test_screen_context_is_persisted_and_replaced_by_new_snapshot(
        self, client: TestClient, token: str
    ):
        conversation_id = create_conversation(client, token)

        first = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=headers(token),
            json={"content": "解释一下这一节", "screen_context": READER_CONTEXT},
        )
        assert first.status_code == 200
        parse_sse(first.text)

        detail = client.get(
            f"/api/v1/conversations/{conversation_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        context = detail.json()["data"]["current_page_context"]
        assert context["bookId"] == str(BOOK_ID)
        assert context["chapterId"] == str(CH1_ID)
        assert context["chapterTitle"] == "规律是怎么发现的"

        # 模拟离开 Reader 到首页：前端发送干净的新快照 → 服务端必须整体替换
        second = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=headers(token),
            json={
                "content": "今天学什么？",
                "screen_context": {"route": "/home", "pageType": "home"},
            },
        )
        assert second.status_code == 200
        parse_sse(second.text)

        detail = client.get(
            f"/api/v1/conversations/{conversation_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        context = detail.json()["data"]["current_page_context"]
        assert "bookId" not in context
        assert "chapterId" not in context
        assert "chapterTitle" not in context
        assert context["pageType"] == "home"


class TestChapterQuizIntent:
    def test_quiz_intent_creates_chapter_related_multi_type_quiz(
        self, client: TestClient, token: str
    ):
        conversation_id = create_conversation(client, token)
        response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=headers(token),
            json={"content": "给我出题", "screen_context": READER_CONTEXT},
        )
        assert response.status_code == 200
        events = parse_sse(response.text)

        tool_result = next(e for e in events if e["event"] == "tool.result")
        assert tool_result["data"]["status"] == "success"
        quiz_session_id = tool_result["data"]["payload"]["quiz_session_id"]

        done = next(e for e in events if e["event"] == "message.done")
        assert done["data"]["metadata"]["quiz_session_id"] == quiz_session_id

        detail = client.get(
            f"/api/v1/quiz-sessions/{quiz_session_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert detail.status_code == 200
        session_data = detail.json()["data"]
        assert session_data["book_id"] == str(BOOK_ID)
        assert session_data["chapter_id"] == str(CH1_ID)
        assert session_data["quiz_kind"] == "CHAPTER_QUIZ"
        snapshot = session_data["questions_snapshot"]
        assert len(snapshot) == 3

        types = {item["question_type"] for item in snapshot}
        assert types <= {"SINGLE_CHOICE", "MULTIPLE_CHOICE", "TRUE_FALSE", "FILL_BLANK"}
        assert len(types) >= 2, "题目应覆盖多种题型"

        stems = " ".join(item["stem"] for item in snapshot)
        assert "训练数据最重要的作用" not in stems, "不得回退到与章节无关的旧题库"
        related = (
            "规律是怎么发现的" in stems
            or "机器学习" in stems
            or "标签" in stems
            or any("本章" in stem for stem in stems.split())
        )
        assert related, "题干应与当前章节内容相关"

        for item in snapshot:
            source = item["source_context"]
            assert source["generation"] == "chapter_deterministic"
            assert source["chapter_id"] == str(CH1_ID)
            assert "bank_id" not in source

        questions_response = client.get(
            f"/api/v1/quiz-sessions/{quiz_session_id}/questions",
            headers={"Authorization": f"Bearer {token}"},
        )
        questions = questions_response.json()["data"]
        by_id = {q["question_id"]: q for q in questions}
        correct_total = 0
        for item in snapshot:
            question = by_id[item["question_id"]]
            answer = self._correct_answer_payload(item)
            submit = client.post(
                f"/api/v1/quiz-sessions/{quiz_session_id}"
                f"/questions/{item['question_id']}/answers",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": f"ans-{item['question_id']}",
                },
                json={"answer": answer, "hint_level_at_submit": 0},
            )
            assert submit.status_code == 201, submit.text
            assert submit.json()["data"]["is_correct"] is True
            correct_total += 1
        assert correct_total == 3

        final_detail = client.get(
            f"/api/v1/quiz-sessions/{quiz_session_id}",
            headers={"Authorization": f"Bearer {token}"},
        ).json()["data"]
        assert final_detail["status"] == "COMPLETED"
        assert final_detail["result_summary"]["correct"] == 3

    @staticmethod
    def _correct_answer_payload(snapshot_item: dict) -> dict:
        correct = snapshot_item["correct_answer"]
        qtype = snapshot_item["question_type"]
        if qtype == "SINGLE_CHOICE":
            return {"key": correct["key"]}
        if qtype == "TRUE_FALSE":
            return {"key": correct["key"]}
        if qtype == "MULTIPLE_CHOICE":
            return {"keys": list(correct["keys"])}
        return {"value": correct["value"]}

    def test_invalid_chapter_yields_explicit_error_not_silent_quiz(
        self, client: TestClient, token: str
    ):
        conversation_id = create_conversation(client, token)
        bogus_context = dict(READER_CONTEXT)
        bogus_context["chapterId"] = str(uuid4())
        bogus_context["bookId"] = str(BOOK_ID)

        response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=headers(token),
            json={"content": "给我出题", "screen_context": bogus_context},
        )
        assert response.status_code == 200
        events = parse_sse(response.text)
        tool_result = next(e for e in events if e["event"] == "tool.result")
        assert tool_result["data"]["status"] == "error"
        assert tool_result["data"]["payload"]["code"] == "CHAPTER_NOT_FOUND"


class TestVoiceScreenContext:
    def test_voice_context_frame_is_merged_into_conversation(
        self, client: TestClient, token: str
    ):
        conversation_id = create_conversation(client, token)
        audio = base64_audio()

        with client.websocket_connect(
            f"/api/v1/voice/ws?conversation_id={conversation_id}&token={token}"
        ) as websocket:
            json.loads(websocket.receive_text())  # initial state

            websocket.send_text(
                json.dumps({"type": "context", "screen_context": READER_CONTEXT})
            )
            echo = json.loads(websocket.receive_text())
            assert echo["type"] == "state"

            websocket.send_text(json.dumps({"type": "audio_chunk", "data": audio}))
            listening = json.loads(websocket.receive_text())
            assert listening == {"type": "state", "state": "LISTENING"}

            websocket.send_text(json.dumps({"type": "audio_end"}))
            # THINKING / partial / final / reply / SPEAKING / audio / IDLE
            frames = [json.loads(websocket.receive_text()) for _ in range(7)]
            reply_frames = [f for f in frames if f.get("type") == "reply"]
            assert reply_frames, "语音链路应返回文字回复"

        async def read_context() -> dict:
            async with async_session() as session:
                conversation = await session.get(Conversation, UUID(conversation_id))
                return dict(conversation.current_page_context or {})

        context = asyncio.run(read_context())
        assert context["bookId"] == str(BOOK_ID)
        assert context["chapterId"] == str(CH1_ID)


def base64_audio() -> str:
    import base64

    return base64.b64encode(b"\x00\x00" * 160).decode("ascii")


class TestTeacherContextBuilder:
    def test_builds_all_sections_from_real_db(self, client: TestClient, token: str):
        async def seed_and_build() -> tuple[str, str]:
            # 使用独立学生：避免共享开发库中其他模块（如异步记忆管线）
            # 对同一学生的画像进行 SUPERSEDED 重建造成交叉干扰。
            async with async_session() as session:
                user = User(
                    username=f"p2-tc-{uuid4().hex[:8]}",
                    password_hash=hash_password(PASSWORD),
                    user_type="STUDENT",
                )
                session.add(user)
                await session.flush()
                profile = StudentProfile(
                    user_id=user.user_id,
                    nickname="TeacherContext 专属",
                    grade=7,
                    language="zh-CN",
                    learning_goal=None,
                )
                session.add(profile)
                await session.flush()
                student_id = profile.student_id

                preference = StudentPreference(
                    student_id=student_id,
                    preferred_explanation_style="EXAMPLE_BASED",
                    preferred_difficulty="MEDIUM",
                    preferred_session_length="SHORT",
                )
                existing_preference = (
                    await session.execute(
                        select(StudentPreference).where(
                            StudentPreference.student_id == student_id
                        )
                    )
                ).scalar_one_or_none()
                if existing_preference is None:
                    session.add(preference)

                from app.infrastructure.database.models import Conversation, StudentMemory
                session.add(
                    StudentMemory(
                        memory_id=uuid4(),
                        student_id=student_id,
                        memory_type="LEARNING",
                        content="喜欢通过具体例子理解抽象概念",
                        tags=[],
                        confidence="HIGH",
                        status="ACTIVE",
                        evidence_ids=[],
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                session.add(
                    ProfileInsight(
                        insight_id=uuid4(),
                        student_id=student_id,
                        insight_type="STRENGTH",
                        dimension="概念理解",
                        level="较强",
                        description="能快速把新概念和已学内容联系起来",
                        evidence_ids=[],
                        status="ACTIVE",
                        valid_from=datetime.now(timezone.utc),
                        rule_version="rule-v1",
                    )
                )
                now = datetime.now(timezone.utc)
                session.add(
                    LearningEvent(
                        event_id=uuid4(),
                        student_id=student_id,
                        event_type="SECTION_READ",
                        occurred_at=now,
                        book_id=BOOK_ID,
                        chapter_id=CH1_ID,
                        payload={"section_key": "第一节"},
                        created_at=now,
                    )
                )
                conversation_row = Conversation(
                    conversation_id=uuid4(),
                    student_id=student_id,
                    title="TeacherContext 测试会话",
                    channel="TEXT",
                    status="ACTIVE",
                    current_page_context={},
                    recent_messages=[],
                )
                session.add(conversation_row)
                quiz_session_row = QuizSession(
                    quiz_session_id=uuid4(),
                    student_id=student_id,
                    conversation_id=conversation_row.conversation_id,
                    book_id=BOOK_ID,
                    chapter_id=CH1_ID,
                    title="规律是怎么发现的 · 随堂测验",
                    quiz_kind="CHAPTER_QUIZ",
                    status="COMPLETED",
                    questions_snapshot=[],
                    result_summary={"correct": 2, "total": 2, "hints_used": 0},
                    duration_seconds=60,
                    ai_feedback=None,
                    model_info={},
                    skill_version="quiz-v2",
                    created_at=now,
                    updated_at=now,
                )
                session.add(quiz_session_row)
                await session.flush()
                from app.infrastructure.database.models import QuizAnswer, QuizQuestion

                for offset in range(2):
                    seeded_qid = uuid4()
                    question_row = QuizQuestion(
                        question_id=seeded_qid,
                        quiz_session_id=quiz_session_row.quiz_session_id,
                        question_order=offset + 1,
                        question_type="SINGLE_CHOICE",
                        stem=f"种子题 {offset + 1}",
                        options=[
                            {"key": "A", "text": "对"},
                            {"key": "B", "text": "错"},
                        ],
                        correct_answer={"key": "A"},
                        explanation="种子解析",
                        source_context={},
                        interaction_policy={
                            "allow_hint": True,
                            "max_hint_level": 3,
                        },
                        knowledge_point_ids=[],
                        created_at=now,
                    )
                    session.add(question_row)
                    await session.flush()
                    session.add(
                        QuizAnswer(
                            answer_id=uuid4(),
                            quiz_session_id=quiz_session_row.quiz_session_id,
                            question_id=seeded_qid,
                            student_id=student_id,
                            submitted_answer={"key": "A"},
                            is_correct=True,
                            attempt_no=1,
                            hint_level_at_submit=0,
                            is_final=True,
                            submitted_at=now,
                            created_at=now,
                        )
                    )
                await session.commit()

                profile.learning_goal = "期末 AI 成绩提升"

                async def build(context: dict) -> str:
                    return await build_teacher_context(
                        session,
                        student_id=student_id,
                        grade=profile.grade,
                        language=profile.language,
                        learning_goal=profile.learning_goal,
                        current_context=context,
                    )

                default_block = await build(
                    {"chapterId": str(CH1_ID), "visibleSection": "第一节"}
                )
                focused_block = await build(
                    {
                        "chapterId": str(CH1_ID),
                        "contentBlockId": str(BLK2_ID),
                    }
                )
                return default_block, focused_block

        block, focused = asyncio.run(seed_and_build())

        assert "【学生档案】" in block
        assert "年级：7" in block
        assert "学习目标：期末 AI 成绩提升" in block
        assert "【学习偏好】" in block
        assert "讲解方式：例子驱动" in block
        assert "难度偏好：中等" in block
        assert "【长期记忆·系统观察，学生可能质疑】" in block
        assert "喜欢通过具体例子理解抽象概念" in block
        assert "【画像洞察·基于证据的定性判断】" in block
        assert "能快速把新概念和已学内容联系起来" in block
        assert "优势·较强" in block
        assert "【最近学习事件】" in block
        assert "SECTION_READ" in block
        assert "【最近测验】" in block
        assert "规律是怎么发现的 · 随堂测验" in block
        assert "最终正确 2/2" in block
        assert "【当前阅读位置】" in block
        assert "规律是怎么发现的" in block
        assert "可见小节：第一节" in block
        # 缺口 2：无 contentBlockId 时回退取本章真实文本块
        assert "当前正文节选：" in block
        assert OWN_TEXT_1 in block
        # 指定 contentBlockId 时优先展示该块正文，而非第一章其他块
        assert OWN_TEXT_2 in focused
        assert OWN_TEXT_1 not in focused.split("当前正文节选：")[1].split("\n\n")[0]
        assert teacher_usage_note() .startswith("【上下文使用约束】")
        assert "不是学生确认过的事实" in teacher_usage_note()

    def test_missing_data_renders_explicit_placeholder(self, client: TestClient):
        async def build_empty() -> str:
            async with async_session() as session:
                user = User(
                    username=f"p2-empty-{uuid4().hex[:8]}",
                    password_hash=hash_password(PASSWORD),
                    user_type="STUDENT",
                )
                session.add(user)
                await session.flush()
                from app.infrastructure.database.models import StudentProfile

                profile = StudentProfile(
                    user_id=user.user_id, nickname="空数据", grade=5, language="zh-CN"
                )
                session.add(profile)
                await session.flush()
                block = await build_teacher_context(
                    session,
                    student_id=profile.student_id,
                    grade=profile.grade,
                    language=profile.language,
                    learning_goal=None,
                    current_context={},
                )
                await session.rollback()
                return block

        block = asyncio.run(build_empty())
        assert "年级：5" in block
        assert "学习目标：暂无" in block
        assert "【长期记忆·系统观察，学生可能质疑】\n- 暂无" in block
        assert "【画像洞察·基于证据的定性判断】\n- 暂无" in block
        assert "【最近学习事件】\n- 暂无" in block
        assert "【最近测验】\n- 暂无" in block


class TestLLMQuestionCountPolicy:
    """缺口 3：LLM 合法题数不足必须整体弃用并回退，不得截断接受。"""

    @staticmethod
    def _valid_question(order: int) -> dict:
        return {
            "question_type": "SINGLE_CHOICE",
            "stem": f"LLM 题 {order}",
            "options": [
                {"key": "A", "text": "甲"},
                {"key": "B", "text": "乙"},
            ],
            "correct_answer": {"key": "A"},
            "explanation": "解析",
            "knowledge_point_ids": [],
        }

    @staticmethod
    async def _make_student_and_conversation(session):
        user = (
            await session.execute(select(User).where(User.username == OWNER))
        ).scalar_one()
        profile = (
            await session.execute(
                select(StudentProfile).where(StudentProfile.user_id == user.user_id)
            )
        ).scalar_one()
        from app.infrastructure.database.models import Conversation

        conv_row = Conversation(
            student_id=profile.student_id,
            title="LLM 题数策略测试",
            channel="TEXT",
            status="ACTIVE",
            current_page_context={},
            recent_messages=[],
        )
        session.add(conv_row)
        await session.flush()
        return profile, conv_row

    class _ScriptedProvider:
        def __init__(self, items: list[dict]) -> None:
            self._items = items
            self.model_info = {"provider": "scripted", "model": "scripted-1"}

        async def stream_chat(self, _history, _system_prompt):
            yield json.dumps(self._items, ensure_ascii=False)

    def test_insufficient_llm_questions_fall_back_to_chapter_generation(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        import app.modules.quiz.skill as skill_module
        from app.config import settings
        from app.modules.quiz.skill import QuizGenerationContext, QuizSkill

        async def run() -> tuple[int, str, int]:
            async with async_session() as session:
                profile, conversation_row = await self._make_student_and_conversation(
                    session
                )

                # LLM 只返回 1 道合法题，请求 3 道 → 输出不可用
                provider = self._ScriptedProvider([self._valid_question(1)])
                monkeypatch.setattr(skill_module, "get_ai_provider", lambda: provider)
                monkeypatch.setattr(settings, "ai_provider", "openai_compatible")

                skill = QuizSkill()
                llm_result = await skill._try_llm_generate(
                    QuizGenerationContext(
                        student_id=profile.student_id,
                        conversation_id=conversation_row.conversation_id,
                        book_id=BOOK_ID,
                        chapter_id=CH1_ID,
                        question_count=3,
                    ),
                    chapter_source=await __import__(
                        "app.modules.quiz.chapter_source", fromlist=["load_chapter_source"]
                    ).load_chapter_source(session, BOOK_ID, CH1_ID),
                )
                assert llm_result is None, "不足额的 LLM 输出必须视为不可用"

                context = QuizGenerationContext(
                    student_id=profile.student_id,
                    conversation_id=conversation_row.conversation_id,
                    book_id=BOOK_ID,
                    chapter_id=CH1_ID,
                    question_count=3,
                    allow_bank_fallback=False,
                )
                rows = await skill.generate(session, context)
                generated = context.generated_session
                assert generated is not None
                return len(rows), generated.model_info["provider"], 0

        row_count, provider_name, _ = asyncio.run(run())
        assert row_count == 3
        assert provider_name == "quiz-skill", "应回退到章节确定性生成"

    def test_sufficient_llm_questions_are_accepted(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        import app.modules.quiz.skill as skill_module
        from app.config import settings
        from app.modules.quiz.skill import QuizGenerationContext, QuizSkill

        async def run() -> tuple[int, str]:
            async with async_session() as session:
                profile, conversation_row = await self._make_student_and_conversation(
                    session
                )

                provider = self._ScriptedProvider(
                    [self._valid_question(i) for i in range(1, 4)]
                )
                monkeypatch.setattr(skill_module, "get_ai_provider", lambda: provider)
                monkeypatch.setattr(settings, "ai_provider", "openai_compatible")

                context = QuizGenerationContext(
                    student_id=profile.student_id,
                    conversation_id=conversation_row.conversation_id,
                    question_count=3,
                    allow_bank_fallback=False,
                )
                rows = await QuizSkill().generate(session, context)
                generated = context.generated_session
                assert generated is not None
                assert all(
                    row.stem.startswith("LLM 题") for row in rows
                ), "足额合法题必须被完整接受"
                return len(rows), generated.model_info["provider"]

        row_count, provider_name = asyncio.run(run())
        assert row_count == 3
        assert provider_name == "openai_compatible"
