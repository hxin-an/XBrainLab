"""Rendered and source-level contract for standard product dialog actions."""

import ast
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialogButtonBox

from XBrainLab.ui.dialogs.common import normalize_dialog_button_box

_REPO_ROOT = Path(__file__).resolve().parents[4]
_UI_ROOT = _REPO_ROOT / "XBrainLab" / "ui"


def _called_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _expression_key(expression: ast.expr) -> str | None:
    if isinstance(expression, ast.Name):
        return expression.id
    if isinstance(expression, ast.Attribute):
        owner = _expression_key(expression.value)
        return f"{owner}.{expression.attr}" if owner else None
    return None


def _standard_button_names(call: ast.Call) -> set[str]:
    return {
        node.attr
        for argument in call.args
        for node in ast.walk(argument)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "StandardButton"
    }


def test_shared_standard_button_box_renders_cancel_left_and_primary_rightmost(
    qtbot,
) -> None:
    button_box = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
    )
    qtbot.addWidget(button_box)
    ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
    cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)
    assert ok_button is not None
    assert cancel_button is not None
    ok_button.setEnabled(False)

    normalize_dialog_button_box(button_box)
    button_box.show()
    qtbot.waitUntil(lambda: button_box.isVisible())

    assert button_box.layoutDirection() is Qt.LayoutDirection.LeftToRight
    assert cancel_button.geometry().right() < ok_button.geometry().left()
    assert not ok_button.isEnabled()
    assert cancel_button.isEnabled()


def test_single_primary_button_keeps_its_existing_role_and_state(qtbot) -> None:
    button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
    qtbot.addWidget(button_box)
    ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
    assert ok_button is not None
    ok_button.setEnabled(False)

    normalize_dialog_button_box(button_box, ok_text="Create")
    button_box.show()
    qtbot.waitUntil(lambda: button_box.isVisible())

    assert button_box.button(QDialogButtonBox.StandardButton.Cancel) is None
    assert ok_button.text() == "Create"
    assert not ok_button.isEnabled()


def test_standard_product_button_boxes_use_one_unconditional_shared_policy() -> None:
    helper_tree = ast.parse(
        (_UI_ROOT / "dialogs" / "common.py").read_text(encoding="utf-8")
    )
    helper = next(
        node
        for node in helper_tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "normalize_dialog_button_box"
    )
    helper_parameters = {
        argument.arg for argument in (*helper.args.args, *helper.args.kwonlyargs)
    }
    assert "confirm_rightmost" not in helper_parameters

    unnormalized: list[str] = []
    unreviewed_roles: list[str] = []
    legacy_opt_ins: list[str] = []
    reviewed_shapes = [{"Ok"}, {"Ok", "Cancel"}]

    for path in sorted(_UI_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        relative_path = path.relative_to(_REPO_ROOT).as_posix()
        for function in (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ):
            normalized_names: set[str] = set()
            for call in (
                node for node in ast.walk(function) if isinstance(node, ast.Call)
            ):
                if _called_name(call) != "normalize_dialog_button_box":
                    continue
                if any(keyword.arg == "confirm_rightmost" for keyword in call.keywords):
                    legacy_opt_ins.append(f"{relative_path}:{call.lineno}")
                if call.args:
                    normalized_name = _expression_key(call.args[0])
                    if normalized_name:
                        normalized_names.add(normalized_name)

            for assignment in (
                node for node in ast.walk(function) if isinstance(node, ast.Assign)
            ):
                if not isinstance(assignment.value, ast.Call):
                    continue
                if _called_name(assignment.value) != "QDialogButtonBox":
                    continue
                roles = _standard_button_names(assignment.value)
                if not roles:
                    continue
                location = f"{relative_path}:{assignment.lineno}"
                if roles not in reviewed_shapes:
                    unreviewed_roles.append(f"{location} ({sorted(roles)})")
                    continue
                assigned_names = {
                    key
                    for target in assignment.targets
                    if (key := _expression_key(target)) is not None
                }
                if not assigned_names & normalized_names:
                    unnormalized.append(location)

    assert legacy_opt_ins == []
    assert unreviewed_roles == []
    assert unnormalized == []
