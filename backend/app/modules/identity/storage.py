"""头像对象键规则与校验（Phase 4 统一存储抽象）。

实际读写通过 app.infrastructure.storage.get_storage() 完成：
local 后端落在 storage/avatars/ 下（路径隔离 + 穿越防护），
s3 后端写入配置桶的同名键。"""

from pathlib import Path

AVATAR_STORAGE_ROOT = Path(__file__).resolve().parents[3] / "storage" / "avatars"

ALLOWED_IMAGE_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

MEDIA_TYPE_BY_SUFFIX = {ext: mime for mime, ext in ALLOWED_IMAGE_TYPES.items()}


def avatar_storage_path(filename: str) -> Path:
    """Resolve a stored avatar filename without allowing path traversal."""
    if (
        not filename
        or "/" in filename
        or "\\" in filename
        or ".." in filename
        or filename.startswith(".")
    ):
        raise ValueError("invalid avatar filename")
    return AVATAR_STORAGE_ROOT / filename


def avatar_object_key(filename: str) -> str:
    """统一对象键前缀：avatars/<filename>。"""
    return f"avatars/{avatar_storage_path(filename).name}"


async def save_avatar_bytes(filename: str, data: bytes, content_type: str) -> None:
    from app.infrastructure.storage import get_storage

    await get_storage().put(avatar_object_key(filename), data, content_type=content_type)


async def load_avatar_bytes(filename: str) -> tuple[bytes, str]:
    from app.infrastructure.storage import get_storage
    from app.infrastructure.storage.base import StorageError

    try:
        stored = await get_storage().get(avatar_object_key(filename))
    except StorageError as exc:
        raise FileNotFoundError(filename) from exc
    media = MEDIA_TYPE_BY_SUFFIX.get("." + filename.rsplit(".", 1)[-1].lower(), "application/octet-stream")
    return stored.data, media
