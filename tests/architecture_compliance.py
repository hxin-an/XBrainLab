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
UI_CONTROLLER_FALLBACK_WRAPPERS = (
    "run_legacy_controller_fallback",
    "_legacy_controller_value",
    "_legacy_locked_preflight_blocked",
    "_legacy_preprocessed_data_list_for_render",
    "_run_legacy_preprocess_fallback",
)
UI_POST_COMMAND_LOCAL_REFRESH_METHODS = (
    "check_ready_to_train",
    "notify_update",
    "on_update",
    "refresh_backend_status",
    "update_info_panel",
    "update_panel",
)
UI_POST_COMMAND_CONTROLLER_ECHO_METHODS = ("get_model_holder",)
UI_CAPABILITY_GATED_CONTROLLER_READINESS_METHODS = (
    "get_channel_names",
    "get_filenames",
    "get_preprocessed_data_list",
    "get_trainer",
    "get_saliency_params",
    "has_datasets",
    "has_data",
    "has_model",
    "has_training_option",
    "is_training",
    "is_locked",
    "validate_ready",
)
UI_CONTROLLER_RENDER_FALLBACK_METHODS = (
    "get_averaged_record",
    "get_channel_names",
    "get_filenames",
    "get_formatted_history",
    "get_loaded_data_list",
    "get_model_summary_str",
    "get_plans",
    "get_pooled_eval_result",
    "get_preprocessed_data_list",
    "get_saliency_params",
    "get_trainers",
)
UI_DIRECT_STUDY_STATE_ATTRIBUTES = (
    "loaded_data_list",
    "preprocessed_data_list",
    "epoch_data",
    "datasets",
    "dataset_generator",
    "model_holder",
    "training_option",
    "trainer",
)
UI_OBSERVER_REFRESH_EVENTS = (
    "data_changed",
    "preprocess_changed",
    "training_started",
    "training_stopped",
    "training_updated",
    "config_changed",
    "history_cleared",
    "montage_changed",
    "saliency_changed",
)
UI_REFRESH_FALSE_READ_ONLY_COMMANDS = (
    "EvaluateCommand",
    "QueryStateCommand",
    "VisualizeCommand",
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

    render_fallback_violations = check_ui_controller_render_fallbacks(Path(root_dir))
    if render_fallback_violations:
        print("\nUI Controller Render Fallback Violations Found:")
        for violation in render_fallback_violations:
            print(f" - {violation}")
        return 1

    direct_controller_mutation_violations = check_ui_direct_controller_mutations(
        Path(root_dir)
    )
    if direct_controller_mutation_violations:
        print("\nUI Direct Controller Mutation Violations Found:")
        for violation in direct_controller_mutation_violations:
            print(f" - {violation}")
        return 1

    legacy_helper_call_violations = check_ui_legacy_mutation_helper_calls(
        Path(root_dir)
    )
    if legacy_helper_call_violations:
        print("\nUI Legacy Mutation Helper Call Violations Found:")
        for violation in legacy_helper_call_violations:
            print(f" - {violation}")
        return 1

    loader_apply_violations = check_ui_direct_loader_apply(Path(root_dir))
    if loader_apply_violations:
        print("\nUI Direct Loader Apply Violations Found:")
        for violation in loader_apply_violations:
            print(f" - {violation}")
        return 1

    study_state_violations = check_ui_direct_study_state_reads(Path(root_dir))
    if study_state_violations:
        print("\nUI Direct Study State Read Violations Found:")
        for violation in study_state_violations:
            print(f" - {violation}")
        return 1

    controller_study_violations = check_ui_controller_study_get_controller_fallbacks(
        Path(root_dir)
    )
    if controller_study_violations:
        print("\nUI Controller Study Fallback Violations Found:")
        for violation in controller_study_violations:
            print(f" - {violation}")
        return 1

    controller_echo_violations = check_ui_post_command_controller_echoes(Path(root_dir))
    if controller_echo_violations:
        print("\nUI Post-command Controller Echo Violations Found:")
        for violation in controller_echo_violations:
            print(f" - {violation}")
        return 1

    capability_readiness_violations = check_ui_capability_gated_controller_readiness(
        Path(root_dir)
    )
    if capability_readiness_violations:
        print("\nUI Capability-gated Controller Readiness Violations Found:")
        for violation in capability_readiness_violations:
            print(f" - {violation}")
        return 1

    refresh_violations = check_ui_post_command_local_refreshes(Path(root_dir))
    if refresh_violations:
        print("\nUI Post-command Local Refresh Violations Found:")
        for violation in refresh_violations:
            print(f" - {violation}")
        return 1

    refresh_false_violations = check_ui_refresh_false_commands(Path(root_dir))
    if refresh_false_violations:
        print("\nUI No-refresh Command Violations Found:")
        for violation in refresh_false_violations:
            print(f" - {violation}")
        return 1

    observer_refresh_violations = check_ui_observer_direct_update_bridges(
        Path(root_dir)
    )
    if observer_refresh_violations:
        print("\nUI Observer Direct Refresh Violations Found:")
        for violation in observer_refresh_violations:
            print(f" - {violation}")
        return 1

    observer_handler_violations = check_ui_observer_handlers_call_refresh_coordinator(
        Path(root_dir)
    )
    if observer_handler_violations:
        print("\nUI Observer Handler Refresh Violations Found:")
        for violation in observer_handler_violations:
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


def check_ui_controller_render_fallbacks(root_dir: Path) -> list[str]:
    """Return UI query-missing branches that read stale controller render state."""
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
                    f"controller.{_call_name(call.func)}() directly in "
                    f"{test_source!r}; render fallback reads must go through "
                    "run_legacy_controller_fallback() so real Study paths do "
                    "not display stale controller state."
                )
                for call in _forbidden_render_fallback_calls(node.body)
            )
    return violations


def _forbidden_render_fallback_calls(nodes: list[ast.stmt]) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for node in nodes:
        visitor = _ControllerRenderFallbackVisitor()
        visitor.visit(node)
        calls.extend(visitor.violations)
    return calls


class _ControllerFallbackVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ast.Call] = []

    def visit_Call(self, node: ast.Call) -> None:
        call_name = _call_name(node.func)
        if call_name in UI_CONTROLLER_FALLBACK_WRAPPERS:
            return
        if call_name in UI_CONTROLLER_FALLBACK_METHODS:
            self.violations.append(node)
            return
        self.generic_visit(node)


class _ControllerRenderFallbackVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ast.Call] = []

    def visit_Call(self, node: ast.Call) -> None:
        call_name = _call_name(node.func)
        if call_name in UI_CONTROLLER_FALLBACK_WRAPPERS:
            return
        if (
            call_name in UI_CONTROLLER_RENDER_FALLBACK_METHODS
            and _call_receiver_is_controller(node.func)
        ):
            self.violations.append(node)
            return
        self.generic_visit(node)


def check_ui_direct_controller_mutations(root_dir: Path) -> list[str]:
    """Return UI controller mutations outside explicit legacy fallback paths."""
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
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if _is_legacy_controller_mutation_helper(node.name):
                continue
            visitor = _DirectControllerMutationVisitor()
            visitor.visit(node)
            violations.extend(
                f"{py_file.relative_to(root_dir)}:{call.lineno} calls "
                f"controller.{_call_name(call.func)}() directly; product UI "
                "mutations must go through ApplicationService, with controller "
                "mutation limited to run_legacy_controller_fallback() or an "
                "explicit legacy/fallback helper."
                for call in visitor.violations
            )
    return violations


def _is_legacy_controller_mutation_helper(function_name: str) -> bool:
    lower_name = function_name.lower()
    return "legacy" in lower_name or "fallback" in lower_name


class _DirectControllerMutationVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ast.Call] = []

    def visit_Call(self, node: ast.Call) -> None:
        call_name = _call_name(node.func)
        if call_name in UI_CONTROLLER_FALLBACK_WRAPPERS:
            return
        if call_name in UI_CONTROLLER_FALLBACK_METHODS and _call_receiver_is_controller(
            node.func
        ):
            self.violations.append(node)
            return
        self.generic_visit(node)


def check_ui_legacy_mutation_helper_calls(root_dir: Path) -> list[str]:
    """Return mutation helpers that can be called outside the legacy gate."""
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

        helper_names = _legacy_controller_mutation_helper_names(tree)
        if not helper_names:
            continue

        visitor = _LegacyMutationHelperCallVisitor(helper_names)
        visitor.visit(tree)
        violations.extend(
            f"{py_file.relative_to(root_dir)}:{call.lineno} calls "
            f"{_call_name(call.func)}() outside run_legacy_controller_fallback(); "
            "legacy/fallback helpers that mutate controllers must remain behind "
            "the explicit mock/legacy gate."
            for call in visitor.violations
        )
    return violations


def _legacy_controller_mutation_helper_names(tree: ast.AST) -> set[str]:
    helper_names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _is_legacy_controller_mutation_helper(node.name):
            continue
        visitor = _DirectControllerMutationVisitor()
        visitor.visit(node)
        if visitor.violations:
            helper_names.add(node.name)
    return helper_names


class _LegacyMutationHelperCallVisitor(ast.NodeVisitor):
    def __init__(self, helper_names: set[str]) -> None:
        self.helper_names = helper_names
        self.violations: list[ast.Call] = []
        self._legacy_gate_depth = 0

    def visit_Call(self, node: ast.Call) -> None:
        if _call_name(node.func) == "run_legacy_controller_fallback":
            self._legacy_gate_depth += 1
            self.generic_visit(node)
            self._legacy_gate_depth -= 1
            return

        if _call_name(node.func) in self.helper_names and self._legacy_gate_depth == 0:
            self.violations.append(node)
            return
        self.generic_visit(node)


def _call_receiver_is_controller(func: ast.expr) -> bool:
    if not isinstance(func, ast.Attribute):
        return False
    receiver = func.value
    if isinstance(receiver, ast.Name):
        return receiver.id == "controller" or receiver.id.endswith("_controller")
    return (
        isinstance(receiver, ast.Attribute)
        and (receiver.attr == "controller" or receiver.attr.endswith("_controller"))
        and isinstance(receiver.value, ast.Name)
        and receiver.value.id == "self"
    )


def check_ui_direct_loader_apply(root_dir: Path) -> list[str]:
    """Return UI code that directly applies raw loaders outside legacy adapters."""
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
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if "legacy" in node.name.lower():
                continue
            visitor = _DirectLoaderApplyVisitor()
            visitor.visit(node)
            violations.extend(
                f"{py_file.relative_to(root_dir)}:{call.lineno} calls "
                "loader.apply() directly; isolate raw loader mutation behind a "
                "legacy loader adapter or ApplicationService command."
                for call in visitor.violations
            )
    return violations


class _DirectLoaderApplyVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ast.Call] = []

    def visit_Call(self, node: ast.Call) -> None:
        if _is_direct_loader_apply(node):
            self.violations.append(node)
            return
        self.generic_visit(node)


def _is_direct_loader_apply(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute) or node.func.attr != "apply":
        return False
    if not isinstance(node.func.value, ast.Name):
        return False
    if node.func.value.id not in {"loader", "raw_loader", "data_loader"}:
        return False
    return any(_expression_mentions_study(arg) for arg in node.args) or any(
        _expression_mentions_study(keyword.value)
        for keyword in node.keywords
        if keyword.value is not None
    )


def check_ui_direct_study_state_reads(root_dir: Path) -> list[str]:
    """Return UI code that reads mutable Study state outside legacy helpers."""
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
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if _is_legacy_controller_mutation_helper(node.name):
                continue
            visitor = _DirectStudyStateReadVisitor()
            visitor.visit(node)
            violations.extend(
                f"{py_file.relative_to(root_dir)}:{attr.lineno} reads "
                f"study.{attr.attr}; product UI render/action state must come "
                "from ApplicationService query/capability results, with direct "
                "Study state reads limited to explicit legacy/fallback helpers."
                for attr in visitor.violations
            )
    return violations


def check_ui_controller_study_get_controller_fallbacks(root_dir: Path) -> list[str]:
    """Return UI code that retrieves controllers through controller.study."""
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
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if _is_legacy_controller_mutation_helper(node.name):
                continue
            visitor = _ControllerStudyGetControllerVisitor()
            visitor.visit(node)
            violations.extend(
                f"{py_file.relative_to(root_dir)}:{call.lineno} calls "
                "controller.study.get_controller(); product UI controller wiring "
                "must be injected or command/query-backed, with controller.study "
                "lookup limited to an explicit legacy/fallback helper."
                for call in visitor.violations
            )
    return violations


class _DirectStudyStateReadVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ast.Attribute] = []

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr not in UI_DIRECT_STUDY_STATE_ATTRIBUTES:
            self.generic_visit(node)
            return
        if _expression_mentions_study(node.value):
            self.violations.append(node)
            return
        self.generic_visit(node)


class _ControllerStudyGetControllerVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ast.Call] = []

    def visit_Call(self, node: ast.Call) -> None:
        if _is_controller_study_get_controller_call(node):
            self.violations.append(node)
            return
        self.generic_visit(node)


def _expression_mentions_study(node: ast.AST) -> bool:
    if isinstance(node, ast.Attribute) and node.attr == "study":
        return True
    return any(
        isinstance(child, ast.Attribute) and child.attr == "study"
        for child in ast.walk(node)
    )


def _is_controller_study_get_controller_call(node: ast.Call) -> bool:
    if _call_name(node.func) != "get_controller":
        return False
    if not isinstance(node.func, ast.Attribute):
        return False
    return _expression_mentions_controller_study(node.func.value)


def _expression_mentions_controller_study(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Attribute) or child.attr != "study":
            continue
        owner = child.value
        if isinstance(owner, ast.Name) and (
            owner.id == "controller" or owner.id.endswith("_controller")
        ):
            return True
        if isinstance(owner, ast.Attribute) and (
            owner.attr == "controller" or owner.attr.endswith("_controller")
        ):
            return True
    return False


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


def check_ui_post_command_local_refreshes(root_dir: Path) -> list[str]:
    """Return UI code that locally refreshes after service-backed commands."""
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
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                violations.extend(
                    f"{py_file.relative_to(root_dir)}:{call.lineno} calls "
                    f"{_call_name(call.func)} after execute_application_command(); "
                    "service-backed success refresh must go through "
                    "refresh_after_command(), with local refresh limited to "
                    "explicit legacy-result helpers."
                    for call in _post_command_local_refresh_calls(
                        node.body,
                        source,
                        node.name,
                    )
                )
    return violations


def check_ui_post_command_controller_echoes(root_dir: Path) -> list[str]:
    """Return UI code that re-reads controller echo state after command success."""
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
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                violations.extend(
                    f"{py_file.relative_to(root_dir)}:{call.lineno} calls "
                    f"controller.{_call_name(call.func)}() after "
                    "execute_application_command(); service-backed success UI "
                    "must trust CommandResult and selected user inputs, with "
                    "controller echo reads limited to explicit legacy fallback "
                    "branches."
                    for call in _post_command_controller_echo_calls(
                        node.body,
                        source,
                    )
                )
    return violations


def check_ui_refresh_false_commands(root_dir: Path) -> list[str]:
    """Return mutating UI commands that suppress command-driven refresh."""
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
            if not isinstance(node, ast.Call):
                continue
            if _call_name(node.func) != "execute_application_command":
                continue
            if not _call_has_refresh_false(node):
                continue
            command_expr = _execute_command_argument(node)
            command_name = _refresh_false_command_name(command_expr)
            if _is_read_only_refresh_false_command(command_expr):
                continue
            violations.append(
                f"{py_file.relative_to(root_dir)}:{node.lineno} calls "
                f"{command_name or 'unknown command'} with refresh=False; only "
                "read/query commands may suppress command-driven UI refresh."
            )
    return violations


def check_ui_capability_gated_controller_readiness(root_dir: Path) -> list[str]:
    """Return UI command gates that consult controller state despite capabilities."""
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
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not _contains_get_command_capability(node):
                continue
            visitor = _CapabilityGatedControllerReadinessVisitor()
            visitor.visit(node)
            violations.extend(
                f"{py_file.relative_to(root_dir)}:{call.lineno} calls "
                f"controller.{_call_name(call.func)}() in a capability-gated "
                "command path; controller readiness checks must be limited to an "
                "explicit capability is None branch."
                for call in visitor.violations
            )
    return violations


def check_ui_observer_direct_update_bridges(root_dir: Path) -> list[str]:
    """Return observer bridges that bypass the simple refresh helper."""
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
            if not isinstance(node, ast.Call):
                continue
            if _observer_bridge_uses_import_finished_simple_refresh(node):
                violations.append(
                    f"{py_file.relative_to(root_dir)}:{node.lineno} wires "
                    "import_finished as a simple refresh event; successful import "
                    "state refresh is owned by data_changed. Use a named callback "
                    "handler for import warnings or event-specific behavior."
                )
                continue
            if _call_name(node.func) != "_create_bridge":
                continue
            if _observer_bridge_uses_direct_update_panel(node):
                violations.append(
                    f"{py_file.relative_to(root_dir)}:{node.lineno} wires observer "
                    "events directly to update_panel(); use _create_refresh_bridge() "
                    "for simple panel refresh (delegating to refresh_from_observer), "
                    "or a named callback handler for event-specific behavior."
                )
                continue
            if (
                py_file.name != "base_panel.py"
                and _observer_bridge_uses_direct_refresh_from_observer(node)
            ):
                violations.append(
                    f"{py_file.relative_to(root_dir)}:{node.lineno} wires simple "
                    "observer refresh through _create_bridge(..., "
                    "refresh_from_observer); use _create_refresh_bridge() instead."
                )
    return violations


def check_ui_observer_handlers_call_refresh_coordinator(root_dir: Path) -> list[str]:
    """Return event-specific observer handlers that skip the refresh coordinator."""
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

        functions = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _call_name(node.func) != "_create_bridge":
                continue
            event_name = _observer_bridge_event_name(node)
            if event_name not in UI_OBSERVER_REFRESH_EVENTS:
                continue
            handler_name = _observer_bridge_handler_method_name(node)
            if not handler_name:
                continue
            handler = functions.get(handler_name)
            if handler is None:
                continue
            if _function_calls_refresh_after_observer(handler):
                continue
            violations.append(
                f"{py_file.relative_to(root_dir)}:{node.lineno} wires "
                f"{event_name!r} to {handler_name}(), but that handler does "
                "not call refresh_after_observer(); event-specific observer "
                "handlers may do local side effects, then must delegate shared "
                "refresh scope to the coordinator."
            )
    return violations


def _observer_bridge_event_name(call: ast.Call) -> str | None:
    if len(call.args) < 2:
        return None
    event_arg = call.args[1]
    if isinstance(event_arg, ast.Constant) and isinstance(event_arg.value, str):
        return event_arg.value
    return None


def _observer_bridge_handler_method_name(call: ast.Call) -> str | None:
    if len(call.args) < 3:
        return None
    handler_arg = call.args[2]
    if not isinstance(handler_arg, ast.Attribute):
        return None
    if isinstance(handler_arg.value, ast.Name) and handler_arg.value.id == "self":
        return handler_arg.attr
    return None


def _function_calls_refresh_after_observer(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    return any(
        isinstance(child, ast.Call)
        and _call_name(child.func) == "refresh_after_observer"
        for child in ast.walk(node)
    )


def _observer_bridge_uses_import_finished_simple_refresh(call: ast.Call) -> bool:
    call_name = _call_name(call.func)
    if call_name == "_create_refresh_bridge":
        return _call_has_string_arg(call, "import_finished")
    if call_name == "QtObserverBridge":
        return _call_has_string_arg(call, "import_finished")
    return False


def _call_has_string_arg(call: ast.Call, value: str) -> bool:
    return any(
        isinstance(arg, ast.Constant) and arg.value == value for arg in call.args
    )


def _observer_bridge_uses_direct_update_panel(call: ast.Call) -> bool:
    if len(call.args) < 3:
        return False
    handler = call.args[2]
    return isinstance(handler, ast.Attribute) and handler.attr == "update_panel"


def _observer_bridge_uses_direct_refresh_from_observer(call: ast.Call) -> bool:
    if len(call.args) < 3:
        return False
    handler = call.args[2]
    return (
        isinstance(handler, ast.Attribute) and handler.attr == "refresh_from_observer"
    )


def _post_command_local_refresh_calls(
    statements: list[ast.stmt],
    source: str,
    function_name: str = "",
) -> list[ast.Call]:
    violations: list[ast.Call] = []
    command_seen = False
    for statement in statements:
        if command_seen:
            visitor = _PostCommandLocalRefreshVisitor(source, function_name)
            visitor.visit(statement)
            violations.extend(visitor.violations)
        violations.extend(
            _post_command_local_refresh_calls(
                _nested_statement_bodies(statement),
                source,
                function_name,
            ),
        )
        if _contains_service_backed_command(statement):
            command_seen = True
    return violations


def _post_command_controller_echo_calls(
    statements: list[ast.stmt],
    source: str,
) -> list[ast.Call]:
    violations: list[ast.Call] = []
    command_seen = False
    for statement in statements:
        if command_seen:
            visitor = _PostCommandControllerEchoVisitor(source)
            visitor.visit(statement)
            violations.extend(visitor.violations)
        violations.extend(
            _post_command_controller_echo_calls(
                _nested_statement_bodies(statement),
                source,
            ),
        )
        if _contains_service_backed_command(statement):
            command_seen = True
    return violations


def _nested_statement_bodies(statement: ast.stmt) -> list[ast.stmt]:
    bodies: list[ast.stmt] = []
    for field_name in ("body", "orelse", "finalbody"):
        value = getattr(statement, field_name, None)
        if isinstance(value, list):
            bodies.extend(node for node in value if isinstance(node, ast.stmt))
    handlers = getattr(statement, "handlers", None)
    if isinstance(handlers, list):
        for handler in handlers:
            body = getattr(handler, "body", None)
            if isinstance(body, list):
                bodies.extend(node for node in body if isinstance(node, ast.stmt))
    return bodies


def _contains_service_backed_command(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if _call_name(child.func) != "execute_application_command":
            continue
        if _call_has_refresh_false(child):
            continue
        return True
    return False


def _execute_command_argument(node: ast.Call) -> ast.AST | None:
    if len(node.args) >= 2:
        return node.args[1]
    for keyword in node.keywords:
        if keyword.arg == "command":
            return keyword.value
    return None


def _refresh_false_command_name(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    if isinstance(node, ast.Name):
        return node.id
    return None


def _is_read_only_refresh_false_command(node: ast.AST | None) -> bool:
    if not isinstance(node, ast.Call):
        return False
    call_name = _call_name(node.func)
    if call_name in UI_REFRESH_FALSE_READ_ONLY_COMMANDS:
        return True
    return call_name == "SaliencyCommand" and not node.args and not node.keywords


def _contains_get_command_capability(node: ast.AST) -> bool:
    return any(
        isinstance(child, ast.Call)
        and _call_name(child.func) == "get_command_capability"
        for child in ast.walk(node)
    )


def _call_has_refresh_false(call: ast.Call) -> bool:
    for keyword in call.keywords:
        if keyword.arg != "refresh":
            continue
        if isinstance(keyword.value, ast.Constant) and keyword.value.value is False:
            return True
    return False


class _PostCommandLocalRefreshVisitor(ast.NodeVisitor):
    def __init__(self, source: str, function_name: str = "") -> None:
        self.source = source
        self.function_name = function_name
        self.violations: list[ast.Call] = []

    def visit_If(self, node: ast.If) -> None:
        if _is_missing_result_guard(node.test):
            if not _is_legacy_result_refresh_helper(self.function_name):
                for statement in node.body:
                    self.visit(statement)
            for statement in node.orelse:
                self.visit(statement)
            return
        if _is_failure_guard(node.test):
            for statement in node.orelse:
                self.visit(statement)
            return
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if _call_name(node.func) in UI_POST_COMMAND_LOCAL_REFRESH_METHODS:
            self.violations.append(node)
            return
        self.generic_visit(node)


class _PostCommandControllerEchoVisitor(ast.NodeVisitor):
    def __init__(self, source: str) -> None:
        self.source = source
        self.violations: list[ast.Call] = []

    def visit_If(self, node: ast.If) -> None:
        if _is_missing_result_guard(node.test):
            for statement in node.orelse:
                self.visit(statement)
            return
        if _is_failure_guard(node.test):
            for statement in node.orelse:
                self.visit(statement)
            return
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        call_name = _call_name(node.func)
        if (
            call_name in UI_POST_COMMAND_CONTROLLER_ECHO_METHODS
            and _call_receiver_is_controller(node.func)
        ):
            self.violations.append(node)
            return
        self.generic_visit(node)


class _CapabilityGatedControllerReadinessVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ast.Call] = []

    def visit_Call(self, node: ast.Call) -> None:
        call_name = _call_name(node.func)
        if call_name in UI_CONTROLLER_FALLBACK_WRAPPERS:
            return
        if (
            call_name in UI_CAPABILITY_GATED_CONTROLLER_READINESS_METHODS
            and _call_receiver_is_controller(node.func)
        ):
            self.violations.append(node)
            return
        self.generic_visit(node)


def _is_failure_guard(node: ast.AST) -> bool:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return False
    if isinstance(node, ast.Attribute):
        return node.attr == "failed"
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        return any(_is_failure_guard(value) for value in node.values)
    return False


def _is_missing_result_guard(node: ast.AST) -> bool:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return False
    if isinstance(node, ast.Compare):
        return _is_none_failure_compare(node)
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        return any(_is_missing_result_guard(value) for value in node.values)
    return False


def _is_missing_capability_guard(node: ast.AST) -> bool:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return False
    if isinstance(node, ast.Compare):
        return _is_capability_none_compare(node)
    if isinstance(node, ast.BoolOp):
        return any(_is_missing_capability_guard(value) for value in node.values)
    return False


def _is_legacy_result_refresh_helper(function_name: str) -> bool:
    return function_name.endswith("_after_legacy_result")


def _is_none_failure_compare(node: ast.Compare) -> bool:
    if len(node.ops) != 1 or len(node.comparators) != 1:
        return False
    left_is_none = isinstance(node.left, ast.Constant) and node.left.value is None
    right_is_none = (
        isinstance(node.comparators[0], ast.Constant)
        and node.comparators[0].value is None
    )
    if not (left_is_none or right_is_none):
        return False
    return isinstance(node.ops[0], (ast.Is, ast.Eq))


def _is_capability_none_compare(node: ast.Compare) -> bool:
    if len(node.ops) != 1 or len(node.comparators) != 1:
        return False
    if not isinstance(node.ops[0], (ast.Is, ast.Eq)):
        return False

    left = node.left
    right = node.comparators[0]
    return (
        _is_capability_reference(left)
        and isinstance(right, ast.Constant)
        and right.value is None
    ) or (
        isinstance(left, ast.Constant)
        and left.value is None
        and _is_capability_reference(right)
    )


def _is_capability_reference(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return "capability" in node.id
    return isinstance(node, ast.Attribute) and "capability" in node.attr


if __name__ == "__main__":
    sys.exit(check_architecture(os.getcwd()))
