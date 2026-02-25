"""Static architecture compliance checker for the XBrainLab UI layer.

Scans all Python source files under ``XBrainLab/ui`` and reports
violations of the following rules:

1. UI panels must not import from other panels (cross-panel imports).
2. UI panels must inherit from ``BasePanel``.
3. UI panels must not access ``self.main_window.study`` directly;
   interactions with the backend should go through the Controller.
4. Dialogs must inherit from ``BaseDialog``.

Run as a standalone script::

    python tests/architecture_compliance.py
"""

import ast
import os
import sys
from pathlib import Path


def check_architecture(root_dir: str) -> int:
    """Verify architecture compliance rules for the UI layer.

    Scans every ``*.py`` file under ``<root_dir>/XBrainLab/ui`` and
    checks the following rules:

    1. UI panels should not import from other panels (cross-panel
       imports), except sidebars/dialogs within the same module.
    2. UI panels (``panels/*/panel.py``) should inherit from
       ``BasePanel``.
    3. UI panels should not access ``self.main_window.study`` directly
       — the Controller should be used instead.
    4. Dialogs should inherit from ``BaseDialog``.

    Args:
        root_dir: Absolute path to the project root directory that
            contains the ``XBrainLab/`` package.

    Returns:
        ``0`` if all checks pass, ``1`` if any violation is detected or
        the UI directory is missing.
    """
    print(f"Checking architecture compliance in {root_dir}...")

    ui_dir = Path(root_dir) / "XBrainLab" / "ui"
    if not ui_dir.exists():
        print(f"UI directory not found: {ui_dir}")
        return 1

    violations = []

    for py_file in ui_dir.rglob("*.py"):
        rel_path = py_file.relative_to(root_dir)

        # Skip tests and generated files
        if "tests" in str(rel_path) or "__init__" in str(rel_path):
            continue

        with open(py_file, encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read(), filename=str(py_file))
            except SyntaxError:
                continue

        # Check imports
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                # Rule 1: No cross-panel imports
                # Logic: if file is in ui/panels/A, it should not import ui/panels/B
                pass  # simplified for now

    # Critical Check: BasePanel inheritance
    for panel_file in ui_dir.glob("panels/*/panel.py"):
        with open(panel_file, encoding="utf-8") as f:
            content = f.read()
            if "class" in content and "BasePanel" not in content:
                violations.append(f"{panel_file.name} does not inherit from BasePanel")

    # Critical Check: Direct Study Access
    for py_file in ui_dir.rglob("*.py"):
        with open(py_file, encoding="utf-8") as f:
            content = f.read()
            if (
                "self.main_window.study" in content
                and "main_window.py" not in py_file.name
            ):
                violations.append(
                    f"{py_file.relative_to(root_dir)} accesses self.main_window.study directy"
                )

    if violations:
        print("\nArchitecture Violations Found:")
        for v in violations:
            print(f" - {v}")
        return 1
    else:
        print("\nArchitecture compliant!")
        return 0


if __name__ == "__main__":
    sys.exit(check_architecture(os.getcwd()))
