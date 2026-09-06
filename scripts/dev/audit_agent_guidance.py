"""Run static checks for XBrainLab's repo-local agent guidance."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

RETIRED_SKILLS = (
    "clean-code-reviewer",
    "mcp-adapter-reviewer",
    "pr-branch-governance",
    "software-design-reviewer",
)
RETIRED_EVAL_FILES = (
    "skill-routing-cases.yaml",
    "authority-cases.yaml",
)
FORBIDDEN_GUIDANCE_TOKENS = (
    "docs/agent_goals/product_quality_closure_goal.md",
    "stabilize/product-quality-closure",
    "Handoff Command Manifest",
    "human-like-walkthrough-runs/current",
)
UNBOUNDED_DELIVERY_TOKENS = (
    "Milestone 是最低門檻",
    "milestone 是最低門檻",
)
REQUIRED_ROOT_TOKENS = (
    "scope ceiling",
    "Plan-first",
    "XBrainLab/ui/",
    "實作前必須先取得使用者明確確認",
    "唯讀診斷",
    "300",
    "800",
    "1,500",
)
AGENTS_MAX_BYTES = 7_500
OPERATIONS_MAX_BYTES = 4_000
MAX_SKILL_LINES = 45
MAX_TOTAL_SKILL_LINES = 500
MAX_WORKFLOW_LINES = 70
MAX_TOTAL_WORKFLOW_LINES = 200
MAX_DESCRIPTION_CHARS = 220
MAX_TOTAL_DESCRIPTION_CHARS = 2_920
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")


def _repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[2]


def _frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: missing YAML frontmatter")
    try:
        raw, body = text[4:].split("\n---\n", 1)
    except ValueError as exc:
        raise ValueError(f"{path}: unterminated YAML frontmatter") from exc
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: frontmatter must be a mapping")
    return data, body


def _audit_size(path: Path, *, label: str, maximum: int) -> list[str]:
    if not path.is_file():
        return [f"missing {label}"]
    size = path.stat().st_size
    if size > maximum:
        return [f"{label} is {size} bytes; maximum is {maximum}"]
    return []


def _audit_skills(root: Path) -> list[str]:
    errors: list[str] = []
    skill_root = root / ".agents" / "skills"
    if not skill_root.is_dir():
        return ["missing .agents/skills"]

    actual_skills = {
        path.parent.name for path in skill_root.glob("*/SKILL.md") if path.is_file()
    }
    for retired in RETIRED_SKILLS:
        if retired in actual_skills:
            errors.append(f"retired skill still active: {retired}")

    total_lines = 0
    total_description_chars = 0
    for name in sorted(actual_skills):
        path = skill_root / name / "SKILL.md"
        try:
            metadata, _body = _frontmatter(path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        unexpected = set(metadata) - {
            "name",
            "description",
            "license",
            "allowed-tools",
            "metadata",
        }
        if unexpected:
            errors.append(f"{path}: unsupported frontmatter keys: {sorted(unexpected)}")
        if metadata.get("name") != name:
            errors.append(f"{path}: name must match its directory")
        description = metadata.get("description")
        if not isinstance(description, str) or not description.strip():
            errors.append(f"{path}: description must be a non-empty string")
            continue
        if "metadata" in metadata and not isinstance(metadata["metadata"], dict):
            errors.append(f"{path}: metadata must be a mapping")
        if len(description) > MAX_DESCRIPTION_CHARS:
            errors.append(
                f"{path}: description is {len(description)} chars; "
                f"maximum is {MAX_DESCRIPTION_CHARS}"
            )
        total_description_chars += len(description)
        lines = len(path.read_text(encoding="utf-8").splitlines())
        total_lines += lines
        if lines > MAX_SKILL_LINES:
            errors.append(f"{path}: {lines} lines; maximum is {MAX_SKILL_LINES}")

    if total_lines > MAX_TOTAL_SKILL_LINES:
        errors.append(
            f"skill bodies total {total_lines} lines; maximum is {MAX_TOTAL_SKILL_LINES}"
        )
    if total_description_chars > MAX_TOTAL_DESCRIPTION_CHARS:
        errors.append(
            "skill descriptions total "
            f"{total_description_chars} chars; maximum is {MAX_TOTAL_DESCRIPTION_CHARS}"
        )
    return errors


def _audit_workflows(root: Path) -> list[str]:
    errors: list[str] = []
    workflow_root = root / ".agents" / "workflows"
    if not workflow_root.is_dir():
        return ["missing .agents/workflows"]

    total_lines = 0
    for path in sorted(workflow_root.glob("*.md")):
        lines = len(path.read_text(encoding="utf-8").splitlines())
        total_lines += lines
        if lines > MAX_WORKFLOW_LINES:
            errors.append(f"{path}: {lines} lines; maximum is {MAX_WORKFLOW_LINES}")
    if total_lines > MAX_TOTAL_WORKFLOW_LINES:
        errors.append(
            "workflow bodies total "
            f"{total_lines} lines; maximum is {MAX_TOTAL_WORKFLOW_LINES}"
        )
    return errors


def _audit_references(root: Path, guidance_files: Sequence[Path]) -> list[str]:
    errors: list[str] = []
    operations = root / ".agents" / "README.md"
    for path in guidance_files:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_GUIDANCE_TOKENS:
            if token in text:
                errors.append(f"{path.relative_to(root)} contains stale token: {token}")
        for token in INLINE_CODE_RE.findall(text):
            if any(marker in token for marker in ("*", "{", "}", "$", " ")):
                continue
            cleaned = token.rstrip("/").rstrip(".,:;")
            if token.startswith(("docs/", ".agents/", "scripts/", "tests/")):
                referenced = root / cleaned
            elif path == operations and token.startswith("workflows/"):
                referenced = path.parent / cleaned
            elif token in {"AGENTS.md", "mkdocs.yml", "settings.json"}:
                referenced = root / cleaned
            else:
                continue
            if not referenced.exists():
                errors.append(
                    f"{path.relative_to(root)} references missing path: {token}"
                )
    return errors


def _audit_model_dispatch_config(root: Path) -> list[str]:
    path = root / ".codex" / "config.toml"
    if not path.is_file():
        return ["missing .codex/config.toml model-dispatch defaults"]
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        return [f".codex/config.toml contains invalid TOML: {exc}"]

    errors: list[str] = []
    expected_root = {
        "model": "gpt-6-astra",
        "model_reasoning_effort": "medium",
    }
    for key, expected in expected_root.items():
        if config.get(key) != expected:
            errors.append(f".codex/config.toml must set {key}={expected!r}")
    if "service_tier" in config:
        errors.append(
            ".codex/config.toml must not persist service_tier; Fast is foreground-only"
        )

    agents = config.get("agents")
    if not isinstance(agents, dict):
        return [*errors, ".codex/config.toml must define an [agents] table"]
    expected_agents = {
        "max_concurrent_threads_per_session": 2,
        "default_subagent_model": "gpt-6-astra",
        "default_subagent_reasoning_effort": "medium",
    }
    for key, expected in expected_agents.items():
        if agents.get(key) != expected:
            errors.append(f".codex/config.toml [agents] must set {key}={expected!r}")
    return errors


def audit_guidance(root: Path) -> list[str]:
    """Return static contract violations for the guidance tree."""
    errors: list[str] = []
    root = root.resolve()
    agents_path = root / "AGENTS.md"
    operations_path = root / ".agents" / "README.md"
    errors.extend(_audit_size(agents_path, label="AGENTS.md", maximum=AGENTS_MAX_BYTES))
    errors.extend(
        _audit_size(
            operations_path,
            label=".agents/README.md",
            maximum=OPERATIONS_MAX_BYTES,
        )
    )
    errors.extend(_audit_skills(root))
    errors.extend(_audit_workflows(root))
    errors.extend(_audit_model_dispatch_config(root))

    if agents_path.is_file():
        agents_text = agents_path.read_text(encoding="utf-8")
        for token in UNBOUNDED_DELIVERY_TOKENS:
            if token in agents_text:
                errors.append(f"AGENTS.md contains unbounded delivery token: {token}")
        for token in REQUIRED_ROOT_TOKENS:
            if token not in agents_text:
                errors.append(f"AGENTS.md is missing required restraint token: {token}")
    retired_files = (
        root / ".agents" / "stack.md",
        root / ".agents" / "skills" / "README.md",
        root / ".agents" / "workflows" / "README.md",
        root / "docs" / "agent_goals" / "product_quality_closure_goal.md",
    )
    errors.extend(
        f"retired guidance file still exists: {path.relative_to(root)}"
        for path in retired_files
        if path.exists()
    )
    runbook_root = root / ".agents" / "runbooks"
    if runbook_root.is_dir():
        runbooks = sorted(path.name for path in runbook_root.glob("*.md"))
        if runbooks:
            errors.append(f"retired runbooks remain: {runbooks}")

    eval_root = root / ".agents" / "evals"
    for filename in RETIRED_EVAL_FILES:
        if (eval_root / filename).exists():
            errors.append(f"retired external eval remains: {filename}")

    guidance_files = [agents_path]
    guidance_files.extend(sorted((root / ".agents").rglob("*.md")))
    errors.extend(_audit_references(root, guidance_files))
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")
    check = subparsers.add_parser("check", help="run static guidance checks")
    check.add_argument("--root", type=Path, default=_repo_root_from_script())
    check.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command in {None, "check"}:
        root = getattr(args, "root", _repo_root_from_script())
        output_format = getattr(args, "format", "text")
        errors = audit_guidance(root)
        if output_format == "json":
            print(json.dumps({"ok": not errors, "errors": errors}, indent=2))
        elif errors:
            print("\n".join(f"ERROR: {error}" for error in errors))
        else:
            print("Agent guidance audit: PASS")
        return 1 if errors else 0
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
