"""Books-list cache tests; database and Redis are both replaced with fakes."""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from app.api.deps import AdminPrincipal
from app.modules.admin import service as admin_module
from app.modules.admin.schemas import CreateBookRequest
from app.modules.admin.service import AdminService
from app.modules.content import service as content_module
from app.modules.content.schemas import BookPageDTO, BookPageMeta
from app.modules.content.service import ContentService


class EmptyResult:
    def scalars(self):
        return self

    def all(self):
        return []


class FakeSession:
    def __init__(self) -> None:
        self.execute_calls = 0

    async def execute(self, _query):
        self.execute_calls += 1
        return EmptyResult()


def run(coro):
    return asyncio.run(coro)


def empty_page() -> BookPageDTO:
    return BookPageDTO(items=[], meta=BookPageMeta(next_cursor=None, has_more=False))


def test_books_list_cache_hit_avoids_database_query(monkeypatch) -> None:
    session = FakeSession()
    page = empty_page()
    seen_keys: list[str] = []

    async def fake_get(key: str):
        seen_keys.append(key)
        return page.model_dump(mode="json")

    async def unexpected_set(*_args, **_kwargs):
        raise AssertionError("cache hit must not rewrite the cache")

    monkeypatch.setattr(content_module, "cache_get", fake_get)
    monkeypatch.setattr(content_module, "cache_set", unexpected_set)

    result = run(
        ContentService().list_books(
            session,
            cursor=None,
            limit=20,
            grade_min=None,
            grade_max=None,
            tag=None,
            status="PUBLISHED",
        )
    )

    assert result == page
    assert session.execute_calls == 0
    assert seen_keys[0].startswith("cache:books:list:")


def test_books_list_cache_miss_queries_and_backfills(monkeypatch) -> None:
    session = FakeSession()
    stored: dict[str, object] = {}

    async def fake_get(key: str):
        return stored.get(key)

    async def fake_set(key: str, value, ttl: int):
        stored[key] = value
        assert ttl == 60
        return True

    monkeypatch.setattr(content_module, "cache_get", fake_get)
    monkeypatch.setattr(content_module, "cache_set", fake_set)

    result = run(
        ContentService().list_books(
            session,
            cursor=None,
            limit=20,
            grade_min=None,
            grade_max=None,
            tag=None,
            status="PUBLISHED",
        )
    )

    assert result == empty_page()
    assert session.execute_calls == 1
    assert len(stored) == 1


def test_admin_book_creation_invalidates_books_namespace(monkeypatch) -> None:
    class AdminSession:
        def add(self, book) -> None:
            self.book = book

        async def flush(self) -> None:
            now = datetime.now(timezone.utc)
            self.book.created_at = now
            self.book.updated_at = now

    invalidations: list[str] = []

    async def fake_delete_prefix(prefix: str) -> int:
        invalidations.append(prefix)
        return 1

    monkeypatch.setattr(admin_module, "cache_delete_prefix", fake_delete_prefix)
    result = run(
        AdminService().create_book(
            AdminSession(),
            AdminPrincipal(
                admin_id=uuid4(),
                user_id=uuid4(),
                display_name="test admin",
                role_level="ADMIN",
            ),
            CreateBookRequest(title="cache invalidation test"),
        )
    )

    assert result.title == "cache invalidation test"
    assert invalidations == ["cache:books:list:"]
