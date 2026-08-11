from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml

from scripts.dev.audit_agent_guidance import (
    CASE_CATEGORY_COUNTS,
    EXPECTED_SKILLS,
    audit_guidance,
    load_cases,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_repository_agent_guidance_contract_is_clean() -> None:
    assert audit_guidance(REPO_ROOT) == []


def test_routing_corpus_has_registered_distribution_and_skill_references() -> None:
    cases = load_cases(REPO_ROOT / ".agents" / "evals" / "skill-routing-cases.yaml")

    assert len(cases) == 60
    assert Counter(case.category for case in cases) == CASE_CATEGORY_COUNTS
    referenced = {
        skill
        for case in cases
        for skill in (
            case.expected_primary,
            *case.allowed_secondary,
            *case.forbidden_skills,
        )
        if skill is not None
    }
    assert referenced == set(EXPECTED_SKILLS)


def test_mcp_skill_is_machine_enforced_as_explicit_only() -> None:
    payload = yaml.safe_load(
        (
            REPO_ROOT
            / ".agents"
            / "skills"
            / "mcp-adapter-reviewer"
            / "agents"
            / "openai.yaml"
        ).read_text(encoding="utf-8")
    )

    assert payload["policy"]["allow_implicit_invocation"] is False
    assert "$mcp-adapter-reviewer" in payload["interface"]["default_prompt"]
