"""本地磁盘实现：根目录隔离（settings.storage_local_root）。"""

import asyncio
from pathlib import Path

from app.config import settings
from app.infrastructure.storage.base import (
    StoredObject,
    StorageError,
    validate_key,
)


class LocalObjectStorage:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or settings.storage_local_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        cleaned = validate_key(key)
        path = (self.root / cleaned).resolve()
        if not str(path).startswith(str(self.root)):
            # 双保险：符号链接/解析后的逃逸同样拦截
            raise StorageError(f"key escapes local root: {key!r}")
        return path

    async def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        path = self._resolve(key)
        await asyncio.to_thread(lambda: (path.parent.mkdir(parents=True, exist_ok=True), path.write_bytes(data)))
        return key

    async def get(self, key: str) -> StoredObject:
        path = self._resolve(key)
        if not path.is_file():
            raise StorageError(f"object not found: {key}")
        data = await asyncio.to_thread(path.read_bytes)
        return StoredObject(key=key, data=data, content_type=None)

    async def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()
