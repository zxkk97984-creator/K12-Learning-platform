# UI 行为契约（UI Behavior Contract）

> 来源：`prototypes/shuangling-v3-prototype.html`（1797 行）
> 审计日期：2026-08-19（Phase 0 Task 0-B）
> 范围：视觉 token、交互契约、Mock 数据形状、Mock 逻辑边界。只记录原型真实实现。

## 1. 视觉契约

### 1.1 设计 token（`:root` CSS 变量）

| Token | 值 | 用途 |
| --- | --- | --- |
| `--bg` | `oklch(99% 0.002 240)` | 页面底色（近白冷灰） |
| `--surface` | `oklch(100% 0 0)` | 卡片/面板表面色 |
| `--fg` | `oklch(18% 0.012 250)` | 主文字/深色元素 |
| `--muted` | `oklch(54% 0.012 250)` | 次级文字 |
| `--border` | `oklch(92% 0.005 250)` | 分隔线/描边 |
| `--accent` | `oklch(58% 0.18 255)` | 强调色（蓝紫） |
| `--accent-soft` | `color-mix(in oklch, var(--accent) 12%, transparent)` | 强调浅底（如 mark、focus） |
| `--accent-faint` | `color-mix(in oklch, var(--accent) 6%, transparent)` | 更浅的强调底 |
| `--fg-soft` | `color-mix(in oklch, var(--fg) 6%, transparent)` | 深色浅底（hover、灰块） |
| `--muted-soft` | `color-mix(in oklch, var(--muted) 11%, transparent)` | 次级文字浅底 |
| `--shadow-soft` | `0 18px 50px color-mix(in oklch, var(--fg) 11%, transparent)` | 浮层投影（popover/panel/menu） |

字体：

| Token | 值 |
| --- | --- |
| `--font-display` | `'Iowan Old Style', 'Charter', Georgia, 'Times New Roman', serif`（标题衬线） |
| `--font-body` | `-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', system-ui, sans-serif` |
| `--font-mono` | `ui-monospace, 'JetBrains Mono', 'SF Mono', Menlo, monospace`（标签/元信息/数据） |

尺寸与动效：

| Token / 常量 | 值 | 用途 |
| --- | --- | --- |
| `--fs-body` | `15px`（默认） | 正文基准字号；小学 17px、高中 14px |
| `--gutter` | `clamp(20px, 4vw, 56px)` | 页面侧边距 |
| `--content` | `1380px` | 内容最大宽度 |
| `--radius` | `14px` | 常规圆角 |
| `--radius-lg` | `22px` | 大卡片圆角 |
| `--ease` | `cubic-bezier(0.23, 1, 0.32, 1)` | 全部过渡/动画缓动 |
| `--shadow-soft` | 见上 | 浮层阴影 |

实现注意：颜色使用 `oklch()` 与 `color-mix()` 现代 CSS 函数，React 化时需确认目标浏览器支持或转成兼容色值。

### 1.2 明暗主题与学段适配

- 原型只有浅色主题，没有暗色主题变量或切换入口。
- 主题变体来自学段（`html[data-age]`）：
  - 初中（默认，`data-age` 为空）：基准样式。
  - 小学（`primary`）：`--fs-body: 17px`、按钮最小高 48px、首页标题更大、桌虫 scale 1（不缩小）。
  - 高中（`senior`）：`--fs-body: 14px`、桌虫 scale 0.8、「全部书籍」网格 5 列。
- 切换入口在个人菜单（`data-age-set="junior|primary|senior"`），选择持久化到 `localStorage['shuangling-age']`。

### 1.3 响应式断点（原型真实媒体查询）

| 断点 | 行为 |
| --- | --- |
| `max-width: 1100px` | reader 布局改 2 列、右侧 `context-rail` 隐藏、home hero 间距收窄、library-all-grid 改 2 列 |
| `max-width: 820px` | hero/section-grid/home-lower/profile-layout 全部单列；brand 副文字与 grade-badge 隐藏；library-grid 2 列；reader 单列、chapter-nav 变横向滚动条；quiz-entry 日期列收窄；profile-rail 不再 sticky |
| `max-width: 720px` | companion-panel 变为底部抽屉：`width: calc(100vw - 20px)`、`left: 10px`、`bottom: 10px`、`height: min(72vh, 600px)`（覆盖 placePanel 的 left/top） |
| `max-width: 560px` | 导航第 3/4 项隐藏；library-grid 单列；首页按钮全宽纵向堆叠；continue-card 书封收窄；voice-sheet 压缩；桌虫 scale 0.87 |
| `max-height: 800px` | 首页 hero 纵向节奏压缩（padding/标题/间距收窄）、continue-card 高度 208px、页底 padding 64px |

关于 1440×900 与 1280×720 的说明：原型没有针对这两个尺寸写专用断点，行为由上述断点推导：1440×900 使用完整 3 列 reader 布局、4 列书库网格（content 上限 1380px，gutter clamp 后有效宽度约 1304px）；1280×720 触发 `max-height: 800px` 的纵向压缩，其余列布局与 1440 相同；720px 以下才触发面板抽屉化。React 化时如需严格按 1440×900 / 1280×720 对齐，应把这条推导固化为测试用例。

### 1.4 视觉组件清单

| 组件 | 出现位置 | 关键样式/状态 |
| --- | --- | --- |
| `grade-badge` | topnav | 胶囊形 mono 10px 徽章「初二 · 8 年级」 |
| `avatar` | topnav | 圆形 30px 深底白字首字 |
| `status-dot` | 全局 | 7px 圆点 + 4px accent-soft 光环 |
| `btn`（primary/secondary/ghost/small） | 全局 | 44px 最小高、10px 圆角；active 下移 1px |
| `presence` 卡 | home | 318px 宽、头像 + 三行当前关注/最近发现/状态 |
| `continue-card` / `book-cover` | home | 左书封（衬线大标题 + 装饰 AI 大字）、右进度 62% |
| `recommend-card` / `evidence` | home | 推荐标题 + 「为什么推荐」证据块 |
| `mini-panel`（timeline/history/memory） | home | 三列；memory 版深色底 + `memory-chip` |
| `timeline-nodes` / `tnode` | home | 左侧竖线时间轴 |
| `history-row` | home | 行内「测验名 + 说明 + 分数」 |
| `library-search` | library | 220px+ 弹性输入框，focus 时 accent 描边 |
| `grade-btn` | library | 分组切换按钮（aria-pressed 高亮） |
| `filter-chip` | library/quizzes | 胶囊 chip，hover/aria-pressed 高亮 |
| `library-card`（精选） | library | 3 列静态推荐卡，封面 nth-child 3 种配色与几何装饰 |
| `book-card`（`book-tint-1~4`） | library | 4 列网格、`--tint` 变体封面、`book-reco` 推荐徽章、`book-why` 按钮 |
| `empty-state` | library/quizzes | 虚线边框居中空态 + CTA |
| `quiz-entry` | quizzes | 时间轴行（日期+圆点+竖线）、分数、AI 点评 |
| `result-tag`（ok/wrong） | quiz-detail | 胶囊结果标签 |
| `question-answer` / `question-correct` | quiz-detail | 答案行（你的答案/正确答案） |
| `interaction-note` | quiz-detail | 当时提示级别与追问记录 |
| `chapter-item`（is-done / aria-current） | reader | 目录项，完成 ✓、当前章 accent 编号 |
| `knowledge-card` / `example-block` / `reader-callout` / `reader-figure` | reader | 知识卡、生活例子、想一想、SVG 图解 |
| `context-rail` | reader | sticky 右栏，>=1101px 可见 |
| `memory-signal` | reader | 「这是我们第三次遇到…」信号行 |
| `selection-popover` | 全局（reader 触发） | 深色浮层：截断选中文本 + 问霜铃按钮 |
| `companion-state` / `companion-status-chip` | dock | 顶部状态胶囊、底部在线 chip（active/suggest 时显示） |
| `companion-sprite` / `chat-mini-sprite` / `.sprite` | dock/panel/voice | spritesheet 逐帧动画（见 2.13） |
| `message-bubble`（user/ai/error/refuse） | panel | 气泡圆角方向区分；error/refuse 有专门样式 |
| `tool-message` | panel | 居中胶囊 tool 状态（accent 圆点） |
| `typing` / `stream-caret` | panel | 三点动画 / 闪烁光标 |
| `quiz-card` / `quiz-option`（is-selected/is-correct/is-wrong） | panel | 对话内嵌测验卡片 |
| `quick-btn` | panel | 横向滚动快捷动作胶囊 |
| `chat-composer` | panel | textarea（42-88px 高度）+ 深色发送按钮 |
| `voice-sheet` / `waveform` / `voice-transcript` | voice-overlay | 全屏语音层、动态波形、转写文本 |
| `toast` | 全局 | 底部居中深色提示，2.2s 自动消失 |
| `user-menu` | topnav | 224px 下拉：学段 + 演示身份 |
| `doc-shell` / `doc-bar` / `doc-tabs` | profile archive | 文档外壳、文件名/更新时间/徽章、preview/edit tab |
| `md-frontmatter` / `md-body` / `level-tag` / `md-judgment` / `md-quote` | profile archive preview | Markdown 渲染样式 |
| `md-editor` / `md-gutter` / `md-source` | profile archive edit | 行号 + textarea 源码编辑 |
| `changelog` | profile archive | 修改记录时间线（is-new 高亮） |
| `memory-item` / `memory-actions` / `memory-confirmed` | profile rail | 记忆条目：正确/不完全正确/修改/忘记；确认后隐藏操作 |
| `profile-rail` / `rail-block` | profile | sticky 右栏 |

## 2. 交互契约

### 2.1 桌虫 dock：拖拽、Safe Zone、位置持久化

- 尺寸：覆盖后为 140×168（触发按钮全尺寸透明覆盖，sprite 140×152）；默认 `transform: scale(.85)`，hover / `data-open="true"` / `data-active="true"` / `data-suggest="true"` 时 scale(1)；`max-width: 560px` 时 scale(0.87)；`html[data-age=senior]` scale(0.8)、`primary` scale(1)。
- 拖拽：`pointerdown` 记录起点并 `setPointerCapture`；位移总和 > 5px 才视为拖动（`drag.moved`）；拖动中实时 `clampDock`。
- Safe Zone / `clampDock(x, y)`：
  - x ∈ `[12, max(12, window.innerWidth - 134)]`
  - y ∈ `[76, max(76, window.innerHeight - 160)]`
  - 常量 134/160 与覆盖后 dock 尺寸（140×168）一致，保证 dock 不越界。
- 位置持久化：`pointerup` 且发生过拖动时写入 `localStorage['shuangling-companion-position']`，值为 `{ x, y }` JSON；初始默认位置 `x = max(24, innerWidth - 168)`、`y = max(80, innerHeight - 188)`；`window resize` 时重新 clamp 并写回 left/top。
- 键盘：方向键每步移动 24px 并持久化；`Escape` 关闭对话面板。
- 点击：发生过拖动则不触发开/关；否则在 `openCompanion('check-in')` 与 `closeCompanion()` 间切换。
- 主动建议：加载后 6s `showSuggestion()` 置 `data-suggest="true"` 并显示「有一个新建议」，7s 后恢复（面板打开时不建议）。

### 2.2 点击桌虫 → conversation panel 定位

- 打开时记录 `lastFocus = document.activeElement`，设置 `dock.dataset.open="true"`、面板加 `is-open`；关闭时恢复 lastFocus 焦点，`aiState` 回到 idle。
- `placePanel()`（面板打开时调用；拖动、键盘移动、resize、路由切换时都会重算）：
  - 尺寸：`width = min(392, innerWidth - 32)`，`height = min(640, innerHeight - 32)`。
  - ≤720px：底部抽屉，`left: 16px`，`top = max(16, innerHeight - height - 16)`。
  - >720px：`gap = 16`；首选 `left = dock.right + 16`、`top = dock.top + dock.height - panelHeight`；若右溢出且左侧空间够（`dock.left >= panelWidth + gap`）则翻转到 dock 左侧；仍溢出则 clamp 到 `[16, innerWidth - width - 16]`；`top < 76` 时压到 76，底部不越过 `innerHeight - 16`。

### 2.3 文字选中 → selection-popover → `data-open-companion="selected"`

- `document.addEventListener('selectionchange', …)`：取 `window.getSelection()` 文本并 trim；只有 `anchorNode.parentElement` 位于 `.reader-copy` 内才显示，否则隐藏。
- 选中文本 `slice(0, 50)` 存入 `state.selectedText` 并写入 popover 的 `#selection-text`。
- 定位：取 `Range.getBoundingClientRect()`；`left = clamp(range.left, 12, innerWidth - 168)`，`top = max(12, range.top - 48)`。
- 点击「问霜铃」→ `openCompanion('selected')`，响应会引用选中文本。
- 离开 reader 路由时 `setView` 清空 `state.selectedText` 并隐藏 popover。

### 2.4 路由切换与 intent 映射

- 路由：文档级 click 委托处理 `[data-route]`（含 `data-quiz-id` 时先 `fillQuizDetail()`）；`setView()` 切换 `.is-active`、同步 nav-link 的 `aria-current`、用 `history.replaceState` 更新 `#hash`。
- 每个路由更新对话上下文标签 `#chat-context-label` 与快捷动作（见 2.6），并重新 clamp dock。
- `openCompanion(intent)` 的 intent 全集与响应来源（`currentIntentText`）：

| intent | 主要触发点 | aiState | 响应要点 |
| --- | --- | --- | --- |
| `check-in` | dock 点击、home 聊两句、reader 提问按钮 | speaking | 询问卡在定义还是影响判断 |
| `explain` | reader 知识卡/右栏 | speaking | 换一种讲法 + 生活例子 |
| `summary` | reader 总结本页 | speaking | 三条要点 |
| `quiz` | reader 出题、quizzes 空态 | encouraging | 特殊流程：tool 消息 → 900ms → 生成 quiz 消息 |
| `selected` | selection-popover | speaking | 引用选中文字 |
| `memory` | home「问问为什么」 | thinking | 解释偏好来源（3 次事件） |
| `memory-dispute` | profile 记忆「不完全正确」 | thinking | 标记待确认、换方式验证 |
| `presence-ask` | home presence 卡 | speaking | 承接昨天追问 + 继续章节 |
| `today-learn` | home 空态 CTA | speaking | 今日建议（12 分钟读完 + 小测） |
| `continue-yesterday` | home quick action | speaking | 接昨天进度 |
| `recent-status` | home quick action | speaking | 最近一周状态 |
| `recommend-next` | library quick action | thinking | 推荐《和算法相处》 |
| `book-fit` | library quick action | thinking | 《机器人会怎么想？》适配理由 |
| `book-why-1/2/3` | library 推荐卡 | thinking | 单书推荐理由 |
| `give-example` | reader quick action | speaking | 音乐推荐例子 |
| `give-hint` | quizzes quick action | speaking | 提示 1 |
| `another-way` | quizzes/quiz-detail quick action | speaking | 换讲法 |
| `why-wrong` | quizzes/quiz-detail quick action | thinking | 第 2 题错误解析 |
| `quiz-requestion` | quiz-detail「现在再问霜铃」 | thinking | 回到当时疑问 + 再出类似题 |
| `quiz-detail` | （保留在响应表中，原型无直接触发点） | — | 说明历史卷不会重新生成 |
| `profile-question` | profile 主按钮 | thinking | 画像判断带依据 |
| `profile-why-transfer` / `profile-why-pace` / `profile-why-question` / `profile-why-change` | profile 各「问霜铃 →」 | thinking | 逐条依据解释 |

- 通用兜底：未命中 intent 时返回「我会把当前页面、这段对话和你最近的学习线索一起考虑。」
- 去重：若 `state.messages` 已存在同 content 的消息则不重复流式输出。

### 2.5 conversation 流式输出、tool 状态

- `pushAiStreaming(text, meta)`：先把已有 `streaming` 消息内容置为 `…`；push `{role:'ai', kind:'text', content:'', meta, streaming:true}` 并渲染；`setInterval` 每 22ms 追加 1 个字符，写入最后一条非 user 气泡并保持 scrollTop 到底；结束时清除 interval、去掉 `streaming`；`aiState` 置 `speaking`。
- 输入流：`sendMessage()` push 用户消息 + `kind:'typing'`（三点动画），820ms 后替换为流式回答或 error/refuse。
- 重试：`retryChat()` 删除 error 消息、显示 typing，700ms 后重推恢复文案。
- Tool 状态：`kind:'tool'` 渲染居中胶囊（accent 圆点 + 文字）；quiz 流程：先「Quiz Skill · 正在生成测验…」，900ms 后改为「Quiz Skill 已创建 · 正式测验已记录」并追加 `kind:'quiz'` 消息。

### 2.6 quick actions 与 hint 分层

- `QUICK_ACTIONS[view]` 按路由渲染快捷按钮，末尾固定追加「语音聊天」；未知 view 回退 home。
  - home：today-learn / continue-yesterday / recent-status
  - library：recommend-next / book-fit
  - reader：explain / give-example / summary / quiz
  - quizzes：give-hint / another-way / why-wrong
  - quiz-detail：another-way / why-wrong
  - profile：profile-question / profile-why-change
- Hint（`requestHint()`）：已完成（`quizAnswer === 'B'`）→ toast「这道题已经完成」；`hintLevel >= 3` → toast；否则逐级：
  1. 训练数据是让机器背答案，还是从例子中找规律？
  2. 教小狗认识球时反复展示的那些例子。
  3. 选出「从例子里发现可重复规律」的选项。
  - 每次提示 aiState=encouraging、追加 `提示 n / 3` 消息；quiz footer 显示「已使用 n 级提示」。

### 2.7 quiz 卡片交互（选项 → 提交 → 答错 → 提示 → 修正）

- 选择：点 `[data-quiz-choice]` 写 `state.quizChoice` 并重渲染（`is-selected`）。
- 提交：`submitQuiz()` 无选择时 toast「先选一个答案」；有选择则 `state.quizAnswer = choice`、aiState=happy。
- 判定：正确答案硬编码为 B；B → `is-correct` + footer「✓ 已完成」+ 复盘文案；非 B → 该选项 `is-wrong`，footer「答案已记录 · 霜铃可以继续给你提示」。
- 持久化（Mock）：首次提交时 `QUIZZES.unshift({ id:'q-live', … })`，分数 `3/3`（B）或 `2/3`，meta 记录提示次数，并 toast「QuizSession 已保存 · 可在测验页查看」。
- 提示按钮在答错后仍可用（完成前）；完成后再点提示 → toast 提示可复盘。
- 答对/答错响应：答对强调「价值不是数量而是可重复规律」；答错引导「从例子里找出规律」。

### 2.8 年级 / 主题 / 测验筛选与「更多筛选」

- 学段：`data-grade-filter`（推荐/小学/初中/高中）单选框，改 aria-pressed 后 `applyLibraryFilter()`。
- 主题：`data-topic-filter` 多选 toggle；`data-more-filters` 展开/收起 `#topic-filters`（hidden + aria-expanded + 按钮文字 ▾/▴）。
- 搜索：`input` 事件实时过滤，匹配 `title + keywords + topic`（小写）。
- 组合逻辑：`visible = grade 命中（推荐恒真）&& topic 命中（空集合恒真）&& 搜索命中`；book-card 逐个 `hidden`。
- 「为你精选」区块只在「推荐 + 无主题 + 无搜索词」时显示；计数 `#book-count` 恒为 `共 12 本`（不改）。
- 无结果：`#library-empty` 显示；`data-clear-library` 重置为推荐 + 清空主题与搜索。
- 测验筛选：`data-quiz-filter`（全部/章节测验/AI 小测/更早）单选；「更早」恒返回空列表；`#quiz-count` 显示当前列表数量；空时显示 `#quiz-empty`。

### 2.9 新同学视角（demo-new）空态

- `data-demo-new` 切换 `body.demo-new` 类与按钮 aria-pressed，toast 提示（不持久化）。
- CSS：`body.demo-new .normal-only { display: none !important }`、`.empty-only` 由隐藏转为显示；影响 home 4 个面板与 quizzes 空态。

### 2.10 doc-mode preview/edit 与导出

- `setDocMode(mode)`：同步 `.doc-tab[aria-selected]` 与 `.doc-view[hidden]`；进入 edit 时同步行号并聚焦 textarea。
- `syncGutter()`：按 textarea 行数生成行号 span，滚动联动。
- `saveDoc()`：空文件 toast 拒绝；保存后更新「最近更新 刚刚 · 你修改过」、显示「用户修改」徽章、changelog 头部插入「今天 / 你手动修改了画像 · 已标记『用户确认』」（is-new）、切回 preview、toast。
- `cancelDoc()`：恢复原始文本、回 preview、toast「已放弃修改」。
- `data-export-profile`：仅 toast「已导出 xiaoming.agent.md（演示）」，无真实下载。
- profile 内部：`setProfileView(student|archive)`；进 archive 默认 preview tab。

### 2.11 记忆操作（memory actions）

| action | 行为 |
| --- | --- |
| `ok` | item 加 `is-confirmed`，显示「已确认 · 霜铃会继续使用」，隐藏操作按钮，toast |
| `forget` | 移除该 item，toast「已忘记这条记忆」 |
| `dispute` | `openCompanion('memory-dispute')` |
| `edit` | 跳 archive 视图 + edit tab，toast「在编辑器中直接修改这条记忆」 |

### 2.12 语音层与对话输入

- `startVoice()`：开遮罩、aiState=listening、聚焦关闭按钮；`closeVoice()` 关闭并聚焦 `#chat-voice`。
- `data-voice-toggle`：listening ↔ speaking 切换状态标题/副文案。
- composer：Enter 发送、Shift+Enter 换行；发送后清空输入框。
- 关键词分支（Mock 错误/拒绝）：输入含「断网/网络」→ error 消息（重试/稍后再问）；含「天气/股票/游戏」→ refuse 消息（不在教学范围 + 建议例句）；含「为什么」→ 因果回答；其他 → 上下文相关通用回答。

### 2.13 其他行为

- 章节目录折叠：`data-collapse-chapters` 切换 `.is-collapsed` 与按钮文字「收起目录 ▾/展开目录 ▸」。
- 阅读上下文：IntersectionObserver（`rootMargin: '-18% 0px -55% 0px'`）观察 `.reader-body [data-read-section]`，把最靠上的可见段写入对话上下文标签。
- Sprite 动画：`spriteFrames` 定义 7 种状态（idle/listening/thinking/speaking/happy/confused/encouraging）的 row/frames/label；`requestAnimationFrame` 每 220ms 切帧，按 8 列 × 11 行 spritesheet（`spritesheet-extended.webp`）计算 background-position；dock/panel/voice 三处 sprite 同步。
- Toast：统一 2.2s 消失。
- 焦点管理：打开面板记录 lastFocus、关闭恢复；语音打开聚焦关闭按钮；route 切换不清聊天消息。

## 3. Mock 数据契约

### 3.1 `state`（页面运行时状态）

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `view` | `string` | 当前路由（home/library/reader/quizzes/quiz-detail/profile） |
| `companionOpen` | `boolean` | 对话面板开/关 |
| `voiceOpen` | `boolean` | 语音层开/关 |
| `selectedText` | `string` | reader 中选中的文字（≤50 字符） |
| `quizChoice` | `string`（A~D） | 当前 quiz 卡片选中的选项 |
| `quizAnswer` | `string`（A~D） | 已提交的答案（空=未提交） |
| `hintLevel` | `number`（0~3） | 已使用的提示层级 |
| `quizSaved` | `boolean` | 本次会话 quiz 是否已写入 QUIZZES |
| `currentQuiz` | `string`（quiz id） | quiz-detail 当前展示的测验 id |
| `aiState` | `string`（spriteFrames key） | 霜铃当前表情/状态 |
| `messages` | `Message[]` | 对话消息数组 |

### 3.2 `Message` 结构

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `role` | `'ai' \| 'user'`（tool/typing 等可省略） | 发言方 |
| `kind` | `'text' \| 'tool' \| 'quiz' \| 'typing' \| 'error' \| 'refuse'` | 消息类型，决定渲染模板 |
| `content` | `string` | 正文（text 流式时为空并带 `streaming`） |
| `meta` | `string` | 元信息（「刚刚」「霜铃 · 当前页面上下文」「网络错误」等） |
| `streaming` | `boolean`（可选） | 是否正在流式输出（渲染闪烁光标） |

示例：`{ role:'ai', kind:'text', content:'…', meta:'基于当前章节与学习偏好' }`；quiz 消息 content 为引导语、meta 为「第 1 题 / 共 3 题」。

### 3.3 `spriteFrames`

| key | row | frames | label |
| --- | --- | --- | --- |
| `idle` | 0 | 7 | 待机中 |
| `listening` | 6 | 6 | 正在听 |
| `thinking` | 8 | 6 | 思考中 |
| `speaking` | 3 | 4 | 讲解中 |
| `happy` | 4 | 5 | 很开心 |
| `confused` | 5 | 8 | 有点疑惑 |
| `encouraging` | 7 | 6 | 给你鼓励 |

### 3.4 `BOOKS`（12 条）

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `id` | `string`（b1~b12） | 唯一标识 |
| `num` | `string`（01~12） | 编号（用于渲染与过滤回查） |
| `title` | `string` | 书名 |
| `grade` | `'小学' \| '初中' \| '高中'` | 学段（过滤器匹配值） |
| `topic` | `string` | 主题（AI 基础/机器人/编程/数据/AI 伦理/数字素养） |
| `chapters` | `number` | 章数 |
| `minutes` | `number` | 预计分钟 |
| `keywords` | `string` | 关键词（顿号分隔，参与搜索） |
| `status` | `string` | 阅读状态（「读到第 3 章」「未开始」） |
| `started` | `boolean` | 是否已开始（影响 book-status 样式） |
| `recommend` | `boolean` | 是否显示「霜铃推荐」徽章 + book-why 按钮 |
| `tint` | `number`（1~4） | 封面配色变体（book-tint-N） |

### 3.5 `QUIZZES`（3 条初始 + 1 条运行时插入）

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `id` | `string`（q1~q3、q-live） | 唯一标识 |
| `date` | `string`（MM-DD 或「今天」） | 测验日期 |
| `type` | `'章节测验' \| 'AI 小测'` | 类型（筛选值） |
| `name` | `string` | 测验名 |
| `book` | `string` | 所属书 |
| `chapter` | `string` | 所属章节 |
| `score` | `string`（如 `8 / 10`） | 分数展示（字符串） |
| `meta` | `string` | 提示次数/完成情况 |
| `note` | `string` | AI 点评 |
| `term` | `string`（`this`） | 预留字段（原型未使用语义） |

`q-live`（提交 quiz 后 unshift 插入）示例：`{ id:'q-live', date:'今天', type:'AI 小测', name:'训练数据 · 随堂测验', book:'AI 不是魔法', chapter:'第 3 章 · 训练数据', score:'3 / 3' | '2 / 3', meta:'使用 N 次提示 · 3 道题', note:…, term:'this' }`。

### 3.6 `QUICK_ACTIONS`

`Record<view, [intent, label][]>`，见 2.6 表格；渲染时末尾追加「语音聊天」按钮。

### 3.7 学生画像与学段映射

- 顶栏年级徽章：`初二 · 8 年级`（静态）；student 档案 frontmatter：`name: 小明`、`grade: 初二 · 8 年级`、`updated: 2026-08-18 20:18`、`preferred_explanation_style: example_based`、`preferred_difficulty: medium`、`preferred_session_length: short`。
- 画像字段（student-view 与 md 双形态）：讲解偏好=例子优先、学习节奏=短时、多轮、难度偏好=中等；表现条目=概念理解（较稳定）/应用迁移（仍需观察）/提问习惯（越来越具体），每条带 level-tag 与依据。
- 记忆列表：3 条（例子学习 / 短时多轮 / 追问为什么）。
- 学段映射：`primary`=小学、`junior`=初中（默认）、`senior`=高中；`BOOKS.grade` 与 `grade-filter` 使用「小学/初中/高中」，个人菜单使用英文 key。
- 本地存储：`shuangling-companion-position`（dock 位置）、`shuangling-age`（学段）；演示身份与对话不持久化。

## 4. Mock 逻辑契约与 Phase 1 替换边界

### 4.1 核心行为函数

| 函数 | 职责 | 关键常量/时序 |
| --- | --- | --- |
| `currentIntentText(intent)` | 按 intent 返回固定回复文案（30 个分支 + 兜底） | 全部硬编码 |
| `pushAiStreaming(text, meta)` | 模拟逐字流式输出 | 22ms/字，setInterval |
| `openCompanion(intent)` | 打开面板、映射 aiState、处理 quiz 特殊流程 | quiz 延迟 900ms |
| `requestHint()` | 三级提示 | 上限 3 级 |
| `submitQuiz()` | 判定答案、写入 q-live、回复 | 正确答案硬编码 B |
| `sendMessage()` | 关键词路由（error/refuse/为什么/通用） | typing 820ms |
| `retryChat()` | 错误后重试 | 700ms |
| `applyLibraryFilter()` | 年级/主题/搜索组合过滤 + 空态 | 实时 |
| `renderBooks()` / `renderQuizzes()` | 从数组渲染列表 | 静态数据 |
| `fillQuizDetail()` | 按 currentQuiz 填充答卷 | q1 才显示题目 |
| `handleMemoryAction()` | 记忆 4 种操作 | 无持久化 |
| `setAge()` / `toggleDemoNew()` | 学段/演示切换 | age 持久化，demo 不持久化 |
| `saveDoc()` / `cancelDoc()` | 画像文件编辑 | 仅 DOM/toast，无真实保存 |
| `placePanel()` / `clampDock()` / `loadCompanionPosition()` | 面板/桌虫几何与持久化 | 见 2.1/2.2 |
| `showSuggestion()` | 6s 后主动建议 | 7s 恢复 |
| sprite 动画 | spritesheet 逐帧播放 | 220ms/帧，8×11 网格 |

### 4.2 Phase 1 Mock Service 替换边界

以下逻辑在 Phase 1 应从原型内联 JS 抽离为可替换的 Mock Service，UI 保持相同契约：

1. **intent → 回复**：`currentIntentText` 的硬编码表 → `IntentResponseService`（或 `mockChatService.reply(intent, context)`），返回 `{ message, aiState, meta }`，并预留真实 LLM 适配层。
2. **流式输出**：22ms 字符定时器 → 统一的流式适配器（本地 mock 流 / 未来 SSE / WebSocket），消息结构 `kind:'text' + streaming` 不变。
3. **Quiz Skill 工具状态**：900ms 硬编码 tool 消息 → 工具调用状态机（`running → done`），tool 消息与 quiz 消息契约保持。
4. **推荐生成**：`today-learn / recommend-next / book-fit / book-why-*` 文案 → 推荐服务（输入学生画像 + 阅读记录 + 书库），home 推荐卡、evidence 由服务返回。
5. **学习画像与记忆**：frontmatter/记忆/表现/变化 → 画像存储 + 记忆 CRUD；`ok/forget/dispute/edit` 需要真实写操作与审计（changelog）。
6. **测验数据**：硬编码 3 题 + 正确答案 B → 题库/测验生成服务；`quiz-detail` 的题面、答案、提示记录来自记录存储。
7. **错误/拒绝分类**：关键词（断网/天气/股票/游戏）→ 错误处理与内容安全/范围判定服务。
8. **筛选**：前端数组过滤 → 查询服务（当前数据量小，可保留前端过滤但接口形状对齐）。
9. **持久化**：`localStorage`（dock 位置、学段）→ 用户偏好 API 或保持 localStorage 并明确 schema。

### 4.3 边界模糊 / 难以 React 化的点（风险清单）

- **几何计算密集**：dock 拖拽、panel 翻转/钳位、selection popover 定位全部依赖 `getBoundingClientRect()` 与窗口尺寸，React 化需要独立 hook（`useCompanionPosition` / `useSelectionPopover`），并处理 resize / 滚动 / 缩放。
- **spritesheet 资产契约**：动画依赖 `spritesheet-extended.webp` 的 8×11 网格与各状态 row/frames 常量，属于静态资产契约，需随代码迁移并校验。
- **AI 状态与消息时序耦合**：aiState（speaking/thinking/encouraging…）由 intent 与异步时序共同驱动，状态机边界需显式建模，避免 React 重渲染打断流式计时器。
- **Mock 逻辑与文案耦合**：推荐、画像依据、测验点评全部是硬编码中文文案，替换为服务时「字段 → 文案」的映射契约尚未存在（应由 Task 0-C~0-G 补充）。
- **无真实持久化**：对话历史、记忆确认、画像修改均只存在内存/DOM，q-live 会在刷新后丢失；验收时不能把「保存成功」视为真实落库。
- **主题色技术债**：oklch/color-mix 在旧浏览器不支持；React 化时应锁定设计 token 的兼容输出或声明浏览器基线。
- **重复内容去重**：`openCompanion` 按 content 全等去重，相同 intent 连点不会重复输出——这个行为需要保留还是改为每次追问，需产品确认。
