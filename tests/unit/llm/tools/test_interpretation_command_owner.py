"""Architecture guard for agent Data Interpretation command translation."""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_REAL_DATASET_TOOLS = (
    _REPO_ROOT / "XBrainLab" / "llm" / "tools" / "real" / "dataset_real.py"
)
_FORBIDDEN_CONSTRUCTORS = {
    "PreviewInterpretationCommand",
    "ReloadInterpretationRecipeCommand",
}


def _resolved_symbol(
    expression: ast.expr,
    aliases: dict[str, tuple[str, ...]],
) -> tuple[str, ...] | None:
    if isinstance(expression, ast.Name):
        return aliases.get(expression.id, (expression.id,))
    if isinstance(expression, ast.Attribute):
        owner = _resolved_symbol(expression.value, aliases)
        return (*owner, expression.attr) if owner is not None else None
    return None


def _constructor_aliases(tree: ast.AST) -> dict[str, tuple[str, ...]]:
    aliases: dict[str, tuple[str, ...]] = {}
    assignments: list[ast.Assign | ast.AnnAssign] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for imported in node.names:
                local_name = imported.asname or imported.name.split(".", 1)[0]
                aliases[local_name] = tuple(imported.name.split("."))
        elif isinstance(node, ast.ImportFrom):
            module = tuple((node.module or "").split("."))
            for imported in node.names:
                local_name = imported.asname or imported.name
                aliases[local_name] = (*module, imported.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            assignments.append(node)

    changed = True
    while changed:
        changed = False
        for assignment in assignments:
            value = assignment.value
            if value is None:
                continue
            resolved = _resolved_symbol(value, aliases)
            if resolved is None:
                continue
            targets = (
                assignment.targets
                if isinstance(assignment, ast.Assign)
                else [assignment.target]
            )
            for target in targets:
                if not isinstance(target, ast.Name):
                    continue
                if aliases.get(target.id) != resolved:
                    aliases[target.id] = resolved
                    changed = True
    return aliases


def _forbidden_constructor_calls(source: str) -> list[str]:
    tree = ast.parse(source)
    aliases = _constructor_aliases(tree)
    duplicate_calls = {
        resolved[-1]
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        if (resolved := _resolved_symbol(node.func, aliases)) is not None
        if resolved[-1] in _FORBIDDEN_CONSTRUCTORS
    }
    return sorted(duplicate_calls)


def test_real_interpretation_tools_do_not_duplicate_command_translation() -> None:
    """Mapped Real* tools must reuse the application-surface command builders."""
    duplicate_calls = _forbidden_constructor_calls(
        _REAL_DATASET_TOOLS.read_text(encoding="utf-8")
    )

    assert duplicate_calls == [], (
        "Data Interpretation command translation belongs to application_surface; "
        f"duplicate constructors found in Real* tools: {duplicate_calls}"
    )


def test_guard_detects_direct_constructor_call() -> None:
    source = "PreviewInterpretationCommand(choices={})"

    assert _forbidden_constructor_calls(source) == ["PreviewInterpretationCommand"]


def test_guard_detects_from_import_alias() -> None:
    source = """
from XBrainLab.backend.application import PreviewInterpretationCommand as Preview

Preview(choices={})
"""

    assert _forbidden_constructor_calls(source) == ["PreviewInterpretationCommand"]


def test_guard_detects_module_attribute_alias() -> None:
    source = """
import XBrainLab.backend.application.commands as command_module

command_module.ReloadInterpretationRecipeCommand(recipe_path="recipe.json")
"""

    assert _forbidden_constructor_calls(source) == ["ReloadInterpretationRecipeCommand"]


def test_guard_detects_assignment_alias_chain() -> None:
    source = """
from XBrainLab.backend.application import PreviewInterpretationCommand

first_alias = PreviewInterpretationCommand
second_alias = first_alias
second_alias(choices={})
"""

    assert _forbidden_constructor_calls(source) == ["PreviewInterpretationCommand"]
