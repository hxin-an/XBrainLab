from __future__ import annotations

import ast
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEV_SCRIPTS = ROOT / "scripts" / "dev"
CAPTURE_SOURCES = (
    *sorted(DEV_SCRIPTS.glob("capture_*.py")),
    *sorted(DEV_SCRIPTS.glob("chatpanel_*/*.py")),
    *sorted((ROOT / "scripts" / "agent" / "evals").glob("*.py")),
    DEV_SCRIPTS / "probe_pyvistaqt_runtime.py",
    DEV_SCRIPTS / "report_data_interpretation_format_matrix.py",
    DEV_SCRIPTS / "report_teacher_dataset_preflight.py",
    DEV_SCRIPTS / "run_chatpanel_ui_dpi_gate.py",
    DEV_SCRIPTS / "run_teacher_handoff_gate.py",
    DEV_SCRIPTS / "update_quality_dashboard.py",
    DEV_SCRIPTS / "write_mcp_client_config.py",
)
TRACKED_DEFAULT_ALLOWLIST: set[tuple[str, str]] = set()
OUTPUT_OPTIONS = {"--artifact-dir", "--artifacts-dir", "--eval-dir", "--output-dir"}
FORBIDDEN_SEGMENTS = {"artifacts", "handoff-evidence"}
TRACKED_ARTIFACT_ALLOWLIST = {
    "artifacts/README.md",
    "artifacts/quality/.gitignore",
    "artifacts/ui/.gitignore",
}


def _assignment_name(node: ast.Assign | ast.AnnAssign) -> str | None:
    if isinstance(node, ast.AnnAssign):
        return node.target.id if isinstance(node.target, ast.Name) else None
    if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
        return None
    return node.targets[0].id


def _assignment_value(node: ast.Assign | ast.AnnAssign) -> ast.expr | None:
    return node.value


def _is_output_default_name(name: str) -> bool:
    if name.startswith("HISTORICAL_"):
        return False
    return (
        name in {"ARTIFACTS_DIR", "OUTPUT_DIR"}
        or name.endswith(("_ARTIFACT_DIR", "_ARTIFACTS_DIR", "_OUTPUT_DIR"))
        or (
            name.startswith("DEFAULT_")
            and any(token in name for token in ("ARTIFACT", "OUTPUT"))
        )
    )


def _forbidden_segments(node: ast.AST) -> set[str]:
    segments: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Constant) or not isinstance(child.value, str):
            continue
        path_segments = child.value.replace("\\", "/").split("/")
        segments.update(FORBIDDEN_SEGMENTS.intersection(path_segments))
    return segments


def _output_option(call: ast.Call) -> str | None:
    if not isinstance(call.func, ast.Attribute) or call.func.attr != "add_argument":
        return None
    options = {
        arg.value
        for arg in call.args
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
    }
    return next(iter(OUTPUT_OPTIONS.intersection(options)), None)


def _violations(source_path: Path) -> list[str]:
    relative_path = source_path.relative_to(ROOT).as_posix()
    tree = ast.parse(
        source_path.read_text(encoding="utf-8"),
        filename=str(source_path),
    )
    violations: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            name = _assignment_name(node)
            value = _assignment_value(node)
            if name is None or value is None or not _is_output_default_name(name):
                continue
            if (relative_path, name) in TRACKED_DEFAULT_ALLOWLIST:
                continue
            segments = _forbidden_segments(value)
            if segments:
                violations.append(
                    f"{relative_path}:{node.lineno}:{name} uses {sorted(segments)}"
                )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_default_") and node.name.endswith("_dir"):
                segments = _forbidden_segments(node)
                if segments:
                    violations.append(
                        f"{relative_path}:{node.lineno}:{node.name} uses "
                        f"{sorted(segments)}"
                    )

    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        option = _output_option(call)
        if option is None:
            continue
        default = next(
            (keyword.value for keyword in call.keywords if keyword.arg == "default"),
            None,
        )
        if default is None:
            continue
        segments = _forbidden_segments(default)
        if segments:
            violations.append(
                f"{relative_path}:{call.lineno}:{option} uses {sorted(segments)}"
            )
    return violations


def test_active_capture_defaults_avoid_tracked_and_final_handoff_namespaces() -> None:
    violations = [
        violation
        for source_path in CAPTURE_SOURCES
        for violation in _violations(source_path)
    ]

    assert violations == [], "\n".join(violations)


def test_tracked_artifact_namespace_contains_policy_files_only() -> None:
    git_executable = shutil.which("git")
    assert git_executable is not None
    completed = subprocess.run(  # noqa: S603 - resolved Git binary with fixed argv.
        [git_executable, "ls-files", "artifacts"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    tracked = {line for line in completed.stdout.splitlines() if line}

    assert tracked == TRACKED_ARTIFACT_ALLOWLIST
