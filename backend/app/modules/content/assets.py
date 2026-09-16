"""图书馆书内图解静态资源服务（T10）。

从 data/library/books/<slug>/assets/ 按文件名只读分发，供前端 <img> 加载。
- 仅允许 get（图片引用）；不过鉴权（书内公开内容）。
- 严格防路径穿越：解析后必须落在本书 assets/ 目录内，拒绝绝对路径与 `..`。
- 允许扩展名：svg/png/webp/jpg/jpeg。
- 文件缺失 / 越界 → 404（前端据 alt/caption 显示"图解暂时无法加载"）。
"""

from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.scripts.validate_library import LIB_ROOT

router = APIRouter(tags=["library-assets"])

ALLOWED_EXT = {".svg", ".png", ".webp", ".jpg", ".jpeg"}
CONTENT_TYPES = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".webp": "image/webp",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


@router.get("/library-assets/{book_slug}/{filename}")
async def get_library_asset(book_slug: str, filename: str):
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(status_code=404, detail="asset not found")
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=404, detail="asset not found")
    book_dir = (LIB_ROOT / "books" / book_slug).resolve()
    target = (book_dir / "assets" / unquote(filename)).resolve()
    assets_root = (book_dir / "assets").resolve()
    if not assets_root.is_dir() or not target.is_relative_to(assets_root) or not target.is_file():
        raise HTTPException(status_code=404, detail="asset not found")
    return FileResponse(target, media_type=CONTENT_TYPES[ext])
