"""Tests for platform-aware native subprocess safety setup."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from scripts.dev import native_process_safety

ROOT = Path(__file__).resolve().parents[3]
NATIVE_STRESS_SCRIPTS = (
    ROOT / "scripts" / "dev" / "run_ui_native_render_stress.py",
    ROOT / "scripts" / "dev" / "run_preprocess_async_filter_stress.py",
    ROOT / "scripts" / "dev" / "run_preprocess_native_lifecycle_stress.py",
)


def test_non_posix_platform_reports_core_limit_as_unsupported(monkeypatch) -> None:
    monkeypatch.setattr(native_process_safety.os, "name", "nt")

    policy = native_process_safety.disable_core_dumps()

    assert policy.core_dump_limit_supported is False
    assert policy.core_dumps_disabled is False


@pytest.mark.parametrize(
    "script_path", NATIVE_STRESS_SCRIPTS, ids=lambda path: path.stem
)
def test_native_safety_guard_precedes_native_imports(script_path: Path) -> None:
    tree = ast.parse(script_path.read_text(encoding="utf-8"))
    setup = next(
        node
        for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "disable_core_dumps"
    )
    guard = next(
        node
        for node in tree.body
        if isinstance(node, ast.If)
        and any(
            isinstance(candidate, ast.Attribute)
            and candidate.attr == "core_dump_limit_supported"
            for candidate in ast.walk(node.test)
        )
        and any(isinstance(candidate, ast.Raise) for candidate in ast.walk(node))
    )
    first_native_import = min(
        node.lineno
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and node.module.split(".", 1)[0] in {"PyQt6", "XBrainLab"}
    )

    assert setup.lineno < guard.lineno < first_native_import
