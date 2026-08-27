"""Bulk re-index knowledge resources to the current embedding provider (CLI).

切换 EMBEDDING_PROVIDER（例如 mock 64 维 → 真实 1024/768 维）后，已入库的知识
资源仍保留旧的 embedding 向量。本脚本遍历现有资源，逐条「删除旧块 + 用当前
provider 重新解析/切块/embedding」（内部复用 ingest_stored_resource）。

数据库向量列是无维度类型（migration c7d8e9f0a1b2），两种维度可共存；检索按查询
维度过滤（modules/knowledge/service.py 的 vector_dims(embedding) = :dim），
所以部分重索引是安全的——旧维度块只是不会被命中。

Usage:
    # 预览将重索引的资源（不真正写库）
    uv run python -m app.scripts.reindex_embeddings --dry-run

    # 重索引全部 READY 资源
    uv run python -m app.scripts.reindex_embeddings

    # 只重索引前 20 条（小批量验证）
    uv run python -m app.scripts.reindex_embeddings --limit 20

    # 包含非 READY（FAILED / 半成品）的资源一并重试
    uv run python -m app.scripts.reindex_embeddings --all-status
"""

import argparse
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.config import settings
from app.infrastructure.database.session import async_session
from app.modules.knowledge.ingestion import ingest_stored_resource


async def list_resources(all_status: bool, corpus_only: bool = False) -> list:
    from app.infrastructure.database.models import KnowledgeResource

    async with async_session() as session:
        query = select(KnowledgeResource).order_by(KnowledgeResource.created_at.asc())
        if corpus_only:
            query = query.where(
                KnowledgeResource.source_url.like("local://library/knowledge/%")
            )
        if not all_status:
            query = query.where(KnowledgeResource.status == "READY")
        return list((await session.execute(query)).scalars().all())


async def _already_up_to_date(resource_id) -> bool:
    """资源的所有 chunk 是否已为目标维度（无需重嵌入）。"""
    from sqlalchemy import func, select

    from app.infrastructure.database.models import (
        KnowledgeChunk,
        KnowledgeResource,
    )

    async with async_session() as session:
        dims = (
            await session.execute(
                select(func.vector_dims(KnowledgeChunk.embedding))
                .where(KnowledgeChunk.resource_id == resource_id)
                .where(KnowledgeChunk.embedding.is_not(None))
                .distinct()
            )
        ).scalars().all()
        return len(dims) == 1 and dims[0] == settings.embedding_dimension


async def reindex(
    *,
    limit: int | None,
    all_status: bool,
    dry_run: bool,
    skip_up_to_date: bool,
    corpus_only: bool = False,
) -> tuple[int, int]:
    resources = await list_resources(all_status, corpus_only=corpus_only)
    if limit is not None:
        resources = resources[:limit]

    processed = 0
    skipped = 0
    ok = 0
    failed = 0
    total = len(resources)
    started = datetime.now(timezone.utc)
    print(
        f"[reindex] 共 {total} 条资源"
        f"（{'dry-run，仅预览' if dry_run else '将重索引'}）"
    )
    for idx, resource in enumerate(resources, 1):
        if skip_up_to_date and await _already_up_to_date(resource.resource_id):
            skipped += 1
            print(
                f"[reindex]   [{idx}/{total}] {resource.source_name} "
                f"({resource.status}) -> 已为 {settings.embedding_dimension} 维，跳过"
            )
            continue
        processed += 1
        print(f"[reindex]   [{idx}/{total}] {resource.source_name} ({resource.status})")
        if dry_run:
            continue
        try:
            async with async_session() as session:
                _, chunk_count = await ingest_stored_resource(
                    session, resource.resource_id, force_reprocess=True
                )
            ok += 1
            print(f"             -> 重建完成，{chunk_count} 块")
        except Exception as exc:  # noqa: BLE001 - 逐条隔离，单条失败不中断整批
            failed += 1
            print(f"             -> FAILED: {exc}")

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    print(
        f"[reindex] 完成：成功 {ok} / 失败 {failed} / 跳过 {skipped} / 共 {total}"
        f"，耗时 {elapsed:.1f}s"
        + ("（dry-run 未做任何写入）" if dry_run else "")
    )
    return ok, failed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="按当前 embedding provider 批量重索引知识资源"
    )
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 条")
    parser.add_argument(
        "--all-status",
        action="store_true",
        help="包含非 READY 资源（FAILED / PARSING 等）一并重试",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只列出将重索引的资源，不做任何写入",
    )
    parser.add_argument(
        "--skip-up-to-date",
        action="store_true",
        help="跳过 chunk 已为目标维度的资源（增量修复上次失败的少数几条）",
    )
    parser.add_argument(
        "--corpus-only",
        action="store_true",
        help="只处理正式语料（source_url 以 local://library/knowledge/ 开头）",
    )
    args = parser.parse_args()

    ok, failed = asyncio.run(
        reindex(
            limit=args.limit,
            all_status=args.all_status,
            dry_run=args.dry_run,
            skip_up_to_date=args.skip_up_to_date,
            corpus_only=args.corpus_only,
        )
    )
    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
