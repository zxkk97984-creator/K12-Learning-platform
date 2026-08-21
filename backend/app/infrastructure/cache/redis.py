"""Small Redis infrastructure layer for locks and best-effort caching.

Redis is deliberately not a source of truth here.  Every operation is
best-effort and returns a safe fallback when Redis is disabled or unavailable.
"""

import json
import logging
from typing import Any
from uuid import uuid4

from redis.asyncio import Redis, from_url

from app.config import settings

logger = logging.getLogger(__name__)

_client: Redis | None = None

_RELEASE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""


def _get_client() -> Redis | None:
    """Create the client lazily; no connection is made until an operation runs."""
    global _client
    if not settings.redis_enabled:
        return None
    if _client is None:
        try:
            _client = from_url(settings.redis_url, decode_responses=True)
        except Exception:
            logger.debug("Redis client initialization failed; using fallbacks", exc_info=True)
            return None
    return _client


def _ttl_milliseconds(ttl: float) -> int:
    if ttl <= 0:
        raise ValueError("Redis TTL must be positive")
    return max(1, int(ttl * 1000))


async def ping() -> bool:
    """Return whether Redis is reachable without making it a startup dependency."""
    client = _get_client()
    if client is None:
        return False
    try:
        return bool(await client.ping())
    except Exception:
        logger.debug("Redis ping failed; continuing with local fallbacks", exc_info=True)
        return False


async def acquire_lock(key: str, ttl: float) -> str | None:
    """Acquire ``key`` for ``ttl`` seconds and return an ownership token.

    ``None`` means either that another owner currently holds the lock or that
    Redis is unavailable.  Callers must use their documented fallback path.
    """
    try:
        ttl_ms = _ttl_milliseconds(ttl)
    except ValueError:
        return None
    client = _get_client()
    if client is None:
        return None
    token = str(uuid4())
    try:
        acquired = await client.set(key, token, nx=True, px=ttl_ms)
    except Exception:
        logger.debug("Redis lock acquisition failed; using local fallback", exc_info=True)
        return None
    return token if bool(acquired) else None


async def release_lock(key: str, token: str) -> bool:
    """Release ``key`` only when it still belongs to ``token``."""
    if not token:
        return False
    client = _get_client()
    if client is None:
        return False
    try:
        released = await client.eval(_RELEASE_LOCK_SCRIPT, 1, key, token)
    except Exception:
        logger.debug("Redis lock release failed", exc_info=True)
        return False
    return bool(released)


async def cache_get(key: str) -> Any | None:
    """Read and JSON-decode a cached value, returning ``None`` on any miss/error."""
    client = _get_client()
    if client is None:
        return None
    try:
        value = await client.get(key)
        return None if value is None else json.loads(value)
    except Exception:
        logger.debug("Redis cache read failed", exc_info=True)
        return None


async def cache_set(key: str, value: Any, ttl: float) -> bool:
    """JSON-encode and write a cache value; failures never affect the request."""
    try:
        ttl_seconds = max(1, int(ttl))
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return False
    client = _get_client()
    if client is None:
        return False
    try:
        return bool(await client.set(key, encoded, ex=ttl_seconds))
    except Exception:
        logger.debug("Redis cache write failed", exc_info=True)
        return False


async def cache_delete(key: str) -> bool:
    """Delete one cache key; return whether Redis reported a deletion."""
    client = _get_client()
    if client is None:
        return False
    try:
        return bool(await client.delete(key))
    except Exception:
        logger.debug("Redis cache delete failed", exc_info=True)
        return False


async def cache_delete_prefix(prefix: str) -> int:
    """Delete keys under a namespace using Redis SCAN, never blocking on KEYS."""
    if not prefix:
        return 0
    client = _get_client()
    if client is None:
        return 0
    try:
        keys = [key async for key in client.scan_iter(match=f"{prefix}*")]
        if not keys:
            return 0
        return int(await client.delete(*keys))
    except Exception:
        logger.debug("Redis cache namespace invalidation failed", exc_info=True)
        return 0


__all__ = [
    "acquire_lock",
    "cache_delete",
    "cache_delete_prefix",
    "cache_get",
    "cache_set",
    "ping",
    "release_lock",
]
