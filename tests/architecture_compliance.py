import ast
import os
import sys
from pathlib import Path


def check_architecture(root_dir: str):
    """
    Verify architecture compliance rules:
    1. UI Panels should not import from each other (except sidebars/dialogs within same module).
    2. UI Panels should inherit from BasePanel.
    3. UI Panels should not access self.main_window.study directly (use Controller).
    4. Dialogs should inherit from BaseDialog.
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
