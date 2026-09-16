"""CodeLab pytest 结果插件 —— 从 pytest 输出中提取每组的通过/失败/错误计数。

逐字移植自 dai-experiment-platform `app/worker/judge_worker.py:145-157` 的
`PLUGIN_CODE`（只把标记名从 `DAI_RESULT_JSON` 改为 `K12_CODELAB_RESULT_JSON`）。

为什么需要它：pytest 的退出码只能表达「全过/有失败」，无法区分
「1 个失败」与「10 个失败」。确定性评分按通过比例给分，因此必须拿到分组计数。
插件在 sessionfinish 时把计数打成一行带标记的 JSON，宿主机侧再解析出来。
"""

import json

COUNTS = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}


def pytest_runtest_logreport(report):
    if report.when == "call":
        if report.passed:
            COUNTS["passed"] += 1
        elif report.failed:
            COUNTS["failed"] += 1
        elif report.skipped:
            COUNTS["skipped"] += 1
    elif report.when in ("setup", "teardown") and report.failed:
        COUNTS["errors"] += 1


def pytest_sessionfinish(session, exitstatus):
    print("K12_CODELAB_RESULT_JSON=" + json.dumps(COUNTS, separators=(",", ":")))
