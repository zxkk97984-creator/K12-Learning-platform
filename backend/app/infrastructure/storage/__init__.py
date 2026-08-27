"""存储工厂：按 settings.storage_backend 返回单例后端。"""

from functools import lru_cache

from app.config import settings
from app.infrastructure.storage.base import (
    ObjectStorage,
    StorageConfigError,
    validate_key,
)
from app.infrastructure.storage.local import LocalObjectStorage


@lru_cache(maxsize=1)
def get_storage() -> ObjectStorage:
    backend = (settings.storage_backend or "local").strip().lower()
    if backend == "local":
        return LocalObjectStorage()
    if backend == "s3":
        from app.infrastructure.storage.s3 import S3ObjectStorage

        return S3ObjectStorage()
    raise StorageConfigError(
        f"未知 storage_backend: {backend!r}（可选 local | s3）"
    )


__all__ = ["get_storage", "ObjectStorage", "StorageConfigError", "validate_key"]
