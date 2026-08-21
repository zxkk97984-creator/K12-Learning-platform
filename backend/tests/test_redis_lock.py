"""Redis infrastructure tests use an in-memory fake; no Redis server required."""

import asyncio
import json

from app.config import settings
from app.infrastructure.cache import redis as redis_layer


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, dict]] = []

    async def set(self, key: str, value: str, **options):
        self.set_calls.append((key, value, options))
        if options.get("nx") and key in self.values:
            return False
        self.values[key] = value
        return True

    async def eval(self, _script: str, _numkeys: int, key: str, token: str):
        if self.values.get(key) != token:
            return 0
        del self.values[key]
        return 1

    async def get(self, key: str):
        return self.values.get(key)

    async def delete(self, *keys: str):
        deleted = 0
        for key in keys:
            if key in self.values:
                del self.values[key]
                deleted += 1
        return deleted

    async def scan_iter(self, *, match: str):
        prefix = match.removesuffix("*")
        for key in list(self.values):
            if key.startswith(prefix):
                yield key

    async def ping(self):
        return True


def run(coro):
    return asyncio.run(coro)


def test_lock_acquire_release_requires_matching_token(monkeypatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(settings, "redis_enabled", True)
    monkeypatch.setattr(redis_layer, "_client", fake)

    token = run(redis_layer.acquire_lock("lock:test", ttl=3))

    assert token
    assert fake.set_calls[-1][2] == {"nx": True, "px": 3000}
    assert run(redis_layer.acquire_lock("lock:test", ttl=3)) is None
    assert run(redis_layer.release_lock("lock:test", "wrong-token")) is False
    assert "lock:test" in fake.values
    assert run(redis_layer.release_lock("lock:test", token)) is True
    assert "lock:test" not in fake.values


def test_redis_errors_are_safe_degradation(monkeypatch) -> None:
    class BrokenRedis(FakeRedis):
        async def set(self, *args, **kwargs):
            raise ConnectionError("redis unavailable")

        async def get(self, *args, **kwargs):
            raise ConnectionError("redis unavailable")

        async def delete(self, *args, **kwargs):
            raise ConnectionError("redis unavailable")

    monkeypatch.setattr(settings, "redis_enabled", True)
    monkeypatch.setattr(redis_layer, "_client", BrokenRedis())

    assert run(redis_layer.acquire_lock("lock:down", ttl=3)) is None
    assert run(redis_layer.cache_get("cache:down")) is None
    assert run(redis_layer.cache_set("cache:down", {"ok": True}, ttl=3)) is False
    assert run(redis_layer.cache_delete("cache:down")) is False


def test_cache_round_trip_and_prefix_invalidation(monkeypatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(settings, "redis_enabled", True)
    monkeypatch.setattr(redis_layer, "_client", fake)

    assert run(redis_layer.cache_set("cache:books:list:a", {"items": [1]}, ttl=60)) is True
    assert run(redis_layer.cache_set("cache:books:list:b", ["two"], ttl=60)) is True
    assert run(redis_layer.cache_get("cache:books:list:a")) == {"items": [1]}
    assert run(redis_layer.cache_get("cache:books:list:b")) == ["two"]
    assert json.loads(fake.set_calls[0][1]) == {"items": [1]}

    assert run(redis_layer.cache_delete_prefix("cache:books:list:")) == 2
    assert run(redis_layer.cache_get("cache:books:list:a")) is None


def test_redis_disabled_does_not_create_client(monkeypatch) -> None:
    def unexpected_from_url(*_args, **_kwargs):
        raise AssertionError("Redis client must not be created when disabled")

    monkeypatch.setattr(settings, "redis_enabled", False)
    monkeypatch.setattr(redis_layer, "_client", None)
    monkeypatch.setattr(redis_layer, "from_url", unexpected_from_url)

    assert run(redis_layer.acquire_lock("lock:disabled", ttl=3)) is None
    assert run(redis_layer.cache_get("cache:disabled")) is None


def test_ping_and_client_factory_errors_are_safe(monkeypatch) -> None:
    monkeypatch.setattr(settings, "redis_enabled", True)
    monkeypatch.setattr(redis_layer, "_client", FakeRedis())
    assert run(redis_layer.ping()) is True

    def broken_from_url(*_args, **_kwargs):
        raise ValueError("invalid redis URL")

    monkeypatch.setattr(redis_layer, "_client", None)
    monkeypatch.setattr(redis_layer, "from_url", broken_from_url)
    assert run(redis_layer.ping()) is False
    assert run(redis_layer.acquire_lock("lock:bad-url", ttl=3)) is None
