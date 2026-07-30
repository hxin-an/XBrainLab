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
    package = tmp_path / "XBrainLab" / "__init__.py"
    package.parent.mkdir()
    package.write_text("", encoding="utf-8")

    with (
        patch.dict(
            "sys.modules",
            {"XBrainLab": SimpleNamespace(__file__=str(package))},
        ),
        pytest.raises(RuntimeError, match="different checkout"),
    ):
        assert_active_checkout_import(Path(__file__).resolve().parents[3])


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
    foreign_module = tmp_path / relative_path
    foreign_module.parent.mkdir(parents=True)
    foreign_module.write_text("", encoding="utf-8")

    with (
        patch.dict(
            "sys.modules",
            {module_name: SimpleNamespace(__file__=str(foreign_module))},
        ),
        pytest.raises(RuntimeError, match="different checkout"),
    ):
        assert_active_checkout_import(Path(__file__).resolve().parents[3])


@pytest.mark.parametrize("script_name", REQUIRED_CHECKOUT_GUARDED_SCRIPTS)
@pytest.mark.parametrize("cwd_kind", ("repo_root", "unrelated"))
def test_standalone_script_help_bootstraps_the_intended_checkout(
    script_name: str,
    cwd_kind: str,
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    cwd = repo_root if cwd_kind == "repo_root" else tmp_path
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    result = subprocess.run(  # noqa: S603 - fixed interpreter and script allowlist
        [sys.executable, str(repo_root / "scripts" / "dev" / script_name), "--help"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()
