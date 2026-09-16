"""CodeLab Docker 沙箱（宿主机侧）。

这是**真正的安全边界**。所有隔离强度都来自 `docker run` 的运行参数，
逐字沿用 dai-experiment-platform 已在生产验证过的那一套
（`app/services/kernel_manager.py:248-272`、`app/worker/judge_worker.py:115-125`）：

    --network none                 无网络（学生代码无法外联/回连）
    --cap-drop ALL                 丢弃全部 Linux capabilities
    --security-opt no-new-privileges   禁止提权
    --read-only                    根文件系统只读
    --tmpfs /tmp:exec,size=64m     仅 /tmp 可写且限 64MB
    --cpus / --memory / --pids-limit   资源配额
    --user 1000:1000               非 root

其余设计要点：
- **一次性容器**（`docker run --rm`），不做常驻 kernel —— CodeLab 的任务形态是
  「实现函数 + 跑测试」，每次运行本就是独立脚本，一次性容器足以覆盖「运行」与
  「判题」两条路径，且没有会话生命周期要管理。
- 学生代码经 **stdin JSON** 传入 runner，不进 argv（避免进程列表泄露）。
- 硬超时后 `docker rm -f`，不留半死容器。
- **Docker 不可用时抛错，绝不回退到宿主机执行**（这是不可协商的约束）。
"""

from __future__ import annotations

import json
import re
import logging
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger("shuangling.codelab.sandbox")

ASSETS_DIR = Path(__file__).parent / "sandbox_assets"
CONTAINER_PREFIX = "k12-codelab-"
RESULT_MARKER = "K12_CODELAB_RESULT_JSON="

# 容器内路径约定
_IN_WORK = "/work"          # 只读：学生代码 / 测试文件 / pytest 插件
_OUT_WORK = "/work_out"     # 可写：cwd、matplotlib 图片、sitecustomize
_RUNNER = "/opt/codelab/runner.py"
_ASSETS = "/opt/codelab"

_swept = False


class CodeLabUnavailableError(RuntimeError):
    """沙箱不可用（Docker 缺失 / 镜像缺失）。调用方应转成 503，不得降级执行。"""


@dataclass
class SandboxResult:
    status: str
    outputs: list[dict] = field(default_factory=list)
    exit_code: int | None = None
    execution_time_ms: int = 0
    error: str | None = None


# ═══════════════════════════════════════════════════════════════
# 可用性探测
# ═══════════════════════════════════════════════════════════════


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def image_available(image: str) -> bool:
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", image, "--format", "{{.Id}}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def ensure_available(image: str) -> None:
    """在真正执行前做一次显式探测，把「不可用」翻译成明确的错误。"""
    if not docker_available():
        raise CodeLabUnavailableError(
            "Docker 不可用，CodeLab 无法运行代码。请确认 Docker 守护进程正在运行，"
            "且当前用户可访问 Docker。"
        )
    if not image_available(image):
        raise CodeLabUnavailableError(
            f"CodeLab 沙箱镜像不存在: {image}。请先构建或拉取该镜像。"
        )


def sweep_orphan_containers() -> int:
    """清理本进程之外遗留的沙箱容器（例如 API 被强杀时留下的）。

    每个进程只执行一次，且只匹配 ``k12-codelab-`` 前缀，不会误伤其它容器。
    """
    global _swept
    if _swept:
        return 0
    _swept = True
    try:
        listed = subprocess.run(
            ["docker", "ps", "-aq", "--filter", f"name={CONTAINER_PREFIX}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return 0
    names = [n for n in listed.stdout.split() if n]
    if not names:
        return 0
    logger.warning("清理遗留 CodeLab 沙箱容器 %d 个", len(names))
    subprocess.run(["docker", "rm", "-f", *names], capture_output=True, timeout=60)
    return len(names)


# ═══════════════════════════════════════════════════════════════
# 容器启动参数（安全参数集中在此，便于审计）
# ═══════════════════════════════════════════════════════════════


def _base_docker_args(
    *,
    container_name: str,
    in_dir: Path,
    out_dir: Path,
    host_in_dir: Path,
    host_out_dir: Path,
    image: str,
    memory_limit_mb: int,
    cpu_limit: float,
    extra_env: dict[str, str] | None = None,
    container_workdir: str = _OUT_WORK,
) -> list[str]:
    """组装 docker run 参数。

    host_in_dir / host_out_dir 是**宿主机**路径；in_dir / out_dir 是容器内挂载点。
    二者在 API 以宿主机进程运行时相同；若将来 API 被容器化，由
    codelab_host_work_dir 提供映射，无需改动这里。
    """
    env_args: list[str] = []
    for key, value in (extra_env or {}).items():
        env_args += ["-e", f"{key}={value}"]
    return [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
        "--network",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--read-only",
        "--tmpfs",
        "/tmp:exec,size=64m",
        "--cpus",
        str(cpu_limit),
        "--memory",
        f"{memory_limit_mb}m",
        "--pids-limit",
        "50",
        "--user",
        "1000:1000",
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
        "-e",
        "PYTHONUNBUFFERED=1",
        "-e",
        "MPLBACKEND=Agg",
        *env_args,
        "-v",
        f"{host_in_dir}:{_IN_WORK}:ro",
        "-v",
        f"{host_out_dir}:{_OUT_WORK}:rw",
        "-v",
        f"{ASSETS_DIR}:{_ASSETS}:ro",
        "-w",
        container_workdir,
        image,
    ]


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…（输出过长，已截断至 {limit} 字节）"


def _truncate_outputs(outputs: list[dict], limit: int) -> list[dict]:
    trimmed: list[dict] = []
    for item in outputs:
        content = dict(item.get("content") or {})
        if "text" in content and isinstance(content["text"], str):
            content["text"] = _truncate(content["text"], limit)
        trimmed.append({**item, "content": content})
    return trimmed


def _prepare_dirs(
    work_root: Path, host_work_root: Path, label: str
) -> tuple[Path, Path, Path, Path]:
    token = uuid4().hex[:12]
    in_dir = work_root / f"{label}-{token}" / "in"
    out_dir = work_root / f"{label}-{token}" / "out"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    if host_work_root == work_root:
        return in_dir, out_dir, in_dir, out_dir
    relative = (work_root / f"{label}-{token}").relative_to(work_root)
    host_base = host_work_root / relative
    return in_dir, out_dir, host_base / "in", host_base / "out"


def _cleanup(*paths: Path) -> None:
    for path in paths:
        shutil.rmtree(path, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════
# 运行学生代码
# ═══════════════════════════════════════════════════════════════


def run_python(
    code: str,
    *,
    work_root: Path,
    host_work_root: Path,
    image: str,
    timeout_seconds: int,
    memory_limit_mb: int,
    cpu_limit: float,
    max_output_bytes: int,
) -> SandboxResult:
    """在一次性沙箱中执行一段 Python，返回输出信封。"""
    ensure_available(image)
    in_dir, out_dir, host_in, host_out = _prepare_dirs(work_root, host_work_root, "run")
    container_name = f"{CONTAINER_PREFIX}{uuid4().hex[:12]}"
    try:
        (in_dir / "user_code.py").write_text(code, encoding="utf-8")
        # sitecustomize 放在可写目录，由 runner 通过 PYTHONPATH 注入：
        # 它让 plt.show() 落盘成 PNG（见 sandbox_assets/sitecustomize.py）
        shutil.copy2(ASSETS_DIR / "sitecustomize.py", out_dir / "sitecustomize.py")

        cmd = _base_docker_args(
            container_name=container_name,
            in_dir=in_dir,
            out_dir=out_dir,
            host_in_dir=host_in,
            host_out_dir=host_out,
            image=image,
            memory_limit_mb=memory_limit_mb,
            cpu_limit=cpu_limit,
            extra_env={"CODELAB_INNER_TIMEOUT": str(max(1, timeout_seconds - 1))},
        )
        cmd += ["python", _RUNNER]

        started = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                input=json.dumps({"code": code}),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
            return SandboxResult(
                status="TIMEOUT",
                execution_time_ms=elapsed_ms,
                error=f"运行超时：超过 {timeout_seconds} 秒，容器已销毁",
            )
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        return _parse_runner_output(proc.stdout, proc.stderr, proc.returncode, elapsed_ms, max_output_bytes)
    finally:
        _cleanup(in_dir.parent)


def _parse_runner_output(
    stdout: str, stderr: str, returncode: int, elapsed_ms: int, max_output_bytes: int
) -> SandboxResult:
    payload: dict | None = None
    for line in reversed((stdout or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                payload = json.loads(line)
                break
            except ValueError:
                continue
    if payload is None:
        detail = (stderr or stdout or "").strip()[:2000]
        return SandboxResult(
            status="ERROR",
            execution_time_ms=elapsed_ms,
            error=f"沙箱未能返回结果（退出码 {returncode}）：{detail or '无输出'}",
        )
    outputs = _truncate_outputs(list(payload.get("outputs") or []), max_output_bytes)
    return SandboxResult(
        status=str(payload.get("status") or ("SUCCESS" if returncode == 0 else "FAILED")),
        outputs=outputs,
        exit_code=payload.get("exit_code"),
        execution_time_ms=elapsed_ms,
        error=payload.get("error"),
    )


# ═══════════════════════════════════════════════════════════════
# 判题：跑一个测试组
# ═══════════════════════════════════════════════════════════════


def run_pytest_group(
    code: str,
    tests: str,
    *,
    work_root: Path,
    host_work_root: Path,
    image: str,
    timeout_seconds: int,
    memory_limit_mb: int,
    cpu_limit: float,
) -> tuple[dict | None, str, str]:
    """在沙箱里用 pytest 跑一个测试组。

    返回 ``(counts, stdout, stderr)``；``counts`` 为 None 表示无法解析结果
    （调用方应记为该组系统错误，而不是学生做错）。

    与 dai 的 `run_test_groups`（judge_worker.py:259-299）行为一致：
    测试代码前自动补 `from user_code import *`，并以 `-p result_plugin` 挂载计数插件。
    """
    ensure_available(image)
    in_dir, out_dir, host_in, host_out = _prepare_dirs(work_root, host_work_root, "judge")
    container_name = f"{CONTAINER_PREFIX}{uuid4().hex[:12]}"
    try:
        # dai 的做法：测试代码没有显式导入被测模块时自动补上，方便教师只写断言
        content = tests
        if "import user_code" not in content and "from user_code" not in content:
            content = f"from user_code import *\n\n{content}"
        (in_dir / "user_code.py").write_text(code, encoding="utf-8")
        (in_dir / "test_group.py").write_text(content, encoding="utf-8")
        shutil.copy2(ASSETS_DIR / "result_plugin.py", in_dir / "result_plugin.py")

        cmd = _base_docker_args(
            container_name=container_name,
            in_dir=in_dir,
            out_dir=out_dir,
            host_in_dir=host_in,
            host_out_dir=host_out,
            image=image,
            memory_limit_mb=memory_limit_mb,
            cpu_limit=cpu_limit,
            # 让 `-p result_plugin` 能从只读的 /work 里导入计数插件
            extra_env={"PYTHONPATH": _IN_WORK},
            # pytest 必须从 /work 运行：测试文件与 user_code.py 都在那里。
            # 运行路径的 cwd 是 /work_out（学生程序把图片写进 cwd），判题路径不同。
            container_workdir=_IN_WORK,
        )
        cmd += [
            "python",
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "result_plugin",
            f"{_IN_WORK}/test_group.py",
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
            return None, "", "EXECUTION_TIMEOUT"
        return parse_result_counts(proc.stdout), proc.stdout, proc.stderr
    finally:
        _cleanup(in_dir.parent)


def parse_result_counts(output: str) -> dict | None:
    """从 pytest 输出中解析 ``K12_CODELAB_RESULT_JSON={...}``。

    移植 dai `judge_worker.py:159-178` 的 `_parse_result_json`。注意必须用
    **搜索**而不是「行首匹配」：pytest 的进度行与插件输出会落在同一行
    （实测得到 ``'.    [100%]K12_CODELAB_RESULT_JSON={...}'``），
    行首匹配永远解析不到。
    """
    if not output:
        return None
    match = re.search(rf"{RESULT_MARKER}(\{{.*?\}})", output)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except ValueError:
        return None
    for key in ("passed", "failed", "errors", "skipped"):
        value = data.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return None
    return data
