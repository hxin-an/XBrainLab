"""Stable source policy for blocking UI modal presentation."""

from __future__ import annotations

import ast
from pathlib import Path


def test_product_ui_does_not_bypass_shared_modal_presentation() -> None:
    """Raw platform message boxes must not re-enter product UI call sites."""
    repository_root = Path(__file__).resolve().parents[4]
    ui_root = repository_root / "XBrainLab" / "ui"
    violations: list[str] = []

    for source_path in sorted(ui_root.rglob("*.py")):
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(source_path))
        relative_path = source_path.relative_to(repository_root)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "PyQt6.QtWidgets":
                if any(alias.name == "QMessageBox" for alias in node.names):
                    violations.append(f"{relative_path}:{node.lineno}: raw import")
            elif isinstance(node, ast.Attribute) and node.attr == "QMessageBox":
                violations.append(f"{relative_path}:{node.lineno}: raw attribute")

    assert violations == []
