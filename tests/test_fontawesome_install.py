import qtawesome
import pytest

from infrastructure.common.qt import icons


@pytest.fixture
def qtawesome_with_dead_font_links(tmp_path, monkeypatch):
    for _prefix, ttf, _charmap in qtawesome._BUNDLED_FONTS:
        (tmp_path / ttf).symlink_to(tmp_path / "missing" / ttf)
    monkeypatch.setattr(icons, "_QTAWESOME_FONTS_DIR", tmp_path)
    monkeypatch.setitem(qtawesome._resource, "iconic", None)


class TestInstallBundledFontawesome5:
    def test_survives_dead_qtawesome_font_links(self, qapp, qtawesome_with_dead_font_links):
        icons.install_bundled_fontawesome5()

        assert not qtawesome.icon("fa5s.network-wired").isNull()

    def test_bundled_fonts_serve_every_fa5_prefix(self, qapp, qtawesome_with_dead_font_links):
        icons.install_bundled_fontawesome5()

        for name in ("fa5.bell", "fa5r.bell", "fa5s.gamepad", "fa5b.steam"):
            assert not qtawesome.icon(name).isNull(), name
