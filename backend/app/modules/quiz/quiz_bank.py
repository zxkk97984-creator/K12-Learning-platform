from dataclasses import dataclass


@dataclass(frozen=True)
class QuizBankQuestion:
    bank_id: str
    difficulty: str
    question_type: str
    stem: str
    options: list[dict[str, str]]
    correct_answer: dict[str, object]
    explanation: str
    hints: tuple[str, str, str]
    knowledge_point_ids: tuple[str, ...]


QUIZ_BANK: tuple[QuizBankQuestion, ...] = (
    QuizBankQuestion(
        bank_id="training-data-purpose",
        difficulty="MEDIUM",
        question_type="SINGLE_CHOICE",
        stem="训练数据最重要的作用是什么？",
        options=[
            {"key": "A", "text": "只要数据越多，结果就一定正确"},
            {"key": "B", "text": "让机器从例子中发现可重复的规律"},
            {"key": "C", "text": "让机器不需要再看新的内容"},
            {"key": "D", "text": "让机器不用验证就直接做决定"},
        ],
        correct_answer={"key": "B"},
        explanation="训练数据的价值，不是数量本身，而是帮助机器发现可重复的规律。",
        hints=(
            "先想想：训练数据是让机器背答案，还是让机器从例子中找规律？",
            "把训练数据想成你教小狗认识球时反复展示的那些例子。",
            "选出那个描述“从例子里发现可重复规律”的选项。",
        ),
        knowledge_point_ids=("training_data",),
    ),
    QuizBankQuestion(
        bank_id="training-data-examples",
        difficulty="MEDIUM",
        question_type="TRUE_FALSE",
        stem="训练数据可以包含文字、图片或数字等不同形式的例子。",
        options=[{"key": "TRUE", "text": "正确"}, {"key": "FALSE", "text": "错误"}],
        correct_answer={"key": "TRUE"},
        explanation="不同任务可以使用不同形式的数据，关键是数据能表达要学习的规律。",
        hints=(
            "想想看：机器学习只能处理文字吗？",
            "图片识别和数字预测也需要训练数据。",
            "选择“正确”。",
        ),
        knowledge_point_ids=("training_data",),
    ),
    QuizBankQuestion(
        bank_id="labels-and-examples",
        difficulty="EASY",
        question_type="SINGLE_CHOICE",
        stem="在监督学习里，标签通常表示什么？",
        options=[
            {"key": "A", "text": "数据的颜色"},
            {"key": "B", "text": "我们希望机器学会的答案"},
            {"key": "C", "text": "模型运行的时间"},
            {"key": "D", "text": "电脑的品牌"},
        ],
        correct_answer={"key": "B"},
        explanation="标签是训练例子对应的目标答案，帮助模型知道应该学会什么。",
        hints=(
            "标签像是例子旁边写好的参考答案。",
            "它不是数据的颜色，而是要预测的目标。",
            "选择“我们希望机器学会的答案”。",
        ),
        knowledge_point_ids=("labels",),
    ),
    QuizBankQuestion(
        bank_id="data-volume-guarantee",
        difficulty="HARD",
        question_type="TRUE_FALSE",
        stem="只要训练数据足够多，模型的结果就一定正确。",
        options=[{"key": "TRUE", "text": "正确"}, {"key": "FALSE", "text": "错误"}],
        correct_answer={"key": "FALSE"},
        explanation="数据还要有代表性、质量和合适的标注，数量多不等于结果一定正确。",
        hints=(
            "多并不总是好，想想重复或错误的例子。",
            "数据质量和代表性同样重要。",
            "选择“错误”。",
        ),
        knowledge_point_ids=("data_quality",),
    ),
    QuizBankQuestion(
        bank_id="good-training-data",
        difficulty="EASY",
        question_type="MULTIPLE_CHOICE",
        stem="哪些做法有助于准备更好的训练数据？",
        options=[
            {"key": "A", "text": "覆盖真实使用场景"},
            {"key": "B", "text": "忽略明显错误的样本"},
            {"key": "C", "text": "检查标签是否一致"},
            {"key": "D", "text": "只保留一种情况"},
        ],
        correct_answer={"keys": ["A", "C"]},
        explanation="代表性和一致的标签能让模型更容易学到稳定规律。",
        hints=(
            "先找和真实使用、数据质量有关的做法。",
            "错误样本不能被忽略，标签也需要检查。",
            "选择 A 和 C。",
        ),
        knowledge_point_ids=("data_quality",),
    ),
    QuizBankQuestion(
        bank_id="model-generalization",
        difficulty="MEDIUM",
        question_type="FILL_BLANK",
        stem="模型从训练数据中发现并用于新问题的是____。",
        options=[],
        correct_answer={"value": "规律"},
        explanation="模型学习的是例子背后的规律，并尝试把规律用于新的问题。",
        hints=(
            "不是把每个答案原封不动地背下来。",
            "训练数据让模型发现可重复的东西。",
            "答案是“规律”。",
        ),
        knowledge_point_ids=("generalization",),
    ),
    QuizBankQuestion(
        bank_id="validation-purpose",
        difficulty="HARD",
        question_type="SINGLE_CHOICE",
        stem="为什么要用没有参与训练的新数据检查模型？",
        options=[
            {"key": "A", "text": "让模型记住更多训练例子"},
            {"key": "B", "text": "让电脑运行得更快"},
            {"key": "C", "text": "观察模型能否把规律用于新情况"},
            {"key": "D", "text": "减少数据的数量"},
        ],
        correct_answer={"key": "C"},
        explanation="新数据能帮助我们观察模型是否真正学到规律，而不是只记住训练例子。",
        hints=(
            "检查不能只拿原来的练习题。",
            "关键是看看模型面对新情况时表现如何。",
            "选择“观察模型能否把规律用于新情况”。",
        ),
        knowledge_point_ids=("generalization",),
    ),
    QuizBankQuestion(
        bank_id="bias-awareness",
        difficulty="EASY",
        question_type="TRUE_FALSE",
        stem="如果训练数据只代表一种情况，模型面对其他情况也一定公平。",
        options=[{"key": "TRUE", "text": "正确"}, {"key": "FALSE", "text": "错误"}],
        correct_answer={"key": "FALSE"},
        explanation="训练数据覆盖不足可能让模型在其他情况上表现不稳定或不公平。",
        hints=(
            "只看一种情况，能代表所有人吗？",
            "代表性不足会带来偏差。",
            "选择“错误”。",
        ),
        knowledge_point_ids=("data_bias",),
    ),
)


def select_questions(difficulty: str, count: int) -> list[QuizBankQuestion]:
    """Prefer the requested difficulty, then fill deterministically from the bank."""
    preferred = [item for item in QUIZ_BANK if item.difficulty == difficulty]
    remaining = [item for item in QUIZ_BANK if item.difficulty != difficulty]
    ordered = preferred + remaining
    return [ordered[index % len(ordered)] for index in range(count)]


from dataclasses import dataclass as _dataclass  # noqa: E402
from uuid import UUID as _UUID  # noqa: E402
from typing import Any as _Any  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession  # noqa: E402
from sqlalchemy import select as _select  # noqa: E402


@_dataclass(frozen=True)
class ReviewedQuestionItem:
    """从 reviewed_questions（仅 APPROVED）导出的可出题项，供 QuizSkill 消费。"""

    stable_key: str
    question_type: str
    stem: str
    options: list[dict[str, str]]
    correct_answer: dict[str, _Any]
    explanation: str
    hints: tuple[str, str, str]
    knowledge_point_ids: tuple[str, ...]
    grade_min: int
    grade_max: int
    review_status: str


async def select_reviewed_questions(
    session: _AsyncSession,
    chapter_id: _UUID,
    grade: int | None,
    count: int,
) -> list[ReviewedQuestionItem]:
    """选取当前章节、适配年级的 APPROVED 审校题（T22b）。

    仅 review_status='APPROVED' 的题才会被选中；年级按 grade_min/grade_max 相交匹配。
    返回空列表表示当前章节无可用审校题，调用方走原有的 LLM/确定性/题库路径（如实标注来源）。
    """
    from app.infrastructure.database.models import ReviewedQuestion

    stmt = _select(ReviewedQuestion).where(
        ReviewedQuestion.chapter_id == chapter_id,
        ReviewedQuestion.review_status == "APPROVED",
    )
    if grade is not None:
        stmt = stmt.where(
            ReviewedQuestion.grade_min <= grade,
            ReviewedQuestion.grade_max >= grade,
        )
    stmt = stmt.order_by(ReviewedQuestion.stable_key.asc())
    rows = (await session.execute(stmt)).scalars().all()
    items: list[ReviewedQuestionItem] = []
    for row in rows[:count]:
        payload = row.payload or {}
        options = list(payload.get("options") or [])
        correct = dict(payload.get("correct_answer") or {})
        hints = tuple(payload.get("hints") or ("", "", ""))[:3]
        kps = tuple(str(kp) for kp in payload.get("knowledge_point_ids") or ())
        items.append(
            ReviewedQuestionItem(
                stable_key=row.stable_key,
                question_type=str(payload.get("question_type") or "SINGLE_CHOICE"),
                stem=str(payload.get("stem") or ""),
                options=options,
                correct_answer=correct,
                explanation=str(payload.get("explanation") or ""),
                hints=hints,
                knowledge_point_ids=kps,
                grade_min=row.grade_min,
                grade_max=row.grade_max,
                review_status=row.review_status,
            )
        )
    return items
