# 霜铃后端镜像：API 与 Worker 共用同一代码/依赖（compose 中以不同 command 启动）。
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# 先只拷贝锁文件以最大化缓存层；package=false，无需安装项目本身。
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY data ./data

ENV PATH="/app/.venv/bin:$PATH"

# 默认入口为后台 Worker；API 容器可在 compose 中覆盖 command 为 uvicorn。
CMD ["python", "-m", "app.jobs.worker"]
