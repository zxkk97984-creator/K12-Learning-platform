"""Ingest Markdown/TXT knowledge resources (Phase 8, CLI).

Usage:
    uv run python -m app.scripts.ingest_knowledge --file path.md \
        --source-name "AI 不是魔法 · 第3章" --source-url "https://demo/ai-ch3"
    uv run python -m app.scripts.ingest_knowledge --seed
"""

import argparse
import asyncio
from pathlib import Path

from sqlalchemy import select

from app.infrastructure.database.engine import engine
from app.infrastructure.database.models import User
from app.infrastructure.database.session import async_session
from app.modules.identity.security import hash_password
from app.modules.knowledge.ingestion import ingest_text

SEED_DIR = Path(__file__).parent / "knowledge_seed"
DEFAULT_LICENSE = "CC-BY-4.0"
DEFAULT_COPYRIGHT = "示例资源仅本地演示"


async def ensure_admin() -> None:
    async with async_session() as session:
        admin = (
            await session.execute(select(User).where(User.username == "admin"))
        ).scalar_one_or_none()
        if admin is None:
            session.add(
                User(
                    username="admin",
                    password_hash=hash_password("admin123"),
                    user_type="ADMIN",
                )
            )
            await session.commit()
            print("ingest_knowledge: 已创建 admin 演示账号（admin / admin123）")


async def ingest_one(
    path: Path,
    *,
    source_name: str,
    source_url: str,
    license: str,
    copyright_status: str,
    author: str | None,
) -> None:
    text = path.read_text(encoding="utf-8")
    async with async_session() as session:
        resource_id, chunk_count = await ingest_text(
            session,
            text=text,
            source_name=source_name,
            source_url=source_url,
            license=license,
            copyright_status=copyright_status,
            author=author,
        )
        print(
            f"ingest_knowledge: resource={resource_id} chunks={chunk_count} "
            f"source={source_name}"
        )


async def run(args: argparse.Namespace) -> None:
    await ensure_admin()
    if args.seed:
        for path in sorted(SEED_DIR.glob("*.md")):
            await ingest_one(
                path,
                source_name=path.stem,
                source_url=f"https://demo.shuangling.local/knowledge/{path.stem}",
                license=args.license,
                copyright_status=args.copyright,
                author=args.author,
            )
        return
    if args.directory:
        for path in sorted(Path(args.directory).glob("*.md")) + sorted(
            Path(args.directory).glob("*.txt")
        ):
            await ingest_one(
                path,
                source_name=path.stem,
                source_url=f"https://demo.shuangling.local/knowledge/{path.stem}",
                license=args.license,
                copyright_status=args.copyright,
                author=args.author,
            )
        return
    if not args.file:
        raise SystemExit("需要 --file / --directory / --seed 之一")
    path = Path(args.file)
    await ingest_one(
        path,
        source_name=args.source_name or path.stem,
        source_url=args.source_url,
        license=args.license,
        copyright_status=args.copyright,
        author=args.author,
    )
    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Knowledge ingestion CLI")
    parser.add_argument("--file", help="Markdown/TXT file path")
    parser.add_argument("--directory", help="directory containing md/txt files")
    parser.add_argument("--seed", action="store_true", help="ingest bundled demo docs")
    parser.add_argument("--source-name", default=None)
    parser.add_argument("--source-url", default=None)
    parser.add_argument("--license", default=DEFAULT_LICENSE)
    parser.add_argument("--copyright", default=DEFAULT_COPYRIGHT)
    parser.add_argument("--author", default=None)
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
