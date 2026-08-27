"""import_library 同标题 legacy 书冲突回归测试（缺陷 B）。

场景还原：manifest 正式书与旧 seed_content 占位书同标题时，旧实现会
按 title 回退劫持 legacy 行（置 PUBLISHED），随后 retire_legacy_seed_books
按 ID 把它归档——导入/归档互相打架，正式书永远无法以确定性 UUID 落库。

本测试验证修复后的契约：
1. 正式书获得自己的确定性 UUID，且 5 章完整、状态 PUBLISHED；
2. 不劫持 legacy 行；retire 按 ID 归档 legacy，重复导入不改变其状态；
3. 历史劫持遗留的确定性章节自动回收挂回正式书（自愈，无需手工清库）；
4. ``--book`` 级重复执行幂等收敛。

说明：测试结束仅清理本测试合成的 fake legacy 行；正式书的确定性章节/
内容块与 ``import_library`` 正常产出完全一致，保留即为收敛态（与 CI
seed 基线一致），不做破坏性删除。
"""

import asyncio
from datetime import datetime, timezone
from uuid import UUID

import pytest
from sqlalchemy import delete, select

import app.scripts.import_library as import_library_mod
from app.infrastructure.database.models import Book, Chapter, ContentBlock
from app.infrastructure.database.session import async_session
from app.scripts.import_library import (
    _book_id,
    _chapter_id,
    import_book,
    retire_legacy_seed_books,
)

SLUG = "robot-how-think"
FAKE_LEGACY_ID = UUID("e1111111-1111-1111-1111-111111111111")


def _book_title() -> str:
    book, _ = import_library_mod.load_book_files(SLUG)
    return book["title"]


@pytest.fixture()
def cleanup_fake_legacy():
    yield

    async def purge() -> None:
        async with async_session() as session:
            await session.execute(
                delete(ContentBlock).where(
                    ContentBlock.chapter_id.in_(
                        select(Chapter.chapter_id).where(
                            Chapter.book_id == FAKE_LEGACY_ID
                        )
                    )
                )
            )
            await session.execute(
                delete(Chapter).where(Chapter.book_id == FAKE_LEGACY_ID)
            )
            await session.execute(
                delete(Book).where(Book.book_id == FAKE_LEGACY_ID)
            )
            await session.commit()

    asyncio.run(purge())


def test_same_title_legacy_and_manifest_book_converge_idempotently(
    monkeypatch: pytest.MonkeyPatch,
    cleanup_fake_legacy,
) -> None:
    async def run() -> None:
        title = _book_title()
        formal_id = _book_id(SLUG)

        # 1. 构造同标题的 legacy 占位书 + 被历史劫持挂错位置的确定性章节。
        #    （若当前库已存在该确定性章节——如真实劫持残留或 CI 已导入——
        #    则跳过合成插入，直接复用现实状态验证回收/幂等行为。）
        async with async_session() as session:
            session.add(
                Book(
                    book_id=FAKE_LEGACY_ID,
                    title=title,
                    description="旧占位书（测试合成）",
                    grade_min=7,
                    grade_max=9,
                    difficulty="EASY",
                    estimated_minutes=30,
                    tags=[],
                    status="PUBLISHED",
                    published_at=datetime.now(timezone.utc),
                )
            )
            existing_det_chapter = await session.get(Chapter, _chapter_id(SLUG, 1))
            if existing_det_chapter is None:
                session.add(
                    Chapter(
                        chapter_id=_chapter_id(SLUG, 1),
                        book_id=FAKE_LEGACY_ID,
                        title="stale-hijacked-chapter",
                        chapter_order=1,
                        estimated_minutes=5,
                        status="PUBLISHED",
                    )
                )
            await session.commit()

        # 2. 把合成行纳入 retire 集合（同时约束导入的标题回退排除逻辑）。
        patched_legacy_ids = frozenset(
            {FAKE_LEGACY_ID} | set(import_library_mod.LEGACY_SEED_BOOK_IDS)
        )
        monkeypatch.setattr(
            import_library_mod, "LEGACY_SEED_BOOK_IDS", patched_legacy_ids
        )

        # ---- 第一次导入：正式书落库，legacy 不被劫持，误挂章节被回收 ----
        await import_book(SLUG)

        async with async_session() as session:
            formal = await session.get(Book, formal_id)
            assert formal is not None, "正式书未以确定性 UUID 创建"
            assert formal.book_id != FAKE_LEGACY_ID
            assert formal.status == "PUBLISHED"
            chapters = (
                await session.execute(
                    select(Chapter).where(Chapter.book_id == formal_id)
                )
            ).scalars().all()
            assert len(chapters) == 5
            adopted = await session.get(Chapter, _chapter_id(SLUG, 1))
            assert adopted is not None
            assert adopted.book_id == formal.book_id, "误挂的确定性章节未被回收"
            blocks = (
                await session.execute(
                    select(ContentBlock).where(
                        ContentBlock.chapter_id == adopted.chapter_id
                    )
                )
            ).scalars().all()
            assert len(blocks) >= 1, "回收后的章节缺少内容块"

        retired = await retire_legacy_seed_books()

        async with async_session() as session:
            legacy = await session.get(Book, FAKE_LEGACY_ID)
            assert legacy is not None
            assert legacy.status == "ARCHIVED", "同标题 legacy 行未被归档"
        assert retired >= 1

        # ---- 第二次导入：幂等收敛，不复活 legacy，不改正式书状态 ----
        formal_status_before = formal.status
        await import_book(SLUG)

        async with async_session() as session:
            formal_again = await session.get(Book, formal_id)
            assert formal_again is not None
            assert formal_again.status == formal_status_before == "PUBLISHED"
            legacy_again = await session.get(Book, FAKE_LEGACY_ID)
            assert legacy_again is not None
            assert legacy_again.status == "ARCHIVED", "重复导入复活了已归档的 legacy 行"
            adopted_again = await session.get(Chapter, _chapter_id(SLUG, 1))
            assert adopted_again is not None
            assert adopted_again.book_id == formal_id

        # ---- 第三次 retire：对已归档行为空操作，不复活任何行 ----
        await retire_legacy_seed_books()
        async with async_session() as session:
            legacy_final = await session.get(Book, FAKE_LEGACY_ID)
            assert legacy_final is not None
            assert legacy_final.status == "ARCHIVED"

    asyncio.run(run())
