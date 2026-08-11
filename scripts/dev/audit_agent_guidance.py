"""Audit and evaluate XBrainLab's repo-local agent guidance."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import shutil
import statistics
import subprocess
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

EXPECTED_SKILLS = (
    "agent-toolcall-designer",
    "architecture-reviewer",
    "code-reviewer",
    "data-interpretation-reviewer",
    "docs-curator",
    "docs-site-product-designer",
    "mcp-adapter-reviewer",
    "performance-resource-reviewer",
    "refactor-slicer",
    "release-packaging-reviewer",
    "security-privacy-reviewer",
    "tdd-guard",
    "test-quality-reviewer",
    "thesis-evidence-reviewer",
    "ui-product-reviewer",
    "validation-runner",
)
RETIRED_SKILLS = (
    "clean-code-reviewer",
    "pr-branch-governance",
    "software-design-reviewer",
)
EXPECTED_WORKFLOWS = (
    "agent-toolcall-scoring.md",
    "architecture-review.md",
    "docs-site-redesign.md",
    "documentation-review.md",
    "handoff-candidate.md",
    "refactor-slice.md",
    "tdd-change.md",
    "test-audit.md",
)
AUTHORITY_CLASSES = (
    "root_invariants",
    "current_truth",
    "target_architecture",
    "validation_registry",
    "skill_trigger",
    "workflow",
    "historical_provenance",
)
CASE_CATEGORY_COUNTS = {
    "positive": 32,
    "negative": 16,
    "overlap": 12,
}
AUTHORITY_CASES_PER_CLASS = 2
FORBIDDEN_GUIDANCE_TOKENS = (
    "docs/agent_goals/product_quality_closure_goal.md",
    "stabilize/product-quality-closure",
    "Handoff Command Manifest",
    "human-like-walkthrough-runs/current",
)
AGENTS_MIN_BYTES = 9_700
AGENTS_MAX_BYTES = 11_200
MAX_SKILL_LINES = 120
MAX_TOTAL_SKILL_LINES = 1_000
MAX_DESCRIPTION_CHARS = 220
MAX_TOTAL_DESCRIPTION_CHARS = 2_920
EVALUATOR_CONTRACT_VERSION = 4
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")


@dataclass(frozen=True)
class RoutingCase:
    """One independent skill-routing evaluation case."""

    id: str
    prompt: str
    category: str
    expected_primary: str | None
    allowed_secondary: tuple[str, ...]
    forbidden_skills: tuple[str, ...]
    expected_authority_class: str


@dataclass(frozen=True)
class AuthorityCase:
    """One independent canonical-authority classification case."""

    id: str
    prompt: str
    expected_authority_class: str


@dataclass(frozen=True)
class EvalRecord:
    """One isolated Codex evaluation execution."""

    variant: str
    run_fingerprint: str
    case_id: str
    repeat: int
    returncode: int
    elapsed_seconds: float
    input_tokens: int | None
    output_tokens: int | None
    response: dict[str, Any] | None
    error: str | None


ROUTING_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "primary_skill",
        "secondary_skills",
        "reason",
    ],
    "properties": {
        "primary_skill": {
            "type": ["string", "null"],
            "enum": [None, *EXPECTED_SKILLS, *RETIRED_SKILLS],
            "description": (
                "Exact repo-local primary skill, or null. When the user explicitly "
                "names a skill in this enum, return that exact skill; explicit-only "
                "controls invocation, not schema availability."
            ),
        },
        "secondary_skills": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [*EXPECTED_SKILLS, *RETIRED_SKILLS],
            },
        },
        "reason": {"type": "string", "maxLength": 240},
    },
}

AUTHORITY_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["authority_class", "reason"],
    "properties": {
        "authority_class": {
            "type": "string",
            "enum": list(AUTHORITY_CLASSES),
            "description": "The one canonical repo layer that owns the requested truth.",
        },
        "reason": {"type": "string", "maxLength": 240},
    },
}


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


def load_cases(path: Path) -> tuple[RoutingCase, ...]:
    """Load and validate the routing corpus."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError(f"{path}: expected a top-level cases list")

    cases: list[RoutingCase] = []
    required = {
        "id",
        "prompt",
        "category",
        "expected_primary",
        "allowed_secondary",
        "forbidden_skills",
        "expected_authority_class",
    }
    for index, item in enumerate(payload["cases"]):
        if not isinstance(item, dict) or set(item) != required:
            raise ValueError(
                f"{path}: case {index} must contain exactly {sorted(required)}"
            )
        case = RoutingCase(
            id=str(item["id"]),
            prompt=str(item["prompt"]),
            category=str(item["category"]),
            expected_primary=item["expected_primary"],
            allowed_secondary=tuple(item["allowed_secondary"]),
            forbidden_skills=tuple(item["forbidden_skills"]),
            expected_authority_class=str(item["expected_authority_class"]),
        )
        if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", case.id) is None:
            raise ValueError(f"{path}: case {index} has an unsafe id: {case.id}")
        cases.append(case)

    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: case ids must be unique")
    counts = Counter(case.category for case in cases)
    if dict(counts) != CASE_CATEGORY_COUNTS:
        raise ValueError(
            f"{path}: expected category counts {CASE_CATEGORY_COUNTS}, got {dict(counts)}"
        )
    valid_skills = set(EXPECTED_SKILLS)
    for case in cases:
        referenced = {
            *case.allowed_secondary,
            *case.forbidden_skills,
        }
        if case.expected_primary is not None:
            referenced.add(case.expected_primary)
        unknown = referenced - valid_skills
        if unknown:
            raise ValueError(
                f"{path}: {case.id} references unknown skills {sorted(unknown)}"
            )
        if case.expected_primary in case.forbidden_skills:
            raise ValueError(f"{path}: {case.id} forbids its expected primary skill")
        if set(case.allowed_secondary) & set(case.forbidden_skills):
            raise ValueError(
                f"{path}: {case.id} allows and forbids the same secondary skill"
            )
        if case.expected_authority_class not in AUTHORITY_CLASSES:
            raise ValueError(f"{path}: {case.id} has an unknown authority class")
    return tuple(cases)


def load_authority_cases(path: Path) -> tuple[AuthorityCase, ...]:
    """Load a balanced, single-purpose authority-classification corpus."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError(f"{path}: expected a top-level cases list")

    cases: list[AuthorityCase] = []
    required = {"id", "prompt", "expected_authority_class"}
    for index, item in enumerate(payload["cases"]):
        if not isinstance(item, dict) or set(item) != required:
            raise ValueError(
                f"{path}: case {index} must contain exactly {sorted(required)}"
            )
        case = AuthorityCase(
            id=str(item["id"]),
            prompt=str(item["prompt"]),
            expected_authority_class=str(item["expected_authority_class"]),
        )
        if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", case.id) is None:
            raise ValueError(f"{path}: case {index} has an unsafe id: {case.id}")
        if case.expected_authority_class not in AUTHORITY_CLASSES:
            raise ValueError(f"{path}: {case.id} has an unknown authority class")
        cases.append(case)

    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: case ids must be unique")
    counts = Counter(case.expected_authority_class for case in cases)
    expected_counts = dict.fromkeys(AUTHORITY_CLASSES, AUTHORITY_CASES_PER_CLASS)
    if dict(counts) != expected_counts:
        raise ValueError(
            f"{path}: expected authority counts {expected_counts}, got {dict(counts)}"
        )
    return tuple(cases)


def audit_guidance(root: Path) -> list[str]:
    """Return contract violations for the guidance tree."""
    errors: list[str] = []
    root = root.resolve()
    agents_path = root / "AGENTS.md"
    if not agents_path.is_file():
        errors.append("missing AGENTS.md")
    else:
        agents_size = agents_path.stat().st_size
        if not AGENTS_MIN_BYTES <= agents_size <= AGENTS_MAX_BYTES:
            errors.append(
                f"AGENTS.md is {agents_size} bytes; expected "
                f"{AGENTS_MIN_BYTES}-{AGENTS_MAX_BYTES}"
            )

    skill_root = root / ".agents" / "skills"
    actual_skills = {
        path.parent.name for path in skill_root.glob("*/SKILL.md") if path.is_file()
    }
    if actual_skills != set(EXPECTED_SKILLS):
        errors.append(
            "skill inventory mismatch: "
            f"expected={sorted(EXPECTED_SKILLS)} actual={sorted(actual_skills)}"
        )
    for retired in RETIRED_SKILLS:
        if (skill_root / retired / "SKILL.md").exists():
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
        if set(metadata) != {"name", "description"}:
            errors.append(f"{path}: frontmatter must contain only name and description")
        if metadata.get("name") != name:
            errors.append(f"{path}: name must match its directory")
        description = metadata.get("description")
        if not isinstance(description, str):
            errors.append(f"{path}: description must be a string")
            continue
        if not description.startswith("Use "):
            errors.append(f"{path}: description must start with 'Use '")
        if name != "mcp-adapter-reviewer" and "Do not " not in description:
            errors.append(f"{path}: description must include a 'Do not' boundary")
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

    workflow_root = root / ".agents" / "workflows"
    actual_workflows = {
        path.name for path in workflow_root.glob("*.md") if path.is_file()
    }
    if actual_workflows != set(EXPECTED_WORKFLOWS):
        errors.append(
            "workflow inventory mismatch: "
            f"expected={sorted(EXPECTED_WORKFLOWS)} actual={sorted(actual_workflows)}"
        )
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
    runbook_files = list((root / ".agents" / "runbooks").glob("*.md"))
    if runbook_files:
        errors.append(
            f"retired runbooks remain: {[path.name for path in runbook_files]}"
        )

    guidance_files = [agents_path]
    guidance_files.extend(sorted((root / ".agents").rglob("*.md")))
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
            if token.startswith(("docs/", ".agents/", "scripts/", "tests/")):
                referenced = root / token.rstrip("/").rstrip(".,:;")
            elif path == root / ".agents" / "README.md" and token.startswith(
                "workflows/"
            ):
                referenced = path.parent / token.rstrip("/").rstrip(".,:;")
            elif token in {"AGENTS.md", "mkdocs.yml", "settings.json"}:
                referenced = root / token
            else:
                continue
            if not referenced.exists():
                errors.append(
                    f"{path.relative_to(root)} references missing path: {token}"
                )

    mcp_yaml = skill_root / "mcp-adapter-reviewer" / "agents" / "openai.yaml"
    if not mcp_yaml.is_file():
        errors.append("mcp-adapter-reviewer is missing agents/openai.yaml")
    else:
        payload = yaml.safe_load(mcp_yaml.read_text(encoding="utf-8"))
        implicit = (
            payload.get("policy", {}).get("allow_implicit_invocation")
            if isinstance(payload, dict)
            else None
        )
        if implicit is not False:
            errors.append("mcp-adapter-reviewer must disable implicit invocation")
        prompt = payload.get("interface", {}).get("default_prompt", "")
        if "$mcp-adapter-reviewer" not in prompt:
            errors.append("MCP default_prompt must mention $mcp-adapter-reviewer")

    cases_path = root / ".agents" / "evals" / "skill-routing-cases.yaml"
    if not cases_path.is_file():
        errors.append("missing .agents/evals/skill-routing-cases.yaml")
    else:
        try:
            load_cases(cases_path)
        except ValueError as exc:
            errors.append(str(exc))
    authority_cases_path = root / ".agents" / "evals" / "authority-cases.yaml"
    if not authority_cases_path.is_file():
        errors.append("missing .agents/evals/authority-cases.yaml")
    else:
        try:
            load_authority_cases(authority_cases_path)
        except ValueError as exc:
            errors.append(str(exc))
    return errors


def _git_sha(repo_root: Path) -> str:
    git_executable = shutil.which("git")
    if git_executable is None:
        raise RuntimeError("git executable not found")
    completed = subprocess.run(  # noqa: S603 - resolved Git executable, fixed argv.
        [git_executable, "rev-parse", "HEAD"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "git rev-parse HEAD failed")
    return completed.stdout.strip()


def _guidance_digest(repo_root: Path) -> str:
    hasher = hashlib.sha256()
    paths = [repo_root / "AGENTS.md"]
    paths.extend(sorted((repo_root / ".agents").rglob("*")))
    for path in paths:
        if not path.is_file():
            continue
        hasher.update(str(path.relative_to(repo_root)).encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def build_codex_command(
    *,
    repo_root: Path,
    model: str,
    reasoning_effort: str,
    schema_path: Path,
    final_path: Path,
    prompt: str,
) -> list[str]:
    """Build the pinned read-only Codex evaluation command."""
    return [
        "codex",
        "exec",
        "--model",
        model,
        "--ignore-user-config",
        "--sandbox",
        "read-only",
        "--ephemeral",
        "--json",
        "-c",
        f'model_reasoning_effort="{reasoning_effort}"',
        "-c",
        'approval_policy="never"',
        "--output-schema",
        str(schema_path),
        "--output-last-message",
        str(final_path),
        "--cd",
        str(repo_root),
        prompt,
    ]


def _routing_prompt(case: RoutingCase) -> str:
    return (
        "Perform a read-only routing decision for the user request below. "
        "Use only repo-local instructions and skill metadata already supplied to you. "
        "Do not inspect .agents/evals, audit scripts, tests, artifacts, or expected answers. "
        "Do not solve the request and do not call tools. Select one primary repo-local skill, "
        "zero or more genuinely necessary secondary skills. If the user explicitly names a "
        "repo-local $skill, select that exact skill when it exists; explicit-only controls when "
        "a skill may be selected, not whether the output schema permits it. Use null when no "
        "repo-local skill is warranted.\n\n"
        f"User request:\n{case.prompt}"
    )


def _authority_prompt(case: AuthorityCase) -> str:
    return (
        "Perform a read-only authority classification for the request below. Use only "
        "repo-local instructions already supplied to you. Do not inspect .agents/evals, audit "
        "scripts, tests, artifacts, or expected answers. Do not solve the request and do not call "
        "tools. Select one canonical authority class for the repository layer that owns the "
        "requested truth, contract, or reusable procedure. Do not select or discuss skills; this "
        "is not a skill-routing task.\n\n"
        f"Authority request:\n{case.prompt}"
    )


def _usage_from_jsonl(text: str) -> tuple[int | None, int | None]:
    input_values: list[int] = []
    output_values: list[int] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if key in {"input_tokens", "total_input_tokens"} and isinstance(
                    nested, int
                ):
                    input_values.append(nested)
                if key in {"output_tokens", "total_output_tokens"} and isinstance(
                    nested, int
                ):
                    output_values.append(nested)
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    for line in text.splitlines():
        try:
            walk(json.loads(line))
        except json.JSONDecodeError:
            continue
    return (
        max(input_values) if input_values else None,
        max(output_values) if output_values else None,
    )


def _error_from_jsonl(text: str) -> str | None:
    """Return the first structured Codex error from an event stream."""
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "error":
            continue
        message = event.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return None


async def _run_case(
    *,
    semaphore: asyncio.Semaphore,
    variant: str,
    run_fingerprint: str,
    case: RoutingCase | AuthorityCase,
    repeat: int,
    repo_root: Path,
    output_dir: Path,
    schema_path: Path,
    model: str,
    reasoning_effort: str,
    timeout_seconds: int,
    prompt_text: str | None = None,
) -> EvalRecord:
    stem = f"{case.id}-r{repeat}"
    jsonl_path = output_dir / f"{stem}.events.jsonl"
    stderr_path = output_dir / f"{stem}.stderr.txt"
    final_path = output_dir / f"{stem}.final.json"
    record_path = output_dir / f"{stem}.record.json"
    if record_path.is_file():
        payload = json.loads(record_path.read_text(encoding="utf-8"))
        if payload.get("run_fingerprint") != run_fingerprint:
            raise RuntimeError(f"{record_path} belongs to a different evaluation run")
        existing = EvalRecord(**payload)
        if existing.error is None and existing.response is not None:
            return existing

    command = build_codex_command(
        repo_root=repo_root,
        model=model,
        reasoning_effort=reasoning_effort,
        schema_path=schema_path,
        final_path=final_path,
        prompt=prompt_text if prompt_text is not None else _routing_prompt(case),
    )
    async with semaphore:
        started = time.monotonic()
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=repo_root,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            process.terminate()
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=10
                )
            except TimeoutError:
                process.kill()
                stdout, stderr = await process.communicate()
            timed_out = True
        else:
            timed_out = False

    elapsed = time.monotonic() - started
    stdout_text = stdout.decode("utf-8", errors="replace")
    stderr_text = stderr.decode("utf-8", errors="replace")
    jsonl_path.write_text(stdout_text, encoding="utf-8")
    stderr_path.write_text(stderr_text, encoding="utf-8")
    input_tokens, output_tokens = _usage_from_jsonl(stdout_text)

    response: dict[str, Any] | None = None
    error: str | None = None
    if timed_out:
        error = f"timed out after {timeout_seconds} seconds"
    elif process.returncode != 0:
        error = (
            _error_from_jsonl(stdout_text)
            or stderr_text.strip()
            or f"Codex exited {process.returncode}"
        )
    elif not final_path.is_file():
        error = "Codex did not write the final response"
    else:
        try:
            parsed = json.loads(final_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            error = f"invalid final JSON: {exc}"
        else:
            if isinstance(parsed, dict):
                secondary = parsed.get("secondary_skills")
                if isinstance(secondary, list) and len(secondary) != len(
                    set(secondary)
                ):
                    error = "response contains duplicate secondary skills"
                else:
                    response = parsed
            else:
                error = "final response is not an object"

    record = EvalRecord(
        variant=variant,
        run_fingerprint=run_fingerprint,
        case_id=case.id,
        repeat=repeat,
        returncode=process.returncode if process.returncode is not None else -1,
        elapsed_seconds=round(elapsed, 6),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        response=response,
        error=error,
    )
    record_path.write_text(
        json.dumps(asdict(record), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return record


async def run_variant(
    *,
    variant: str,
    repo_root: Path,
    cases: Sequence[RoutingCase | AuthorityCase],
    output_dir: Path,
    repeats: int,
    max_concurrency: int,
    model: str,
    reasoning_effort: str,
    timeout_seconds: int,
    suite_name: str = "routing",
    output_schema: dict[str, Any] = ROUTING_OUTPUT_SCHEMA,
    prompt_builder: Callable[[Any], str] = _routing_prompt,
) -> list[EvalRecord]:
    """Run one isolated evaluation-suite variant."""
    output_dir.mkdir(parents=True, exist_ok=True)
    variant_manifest = {
        "variant": variant,
        "suite": suite_name,
        "repo_root": str(repo_root.resolve()),
        "repo_sha": _git_sha(repo_root),
        "guidance_digest": _guidance_digest(repo_root),
        "model": model,
        "reasoning_effort": reasoning_effort,
        "evaluator_contract_version": EVALUATOR_CONTRACT_VERSION,
        "repeats": repeats,
        "case_digest": hashlib.sha256(
            json.dumps(
                [asdict(case) for case in cases],
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
    }
    manifest_path = output_dir / "variant-manifest.json"
    if manifest_path.is_file():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing != variant_manifest:
            raise RuntimeError(
                f"{manifest_path} does not match the requested evaluation run"
            )
    else:
        manifest_path.write_text(
            json.dumps(variant_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    run_fingerprint = hashlib.sha256(
        json.dumps(variant_manifest, sort_keys=True).encode("utf-8")
    ).hexdigest()
    schema_path = output_dir / f"{suite_name}-output-schema.json"
    schema_path.write_text(
        json.dumps(output_schema, indent=2) + "\n",
        encoding="utf-8",
    )
    semaphore = asyncio.Semaphore(max_concurrency)
    pending = [(case, repeat) for case in cases for repeat in range(1, repeats + 1)]
    if not pending:
        return []
    preflight_case, preflight_repeat = pending.pop(0)
    preflight = await _run_case(
        semaphore=semaphore,
        variant=variant,
        run_fingerprint=run_fingerprint,
        case=preflight_case,
        repeat=preflight_repeat,
        repo_root=repo_root,
        output_dir=output_dir,
        schema_path=schema_path,
        model=model,
        reasoning_effort=reasoning_effort,
        timeout_seconds=timeout_seconds,
        prompt_text=prompt_builder(preflight_case),
    )
    if preflight.error is not None:
        raise RuntimeError(f"{variant} preflight failed: {preflight.error}")
    tasks = [
        _run_case(
            semaphore=semaphore,
            variant=variant,
            run_fingerprint=run_fingerprint,
            case=case,
            repeat=repeat,
            repo_root=repo_root,
            output_dir=output_dir,
            schema_path=schema_path,
            model=model,
            reasoning_effort=reasoning_effort,
            timeout_seconds=timeout_seconds,
            prompt_text=prompt_builder(case),
        )
        for case, repeat in pending
    ]
    records = [preflight, *await asyncio.gather(*tasks)]
    invalid = [record for record in records if record.error is not None]
    if invalid:
        details = "; ".join(
            f"{record.case_id}-r{record.repeat}: {record.error}"
            for record in invalid[:3]
        )
        raise RuntimeError(
            f"{variant} produced {len(invalid)} invalid record(s): {details}"
        )
    return records


def score_variant(
    cases: Sequence[RoutingCase],
    records: Sequence[EvalRecord],
) -> dict[str, Any]:
    """Score routing records without model-based grading."""
    by_id = {case.id: case for case in cases}
    scored: list[dict[str, Any]] = []
    for record in records:
        case = by_id[record.case_id]
        response = record.response or {}
        primary = response.get("primary_skill")
        secondary = response.get("secondary_skills")
        secondary_set = set(secondary) if isinstance(secondary, list) else set()
        valid = record.error is None and bool(record.response)
        primary_ok = valid and primary == case.expected_primary
        secondary_ok = valid and secondary_set <= set(case.allowed_secondary)
        forbidden_ok = valid and not (
            {primary, *secondary_set} & set(case.forbidden_skills)
        )
        scored.append(
            {
                "case_id": case.id,
                "category": case.category,
                "valid": valid,
                "primary_ok": primary_ok,
                "secondary_ok": secondary_ok,
                "forbidden_ok": forbidden_ok,
                "selected_count": int(primary is not None) + len(secondary_set),
                "primary_skill": primary,
            }
        )

    def rate(rows: Sequence[dict[str, Any]], key: str) -> float:
        return sum(bool(row[key]) for row in rows) / len(rows) if rows else 0.0

    negative_rows = [
        row for row in scored if by_id[row["case_id"]].expected_primary is None
    ]
    overlap_rows = [row for row in scored if row["category"] == "overlap"]
    mcp_explicit = [
        row
        for row in scored
        if by_id[row["case_id"]].expected_primary == "mcp-adapter-reviewer"
    ]
    mcp_incidental = [
        row
        for row in scored
        if "mcp-adapter-reviewer" in by_id[row["case_id"]].forbidden_skills
    ]
    single_scope = [row for row in scored if row["category"] != "overlap"]
    input_tokens = [
        record.input_tokens for record in records if record.input_tokens is not None
    ]
    elapsed = [record.elapsed_seconds for record in records]
    return {
        "executions": len(records),
        "valid_response_rate": rate(scored, "valid"),
        "primary_accuracy": rate(scored, "primary_ok"),
        "false_positive_rate": (
            sum(row["primary_skill"] is not None for row in negative_rows)
            / len(negative_rows)
            if negative_rows
            else 0.0
        ),
        "overlap_primary_accuracy": rate(overlap_rows, "primary_ok"),
        "secondary_boundary_accuracy": rate(scored, "secondary_ok"),
        "forbidden_skill_accuracy": rate(scored, "forbidden_ok"),
        "mcp_explicit_accuracy": rate(mcp_explicit, "primary_ok"),
        "mcp_incidental_rate": (
            sum(not row["forbidden_ok"] for row in mcp_incidental) / len(mcp_incidental)
            if mcp_incidental
            else 0.0
        ),
        "average_selected_skills_single_scope": (
            statistics.fmean(row["selected_count"] for row in single_scope)
            if single_scope
            else 0.0
        ),
        "median_input_tokens": (
            statistics.median(input_tokens) if input_tokens else None
        ),
        "median_latency_seconds": statistics.median(elapsed) if elapsed else None,
    }


def score_authority_variant(
    cases: Sequence[AuthorityCase],
    records: Sequence[EvalRecord],
) -> dict[str, Any]:
    """Score the independent authority-classification suite."""
    by_id = {case.id: case for case in cases}
    valid = [record for record in records if record.error is None and record.response]
    correct = [
        record
        for record in valid
        if record.response is not None
        and record.response.get("authority_class")
        == by_id[record.case_id].expected_authority_class
    ]
    return {
        "authority_executions": len(records),
        "authority_valid_response_rate": (
            len(valid) / len(records) if records else 0.0
        ),
        "authority_accuracy": len(correct) / len(records) if records else 0.0,
    }


def acceptance_summary(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Apply the pre-registered acceptance thresholds."""
    baseline_tokens = baseline.get("median_input_tokens")
    candidate_tokens = candidate.get("median_input_tokens")
    baseline_latency = baseline.get("median_latency_seconds")
    candidate_latency = candidate.get("median_latency_seconds")
    token_reduction = (
        round(1 - candidate_tokens / baseline_tokens, 12)
        if baseline_tokens and candidate_tokens is not None
        else None
    )
    token_savings = (
        baseline_tokens - candidate_tokens
        if baseline_tokens is not None and candidate_tokens is not None
        else None
    )
    latency_change = (
        round(candidate_latency / baseline_latency - 1, 12)
        if baseline_latency and candidate_latency is not None
        else None
    )
    checks = {
        "primary_accuracy_gte_95pct": candidate["primary_accuracy"] >= 0.95,
        "false_positive_rate_lte_5pct": candidate["false_positive_rate"] <= 0.05,
        "overlap_primary_accuracy_gte_90pct": (
            candidate["overlap_primary_accuracy"] >= 0.90
        ),
        "mcp_explicit_accuracy_100pct": candidate["mcp_explicit_accuracy"] == 1.0,
        "mcp_incidental_rate_0pct": candidate["mcp_incidental_rate"] == 0.0,
        "authority_accuracy_100pct": candidate["authority_accuracy"] == 1.0,
        "average_selected_skills_lte_1_2": (
            candidate["average_selected_skills_single_scope"] <= 1.2
        ),
        "median_input_token_savings_gte_500": (
            token_savings is not None and token_savings >= 500
        ),
        "median_latency_change_lte_10pct": (
            latency_change is not None and latency_change <= 0.10
        ),
    }
    return {
        "checks": checks,
        "automatic_pass": all(checks.values()),
        "token_reduction": token_reduction,
        "median_input_token_savings": token_savings,
        "latency_change": latency_change,
        "human_review_required": {
            "sample_size": 12,
            "automatic_agreement_threshold": 0.90,
            "status": "pending",
        },
    }


def _write_blind_sample(
    *,
    cases: Sequence[RoutingCase],
    baseline_records: Sequence[EvalRecord],
    candidate_records: Sequence[EvalRecord],
    authority_cases: Sequence[AuthorityCase],
    baseline_authority_records: Sequence[EvalRecord],
    candidate_authority_records: Sequence[EvalRecord],
    output_root: Path,
) -> None:
    routing_baseline = {
        (record.case_id, record.repeat): record for record in baseline_records
    }
    routing_candidate = {
        (record.case_id, record.repeat): record for record in candidate_records
    }
    authority_baseline = {
        (record.case_id, record.repeat): record for record in baseline_authority_records
    }
    authority_candidate = {
        (record.case_id, record.repeat): record
        for record in candidate_authority_records
    }
    ranked_routing = sorted(
        cases,
        key=lambda case: hashlib.sha256(case.id.encode()).hexdigest(),
    )[:8]
    ranked_authority = sorted(
        authority_cases,
        key=lambda case: hashlib.sha256(case.id.encode()).hexdigest(),
    )[:4]
    sample: list[dict[str, Any]] = []
    key: list[dict[str, Any]] = []
    selected: list[
        tuple[
            str,
            RoutingCase | AuthorityCase,
            dict[tuple[str, int], EvalRecord],
            dict[tuple[str, int], EvalRecord],
        ]
    ] = [
        ("routing", case, routing_baseline, routing_candidate)
        for case in ranked_routing
    ]
    selected.extend(
        ("authority", case, authority_baseline, authority_candidate)
        for case in ranked_authority
    )
    for case_type, case, baseline, candidate in selected:
        pair_key = (case.id, 1)
        left_is_candidate = (
            int(hashlib.sha256(case.prompt.encode()).hexdigest(), 16) % 2
        )
        left_variant = "candidate" if left_is_candidate else "baseline"
        right_variant = "baseline" if left_is_candidate else "candidate"
        records_by_variant = {
            "baseline": baseline[pair_key],
            "candidate": candidate[pair_key],
        }
        records_by_label = {
            "A": records_by_variant[left_variant],
            "B": records_by_variant[right_variant],
        }
        sample.append(
            {
                "case_id": case.id,
                "case_type": case_type,
                "prompt": case.prompt,
                "A": records_by_label["A"].response,
                "B": records_by_label["B"].response,
                "A_pass": None,
                "B_pass": None,
                "reviewer_notes": "",
            }
        )
        key.append(
            {
                "case_id": case.id,
                "case_type": case_type,
                "A": left_variant,
                "B": right_variant,
                "A_auto_pass": _blind_record_pass(case, records_by_label["A"]),
                "B_auto_pass": _blind_record_pass(case, records_by_label["B"]),
            }
        )
    (output_root / "human-review-sample.yaml").write_text(
        yaml.safe_dump({"samples": sample}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (output_root / "human-review-key.json").write_text(
        json.dumps({"key": key}, indent=2) + "\n",
        encoding="utf-8",
    )


def _record_pass(case: RoutingCase, record: EvalRecord) -> bool:
    if record.error is not None or record.response is None:
        return False
    primary = record.response.get("primary_skill")
    secondary = record.response.get("secondary_skills")
    if not isinstance(secondary, list):
        return False
    selected = {primary, *secondary}
    return bool(
        primary == case.expected_primary
        and set(secondary) <= set(case.allowed_secondary)
        and not selected & set(case.forbidden_skills)
    )


def _blind_record_pass(
    case: RoutingCase | AuthorityCase,
    record: EvalRecord,
) -> bool:
    if isinstance(case, RoutingCase):
        return _record_pass(case, record)
    return bool(
        record.error is None
        and record.response is not None
        and record.response.get("authority_class") == case.expected_authority_class
    )


def score_human_review(
    *,
    sample_path: Path,
    key_path: Path,
    summary_path: Path,
) -> dict[str, Any]:
    """Score a completed blind review and update the A/B summary."""
    sample_payload = yaml.safe_load(sample_path.read_text(encoding="utf-8"))
    key_payload = json.loads(key_path.read_text(encoding="utf-8"))
    samples = sample_payload.get("samples", [])
    keys = key_payload.get("key", [])
    if len(samples) != 12 or len(keys) != 12:
        raise ValueError("blind review must contain exactly 12 cases")
    key_by_id = {item["case_id"]: item for item in keys}
    matches = 0
    decisions = 0
    for sample in samples:
        key = key_by_id.get(sample.get("case_id"))
        if key is None:
            raise ValueError(f"missing blind key for {sample.get('case_id')}")
        for label in ("A", "B"):
            human = sample.get(f"{label}_pass")
            if not isinstance(human, bool):
                raise ValueError(
                    f"{sample.get('case_id')} requires a boolean {label}_pass"
                )
            matches += int(human == key[f"{label}_auto_pass"])
            decisions += 1
    agreement = matches / decisions
    result = {
        "sample_size": len(samples),
        "decisions": decisions,
        "agreement": agreement,
        "threshold": 0.90,
        "pass": agreement >= 0.90,
    }
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["acceptance"]["human_review_required"] = {
        **result,
        "status": "complete",
    }
    summary["acceptance"]["overall_pass"] = bool(
        summary["acceptance"]["automatic_pass"] and result["pass"]
    )
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def _run_ab(args: argparse.Namespace) -> int:
    baseline_root = args.baseline_root.resolve()
    candidate_root = args.candidate_root.resolve()
    cases = load_cases(args.cases.resolve())
    authority_cases = load_authority_cases(args.authority_cases.resolve())
    base_sha = _git_sha(baseline_root)
    output_root = args.output_root.resolve() / base_sha
    output_root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "baseline_root": str(baseline_root),
        "baseline_sha": base_sha,
        "candidate_root": str(candidate_root),
        "candidate_sha": _git_sha(candidate_root),
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "repeats": args.repeats,
        "max_concurrency": args.max_concurrency,
        "case_count": len(cases),
        "authority_case_count": len(authority_cases),
        "planned_executions": (len(cases) + len(authority_cases)) * args.repeats * 2,
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    baseline_records = asyncio.run(
        run_variant(
            variant="baseline",
            repo_root=baseline_root,
            cases=cases,
            output_dir=output_root / "routing" / "baseline",
            repeats=args.repeats,
            max_concurrency=args.max_concurrency,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            timeout_seconds=args.timeout_seconds,
        )
    )
    candidate_records = asyncio.run(
        run_variant(
            variant="candidate",
            repo_root=candidate_root,
            cases=cases,
            output_dir=output_root / "routing" / "candidate",
            repeats=args.repeats,
            max_concurrency=args.max_concurrency,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            timeout_seconds=args.timeout_seconds,
        )
    )
    baseline_authority_records = asyncio.run(
        run_variant(
            variant="baseline",
            repo_root=baseline_root,
            cases=authority_cases,
            output_dir=output_root / "authority" / "baseline",
            repeats=args.repeats,
            max_concurrency=args.max_concurrency,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            timeout_seconds=args.timeout_seconds,
            suite_name="authority",
            output_schema=AUTHORITY_OUTPUT_SCHEMA,
            prompt_builder=_authority_prompt,
        )
    )
    candidate_authority_records = asyncio.run(
        run_variant(
            variant="candidate",
            repo_root=candidate_root,
            cases=authority_cases,
            output_dir=output_root / "authority" / "candidate",
            repeats=args.repeats,
            max_concurrency=args.max_concurrency,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            timeout_seconds=args.timeout_seconds,
            suite_name="authority",
            output_schema=AUTHORITY_OUTPUT_SCHEMA,
            prompt_builder=_authority_prompt,
        )
    )
    baseline_score = score_variant(cases, baseline_records)
    baseline_score.update(
        score_authority_variant(authority_cases, baseline_authority_records)
    )
    candidate_score = score_variant(cases, candidate_records)
    candidate_score.update(
        score_authority_variant(authority_cases, candidate_authority_records)
    )
    summary = {
        "baseline": baseline_score,
        "candidate": candidate_score,
        "acceptance": acceptance_summary(baseline_score, candidate_score),
    }
    (output_root / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_blind_sample(
        cases=cases,
        baseline_records=baseline_records,
        candidate_records=candidate_records,
        authority_cases=authority_cases,
        baseline_authority_records=baseline_authority_records,
        candidate_authority_records=candidate_authority_records,
        output_root=output_root,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["acceptance"]["automatic_pass"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")
    check = subparsers.add_parser("check", help="run static guidance checks")
    check.add_argument("--root", type=Path, default=_repo_root_from_script())
    check.add_argument("--format", choices=("text", "json"), default="text")

    ab = subparsers.add_parser("ab", help="run the pinned baseline/candidate eval")
    ab.add_argument("--baseline-root", type=Path, required=True)
    ab.add_argument("--candidate-root", type=Path, required=True)
    ab.add_argument(
        "--cases",
        type=Path,
        default=_repo_root_from_script()
        / ".agents"
        / "evals"
        / "skill-routing-cases.yaml",
    )
    ab.add_argument(
        "--authority-cases",
        type=Path,
        default=_repo_root_from_script() / ".agents" / "evals" / "authority-cases.yaml",
    )
    ab.add_argument(
        "--output-root",
        type=Path,
        default=_repo_root_from_script()
        / "build"
        / "dev-artifacts"
        / "agent-guidance-eval",
    )
    ab.add_argument("--model", default="gpt-5.6-sol")
    ab.add_argument("--reasoning-effort", default="xhigh")
    ab.add_argument("--repeats", type=int, default=3)
    ab.add_argument("--max-concurrency", type=int, default=3)
    ab.add_argument("--timeout-seconds", type=int, default=300)
    human = subparsers.add_parser(
        "score-human",
        help="score a completed 12-case blind review",
    )
    human.add_argument("--sample", type=Path, required=True)
    human.add_argument("--key", type=Path, required=True)
    human.add_argument("--summary", type=Path, required=True)
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
    if args.command == "ab":
        if args.repeats < 1 or not 1 <= args.max_concurrency <= 3:
            parser.error("repeats must be positive and max-concurrency must be 1-3")
        return _run_ab(args)
    if args.command == "score-human":
        result = score_human_review(
            sample_path=args.sample,
            key_path=args.key,
            summary_path=args.summary,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["pass"] else 1
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
