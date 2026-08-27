"""图书馆语料库幂等导入器：文件语料 → 开发库。

用法：
    uv run python -m app.scripts.import_library --book <slug>
    uv run python -m app.scripts.import_library --knowledge <slug>
    uv run python -m app.scripts.import_library --all

约定：
- 导入前先跑 validate_library 的结构校验，FAIL 直接中止（不写库）；
- 主键采用确定性 UUID（uuid5），重复运行天然幂等，按「存在即更新」收敛；
- Book / Chapter 固定写 status=PUBLISHED；书内 knowledge_points 按 slug
  存在则跳过、不存在则创建；
- 知识库文档走 app.modules.knowledge.ingestion.ingest_text，
  幂等键为 (source_url, storage_key)；source_url 为空时生成稳定内部 URI；
- 导入完成后失效书单 Redis 缓存（cache:books:list:*），避免书库读到旧缓存；
- ``--all`` 会把旧 seed_content.py 占位路径创建的 12 本旧书归档
  （status=ARCHIVED，保留阅读历史外键，不再出现在正式书库），
  这是旧内容的唯一正式处理策略；全新环境无旧行时为空操作。
- 同名冲突策略（缺陷 B 回归约定）：标题回退匹配只收编「历史非确定性
  导入且仍在线」的书行；legacy 占位书与已归档行一律不劫持——正式书
  以确定性 UUID 新建并写入完整章节。若历史版本曾把确定性章节/内容块
  误挂到 legacy 书名下，导入时按确定性 ID 自动回收（改挂正式书），
  无需手工清库。
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select

from app.infrastructure.cache.redis import cache_delete_prefix
from app.infrastructure.database.engine import engine
from app.infrastructure.database.models import (
    Book,
    Chapter,
    ContentBlock,
    KnowledgePoint,
)
from app.infrastructure.database.session import async_session
from app.modules.knowledge.ingestion import (
    ingest_text,
    storage_key_for,
)
from app.scripts.validate_library import (
    LIB_ROOT,
    TYPE_TO_DB,
    build_content,
    load_manifest,
    parse_chapter_md,
    parse_knowledge_doc,
    validate_book,
)


def _uuid(key: str) -> UUID:
    """确定性 UUID：与旧 seed_content 同一命名空间模式，重复导入主键不变。"""
    return uuid5(NAMESPACE_URL, key)


def _book_id(slug: str) -> UUID:
    return _uuid(f"shuangling:library:book:{slug}")


def _chapter_id(slug: str, order: int) -> UUID:
    return _uuid(f"shuangling:library:chapter:{slug}:{order}")


def _block_id(slug: str, ch_order: int, block_order: int) -> UUID:
    return _uuid(f"shuangling:library:block:{slug}:{ch_order}:{block_order}")


def _kp_id(slug: str) -> UUID:
    return _uuid(f"shuangling:kp:{slug}")


# 旧 seed_content.py（占位路径）创建的 12 本书确定性主键：uuid5("shuangling:book:<no>")
LEGACY_SEED_BOOK_IDS = frozenset(
    _uuid(f"shuangling:book:{no:02d}") for no in range(1, 13)
)


def _require_pass(slug: str) -> None:
    issues, _ = validate_book(slug, {})
    if issues:
        for issue in issues:
            print(f"  [FAIL][{issue.rule}][{issue.where}] {issue.message}")
        raise SystemExit(f"validate_library 未通过，禁止导入：{slug}")


async def ensure_knowledge_points(session, kps: list[dict]) -> tuple[dict[str, KnowledgePoint], int]:
    rows: dict[str, KnowledgePoint] = {}
    created = 0
    for item in kps:
        slug = item["slug"]
        row = (
            await session.execute(
                select(KnowledgePoint).where(KnowledgePoint.slug == slug)
            )
        ).scalar_one_or_none()
        if row is None:
            created += 1
            row = KnowledgePoint(
                knowledge_point_id=_kp_id(slug),
                name=item["name"],
                slug=slug,
                description=item.get("description"),
                topic=item.get("topic"),
                parent_id=None,
                status="ACTIVE",
            )
            session.add(row)
        rows[slug] = row
    await session.flush()
    return rows, created


def load_book_files(slug: str) -> tuple[dict, list[tuple[int, list[dict], list[list[str]]]]]:
    book_dir = LIB_ROOT / "books" / slug
    book = json.loads((book_dir / "book.json").read_text(encoding="utf-8"))
    parsed: list[tuple[int, list[dict], list[list[str]]]] = []
    for ch in sorted(book["chapters"], key=lambda c: c["order"]):
        issues: list = []
        blocks, _meta = parse_chapter_md(book_dir / ch["file"], issues)
        if issues:
            raise SystemExit(f"{ch['file']} 解析异常：{issues}")
        contents = []
        kp_lists = []
        for block in blocks:
            contents.append(
                {
                    "block_type": TYPE_TO_DB[block["type"]],
                    "content": build_content(block),
                    "section_key": block["section_key"],
                }
            )
            kp_lists.append([s.strip() for s in block["kps"]])
        parsed.append((ch["order"], contents, kp_lists))
    return book, parsed


async def import_book(slug: str) -> None:
    print(f"== 导入书籍 {slug} ==")
    _require_pass(slug)
    book, parsed = load_book_files(slug)

    async with async_session() as session:
        kps, kp_created = await ensure_knowledge_points(
            session, book.get("knowledge_points", [])
        )

        # ---- Book ----
        row = await session.get(Book, _book_id(slug))
        if row is None:
            # 标题回退只允许收编「历史非确定性导入且仍在线」的书行。
            # 绝不能劫持：① legacy 占位书（retire 按 ID 归档它们，劫持会造成
            # 导入置 PUBLISHED ↔ 归档互相打架，且正式书永远无法以确定性
            # UUID 落库）；② 已 ARCHIVED 的行。同名冲突时正式书必须获得
            # 自己的确定性 UUID 与完整章节内容（缺陷 B）。
            # 排除条件必须下推到 SQL：库里可能同时存在多条同名行
            # （如 legacy 行 + 已归档行），Python 侧过滤会先撞上
            # MultipleResultsFound。候选不唯一时视为歧义，直接走新建。
            candidates = (
                await session.execute(
                    select(Book)
                    .where(Book.title == book["title"])
                    .where(Book.book_id.not_in(LEGACY_SEED_BOOK_IDS))
                    .where(Book.status != "ARCHIVED")
                )
            ).scalars().all()
            if len(candidates) == 1:
                row = candidates[0]
        now = datetime.now(UTC)
        if row is None:
            row = Book(book_id=_book_id(slug))
            session.add(row)
            print(f"  创建书籍《{book['title']}》")
        else:
            print(f"  更新已有书籍《{row.title}》（id={row.book_id}）")
        row.title = book["title"]
        row.description = book["description"]
        row.grade_min = book["grade_min"]
        row.grade_max = book["grade_max"]
        row.difficulty = book["difficulty"]
        row.estimated_minutes = book["estimated_minutes"]
        row.author = book.get("author")
        row.tags = book.get("tags", [])
        row.license = book.get("license")
        row.copyright_status = book.get("copyright_status")
        row.status = "PUBLISHED"
        if getattr(row, "published_at", None) is None:
            row.published_at = now
        if row.source_ids is None:
            row.source_ids = []
        await session.flush()
        book_id = row.book_id

        total_blocks = 0
        total_cjk = 0
        for ch_order, contents, kp_lists in parsed:
            det_chapter_id = _chapter_id(slug, ch_order)
            ch_row = (
                await session.execute(
                    select(Chapter).where(
                        Chapter.book_id == book_id,
                        Chapter.chapter_order == ch_order,
                    )
                )
            ).scalar_one_or_none()
            if ch_row is None:
                # 确定性章节 ID 可能已存在但被历史劫持挂在了别的书名下
                # （如旧版实现按标题误更新 legacy 行的遗留）。此时把章节
                # 重新认领到正式书名下，内容块随章节一并归属，无需手工
                # 清库即可自愈。
                ch_row = await session.get(Chapter, det_chapter_id)
                if ch_row is not None and ch_row.book_id != book_id:
                    print(
                        f"  回收误挂章节 order={ch_order}"
                        f"（原 book_id={ch_row.book_id} → {book_id}）"
                    )
                    ch_row.book_id = book_id
            if ch_row is None:
                ch_row = Chapter(
                    chapter_id=det_chapter_id,
                    book_id=book_id,
                    chapter_order=ch_order,
                )
                session.add(ch_row)
            ch_meta = next(c for c in book["chapters"] if c["order"] == ch_order)
            ch_row.title = ch_meta["title"]
            ch_row.summary = ch_meta["summary"]
            ch_row.estimated_minutes = ch_meta["minutes"]
            ch_row.status = "PUBLISHED"
            await session.flush()

            existing = (
                await session.execute(
                    select(ContentBlock).where(ContentBlock.chapter_id == ch_row.chapter_id)
                )
            ).scalars().all()
            existing_by_order = {b.block_order: b for b in existing}

            for i, item in enumerate(contents, start=1):
                kp_ids = [
                    str(kps[s].knowledge_point_id) for s in kp_lists[i - 1] if s in kps
                ]
                block = existing_by_order.pop(i, None)
                if block is None:
                    # 与章节同理：确定性内容块 ID 也可能被历史劫持残留挂在
                    # 别的章节名下，按 ID 认领回来，避免主键冲突。
                    block = await session.get(
                        ContentBlock, _block_id(slug, ch_order, i)
                    )
                    if block is not None and block.chapter_id != ch_row.chapter_id:
                        print(f"  回收误挂内容块 ch={ch_order} order={i}")
                        block.chapter_id = ch_row.chapter_id
                if block is None:
                    block = ContentBlock(
                        block_id=_block_id(slug, ch_order, i),
                        chapter_id=ch_row.chapter_id,
                        block_order=i,
                    )
                    session.add(block)
                block.block_type = item["block_type"]
                block.content = item["content"]
                block.section_key = item["section_key"]
                block.knowledge_point_ids = kp_ids
                text = item["content"].get("text") or item["content"].get("caption") or ""
                total_cjk += len(text)
            # 清理本章节中属于本书但已被文件删除的尾部旧块（仅限确定性 ID 归属）
            known_ours = {
                _block_id(slug, ch_order, j) for j in range(1, max(len(contents), 200) + 1)
            }
            for order_stale, block in existing_by_order.items():
                if block.block_id in known_ours:
                    await session.delete(block)
                    print(f"  清理陈旧块 chapter={ch_order} order={order_stale}")
            total_blocks += len(contents)

        db_chapters = (
            await session.execute(select(Chapter).where(Chapter.book_id == book_id))
        ).scalars().all()
        stale = [c.chapter_order for c in db_chapters if c.chapter_order not in {o for o, _, _ in parsed}]
        if stale:
            print(f"  警告：数据库中存在未导入的章节序号 {stale}（保留不删）")

        await session.commit()

    print(
        f"  完成：chapters={len(parsed)} blocks={total_blocks} "
        f"kp_total={len(kps)} kp_new={kp_created} approx_chars={total_cjk}"
    )


async def import_knowledge(slug: str) -> None:
    path = LIB_ROOT / "knowledge" / f"{slug}.md"
    if not path.is_file():
        raise SystemExit(f"找不到知识文档：{path}")
    issues: list = []
    front, body, n = parse_knowledge_doc(path, issues)
    if issues:
        for issue in issues:
            print(f"  [FAIL][{issue.rule}] {issue.message}")
        raise SystemExit(f"知识文档校验未通过，禁止导入：{slug}")

    source_name = front.get("source_name") or slug
    source_url = front.get("source_url") or f"local://library/knowledge/{slug}"
    storage_key = storage_key_for(source_url, source_name)

    # 与 Admin 上传行为一致：源文件落盘便于 Worker 重解析；只存正文，
    # 使存储副本与 ingest_text 的切块输入完全一致（front matter 元数据进 DB 列）。
    # Phase 4：源文件经统一存储抽象落盘（键带 knowledge/ 类别前缀）
    from app.infrastructure.storage import get_storage

    await get_storage().put(
        f"knowledge/{storage_key}", (body.strip() + "\n").encode("utf-8"), content_type="text/markdown"
    )

    async with async_session() as session:
        resource_id, chunk_count = await ingest_text(
            session,
            text=body,
            source_name=source_name,
            source_url=source_url,
            license=front.get("license") or "CC-BY",
            copyright_status=front.get("copyright_status") or "原创",
            author=front.get("author"),
            storage_key=storage_key,
        )
        print(
            f"== 导入知识文档 {slug} ==\n"
            f"  resource={resource_id} chunks={chunk_count} cjk={n} "
            f"source={source_name}"
        )


async def retire_legacy_seed_books() -> int:
    """归档旧 seed_content.py 创建的 12 本占位书（幂等）。

    处理策略：status=ARCHIVED（不物理删除）——保留 BookProgress / 学习事件等
    外键引用与历史可追溯性；ARCHIVED 书不出现在正式书库（PUBLISHED 过滤），
    旧占位章节随之不再可达。全新环境没有这些行时为空操作。
    """
    async with async_session() as session:
        rows = (
            await session.execute(
                select(Book).where(Book.book_id.in_(LEGACY_SEED_BOOK_IDS))
            )
        ).scalars().all()
        archived: list[str] = []
        for row in rows:
            if row.status != "ARCHIVED":
                row.status = "ARCHIVED"
                archived.append(f"《{row.title}》(id={row.book_id})")
        await session.commit()
    for title in archived:
        print(f"  归档旧占位书 {title}")
    return len(archived)


async def run(args: argparse.Namespace) -> None:
    try:
        if args.book:
            await import_book(args.book)
        elif args.knowledge:
            await import_knowledge(args.knowledge)
        elif args.all:
            manifest_slugs = load_manifest([])
            imported_slugs = sorted(manifest_slugs)
            for slug in imported_slugs:
                await import_book(slug)
            for doc in sorted((LIB_ROOT / "knowledge").glob("*.md")):
                await import_knowledge(doc.stem)
            retired = await retire_legacy_seed_books()
            print(
                f"import_library --all 完成：books={len(imported_slugs)} "
                f"knowledge={len(list((LIB_ROOT / 'knowledge').glob('*.md')))} "
                f"legacy_archived={retired}"
            )
        # 内容可能已变化：失效书单缓存，避免书库 API 读到导入前的旧页。
        invalidated = await cache_delete_prefix("cache:books:list:")
        if invalidated:
            print(f"  已失效书单缓存条目 {invalidated} 个")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="图书馆语料库幂等导入器")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--book", help="导入单本书（按 slug）")
    group.add_argument("--knowledge", help="导入单篇知识文档（按 slug）")
    group.add_argument("--all", action="store_true", help="导入 manifest 全部书 + 全部知识文档")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
