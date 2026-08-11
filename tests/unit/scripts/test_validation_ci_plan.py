from __future__ import annotations

import subprocess
import sys

import pytest

from scripts.dev.ci_gate_ownership import CI_GATE_OWNERS
from scripts.dev.ci_test_command_catalog import LINUX_CI_COMMANDS, PLATFORM_CI_COMMANDS
from scripts.dev.handoff_gate_spec import HANDOFF_GATE_SPECS
from scripts.dev.validation_ci_plan import CiValidationPlan, build_ci_validation_plan
from scripts.dev.validation_control_plane import (
    ChangeDescriptor,
    ChangeIntent,
    ClaimLevel,
    Layer,
    bind_validation_plan,
    plan_validation,
)
from scripts.dev.validation_gate_catalog import HANDOFF_VALIDATION_GATE_CATALOG


def _plan(path: str, *layers: Layer):
    plan = plan_validation(
        ChangeDescriptor(
            intent=ChangeIntent.BUG_FIX,
            claim_level=ClaimLevel.PRODUCT_PR,
            declared_layers=frozenset(layers),
        ),
        [path],
        gate_catalog=HANDOFF_VALIDATION_GATE_CATALOG,
    )
    return bind_validation_plan(plan, source_sha="a" * 40, base_sha="b" * 40)


def test_backend_product_pr_selects_one_linux_suite_without_unrelated_matrices() -> (
    None
):
    plan = _plan("XBrainLab/backend/utils/logger.py", Layer.BACKEND_DOMAIN)
    ci = build_ci_validation_plan(plan, source_sha="a" * 40)

    assert ci.run_product
    assert ci.run_lint
    assert ci.linux_commands == LINUX_CI_COMMANDS
    assert ci.platform_commands == ()
    assert ci.run_public_data is False
    assert ci.run_docs is False
    assert ci.required_owners == ("focused", "lint", "plan", "product")
    assert {gate_id for gate_id, _owner in ci.gate_owners} == set(plan.execution_ids)
    assert ci.gate_ids_for_owner("lint") == tuple(
        gate_id
        for gate_id in HANDOFF_GATE_SPECS
        if gate_id in plan.execution_ids and CI_GATE_OWNERS[gate_id] == "lint"
    )


def test_data_native_and_docs_risks_select_only_their_ci_capabilities() -> None:
    data = build_ci_validation_plan(
        _plan(
            "XBrainLab/backend/dataset/split_audit.py",
            Layer.DATA_SEMANTICS,
        ),
        source_sha="a" * 40,
    )
    native = build_ci_validation_plan(
        _plan(
            "XBrainLab/ui/visualization/native_lifecycle.py",
            Layer.NATIVE_LIFECYCLE,
        ),
        source_sha="a" * 40,
    )
    docs_plan = plan_validation(
        ChangeDescriptor(
            intent=ChangeIntent.DOCS,
            claim_level=ClaimLevel.PRODUCT_PR,
            declared_layers=frozenset({Layer.GUIDANCE_DOCS}),
        ),
        ["AGENTS.md", "docs/validation/README.md"],
        gate_catalog=HANDOFF_VALIDATION_GATE_CATALOG,
    )
    docs_plan = bind_validation_plan(
        docs_plan,
        source_sha="a" * 40,
        base_sha="b" * 40,
    )
    docs = build_ci_validation_plan(docs_plan, source_sha="a" * 40)

    assert data.run_public_data
    assert data.run_platform is False
    assert data.platform_commands == ()
    assert native.run_platform
    assert native.run_native
    assert native.run_ui
    assert native.platform_commands == PLATFORM_CI_COMMANDS
    assert native.run_public_data is False
    assert docs.run_docs
    assert docs.run_product is False
    assert docs.linux_commands == ()
    assert docs.required_owners == ("docs", "plan")


def test_dependency_change_requires_cross_platform_ci() -> None:
    dependency = build_ci_validation_plan(
        _plan("poetry.lock", Layer.DEPENDENCY),
        source_sha="a" * 40,
    )

    assert dependency.run_platform
    assert dependency.platform_commands == PLATFORM_CI_COMMANDS


def test_ci_plan_has_stable_json_and_lineage() -> None:
    plan = _plan("XBrainLab/backend/utils/logger.py", Layer.BACKEND_DOMAIN)
    first = build_ci_validation_plan(plan, source_sha="a" * 40)
    second = build_ci_validation_plan(plan, source_sha="a" * 40)

    assert first == second
    assert first.plan_digest == plan.digest()
    assert first.source_sha == "a" * 40
    assert first.digest() == second.digest()
    assert '"linux_commands"' in first.to_json()
    assert CiValidationPlan.from_json(first.to_json()) == first


def test_ci_expansion_rejects_unbound_or_different_source_plan() -> None:
    unbound = plan_validation(
        ChangeDescriptor(
            intent=ChangeIntent.BUG_FIX,
            claim_level=ClaimLevel.PRODUCT_PR,
        ),
        ["XBrainLab/backend/utils/logger.py"],
        gate_catalog=HANDOFF_VALIDATION_GATE_CATALOG,
    )

    with pytest.raises(ValueError, match="bound"):
        build_ci_validation_plan(unbound, source_sha="a" * 40)
    with pytest.raises(ValueError, match="source SHA"):
        build_ci_validation_plan(
            _plan("XBrainLab/backend/utils/logger.py"), source_sha="c" * 40
        )


def test_ci_expansion_fails_closed_when_selected_gate_has_no_execution_owner() -> None:
    plan = plan_validation(
        ChangeDescriptor(
            intent=ChangeIntent.BUG_FIX,
            claim_level=ClaimLevel.PRODUCT_PR,
            required_rule_ids=frozenset({"exact-model"}),
        ),
        ["XBrainLab/llm/core/model_catalog.py"],
        gate_catalog=HANDOFF_VALIDATION_GATE_CATALOG,
    )
    plan = bind_validation_plan(plan, source_sha="a" * 40, base_sha="b" * 40)

    with pytest.raises(ValueError, match=r"no CI execution owner.*granite-runtime"):
        build_ci_validation_plan(plan, source_sha="a" * 40)


def test_ci_command_metadata_import_is_dependency_free() -> None:
    completed = subprocess.run(  # noqa: S603 - fixed interpreter metadata import.
        [
            sys.executable,
            "-S",
            "-c",
            (
                "from scripts.dev.validation_ci_plan import "
                "build_ci_validation_plan; assert build_ci_validation_plan"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr


def test_ci_owner_registry_is_registered_and_covers_product_semantic_space() -> None:
    assert set(CI_GATE_OWNERS) <= set(HANDOFF_GATE_SPECS)

    paths = {
        Layer.GUIDANCE_DOCS: "docs/current.md",
        Layer.TEST_INFRASTRUCTURE: "tests/unit/backend/test_owner.py",
        Layer.CI_VALIDATION: ".github/workflows/ci.yml",
        Layer.DEPENDENCY: "poetry.lock",
        Layer.UI_PRESENTATION: "XBrainLab/ui/panels/training_panel.py",
        Layer.UI_BEHAVIOR: "XBrainLab/ui/controllers/training.py",
        Layer.APPLICATION_SERVICE: "XBrainLab/backend/application/application_service.py",
        Layer.BACKEND_DOMAIN: "XBrainLab/backend/utils/logger.py",
        Layer.PERSISTENCE: "XBrainLab/backend/training/record/safe_artifact_store.py",
        Layer.DATA_SEMANTICS: "XBrainLab/backend/dataset/split_audit.py",
        Layer.MODEL_RUNTIME: "XBrainLab/llm/core/model_catalog.py",
        Layer.ASSISTANT: "XBrainLab/llm/tools/tool_registry.py",
        Layer.NATIVE_LIFECYCLE: "XBrainLab/ui/visualization/native_lifecycle.py",
        Layer.PLATFORM_PACKAGING: "scripts/launchers/xbrainlab_wsl_launcher.ps1",
        Layer.SECURITY_PRIVACY: "XBrainLab/llm/tools/authorized_paths.py",
    }
    for intent in ChangeIntent:
        for layer, path in paths.items():
            plan = plan_validation(
                ChangeDescriptor(
                    intent=intent,
                    claim_level=ClaimLevel.PRODUCT_PR,
                    declared_layers=frozenset({layer}),
                ),
                [path],
                gate_catalog=HANDOFF_VALIDATION_GATE_CATALOG,
            )
            plan = bind_validation_plan(
                plan,
                source_sha="a" * 40,
                base_sha="b" * 40,
            )

            ci_plan = build_ci_validation_plan(plan, source_sha="a" * 40)

            assert set(ci_plan.selected_gate_ids) == set(plan.execution_ids)
