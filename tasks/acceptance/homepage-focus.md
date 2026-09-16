# T08 · 首页聚焦学习行动

> 日期：2026-09-06。任务 T08（M，依赖：T05、T07）。

## 已解决的用户问题与行为变化

首页重复入口、误导性空态、静态"在线"的问题已修复，按 §5.3 聚焦到一个学习行动：

- **时段问候**：`greetingForHour(hour)` 纯函数：05–11 早上好、11–14 中午好、14–18 下午好、18–05 晚上好；可测（`home-time.test.ts` 用固定时间断言），不依机器时间随机。
- **页面结构**：问候与今日提示 → 唯一主学习卡（2/3）→ 老师提示（1/3，移动端上下堆叠）→ 下一步建议 → 最近一次学习变化。首页不再重复"继续学习/聊天"两个同权重入口。
- **主学习卡四态**：加载 / 进度失败（明确"暂时无法读取上次进度"而非"还没有学习过"）/ 新用户（"选一门适合你的课程"）/ 进行中（书名+章节+位置+最近阅读+唯一"继续第 N 章"主行动）/ 已完成（"上一章已完成"+主行动改"继续下一章"）。
- **老师提示"学习助手"**：静态"在线"改"学习助手"，无服务数据不表示在线；`CompanionSprite` label 用教师名。
- **统计降为低权重**：最多三个与当前阶段相关指标（学习天数/累计分钟/测验次数）+ "查看全部"入口。
- **独立并发请求**：`use-home-data.ts` 用 fetch 并发、独立失败；stats/继续进度/情节/记忆/测验/推荐各自失败不影响其他片区；currentUser 只用于昵称初始值，不再重复 getMe 只为昵称（getMe 仍取统计，独立于推荐）。

## 修改文件

| 文件 | 改动 |
|---|---|
| `frontend/src/pages/home/home-time.ts` | 增 `greetingForHour` |
| `frontend/src/pages/home/home-time.test.ts`（新增） | 时段问候 + formatNow 固定时间断言 |
| `frontend/src/pages/home/use-home-data.ts`（新增） | 首页数据并发独立请求 + 独立错误标志 |
| `frontend/src/pages/home/components/ContinueLearningCard.tsx`（新增） | 主学习卡四态 |
| `frontend/src/pages/home/components/ContinueLearningCard.test.tsx`（新增） | 5 项：加载/失败/新用户/进行中/已完成 |
| `frontend/src/pages/home/HomePage.tsx` | 按 §5.3 重排；问候、主卡、下一步建议、统计≤3、最近变化 |
| `frontend/src/pages/home/HomePage.recommendation.test.tsx` | 问候断言改由 `greetingForHour` 计算（时间不敏感） |

## 回归测试

```bash
cd frontend && pnpm exec vitest run src/pages/home/
# 3 files / 18 passed
pnpm test    # 全量：42 files / 215 passed
pnpm build   # 通过
```

## 浏览器实测（localhost:5175 → :8002，xiaoming）

- 1280：问候（"晚上好，小明。"——按当前 23:48 时段正确）+ 唯一主学习卡"第 1 章 · 第一章"、"继续第 1 章 →"、55%、最近阅读；老师提示"学习助手"+"问问霜铃"；下一步建议（真实推荐+理由+打开书+不感兴趣）；统计 3 指标；最近变化（时间线/最近测验/AI 记得什么）。
- 390：主卡与老师提示上下堆叠。
- 截屏：`tasks/acceptance/08-home-1280.png`、`08-home-390.png`（真实运行页面）。

## 尚未验证 / 遗留

- "已完成用户主行动"（上一章已完成→下一章/练习）在当前账号未达全书完成态，逻辑以 `ContinueLearningCard.test.tsx` 覆盖；真实全书完成态在 T13 章节完成闭环验证。
- 下一步行动的**统一规则**（继续练习/错题回顾/下一章/继续阅读优先级）由 T16 接入；首页当前显示推荐（规则推荐），T16 后替换为统一 next-learning-action。
- 首屏性能/长列表首屏测量在 T25。

## tasks/todo.md 状态

实现完成 / 验收完成（前端 215 passed + build；真实浏览器 1280/390 截图）。
