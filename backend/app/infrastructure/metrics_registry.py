"""进程内 Prometheus 指标注册表（单例，由 main.py 挂到 /metrics）。"""

import time

from app.config import settings

_PROCESS_START = time.time()


class MetricsRegistry:
    def __init__(self) -> None:
        self.environment = settings.environment
        self.request_total: dict[tuple[str, int], int] = {}
        self.duration_seconds_sum = 0.0
        self.request_count = 0

    def observe(self, *, method: str, status: int, duration_ms: float) -> None:
        key = (method, status)
        self.request_total[key] = self.request_total.get(key, 0) + 1
        self.duration_seconds_sum += duration_ms / 1000.0
        self.request_count += 1

    def render(self) -> str:
        lines: list[str] = [
            "# HELP http_requests_total Total HTTP requests.",
            "# TYPE http_requests_total counter",
        ]
        for (method, status), count in sorted(self.request_total.items()):
            lines.append(
                f'http_requests_total{{method="{method}",status="{status}",env="{self.environment}"}} {count}'
            )
        lines += [
            "# HELP http_request_duration_seconds_total Cumulative request duration.",
            "# TYPE http_request_duration_seconds_total counter",
            f'http_request_duration_seconds_total{{env="{self.environment}"}} '
            f"{round(self.duration_seconds_sum, 4)}",
            "# HELP http_requests_completed_total Completed requests.",
            "# TYPE http_requests_completed_total gauge",
            f'http_requests_completed_total{{env="{self.environment}"}} {self.request_count}',
            f'process_uptime_seconds{{env="{self.environment}"}} '
            f"{round(time.time() - _PROCESS_START, 2)}",
        ]
        return "\n".join(lines) + "\n"


metrics_registry = MetricsRegistry()
