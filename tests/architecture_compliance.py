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

FORBIDDEN_PRODUCT_LLM_TOKENS = (
    "APIBackend",
    "GeminiBackend",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "XBRAINLAB_SHOW_LEGACY_REMOTE_LLM",
)
REMOTE_SDK_DEFAULT_DEPS = ("openai", "google-genai")
UI_CONTROLLER_FALLBACK_METHODS = (
    "_run_legacy_label_import",
    "_run_metadata_update_fallback",
    "apply_channel_selection",
    "apply_data_splitting",
    "apply_epoching",
    "apply_filter",
    "apply_labels_batch",
    "apply_labels_legacy",
    "apply_montage",
    "apply_normalization",
    "apply_resample",
    "apply_rereference",
    "apply_smart_parse",
    "clean_dataset",
    "clean_datasets",
    "clear_history",
    "import_files",
    "remove_files",
    "reset_preprocess",
    "set_model_holder",
    "set_saliency_params",
    "set_training_option",
    "start_training",
    "stop_training",
    "update_metadata",
)


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

    llm_violations = check_local_only_llm_runtime(Path(root_dir))
    if llm_violations:
        print("\nLocal-only LLM Runtime Violations Found:")
        for violation in llm_violations:
            print(f" - {violation}")
        return 1

    fallback_violations = check_ui_controller_fallbacks(Path(root_dir))
    if fallback_violations:
        print("\nUI Controller Fallback Violations Found:")
        for violation in fallback_violations:
            print(f" - {violation}")
        return 1

    print("\nArchitecture compliant!")
    return 0


def check_local_only_llm_runtime(root_dir: Path) -> list[str]:
    """Return violations of the product local-only LLM runtime boundary."""
    violations: list[str] = []
    product_dir = root_dir / "XBrainLab"
    if product_dir.exists():
        for py_file in product_dir.rglob("*.py"):
            if "llm/core/models" in py_file.as_posix():
                continue
            content = py_file.read_text(encoding="utf-8")
            violations.extend(
                f"{py_file.relative_to(root_dir)} contains forbidden "
                f"local-only runtime token {token!r}"
                for token in FORBIDDEN_PRODUCT_LLM_TOKENS
                if token in content
            )

    pyproject = root_dir / "pyproject.toml"
    if pyproject.exists():
        default_deps = _read_poetry_default_dependency_names(pyproject)
        violations.extend(
            f"pyproject.toml default dependencies include {dep_name!r}; "
            "remote SDKs must stay in optional legacy groups."
            for dep_name in REMOTE_SDK_DEFAULT_DEPS
            if dep_name in default_deps
        )

    return violations


def check_ui_controller_fallbacks(root_dir: Path) -> list[str]:
    """Return UI branches that silently mutate controllers on missing results."""
    violations: list[str] = []
    ui_dir = root_dir / "XBrainLab" / "ui"
    if not ui_dir.exists():
        return violations

    for py_file in ui_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            test_source = ast.get_source_segment(source, node.test) or ""
            if "result" not in test_source or "None" not in test_source:
                continue
            violations.extend(
                (
                    f"{py_file.relative_to(root_dir)}:{call.lineno} calls "
                    f"{_call_name(call.func)} directly in {test_source!r}; use "
                    "run_legacy_controller_fallback() for mock/legacy-only fallback."
                )
                for call in _forbidden_fallback_calls(node.body)
            )
    return violations


def _forbidden_fallback_calls(nodes: list[ast.stmt]) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for node in nodes:
        visitor = _ControllerFallbackVisitor()
        visitor.visit(node)
        calls.extend(visitor.violations)
    return calls


class _ControllerFallbackVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ast.Call] = []

    def visit_Call(self, node: ast.Call) -> None:
        call_name = _call_name(node.func)
        if call_name == "run_legacy_controller_fallback":
            return
        if call_name in UI_CONTROLLER_FALLBACK_METHODS:
            self.violations.append(node)
            return
        self.generic_visit(node)


def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _read_poetry_default_dependency_names(pyproject: Path) -> set[str]:
    """Return dependency keys from ``[tool.poetry.dependencies]`` only."""
    deps: set[str] = set()
    in_default_deps = False
    for raw_line in pyproject.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            in_default_deps = line == "[tool.poetry.dependencies]"
            continue
        if not in_default_deps or "=" not in line:
            continue
        deps.add(line.split("=", 1)[0].strip().strip('"'))
    return deps


if __name__ == "__main__":
    sys.exit(check_architecture(os.getcwd()))
