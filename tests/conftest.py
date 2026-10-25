import pytest

from img2print import fonts


@pytest.fixture(autouse=True)
def offline_fonts(tmp_path, monkeypatch):
    """Every test gets its own empty font folder, and Google Fonts stays offline."""
    monkeypatch.setenv("IMG2PRINT_FONT_DIR", str(tmp_path / "fonts"))
    monkeypatch.setenv("IMG2PRINT_GOOGLE_FONTS", "0")
    monkeypatch.setattr(fonts, "_catalog", None)
