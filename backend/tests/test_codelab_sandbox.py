"""CodeLab 沙箱隔离测试（真实 Docker）。

这些用例把**安全边界**变成可自动执行的断言，而不是只写在文档里的声明。
之前隔离属性只在审计时手工验证过一次；一旦有人误删 `sandbox.py:_base_docker_args`
里的某个参数，手工验证不会重跑，但这里会直接失败。

Docker 或镜像不可用时整类跳过（用 `-rs` 可以看到跳过原因）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import settings
from app.modules.codelab import sandbox

pytestmark = pytest.mark.skipif(
    not sandbox.docker_available() or not sandbox.image_available(settings.codelab_run_image),
    reason="需要 Docker 与 CodeLab 运行镜像",
)


@pytest.fixture(scope="module")
def work_root() -> Path:
    root = Path("/tmp/k12-codelab-sandbox-tests")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _run(code: str, work_root: Path, *, timeout: int = 15):
    return sandbox.run_python(
        code,
        work_root=work_root,
        host_work_root=work_root,
        image=settings.codelab_run_image,
        timeout_seconds=timeout,
        memory_limit_mb=settings.codelab_memory_limit_mb,
        cpu_limit=settings.codelab_cpu_limit,
        max_output_bytes=settings.codelab_max_output_bytes,
    )


def _stdout(result) -> str:
    return "".join(
        (item["content"].get("text") or "")
        for item in result.outputs
        if item["msg_type"] == "stream" and item["content"].get("name") == "stdout"
    )


class TestIsolation:
    def test_network_is_disabled(self, work_root: Path):
        """`--network none`：学生代码不得有任何外联能力。"""
        result = _run(
            "import socket\n"
            "try:\n"
            "    socket.create_connection(('1.1.1.1', 53), timeout=3)\n"
            "    print('NETWORK_REACHABLE')\n"
            "except Exception as exc:\n"
            "    print('NETWORK_BLOCKED', type(exc).__name__)\n",
            work_root,
        )
        out = _stdout(result)
        assert "NETWORK_BLOCKED" in out
        assert "NETWORK_REACHABLE" not in out

    def test_root_filesystem_is_read_only(self, work_root: Path):
        """`--read-only`：根文件系统不可写。"""
        result = _run(
            "try:\n"
            "    open('/k12_write_probe', 'w').write('x')\n"
            "    print('ROOTFS_WRITABLE')\n"
            "except Exception as exc:\n"
            "    print('ROOTFS_READONLY', type(exc).__name__)\n",
            work_root,
        )
        out = _stdout(result)
        assert "ROOTFS_READONLY" in out
        assert "ROOTFS_WRITABLE" not in out

    def test_runs_as_non_root(self, work_root: Path):
        """`--user 1000:1000`：不得以 root 运行。"""
        result = _run("import os\nprint('UID', os.getuid())\n", work_root)
        assert "UID 1000" in _stdout(result)

    def test_memory_limit_is_enforced(self, work_root: Path):
        """`--memory`：超量分配必须被杀掉，而不是拖垮宿主机。"""
        result = _run("x = bytearray(900 * 1024 * 1024)\nprint('ALLOCATED')\n", work_root)
        assert result.status == "FAILED"
        assert result.exit_code != 0
        assert "ALLOCATED" not in _stdout(result)


class TestLimits:
    def test_hard_timeout_kills_container_and_leaves_no_residue(self, work_root: Path):
        """超时必须被强杀，且不留下孤儿容器（否则会持续占用 CPU）。"""
        result = _run("while True:\n    pass\n", work_root, timeout=8)
        assert result.status == "TIMEOUT"
        assert result.error and "超时" in result.error

        import subprocess

        listed = subprocess.run(
            ["docker", "ps", "-aq", "--filter", f"name={sandbox.CONTAINER_PREFIX}"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert listed.stdout.strip() == "", f"存在残留沙箱容器: {listed.stdout.strip()}"

    def test_output_is_truncated(self, work_root: Path):
        """超长输出必须被截断，避免响应体失控。"""
        result = _run("print('x' * 200000)\n", work_root)
        total = len(_stdout(result))
        assert total < settings.codelab_max_output_bytes + 200
        assert "已截断" in _stdout(result)


class TestRunnerContract:
    def test_stdout_and_stderr_are_separated(self, work_root: Path):
        """stdout 与 stderr 必须分开返回。

        dai 的 sample-run 在服务端把两者拼成一个字符串，前端无从区分；
        CodeLab 的输出契约刻意不沿用那个做法。
        """
        result = _run(
            "import sys\nprint('OUT')\nprint('ERR', file=sys.stderr)\n", work_root
        )
        by_name = {
            item["content"]["name"]: item["content"]["text"]
            for item in result.outputs
            if item["msg_type"] == "stream"
        }
        assert "OUT" in by_name.get("stdout", "")
        assert "ERR" in by_name.get("stderr", "")
        assert "ERR" not in by_name.get("stdout", "")

    def test_traceback_goes_to_stderr_without_matplotlib_noise(self, work_root: Path):
        """语法错误的 traceback 必须可读，且不被 matplotlib 的只读目录警告淹没。

        （沙箱 HOME 只读，若不设置 MPLCONFIGDIR，每次运行都会先打一段
        "Read-only file system" 警告 —— 这是实测踩到并修掉的问题。）
        """
        result = _run("def f(x)\n    return x\n", work_root)
        stderr = "".join(
            (item["content"].get("text") or "")
            for item in result.outputs
            if item["msg_type"] == "stream" and item["content"].get("name") == "stderr"
        )
        assert "SyntaxError" in stderr
        assert "Read-only file system" not in stderr
        assert "MPLCONFIGDIR" not in stderr

    def test_image_output_is_captured(self, work_root: Path):
        """plt.show() 必须产出 PNG（sitecustomize 把 Agg 后端的 show 落盘）。"""
        result = _run(
            "import matplotlib.pyplot as plt\nplt.plot([1, 2, 3])\nplt.show()\nprint('done')\n",
            work_root,
        )
        images = [o for o in result.outputs if o["msg_type"] == "display_data"]
        assert result.status == "SUCCESS"
        assert "done" in _stdout(result)
        assert len(images) == 1
        assert len(images[0]["content"]["data"]["image/png"]) > 1000

    def test_os_exit_does_not_lose_the_result_envelope(self, work_root: Path):
        """学生代码 `os._exit()` 不能带走 runner —— 子进程隔离的意义所在。"""
        result = _run("import os\nprint('before')\nos._exit(3)\n", work_root)
        assert result.status == "FAILED"
        assert result.exit_code == 3
        assert "before" in _stdout(result)
