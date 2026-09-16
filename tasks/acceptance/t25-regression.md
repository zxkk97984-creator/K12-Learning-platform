# T25 · 回归矩阵、性能与失败证据

> 日期：2026-09-07。任务 T25（拆 25a/25b，依赖：T05–T21）。

## T25b · 按测量拆分路由 lazy + 独立 admin bundle（性能）

- `frontend/src/app/router/index.tsx`：页面组件改 `React.lazy` + `Suspense`（`withSuspense` helper）；`AppLayout`/登录页保持即时预加载与登录恢复；Admin 独立成包。
- 构建前后对照（同环境 `pnpm build`）：

| 项 | 拆分前 | 拆分后 |
|---|---|---|
| 主入口 js | 517.26 kB（gzip 151.17 kB） | **272.40 kB**（gzip 85.50 kB），**-45%** |
| admin 包 | 并入主 bundle | 独立 `admin-*.js` **18.15 kB**（gzip 4.91 kB） |
| >500 kB 警告 | 有 | 无 |
| 逐页 chunks | 单个大包 | 每页 4.2–25.3 kB 按需加载 |

- 证据：`tasks/acceptance/performance.md`（含首屏/接口数说明，真实 LCP 由 25a 浏览器回归记录，未以 gzip 大小冒充）。

## T25a · 手机视口项目 + 回归规格 + CI 改进

**文件：**
- `frontend/playwright.config.ts`：新增 mobile-390 / tablet-820 / desktop-1280 视口项目（均基于 chromium；`isMobile`/`hasTouch` 显式设定，不依赖 webkit 设备描述符）。视口敏感 specs（`mobile-learning`、`account-switch`）跑全部项目；既有桌面 specs 仅 `chromium` 项目跑，避免手机导航隐藏误报。失败保留 trace (`retain-on-failure`) + screenshot (`only-on-failure`)。
- `frontend/e2e/mobile-learning.spec.ts`（新增）：核心流程 / 网络失败 / 401 / 重复提交，全部项目运行。
- `frontend/e2e/account-switch.spec.ts`（新增）：学生↔管理员真实登录切换，无跨账号状态残留。
- `.github/workflows/ci.yml`：
  - 后端 Worker smoke 从"进程存活"升级为"至少一个任务到终态"：入队 `memory_consolidation` 并轮询 `background_jobs` 至 `success/failed`。
  - E2E 失败时上传 Playwright trace/screenshot 及后端/worker 日志 artifact（`actions/upload-artifact`）。

**真实修复（非仅记录，含前置复现）：**
- 对话面板定位器陈旧：`golden-path`/`companion-sprite` 用 `getByRole('complementary')`，但面板为 `role="dialog"`（CompanionPanel）。改为 `dialog`，测试方恢复通过。
- 导航链接陈旧：`golden-path` 用 `link 测验`，现导航项为「练习」（→/quizzes）。改用 `练习`。
- **重复提交真实缺陷**：`ChatComposer` 发送按钮无在途守卫，快速双击 `submit()` 触发两次 `sendMessage` → 落库两条同内容用户消息。新增 `sendingRef` 守卫 + `disabled` 发送按钮（`disabled:opacity-50`）。E2E 以拦截 `**/conversations/*/messages` POST 计数断言只放行一次。
- **CompanionDock 遮挡主按钮**：常驻浮动 dock（140×168，`fixed z-40`）盖住设置页「保存设置」。容器改 `pointer-events-none`，按钮 `pointer-events-auto` 且命中区收窄至精灵本体，透明边距对底层内容透传。修复后 `grade-persistence`/`voice-preference` 回到通过。
- `prepareContinueLearning` helper 选章节：跳过空 `content_blocks` 章节（避免空章节导致测验 `QUIZ_SKILL_ERROR`），并优先选内容确有的章节。

## 回归矩阵（全项目，隔离库）

| 规格 | chromium | mobile-390 | tablet-820 | desktop-1280 |
|---|---|---|---|---|
| account-switch · 学生→管理员 | ✓ | ✓ | ✓ | ✓ |
| account-switch · 管理员→学生 | ✓ | ✓ | ✓ | ✓ |
| mobile-learning · 核心流程 | ✓ | ✓ | ✓ | ✓ |
| mobile-learning · 网络失败+重试 | ✓ | ✓ | ✓ | ✓ |
| mobile-learning · 401 失效 | ✓ | ✓ | ✓ | ✓ |
| mobile-learning · 重复提交(连点) | ✓ | ✓ | ✓ | ✓ |
| golden-path（学习→练习→讲解→复习） | ✓ | n/a | n/a | n/a |
| companion-sprite | ✓ | n/a | n/a | n/a |
| grade-persistence / voice-preference | ✓ | n/a | n/a | n/a |
| memory-flow | ✓ | n/a | n/a | n/a |
| login-flow / admin / profile-insights / teacher-role | ✓ | n/a | n/a | n/a |

> 全量：**33 passed**（chromium 11 + mobile-390 6 + tablet-820 6 + desktop-1280 6 + 桌面附加）。workers=1 串行，避免共享 seed 账号/真实 DB 状态竞争。

**环境说明：** E2E 在隔离库 `shuangling_audit` 上运行。之前出现的失败（核心流程选中「AI 可见性测试书」、golden-path `QUIZ_SKILL_ERROR`（空章节）、memory-flow 记忆被先跑遗忘）均为**隔离库被后端 pytest 的 fixture 书籍污染**所致；重置为干净态（drop→migrate→content-init→seed）后全绿。属测试隔离问题，非产品功能缺陷。

## 单元/构建门禁

- 后端 `uv run pytest -q` → **384 passed**（隔离库 `shuangling_audit`）。
- 前端 `pnpm test` → **258 passed**（49 files）。
- 前端 `pnpm build` → 无 >500 kB 警告（主 bundle 272 kB，独立 admin 18 kB）。
- 前端 `pnpm exec tsc --noEmit` → 0 错误。
- `.github/workflows/ci.yml` YAML 校验通过。
- CI worker smoke 脚本导入路径（`app.infrastructure.database.session.async_session`、`hash_password`）验证可解析。

## 真实浏览器（非生成图）

- 截图来自真实运行页面：`test-results/**/test-failed-*.png`（失败保留）、trace.zip。视口 390/820/1280 均覆盖于全项目回归。
- 未将 gzip 大小冒充 LCP；首屏 LCP 由 25a 浏览器回归覆盖（构建大小对照见 performance.md）。

## 未决 / 外部

- 真实付费模型评测（T23）与人工审校签署仍待外部授权/预算，不在本任务范围。
- CI 云端运行（GitHub Actions service container 同一套 `DATABASE_URL`）本任务在本地对标 `ci.sh`/`ci-e2e.sh` 验证；云端上传 artifact 逻辑按 workflow 代码交付，未在云端实际触发（本地无 GitHub runner）。
