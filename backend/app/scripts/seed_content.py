"""幂等内容种子：12 本书 + b1 章节 + b1 第 3 章正文 + 知识点。

数据来源（3-C 快照，不得与前端 mock / 原型漂移）：
- 12 本书：frontend/src/mocks/data/books.ts（b1~b12 的 title/grade/minutes/topic/keywords）
- b1 章节目录：prototypes/shuangling-v3-prototype.html #view-reader 本章目录（5 章）
- b1 第 3 章正文：原型 reader 正文 data-read-section 锚点（与前端 mockContentBlocks 一致）
- 知识点：原型 context-rail「特征 · 标签 · 规律」+ 前端 mockKnowledgePoints

用法：uv run python -m app.scripts.seed_content
"""

import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid5, NAMESPACE_URL

from sqlalchemy import select

from app.infrastructure.database.engine import engine
from app.infrastructure.database.models import (
    Book,
    Chapter,
    ContentBlock,
    KnowledgePoint,
)
from app.infrastructure.database.session import async_session


def _uuid(key: str) -> UUID:
    """确定性 UUID：重复运行 seed 得到相同主键，天然幂等。"""
    return uuid5(NAMESPACE_URL, f"shuangling:{key}")


def _book_id(no: str) -> UUID:
    return _uuid(f"book:{no}")


def _chapter_id(no: str, order: int) -> UUID:
    return _uuid(f"chapter:{no}:{order}")


def _block_id(no: str, order: int) -> UUID:
    return _uuid(f"block:{no}:{order}")


def _kp_id(slug: str) -> UUID:
    return _uuid(f"kp:{slug}")


# 12 本书（来源：frontend/src/mocks/data/books.ts；keywords 保留在 tags[1]，topic 在 tags[0]）
BOOKS: list[dict] = [
    {
        "no": "01",
        "title": "AI 不是魔法",
        "description": "从推荐系统、训练数据到算法公平，建立一张看懂 AI 的地图。",
        "grade_min": 7,
        "grade_max": 9,
        "minutes": 90,
        "topic": "AI 基础",
        "keywords": "训练数据 · 标签 · 算法",
    },
    {
        "no": "02",
        "title": "机器人会怎么想？",
        "description": "用真实案例理解感知、决策和行动之间的关系。",
        "grade_min": 7,
        "grade_max": 9,
        "minutes": 65,
        "topic": "机器人",
        "keywords": "感知 · 决策 · 行动",
    },
    {
        "no": "03",
        "title": "和算法相处",
        "description": "当算法参与选择，我们怎样保留自己的判断？",
        "grade_min": 7,
        "grade_max": 9,
        "minutes": 70,
        "topic": "数字素养",
        "keywords": "选择 · 判断 · 公平",
    },
    {
        "no": "04",
        "title": "数据会说话吗？",
        "description": "从数据、图表到结论，学会看懂数字背后的信息。",
        "grade_min": 7,
        "grade_max": 9,
        "minutes": 40,
        "topic": "数据",
        "keywords": "数据 · 图表 · 结论",
    },
    {
        "no": "05",
        "title": "让代码动起来",
        "description": "从第一行代码开始，理解编程、逻辑与循环。",
        "grade_min": 7,
        "grade_max": 9,
        "minutes": 95,
        "topic": "编程",
        "keywords": "编程 · 逻辑 · 循环",
    },
    {
        "no": "06",
        "title": "机器如何理解语言",
        "description": "从语言、模型到上下文，看机器如何读懂文字。",
        "grade_min": 10,
        "grade_max": 12,
        "minutes": 75,
        "topic": "AI 基础",
        "keywords": "语言 · 模型 · 上下文",
    },
    {
        "no": "07",
        "title": "和未来一起学习",
        "description": "面向未来的工具与协作方式。",
        "grade_min": 10,
        "grade_max": 12,
        "minutes": 60,
        "topic": "数字素养",
        "keywords": "未来 · 工具 · 协作",
    },
    {
        "no": "08",
        "title": "你好，机器人",
        "description": "用故事和动手实验认识机器人。",
        "grade_min": 1,
        "grade_max": 6,
        "minutes": 35,
        "topic": "机器人",
        "keywords": "机器人 · 故事 · 动手",
    },
    {
        "no": "09",
        "title": "会思考的盒子",
        "description": "通过类比和小实验理解 AI。",
        "grade_min": 1,
        "grade_max": 6,
        "minutes": 40,
        "topic": "AI 基础",
        "keywords": "AI · 类比 · 小实验",
    },
    {
        "no": "10",
        "title": "数据是什么颜色？",
        "description": "用颜色和分类认识数据。",
        "grade_min": 1,
        "grade_max": 6,
        "minutes": 30,
        "topic": "数据",
        "keywords": "数据 · 颜色 · 分类",
    },
    {
        "no": "11",
        "title": "算法与偏见",
        "description": "探讨偏见、公平与责任。",
        "grade_min": 10,
        "grade_max": 12,
        "minutes": 85,
        "topic": "AI 伦理",
        "keywords": "偏见 · 公平 · 责任",
    },
    {
        "no": "12",
        "title": "自己动手训练 AI",
        "description": "从训练到数据，亲手实践一次 AI 训练。",
        "grade_min": 10,
        "grade_max": 12,
        "minutes": 100,
        "topic": "编程",
        "keywords": "训练 · 数据 · 实战",
    },
]

# b1 章节目录（来源：原型 reader 本章目录，共 5 章；前端 mock chapter_count=7 的差异见 Report）
B1_CHAPTERS: list[tuple[int, str, int]] = [
    (1, "从“会回答”开始", 13),
    (2, "推荐系统看见了什么", 13),
    (3, "训练数据", 13),
    (4, "算法偏见", 13),
    (5, "让判断回到人手里", 13),
]

PLACEHOLDER_CHAPTER_TITLE = "全书导览"
PLACEHOLDER_CHAPTER_SUMMARY = "占位章节：本书章节明细待后续内容任务补充（3-C 仅保证《AI 不是魔法》第 3 章有完整正文）。"

# 知识点（来源：原型 context-rail + 前端 mockKnowledgePoints；新增「规律」来自 context-rail）
KNOWLEDGE_POINTS: list[dict] = [
    {
        "slug": "training_data",
        "name": "训练数据",
        "description": "训练数据是一组用来帮助机器发现规律的例子。",
        "topic": "AI 基础",
        "parent": None,
    },
    {
        "slug": "feature",
        "name": "特征",
        "description": "机器看到的内容。",
        "topic": "AI 基础",
        "parent": "training_data",
    },
    {
        "slug": "label",
        "name": "标签",
        "description": "我们希望机器学会的答案。",
        "topic": "AI 基础",
        "parent": "training_data",
    },
    {
        "slug": "pattern",
        "name": "规律",
        "description": "从例子中反复出现、可以帮助机器做出预测的关系。",
        "topic": "AI 基础",
        "parent": "training_data",
    },
    {
        "slug": "algorithm_bias",
        "name": "算法偏见",
        "description": "算法基于不完整例子学到的规律可能带来的判断偏差。",
        "topic": "AI 伦理",
        "parent": None,
    },
]

# b1 第 3 章正文（来源：原型 reader 正文 data-read-section；与前端 mockContentBlocks 一致）
CH3_BLOCKS: list[dict] = [
    {
        "order": 1,
        "block_type": "PARAGRAPH",
        "content": {
            "text": "想象你在教一只小狗认识“球”。你不会只说一次“这是球”，而是会拿出不同颜色、不同大小、不同材质的球，让它一次次看到：这些东西虽然长得不完全一样，但有一些共同的特征。"
        },
        "section_key": "训练数据 · 导入",
        "kps": ["training_data"],
    },
    {
        "order": 2,
        "block_type": "PARAGRAPH",
        "content": {
            "text": "机器学习里的训练数据，就像这些被反复展示的例子。它们通常包含“机器看到的内容”和“我们希望它学会的答案”，也就是特征和标签。",
            "mark": "训练数据",
        },
        "section_key": "训练数据 · 定义",
        "kps": ["training_data", "feature", "label"],
    },
    {
        "order": 3,
        "block_type": "KNOWLEDGE_CARD",
        "content": {
            "title": "训练数据",
            "text": "训练数据是一组用来帮助机器发现规律的例子。例子越能代表真实世界，机器之后遇到新情况时，越可能做出合适的判断。",
            "example": {
                "label": "生活里的例子",
                "text": "给音乐推荐系统看你喜欢过的歌曲，它就能尝试猜测下一首你可能想听什么。",
            },
        },
        "section_key": "知识卡片 · 训练数据",
        "kps": ["training_data", "pattern"],
    },
    {
        "order": 4,
        "block_type": "FIGURE",
        "content": {
            "aria_label": "训练数据三个角色图解",
            "caption": "训练数据的三个角色：例子 → 规律 → 预测",
        },
        "section_key": "图解 · 训练数据的三个角色",
        "kps": [],
    },
    {
        "order": 5,
        "block_type": "CALLOUT",
        "content": {
            "title": "想一想",
            "text": "如果例子只有一种情况，机器学到的规律会怎样？下一节「算法偏见」会给你答案。",
        },
        "section_key": "想一想",
        "kps": ["algorithm_bias"],
    },
    {
        "order": 6,
        "block_type": "PARAGRAPH",
        "content": {
            "text": "但“看过很多例子”不等于“永远不会出错”。如果例子只来自一种情况，机器学到的规律也可能变得狭窄。"
        },
        "section_key": "小结",
        "kps": ["training_data"],
    },
]


async def ensure_knowledge_points(session) -> dict[str, KnowledgePoint]:
    rows: dict[str, KnowledgePoint] = {}
    # 第一遍：全部以 parent_id=None 创建，避免自引用 FK 依赖顺序
    for item in KNOWLEDGE_POINTS:
        row = (
            await session.execute(select(KnowledgePoint).where(KnowledgePoint.slug == item["slug"]))
        ).scalar_one_or_none()
        if row is None:
            row = KnowledgePoint(
                knowledge_point_id=_kp_id(item["slug"]),
                name=item["name"],
                slug=item["slug"],
                description=item["description"],
                topic=item["topic"],
                parent_id=None,
                status="ACTIVE",
            )
            session.add(row)
        else:
            # 收敛式幂等：已有行补全/校正为权威值
            row.name = item["name"]
            row.description = item["description"]
            row.topic = item["topic"]
            row.status = "ACTIVE"
        rows[item["slug"]] = row
    await session.flush()
    # 第二遍：父节点已落库，再补 parent_id
    for item in KNOWLEDGE_POINTS:
        if item["parent"]:
            rows[item["slug"]].parent_id = rows[item["parent"]].knowledge_point_id
    await session.flush()
    return rows


async def ensure_books(session) -> dict[str, Book]:
    rows: dict[str, Book] = {}
    for item in BOOKS:
        row = (
            await session.execute(select(Book).where(Book.title == item["title"]))
        ).scalar_one_or_none()
        if row is None:
            row = Book(
                book_id=_book_id(item["no"]),
                title=item["title"],
                description=item["description"],
                grade_min=item["grade_min"],
                grade_max=item["grade_max"],
                difficulty="MEDIUM",
                estimated_minutes=item["minutes"],
                tags=[item["topic"], item["keywords"]],
                source_ids=[],
                status="PUBLISHED",
                published_at=datetime.now(timezone.utc),
            )
            session.add(row)
        else:
            # 收敛式幂等：已有行（如 3-A 验证时手插的行）补全/校正
            row.description = item["description"]
            row.grade_min = item["grade_min"]
            row.grade_max = item["grade_max"]
            row.difficulty = "MEDIUM"
            row.estimated_minutes = item["minutes"]
            row.tags = [item["topic"], item["keywords"]]
            row.status = "PUBLISHED"
            if row.published_at is None:
                row.published_at = datetime.now(timezone.utc)
        rows[item["no"]] = row
    await session.flush()
    return rows


async def ensure_chapters(session, books: dict[str, Book]) -> dict[str, Chapter]:
    rows: dict[str, Chapter] = {}
    for order, title, minutes in B1_CHAPTERS:
        book = books["01"]
        row = (
            await session.execute(
                select(Chapter).where(
                    Chapter.book_id == book.book_id,
                    Chapter.chapter_order == order,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = Chapter(
                chapter_id=_chapter_id("01", order),
                book_id=book.book_id,
                title=title,
                chapter_order=order,
                summary=None,
                estimated_minutes=minutes,
                status="PUBLISHED",
            )
            session.add(row)
        else:
            # 收敛式幂等：标题/时长/状态对齐权威目录
            row.title = title
            row.summary = None
            row.estimated_minutes = minutes
            row.status = "PUBLISHED"
        rows[f"01:{order}"] = row
    # 其余 11 本书：每本 1 个占位章节（0-D 允许；保证书库可进入阅读器演示）
    for no in ("02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"):
        book = books[no]
        row = (
            await session.execute(
                select(Chapter).where(
                    Chapter.book_id == book.book_id,
                    Chapter.chapter_order == 1,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = Chapter(
                chapter_id=_chapter_id(no, 1),
                book_id=book.book_id,
                title=PLACEHOLDER_CHAPTER_TITLE,
                chapter_order=1,
                summary=PLACEHOLDER_CHAPTER_SUMMARY,
                estimated_minutes=5,
                status="PUBLISHED",
            )
            session.add(row)
        else:
            row.title = PLACEHOLDER_CHAPTER_TITLE
            row.summary = PLACEHOLDER_CHAPTER_SUMMARY
            row.estimated_minutes = 5
            row.status = "PUBLISHED"
        rows[f"{no}:1"] = row
    await session.flush()
    return rows


async def ensure_ch3_blocks(
    session,
    chapters: dict[str, Chapter],
    kps: dict[str, KnowledgePoint],
) -> None:
    ch3 = chapters["01:3"]
    for item in CH3_BLOCKS:
        row = (
            await session.execute(
                select(ContentBlock).where(
                    ContentBlock.chapter_id == ch3.chapter_id,
                    ContentBlock.block_order == item["order"],
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = ContentBlock(
                block_id=_block_id("01-3", item["order"]),
                chapter_id=ch3.chapter_id,
                block_type=item["block_type"],
                content=item["content"],
                block_order=item["order"],
                section_key=item["section_key"],
                knowledge_point_ids=[str(kps[slug].knowledge_point_id) for slug in item["kps"]],
            )
            session.add(row)
        else:
            # 收敛式幂等：正文/锚点/知识点引用对齐原型
            row.block_type = item["block_type"]
            row.content = item["content"]
            row.section_key = item["section_key"]
            row.knowledge_point_ids = [
                str(kps[slug].knowledge_point_id) for slug in item["kps"]
            ]
    await session.flush()


async def seed() -> None:
    try:
        async with async_session() as session:
            kps = await ensure_knowledge_points(session)
            books = await ensure_books(session)
            chapters = await ensure_chapters(session, books)
            await ensure_ch3_blocks(session, chapters, kps)
            await session.commit()
            print(
                f"seed_content: 就绪 books={len(books)} kps={len(kps)} "
                f"chapters={len(chapters)} ch3_blocks={len(CH3_BLOCKS)}"
            )
    finally:
        # 释放连接池，避免跨事件循环复用 asyncpg 连接（asyncio.run / TestClient 场景）
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
