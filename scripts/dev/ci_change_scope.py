"""Classify changed repository paths into CI validation scopes."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class ChangeScope:
    """The CI lanes required for one non-empty diff."""

    product: bool
    ui_visual: bool
    agent_guidance: bool


GUIDANCE_EXACT_PATHS = frozenset(
    {
        "AGENTS.md",
        ".codex/config.toml",
        "scripts/dev/audit_agent_guidance.py",
        "tests/unit/scripts/test_audit_agent_guidance.py",
    }
)
DOCUMENTATION_EXACT_PATHS = frozenset(
    {
        "README.md",
        "CHANGELOG.md",
        "LICENSE",
        "artifacts/README.md",
        "mkdocs.yml",
        "mkdocs.user.yml",
        "scripts/dev/build_docs_portal.py",
        "tests/unit/scripts/test_build_docs_portal.py",
    }
)
DOCUMENTATION_PREFIXES = ("docs/", "user_docs/", "artifacts/docs-site/")
UI_VISUAL_PREFIXES = ("XBrainLab/ui/", "tests/baselines/ui/")
UI_VISUAL_EXACT_PATHS = frozenset(
    {
        "scripts/dev/capture_ui_baseline.py",
        "scripts/dev/capture_ui_polish_surfaces.py",
        "scripts/dev/app_polish_capture_contract.py",
        "scripts/dev/run_app_polish_ui_dpi_gate.py",
        "scripts/dev/update_quality_dashboard.py",
        ".github/workflows/ci.yml",
    }
)


def _has_prefix(path: str, prefixes: tuple[str, ...]) -> bool:
    return path.startswith(prefixes)


def _is_guidance_core_path(path: str) -> bool:
    return path in GUIDANCE_EXACT_PATHS or path.startswith(".agents/")


def _is_documentation_path(path: str) -> bool:
    return path in DOCUMENTATION_EXACT_PATHS or _has_prefix(
        path, DOCUMENTATION_PREFIXES
    )


def _is_ui_visual_path(path: str) -> bool:
    return path in UI_VISUAL_EXACT_PATHS or _has_prefix(path, UI_VISUAL_PREFIXES)


def classify_changed_paths(paths: Iterable[str]) -> ChangeScope:
    """Return the fail-closed CI scope for changed repository-relative paths."""
    changed_paths = tuple(paths)
    if not changed_paths:
        return ChangeScope(product=True, ui_visual=True, agent_guidance=False)

    if all(
        _is_guidance_core_path(path) or _is_documentation_path(path)
        for path in changed_paths
    ) and any(_is_guidance_core_path(path) for path in changed_paths):
        return ChangeScope(product=False, ui_visual=False, agent_guidance=True)

    if all(_is_documentation_path(path) for path in changed_paths):
        return ChangeScope(product=False, ui_visual=False, agent_guidance=False)

    return ChangeScope(
        product=True,
        ui_visual=any(_is_ui_visual_path(path) for path in changed_paths),
        agent_guidance=False,
    )


def main() -> int:
    """Write GitHub Actions output fields for newline-delimited stdin paths."""
    scope = classify_changed_paths(
        path for path in sys.stdin.read().splitlines() if path
    )
    print(f"product={str(scope.product).lower()}")
    print(f"ui_visual={str(scope.ui_visual).lower()}")
    print(f"agent_guidance={str(scope.agent_guidance).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
