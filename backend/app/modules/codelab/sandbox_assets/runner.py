"""CodeLab 容器内 runner —— 在一次性 Docker 沙箱中执行学生代码。

职责边界（重要）：
- 本文件运行在**容器内**，它本身是可信代码；学生代码由它作为**子进程**启动。
- 之所以要多一层子进程：学生代码可能 `sys.exit()`、`os._exit()`、段错误或死循环，
  放在同进程会把 runner 一起带走，导致连输出信封都拿不到。子进程隔离让这些
  情况都能被翻译成一条可读的错误输出。
- 真正的安全边界**不是**本文件，而是宿主机侧 `docker run` 的
  `--network none --cap-drop ALL --read-only --pids-limit ...` 等参数
  （见 sandbox.py）。本文件不做也不应做安全判断。

输出契约（沿用 dai / Jupyter IOPub 的形状）：
    {"msg_type": "stream",        "content": {"name": "stdout"|"stderr", "text": str}}
    {"msg_type": "error",         "content": {"text": "<traceback 文本>"}}
    {"msg_type": "display_data",  "content": {"data": {"image/png": "<base64>"}}}

stdout 与 stderr **分开**保留。dai 的 `sample-run` 把两者拼成一个字符串
（`f"{stdout}\n{stderr}"`），前端无法区分正常输出与错误输出 —— 这里不沿用那个缺陷。
"""

import base64
import json
import os
import subprocess
import sys

WORK_DIR = "/work"
OUT_DIR = "/work_out"
USER_CODE_PATH = os.path.join(WORK_DIR, "user_code.py")
IMAGE_SUFFIX = ".png"


def _emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    sys.stdout.flush()


def _collect_images(outputs: list[dict]) -> None:
    """把写进输出目录的 PNG 作为 display_data 输出（matplotlib 图表）。"""
    try:
        names = sorted(os.listdir(OUT_DIR))
    except OSError:
        return
    for name in names:
        if not name.endswith(IMAGE_SUFFIX):
            continue
        path = os.path.join(OUT_DIR, name)
        try:
            with open(path, "rb") as handle:
                encoded = base64.b64encode(handle.read()).decode("ascii")
        except OSError:
            continue
        outputs.append(
            {"msg_type": "display_data", "content": {"data": {"image/png": encoded}}}
        )


def main() -> int:
    if not os.path.exists(USER_CODE_PATH):
        _emit({"outputs": [], "error": "学生代码文件缺失"})
        return 1

    # 内层超时比宿主机外层超时少 1 秒：正常情况下由内层先触发，能给出
    # 一条干净的「运行超时」输出；外层超时只是兜底（容器无响应时强杀）。
    try:
        inner_timeout = max(1, int(os.environ.get("CODELAB_INNER_TIMEOUT", "9")))
    except ValueError:
        inner_timeout = 9

    env = dict(os.environ)
    # sitecustomize.py 放在可写的 OUT_DIR 里，通过 PYTHONPATH 自动生效：
    # 它把 matplotlib 切到 Agg 并让 plt.show() 落盘成 PNG。
    env["PYTHONPATH"] = os.pathsep.join(
        [OUT_DIR] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    env["CODELAB_OUT_DIR"] = OUT_DIR
    env["MPLBACKEND"] = "Agg"
    # matplotlib 默认把缓存写到 $HOME/.config/matplotlib，而沙箱根文件系统是只读的。
    # 不指定 MPLCONFIGDIR 时每次运行都会往学生看到的 stderr 里打一段
    # "Read-only file system" 警告，把真正的报错淹没（实测过这个问题）。
    mpl_config_dir = os.path.join(OUT_DIR, ".mplconfig")
    try:
        os.makedirs(mpl_config_dir, exist_ok=True)
    except OSError:
        pass
    env["MPLCONFIGDIR"] = mpl_config_dir
    # 不把宿主机代理变量带进沙箱：容器本来就没有网络。
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env.pop(key, None)

    outputs: list[dict] = []
    try:
        proc = subprocess.run(
            [sys.executable, USER_CODE_PATH],
            cwd=OUT_DIR,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=inner_timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        _append_stream(outputs, "stdout", _decode(exc.stdout))
        _append_stream(outputs, "stderr", _decode(exc.stderr))
        _collect_images(outputs)
        _emit(
            {
                "outputs": outputs,
                "status": "TIMEOUT",
                "exit_code": None,
                "error": f"运行超时：超过 {inner_timeout} 秒仍未结束",
            }
        )
        return 0

    _append_stream(outputs, "stdout", proc.stdout or "")
    _append_stream(outputs, "stderr", proc.stderr or "")
    _collect_images(outputs)
    _emit(
        {
            "outputs": outputs,
            "status": "SUCCESS" if proc.returncode == 0 else "FAILED",
            "exit_code": proc.returncode,
            "error": None if proc.returncode == 0 else proc.stderr.strip()[-2000:] or None,
        }
    )
    return 0


def _decode(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _append_stream(outputs: list[dict], name: str, text: str) -> None:
    if text:
        outputs.append({"msg_type": "stream", "content": {"name": name, "text": text}})


if __name__ == "__main__":
    sys.exit(main())
