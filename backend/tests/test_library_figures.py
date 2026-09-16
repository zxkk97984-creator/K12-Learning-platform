"""T10 图片内容契约与导入测试。

覆盖：
- 新 FIG 三段式（描述 :: 图注 :: assets/文件名.svg）解析出 alt/caption/asset；
- 导入后 content 含 src/alt/caption；
- 非法路径/缺失图/非法扩展名 → R8 拒绝（R8 与结构校验 R1-R7 区分）；
- 旧两段 FIG 仍兼容（无 src，不伪造）；
- 静态资源路由安全分发 / 拒绝路径穿越。
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.scripts.validate_library import build_content, parse_chapter_md, _validate_fig_asset, Issue

client = TestClient(app)


def make_block(block_type: str, payload: str) -> dict:
    return {"type": block_type, "payload": payload}


class TestBuildContent:
    def test_fig_three_part_yields_asset(self) -> None:
        content = build_content(make_block("FIG", "训练流程图 :: 训练数据如何进入模型 :: assets/flow.svg"))
        assert content["aria_label"] == "训练流程图"
        assert content["caption"] == "训练数据如何进入模型"
        assert content["asset"] == "assets/flow.svg"

    def test_fig_legacy_two_part_no_asset(self) -> None:
        content = build_content(make_block("FIG", "无障碍描述 :: 图注文字"))
        assert content["aria_label"] == "无障碍描述"
        assert content["caption"] == "图注文字"
        assert "asset" not in content


class TestFigAssetValidation:
    def _tmp_book_dir(self, tmp_path):
        book_dir = tmp_path / "books" / "s" / "tempbook"
        (book_dir / "assets").mkdir(parents=True)
        (book_dir / "assets" / "flow.svg").write_text("<svg></svg>", encoding="utf-8")
        return book_dir

    def test_illegal_traversal_rejected(self, tmp_path) -> None:
        issues: list[Issue] = []
        _validate_fig_asset(self._tmp_book_dir(tmp_path), "assets/../secret.svg", "ch01.md", 5, issues)
        assert any(i.rule == "R8" for i in issues)

    def test_illegal_absolute_rejected(self, tmp_path) -> None:
        issues: list[Issue] = []
        _validate_fig_asset(self._tmp_book_dir(tmp_path), "/etc/passwd", "ch01.md", 5, issues)
        assert any(i.rule == "R8" for i in issues)

    def test_bad_extension_rejected(self, tmp_path) -> None:
        issues: list[Issue] = []
        _validate_fig_asset(self._tmp_book_dir(tmp_path), "assets/flow.exe", "ch01.md", 5, issues)
        assert any(i.rule == "R8" for i in issues)

    def test_missing_file_rejected(self, tmp_path) -> None:
        issues: list[Issue] = []
        _validate_fig_asset(self._tmp_book_dir(tmp_path), "assets/nope.svg", "ch01.md", 5, issues)
        assert any(i.rule == "R8" for i in issues)

    def test_existing_file_ok(self, tmp_path) -> None:
        issues: list[Issue] = []
        _validate_fig_asset(self._tmp_book_dir(tmp_path), "assets/flow.svg", "ch01.md", 5, issues)
        assert not any(i.rule == "R8" for i in issues)


class TestStaticAssetRoute:
    def test_traversal_returns_404(self) -> None:
        resp = client.get("/api/v1/library-assets/ai-primary-fun/..%2F..%2Fsecret")
        assert resp.status_code == 404

    def test_unknown_book_returns_404(self) -> None:
        resp = client.get("/api/v1/library-assets/definitely-not-a-book/x.svg")
        assert resp.status_code == 404

    def test_bad_extension_returns_404(self) -> None:
        resp = client.get("/api/v1/library-assets/ai-primary-fun/readme.txt")
        assert resp.status_code == 404

    def test_existing_book_missing_asset_returns_404(self) -> None:
        # 真实书存在但无 assets 目录/文件 → 404。
        resp = client.get("/api/v1/library-assets/ai-primary-fun/anything.svg")
        assert resp.status_code == 404


class TestLegacyFigImportNoFakeSrc:
    """旧两段 FIG 导入后不得伪造 src（缺图即如实缺）。"""

    def test_fig_content_legacy_has_no_src(self) -> None:
        content = build_content(make_block("FIG", "无障碍描述 :: 图注文字"))
        assert "src" not in content
        assert "asset" not in content
        # 导入转换仅在显式 asset 引用时才加 src。
        from app.scripts.import_library import _fig_content
        out = _fig_content(dict(content), "legacy-book")
        assert "src" not in out
        assert out.get("alt") == "无障碍描述"
        assert out.get("caption") == "图注文字"

    def test_fig_content_with_asset_gets_src(self) -> None:
        from app.scripts.import_library import _fig_content
        content = build_content(make_block("FIG", "描述 :: 图注 :: assets/flow.svg"))
        out = _fig_content(content, "ml-how-machines-learn")
        assert out["src"].endswith("/api/v1/library-assets/ml-how-machines-learn/flow.svg")
        assert out["alt"] == "描述"
        assert out["caption"] == "图注"
        assert "asset" not in out
