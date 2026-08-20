import ast
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scripts.dev.active_checkout import assert_active_checkout_import

REQUIRED_CHECKOUT_GUARDED_SCRIPTS = (
    "capture_chatpanel_ui_ux_walkthrough.py",
    "capture_human_like_product_walkthrough.py",
    "inspect_local_assistant_runtime.py",
    "report_data_interpretation_format_matrix.py",
    "run_public_cross_source_training_smoke.py",
)


def test_active_checkout_guard_prepends_the_current_checkout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    root_resolved = repo_root.resolve()
    path_without_root = [
        entry
        for entry in sys.path
        if not entry or Path(entry).resolve() != root_resolved
    ]
    monkeypatch.setattr(sys, "path", path_without_root)

    assert_active_checkout_import(repo_root)

    assert Path(sys.path[0]).resolve() == root_resolved


def test_active_checkout_guard_rejects_another_checkout(tmp_path) -> None:
    expected_root = tmp_path / "expected-checkout"
    package = tmp_path / "foreign-checkout" / "XBrainLab" / "__init__.py"
    package.parent.mkdir(parents=True)
    package.write_text("", encoding="utf-8")

    with (
        patch.dict(
            "sys.modules",
            {"XBrainLab": SimpleNamespace(__file__=str(package))},
        ),
        pytest.raises(RuntimeError, match="different checkout"),
    ):
        assert_active_checkout_import(expected_root)


@pytest.mark.parametrize(
    ("module_name", "relative_path"),
    [
        ("XBrainLab.backend.foreign", Path("XBrainLab/backend/foreign.py")),
        ("scripts.dev.foreign", Path("scripts/dev/foreign.py")),
    ],
)
def test_active_checkout_guard_rejects_mixed_loaded_modules(
    module_name: str,
    relative_path: Path,
    tmp_path: Path,
) -> None:
    expected_root = tmp_path / "expected-checkout"
    foreign_module = tmp_path / "foreign-checkout" / relative_path
    foreign_module.parent.mkdir(parents=True)
    foreign_module.write_text("", encoding="utf-8")

    with (
        patch.dict(
            "sys.modules",
            {module_name: SimpleNamespace(__file__=str(foreign_module))},
        ),
        pytest.raises(RuntimeError, match="different checkout"),
    ):
        assert_active_checkout_import(expected_root)


@pytest.mark.parametrize("script_name", REQUIRED_CHECKOUT_GUARDED_SCRIPTS)
def test_standalone_script_guards_checkout_before_product_import(
    script_name: str,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    source = (repo_root / "scripts" / "dev" / script_name).read_text(encoding="utf-8")
    tree = ast.parse(source)
    guard_line = next(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "assert_active_checkout_import"
    )
    product_import_lines = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and any(
            name == "XBrainLab" or name.startswith("XBrainLab.")
            for name in (
                [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else [alias.name for alias in node.names]
            )
        )
    ]

    assert product_import_lines
    assert guard_line < min(product_import_lines)


def test_representative_standalone_script_bootstraps_from_unrelated_cwd(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    result = subprocess.run(  # noqa: S603 - fixed interpreter and script allowlist
        [
            sys.executable,
            str(repo_root / "scripts/dev/report_data_interpretation_format_matrix.py"),
            "--help",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()
