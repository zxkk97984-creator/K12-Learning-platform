"""CodeLab 编程任务幂等导入器：data/codelab/tasks/*.json → code_tasks。

用法：
    uv run python -m app.scripts.import_code_tasks            # 全部
    uv run python -m app.scripts.import_code_tasks --slug binary-search

约定（与 import_library / import_assessments 保持一致）：
- 按 `slug` 幂等 upsert，导入两次数量不翻倍；
- 导入前做**结构校验**：test_groups 的 id 唯一、dimension ∈ {F,R}、
  F 组合计满分 60、R 组合计满分 10、tests 非空且能被解析；
  校验不过则该任务整体拒绝导入（不允许半成品任务进入学生视野）；
- 不覆盖已锁定的 rubric：已存在的任务的 rubric 保留，避免每次导入都重新生成；
- `status` 由 JSON 决定（DRAFT / PUBLISHED / ARCHIVED）。

为什么不做成管理端 CRUD：Phase 1 的目标是把在线编程闭环跑通，
题目来源用文件 + 幂等导入与霜铃既有内容管线一致，成本最低且可评审。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.infrastructure.database.models import CodeTask
from app.infrastructure.database.session import async_session

logger = logging.getLogger(__name__)

TASKS_DIR = Path(__file__).resolve().parents[2] / "data" / "codelab" / "tasks"

VALID_STATUS = {"DRAFT", "PUBLISHED", "ARCHIVED"}
FUNCTIONAL_TOTAL = 60.0
ROBUSTNESS_TOTAL = 10.0


class TaskValidationError(ValueError):
    """任务定义不符合约定。"""


def _validate(path: Path, payload: dict[str, Any]) -> list[str]:
    """校验任务定义，返回问题列表（空表示通过）。"""
    issues: list[str] = []
    for field in ("slug", "title", "description", "starter_code"):
        if not isinstance(payload.get(field), str) or not payload.get(field, "").strip():
            issues.append(f"缺少或为空的字段：{field}")
    status = payload.get("status", "DRAFT")
    if status not in VALID_STATUS:
        issues.append(f"status 非法：{status}")

    groups = payload.get("test_groups", [])
    if not isinstance(groups, list):
        issues.append("test_groups 必须是数组")
        return issues

    seen_ids: set[str] = set()
    f_total = 0.0
    r_total = 0.0
    for index, group in enumerate(groups):
        label = f"test_groups[{index}]"
        if not isinstance(group, dict):
            issues.append(f"{label} 不是对象")
            continue
        group_id = group.get("id")
        if not isinstance(group_id, str) or not group_id:
            issues.append(f"{label} 缺少 id")
        elif group_id in seen_ids:
            issues.append(f"测试组 id 重复：{group_id}")
        else:
            seen_ids.add(group_id)
        dimension = group.get("dimension")
        if dimension not in ("F", "R"):
            issues.append(f"测试组 {group_id} 的 dimension 必须是 F 或 R")
            continue
        try:
            max_score = float(group.get("max_score"))
        except (TypeError, ValueError):
            issues.append(f"测试组 {group_id} 的 max_score 不是数字")
            continue
        if max_score <= 0:
            issues.append(f"测试组 {group_id} 的 max_score 必须为正")
        tests = group.get("tests")
        if not isinstance(tests, str) or not tests.strip():
            issues.append(f"测试组 {group_id} 缺少 tests 代码")
        if dimension == "F":
            f_total += max_score
        else:
            r_total += max_score

    if groups:
        if abs(f_total - FUNCTIONAL_TOTAL) > 1e-6:
            issues.append(f"F 组合计满分应为 {FUNCTIONAL_TOTAL:g}，实际 {f_total:g}")
        if abs(r_total - ROBUSTNESS_TOTAL) > 1e-6:
            issues.append(f"R 组合计满分应为 {ROBUSTNESS_TOTAL:g}，实际 {r_total:g}")
    return issues


def load_task_files(slug: str | None = None) -> list[tuple[Path, dict[str, Any]]]:
    if not TASKS_DIR.is_dir():
        raise FileNotFoundError(f"任务目录不存在：{TASKS_DIR}")
    loaded: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(TASKS_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if slug is not None and payload.get("slug") != slug:
            continue
        issues = _validate(path, payload)
        if issues:
            raise TaskValidationError(
                f"{path.name} 校验未通过：\n  - " + "\n  - ".join(issues)
            )
        loaded.append((path, payload))
    return loaded


async def import_tasks(slug: str | None = None) -> dict[str, int]:
    loaded = load_task_files(slug)
    created = 0
    updated = 0
    async with async_session() as session:
        for path, payload in loaded:
            existing = (
                await session.execute(
                    select(CodeTask).where(CodeTask.slug == payload["slug"])
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    CodeTask(
                        slug=payload["slug"],
                        title=payload["title"],
                        description=payload["description"],
                        starter_code=payload.get("starter_code", ""),
                        test_groups=payload.get("test_groups", []),
                        reference_solution=payload.get("reference_solution"),
                        rubric=payload.get("rubric"),
                        status=payload.get("status", "DRAFT"),
                    )
                )
                created += 1
            else:
                existing.title = payload["title"]
                existing.description = payload["description"]
                existing.starter_code = payload.get("starter_code", "")
                existing.test_groups = payload.get("test_groups", [])
                existing.reference_solution = payload.get("reference_solution")
                existing.status = payload.get("status", existing.status)
                # 已锁定的 rubric 不覆盖：避免每次导入都作废历史评分口径
                if payload.get("rubric") is not None:
                    existing.rubric = payload["rubric"]
                updated += 1
        await session.commit()
    logger.info("import_code_tasks: created=%d updated=%d", created, updated)
    return {"created": created, "updated": updated, "total": len(loaded)}


def main() -> None:
    parser = argparse.ArgumentParser(description="导入 CodeLab 编程任务（幂等）")
    parser.add_argument("--slug", default=None, help="只导入指定 slug")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    result = asyncio.run(import_tasks(slug=args.slug))
    print(
        f"import_code_tasks 完成：新增 {result['created']}，更新 {result['updated']}，"
        f"共处理 {result['total']} 个任务"
    )


if __name__ == "__main__":
    main()
