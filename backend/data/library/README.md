# library/ — 文件语料库（内容生产 → 校验 → 导入 DB）

本目录是 K12 AI 通识学习平台的**内容源头**。所有书与知识库文档先以纯文件形式在这里生产、
用 `validate_library.py` 校验，再由 `import_library.py` 幂等导入数据库。
**禁止绕过管道直接写库。**

## 主题域边界

K12 AI 与计算通识：AI 基础、机器学习、机器人、编程（Python/Scratch）、数据素养、
算法思维、网络素养、AI 伦理。年级段：小学(1-6) / 初中(7-9) / 高中(10-12)，
语言深度必须匹配年级段（小学：具体生活比喻+短句；初中：通俗概念+少量代码；
高中：可引入术语与简单代码/伪代码）。

## 目录结构

```
library/
  README.md                       本文件（格式规范）
  manifest.json                   所有书的元数据索引
  books/<slug>/
    book.json                     单书元数据 + 章节清单 + knowledge_points 声明
    ch01.md ... chNN.md           章节正文（标记语法见下）
  knowledge/<slug>.md             知识库 RAG 文档（front matter + 正文）
```

`<slug>` 一律小写字母、数字、连字符（`[a-z0-9-]+`），全局唯一，冲突时加主题前缀。

## book.json 格式

```json
{
  "slug": "python-first-steps",
  "title": "Python 第一步：从打印到循环",
  "description": "一句话简介（30-60字）",
  "grade_min": 7, "grade_max": 9,
  "difficulty": "EASY",
  "estimated_minutes": 90,
  "author": null,
  "tags": ["编程", "入门"],
  "topic": "编程",
  "license": "CC-BY",
  "copyright_status": "原创",
  "knowledge_points": [
    {"slug": "loop", "name": "循环", "description": "一句话定义", "topic": "编程"}
  ],
  "chapters": [
    {"order": 1, "file": "ch01.md", "title": "你好，世界", "minutes": 14,
     "summary": "一句话章节简介"}
  ]
}
```

规则：

- `difficulty` 只能是 `EASY` / `MEDIUM` / `HARD`；
- 每本书 5~7 章；每章 `minutes` 8~25；
- `knowledge_points` 每本 4~8 个，`slug` 全局唯一，`@kp` 只能引用这里声明过的 slug；
- `status` 不写在文件里——导入器固定写 `PUBLISHED`；
- 新增书必须同步登记进 `manifest.json` 的 `books` 数组。

## 章节 Markdown 标记语法

行首标记，严格遵循；除下列行外**不允许出现任何其他非空行**：

```
<!-- meta
chapter_title: 你好，世界          ← 必须与 book.json 该章 title 一致
estimated_minutes: 14              ← 必须与该章 minutes 一致
summary: 一句话章节简介            ← 必须与该章 summary 一致
-->
T: 章节导语标题
P: 段落正文，60~240 字的生活化讲解。|mark:关键术语      ← |mark: 可省略；术语必须是正文的子串
KC: 卡片标题 :: 卡片定义正文（40~120字） :: 例子标签 :: 例子正文   ← 例子部分可整体省略
CALL: 标题 :: 引导思考的问题或过渡
FIG: 图解的无障碍描述 :: 图注文字
S: 小节锚点名                      ← 可选，之后的块归入该 section_key
@kp=training_data,label            ← 可选，作用于其上方最近的一个内容块
```

硬规则（校验器强制）：

1. 每章 ≥12 个内容块（T/P/KC/CALL/FIG 都算），其中 KC ≥2、CALL ≥1、FIG ≥1；
2. 每个 P 块正文 **60~240 个中文字符**；每个 KC 定义正文 **40~120 个中文字符**
   （中文字符数按 CJK 字符计，不含标点/英文/数字）；
3. 全书所有块正文合计 ≥6000 中文字符；
4. 禁止出现「占位」「待补充」「TODO」「例如等等」等字样；相邻两块正文不得重复；
5. `@kp=` 引用的 slug 必须在本书 `book.json` 的 `knowledge_points` 中声明过；
6. JSON / Markdown 解析失败即 FAIL；meta 与 book.json 不一致即 FAIL。

内容质量要求（人工抽查项）：

- 讲解节奏遵循 runoob 教程式四拍：**概念 → 为什么重要 → 生活化例子 → 动手想/试**；
- 语言匹配年级段；知识卡片是可独立背诵的定义；CALLOUT 是真实的引导问题；
- 章节之间有承接（上一章结尾 CALL 埋下一章引子）；
- 技术事实必须准确（语法、行为、报错信息等）。

## content JSON 形状（导入器负责转换，作者按语义写对即可）

| 标记 | block_type | content |
|------|------------|---------|
| T    | TITLE         | `{"text": "..."}` |
| P    | PARAGRAPH     | `{"text": "..."}` 或带 mark 时 `{"text": "...", "mark": "..."}` |
| KC   | KNOWLEDGE_CARD| `{"title","text","example":{"label","text"}}`（无例子时省略 example 键）|
| CALL | CALLOUT       | `{"title","text"}` |
| FIG  | FIGURE        | `{"aria_label","caption"}` |

## 知识库文档 knowledge/<slug>.md

```markdown
---
source_name: 什么是训练数据
source_url:                      # 真实参考了才填 URL，否则留空（禁止编造 URL）
topic: AI 基础
grade_band: 初中                  # 小学 / 初中 / 高中
license: CC-BY
copyright_status: 原创
---
正文 800~1500 字的科普短文……
```

硬规则：单一主题、事实准确、800~1500 字（中文字符）、面向对应年级段。
导入时 `source_url` 为空则由导入器生成稳定内部 URI `local://library/knowledge/<slug>`。

## 工具链

```bash
# 结构校验（不连库、不改文件）
uv run python -m app.scripts.validate_library --all
uv run python -m app.scripts.validate_library --book <slug>

# 幂等导入开发库
uv run python -m app.scripts.import_library --book <slug>
uv run python -m app.scripts.import_library --knowledge <slug>
```

新批次（OC-2~OC-N）流程：复制样书结构 → 写作 → `validate_library --all` PASS →
交 Hermes 质量抽查 → 导入。
