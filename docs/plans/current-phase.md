# 当前阶段状态（Phase 5-B-II 实测收口）

> 本文件以 2026-08-25 工作区实际代码与本次验收实测为准。

## 迁移
- Alembic head：`d4e5f6a7b8c9`（补齐 reading_settlements.session_id → learning_sessions FK，RESTRICT）
- `alembic check`：No new upgrade operations detected（仅剩 student_episodes.embedding 的 pgvector 类型识别 INFO，属 autogenerate 已知限制）

## 测试基线（本次实测）
- 后端 pytest：**311 passed / 0 failed**
- 前端 Vitest：**191 passed / 0 failed**（38 files）
- 前端 tsc --noEmit / pnpm build：通过
- E2E Playwright（scripts/ci-e2e.sh，真实后端+Redis）：**9 passed / 0 failed**（含重写后的 golden-path 多题闭环与 teacher-role 真实风格名）

## 内容初始化
- validate_library --all：PASS（books=25, violations=0）
- import_library --all：books=25 knowledge=56 幂等导入

## 本阶段新增能力
- 账号状态安全（DISABLED 登录/依赖/WS 全链路失效）与严格后台鉴权（ADMIN_PROFILE_REQUIRED，移除 legacy 放行）
- GET /me/admin + 前端 ADMIN 登录/刷新真实验证；全局 401 事件统一清登录态
- 限流（登录 ip+username / 全局 IP；Redis 优先、进程内降级均强制）429 RATE_LIMITED
- X-Request-ID 贯穿（含错误响应）、JSON 访问日志（不含敏感字段）、/metrics Prometheus 文本
- Idempotency 过期不复用；SSE 消息幂等键 + replay SSE；消息/测验序号 FOR UPDATE 串行化
- 存储抽象（local/S3 SigV4）；TTS Provider 化（none 默认明确不可用）；知识库 PDF 与失败/重处理可见
- 对话历史 UI（切换/新建/归档/删除/清空）；Profile 编辑导出真实持久化；Admin 风格/章节/内容块/知识点管理页

## 尚未确认项（不写“无 blocker”）
- GitHub Actions 远端流水线（redis service）未在远端实测
- S3 兼容对象存储仅 SigV4 单测 + 本地联调，未接真实对象存储服务
- 真实 LLM/ASR/TTS 外部端点质量未验证（CI/E2E 均用 mock provider）
- 多副本部署下 /metrics 进程内口径聚合方案待定
- Worker 消费已在冒烟中确认存活与轮询，长时稳定性未压测
