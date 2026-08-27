"""DB 数据治理预览：只读归类，不改动任何数据（CLI）。

对照 backend/data/library/manifest.json（25 本正式书）与 knowledge/*.md（56 篇知识
文档），把线上库的内容归类为「正式语料」与「测试/垃圾」两类，供归档前确认。

Usage:
    uv run python -m app.scripts.preview_data_governance
"""

import asyncio
import json
import uuid
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import text

from app.infrastructure.database.engine import engine

LIB_ROOT = Path(__file__).parent.parent.parent / "data" / "library"
MANIFEST = LIB_ROOT / "manifest.json"


def _uuid(namespace_text: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, namespace_text)


def _book_id(slug: str) -> uuid.UUID:
    return _uuid(f"shuangling:library:book:{slug}")


def load_corpus() -> tuple[set[uuid.UUID], set[str]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    real_book_ids = {_book_id(item["slug"]) for item in manifest["books"]}
    real_doc_slugs = {
        path.stem for path in (LIB_ROOT / "knowledge").glob("*.md")
    }
    return real_book_ids, real_doc_slugs


async def go() -> None:
    real_book_ids, real_doc_slugs = load_corpus()

    async with engine.connect() as conn:
        books = (
            await conn.execute(
                text(
                    "select book_id, title, status, source_ids from books "
                    "order by created_at asc"
                )
            )
        ).mappings().all()
        resources = (
            await conn.execute(
                text(
                    "select resource_id, source_name, source_url, status, "
                    "(select count(*) from knowledge_chunks kc where kc.resource_id = knowledge_resources.resource_id) as chunk_count "
                    "from knowledge_resources order by created_at asc"
                )
            )
        ).mappings().all()

    print(f"语料基线：正式书 {len(real_book_ids)} 本，知识文档 {len(real_doc_slugs)} 篇\n")
    print("=== 书籍（对 692 本）===")
    kept = archived = draft = published_noncorpus = 0
    for b in books:
        is_real = uuid.UUID(str(b["book_id"])) in real_book_ids
        st = b["status"]
        if is_real:
            kept += 1
        elif st == "ARCHIVED":
            archived += 1
        elif st == "DRAFT":
            draft += 1
        else:
            published_noncorpus += 1
    print(f"  [保留] 正式语料（manifest 命中）: {kept}")
    print(f"  [已归档] ARCHIVED（无需处理）: {archived}")
    print(f"  [候选归档] DRAFT（非正式书）: {draft}")
    print(f"  [候选归档] PUBLISHED 但非 manifest（测试/临时书）: {published_noncorpus}")

    print("\n=== 知识资源（对全部）===")
    real_res = garbage_ready = failed = 0
    for r in resources:
        st = r["status"]
        if st == "FAILED":
            failed += 1
            continue
        url = r["source_url"] or ""
        slug = Path(urlparse(url).path).stem
        is_real = slug in real_doc_slugs or str(r["source_url"]).startswith(
            "corpus://knowledge/"
        )
        if is_real:
            real_res += 1
        else:
            garbage_ready += 1
    print(f"  [保留] 正式语料文档: {real_res}")
    print(f"  [候选归档] READY 但非语料（测试上传）: {garbage_ready}")
    print(f"  [候选处置] FAILED（垃圾/失败）: {failed}")

    print("\n说明：本脚本只读，不做任何写入。归档规则待你确认后另行执行。")


if __name__ == "__main__":
    asyncio.run(go())
