# 霜铃 K12 项目优化 Implementation Plan

> 交接日期：2026-09-06。状态：**计划待执行，业务修复尚未实施**。
> For agentic workers：按任务逐项执行；可使用 `superpowers:executing-plans`。本文件不授权自动发布、删库或重置工作区。用户将另行指定执行 agent。

**Goal：** 将已有 AI 通识学习平台优化为内容完整、学习路径清楚、记录可信、可恢复、可验收的小规模学生试用产品。

**Architecture：** 保留 React SPA + FastAPI 模块化单体、PostgreSQL/pgvector、现有 Worker、Redis 与存储接口。沿用 Service 层，按用户流程做小批次修复；不迁移框架、不拆微服务、不重建已经存在的能力。

**Tech Stack：** React 19、TypeScript、Vite、Tailwind、Zustand、TanStack Query；Python 3.12、FastAPI、SQLAlchemy async、Alembic；Vitest、pytest、Playwright。

**Spec：** 本文件第 1–7 节为本轮优化规格；业务原始范围以 `docs/requirements/产品需求总纲.md` 为依据。阅读 `backend/data/library/README.md` 理解实际课程范围。执行状态写 `tasks/todo.md`，验收证据写 `tasks/acceptance/`。

## 0. 执行前必须知道

1. 仓库已有根目录 `plan.md` 和 `docs/plans/post-audit-plan.md`，本轮不覆盖它们，也不把历史 PASS 当作当前 PASS。此文件是 **2026-09-06 优化工作入口**，历史文件供理解决策使用。
2. 当前目标是评审与交接。此文件中的新增接口、组件和测试均为拟议交付，不能描述为已存在。
3. 本轮读取时 HEAD 为 `970ffda`；初始未跟踪项为 `.playwright-mcp/`、`backend/空`。不得删除这些用户已有文件。执行开始重新记录 `git status` 和 HEAD，若已变化，以新代码核实问题是否仍存在。
4. 不伪造推荐、掌握度、学习次数、服务在线状态或测试通过数。保持“不引入主观知识掌握百分比”的原始产品约束。
5. 只保留学生端和轻量管理员端。教师布置作业、班级、家长驾驶舱、支付、排行榜、多租户均不属于本轮。
6. 使用真实现有课程。当前语料集中在 AI、编程、数据、机器人、计算思维和数字素养，不以“全学科提分平台”宣传。
7. 单次执行一个任务；任务涉及多于约 5 个生产文件时进一步拆成子提交。测试与契约文件可以随实现一起修改。不要同时重写 Reader、Auth 和 conversation store。
8. 先添加能够暴露原问题的行为测试，看到预期失败，再修复，再跑相关测试和 build。纯文档/字号调整无需机械添加镜像测试。
9. 数据库测试必须使用明确隔离的测试库。已有脚本会 seed/import 并修改数据库，**不得直接对当前学习数据库运行全量 CI**。不打印 `.env` 或令牌。
10. 无需执行 agent 每完成一步都重新请用户批准；在约定范围内推进。只有范围变更、真实用户数据破坏、费用超预算、真实对外发布才另行确认。

## 1. 项目经理判断：现在最应该解决什么

项目已具备较完整的功能模块和一定测试基础，值得在现有实现上收敛。现在的关键不是增加页面数量，而是保证学生能够找到课程、看懂材料、得到针对性帮助、完成练习，并知道下一次从哪里继续。

建议版本目标：**完成一条高质量学习闭环并进入受控试用**。第一批精修课程覆盖现有小学、初中、高中内容各一本；先集中测试初中阅读体验，其他学段作为兼容性检查，不删除或屏蔽原有年级。

### 1.1 保留的资产

- Service 接口已连接真实 API；书本详情已包含独立加载、错误和重试，不要重新实现成占位页。
- 已有学生/管理员鉴权、账号禁用、SSE 幂等重放、测验序号锁、学习结算防重。
- 已有记忆证据、画像历史、规则推荐、内容导入、知识资源处理状态、任务 Worker、Redis 锁/缓存、请求日志与 metrics。
- 已有可复用配色与布局 token、桌宠及对话面板、章节知识卡片。
- 文件语料为 25 本书、56 篇知识文档，有结构校验流程。

### 1.2 问题与修改方向

证据级别：**代码确认**表示可直接定位实现；**本轮实测**表示确实执行过；**待复现**表示有明确风险路径但未完成运行复现；**产品建议**表示拟议优化而非既有 bug。

| 编号 | 优先级 / 证据 | 问题与用户影响 | 原因、方向与任务 |
|---|---|---|---|
| F01 | P0 / 代码确认 | 学生内容发布边界不完整，可能访问草稿/归档内容 | `/books` 接受学生传入 status；章节列表不筛章节状态；章节详情仅检查存在。统一学生内容可见性并检查缓存/RAG/出题，T02–T03。尚未用真实账号做越权请求，不宣称已发生数据泄漏。 |
| F02 | P0 / 代码确认 | 书库“全部”实际可能只有第一页，搜索找不到后续课程 | 后端默认 limit=20；http.ts 只返回 data 丢弃 meta；getBooks 不遍历页；文件语料 25 本。增加完整分页与全库筛选，T04–T05。当前数据库发布数量未查询，25 是文件数。 |
| F03 | P0 / 代码确认 | 接口失败被误报无数据，部分页面无限加载 | Home/Library/Quizzes catch 清空；Profile 首次 Promise.all 任一失败导致 prefs=null，渲染条件 `loading || !prefs` 持续骨架；AdminDashboard 失败持续“加载”。T07–T09、T21。 |
| F04 | P0 / 代码确认 | 图解没有图，IMAGE 内容不渲染 | Reader 的 FIGURE 分支输出“图解占位”，IMAGE 落到 return null；语料规范要求每章有 FIG，但只存描述。修复内容契约→导入→显示全链路，T10–T12。 |
| F05 | P0 / 待运行复现 | 共用设备切换账号可能看到上个账号对话 | Auth 清 token/user，未清模块级 conversation store；store loaded 短路和 active-conversation 本地键无用户隔离。优先复现并修复，T06，不扩大成“后端越权已证实”。 |
| F06 | P1 / 代码确认 | 答卷“再问老师”目标不明确，按钮与实际意图不一致 | 每题按钮调用同一个 askAgain，意图是“再出一道类似的题”；没有显式 quiz/question/answer 上下文。改为“讲解这道题”并单独做同类练习，T14–T16。 |
| F07 | P1 / 代码确认 + 产品建议 | 学习完成数和进度的口径容易产生误导 | 滚动到末块发 CHAPTER_FINISHED；末章末块发 BOOK_FINISHED；后端分别计不同事件数，未以全部章节完成作为书籍完成条件。先核实并统一语义，T13。 |
| F08 | P1 / 代码确认 + 产品建议 | 页面入口多，章节末尾缺乏明确下一步 | 首页重复继续学习/聊天入口；Reader 末尾是问问题，没有成套“完成—练习—下一章”操作。T08、T13、T16。 |
| F09 | P1 / 代码确认、视觉待验 | 小字号、固定导航、面板工具过密，不利于儿童与窄屏 | 多处 9–11px 正文/操作；AppLayout 无窄屏导航分支；body overflow-x:hidden 可能掩盖裁切。按第 5 节统一，T17–T19。不声称已实测手机溢出。 |
| F10 | P1 / 代码确认 | 展示了内部开发文案 | 对话头“骨架·1-F”、404“Phase 1”、答卷“技能版本”等。用面向学生的文案替换，T17–T19。 |
| F11 | P1 / 代码确认 | 长对话摘要没有实际压缩输入，成本/时延随历史增长 | conversation service 查询全部 messages，同时拼摘要，仍把全量 history 传 provider。定义摘要覆盖边界和输入预算，T20。 |
| F12 | P1 / 代码确认 | token 使用量实际是字符长度，不能用于真实计费判断 | service 多处 input_tokens=sum(len(...))、output_tokens=len(content)。改为 provider usage 或明确 estimated 字段，T20。 |
| F13 | P1 / 代码确认 + 产品建议 | 题目可运行不代表有教学价值 | 确定性题目多为“是不是本章内容/知识点”；不是概念应用评估。优先精修三门样板课、人工审题与真实模型评测，T22–T24。 |
| F14 | P2 / 代码确认 | 数据加载方式分散、请求瀑布、重复详情查询 | QueryClient 已配置，但 src 中没有 useQuery/useMutation 使用；Home 多段串行 await；QuizList 对每项查来源。渐进迁移而非换状态框架，T07–T09、T15。 |
| F15 | P2 / 代码确认 | 管理端上传后状态不自动追踪 | AdminKnowledge 只 load 一次，无处理中轮询，上传/重新处理反馈易被理解为处理完成。T21。 |
| F16 | P2 / 代码确认 | 核心文件责任过多，修改容易引发连锁错误 | Reader 776 行、Home 576 行、Settings 519 行、conversation service 1278 行、store 611 行。只随任务按职责拆，T08、T10、T20；行数是复杂度线索，不是强制质量指标。 |
| F17 | P1 / 代码与文档确认 | 技术门禁不能证明真实教学质量和试用准备度 | 历史验收承认真实 LLM/ASR/TTS、S3、远端 CI、多副本、Worker 长稳未确认；E2E 只有桌面 Chromium 项目。T23–T26。 |
| F18 | P2 / 代码与文档确认 | 多份完成状态与测试数字不一致 | 早期文档“全部完成”与 README/当前阶段“收口”并存，容易误导下一位 agent。T01、T26。 |

## 2. 本轮验证与限制

| 检查 | 本轮结果 | 可以说明什么 |
|---|---|---|
| `cd frontend && pnpm test` | 38 files、191 tests passed | 当前已有前端自动化用例通过；不能覆盖尚未写的失败路径 |
| `cd frontend && pnpm build` | 成功；JS 496.76 kB，gzip 145.47 kB；CSS 34.79 kB | 类型与生产构建通过；不是首屏性能实测 |
| `cd backend && uv run --no-sync python -m app.scripts.validate_library --all` | PASS，books=25、violations=0；56 篇知识文档 | 文件语料符合现有结构规则；不证明图像资产齐全、事实正确或年龄适配 |
| 本机 `/health` | 返回 status=ok | HTTP 进程响应；不等价于数据库/Worker/模型全部正常 |
| 浏览器 | 本轮仅捕获登录页 | 登录提交被自动审批拦截；未完成学生/管理员内部页面的视觉与交互评审 |
| 后端 provider/embedding 单测 | 本轮 12 passed | 仅协议与向量相关单测，未连接真实模型 |
| 后端全量 pytest / E2E | 本轮未执行 | 测试含真实库写入，本轮没有建立隔离库，不沿用历史 311/9 数字作为新结果 |
| 真实模型/语音/远端部署 | 未调用、未验证 | 相关事项列为上线前验收，不假定已通过 |

登录页截图：`tasks/audit-2026-09-06/01-login.png`。表单层级简洁；缺少账号获取/登录求助入口是产品建议，不能据截图推断登录功能故障。

登录内部流程的步骤与状态：1. 登录页已观察；2. 提交登录受审批阻止；3. 首页、书库、阅读、练习、成长、设置和后台均以代码审查为依据，视觉验收留给 T01。此文件是项目代码/产品评审计划，不是已经完成的全流程 UI 审计报告。

## 3. 版本范围、指标与排期

### 3.1 三个里程碑

- **M0 可相信的数据与内容边界**：T01–T12。解决可见性、分页、跨账号残留、误报空态、图片链路。可以先合入 T02/T04/T06/T07 的独立修复，不被大范围视觉调整阻塞。
- **M1 一次学习能够完整收尾**：T13–T20。统一完成语义；精确错题讲解；首页和复习串联；移动端、对话面板、成长界面清晰；对话输入可控。
- **M2 可运营、可受控试用**：T21–T26。后台状态、样板课程、教学评测、验证矩阵和试用观察。

粗估：1 名熟悉代码的全栈开发者加内容审校，M0 约 5–8 人日，M1 约 7–12 人日，M2 约 5–8 人日；共 17–28 人日，另留约 25% 不确定性。此为范围估算，不是 agent 耗时承诺。前两项任务完成后根据实际返工重估。范围不缩减，以里程碑分批交付。

### 3.2 试用指标（目标，不是假造基线）

| 指标 | 明确定义 | 初始验收目标 |
|---|---|---|
| 学习路径完成率 | 测试用户从首页开始，完成一个小节、提问一次、交一份练习并看到反馈 / 开始人数 | 5–8 位自愿测试者中至少 80% 可在无需操作者讲解的情况下完成；小样本仅发现问题 |
| 首次有效学习耗时 | 登录成功→打开适配课程正文 | 观察值中位数 ≤90 秒；记录迷路位置，不用动画延迟凑指标 |
| 技术成功率 | 合法请求中的完整回答/提交成功比例；取消单列 | 在固定测试环境跑指定集，失败有可恢复入口；不以小样本宣称生产 SLA |
| 记录一致性 | 阅读恢复、完成计数、答卷与来源吻合 | 指定验收用例 100% 通过 |
| 学习价值 | 学生能否用自己的话解释一个概念、独立完成一道应用题 | 保留学习前后答案，由内容审校按规则评价，不换算人格/能力分数 |
| 再次使用 | 试用 7 日内主动回来并做有效学习的用户占比 | 先测基线再定目标，不为了留存加签到压力 |
| 模型效率 | 首字时延、整答时延、实际/估算 token、失败与降级数 | 实际 provider 单独测量，先建立基线，再设模型专属阈值 |

## 4. 接口与状态设计原则

### 4.1 分页必须保留信封

保留现有 `apiRequest<T>` 返回 data 的行为，增加 `apiRequestEnvelope<T, M>`，两者复用一个解析器，不复制鉴权/错误分支。不要把所有旧调用一次改成新返回类型。

```ts
// 拟新增于 shared/api/http.ts 或同目录 envelope.ts
export interface ApiEnvelope<T, M = Record<string, unknown>> { data: T; meta: M }
export interface CursorMeta { next_cursor: string | null; has_more: boolean; total?: number }
export interface BookPage { items: Book[]; meta: CursorMeta }
// ContentService 增加 getBooksPage(params): Promise<BookPage>
// 旧 getBooks 调用逐个核查，兼容期明确其仅返回一页，不再用它表达“全部”。
```

`GET /books?cursor=&limit=20&search=&grade_min=&grade_max=&tag=`：search 在后端全库过滤后分页；排序保持 `(created_at desc, book_id desc)`，grade 使用区间相交（book.min ≤ requested.max 且 book.max ≥ requested.min）。搜索词 trim；参数长度上限 100；SQL 使用绑定参数；搜索及所有筛选加入缓存键。筛选变化重置 cursor，搜索防抖 300ms，旧响应不可覆盖新查询。不先拉 100 本后本地搜索来掩盖问题。

### 4.2 请求状态必须有语义

```ts
type ResourceState<T> =
  | { status: 'loading' }
  | { status: 'success'; data: T }
  | { status: 'error'; message: string; requestId?: string };
// 空态只在 success 且 data 确实为空时成立。
// 已有数据重取失败：保留旧数据 + “更新失败” + 重试；禁止擦成零。
```

查询渐进使用现有 TanStack Query。用户数据 query key 包含 user_id；logout/401 同步取消请求、清对应缓存及用户内存状态。权限失败不无限重试；网络/5xx 最多自动重试 1 次，429 遵守 Retry-After。添加 AbortSignal 支持，避免路由/账号切换后的迟到响应回填。

### 4.3 AI 必须明确在讲什么

扩展现有 ScreenContext 类型和后端校验，不另建第二套上下文：支持 `quizSessionId`、`questionId`（前端命名在 adapter 转成后端已约定格式）。后端根据当前用户与 ID 查询可信快照，不相信客户端传来的正确答案、学生 ID 或权限结论。发送动作时冻结上下文；用户切页后不篡改正在生成的回答来源。

“讲解这道题”→解释当前快照与作答；“再练一道”→创建新的 quiz session，并记录 source_quiz_session_id/source_question_id。只看旧答卷不得产生新测验。未知/不属于自己/已不可访问的资源返回明确错误。

### 4.4 完成与时长分开

- `position_percent` 仅指当前位置，不叫掌握度、不当全书完成百分比。
- 滚到末块只说明到达末尾。新增有意识操作“完成本章”；章节完成记录防重；全书所有应学的已发布章节完成才显示已完成。
- 保留旧事件，不批量删历史。引入版本化完成口径或独立 ChapterCompletion 事实表，旧滚动事件标为历史阅读行为，迁移不凭空推断学习完成。
- 时长现有实现是起止墙钟差加上限。先诚实标注“阅读会话时长”；若升级为有效时长，再加入可见性/活动区间心跳。不要悄悄改历史分钟数。

## 5. 前端实施规格：执行 agent 不得自行发挥

### 5.1 视觉方向与 token

保留现有浅色背景、深灰文字、蓝色操作色、轻边框和桌宠形象。不要改成营销落地页、炫光渐变、霓虹背景、玻璃卡片墙或密集仪表盘。

| 项 | 统一规格 |
|---|---|
| 内容宽度 | 沿用 --content=1380px；一般页面信息区建议 ≤1200px；阅读正文 620–720px；现有 gutter 可继续使用，320/390px 下边距 16px |
| 页面节奏 | 桌面顶部 32px、区块间 24px、卡片内 20–24px；移动顶部 20px、区块间 20px、卡片内 16px |
| 标题 | 首页 h1 桌面 36–40px/1.2，手机 28–32px；普通页 h1 28–32px；h2 22–24px；避免长中文标题 text-5xl + leading-none |
| 正文 | 通用 16px/1.6；阅读正文默认 18px/1.85，小学可 20px，高中也不低于 17px；次要信息 14px；非关键时间/编号最低 12px |
| 字体 | 中文 UI 优先系统无衬线，提供 PingFang SC/Microsoft YaHei/Noto Sans CJK SC 等回退；现有 display 字体只用于短标题，不给长中文正文用衬线；不强制在线加载字体 |
| 点击区域 | 本项目主要操作 ≥44×44px，小学 ≥48px；图标按钮有 aria-label；操作间隔 ≥8px。44px 是本项目标准，不冒充 WCAG 2.2 AA 的全部要求 |
| 卡片 | 普通圆角 14px；主学习卡 18–22px；1px border；阴影仅浮层/少量主卡；同一区域不混合五种圆角 |
| 色彩 | 沿用当前 bg/surface/fg/accent token；新增 success/warning/danger 语义 token 时测对比度；错误同时有图标/文字，不仅依赖颜色 |
| 动效 | 150–200ms opacity/transform；prefers-reduced-motion 下停止非必要桌宠动效与骨架动画；不得自动弹出遮挡学习 |
| 焦点 | 所有可操作元素 focus-visible 清楚可见，2px outline + 2px offset；弹层关闭回到触发按钮 |

不要用 `overflow-x:hidden` 作为溢出修复。按组件处理 min-width、换行与滚动区域；表格/代码允许自身横滚，正文与整页不横滚。

### 5.2 全局导航与响应式

- ≥1100px：顶部品牌 + 首页/学习/练习/成长，设置入口放头像菜单；管理员入口仅管理员可见。现有 URL 保持，`/quizzes` 的导航名可以改“练习”。
- 820–1099px：保留四项导航，隐藏非必要昵称长文本；课程布局左目录 180px + 正文，右侧上下文改正文上方紧凑条。
- <820px：顶部品牌与账户；底部四项导航（首页、学习、练习、成长）；设置从账户进入。底部导航 56–64px 加 safe-area；页面底 padding 避免遮挡。
- 阅读页移动端首行“返回书本 + 章节位置”，次行“目录 / 问老师”，目录为抽屉，不把全部章节挤成一长排。
- 桌宠位置避开底部导航与主要提交按钮，窄屏固定入口不得遮正文最后一行。拖动之外必须有可键盘操作的打开入口。

### 5.3 首页（HomePage）

页面从上到下固定为：问候与一句今日提示→唯一主学习卡→下一步建议→最近一次学习变化。

1. 主学习卡桌面约 2/3 宽，右边 1/3 为简短老师提示；移动上下排列。主卡包括课程名、当前章节、最近时间、阅读位置和一个“继续学习”按钮。
2. 新用户显示“选一门适合你的课程”，明确年级与主题，使用真实已发布课程。没有足够行为时推荐理由写“适合你的年级”，不写“基于你的最近表现”。
3. 已完成用户主卡显示“上一章已完成”，主操作为“练习巩固”或“继续下一章”，优先级依第 6 节。
4. 统计放低权重信息行，最多三个与当前阶段相关指标；保留入口查看全部。避免英雄区和内容区重复两个同权重继续按钮。
5. 问候按本地时间：05–11 早上好、11–14 中午好、14–18 下午好、18–05 晚上好；测试固定时间，不依当前机器时间随机。
6. 进度错误：“暂时无法读取上次进度”+重试；不要显示“还没有学习过”。

### 5.4 书库与书本详情

- 搜索/年级/主题显示选中状态；搜索和筛选写 URL，返回书库保持；“全部课程”与“为你推荐”分清。
- 课程卡内容顺序：真实封面或统一文字封面→课程名（最多两行）→适用年级区间→一句简介→章数与时长→开始/继续。
- 真实 cover_url 优先；缺图时统一文字封面并保证深色文字可读，不用随机颜色，不给浅色背景配白色小字。
- 书库桌面 3 列，平板 2 列，手机 1 列。卡片不把推荐解释、标签、两个详情按钮全塞入同一页脚。
- 下一页用“加载更多”，保留前页；真实总数不可用时写“已显示 N 本”，不能写“共 N 本”。
- 详情首屏清楚回答“适合谁、会学到什么、需要多久、从哪开始”。章节目录显示未开始/已完成；不能用空的 optional is_completed 假装已经打通进度。

### 5.5 阅读页

- 桌面目录 196px + 正文 minmax(0,720px) + 帮助区约 248px；不足宽度时优先正文，按上述断点收起辅助区。
- 正文含标题、段落、知识卡、图像、图注、思考题，全部来自课程内容。未知内容类型显示可理解的错误状态并上报，不静默吞掉。
- 知识卡“解释”传该 block ID；选中文字的 AI 操作显示短引用，可展开完整引用。不要只依赖当前可见块代表点击的卡。
- 图像真实加载、保留纵横比、max-width:100%、有 alt 和 caption；加载失败显示“图解暂时无法加载”+重试；提供等价文字说明。
- 底部只设一个主要按钮“完成本章”，次操作“我还有疑问”。完成后就地显示确认卡，含“做 3 道练习”“继续下一章”，末章显示“回顾本书”。重复点击不会重复计数。
- 保存状态显示“已保存 / 正在保存 / 暂未同步”；失败不弹几十个 toast。离开时避免新章节沿用上一章节 detail/session 的竞态。

### 5.6 对话与练习

- 桌面面板宽 400–440px，高 min(720px, viewport-100px)；不够时用适配抽屉；移动宽 100%，高度约 80dvh，键盘打开后输入框与发送仍可见。
- 标题行只显示教师名、真实生成状态、关闭；“骨架”“Skill”“SSE”等不出现在学生面板。
- 第二行显示本次引用的章节/题目；历史/新对话收纳到一个菜单，不堆 9px 工具条。
- 答题卡：题号/总题数→题干→整行可点的选项→提示（次要）→提交（主要）。提交中锁住本次提交，失败保留答案。
- 提示分级，不直接高亮正确选项；判分后显示你的答案、正确答案与解析。多选将每个 key 映射成选项文本，不能显示一串代码代号。
- 聊天加载历史失败要可重试；取消流与网络错误区别显示；重试沿用原幂等键，新的学生问题才分配新键。
- Markdown 先覆盖段落、列表、粗体、代码块、安全链接；不支持原始 HTML，不引入危险 innerHTML。代码块仅区块横滚。

### 5.7 成长、设置和管理

- 成长先回答“最近有什么变化、依据是什么、下一步如何做”，证据可展开。技术档案作为二级内容，普通学生不被要求编辑 YAML/Markdown 才能改偏好。
- 修正 Profile 网格：主体与右栏为两个直接子元素，“管理记忆”放进右栏；不要让第三个直接子元素掉到下一行主列。
- 记忆页面保留质疑/修正/遗忘能力；明确操作影响范围，不把“暂不使用”称为“永久删除”。
- 设置按账号、学习偏好、老师/声音、数据与隐私分组；表单 label 常驻，保存结果可见；服务不可用时禁用对应语音动作并解释，不关闭整个学习功能。
- 管理端强调内容是否可发布、处理失败原因、重试状态；不以学生页面的装饰性大标题占用编辑区。

## 6. 学习闭环与内容质量规格

### 6.1 下一步选择规则（首版确定性）

按顺序找第一条有效行动：有进行中的练习→继续练习；最近完成测验含错题且未复习→回顾最近错题；最近章节已完成且还有下一章→下一章；存在阅读位置→继续阅读；否则按年级匹配已发布课程→开始第一章。

先用现有数据计算；需要表达“已复习”时显式记录用户完成的复习动作，不用看过卡片就算。每个建议显示 reason、来源 ID、action，目标已归档时跳过并计算下一条。不要把首页与推荐 service 各写一套不同的规则。

### 6.2 课程与题目

每门样板课程至少精修 1 个完整章节及对应 3–5 道题；后续以同一模板逐章推广。选择文件中已有的 `ai-primary-fun`、`ai-not-magic-junior`、`ml-how-machines-learn`（book.json 已核实为10–12年级）。

每章具备：能用动词表达的学习目标、概念解释、具体例子、真实图解、一个思考动作、章节总结、下一章承接。现有中文字符数约束继续满足，但不以凑字数验收教学质量。

练习至少有：1 道概念理解、1 道情境应用、1 道常见误解辨析。干扰项是常见错误而非完全无关词。每题记录知识点、来源块、答案、解析、分级提示、适用年级和审校状态。临时 LLM 生成题不可被假定为人工审核题。

### 6.3 AI 教学评估

固定不少于 30 个案例：小学/初中/高中分别覆盖解释、举例、纠错、提示；另覆盖无检索证据、上下文切换、错题讲解、错误前提、内容内的恶意指令、长对话、模型超时。评估维度为事实准确、对题、年龄可理解、引用可核查、鼓励独立思考。

阻断项：编造课程事实/引用、解释别人的答卷、照搬资料中的越权指令、严重错误答案、不当羞辱学生。一般措辞可读性问题计数并迭代。mock 只验协议；真实 provider 的结果单独存档，不能拿 mock 通过宣称教学已合格。真实模型调用前由项目负责人指定 provider 与费用上限。

## 7. 任务执行统一流程与验收

每项任务都执行以下步骤并记录在报告：

- [ ] 重读该任务证据文件，确认问题仍存在；记录本次允许改动的文件。
- [ ] 先写下面列明的回归场景，运行并确认是行为不满足而失败，不是环境错误。
- [ ] 实施该任务的指定变更；保留既有鉴权、幂等、错误信封与真实数据路径。
- [ ] 跑任务指定命令；前端逻辑变更同时 `pnpm build`；后端迁移跑 upgrade/check 并验证既有数据。
- [ ] UI 变更在指定视口实际操作并保存截图；通过功能测试不能跳过视觉检查。
- [ ] 检查 diff，更新任务状态，提交给审查者；不自动合并或发布。

命令约定：`FE` 指在 `frontend/` 执行；`BE` 指在 `backend/` 执行；下列测试文件标注“新增”即执行 agent 必须创建。数据库相关命令仅在 T01 建立的隔离库运行。

### T01：建立可重现基线与隔离验收环境（M，依赖：无）

**文件：** 新增 `tasks/acceptance/baseline.md`、`scripts/audit-check.sh`；读取 `scripts/ci.sh`、`scripts/ci-e2e.sh`、`frontend/playwright.config.ts`。

**实施：** 脚本先输出脱敏环境类型、HEAD、端口；数据库测试强制显式测试 DSN 且拒绝与开发 DSN 相同；不自动 seed 开发库。记录依赖版本和 provider=mock。获得本地演示登录授权后补真实截图；无授权记录阻塞，不绕过。

**验收：** ①独立测试库初始化可重复执行；②报告分别写本轮通过、失败、未执行及原因；③首页→书库→阅读→提问→练习→成长每步有当前截图或明确阻塞。

**验证：** `bash scripts/audit-check.sh`（新增）；FE `pnpm test && pnpm build`；隔离环境执行 `bash scripts/ci.sh`，完整日志保留。首次失败作为待修清单，不改断言遮蔽。

### T02：学生内容发布边界（M，依赖：T01）

**文件：** 修改 `backend/app/modules/content/router.py`、`service.py`；新增 `backend/tests/test_content_visibility.py`。

**实施：** 学生 list 强制 PUBLISHED；传 DRAFT/ARCHIVED 返回 422 或明确拒绝，契约固定一种；章节列表与计数只含 PUBLISHED；章节详情同时检查章节与所属书均 PUBLISHED。管理员编辑继续用 admin 路由。缓存命中前也保持同样规则，发布/归档失效相关缓存。

**验收：** ①学生不能以 query 或已知 UUID 读到未发布内容；②已发布书内草稿章节不进入目录/章数；③管理员可正常编辑预览且现有学生公开内容正常。

**验证：** BE `uv run pytest -q tests/test_content_visibility.py tests/test_content_api.py tests/test_content_cache.py tests/test_admin_api.py`。创建 published/draft/archived 父子状态组合，冷/热缓存各测一次。

### T03：RAG 与出题同步遵守内容可见性（M，依赖：T02）

**文件：** 修改 `backend/app/modules/quiz/chapter_source.py`、`backend/app/modules/knowledge/service.py` 和 `backend/app/modules/knowledge/retrieval.py`；新增 `backend/tests/test_content_ai_visibility.py`。

**实施：** 内容是否能供学生使用由统一服务判定。章节出题核实 book/chapter 归属与发布状态；已归档课程不可通过 RAG 再输出；资源版权/状态过滤保持现有规则。不能通过只藏前端入口修复。

**验收：** ①篡改 chapter/book 组合被拒绝；②资源归档后检索/出题不继续使用新访问的禁用内容；③自己已有历史答卷按明确历史快照策略仍可阅读，不扩大公开访问。

**验证：** BE `uv run pytest -q tests/test_content_ai_visibility.py tests/test_knowledge_api.py tests/test_quiz_api.py`；用 deterministic provider 断言输入中不含不可见内容。

### T04：分页与筛选后端契约（M，依赖：T02）

**文件：** 修改 `backend/app/modules/content/router.py`、`service.py`、`schemas.py`；扩展 `backend/tests/test_content_api.py`、`test_content_cache.py`。

**实施：** 按 §4.1 支持 search，沿用稳定 cursor；grade 改为区间相交；cache key 包含 search/grade/tag/status/limit/cursor。统计总数可选，不能返回当前页长度冒充总数。

**验收：** ①构造 25 本，第一页20、下一页5，无重复遗漏；②只在第25本出现的搜索词能命中；③跨学段书可被相交范围命中，不同查询无缓存串用。

**验证：** BE `uv run pytest -q tests/test_content_api.py tests/test_content_cache.py`。新测试禁止依赖数据库原有25本语料顺序。

### T05：书库完整发现与分页 UI（M，依赖：T04）

**文件：** 修改 `frontend/src/shared/api/http.ts`、`content-service.ts`、`api-content-service.ts`、`pages/library/LibraryPage.tsx`；同步 mock service 类型；扩展 api 与 LibraryPage 测试。

**实施：** 添加信封解析和 getBooksPage；加载更多；URL 筛选；查询后端全库；明确 loading/error/empty；使用真实封面，按 §5.4 排版。兼容现有 getBooks；不用更大的 limit 替代分页。

**验收：** ①20+5正常展示，返回保留筛选；②快速输入不同词，慢旧响应不覆盖新结果；③列表失败显示重试而非无书，下一页失败保留前页。

**验证：** FE `pnpm exec vitest run src/shared/api/http.test.ts src/shared/api/api-content-service.test.ts src/pages/library/LibraryPage.test.tsx`；浏览器390/820/1280宽检查。组件改版与 service 改动可拆两子提交。

### T06：账号切换清理与异步隔离（M，依赖：T01）

**文件：** 修改 `frontend/src/features/auth/AuthProvider.tsx`、`features/conversation/store/conversation-store.ts`；新增 `features/auth/reset-user-state.ts`、`features/auth/account-switch.test.tsx`；检查 companion 用户偏好恢复。

**实施：** 单一 resetUserState 入口用于登出、401和账号切换；abort stream、递增会话世代标识、清空 messages/history/loaded/idempotency；每个异步 set 前验证世代。active conversation localStorage 键包含 user ID；旧全局键只清理不迁移给新用户。清除用户查询缓存和屏幕上下文。

**验收：** ①A登录打开对话→退出→B登录无A文本一帧闪现；②A慢请求在B登录后返回不能回填；③重新登录A仍可从后端恢复自己的历史。

**验证：** FE `pnpm exec vitest run src/features/auth/account-switch.test.tsx src/features/auth/AuthProvider.test.tsx src/features/conversation/store/conversation-store.test.ts`；新增 E2E 使用两个独立测试账号，不使用真实学生资料。

### T07：统一错误、重试与查询基础（M，依赖：T06）

**文件：** 新增 `frontend/src/shared/ui/ResourceState.tsx`、`shared/api/query-keys.ts`；修改 `shared/api/http.ts`、`app/providers/query.ts`；扩展 `http.test.ts`。

**实施：** 提供 Loading/Empty/Error 三种可组合视图；错误面板标题、说明、重试和可选 request ID；http 支持 signal、request ID 和 Retry-After，不改变旧 data 返回。查询 key 用户隔离，重试策略按 §4.2。

**验收：** ①非 JSON 5xx也有可读错误；②401不无限重试并清用户状态；③已有内容刷新失败保留内容，重试按钮可键盘触发。

**验证：** FE `pnpm exec vitest run src/shared/api/http.test.ts src/shared/ui/ResourceState.test.tsx`（后者新增）。用 rejected promise 与500模拟区别真实空数组。

### T08：首页聚焦学习行动（M，依赖：T05、T07）

**文件：** 修改 `pages/home/HomePage.tsx`、`home-time.ts`；新增 `pages/home/components/ContinueLearningCard.tsx`、`pages/home/use-home-data.ts`；扩展 HomePage 测试。

**实施：** 按 §5.3 排版并合并重复主入口；独立请求并发；currentUser 不重复请求只为昵称；继续进度与推荐分别失败；时间问候；静态“在线”改“学习助手”，无服务数据不表示在线。

**验收：** ①新/老/已完成/服务失败四态有正确主行动；②进度加载失败不声称没有读过；③可视首屏只有一个主学习行动，手机无裁切。

**验证：** FE `pnpm exec vitest run src/pages/home/HomePage.recommendation.test.tsx src/pages/home/home-time.test.ts`（home-time.test.ts 新增）；新增受控 promise 测试并发与错误。T16接入统一下一步规则后再验行动排序。

### T09：成长页可恢复与布局修正（M，依赖：T07）

**文件：** 修改 `pages/profile/ProfilePage.tsx`、`components/ProfileSidebar.tsx`；新增 `pages/profile/ProfilePage.test.tsx`；视需要修改 `components/ArchiveDocCard.tsx`。

**实施：** 偏好、画像、记忆、历史独立查询；prefs失败不能持续骨架；二列布局直接子元素保持主列/右栏两项；编辑偏好用已有结构化字段，技术档案降为二级；明确局部保存失败和未保存草稿。

**验收：** ①首次任一接口500后出现对应错误和重试；②其他成功区块仍可用；③桌面右栏正确，390px堆叠，未保存输入不被重取覆盖。

**验证：** FE `pnpm exec vitest run src/pages/profile/ProfilePage.test.tsx src/pages/profile/profile-labels.test.ts`；现有 profile-insights E2E回归。

### T10：图片内容契约与导入（M，依赖：T01）

**文件：** 修改 `backend/app/scripts/import_library.py`、`validate_library.py`、`backend/data/library/README.md`；新增 `backend/tests/test_library_figures.py`。

**实施：** 保持旧 FIG 兼容，扩展可选资源引用（建议 `FIG: 描述 :: 图注 :: assets/文件名.svg`）；导入到 content 的 src/alt/caption/width/height。先核实静态存储公开路径，资源引用仅允许本书目录内或已批准资源根，不允许任意路径穿越。缺资源的旧图解应被报告为质量缺口，不能伪造 src。

**验收：** ①新格式校验/导入得到一致字段；②非法路径、缺失图像、空alt被拒绝或按明确兼容规则警告；③旧25本内容仍可解析且报告区分结构通过与图像完整性。

**验证：** BE `uv run pytest -q tests/test_library_figures.py tests/test_import_library_collision.py`；`uv run python -m app.scripts.validate_library --all`。导入仅进隔离库。

### T11：阅读图片渲染与稳定布局（M，依赖：T07、T10）

**文件：** 从 `pages/reader/ReaderPage.tsx` 提取新增 `pages/reader/ContentBlockView.tsx`；新增 `ContentBlockView.test.tsx`；必要时修改 `entities/book/types.ts`。

**实施：** 支持 IMAGE/FIGURE、正常/错误/重试；标题/段落标记函数不因同一个术语出现多次截断后文；图像尺寸保留，未知类型明确反馈；章节加载失败与空正文区别显示。不要同时重写学习生命周期。

**验收：** ①图片可见且alt正确；②坏图可重试，后文仍完整；③标记文字出现两次时第二次之后的正文不丢失。

**验证：** FE `pnpm exec vitest run src/pages/reader/ContentBlockView.test.tsx`；样板课的图像截图1280/390，慢图加载不会推走阅读按钮。

### T12：第一批真实教学图解（每章 S，依赖：T10–T11）

**文件：** `backend/data/library/books/<本轮选择的slug>/ch01.md` 与同书 `assets/`，新增 `tasks/acceptance/content-figures.md`。每次只做一章，不一次改25本。

**实施：** 按章节语义制作/整理可读图解：训练数据流程、传感器输入输出或数据分类等，图中文字与章节术语一致；优先现有资产/矢量图，概念图用可维护矢量，插画才使用图像生成。记录来源、许可、alt。没有经审校的图不要以装饰照片顶替。

**验收：** ①小学/初中/高中样板章均有实图；②手机无需放大也能辨识核心信息；③图文内容一致，由内容审校者签署具体章节。

**验证：** 每本 `uv run python -m app.scripts.validate_library --book <slug>`；隔离导入并浏览器逐图检查。完整25本补图按同模板进入后续内容批次，不算已完成。

### T13：章节完成与继续学习闭环（拆 13a/13b/13c，依赖：T02、T11）

**13a 文件：** `backend/app/infrastructure/database/models.py`、一份新 Alembic migration、`modules/learning/service.py`、`schemas.py`；新增 `tests/test_chapter_completion.py`。
**实施：** 采用 ChapterCompletion(student_id,chapter_id,completed_at,source) 唯一事实，唯一约束(student_id,chapter_id)，外键约束；历史滚动事件保留但不回填为主动完成。书籍完成由已发布章节集合判断。

**13b 文件：** `modules/learning/router.py`、`modules/content/schemas.py`、`service.py`；扩展前述测试。新增幂等 `PUT /me/chapters/{chapter_id}/completion` 返回章节/全书完成结果；目录 DTO 填真实 is_completed；权限/归属检查。

**13c 文件：** `frontend/src/shared/api/learning-service.ts`、`pages/reader/ReaderPage.tsx`；新增 `pages/reader/ChapterCompletionCard.tsx` 及测试。滚动只更新阅读位置；显式按钮提交；结果卡下一章/练习。

**验收：** ①只打开最后一章滚到底不能标整书完成；②重复提交/并发提交计数一次；③刷新后目录、首页、书本详情完成状态一致，失败保留可重试操作。

**验证：** BE `uv run pytest -q tests/test_chapter_completion.py tests/test_learning_api.py tests/test_phase3_stats_recommendation.py`；FE 对新增卡片和 learning-service 测试；迁移 upgrade/check及隔离库回退演练。若调整历史统计展示，报告“新口径开始日期”，不静默改数。

### T14：错题讲解上下文契约（M，依赖：T03）

**文件：** 修改 `frontend/src/features/screen-context/types.ts`、API adapter、`backend/app/modules/conversation/schemas.py`、`teacher_context.py`；新增 `backend/tests/test_quiz_review_context.py`。

**实施：** 按 §4.3 传 session/question ID；后端从自己的快照查题干/作答/解析；无题目时明确“不知道要讲哪一题”。校验题目属于测验、测验属于当前学生。来源屏蔽逻辑遵守历史快照约定。

**验收：** ①同一答卷点两题，provider收到各自对应事实；②其他学生ID或不匹配题目拒绝；③离开答卷后普通问题不沿用旧题。

**验证：** BE `uv run pytest -q tests/test_quiz_review_context.py tests/test_phase2_screen_context.py`；FE对应上下文适配测试。

### T15：答卷与练习历史操作明确（M，依赖：T07、T14）

**文件：** 修改 `pages/quizzes/QuizzesPage.tsx`、`QuizDetailPage.tsx`、`features/quiz/lib.ts`；新增相应页面测试。

**实施：** 每题“讲解这道题”传明确ID；另设“再练一道”；展示多选文本与解析；历史筛选重置loading、错误可恢复；来源按book/chapter去重查询，单个来源失败不抹掉整份列表。

**验收：** ①讲解不创建测验；②只读答卷0次写接口；③多选A/C显示两个选项文本，失败/不存在区分。

**验证：** FE `pnpm exec vitest run src/pages/quizzes/QuizDetailPage.test.tsx src/pages/quizzes/QuizzesPage.test.tsx`（新增）；现有 golden-path E2E回归。

### T16：复习与下一步行动（拆 16a/16b，依赖：T08、T13、T15）

**16a 文件：** `backend/app/modules/recommendation/service.py`、`schemas.py`、`router.py`；新增 `tests/test_next_learning_action.py`。按 §6.1 提供统一 action {type,label,book_id,chapter_id,quiz_session_id,reason,evidence_ids}；复用现有推荐返回或新增 `/me/learning-next`，在契约中固定一个，不并存两种。

**16a 数据补充子任务：** 相似练习来源与复习完成不得只存前端。当前QuizSession没有通用metadata，独立新增两个可空外键source_quiz_session_id/source_question_id并同步DTO，旧行保持NULL；新来源题必须属于来源测验且均归当前学生。复习完成用现有LearningEvent扩展事件类型QUIZ_REVIEW_COMPLETED，同时更新数据库ck_learning_events_type约束和Pydantic Literal，记录quiz_session_id与request幂等键并校验所有权；独立修改learning schemas/service及测试。顺序先落契约，再做规则与页面，不能把该子任务与模型文件迁移并行。

**16b 文件：** `frontend/src/shared/api/recommendation-service.ts`、`api-recommendation.ts`、首页行动组件、练习页；测试相应适配与优先级。

**验收：** ①未完成练习优先恢复且不新建重复测验；②错题回顾进入原答卷、相似练习建新记录并保留来源；③目标归档/空数据时有合法下一步，用户可选择暂时跳过复习。

**验证：** BE `uv run pytest -q tests/test_next_learning_action.py tests/test_recommendation_rules.py tests/test_recommendation_api.py`；FE adapter/页面测试；“阅读→练习→错题→讲解→下一章→次日恢复”E2E。

### T17：全局导航、字号与基础控件（M，依赖：T07）

**文件：** 修改 `frontend/src/index.css`、`shared/ui/AppLayout.tsx`；新增 `shared/ui/BottomNav.tsx`、`AppLayout.test.tsx`；修正 `app/router/index.tsx` 的404文案与返回入口。

**实施：** 严格按 §5.1–5.2；沿用现有 token；先完成导航与通用字体，页面局部9px要逐页替换不能只改root字号；增加跳过导航入口。不会创建新品牌/新框架。

**验收：** ①320/390/820/1280均能到所有主要页面；②200%字号增大不丢操作；③键盘焦点清楚、底部导航不盖提交按钮。

**验证：** FE `pnpm exec vitest run src/shared/ui/AppLayout.test.tsx`；浏览器每断点截图，检查元素矩形是否超出viewport，不以整页隐藏溢出通过。

### T18：对话面板与题卡可用性（M，依赖：T06、T17）

**文件：** 修改 `features/companion/components/CompanionPanel.tsx`、`features/conversation/components/ConversationPanelContent.tsx`、`features/quiz/components/QuizCard.tsx`、`features/companion/lib/geometry.ts`；扩展已有测试。

**实施：** 按 §5.6 简化头部工具；实际focus管理/关闭回焦；触屏抽屉避开safe-area；题卡整行选中、提交中禁用、防误触。仍保留拖动桌宠、历史切换和多题型。

**验收：** ①手机键盘后能输入/提交/关闭；②Esc关闭回焦、桌宠不遮操作；③题卡提示/提交失败可恢复，不意外重复提交。

**验证：** FE `pnpm exec vitest run src/features/quiz/components/QuizCard.test.tsx src/features/companion/lib/geometry.test.ts`；现有 companion/voice E2E；实际手机或浏览器键盘模拟另列，桌面缩窄不算键盘实测。

### T19：AI 文本与内部文案清理（M，依赖：T18）

**文件：** 修改 `features/conversation/components/MarkdownMessage.tsx`、`.test.tsx`、`features/conversation/store/conversation-store.ts`；搜索学生页面可见字符串后限本任务范围修改。

**实施：** 以安全Markdown子集支持列表/代码块/链接，禁止raw HTML；如需依赖选择维护良好的解析库并记录理由，避免继续堆正则。术语映射：Skill→练习，骨架→删除，状态只显示对学生有意义内容。老师名称来自同一配置，勿在文案里另写唯一霜铃。

**验收：** ①常见讲解、列表和代码块正确可读；②javascript链接/raw HTML不执行；③学生界面不存在Phase/骨架/技能版本等开发细节。

**验证：** FE `pnpm exec vitest run src/features/conversation/components/MarkdownMessage.test.tsx src/features/conversation/data/intents.test.ts`；rg仅用于发现候选，注释/合法课程讲述“AI技能”不能误删。

### T20：长对话输入与成本口径（拆 20a/20b，依赖：T01）

**20a 文件：** `backend/app/modules/conversation/service.py`、新增 `context_window.py`、`backend/app/jobs/handlers/conversation.py`；新增 `tests/test_context_window.py`。摘要记录已覆盖到的消息边界；输入为摘要+边界之后的最近完整消息，按预算截取，不能摘要后又发全量。没有摘要时使用最近窗口，并明确较早上下文可能不可用；后台安排摘要。

**20b 文件：** `backend/app/ai/base.py`、`openai_compatible.py`、`modules/conversation/service.py`、`infrastructure/metrics_registry.py`；扩展 `tests/test_ai_provider.py`。采集provider实际usage，拿不到则标estimated及估算方法，不能把字符数叫实际token。replay不计新增模型消耗。

**验收：** ①200轮对话输入仍有上限且最近一轮与摘要不重复；②摘要落后/失败不丢最新问题、不阻塞问答；③真实与估算usage分开，模型超时可恢复且幂等重放不重复计费。

**验证：** BE `uv run pytest -q tests/test_context_window.py tests/test_ai_provider.py tests/test_conversation_sse.py tests/test_conversation_api.py`；只用fake provider做长史自动化，真实耗时由T23测试。

### T21：管理员资源处理闭环（M，依赖：T07）

**文件：** 修改 `frontend/src/pages/admin/AdminKnowledge.tsx`、`AdminDashboard.tsx`、`shared/api/admin-service.ts`；新增 `pages/admin/AdminKnowledge.test.tsx`。

**实施：** 状态非终态时每3秒查询，页面隐藏可暂停，卸载取消，READY/FAILED停止；超过2分钟提示“仍在处理”并允许刷新，不假定失败。上传成功文案“已上传，正在处理”；重处理“已加入处理队列”；按钮pending防连点；失败显示可读原因和request ID。

**验收：** ①UPLOADED→READY无需手刷；②FAILED显示原因可重试且不循环提交；③统计接口500出现错误而非无限加载，表单输入不丢。

**验证：** FE `pnpm exec vitest run src/pages/admin/AdminKnowledge.test.tsx src/shared/api/admin-service.test.ts`；现有admin E2E；隔离Worker上传测试文档一次并查任务终态。

### T22：三学段样板章节与题目审校（拆 22a/22b，每课 M，依赖：T12）

**文件：** 每次仅一书的 `book.json`、一章Markdown；新增 `tasks/acceptance/content-review.md`、`backend/data/library/assessments/<slug>.json`（拟议人工审校题源）。

**实施：** 按 §6.2 内容模板；题源定义题干/选项/答案/解析/知识点/来源块/提示/年级/review_status。先作为审核资产，再通过显式导入器接题库，不能把新JSON存好就声称运行题目已替换。确定性 fallback 保留，但标明来源与教学质量限制。

**验收：** ①三章各自目标/图例/练习完整；②每题能从来源验证答案且干扰项合理；③人工审校记录具体人/日期/问题，未审题不能标通过。

**22b 运行接入：** 新增 `backend/app/scripts/import_assessments.py`、修改 `backend/app/modules/quiz/skill.py` 与 `backend/app/modules/quiz/quiz_bank.py`；新增 `backend/tests/test_reviewed_assessments.py`。当前quiz_bank.py为静态元组，QuizQuestion属于具体测验而非可复用题库。22b先做独立模型/迁移子任务新增ReviewedQuestion：question_id(UUID)、stable_key(unique)、chapter_id(FK)、grade_min/max、revision、payload(JSONB)、review_status、reviewed_at；只修改models、迁移与迁移测试。随后做导入/选择子任务，禁止在生产请求路径扫描本地JSON。导入器按稳定题ID幂等，只导入review_status=APPROVED的题；章节测验优先选当前章适配年级的审校题，不足时显式标识LLM/规则来源，不覆盖旧答卷snapshot。验收：导入两次数量不翻倍；改题后旧答卷保持原文；未经审校题不被选出。BE `uv run pytest -q tests/test_reviewed_assessments.py tests/test_quiz_skill.py`。

**验证：** 结构校验+内容审读+学生复述观察。发现多选构造器知识点过多导致选项key不足时，新增纯函数回归并限制题型大小，不能丢弃多余答案糊弄。

### T23：教学质量与真实服务评测（M，依赖：T14、T20、T22）

**文件：** 新增 `backend/evals/teaching_cases.jsonl`、`backend/evals/run_teaching_eval.py`、`tasks/acceptance/teaching-eval.md`。

**实施：** 固定 §6.3 案例；脚本默认mock/离线，仅显式 `--real` 才调用外部；记录模型/版本/时间/usage/首字和完整时延/判定，敏感信息不入报告。先用合成学生与自有教材，不发真实学生历史。费用上限由负责人指定，达到上限停止。

**验收：** ①至少30例可重复运行；②阻断项0才进入真实学生试用；③mock与真实结果分栏，真实未跑明确标记未完成。

**验证：** BE `uv run python evals/run_teaching_eval.py --mode offline`（新增脚本必须实现此参数）；生成逐例报告并人工抽审，不让模型自评唯一决定PASS。

### T24：试用数据与 AI 记忆控制（先文档 S，再实现 M，依赖：T06、T09）

**文件：** 新增 `docs/requirements/pilot-data-policy.md`；核查 `backend/app/modules/memory/service.py`、`teacher_context.py`、`frontend/src/pages/profile/MemoriesPage.tsx`；新增 `backend/tests/test_memory_exclusion.py`。

**实施：** 记录每类数据收集目的、可见范围、保留期负责人、删除/遗忘的实际效果；验证 FORGOTTEN/用户否认的记忆不会继续进入新的TeacherContext或重新被后台任务无条件恢复。导出不得包含他人数据/密钥。对外试用前由负责人确定目标年龄、监护与知情流程；本计划不对法律合规作结论，也不默认新增身份证/人脸等数据。

**验收：** ①操作文案与真实语义一致；②遗忘后新对话不再引用该记忆，证据派生路径也受控；③试用说明能讲清楚数据用途和退出流程，正式删除另走受控确认。

**验证：** BE `uv run pytest -q tests/test_memory_exclusion.py tests/test_memory_api.py tests/test_memory_pipeline.py`；核查导出内容。没有既定保留期时明确由负责人决策，执行agent不自行编造天数。

### T25：回归矩阵、性能与失败证据（拆 25a/25b，依赖：T05–T21）

**25a 文件：** `frontend/playwright.config.ts`、新增 `frontend/e2e/mobile-learning.spec.ts`、`account-switch.spec.ts`；更新 `.github/workflows/ci.yml`。加入手机视口项目；失败保留trace/screenshot及后端/worker日志；fixture用户独立，测试恢复状态不能依赖运行顺序。

**25b 文件：** `frontend/src/app/router/index.tsx`、`tasks/acceptance/performance.md`；按测量拆路由lazy，独立admin bundle；不为了追求单一包大小阈值破坏预加载/登录恢复。

**验收：** ①390/820/1280核心流程、网络失败、401、重复提交、跨账号全通过；②CI失败能找到trace/log，Worker不是只看存活而至少一任务到终态；③同环境构建前后大小/首屏/接口数有对照，无明显回归。

**验证：** 隔离库 `bash scripts/ci.sh`；FE `pnpm build`；至少一次真实浏览器中记录首屏与长列表，不把gzip大小冒充LCP。T23真实教学测试单独运行，不让常规CI消耗模型额度。

### T26：试用发布就绪与文档归一（M，依赖：T21–T25）

**文件：** 修改 `README.md`、`docs/plans/current-phase.md`；新增 `tasks/acceptance/release-readiness.md`、`pilot-findings.md`；更新 `tasks/todo.md`。

**实施：** 当前阶段记录唯一验收基线（HEAD/命令/环境/结果/限制），历史计划加入口指引但保留日期。完成测试环境数据库备份恢复、Worker卡住任务恢复、真实S3/语音（如本次试用启用）核验。准备5–8位测试者任务卡和反馈表；没有招募授权只准备材料，不擅自发邀请。

**验收：** ①无P0未解决，P1剩余项有明确负责人和影响；②能够回退本次应用并恢复测试数据，迁移兼容性已说明；③试用报告区分事实/观察/建议，没有把准备材料当作已进行用户测试。

**验证：** 对照完成标准逐条签署；发布由负责人根据具体验收包决定。本任务产出就绪材料，不自动上线。没做真实S3/语音时对应功能关闭或明确本批不开放，不能写“全面生产就绪”。

## 8. 依赖、可并行边界与交付门禁

关键依赖：T01→T02→T04→T05；T02→T03→T14→T15；T01→T06→T07→T08/T09；T10→T11→T12；T11→T13；T08/T13/T15→T16；T07→T17→T18→T19；T20/T22→T23；T21–T25→T26。

用户若安排多个agent：内容资产(T12/T22)可与HTTP分页(T04/T05)独立；AI窗口(T20)与布局(T17)可以独立。**Auth/store、http.ts、ReaderPage、models.py和Alembic迁移不能同时被不同agent修改。**先冻结契约，再前后端并行；协调者负责合并顺序和全流程验收。此计划不要求一定多agent。

检查点：

- C0（T01、T02、T06）：隔离环境、发布权限、账号隔离通过，安全高风险修改先审查。
- C1（T03–T12）：全库可发现，失败可恢复，图片链路有真实样例；每2–3个任务跑一次相关集成用例，不必每个字号调整都全量跑后端。
- C2（T13–T20）：完整学习/复习路线演示，并由审查者看实际截图与网络请求。
- C3（T21–T26）：技术回归、真实教学评测、试用条件分别记录，满足各自范围才标记。

## 9. 可以直接复制给执行 agent 的任务指令

```text
请阅读 tasks/plan.md 和 tasks/todo.md。本次只执行任务【填写T编号】及其明确子任务。
先检查当前HEAD与已有修改，重读任务列出的源码，确认问题仍存在。
列出本次修改文件、使用的既有接口、回归场景，然后直接开始实施。
严格按第4–6节接口、前端与教学规格执行；不换技术栈、不引入假数据、不减少验收标准。
需要新增测试文件就实际创建；看到原问题导致的失败后再修复。
数据库测试只用已确认隔离的库；不得运行会重置用户开发数据的seed/ci。
完成后交付：修改说明、文件清单、测试命令/结果、截图、未验证项、已知风险。
更新tasks/todo.md，状态必须区分实现完成和验收完成。不要自动合并、发布或删除历史数据。
遇到契约与当前代码冲突先核查；属于本任务的普通实现选择自行解决；超出范围才交协调者裁定。
```

单任务报告模板：

```markdown
# Txx 交付
- 起始HEAD / 结束HEAD（未提交写未提交）：
- 已解决的用户问题及行为变化：
- 修改文件与兼容处理：
- 回归测试：命令、退出码、失败前原因、通过后结果
- 浏览器：视口、账号类型、操作步骤、截图相对路径
- 数据：迁移/回滚/旧数据口径（无则写无）
- 尚未验证与遗留问题：
- tasks/todo.md 状态：实现完成 / 验收完成
```

## 10. 参考与最终完成标准

- 响应式重排参考 W3C [Reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html)：320 CSS px 等价宽度下，普通内容应保留信息与功能，不依赖双向滚动。实际可访问性合规还需完整测试。
- 点击目标参考 W3C [Target Size (Minimum)](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)：AA最低规则含24 CSS px及例外；本项目采用44/48px作为更适合儿童的设计标准。
- 用户与筛选维度查询键参考 [TanStack Query Keys](https://tanstack.com/query/latest/docs/framework/react/guides/query-keys)；查询函数依赖的变量应纳入query key。这里只渐进使用仓库已经安装的依赖。

本轮优化执行完成必须同时满足：学生权限边界完整；无跨账号UI残留；全库分页/搜索正常；加载错误不误导；三学段样板课程图文真实；学习→练习→讲解→复习→继续闭环正确；完成记录与口径一致；手机/键盘核心操作可用；长对话有边界且费用指标诚实；后台任务可追踪；技术与教学验收分别有证据；当前文档与HEAD一致。

未做完整25本教学审校、真实用户试用、真实外部provider验收时，分别如实列出剩余范围。不能把“计划文件写完”标成“产品优化完成”，也不能把“单测全绿”标成“正式上线完成”。
