from __future__ import annotations

from dataclasses import replace

import pytest

from scripts.dev.product_scenario_manifest import (
    IMMEDIATE_PROFILE_ID,
    PRODUCT_SCENARIO_EXECUTIONS,
    PRODUCT_SCENARIO_PROFILES,
    PRODUCT_SCENARIOS,
    ProfileSpec,
    ScenarioManifestError,
    validate_manifest,
)


def test_immediate_profile_has_exactly_twenty_unique_high_difference_scenarios() -> (
    None
):
    profile = PRODUCT_SCENARIO_PROFILES[IMMEDIATE_PROFILE_ID]
    selected = [PRODUCT_SCENARIOS[item] for item in profile.scenario_ids]

    assert profile.expected_scenario_count == 20
    assert profile.denominator_kind == "product_scenarios"
    assert profile.moabb_dataset_campaign_in_scope is False
    assert len(selected) == 20
    assert len({item.scenario_id for item in selected}) == 20
    assert len({(item.execution_id, item.evidence_key) for item in selected}) == 20
    assert all(item.scope.strip() for item in selected)
    assert all(item.pass_criteria for item in selected)
    assert all(item.claim_boundary.strip() for item in selected)
    assert all(item.artifact_policy.description.strip() for item in selected)


def test_immediate_profile_covers_required_product_dimensions() -> None:
    profile = PRODUCT_SCENARIO_PROFILES[IMMEDIATE_PROFILE_ID]
    selected = [PRODUCT_SCENARIOS[item] for item in profile.scenario_ids]
    tags = {tag for item in selected for tag in item.coverage_tags}

    assert {
        "real-source-3plus",
        "multi-format-import",
        "label",
        "epoch",
        "training",
        "evaluation",
        "visualization",
        "agent-success",
        "agent-blocked",
        "agent-confirmation",
        "agent-recovery",
        "full",
        "narrow",
        "dpi-100",
        "dpi-125",
        "dpi-150",
    } <= tags


def test_manifest_reuses_canonical_handoff_gates_and_stable_showcase_cases() -> None:
    validate_manifest()

    gate_refs = {
        execution.gate_id
        for execution in PRODUCT_SCENARIO_EXECUTIONS.values()
        if execution.gate_id is not None
    }
    assert {
        "fetch-required-ci",
        "verify-required-ci",
        "command-spine",
        "human-like-product",
        "dataset-narrow",
        "visualization-render",
        "chatpanel-dpi",
        "dataset-validation-matrix",
        "data-interpretation-matrix",
        "real-data-interpretation-training",
        "public-cross-source-training",
    } <= gate_refs

    assert PRODUCT_SCENARIO_EXECUTIONS[
        "verify-required-ci"
    ].depends_on_execution_ids == ("fetch-required-ci",)
    for execution_id in (
        "dataset-validation-matrix",
        "data-interpretation-matrix",
        "real-data-interpretation-training",
        "public-cross-source-training",
    ):
        assert PRODUCT_SCENARIO_EXECUTIONS[execution_id].depends_on_execution_ids == (
            "verify-required-ci",
        )

    agent_scenarios = [
        item
        for item in PRODUCT_SCENARIOS.values()
        if item.validator.kind == "agent_showcase_case"
    ]
    assert len(agent_scenarios) == 8
    assert len({item.validator.key for item in agent_scenarios}) == 8


def test_all_native_executions_are_bounded_and_disable_core_dumps() -> None:
    for execution in PRODUCT_SCENARIO_EXECUTIONS.values():
        assert execution.timeout_seconds > 0
        if execution.native:
            command = execution.command_template()
            assert command[:3] == ("prlimit", "--core=0", "--")


def test_profiles_are_configurable_without_treating_twenty_as_catalog_capacity() -> (
    None
):
    base = next(iter(PRODUCT_SCENARIOS.values()))
    expanded = {
        f"configurable.case-{index:02d}": replace(
            base,
            scenario_id=f"configurable.case-{index:02d}",
            evidence_key=f"configurable.case-{index:02d}",
        )
        for index in range(24)
    }
    profile = ProfileSpec(
        profile_id="configurable-24",
        scenario_ids=tuple(expanded),
        expected_scenario_count=24,
        purpose="Test-only configurable profile.",
        claim_boundary="This test profile supports no product claim.",
    )

    validate_manifest(
        scenarios=expanded,
        executions=PRODUCT_SCENARIO_EXECUTIONS,
        profiles={profile.profile_id: profile},
    )


def test_manifest_rejects_duplicate_shared_evidence_and_profile_drift() -> None:
    profile = PRODUCT_SCENARIO_PROFILES[IMMEDIATE_PROFILE_ID]
    first = PRODUCT_SCENARIOS[profile.scenario_ids[0]]
    second_id = profile.scenario_ids[1]
    duplicated = dict(PRODUCT_SCENARIOS)
    duplicated[second_id] = replace(
        duplicated[second_id],
        execution_id=first.execution_id,
        evidence_key=first.evidence_key,
    )

    with pytest.raises(ScenarioManifestError, match="reuses evidence"):
        validate_manifest(scenarios=duplicated)

    drifted_profile = replace(profile, expected_scenario_count=19)
    with pytest.raises(ScenarioManifestError, match="expected scenario count"):
        validate_manifest(
            profiles={IMMEDIATE_PROFILE_ID: drifted_profile},
        )


def test_immediate_claim_boundary_rejects_statistical_and_moabb_extrapolation() -> None:
    profile = PRODUCT_SCENARIO_PROFILES[IMMEDIATE_PROFILE_ID]
    boundary = profile.claim_boundary.casefold()

    assert "bug risk" in boundary
    assert "<5%" in boundary
    assert "moabb" in boundary
    assert "20" in boundary


def test_cross_source_scenario_preserves_public_fixture_scientific_boundary() -> None:
    scenario = PRODUCT_SCENARIOS["data.cross-source-training-persistence"]
    scope = scenario.scope.casefold()
    boundary = scenario.claim_boundary.casefold()

    assert "class-grounded physionet edf and bbci gdf training" in scope
    assert "sccn set and mne cnt import/preprocess-only boundary cases" in scope
    assert "supervised epoch is intentionally blocked" in scope
    assert "epoch-only" not in scope
    assert "import/preprocess-only fixtures" in boundary
    assert "not relabeled as supervised data" in boundary


def test_profile_rejects_moabb_dataset_campaign_conflation() -> None:
    profile = PRODUCT_SCENARIO_PROFILES[IMMEDIATE_PROFILE_ID]

    with pytest.raises(ScenarioManifestError, match="conflates product scenarios"):
        validate_manifest(
            profiles={
                IMMEDIATE_PROFILE_ID: replace(
                    profile,
                    moabb_dataset_campaign_in_scope=True,
                )
            }
        )
