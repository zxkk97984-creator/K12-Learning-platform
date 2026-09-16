# 内容验收 · 章节评测题（T22a）记录

> 本任务为三本样书的第一章生成了**可审查的题目集数据资产**（`backend/data/library/assessments/<slug>/ch01.json`）。
> **尚未接入运行时选题逻辑**——这属于后续独立步骤。
> 以下题目均为**代理（agent）生成，未经人工审校**：审校记录的具体人与日期为**空**，`review_status: DRAFT`，`reviewed_by: null`。未经人工审核，不得据此对外宣称「已审校」或直接投入使用。

## 学习目标（各书第一章，动词化）

- **ml-how-machines-learn**：学完这一章，你将能够说出监督、无监督、强化三种学习方式各自的训练信号，并判断一个具体任务该归入哪一类。
- **ai-not-magic-junior**：学完这一章，你将能够区分规则程序与学习程序这两种路线，并用自己的话讲清模型训练「猜测—对照—调整」的循环。
- **ai-primary-fun**：学完这一章，你将能够说出「AI 是人写的、靠例子学的、是帮手不是魔法师」这三句话。

## 各书题目清单

### ml-how-machines-learn · ch01（5 题）

| key | 类型 | 难度 | 知识点 | 题干（要点） | 正确答案 | 解析要点 |
|---|---|---|---|---|---|---|
| ...-q01 | 单选 | EASY | supervised-learning | 区分学习方式的关键依据 | A（是否有人标注的标准答案） | 三种方式按「有没有答案、有没有反馈」划分 |
| ...-q02 | 单选 | MEDIUM | reinforcement-learning | 自动驾驶变道试错、奖惩反馈 | C（强化学习） | 智能体靠奖励/惩罚调整策略 |
| ...-q03 | 判断 | MEDIUM | reinforcement-learning | 强化学习需先备好「输入-答案」标注数据 | 错误（B） | 强化学习给奖励信号，非标注答案 |
| ...-q04 | 多选 | HARD | unsupervised-learning | 哪些任务适合无监督 | A、C（分群组/聚话题簇） | 聚类属无监督；分类/识别靠标注属监督 |
| ...-q05 | 填空 | EASY | unsupervised-learning | 无监督学习最典型任务是____ | 聚类 | 把相似样本聚成簇 |

### ai-not-magic-junior · ch01（4 题）

| key | 类型 | 难度 | 知识点 | 题干（要点） | 正确答案 | 解析要点 |
|---|---|---|---|---|---|---|
| ...-q01 | 单选 | EASY | model-training | 模型训练核心循环 | B（猜测→对照→调整） | 对照误差、反复微调、准确率爬坡 |
| ...-q02 | 单选 | MEDIUM | model-training | 规则被「中獎+表情」绕过说明什么 | C（规则认死写法易失灵） | 只匹配写死条件，缺乏概括能力 |
| ...-q03 | 判断 | MEDIUM | model-training | 训练例题答得好=真学会 | 错误（B） | 须用从没见过的数据测泛化能力 |
| ...-q04 | 单选 | HARD | model-training | 旧照片准、新照片错说明什么 | A（可能在背题、未泛化） | 泛化要用新数据检验 |

### ai-primary-fun · ch01（4 题）

| key | 类型 | 难度 | 知识点 | 题干（要点） | 正确答案 | 解析要点 |
|---|---|---|---|---|---|---|
| ...-q01 | 单选 | EASY | ai-as-helper | AI 是什么 | A（人写的一段段电脑程序） | 非电影机器人、非魔法 |
| ...-q02 | 单选 | EASY | ai-as-helper | 教 AI 认猫的方法 | A（看成千上万张猫片找共同特点） | 靠例子学 |
| ...-q03 | 判断 | EASY | ai-as-helper | AI 不要人指挥、想干嘛干嘛 | 错误（B） | 是帮手不是魔法师，需人指挥 |
| ...-q04 | 多选 | MEDIUM | ai-as-helper | 哪些说法对 | A、C（例子外会发懵/例子越多越准） | 有局限、会出错、非万能 |

每书均满足：≥1 概念理解题、≥1 情境/应用题、≥1 常见误解辨析题；干扰项为常见误解而非随机词。

## 审校状态

- 三书所有题目 `review_status: DRAFT`，`reviewed_by: null`，`reviewed_at: null`。
- **未人工审校：审校记录具体人/日期为空（或为 null）。**
- 本产品数据/内容均由代理编写，未经真实讲师、内容专家或编辑人工复核，准入前必须补充人工审校环节。

## 22b 运行接入状态

- 已新增 `reviewed_questions` 模型 + 迁移（`a7b8c9d0e1f2`）、`import_assessments.py` 导入器（按 `stable_key` 幂等 upsert）、`select_reviewed_questions` 选择器（仅 `review_status='APPROVED'` 且年级匹配的题会被选中）、`QuizSkill` 集成（章节测验优先审校题，来源如实标注 `generation=reviewed/stale_key=...`）。
- **诚实归属**：三书题源当前 `review_status=DRAFT`、`reviewed_by=null`，故 `select_reviewed_questions` 目前返回空 → 章节测验**不会**选出任何未经审校的题（未审校题不能被选出），仍走既有 LLM/确定性/题库路径并如实标注来源。审校题**未**顶替运行时出题。
- 导入两次数量不翻倍（`stable_key` 唯一约束 + 幂等 upsert）；改题后旧 `quiz_sessions.questions_snapshot` 保存原文（快照不可变，不被覆盖）。
- 数据资产（题源 JSON）由 agent 创作，**未经人工审校**；审校签署（具体人/日期/问题）属外部验收，如实列为待外部。
