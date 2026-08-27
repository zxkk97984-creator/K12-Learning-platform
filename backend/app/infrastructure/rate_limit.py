"""轻量限流（Phase 5-A）。

策略：Redis 可用（settings.redis_enabled 且连接成功）时用 INCR+EXPIRE
实现分布式固定窗口；否则降级为**进程内**滑动窗口计数。两种模式都会
真实拒绝超限请求——绝不静默放行。

键维度：
- 登录接口：ip + username（防撞库）
- 普通 API：client ip（全局兜底）
"""

import time
from collections import defaultdict, deque
from dataclasses import dataclass

from app.config import settings


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after: int


class _MemoryWindow:
    """进程内滑动窗口（单实例部署 / Redis 不可用时的降级）。

    整改 1：防止长期堆积——每次 check 做该键的过期出队；
    每 `_SWEEP_EVERY` 次调用触发一次全表清扫，移除所有已滑出窗口的键，
    并对总量做硬上限（超出时优先丢弃最久未活跃的键）。
    """

    MAX_TRACKED_KEYS = 10_000
    _SWEEP_EVERY = 512

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._checks_since_sweep = 0

    def _sweep(self, window_seconds: int) -> None:
        cutoff = time.monotonic() - window_seconds
        stale = [k for k, dq in self._hits.items() if not dq or dq[-1] <= cutoff]
        for k in stale:
            self._hits.pop(k, None)
        # 容量上限：仍超限时按「最新命中时间」从旧到新淘汰
        if len(self._hits) > self.MAX_TRACKED_KEYS:
            ordered = sorted(
                self._hits.items(), key=lambda item: item[1][-1] if item[1] else 0.0
            )
            excess = len(self._hits) - self.MAX_TRACKED_KEYS
            for k, _ in ordered[:excess]:
                self._hits.pop(k, None)

    def check(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        self._checks_since_sweep += 1
        if self._checks_since_sweep >= self._SWEEP_EVERY:
            self._checks_since_sweep = 0
            self._sweep(window_seconds)

        now = time.monotonic()
        window_start = now - window_seconds
        hits = self._hits[key]
        while hits and hits[0] <= window_start:
            hits.popleft()
        if len(hits) >= limit:
            retry_after = max(1, int(window_seconds - (now - hits[0]) + 1))
            return RateLimitResult(False, 0, retry_after)
        hits.append(now)
        return RateLimitResult(True, limit - len(hits), 0)


class RateLimiter:
    def __init__(self) -> None:
        self._memory = _MemoryWindow()
        self._redis = None
        self._redis_checked = False

    def _get_redis(self):
        if not settings.redis_enabled:
            return None
        if not self._redis_checked:
            self._redis_checked = True
            try:
                import redis  # redis-py 已是项目依赖

                client = redis.Redis.from_url(
                    settings.redis_url,
                    socket_connect_timeout=0.3,
                    socket_timeout=0.5,
                    decode_responses=True,
                )
                client.ping()
                self._redis = client
            except Exception:
                # 连接失败 → 明确降级为进程内限流（仍强制），不静默放行
                self._redis = None
        return self._redis

    def check(self, key: str, *, limit: int, window_seconds: int = 60) -> RateLimitResult:
        if limit <= 0:
            return RateLimitResult(True, 0, 0)
        redis_client = self._get_redis()
        if redis_client is not None:
            try:
                bucket = f"rl:{key}:{int(time.time()) // window_seconds}"
                pipe = redis_client.pipeline()
                pipe.incr(bucket)
                pipe.expire(bucket, window_seconds)
                count = int(pipe.execute()[0])
                if count > limit:
                    retry_after = window_seconds - int(time.time()) % window_seconds
                    return RateLimitResult(False, 0, max(1, retry_after))
                return RateLimitResult(True, max(0, limit - count), 0)
            except Exception:
                # Redis 中途故障 → 降级进程内，仍强制
                pass
        return self._memory.check(key, limit, window_seconds)


rate_limiter = RateLimiter()
