from __future__ import annotations

from pathlib import Path

import pytest

from scripts.dev.audit_agent_guidance import (
    AGENTS_MAX_BYTES,
    RETIRED_EVAL_FILES,
    audit_guidance,
    build_parser,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_current_repository_guidance_passes_the_public_audit() -> None:
    """Keep one real-tree check alongside the isolated audit failure cases."""
    assert audit_guidance(REPO_ROOT) == []


def test_public_audit_rejects_invalid_model_dispatch_settings(tmp_path: Path) -> None:
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir()
    config.write_text(
        """\
model = "gpt-5.6-sol"
model_reasoning_effort = "medium"
service_tier = "fast"

[agents]
default_subagent_model = "gpt-5.6-terra"
default_subagent_reasoning_effort = "medium"
""",
        encoding="utf-8",
    )

    errors = audit_guidance(tmp_path)

    assert ".codex/config.toml must set model='gpt-6-astra'" in errors
    assert (
        ".codex/config.toml [agents] must set "
        "max_concurrent_threads_per_session=2" in errors
    )
    assert (
        ".codex/config.toml must not persist service_tier; Fast is foreground-only"
        in errors
    )


def test_public_audit_rejects_worker_and_concurrency_drift(tmp_path: Path) -> None:
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir()
    config.write_text(
        """\
model = "gpt-6-astra"
model_reasoning_effort = "medium"

[agents]
max_concurrent_threads_per_session = 3
default_subagent_model = "gpt-5.6-luna"
default_subagent_reasoning_effort = "medium"
""",
        encoding="utf-8",
    )

    errors = audit_guidance(tmp_path)

    assert (
        ".codex/config.toml [agents] must set max_concurrent_threads_per_session=2"
        in errors
    )
    assert (
        ".codex/config.toml [agents] must set default_subagent_model='gpt-6-astra'"
        in errors
    )


def test_agents_size_contract_has_no_minimum(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("short\n", encoding="utf-8")

    errors = audit_guidance(tmp_path)

    assert not any("minimum" in error or "expected range" in error for error in errors)
    assert not any("AGENTS.md is" in error and "bytes" in error for error in errors)


def test_agents_size_contract_rejects_only_oversized_content(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "x" * (AGENTS_MAX_BYTES + 1),
        encoding="utf-8",
    )

    errors = audit_guidance(tmp_path)

    assert any("AGENTS.md is" in error and "maximum" in error for error in errors)


def test_static_audit_rejects_unbounded_milestone_language(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "Milestone 是最低門檻。\n",
        encoding="utf-8",
    )

    errors = audit_guidance(tmp_path)

    assert any("unbounded delivery token" in error for error in errors)


def test_skill_inventory_accepts_optional_metadata_and_neutral_description(
    tmp_path: Path,
) -> None:
    skill = tmp_path / ".agents" / "skills" / "new-reviewer" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\n"
        "name: new-reviewer\n"
        'description: "Bounded review of one production concern."\n'
        "license: Apache-2.0\n"
        'allowed-tools: "Read, Grep"\n'
        "metadata:\n"
        "  display_name: New Reviewer\n"
        "---\n\n"
        "# New Reviewer\n",
        encoding="utf-8",
    )

    errors = audit_guidance(tmp_path)

    assert not any(str(skill) in error for error in errors)


@pytest.mark.parametrize(
    ("frontmatter", "expected_error"),
    [
        ('description: ""\n', "description must be a non-empty string"),
        ("unknown_metadata: true\n", "unsupported frontmatter keys"),
    ],
)
def test_skill_frontmatter_rejects_invalid_required_or_optional_metadata(
    tmp_path: Path,
    frontmatter: str,
    expected_error: str,
) -> None:
    skill = tmp_path / ".agents" / "skills" / "new-reviewer" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        f"---\nname: new-reviewer\n{frontmatter}---\n",
        encoding="utf-8",
    )

    errors = audit_guidance(tmp_path)

    assert any(expected_error in error and str(skill) in error for error in errors)


def test_retired_external_eval_corpus_is_rejected(tmp_path: Path) -> None:
    eval_root = tmp_path / ".agents" / "evals"
    eval_root.mkdir(parents=True)
    retired = RETIRED_EVAL_FILES[0]
    (eval_root / retired).write_text("cases: []\n", encoding="utf-8")

    errors = audit_guidance(tmp_path)

    assert any(f"retired external eval remains: {retired}" in error for error in errors)


@pytest.mark.parametrize("command", ["ab", "score-human"])
def test_parser_exposes_only_static_check(command: str) -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args([command])
