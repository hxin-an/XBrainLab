from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from scripts.dev.handoff_gate_spec import HANDOFF_GATE_SPECS
from scripts.dev.validation_control_plane import (
    ChangeDescriptor,
    ChangeIntent,
    ClaimLevel,
    Layer,
    plan_validation,
)
from scripts.dev.validation_gate_catalog import (
    CONTROL_PLANE_RULE_TAGS,
    HANDOFF_VALIDATION_GATE_CATALOG,
)


def test_catalog_adds_selection_metadata_without_forking_command_truth() -> None:
    assert tuple(HANDOFF_VALIDATION_GATE_CATALOG) == tuple(HANDOFF_GATE_SPECS)

    for gate_id, entry in HANDOFF_VALIDATION_GATE_CATALOG.items():
        assert entry.gate_id == gate_id
        assert entry.tags
        assert isinstance(entry.tags, frozenset)
        assert isinstance(entry.dependencies, tuple)
        assert not hasattr(entry, "argv")
        assert not hasattr(entry, "timeout_seconds")

        with pytest.raises(FrozenInstanceError):
            entry.expensive = not entry.expensive  # type: ignore[misc]

    with pytest.raises(TypeError):
        HANDOFF_VALIDATION_GATE_CATALOG["new-gate"] = object()  # type: ignore[index]


def test_catalog_dependencies_are_registered_unique_and_topologically_ordered() -> None:
    positions = {
        gate_id: index for index, gate_id in enumerate(HANDOFF_VALIDATION_GATE_CATALOG)
    }

    for gate_id, entry in HANDOFF_VALIDATION_GATE_CATALOG.items():
        assert len(entry.dependencies) == len(set(entry.dependencies))
        assert all(dependency in positions for dependency in entry.dependencies)
        assert all(
            positions[dependency] < positions[gate_id]
            for dependency in entry.dependencies
        )


def test_every_control_plane_rule_has_a_canonical_registered_gate() -> None:
    supported = frozenset(
        tag for entry in HANDOFF_VALIDATION_GATE_CATALOG.values() for tag in entry.tags
    )

    assert supported >= CONTROL_PLANE_RULE_TAGS


def test_expensive_boundaries_are_explicit_in_catalog_metadata() -> None:
    expensive = {
        gate_id
        for gate_id, entry in HANDOFF_VALIDATION_GATE_CATALOG.items()
        if entry.expensive
    }

    assert {
        "complete-regression",
        "granite-runtime",
        "human-like-product",
        "native-lifecycle-tests",
        "required-public-io",
    } <= expensive
    assert {
        "git-diff-check",
        "ruff-check",
        "ruff-format-check",
        "mkdocs-strict",
    }.isdisjoint(expensive)


def test_product_backend_plan_runs_full_regression_without_unrelated_expensive_qa() -> (
    None
):
    plan = plan_validation(
        ChangeDescriptor(
            intent=ChangeIntent.FEATURE,
            claim_level=ClaimLevel.PRODUCT_PR,
            declared_layers=frozenset({Layer.BACKEND_DOMAIN}),
        ),
        ["XBrainLab/backend/utils/logger.py"],
        gate_catalog=HANDOFF_VALIDATION_GATE_CATALOG,
    )

    assert plan.ready
    assert "complete-regression" in plan.execution_ids
    assert {
        "granite-runtime",
        "human-like-product",
        "native-lifecycle-tests",
        "required-public-io",
    }.isdisjoint(plan.execution_ids)


def test_eeg_training_plan_does_not_select_granite_or_assistant_qa() -> None:
    plan = plan_validation(
        ChangeDescriptor(
            intent=ChangeIntent.BUG_FIX,
            claim_level=ClaimLevel.PRODUCT_PR,
        ),
        ["XBrainLab/backend/training/trainer.py"],
        gate_catalog=HANDOFF_VALIDATION_GATE_CATALOG,
    )

    assert plan.ready
    assert "complete-regression" in plan.execution_ids
    assert "granite-runtime" not in plan.execution_ids
    assert "assistant-security-suite" not in plan.execution_ids


def test_handoff_dashboard_depends_on_its_calibration_artifact_producer() -> None:
    dashboard = HANDOFF_VALIDATION_GATE_CATALOG["handoff-dashboard"]

    assert "resource-calibration" in dashboard.dependencies


def test_performance_pr_selects_cpu_safe_contract_not_handoff_gpu_calibration() -> None:
    plan = plan_validation(
        ChangeDescriptor(
            intent=ChangeIntent.PERFORMANCE,
            claim_level=ClaimLevel.PRODUCT_PR,
            declared_layers=frozenset({Layer.BACKEND_DOMAIN}),
        ),
        ["XBrainLab/backend/utils/logger.py"],
        gate_catalog=HANDOFF_VALIDATION_GATE_CATALOG,
    )

    assert "resource-contract" in plan.execution_ids
    assert "resource-calibration" not in plan.execution_ids


def test_resource_policy_bug_fix_selects_cpu_resource_contract_by_path() -> None:
    plan = plan_validation(
        ChangeDescriptor(
            intent=ChangeIntent.BUG_FIX,
            claim_level=ClaimLevel.PRODUCT_PR,
        ),
        ["XBrainLab/backend/application/resource_guard.py"],
        gate_catalog=HANDOFF_VALIDATION_GATE_CATALOG,
    )

    assert "resource-contract" in plan.execution_ids
    assert "resource-calibration" not in plan.execution_ids
