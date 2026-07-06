"""UI polish guards for desktop-facing text and controls."""

from pathlib import Path


def test_ui_source_does_not_render_return_arrow_glyph():
    """U+21B5 should not appear in UI labels, buttons, or styles."""
    ui_root = Path("XBrainLab/ui")
    offenders = [
        str(path)
        for path in ui_root.rglob("*.py")
        if "↵" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
