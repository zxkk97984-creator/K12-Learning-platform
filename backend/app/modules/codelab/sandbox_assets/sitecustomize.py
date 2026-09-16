"""CodeLab 容器内 sitecustomize —— 自动被 Python 启动时导入（PYTHONPATH 命中即生效）。

只做一件事：让学生的 `plt.show()` 真的产出图片。

沙箱里 matplotlib 用 Agg 后端（无 GUI），`plt.show()` 默认什么都不做，
学生会以为画图失败了。这里把 show() 改成「把所有打开的图保存成 PNG」，
保存目录由 CODELAB_OUT_DIR 指定，runner 随后会把它们收集成 display_data 输出。

任何异常都必须被吞掉：这个文件在**每个** python 子进程启动时都会执行，
它一旦抛错会污染学生代码的运行结果。
"""

try:
    import os

    import matplotlib

    matplotlib.use("Agg", force=True)

    import matplotlib.pyplot as plt

    _out_dir = os.environ.get("CODELAB_OUT_DIR") or "."
    _original_show = plt.show

    def _show(*args, **kwargs):  # noqa: ANN002, ANN003
        try:
            for number in plt.get_fignums():
                figure = plt.figure(number)
                figure.savefig(
                    os.path.join(_out_dir, f"figure_{number}.png"),
                    bbox_inches="tight",
                )
        except Exception:  # pragma: no cover - 保底：画图失败不能影响学生代码
            pass
        finally:
            try:
                plt.close("all")
            except Exception:  # pragma: no cover
                pass

    plt.show = _show
except Exception:  # pragma: no cover - matplotlib 不存在时静默跳过
    pass
