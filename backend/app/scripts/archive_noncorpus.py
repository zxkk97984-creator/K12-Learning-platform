"""DB 数据治理归档：软归档非语料内容（CLI，幂等）。

对照 backend/data/library/manifest.json（25 本正式书）与 knowledge/*.md（56 篇
知识文档），把线上库中「非正式语料」的内容归档/标记：

- books：非 25 本正式书 → status='ARCHIVED'（软删，保留全部 FK/历史）。
- knowledge_resources：非 56 篇语料 `local://library/knowledge/*` → status='FAILED'
  + error='archived: test data'（不再进入 RAG；chunks 保留以维持 FK 完整）。

正式语料内容保持 READY / PUBLISHED 不变。

Usage:
    uv run python -m app.scripts.archive_noncorpus --dry-run   # 先预览
    uv run python -m app.scripts.archive_noncorpus             # 执行归档
"""

import argparse
import asyncio
import uuid
from pathlib import Path

from sqlalchemy import text

from app.infrastructure.database.engine import engine

LIB_ROOT = Path(__file__).parent.parent.parent / "data" / "library"
MANIFEST = LIB_ROOT / "manifest.json"


def _book_id(slug: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"shuangling:library:book:{slug}")


def real_book_ids() -> list[str]:
    manifest = json_manifest()
    return [str(_book_id(item["slug"])) for item in manifest["books"]]


def json_manifest():
    import json

    return json.loads(MANIFEST.read_text(encoding="utf-8"))


async def go(dry_run: bool) -> None:
    real_ids = real_book_ids()
    real_ids_set = {uuid.UUID(rid) for rid in real_ids}
    now = "now()"
    # 确定性 UUID（uuid5 十六进制）只含合法字符，安全用于内联 IN 列表。
    real_in = ",".join(f"'{rid}'::uuid" for rid in real_ids)

    async with engine.begin() as conn:
        # ---- 知识资源：保留 56 篇语料，其余标记 FAILED ----
        noncorpus_res = (
            await conn.execute(
                text(
                    "select resource_id, source_name, status from knowledge_resources "
                    "where source_url not like 'local://library/knowledge/%'"
                )
            )
        ).all()
        print(
            f"[知识资源] 非语料 {len(noncorpus_res)} 条待标记 "
            f"({sum(1 for r in noncorpus_res if r.status=='READY')} READY + "
            f"{sum(1 for r in noncorpus_res if r.status=='FAILED')} FAILED)"
        )
        if not dry_run:
            await conn.execute(
                text(
                    "update knowledge_resources set status='FAILED', "
                    "error='archived: test data', updated_at=now() "
                    "where source_url not like 'local://library/knowledge/%'"
                )
            )

        # ---- 书籍：保留 manifest 命中，其余 ARCHIVED ----
        # 排除测试夹具书：测试用固定确定性 UUID（如 5e3f0000-… / 5e300000-…）
        # 在库中捏造的 PUBLISHED 书，归档会让依赖它们的测试失效。
        book_ctx = (
            await conn.execute(
                text(
                    "select book_id, title, status from books "
                    f"where status != 'ARCHIVED' and book_id not in ({real_in}) "
                    "and book_id::text not like '5e3%0000%'"
                )
            )
        ).all()
        print(
            f"[书籍] 非语料待归档 {len(book_ctx)} 本 "
            f"({sum(1 for b in book_ctx if b.status=='PUBLISHED')} PUBLISHED + "
            f"{sum(1 for b in book_ctx if b.status=='DRAFT')} DRAFT)"
        )
        if not dry_run:
            await conn.execute(
                text(
                    "update books set status='ARCHIVED', published_at=NULL "
                    f"where status != 'ARCHIVED' and book_id not in ({real_in}) "
                    "and book_id::text not like '5e3%0000%'"
                )
            )
        print("dry-run，未写入" if dry_run else "完成归档")


def main() -> None:
    parser = argparse.ArgumentParser(description="归档非语料内容")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不写入")
    args = parser.parse_args()
    asyncio.run(go(args.dry_run))


if __name__ == "__main__":
    main()
