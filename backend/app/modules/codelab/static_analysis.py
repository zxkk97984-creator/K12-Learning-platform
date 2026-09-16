"""只读静态分析 —— 纯 AST，不执行学生代码。

源自 dai-experiment-platform `app/services/static_analysis.py` 的 `analyze_python`，
**裁剪掉了 ruff / radon 两个子进程**：霜铃没有这两个依赖，而它们的产出只是给
LLM 的参考信号（不参与任何计分）。后续若需要，可以在此文件内加回，接口不变。

这个模块产出两条对 CodeLab 有价值的信息：
1. `parseable` —— 学生代码能否被解析。这是**确定性判题的前置检查**：
   语法错误时 pytest 会以「收集错误」结束而给出 0/0/0/0 计数，若不做这个检查，
   学生会被误报为「系统错误」而不是「你的代码有语法错误」。见 execution.py。
2. 结构统计（函数数、最大嵌套深度、行数）—— 作为 LLM 评分的参考上下文。
"""

from __future__ import annotations

import ast


def _max_nesting(tree: ast.AST) -> int:
    """AST 最大嵌套深度（移植 dai static_analysis.py:80+）。"""
    max_depth = 0

    def walk(node: ast.AST, depth: int = 0) -> None:
        nonlocal max_depth
        max_depth = max(max_depth, depth)
        for child in ast.iter_child_nodes(node):
            # 只把真正构成控制流的节点算作一层嵌套，避免把表达式树算进去
            if isinstance(
                child,
                (
                    ast.If,
                    ast.For,
                    ast.AsyncFor,
                    ast.While,
                    ast.With,
                    ast.AsyncWith,
                    ast.Try,
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                    ast.ClassDef,
                ),
            ):
                walk(child, depth + 1)
            else:
                walk(child, depth)

    walk(tree)
    return max_depth


def analyze_python(code: str) -> dict:
    """对学生代码做只读静态分析，绝不执行它。"""
    lines = code.splitlines()
    result: dict = {
        "parseable": True,
        "syntax_error": None,
        "line_count": len(lines),
        "function_count": 0,
        "max_nesting": 0,
        "diagnostics": [],  # 保留字段：将来接 ruff 时在此填充
    }
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        result["parseable"] = False
        result["syntax_error"] = f"{exc.msg} (line {exc.lineno})"
        return result

    result["function_count"] = sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    result["max_nesting"] = _max_nesting(tree)
    return result
