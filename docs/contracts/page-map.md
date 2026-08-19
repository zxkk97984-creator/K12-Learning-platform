# 页面地图（Page Map）

> 来源：`prototypes/shuangling-v3-prototype.html`（1797 行，单文件 SPA 原型）
> 审计日期：2026-08-19（Phase 0 Task 0-B）
> 用途：作为 Phase 1 React 化的页面/路由清单，以及契约建立（Task 0-C~0-G）的输入。本文只描述原型中真实存在的元素，不包含未实现内容。

## 1. 路由模型

原型是单文件 SPA：所有页面都是 `<section class="view">`，通过 `.is-active` 类切换显示（默认 `display: none`）。切换路由时用 `history.replaceState({}, '', '#<view>')` 更新 hash，不做前进/后退历史栈。

| 路由标识 | section id | 页面标题（h1） | 默认 hash |
| --- | --- | --- | --- |
| `home` | `view-home` | 晚上好，小明。 | `#home` |
| `library` | `view-library` | 找到下一本适合你的书。 | `#library` |
| `reader` | `view-reader` | 训练数据：机器是怎么学会的？ | `#reader` |
| `quizzes` | `view-quizzes` | 每一次答题，都会留下线索。 | `#quizzes` |
| `quiz-detail` | `view-quiz-detail` | 机器学习基础小测（动态填充） | `#quiz-detail` |
| `profile` | `view-profile` | 霜铃眼中的你。 | `#profile` |

路由切换入口统一由文档级 `click` 委托处理 `[data-route]`；导航栏 4 个入口（首页/学习/测验/成长）会同步 `aria-current="page"`。

## 2. 全局层（不随路由切换销毁）

以下元素在 6 个路由间始终保持存在，React 化时应作为全局布局层（而非某个页面的一部分）：

| 全局层 | 定位 / z-index | 作用 |
| --- | --- | --- |
| `topnav` | `position: sticky; top: 0; z-index: 20` | 品牌、主导航（4 个 `data-route` 按钮）、年级徽章、学生入口、个人菜单 |
| `user-menu`（个人菜单） | `position: absolute`，挂在 `.nav-right` 内，`z-index: 50` | 学段切换（初中/小学/高中）、演示身份（新同学视角）；点击外部自动关闭 |
| `companion-dock`（桌虫） | `position: fixed; z-index: 40` | 全局 AI 教师入口：可拖拽、可点击开/关对话面板；含状态胶囊与状态标签 |
| `companion-panel`（对话面板） | `position: fixed; z-index: 35` | 聊天：header、当前上下文、feed、quick actions、composer、语音按钮 |
| `selection-popover`（选中弹层） | `position: fixed; z-index: 34` | 阅读页文字选中后的「问霜铃」快捷入口；仅 reader 内有效 |
| `voice-overlay`（语音层） | `position: fixed; inset: 0; z-index: 60` | 全屏语音对话遮罩（正在听/正在回答、波形、转写文本、切换/结束按钮） |
| `toast` | `position: fixed; left: 50%; bottom: 24px; z-index: 90` | 全局轻提示（约 2.2s 自动消失） |

## 3. 页面详述

### 3.1 home（首页）

- 路由标识：`home`；进入方式：初始默认视图、brand 点击、导航「首页」、reader 顶部「← 返回首页」；退出：任意 `data-route`。
- 主要区块：
  - `home-hero`：问候语（周二 19:42）、标题、学习线索 lead、操作区（「继续学习」→ reader、「和霜铃聊两句」→ check-in）、在线状态 note、AI presence 卡片（当前关注/最近发现/状态/「问问霜铃」→ presence-ask）。
  - `section-grid`：左侧「继续学习」`continue-card`（书封、章节进度 62%、预计时长、继续按钮 → reader）；右侧「霜铃的下一步建议」`recommend-card`（推荐标题 + 为什么推荐 evidence）。
  - `home-lower`：三张 mini-panel —— 最近变化时间线（→ profile）、最近测验（→ quizzes）、AI 记得什么（→ memory intent）。
- 关键交互元素：`data-route="reader"`、`data-route="profile"`、`data-route="quizzes"`、`data-route="library"`；`data-open-companion`：`check-in` / `presence-ask` / `memory` / `today-learn`。
- 空态（新同学视角 `body.demo-new`）：`empty-only` 版「继续学习」（推荐第一本书 + today-learn CTA）、「最近变化」「最近测验」「AI 记得什么」共 4 个空态卡片，替换 `normal-only` 卡片。

### 3.2 library（书库）

- 路由标识：`library`；进入：导航「学习」、home 空态「开始第一课」、quizzes 空态「去书库开始学习」；退出：卡片「继续 →」→ reader、导航等。
- 主要区块：
  - `library-toolbar`：搜索框（书名/知识点/主题）、学段筛选 `grade-filter`（推荐/小学/初中/高中）、「更多筛选 ▾」按钮。
  - `topic-filters`（默认 `hidden`，由「更多筛选」展开）：主题 chips（AI 基础/机器人/编程/数据/AI 伦理/数字素养）。
  - 「为你精选」：`library-grid` 3 张静态推荐卡（AI 不是魔法/机器人会怎么想？/和算法相处），含状态、章数/时长、继续/为什么推荐按钮。
  - 「全部书籍」：`library-all-grid`，由 `renderBooks()` 用 `BOOKS`（12 本）渲染 `book-card`。
  - `#library-empty`：搜索/筛选无结果时空态。
- 关键交互元素：搜索输入、`data-grade-filter`、`data-topic-filter`、`data-more-filters`、`data-clear-library`、`data-route="reader"`、`data-open-companion="book-why-2/3"`（book-card 内动态 `book-why-1/2/3`）。
- 空态：`#library-empty`（没有找到匹配的书，含「清除筛选」）。无 loading / error 态。

### 3.3 reader（阅读页）

- 路由标识：`reader`；进入：home「继续学习」/「继续第 3 章 →」、library 卡片「继续 →」；退出：「← 返回首页」、导航。
- 主要区块：
  - `reader-topbar`：面包屑（首页 / AI 不是魔法 / 训练数据 / 第 3/7 节）+ 操作（「总结本页」→ summary、「给我出题」→ quiz）。
  - `chapter-nav`：目录折叠按钮（`data-collapse-chapters`）+ 5 个章节项（`chapter-item`，含 `is-done` 已完成标记与 `aria-current="page"` 当前章）。
  - `reader-copy`：章节标题、dek、`memory-signal`（记忆信号）、正文段落（`data-read-section` 观察点）、`mark[data-selected-term]`、`knowledge-card`（「让霜铃讲给我听」→ explain）、`reader-figure`（SVG 图解）、`reader-callout`（想一想）、页脚（选择文字提示 + 「我想问一个问题」→ check-in）。
  - `context-rail`：右侧固定栏「当前学习上下文」（书本/章节/知识点 + 解释/总结/出题三个按钮）。
- 关键交互元素：文字选中 → `selection-popover`（仅 `.reader-copy` 内有效）→ `data-open-companion="selected"`；`data-read-section` 由 IntersectionObserver 实时更新对话上下文标签；`data-open-companion`：`summary` / `quiz` / `explain` / `check-in` / `selected`。
- 空态 / loading / error：页面本身无；对话相关的 typing / streaming / error 见全局对话层。

### 3.4 quizzes（测验历史）

- 路由标识：`quizzes`；进入：导航「测验」、home「最近测验 → 查看全部」；退出：「查看答卷」→ quiz-detail、导航。
- 主要区块：
  - `quiz-filter-row`：测验筛选 chips（全部/章节测验/AI 小测/更早）+ 计数（共 N 次测验）。
  - `quiz-timeline`：由 `renderQuizzes()` 渲染 `quiz-entry`（日期、类型、名称、分数、来源书/章、meta、AI 点评、「查看答卷」按钮）。
  - 空态两个：`#quiz-empty`（筛选无结果，CTA「让霜铃出一份测验」→ quiz intent）、`empty-only` 版「还没有正式测验」（新同学视角，CTA → library）。
- 关键交互元素：`data-quiz-filter`、`data-route="quiz-detail" data-quiz-id`、`data-open-companion="quiz"`、`data-route="library"`。

### 3.5 quiz-detail（答卷回顾）

- 路由标识：`quiz-detail`；进入：quizzes 列表「查看答卷」（携带 `data-quiz-id`）；退出：「← 返回测验记录」→ quizzes、导航。
- 主要区块：
  - `quiz-detail-top`：返回按钮、测验名称/来源/分数（动态填充 `#quiz-detail-name/src/score/note`）。
  - `question-list`：3 道示例题回顾（题号+题型、正确/错误 result-tag、题干、你的答案、正确答案、当时的交互记录：提示级别、追问、霜铃提示、「现在再问霜铃」→ `quiz-requestion`）。
  - 页脚：`quiz-detail-foot`（共 10 题 · 这里展示 3 题回顾）与 `#quiz-detail-sample-note`（非 q1 时显示「答卷回顾以机器学习基础小测为例」）。
- 动态逻辑：`fillQuizDetail()` 按 `state.currentQuiz` 从 `QUIZZES` 填充；仅 `q1` 展示 question-list 与 foot，其他测验显示 sample note。
- 空态 / loading / error：无页面级。

### 3.6 profile（成长 / AI 学习画像）

- 路由标识：`profile`；进入：导航「成长」、右上角学生入口（头像+小明）、home「查看完整变化」；退出：导航。
- 主要区块：
  - `profile-main`：
    - `student-view`（默认）：`student-intro`（AI 对我的认识 + 依据）、学习方式 `habit-list`（讲解偏好/学习节奏/难度偏好）、当前表现 `student-rows`（概念理解/应用迁移/提问习惯，含 `level-tag` 与「问霜铃 →」）、最近变化（`md-quote` + 依据）。
    - `archive-view`（原始 AI 档案，`hidden` 默认）：`doc-shell` 文档视图，见下。
  - `profile-rail`：证据覆盖说明、记忆列表 `memory-list`（3 条 memory-item，操作：正确/不完全正确/修改/忘记）、操作区（「问霜铃：为什么这样判断？」→ profile-question、「查看原始 AI 档案」→ archive）。
- 次级视图（均在 profile 路由内切换）：
  - 学生视图 ↔ 原始 AI 档案：`data-profile-view="student|archive"`，由 `setProfileView()` 控制 `hidden`。
  - 文档 preview ↔ edit 两个 tab：`data-doc-mode="preview|edit"`、`data-doc-view`，由 `setDocMode()` 控制；edit 含带行号 gutter 的 `md-source` textarea。
  - 文档操作：`data-doc-save` / `data-doc-cancel` / `data-export-profile`（导出 toast）。
- 关键交互元素：`data-open-companion`：`profile-question` / `profile-why-transfer` / `profile-why-question` / `profile-why-pace` / `profile-why-change`；`data-mem-action`：`ok` / `dispute` / `edit` / `forget`。
- 空态 / loading / error：无页面级。

## 4. 空态 / loading / error 状态汇总

| 位置 | 空态 | Loading | Error |
| --- | --- | --- | --- |
| home | 新同学视角下 4 个 `empty-only` 卡片（继续学习/最近变化/最近测验/AI 记得什么） | 无 | 无 |
| library | `#library-empty`（无匹配书籍 + 清除筛选） | 无 | 无 |
| reader | 无 | 无 | 无 |
| quizzes | `#quiz-empty`（筛选无结果）、`empty-only`（无测验记录） | 无 | 无 |
| quiz-detail | 非 q1 测验隐藏题目列表并显示「示例」提示 | 无 | 无 |
| profile | 无 | 无 | 无 |
| 对话层（全局） | — | typing 三点动画、`stream-caret` 流式光标、Quiz Skill 生成中 tool 消息、dock 思考/鼓励状态 | `message-bubble.is-error`（网络错误 + 重试/稍后再问）、`is-refuse`（超范围问题）、toast 提示 |

## 5. 审计备注

- 原型中的 `data-od-id` 是观察/调试锚点（Observation ID），不影响行为，React 化时可保留为测试选择器。
- 路由不维护 history 栈（只用 `replaceState`），浏览器前进/后退不会切换页面。
- 页面标题、推荐文案、测验内容均为静态 Mock，动态部分仅由 `BOOKS` / `QUIZZES` / `state.messages` 渲染。
