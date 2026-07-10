"""UI polish guards for desktop-facing text and controls."""

from pathlib import Path


def test_ui_source_does_not_render_return_arrow_glyph():
    """Enter/return glyphs should not appear in UI labels, buttons, or styles."""
    forbidden_glyphs = tuple(
        chr(codepoint) for codepoint in (0x21B5, 0x23CE, 0x21A9, 0x21B2)
    )
    ui_root = Path("XBrainLab/ui")
    offenders = [
        str(path)
        for path in ui_root.rglob("*.py")
        if any(glyph in path.read_text(encoding="utf-8") for glyph in forbidden_glyphs)
    ]
    assert offenders == []
