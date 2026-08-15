from __future__ import annotations

from pathlib import Path

import yaml

from scripts.dev.audit_agent_guidance import (
    AGENTS_MAX_BYTES,
    OPERATIONS_MAX_BYTES,
    audit_guidance,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_repository_agent_guidance_contract_is_clean() -> None:
    assert audit_guidance(REPO_ROOT) == []


def test_root_guidance_is_lean_and_scope_bounded() -> None:
    agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    operations = (REPO_ROOT / ".agents" / "README.md").read_text(encoding="utf-8")

    assert len(agents.encode("utf-8")) <= AGENTS_MAX_BYTES
    assert len(operations.encode("utf-8")) <= OPERATIONS_MAX_BYTES
    assert "scope ceiling" in agents
    assert "Milestone 是最低門檻" not in agents
    assert "300" in agents and "800" in agents and "1,500" in agents


def test_ui_mutation_requires_explicit_user_confirmation() -> None:
    agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "XBrainLab/ui/" in agents
    assert "實作前必須先取得使用者明確確認" in agents
    assert "唯讀診斷" in agents


def test_product_repairs_follow_one_durable_plan_before_implementation() -> None:
    agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "plan-first" in agents.lower()
    assert "docs/planning/now.md" in agents
    assert "問題與證據" in agents
    assert "修理步驟" in agents
    assert "開始實作" in agents


def test_product_merge_requires_user_manual_acceptance() -> None:
    agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    handoff = (REPO_ROOT / ".agents" / "workflows" / "handoff-candidate.md").read_text(
        encoding="utf-8"
    )

    assert "手測通過並同意 merge" in agents
    assert "Manual acceptance" in agents
    assert "later source changes require retest" in handoff
    assert "Automation does not substitute" in handoff


def test_external_guidance_ab_surface_is_retired() -> None:
    assert not (REPO_ROOT / ".agents" / "evals" / "skill-routing-cases.yaml").exists()
    assert not (REPO_ROOT / ".agents" / "evals" / "authority-cases.yaml").exists()


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
