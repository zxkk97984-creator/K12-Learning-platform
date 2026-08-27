"""统一对象存储抽象（Phase 4）。

知识库源文件与学生头像共用同一接口；后端可配置为本地磁盘或
S3 兼容对象存储（AWS Signature V4，基于 httpx 实现，无额外依赖）。

选择依据：settings.storage_backend = "local" | "s3"。
未配置 s3 必需项时，工厂抛出 StorageConfigError（明确、可观察），
绝不静默回退到本地，避免「以为上了对象存储实际落在本地盘」。
"""

from dataclasses import dataclass
from typing import Protocol

from app.config import settings


class StorageError(RuntimeError):
    """存储操作失败（网络/权限/不存在等）。"""


class StorageConfigError(StorageError):
    """存储后端配置缺失或非法。"""


@dataclass(frozen=True)
class StoredObject:
    key: str
    data: bytes
    content_type: str | None


class ObjectStorage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str | None = None) -> str: ...
    async def get(self, key: str) -> StoredObject: ...
    async def exists(self, key: str) -> bool: ...


def validate_key(key: str) -> str:
    """规范化并校验对象键：拒绝绝对路径与路径穿越。"""
    cleaned = key.strip().lstrip("/")
    if not cleaned or ".." in cleaned.split("/") or "\\" in cleaned or cleaned.startswith("."):
        raise StorageError(f"illegal storage key: {key!r}")
    return cleaned
