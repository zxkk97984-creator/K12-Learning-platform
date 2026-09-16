"""图书馆语料库结构校验器（不依赖数据库、不修改任何文件）。

用法：
    uv run python -m app.scripts.validate_library --book <slug>
    uv run python -m app.scripts.validate_library --all

校验规则编号（与 data/library/README.md 对应）：
    R1  每本书 5~7 章；每章 estimated_minutes 在 8~25
    R2  每章 >=12 个内容块；其中 KC>=2、CALL>=1、FIG>=1，其余为 P/T
    R3  P 块正文 60~240 个中文字符；KC 定义正文 40~120 个中文字符
    R4  全书所有块正文合计 >=6000 个中文字符
    R5  禁止「占位/待补充/TODO/例如等等」；相邻两块正文不得重复
    R6  @kp 引用的 slug 必须在本书 knowledge_points 中声明过
    R7  JSON/Markdown 解析合法；meta 与 book.json 一致；mark 是正文子串；
        文件与章节清单一一对应；slug/manifest 全局一致
    K1  知识库文档 front matter 合法且字段齐全
    K2  知识库文档正文 800~1500 个中文字符
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

LIB_ROOT = Path(__file__).resolve().parents[2] / "data" / "library"

BLOCK_PREFIXES = ("T:", "P:", "KC:", "CALL:", "FIG:")
ALLOWED_LINE_RE = re.compile(r"^(T|P|KC|CALL|FIG): |^S: |^@kp=")
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# T10：图解资源引用仅允许 asset 目录下的安全文件名（相对路径、无穿越、白名单扩展名）。
_ALLOWED_ASSET_RE = re.compile(r"^assets/[A-Za-z0-9._-]+$")
_ALLOWED_ASSET_EXT = {".svg", ".png", ".webp", ".jpg", ".jpeg"}
META_KEYS = ("chapter_title", "estimated_minutes", "summary")
FORBIDDEN_TOKENS = ("占位", "待补充", "TODO", "todo", "例如等等")
CJK_RE = re.compile(r"[\u3400-\u9fff]")
GRADE_BANDS = ("小学", "初中", "高中")
DIFFICULTIES = ("EASY", "MEDIUM", "HARD")

P_CJK_RANGE = (60, 240)
KC_CJK_RANGE = (40, 120)
BOOK_MIN_CJK = 6000
KNOWLEDGE_CJK_RANGE = (800, 1500)


class Issue:
    def __init__(self, rule: str, where: str, message: str) -> None:
        self.rule = rule
        self.where = where
        self.message = message

    def render(self, book: str) -> str:
        return f"  [FAIL][{self.rule}][{book}/{self.where}] {self.message}"


def cjk_count(text: str) -> int:
    return len(CJK_RE.findall(text))


def iter_text_strings(value: Any) -> list[str]:
    """Collect all plain strings inside a JSON-ish structure."""
    found: list[str] = []
    if isinstance(value, str):
        found.append(value)
    elif isinstance(value, dict):
        for v in value.values():
            found.extend(iter_text_strings(v))
    elif isinstance(value, list):
        for v in value:
            found.extend(iter_text_strings(v))
    return found


# --------------------------------------------------------------------------- #
# Chapter markdown parsing
# --------------------------------------------------------------------------- #

def parse_meta(lines: list[str], where: str, issues: list[Issue]) -> dict[str, str]:
    """Validate the leading <!-- meta ... --> comment; return its key/values."""
    first_idx = next((i for i, l in enumerate(lines) if l.strip()), None)
    if first_idx is None or not lines[first_idx].strip().startswith("<!-- meta"):
        issues.append(Issue("R7", where, "文件必须以 <!-- meta ... --> 注释开头"))
        return {}
    meta: dict[str, str] = {}
    closed = False
    for idx in range(first_idx, len(lines)):
        raw = lines[idx]
        stripped = raw.strip()
        if idx == first_idx:
            continue
        if stripped == "-->":
            closed = True
            break
        if ":" not in stripped:
            issues.append(Issue("R7", where, f"meta 第 {idx + 1} 行缺少冒号：{stripped!r}"))
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        if key not in META_KEYS:
            issues.append(
                Issue("R7", where, f"meta 含未知键 {key!r}（只允许 {META_KEYS}）")
            )
        meta[key] = value.strip()
    if not closed:
        issues.append(Issue("R7", where, "meta 注释未以 --> 结束"))
    for key in META_KEYS:
        if key not in meta:
            issues.append(Issue("R7", where, f"meta 缺少必需键 {key}"))
    return meta


def parse_chapter_md(path: Path, issues: list[Issue]) -> tuple[list[dict], dict[str, str]]:
    """Strictly parse a chapter file into blocks + meta.

    Returns (blocks, meta); each block is
    {"type","line","section_key","kps","parts"} where parts is the raw
    payload after the marker prefix.
    """
    rel = path.name
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        issues.append(Issue("R7", rel, f"文件不是合法 UTF-8：{exc}"))
        return [], {}

    lines = text.splitlines()
    meta = parse_meta(lines, rel, issues)

    blocks: list[dict] = []
    section_key: str | None = None
    seen_meta_close = False

    for idx, raw in enumerate(lines):
        lineno = idx + 1
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if not seen_meta_close:
            if stripped == "-->":
                seen_meta_close = True
                continue
            # Inside/around the meta comment region: skip until close.
            continue
        if stripped.startswith("@kp="):
            slugs = [s.strip() for s in stripped[len("@kp="):].split(",") if s.strip()]
            if not blocks:
                issues.append(Issue("R7", rel, f"第 {lineno} 行 @kp= 上方没有任何内容块"))
            else:
                blocks[-1]["kps"].extend(slugs)
            continue
        if stripped.startswith("S:"):
            section_key = stripped[len("S:"):].strip()
            if not section_key:
                issues.append(Issue("R7", rel, f"第 {lineno} 行 S: 锚点名不能为空"))
            continue
        matched_prefixes = [p for p in BLOCK_PREFIXES if stripped.startswith(p)]
        if not matched_prefixes:
            if ALLOWED_LINE_RE.match(stripped):
                issues.append(
                    Issue("R7", rel, f"第 {lineno} 行标记后缺少空格：{stripped[:12]!r}...")
                )
            else:
                issues.append(
                    Issue(
                        "R7",
                        rel,
                        f"第 {lineno} 行不是允许的标记行（T/P/KC/CALL/FIG/S/@kp）："
                        f"{stripped[:24]!r}",
                    )
                )
            continue
        marker = matched_prefixes[0][: -1]  # e.g. "T"
        payload = stripped[len(marker) + 1:].strip()
        if not payload:
            issues.append(Issue("R7", rel, f"第 {lineno} 行 {marker}: 内容不能为空"))
            continue
        blocks.append(
            {
                "type": marker,
                "line": lineno,
                "section_key": section_key,
                "kps": [],
                "payload": payload,
            }
        )

    return blocks, meta


TYPE_TO_DB = {"T": "TITLE", "P": "PARAGRAPH", "KC": "KNOWLEDGE_CARD", "CALL": "CALLOUT", "FIG": "FIGURE"}


def build_content(block: dict) -> dict[str, Any]:
    """Convert a parsed block's payload into its content JSON shape."""
    payload = block["payload"]
    btype = block["type"]
    if btype == "T":
        return {"text": payload}
    if btype == "P":
        if "|mark:" in payload:
            text, _, rest = payload.rpartition("|mark:")
            mark = rest.strip()
            return {"text": text.strip(), "mark": mark}
        return {"text": payload}
    if btype == "KC":
        segs = [seg.strip() for seg in payload.split("::")]
        content: dict[str, Any] = {"title": segs[0], "text": segs[1] if len(segs) > 1 else ""}
        if len(segs) >= 4 and segs[2] and segs[3]:
            content["example"] = {"label": segs[2], "text": segs[3]}
        return content
    if btype == "CALL":
        title, _, text = payload.partition("::")
        return {"title": title.strip(), "text": text.strip()}
    if btype == "FIG":
        # FIG 兼容旧式两段：描述 :: 图注。可选资源引用采用显式 `:: assets/<file>`
        # 结尾；只有结尾段严格匹配 assets/<文件名> 才视为 asset，避免把含 `::`
        # 的普通图注误判为资源（如"权利…阶梯：每一级…考量"）。
        aria, _, rest = payload.partition("::")
        aria = aria.strip()
        caption = rest.strip()
        asset = None
        if "::" in rest:
            tail_src, _, tail = rest.rpartition("::")
            tail = tail.strip()
            if _ALLOWED_ASSET_RE.match(tail) and not tail_src.endswith("::"):
                asset = tail
                caption = (tail_src + "::").strip()
                caption = caption.rstrip(":").strip() or caption
        content: dict[str, Any] = {
            "aria_label": aria,
            "caption": caption,
        }
        if asset:
            content["asset"] = asset
        return content
    raise ValueError(f"unknown block type {btype}")  # pragma: no cover


def main_text_of(content: dict[str, Any]) -> str:
    """The primary prose of a block (used for duplicate detection)."""
    if "text" in content and isinstance(content["text"], str):
        return content["text"]
    return ""


# T10：图解资源引用校验（规则与 build_content 一致，解析后必须落在本书目录内）。
def _fig_asset_path(book_dir: Path, asset: str) -> Path:
    """把 asset 引用解析为绝对路径；解析失败视为不可用（由调用方记 R8）。"""
    return (book_dir / asset.lstrip("/")).resolve()


def _validate_fig_asset(
    book_dir: Path, asset: str, rel: str, line: int, issues: list[Issue]
) -> None:
    where = f"{rel}:{line}"
    if "\\" in asset or asset.startswith("/") or not _ALLOWED_ASSET_RE.match(asset):
        issues.append(
            Issue("R8", where, f"图解资源路径非法（仅允许 assets/<文件名> 相对路径）：{asset!r}")
        )
        return
    if Path(asset).suffix.lower() not in _ALLOWED_ASSET_EXT:
        issues.append(
            Issue("R8", where, f"图解资源扩展名不允许：{Path(asset).suffix!r}")
        )
        return
    target = _fig_asset_path(book_dir, asset)
    if not target.is_relative_to(book_dir.resolve()):
        issues.append(Issue("R8", where, f"图解资源越出本书目录（路径穿越）：{asset!r}"))
        return
    if not target.is_file():
        issues.append(
            Issue("R8", where, f"引用的图解资源不存在：{asset}")
        )


# --------------------------------------------------------------------------- #
# Validation passes
# --------------------------------------------------------------------------- #

def validate_book_json(book_dir: Path, manifest_slugs: set[str], global_kp_slugs: dict[str, str],
                       issues: list[Issue]) -> dict | None:
    slug = book_dir.name
    where = "book.json"
    if not SLUG_RE.match(slug):
        issues.append(Issue("R7", where, f"目录名 {slug!r} 不符合 slug 规则 [a-z0-9-]+"))
    path = book_dir / where
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        issues.append(Issue("R7", where, f"JSON 解析失败：{exc}"))
        return None

    required = ["slug", "title", "description", "grade_min", "grade_max", "difficulty",
                "estimated_minutes", "tags", "topic", "license", "copyright_status",
                "knowledge_points", "chapters"]
    for key in required:
        if key not in data:
            issues.append(Issue("R7", where, f"缺少必需字段 {key}"))
    if any(key not in data for key in required):
        return data

    if data["slug"] != slug:
        issues.append(Issue("R7", where, f"slug={data['slug']!r} 与目录名不一致"))
    if data["slug"] not in manifest_slugs:
        issues.append(Issue("R7", "manifest.json", f"书 {slug} 未登记进 manifest.books"))
    for field in ("title", "description", "topic", "license", "copyright_status"):
        if not isinstance(data[field], str) or not data[field].strip():
            issues.append(Issue("R7", where, f"{field} 必须是非空字符串"))
    if data["difficulty"] not in DIFFICULTIES:
        issues.append(Issue("R7", where, f"difficulty 必须是 {DIFFICULTIES} 之一"))
    grades = (data["grade_min"], data["grade_max"])
    if not all(isinstance(g, int) and 1 <= g <= 12 for g in grades):
        issues.append(Issue("R7", where, "grade_min/grade_max 必须是 1~12 的整数"))
    elif grades[0] > grades[1]:
        issues.append(Issue("R7", where, "grade_min 不能大于 grade_max"))
    if not isinstance(data["estimated_minutes"], int) or data["estimated_minutes"] <= 0:
        issues.append(Issue("R7", where, "estimated_minutes 必须是正整数"))

    kps = data["knowledge_points"]
    if not isinstance(kps, list) or not (4 <= len(kps) <= 8):
        issues.append(Issue("R7", where, f"knowledge_points 需要 4~8 个，当前 {len(kps)}"))
    for kp in kps:
        for key in ("slug", "name", "description", "topic"):
            if not kp.get(key):
                issues.append(Issue("R7", where, f"知识点缺字段 {key}: {kp}"))
        kp_slug = kp.get("slug", "")
        if kp_slug and not SLUG_RE.match(kp_slug):
            issues.append(Issue("R7", where, f"知识点 slug 非法：{kp_slug!r}"))
        if kp_slug in global_kp_slugs and global_kp_slugs[kp_slug] != slug:
            issues.append(
                Issue("R7", where,
                      f"知识点 slug {kp_slug!r} 已被书 {global_kp_slugs[kp_slug]} 占用")
            )
        else:
            global_kp_slugs[kp_slug] = slug

    chapters = data["chapters"]
    if not isinstance(chapters, list) or not (5 <= len(chapters) <= 7):
        issues.append(Issue("R1", where, f"章节数必须是 5~7，当前 "
                                         f"{len(chapters) if isinstance(chapters, list) else '非列表'}"))
    declared_files: set[str] = set()
    for i, ch in enumerate(chapters, start=1):
        tag = f"chapters[{i}]"
        if ch.get("order") != i:
            issues.append(Issue("R7", where, f"{tag}.order 应为 {i}，实际 {ch.get('order')}"))
        for key in ("file", "title", "summary"):
            if not isinstance(ch.get(key), str) or not ch[key].strip():
                issues.append(Issue("R7", where, f"{tag} 缺少非空字段 {key}"))
        minutes = ch.get("minutes")
        if not isinstance(minutes, int) or not (8 <= minutes <= 25):
            issues.append(Issue("R1", where, f"{tag}.minutes 必须在 8~25，实际 {minutes}"))
        f = ch.get("file", "")
        if f:
            if f in declared_files:
                issues.append(Issue("R7", where, f"{tag}.file 重复引用 {f}"))
            declared_files.add(f)
            if not (book_dir / f).is_file():
                issues.append(Issue("R7", where, f"{tag}.file 不存在：{f}"))
    actual_files = sorted(p.name for p in book_dir.glob("*.md"))
    extra = sorted(set(actual_files) - declared_files)
    if extra:
        issues.append(Issue("R7", where, f"存在未登记的章节文件：{extra}"))
    return data


def validate_chapter(book: dict, book_dir: Path, ch: dict, issues: list[Issue]) -> dict:
    """Validate one chapter file against the quality bars; return its stats."""
    rel = ch["file"]
    path = book_dir / rel
    blocks, meta = parse_chapter_md(path, issues)

    if meta:
        if meta.get("chapter_title") != ch["title"]:
            issues.append(
                Issue("R7", rel,
                      f"meta.chapter_title={meta.get('chapter_title')!r} 与 book.json "
                      f"title={ch['title']!r} 不一致")
            )
        try:
            m_minutes = int(meta.get("estimated_minutes", ""))
        except ValueError:
            m_minutes = None
        if m_minutes != ch["minutes"]:
            issues.append(
                Issue("R1", rel,
                      f"meta.estimated_minutes={meta.get('estimated_minutes')!r} 与 "
                      f"book.json minutes={ch['minutes']} 不一致（或不是整数）")
            )
        if meta.get("summary") != ch["summary"]:
            issues.append(
                Issue("R7", rel, "meta.summary 与 book.json 该章 summary 不一致")
            )

    counts = {"T": 0, "P": 0, "KC": 0, "CALL": 0, "FIG": 0}
    total_cjk = 0
    prev_norm: str | None = None
    declared_kp_slugs = {kp.get("slug") for kp in book.get("knowledge_points", [])}

    for i, block in enumerate(blocks, start=1):
        counts[block["type"]] += 1
        content = build_content(block)

        if block["type"] == "P":
            n = cjk_count(content["text"])
            lo, hi = P_CJK_RANGE
            if not lo <= n <= hi:
                issues.append(
                    Issue("R3", f"{rel}:{block['line']}",
                          f"P 块正文 {n} 个中文字符，要求 {lo}~{hi}")
                )
            mark = content.get("mark")
            if mark and mark not in content["text"]:
                issues.append(
                    Issue("R7", f"{rel}:{block['line']}",
                          f"|mark:{mark} 不是该 P 块正文的子串")
                )
        elif block["type"] == "KC":
            if not content.get("title"):
                issues.append(Issue("R7", f"{rel}:{block['line']}", "KC 卡片标题不能为空"))
            n = cjk_count(content.get("text", ""))
            lo, hi = KC_CJK_RANGE
            if not lo <= n <= hi:
                issues.append(
                    Issue("R3", f"{rel}:{block['line']}",
                          f"KC 定义正文 {n} 个中文字符，要求 {lo}~{hi}")
                )
        elif block["type"] == "CALL":
            if not content.get("title") or not content.get("text"):
                issues.append(
                    Issue("R7", f"{rel}:{block['line']}", "CALL 需要 标题 :: 正文 两段")
                )
        elif block["type"] == "FIG":
            # T10：图解可引用本书 assets/ 下资源；路径必须安全且文件存在，
            # 否则记为图像完整性缺口（R8），不与结构校验（R1-R7）混合统计。
            asset = content.get("asset")
            if asset:
                _validate_fig_asset(book_dir, asset, rel, block["line"], issues)

        for token in FORBIDDEN_TOKENS:
            joined = " ".join(iter_text_strings(content))
            if token in joined:
                issues.append(
                    Issue("R5", f"{rel}:{block['line']}", f"出现禁用字样：{token!r}")
                )

        norm = "".join(main_text_of(content).split())
        if prev_norm is not None and norm and norm == prev_norm:
            issues.append(
                Issue("R5", f"{rel}:{block['line']}", "相邻两块正文完全重复")
            )
        prev_norm = norm

        for kp in block["kps"]:
            if kp not in declared_kp_slugs:
                issues.append(
                    Issue("R6", f"{rel}:{block['line']}",
                          f"@kp 引用了未声明的知识点 {kp!r}（须出现在 book.json "
                          f"knowledge_points）")
                )

        total_cjk += sum(cjk_count(s) for s in iter_text_strings(content))

    n_blocks = len(blocks)
    if n_blocks < 12:
        issues.append(
            Issue("R2", rel, f"内容块只有 {n_blocks} 个，要求 >=12（当前分布 {counts}）")
        )
    if counts["KC"] < 2:
        issues.append(Issue("R2", rel, f"知识卡片只有 {counts['KC']} 个，要求 >=2"))
    if counts["CALL"] < 1:
        issues.append(Issue("R2", rel, f"CALLOUT 只有 {counts['CALL']} 个，要求 >=1"))
    if counts["FIG"] < 1:
        issues.append(Issue("R2", rel, f"FIGURE 只有 {counts['FIG']} 个，要求 >=1"))

    return {
        "file": rel,
        "order": ch["order"],
        "title": ch["title"],
        "minutes": ch["minutes"],
        "blocks": n_blocks,
        "P": counts["P"],
        "KC": counts["KC"],
        "CALL": counts["CALL"],
        "FIG": counts["FIG"],
        "cjk": total_cjk,
    }


FRONTMATTER_KEYS = ("source_name", "source_url", "topic", "grade_band", "license",
                    "copyright_status")


def parse_knowledge_doc(path: Path, issues: list[Issue]) -> tuple[dict[str, str], str, int]:
    """Parse front matter + body; return (front, body, cjk_count)."""
    rel = f"knowledge/{path.name}"
    stem = path.stem
    if not SLUG_RE.match(stem):
        issues.append(Issue("K1", rel, f"文件名 {stem!r} 不符合 slug 规则"))
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        issues.append(Issue("K1", rel, f"文件不是合法 UTF-8：{exc}"))
        return {}, "", 0

    if not text.lstrip().startswith("---"):
        issues.append(Issue("K1", rel, "缺少 front matter（必须以 --- 开头）"))
        return {}, "", 0
    parts = text.lstrip().split("---", 2)
    if len(parts) < 3:
        issues.append(Issue("K1", rel, "front matter 未用 --- 正确闭合"))
        return {}, "", 0
    front_raw, body = parts[1], parts[2]
    front: dict[str, str] = {}
    for line in front_raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" not in line:
            issues.append(Issue("K1", rel, f"front matter 行缺少冒号：{line!r}"))
            continue
        key, _, value = line.partition(":")
        front[key.strip()] = value.strip()

    for key in FRONTMATTER_KEYS:
        if key not in front:
            issues.append(Issue("K1", rel, f"front matter 缺少键 {key}"))
    if front.get("grade_band") not in GRADE_BANDS:
        issues.append(
            Issue("K1", rel,
                  f"grade_band 必须是 {GRADE_BANDS} 之一，实际 {front.get('grade_band')!r}")
        )
    url = front.get("source_url", "")
    if url and not url.startswith(("http://", "https://")):
        issues.append(Issue("K1", rel, "source_url 只能留空或为 http(s) 链接（禁止编造）"))
    for key in ("source_name", "topic", "license", "copyright_status"):
        if front.get(key) is not None and not str(front.get(key, "")).strip():
            issues.append(Issue("K1", rel, f"{key} 不能为空字符串"))

    n = cjk_count(body)
    lo, hi = KNOWLEDGE_CJK_RANGE
    if not lo <= n <= hi:
        issues.append(Issue("K2", rel, f"正文 {n} 个中文字符，要求 {lo}~{hi}"))
    for token in FORBIDDEN_TOKENS:
        if token in body:
            issues.append(Issue("R5", rel, f"出现禁用字样：{token!r}"))
    return front, body, n


def validate_knowledge_doc(path: Path, issues: list[Issue]) -> int:
    _, _, n = parse_knowledge_doc(path, issues)
    return n


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def load_manifest(issues: list[Issue]) -> set[str]:
    path = LIB_ROOT / "manifest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {b.get("slug", "") for b in data.get("books", [])}
    except (OSError, json.JSONDecodeError) as exc:
        issues.append(Issue("R7", "manifest.json", f"读取或解析失败：{exc}"))
        return set()


def validate_book(slug: str, global_kp_slugs: dict[str, str]) -> tuple[list[Issue], list[dict]]:
    issues: list[Issue] = []
    book_dir = LIB_ROOT / "books" / slug
    if not book_dir.is_dir():
        issues.append(Issue("R7", "-", f"找不到书目录 books/{slug}"))
        return issues, []

    manifest_slugs = load_manifest(issues)
    book = validate_book_json(book_dir, manifest_slugs, global_kp_slugs, issues)
    if book is None:
        return issues, []

    stats = []
    for ch in book.get("chapters", []):
        if not (book_dir / ch.get("file", "")).is_file():
            continue
        stats.append(validate_chapter(book, book_dir, ch, issues))
    return issues, stats


def main() -> int:
    parser = argparse.ArgumentParser(description="图书馆语料库结构校验器")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--book", help="校验单本书（按 slug）")
    group.add_argument("--all", action="store_true", help="校验全部书 + 知识库文档")
    args = parser.parse_args()

    all_issues: list[Issue] = []
    global_kp_slugs: dict[str, str] = {}

    if args.book:
        slugs = [args.book]
    else:
        books_root = LIB_ROOT / "books"
        slugs = sorted(p.name for p in books_root.iterdir() if p.is_dir()) \
            if books_root.is_dir() else []

    total_stats: list[tuple[str, list[dict]]] = []
    ok_books = True
    for slug in slugs:
        issues, stats = validate_book(slug, global_kp_slugs)
        all_issues.extend(issues)
        book_issues = [i for i in issues]
        total_cjk = sum(s["cjk"] for s in stats)
        if total_cjk < BOOK_MIN_CJK and stats:
            all_issues.append(
                Issue("R4", "全书", f"总中文字符 {total_cjk}，要求 >=6000")
            )
        passed = not book_issues
        ok_books = ok_books and passed
        status = "PASS" if passed else "FAIL"
        print(f"== {slug}: {status} ==")
        for issue in book_issues:
            print(issue.render(slug))
        if stats:
            for s in stats:
                print(
                    f"   ch{s['order']:>02} {s['file']:<8} blocks={s['blocks']:<3}"
                    f"(P{s['P']}/KC{s['KC']}/CALL{s['CALL']}/FIG{s['FIG']}) "
                    f"minutes={s['minutes']:<3} cjk={s['cjk']}"
                )
            n_blocks = sum(s["blocks"] for s in stats)
            print(
                f"   合计 chapters={len(stats)} blocks={n_blocks} "
                f"cjk={total_cjk}/{BOOK_MIN_CJK}"
            )
        total_stats.append((slug, stats))

    if args.all:
        kdir = LIB_ROOT / "knowledge"
        docs = sorted(kdir.glob("*.md")) if kdir.is_dir() else []
        print(f"== knowledge docs ({len(docs)}) ==")
        for doc in docs:
            before = len(all_issues)
            n = validate_knowledge_doc(doc, all_issues)
            new_issues = all_issues[before:]
            status = "PASS" if not new_issues else "FAIL"
            print(f"   {doc.name:<36} {status} cjk={n}")
            for issue in new_issues:
                print(f"     [FAIL][{issue.rule}] {issue.message}")

    failed = bool(all_issues)
    print()
    print(f"RESULT: {'FAIL' if failed else 'PASS'} "
          f"(books={len(slugs)}, violations={len(all_issues)})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
