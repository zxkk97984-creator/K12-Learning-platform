"""Phase 5 Quiz Domain API tests (real PostgreSQL + TestClient)."""

import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.infrastructure.database.models import (
    Book,
    Chapter,
    StudentProfile,
    User,
)
from app.infrastructure.database.session import async_session
from app.main import app
from app.modules.identity.security import hash_password


OWNER_NAME = "test_quiz_user"
OWNER_PASSWORD = "quizpass"
OTHER_NAME = "other_quiz_user"
OTHER_PASSWORD = "otherquizpass"
BOOK_ID = UUID("b5000000-0000-0000-0000-000000000001")
CHAPTER_ID = UUID("c5000000-0000-0000-0000-000000000001")


def _ensure_content() -> None:
    async def run() -> None:
        async with async_session() as session:
            book = await session.get(Book, BOOK_ID)
            if book is None:
                session.add(
                    Book(
                        book_id=BOOK_ID,
                        title="测验测试书",
                        grade_min=7,
                        grade_max=9,
                        difficulty="MEDIUM",
                        estimated_minutes=60,
                        status="PUBLISHED",
                        published_at=datetime.now(timezone.utc),
                    )
                )
            chapter = await session.get(Chapter, CHAPTER_ID)
            if chapter is None:
                session.add(
                    Chapter(
                        chapter_id=CHAPTER_ID,
                        book_id=BOOK_ID,
                        title="训练数据测验章",
                        chapter_order=1,
                        estimated_minutes=15,
                        status="PUBLISHED",
                    )
                )
            await session.commit()

    asyncio.run(run())


def _ensure_user(username: str, password: str, nickname: str) -> None:
    async def run() -> None:
        async with async_session() as session:
            user = (
                await session.execute(select(User).where(User.username == username))
            ).scalar_one_or_none()
            if user is None:
                user = User(
                    username=username,
                    password_hash=hash_password(password),
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
                        nickname=nickname,
                        grade=8,
                        language="zh-CN",
                    )
                )
            await session.commit()

    asyncio.run(run())


@pytest.fixture(scope="module")
def client() -> TestClient:
    _ensure_content()
    _ensure_user(OWNER_NAME, OWNER_PASSWORD, "测验测试")
    _ensure_user(OTHER_NAME, OTHER_PASSWORD, "其他测验测试")
    return TestClient(app)


@pytest.fixture(scope="module")
def token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": OWNER_NAME, "password": OWNER_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


@pytest.fixture(scope="module")
def other_token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": OTHER_NAME, "password": OTHER_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def headers(token: str, **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", **extra}


def create_conversation(client: TestClient, token: str) -> dict:
    response = client.post(
        "/api/v1/conversations",
        headers=headers(token, **{"Idempotency-Key": f"conv-{uuid4()}"}),
        json={"title": "测验发起会话"},
    )
    assert response.status_code == 201
    return response.json()["data"]


def create_quiz(
    client: TestClient,
    token: str,
    *,
    question_count: int = 1,
    conversation_id: str | None = None,
) -> tuple[dict, str]:
    conversation = (
        {"conversation_id": conversation_id}
        if conversation_id is not None
        else create_conversation(client, token)
    )
    response = client.post(
        "/api/v1/quiz-sessions",
        headers=headers(token),
        json={
            "conversation_id": conversation["conversation_id"],
            "book_id": str(BOOK_ID),
            "chapter_id": str(CHAPTER_ID),
            "quiz_kind": "CHAPTER_QUIZ",
            "question_count": question_count,
            "difficulty": "MEDIUM",
        },
    )
    assert response.status_code == 201
    return response.json()["data"], conversation["conversation_id"]


class TestQuizAPI:
    def test_requires_authentication(self, client: TestClient) -> None:
        response = client.get("/api/v1/quiz-sessions")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHENTICATED"

    def test_create_generates_active_session_snapshot_and_questions(
        self, client: TestClient, token: str
    ) -> None:
        session, _ = create_quiz(client, token, question_count=3)

        assert session["status"] == "ACTIVE"
        assert session["quiz_kind"] == "CHAPTER_QUIZ"
        assert session["skill_version"] == "quiz-v1"
        assert len(session["questions_snapshot"]) == 3
        assert all("correct_answer" in question for question in session["questions_snapshot"])

        questions = client.get(
            f"/api/v1/quiz-sessions/{session['quiz_session_id']}/questions",
            headers=headers(token),
        )
        assert questions.status_code == 200
        rows = questions.json()["data"]
        assert [row["question_order"] for row in rows] == [1, 2, 3]
        assert all("correct_answer" not in row for row in rows)
        assert all("explanation" not in row for row in rows)

        detail = client.get(
            f"/api/v1/quiz-sessions/{session['quiz_session_id']}",
            headers=headers(token),
        )
        assert detail.status_code == 200
        assert detail.json()["data"]["questions_snapshot"] == session["questions_snapshot"]

    def test_list_filters_and_detail_is_owner_scoped(
        self,
        client: TestClient,
        token: str,
        other_token: str,
    ) -> None:
        session, _ = create_quiz(client, token)
        response = client.get(
            "/api/v1/quiz-sessions",
            params={
                "quiz_kind": "CHAPTER_QUIZ",
                "status": "ACTIVE",
                "book_id": str(BOOK_ID),
                "limit": 10,
            },
            headers=headers(token),
        )
        assert response.status_code == 200
        assert session["quiz_session_id"] in {
            row["quiz_session_id"] for row in response.json()["data"]
        }

        forbidden = client.get(
            f"/api/v1/quiz-sessions/{session['quiz_session_id']}",
            headers=headers(other_token),
        )
        assert forbidden.status_code == 403
        assert forbidden.json()["error"]["code"] == "FORBIDDEN"

        missing = client.get(
            f"/api/v1/quiz-sessions/{uuid4()}", headers=headers(token)
        )
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "QUIZ_NOT_FOUND"

    def test_correct_answer_is_idempotent_and_links_learning_event(
        self, client: TestClient, token: str
    ) -> None:
        session, _ = create_quiz(client, token)
        question = session["questions_snapshot"][0]
        answer_payload = {"answer": question["correct_answer"]}
        endpoint = (
            f"/api/v1/quiz-sessions/{session['quiz_session_id']}"
            f"/questions/{question['question_id']}/answers"
        )
        answer_headers = headers(token, **{"Idempotency-Key": "quiz-answer-1"})

        created = client.post(endpoint, headers=answer_headers, json=answer_payload)
        assert created.status_code == 201
        answer = created.json()["data"]
        assert answer["is_correct"] is True
        assert answer["attempt_no"] == 1
        assert answer["is_final"] is True

        replay = client.post(endpoint, headers=answer_headers, json=answer_payload)
        assert replay.status_code == 200
        assert replay.headers["idempotency-replayed"] == "true"
        assert replay.json()["data"]["answer_id"] == answer["answer_id"]

        answers = client.get(
            f"/api/v1/quiz-sessions/{session['quiz_session_id']}/answers",
            headers=headers(token),
        )
        assert answers.status_code == 200
        assert len(answers.json()["data"]) == 1

        interactions = client.get(
            f"/api/v1/quiz-sessions/{session['quiz_session_id']}/interactions",
            headers=headers(token),
        )
        assert [row["interaction_type"] for row in interactions.json()["data"]] == [
            "ANSWER_SUBMIT",
            "ANSWER_RESULT",
        ]

        events = client.get(
            "/api/v1/me/learning-events?event_type=ANSWER_CORRECT",
            headers=headers(token),
        )
        assert events.status_code == 200
        assert any(
            row["quiz_session_id"] == session["quiz_session_id"]
            for row in events.json()["data"]
        )

        detail = client.get(
            f"/api/v1/quiz-sessions/{session['quiz_session_id']}",
            headers=headers(token),
        )
        assert detail.json()["data"]["status"] == "COMPLETED"
        assert detail.json()["data"]["result_summary"] == {
            "correct": 1,
            "total": 1,
            "hints_used": 0,
        }

        revealed = client.get(
            f"/api/v1/quiz-sessions/{session['quiz_session_id']}/questions",
            headers=headers(token),
        )
        assert revealed.json()["data"][0]["correct_answer"] == question["correct_answer"]
        assert revealed.json()["data"][0]["explanation"]

    def test_wrong_then_correct_creates_new_attempt(
        self, client: TestClient, token: str
    ) -> None:
        session, _ = create_quiz(client, token)
        question = session["questions_snapshot"][0]
        wrong_key = "A" if question["correct_answer"].get("key") != "A" else "C"
        endpoint = (
            f"/api/v1/quiz-sessions/{session['quiz_session_id']}"
            f"/questions/{question['question_id']}/answers"
        )

        wrong = client.post(
            endpoint,
            headers=headers(token, **{"Idempotency-Key": "quiz-answer-wrong"}),
            json={"answer": {"key": wrong_key}},
        )
        assert wrong.status_code == 201
        assert wrong.json()["data"]["is_correct"] is False
        assert wrong.json()["data"]["is_final"] is False

        correct = client.post(
            endpoint,
            headers=headers(token, **{"Idempotency-Key": "quiz-answer-correct"}),
            json={"answer": question["correct_answer"]},
        )
        assert correct.status_code == 201
        assert correct.json()["data"]["attempt_no"] == 2
        assert correct.json()["data"]["is_final"] is True

    def test_hints_create_message_and_audit_until_limit(
        self, client: TestClient, token: str
    ) -> None:
        session, conversation_id = create_quiz(client, token)
        question = session["questions_snapshot"][0]
        endpoint = (
            f"/api/v1/quiz-sessions/{session['quiz_session_id']}"
            f"/questions/{question['question_id']}/hints"
        )

        first = client.post(
            endpoint,
            headers=headers(token, **{"Idempotency-Key": "quiz-hint-1"}),
        )
        assert first.status_code == 201
        first_data = first.json()["data"]
        assert first_data["hint_level"] == 1
        assert first_data["hint_text"]
        assert first_data["max_hint_level"] == 3

        second = client.post(endpoint, headers=headers(token))
        third = client.post(endpoint, headers=headers(token))
        assert second.status_code == 201
        assert third.status_code == 201
        assert third.json()["data"]["hint_level"] == 3

        exhausted = client.post(endpoint, headers=headers(token))
        assert exhausted.status_code == 409
        assert exhausted.json()["error"]["code"] == "QUIZ_HINT_LIMIT_REACHED"

        interactions = client.get(
            f"/api/v1/quiz-sessions/{session['quiz_session_id']}/interactions",
            headers=headers(token),
        )
        types = [row["interaction_type"] for row in interactions.json()["data"]]
        assert types == [
            "HINT_REQUEST",
            "HINT_RESPONSE",
            "HINT_REQUEST",
            "HINT_RESPONSE",
            "HINT_REQUEST",
            "HINT_RESPONSE",
        ]

        messages = client.get(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=headers(token),
        )
        assert messages.status_code == 200
        assert [row["type"] for row in messages.json()["data"]] == ["HINT", "HINT", "HINT"]
        assert all(row["content"] for row in messages.json()["data"])
        assert "训练数据" in messages.json()["data"][0]["content"]

    def test_answer_and_hint_reject_foreign_question_or_completed_session(
        self,
        client: TestClient,
        token: str,
        other_token: str,
    ) -> None:
        session, _ = create_quiz(client, token)
        question = session["questions_snapshot"][0]
        question_path = (
            f"/api/v1/quiz-sessions/{session['quiz_session_id']}"
            f"/questions/{question['question_id']}"
        )

        forbidden = client.post(
            f"{question_path}/answers",
            headers=headers(other_token),
            json={"answer": {"key": "A"}},
        )
        assert forbidden.status_code == 403

        missing_question = client.post(
            f"/api/v1/quiz-sessions/{session['quiz_session_id']}/questions/{uuid4()}/answers",
            headers=headers(token),
            json={"answer": {"key": "A"}},
        )
        assert missing_question.status_code == 404
        assert missing_question.json()["error"]["code"] == "QUESTION_NOT_FOUND"

        answer_endpoint = f"{question_path}/answers"
        answer = client.post(
            answer_endpoint,
            headers=headers(token),
            json={"answer": question["correct_answer"]},
        )
        assert answer.status_code == 201
        finalized = client.post(
            answer_endpoint,
            headers=headers(token),
            json={"answer": {"key": "A"}},
        )
        assert finalized.status_code == 409
        assert finalized.json()["error"]["code"] == "QUIZ_FINALIZED"

        hint = client.post(f"{question_path}/hints", headers=headers(token))
        assert hint.status_code == 409
        assert hint.json()["error"]["code"] == "QUIZ_FINALIZED"

    def test_create_rejects_foreign_conversation_and_invalid_content_reference(
        self,
        client: TestClient,
        token: str,
        other_token: str,
    ) -> None:
        other_conversation = create_conversation(client, other_token)
        foreign = client.post(
            "/api/v1/quiz-sessions",
            headers=headers(token),
            json={"conversation_id": other_conversation["conversation_id"]},
        )
        assert foreign.status_code == 403
        assert foreign.json()["error"]["code"] == "FORBIDDEN"

        conversation = create_conversation(client, token)
        invalid_reference = client.post(
            "/api/v1/quiz-sessions",
            headers=headers(token),
            json={
                "conversation_id": conversation["conversation_id"],
                "book_id": str(BOOK_ID),
                "chapter_id": str(uuid4()),
            },
        )
        assert invalid_reference.status_code == 404
        assert invalid_reference.json()["error"]["code"] == "CHAPTER_NOT_FOUND"

    @pytest.mark.parametrize(
        "payload",
        [
            {"question_count": 0},
            {"question_count": 11},
            {"quiz_kind": "UNKNOWN"},
            {"difficulty": "UNKNOWN"},
        ],
    )
    def test_create_validates_generation_parameters(
        self, client: TestClient, token: str, payload: dict
    ) -> None:
        conversation = create_conversation(client, token)
        body = {"conversation_id": conversation["conversation_id"], **payload}
        response = client.post(
            "/api/v1/quiz-sessions", headers=headers(token), json=body
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_create_rejects_missing_conversation(
        self, client: TestClient, token: str
    ) -> None:
        response = client.post(
            "/api/v1/quiz-sessions",
            headers=headers(token),
            json={"conversation_id": str(uuid4())},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"

    def test_create_rejects_missing_book(
        self, client: TestClient, token: str
    ) -> None:
        conversation = create_conversation(client, token)
        response = client.post(
            "/api/v1/quiz-sessions",
            headers=headers(token),
            json={
                "conversation_id": conversation["conversation_id"],
                "book_id": str(uuid4()),
            },
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "BOOK_NOT_FOUND"

    def test_create_rejects_deleted_conversation(
        self, client: TestClient, token: str
    ) -> None:
        conversation = create_conversation(client, token)
        deleted = client.patch(
            f"/api/v1/conversations/{conversation['conversation_id']}",
            headers=headers(token),
            json={"status": "DELETED"},
        )
        assert deleted.status_code == 200

        response = client.post(
            "/api/v1/quiz-sessions",
            headers=headers(token),
            json={"conversation_id": conversation["conversation_id"]},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "QUIZ_INVALID_STATUS"

    def test_create_supports_ai_quiz_with_default_question_count(
        self, client: TestClient, token: str
    ) -> None:
        conversation = create_conversation(client, token)
        response = client.post(
            "/api/v1/quiz-sessions",
            headers=headers(token),
            json={
                "conversation_id": conversation["conversation_id"],
                "quiz_kind": "AI_QUIZ",
            },
        )
        assert response.status_code == 201
        session = response.json()["data"]
        assert session["quiz_kind"] == "AI_QUIZ"
        assert session["status"] == "ACTIVE"
        assert len(session["questions_snapshot"]) == 3
        assert session["result_summary"]["total"] == 3

    def test_list_cursor_pagination_has_no_overlap(
        self, client: TestClient, token: str
    ) -> None:
        for _ in range(3):
            create_quiz(client, token)

        first = client.get(
            "/api/v1/quiz-sessions",
            params={"book_id": str(BOOK_ID), "limit": 2},
            headers=headers(token),
        )
        assert first.status_code == 200
        first_rows = first.json()["data"]
        assert len(first_rows) == 2
        assert first.json()["meta"]["has_more"] is True
        next_cursor = first.json()["meta"]["next_cursor"]
        assert next_cursor

        second = client.get(
            "/api/v1/quiz-sessions",
            params={"book_id": str(BOOK_ID), "limit": 2, "cursor": next_cursor},
            headers=headers(token),
        )
        assert second.status_code == 200
        second_rows = second.json()["data"]
        assert second_rows
        first_ids = {row["quiz_session_id"] for row in first_rows}
        second_ids = {row["quiz_session_id"] for row in second_rows}
        assert first_ids.isdisjoint(second_ids)

    @pytest.mark.parametrize(
        "method,path_template",
        [
            ("GET", "/api/v1/quiz-sessions/{quiz}/questions"),
            ("GET", "/api/v1/quiz-sessions/{quiz}/answers"),
            ("GET", "/api/v1/quiz-sessions/{quiz}/interactions"),
            (
                "POST",
                "/api/v1/quiz-sessions/{quiz}/questions/{question}/answers",
            ),
            ("POST", "/api/v1/quiz-sessions/{quiz}/questions/{question}/hints"),
        ],
    )
    def test_unknown_quiz_returns_404_for_every_subresource(
        self,
        client: TestClient,
        token: str,
        method: str,
        path_template: str,
    ) -> None:
        path = path_template.format(quiz=uuid4(), question=uuid4())
        kwargs = {}
        if method == "POST" and path.endswith("/answers"):
            kwargs["json"] = {"answer": {"key": "A"}}
        response = client.request(method, path, headers=headers(token), **kwargs)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "QUIZ_NOT_FOUND"

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/quiz-sessions/{quiz}/questions",
            "/api/v1/quiz-sessions/{quiz}/answers",
            "/api/v1/quiz-sessions/{quiz}/interactions",
        ],
    )
    def test_quiz_subresources_are_owner_scoped(
        self,
        client: TestClient,
        token: str,
        other_token: str,
        path: str,
    ) -> None:
        session, _ = create_quiz(client, token)
        response = client.get(
            path.format(quiz=session["quiz_session_id"]),
            headers=headers(other_token),
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"

    def test_hint_limit_is_per_question(
        self, client: TestClient, token: str
    ) -> None:
        session, _ = create_quiz(client, token, question_count=2)
        first_question = session["questions_snapshot"][0]
        second_question = session["questions_snapshot"][1]
        first_endpoint = (
            f"/api/v1/quiz-sessions/{session['quiz_session_id']}"
            f"/questions/{first_question['question_id']}/hints"
        )
        second_endpoint = (
            f"/api/v1/quiz-sessions/{session['quiz_session_id']}"
            f"/questions/{second_question['question_id']}/hints"
        )

        for _ in range(3):
            assert client.post(first_endpoint, headers=headers(token)).status_code == 201
        assert client.post(first_endpoint, headers=headers(token)).status_code == 409

        fresh = client.post(second_endpoint, headers=headers(token))
        assert fresh.status_code == 201
        assert fresh.json()["data"]["hint_level"] == 1

    def test_wrong_then_hint_then_correct_tracks_hint_usage(
        self, client: TestClient, token: str
    ) -> None:
        session, _ = create_quiz(client, token)
        question = session["questions_snapshot"][0]
        correct_key = question["correct_answer"]["key"]
        wrong_key = "A" if correct_key != "A" else "C"
        answer_endpoint = (
            f"/api/v1/quiz-sessions/{session['quiz_session_id']}"
            f"/questions/{question['question_id']}/answers"
        )
        hint_endpoint = (
            f"/api/v1/quiz-sessions/{session['quiz_session_id']}"
            f"/questions/{question['question_id']}/hints"
        )

        wrong = client.post(
            answer_endpoint,
            headers=headers(token, **{"Idempotency-Key": "hint-flow-wrong"}),
            json={"answer": {"key": wrong_key}},
        )
        assert wrong.status_code == 201
        assert wrong.json()["data"]["is_correct"] is False
        assert wrong.json()["data"]["is_final"] is False

        hint = client.post(hint_endpoint, headers=headers(token))
        assert hint.status_code == 201
        assert hint.json()["data"]["hint_level"] == 1

        correct = client.post(
            answer_endpoint,
            headers=headers(token, **{"Idempotency-Key": "hint-flow-correct"}),
            json={"answer": question["correct_answer"]},
        )
        assert correct.status_code == 201
        assert correct.json()["data"]["attempt_no"] == 2
        assert correct.json()["data"]["is_final"] is True

        detail = client.get(
            f"/api/v1/quiz-sessions/{session['quiz_session_id']}",
            headers=headers(token),
        )
        assert detail.json()["data"]["result_summary"]["hints_used"] == 1

    def test_same_idempotency_key_with_different_answer_is_rejected(
        self, client: TestClient, token: str
    ) -> None:
        session, _ = create_quiz(client, token)
        question = session["questions_snapshot"][0]
        endpoint = (
            f"/api/v1/quiz-sessions/{session['quiz_session_id']}"
            f"/questions/{question['question_id']}/answers"
        )
        key_headers = headers(token, **{"Idempotency-Key": "conflict-key"})

        first = client.post(
            endpoint,
            headers=key_headers,
            json={"answer": question["correct_answer"]},
        )
        assert first.status_code == 201

        conflict = client.post(
            endpoint,
            headers=key_headers,
            json={"answer": {"key": "A"}},
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    def test_identical_answer_without_key_is_replayed(
        self, client: TestClient, token: str
    ) -> None:
        session, _ = create_quiz(client, token)
        question = session["questions_snapshot"][0]
        endpoint = (
            f"/api/v1/quiz-sessions/{session['quiz_session_id']}"
            f"/questions/{question['question_id']}/answers"
        )

        first = client.post(
            endpoint,
            headers=headers(token),
            json={"answer": question["correct_answer"]},
        )
        assert first.status_code == 201
        replay = client.post(
            endpoint,
            headers=headers(token),
            json={"answer": question["correct_answer"]},
        )
        assert replay.status_code == 200
        assert replay.headers["idempotency-replayed"] == "true"
        assert replay.json()["data"]["answer_id"] == first.json()["data"]["answer_id"]

    def test_hint_idempotency_key_is_replayed(
        self, client: TestClient, token: str
    ) -> None:
        session, _ = create_quiz(client, token)
        question = session["questions_snapshot"][0]
        endpoint = (
            f"/api/v1/quiz-sessions/{session['quiz_session_id']}"
            f"/questions/{question['question_id']}/hints"
        )
        key_headers = headers(token, **{"Idempotency-Key": "hint-replay-key"})

        first = client.post(endpoint, headers=key_headers)
        assert first.status_code == 201
        replay = client.post(endpoint, headers=key_headers)
        assert replay.status_code == 200
        assert replay.headers["idempotency-replayed"] == "true"
        assert replay.json()["data"]["interaction_id"] == first.json()["data"]["interaction_id"]
        assert replay.json()["data"]["hint_level"] == first.json()["data"]["hint_level"]

    def test_three_wrong_attempts_finalize_question_and_session(
        self, client: TestClient, token: str
    ) -> None:
        session, _ = create_quiz(client, token)
        question = session["questions_snapshot"][0]
        correct_key = question["correct_answer"]["key"]
        wrong_keys = [
            option["key"]
            for option in question["options"]
            if option["key"] != correct_key
        ][:3]
        assert len(wrong_keys) == 3
        endpoint = (
            f"/api/v1/quiz-sessions/{session['quiz_session_id']}"
            f"/questions/{question['question_id']}/answers"
        )

        finals = []
        for index, wrong_key in enumerate(wrong_keys, start=1):
            response = client.post(
                endpoint,
                headers=headers(token, **{"Idempotency-Key": f"final-attempt-{index}"}),
                json={"answer": {"key": wrong_key}},
            )
            assert response.status_code == 201
            finals.append(response.json()["data"]["is_final"])
        assert finals == [False, False, True]

        detail = client.get(
            f"/api/v1/quiz-sessions/{session['quiz_session_id']}",
            headers=headers(token),
        )
        assert detail.json()["data"]["status"] == "COMPLETED"
        assert detail.json()["data"]["ai_feedback"]

        after = client.post(
            endpoint,
            headers=headers(token),
            json={"answer": question["correct_answer"]},
        )
        assert after.status_code == 409
        assert after.json()["error"]["code"] == "QUIZ_FINALIZED"
