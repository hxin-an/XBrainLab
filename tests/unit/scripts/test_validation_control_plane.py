from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass

import pytest

from scripts.dev.validation_control_plane import (
    ChangeDescriptor,
    ChangedPath,
    ChangeIntent,
    ClaimLevel,
    Layer,
    PlannedExecution,
    RiskLevel,
    ValidationPlan,
    ValidationReceipt,
    VerdictStatus,
    bind_validation_plan,
    evaluate_validation_receipt,
    infer_changed_path,
    plan_validation,
)


@dataclass(frozen=True)
class _CatalogEntry:
    tags: frozenset[str]
    dependencies: tuple[str, ...] = ()
    expensive: bool = False


def _catalog() -> dict[str, object]:
    return {
        "git-diff-check": {"tags": {"identity"}},
        "ruff-check": {
            "tags": {"static"},
            "dependencies": ("git-diff-check",),
        },
        "focused-contract": {
            "tags": {"focused"},
            "dependencies": ("ruff-check",),
        },
        "mkdocs-strict": {
            "tags": {"docs"},
            "dependencies": ("git-diff-check",),
        },
        "guidance-contract": {
            "tags": {"guidance-contract"},
            "dependencies": ("mkdocs-strict",),
        },
        "test-quality": {
            "tags": {"test-infrastructure"},
            "dependencies": ("focused-contract",),
        },
        "ci-contract": {
            "tags": {"ci-validation", "dependency-change"},
            "dependencies": ("focused-contract",),
        },
        "backend-contract": {
            "tags": {"backend"},
            "dependencies": ("focused-contract",),
        },
        "command-spine": {
            "tags": {"application-service", "persistence"},
            "dependencies": ("backend-contract",),
        },
        "complete-regression": {
            "tags": {"product-regression", "unknown-change"},
            "dependencies": ("focused-contract",),
            "expensive": True,
        },
        "ui-behavior": {
            "tags": {"ui-behavior"},
            "dependencies": ("focused-contract",),
        },
        "human-like-product": _CatalogEntry(
            tags=frozenset({"ui-visible"}),
            dependencies=("ui-behavior",),
            expensive=True,
        ),
        "semantic-oracle": {
            "tags": {"data-semantics", "model-runtime"},
            "dependencies": ("command-spine",),
        },
        "required-public-io": {
            "tags": {"data-diversity"},
            "dependencies": ("semantic-oracle",),
            "expensive": True,
        },
        "assistant-security-suite": {
            "tags": {"assistant"},
            "dependencies": ("command-spine",),
        },
        "granite-runtime": {
            "tags": {"exact-model"},
            "dependencies": ("assistant-security-suite",),
            "expensive": True,
        },
        "native-lifecycle-tests": {
            "tags": {"native-lifecycle"},
            "dependencies": ("focused-contract",),
            "expensive": True,
        },
        "platform-contracts": {
            "tags": {"platform-packaging"},
            "dependencies": ("native-lifecycle-tests",),
            "expensive": True,
        },
        "security-boundary": {
            "tags": {"security-privacy"},
            "dependencies": ("focused-contract",),
        },
        "handoff-dashboard": {
            "tags": {"handoff"},
            "dependencies": ("complete-regression",),
            "expensive": True,
        },
        "release-acceptance": {
            "tags": {"release"},
            "dependencies": ("handoff-dashboard", "platform-contracts"),
            "expensive": True,
        },
        "thesis-protocol": {
            "tags": {"thesis"},
            "dependencies": ("handoff-dashboard", "granite-runtime"),
            "expensive": True,
        },
    }


def _descriptor(
    *,
    intent: ChangeIntent = ChangeIntent.BUG_FIX,
    claim: ClaimLevel = ClaimLevel.CHECKPOINT,
    layers: frozenset[Layer] = frozenset(),
    risk: RiskLevel = RiskLevel.LOW,
) -> ChangeDescriptor:
    return ChangeDescriptor(
        intent=intent,
        claim_level=claim,
        declared_layers=layers,
        declared_risk=risk,
    )


def test_models_are_immutable_and_use_canonical_collection_types() -> None:
    descriptor = _descriptor(layers=frozenset({Layer.UI_BEHAVIOR}))
    changed = infer_changed_path("XBrainLab/ui/controllers/training.py")
    execution = PlannedExecution(
        gate_id="focused-contract",
        dependencies=("ruff-check",),
        satisfies_rules=("focused",),
        expensive=False,
    )

    with pytest.raises(FrozenInstanceError):
        descriptor.declared_risk = RiskLevel.CRITICAL  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        changed.path = "docs/current.md"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        execution.gate_id = "other"  # type: ignore[misc]

    assert isinstance(descriptor.declared_layers, frozenset)
    assert isinstance(changed.layers, frozenset)
    assert isinstance(execution.dependencies, tuple)


@pytest.mark.parametrize(
    ("path", "expected_layer", "risk_floor"),
    [
        ("unowned/new_surface.xyz", Layer.UNKNOWN, RiskLevel.CRITICAL),
        ("tests/unit/backend/test_owner.py", Layer.TEST_INFRASTRUCTURE, RiskLevel.HIGH),
        ("tests/fixtures/data/new.edf", Layer.DATA_SEMANTICS, RiskLevel.CRITICAL),
        ("scripts/dev/handoff_gate_spec.py", Layer.CI_VALIDATION, RiskLevel.CRITICAL),
        (
            "scripts/dev/select_validation_gates.py",
            Layer.CI_VALIDATION,
            RiskLevel.CRITICAL,
        ),
        (
            "scripts/dev/validation_gate_catalog.py",
            Layer.CI_VALIDATION,
            RiskLevel.CRITICAL,
        ),
        (
            "scripts/dev/ci_gate_ownership.py",
            Layer.CI_VALIDATION,
            RiskLevel.CRITICAL,
        ),
        (
            "scripts/dev/validation_ci_evidence.py",
            Layer.CI_VALIDATION,
            RiskLevel.CRITICAL,
        ),
        ("scripts/ci/run_checks.py", Layer.CI_VALIDATION, RiskLevel.CRITICAL),
        (".github/workflows/ci.yml", Layer.CI_VALIDATION, RiskLevel.CRITICAL),
        ("poetry.lock", Layer.DEPENDENCY, RiskLevel.CRITICAL),
        (
            "XBrainLab/backend/application/application_service.py",
            Layer.APPLICATION_SERVICE,
            RiskLevel.CRITICAL,
        ),
        (
            "XBrainLab/backend/state.py",
            Layer.APPLICATION_SERVICE,
            RiskLevel.CRITICAL,
        ),
        (
            "XBrainLab/backend/training/record/safe_artifact_store.py",
            Layer.PERSISTENCE,
            RiskLevel.CRITICAL,
        ),
        (
            "XBrainLab/llm/tools/authorized_paths.py",
            Layer.SECURITY_PRIVACY,
            RiskLevel.CRITICAL,
        ),
        (
            "XBrainLab/backend/dataset/split_audit.py",
            Layer.DATA_SEMANTICS,
            RiskLevel.CRITICAL,
        ),
        (
            "XBrainLab/llm/core/model_catalog.py",
            Layer.MODEL_RUNTIME,
            RiskLevel.CRITICAL,
        ),
        (
            "XBrainLab/ui/visualization/native_lifecycle.py",
            Layer.NATIVE_LIFECYCLE,
            RiskLevel.CRITICAL,
        ),
    ],
)
def test_path_inference_applies_fail_closed_risk_floors(
    path: str,
    expected_layer: Layer,
    risk_floor: RiskLevel,
) -> None:
    changed = infer_changed_path(path)

    assert expected_layer in changed.layers
    assert changed.risk_floor >= risk_floor
    assert changed.matched_rule_ids


def test_eeg_training_backend_does_not_trigger_exact_local_llm_validation() -> None:
    changed = infer_changed_path("XBrainLab/backend/training/trainer.py")

    assert Layer.BACKEND_DOMAIN in changed.layers
    assert Layer.MODEL_RUNTIME not in changed.layers


def test_pull_request_template_is_guidance_not_an_unknown_path() -> None:
    changed = infer_changed_path(".github/pull_request_template.md")

    assert changed.layers == frozenset({Layer.GUIDANCE_DOCS})
    assert changed.risk_floor is RiskLevel.LOW


@pytest.mark.parametrize(
    "path",
    [
        "XBrainLab/ui/panels/training_panel.py",
        "XBrainLab/ui/chat/chat_panel.py",
        "XBrainLab/ui/main_window.py",
    ],
)
def test_render_owning_ui_surfaces_are_visible_presentation(path: str) -> None:
    changed = infer_changed_path(path)

    assert Layer.UI_PRESENTATION in changed.layers
    assert changed.risk_floor >= RiskLevel.HIGH


@pytest.mark.parametrize(
    "path",
    [
        "XBrainLab/ui/core/event_dispatch.py",
        "XBrainLab/ui/components/label_widget.py",
    ],
)
def test_generic_ui_event_or_label_names_do_not_trigger_data_semantics(
    path: str,
) -> None:
    assert Layer.DATA_SEMANTICS not in infer_changed_path(path).layers


def test_agent_semantics_union_with_path_inference_and_cannot_downgrade() -> None:
    forged_low_risk_path = ChangedPath(
        path="XBrainLab/backend/application/application_service.py",
        layers=frozenset({Layer.GUIDANCE_DOCS}),
        risk_floor=RiskLevel.LOW,
        matched_rule_ids=("agent-claim",),
    )
    plan = plan_validation(
        _descriptor(
            layers=frozenset({Layer.UI_BEHAVIOR}),
            risk=RiskLevel.MEDIUM,
        ),
        [forged_low_risk_path],
        gate_catalog=_catalog(),
    )

    assert plan.risk_level is RiskLevel.CRITICAL
    assert plan.layers >= frozenset(
        {
            Layer.GUIDANCE_DOCS,
            Layer.UI_BEHAVIOR,
            Layer.APPLICATION_SERVICE,
        }
    )
    assert "path:application-service" in plan.applied_rule_ids


def test_product_pr_always_selects_complete_regression_but_docs_only_does_not() -> None:
    product = plan_validation(
        _descriptor(claim=ClaimLevel.PRODUCT_PR),
        ["XBrainLab/backend/utils/logger.py"],
        gate_catalog=_catalog(),
    )
    docs = plan_validation(
        _descriptor(
            intent=ChangeIntent.DOCS,
            claim=ClaimLevel.PRODUCT_PR,
            layers=frozenset({Layer.GUIDANCE_DOCS}),
        ),
        ["docs/current.md", "AGENTS.md"],
        gate_catalog=_catalog(),
    )

    assert "complete-regression" in product.execution_ids
    assert "product-regression" in product.required_rule_ids
    assert "complete-regression" not in docs.execution_ids
    assert docs.required_rule_ids == (
        "docs",
        "guidance-contract",
        "identity",
    )


def test_expensive_gates_are_selected_only_for_applicable_layers_and_claims() -> None:
    ui_wiring = plan_validation(
        _descriptor(layers=frozenset({Layer.UI_BEHAVIOR})),
        ["XBrainLab/ui/controllers/training.py"],
        gate_catalog=_catalog(),
    )
    visible_ui = plan_validation(
        _descriptor(layers=frozenset({Layer.UI_PRESENTATION})),
        ["XBrainLab/ui/components/status_card.py"],
        gate_catalog=_catalog(),
    )
    mixed_runtime = plan_validation(
        _descriptor(
            layers=frozenset(
                {
                    Layer.DATA_SEMANTICS,
                    Layer.ASSISTANT,
                    Layer.MODEL_RUNTIME,
                    Layer.NATIVE_LIFECYCLE,
                }
            )
        ),
        ["XBrainLab/backend/dataset/split_audit.py"],
        gate_catalog=_catalog(),
    )

    assert "ui-behavior" not in ui_wiring.execution_ids
    assert "human-like-product" not in ui_wiring.execution_ids
    assert "complete-regression" not in ui_wiring.execution_ids
    assert "human-like-product" in visible_ui.execution_ids
    assert {
        "required-public-io",
        "assistant-security-suite",
        "native-lifecycle-tests",
    }.issubset(mixed_runtime.execution_ids)
    assert "granite-runtime" not in mixed_runtime.execution_ids


def test_bounded_ui_behavior_claim_escalates_from_focused_to_full_regression() -> None:
    checkpoint = plan_validation(
        _descriptor(layers=frozenset({Layer.UI_BEHAVIOR})),
        ["XBrainLab/ui/controllers/training.py"],
        gate_catalog=_catalog(),
    )
    bounded = plan_validation(
        _descriptor(
            claim=ClaimLevel.BOUNDED_COMPLETE,
            layers=frozenset({Layer.UI_BEHAVIOR}),
        ),
        ["XBrainLab/ui/controllers/training.py"],
        gate_catalog=_catalog(),
    )

    assert "complete-regression" not in checkpoint.execution_ids
    assert "complete-regression" in bounded.execution_ids


def test_product_pr_model_change_uses_automatable_contract_not_handoff_runtime() -> (
    None
):
    plan = plan_validation(
        _descriptor(
            claim=ClaimLevel.PRODUCT_PR,
            layers=frozenset({Layer.MODEL_RUNTIME}),
        ),
        ["XBrainLab/llm/core/model_catalog.py"],
        gate_catalog=_catalog(),
    )

    assert "assistant-security-suite" in plan.execution_ids
    assert "granite-runtime" not in plan.execution_ids
    assert "exact-model" not in plan.required_rule_ids


def test_handoff_and_higher_claims_require_the_complete_registered_inventory() -> None:
    catalog = _catalog()

    for claim_level in (ClaimLevel.HANDOFF, ClaimLevel.RELEASE, ClaimLevel.THESIS):
        plan = plan_validation(
            _descriptor(claim=claim_level, layers=frozenset({Layer.BACKEND_DOMAIN})),
            ["XBrainLab/backend/utils/logger.py"],
            gate_catalog=catalog,
        )

        assert set(plan.execution_ids) == set(catalog)


def test_mixed_change_unions_rules_and_deduplicates_the_gate_dag() -> None:
    catalog = _catalog()
    catalog["shared-product-workflow"] = {
        "tags": {"ui-visible", "data-semantics"},
        "dependencies": ("focused-contract",),
    }
    plan = plan_validation(
        _descriptor(
            claim=ClaimLevel.PRODUCT_PR,
            layers=frozenset({Layer.UI_PRESENTATION}),
        ),
        ["XBrainLab/backend/dataset/split_audit.py"],
        gate_catalog=catalog,
    )

    assert plan.execution_ids.count("shared-product-workflow") == 1
    shared = next(
        execution
        for execution in plan.executions
        if execution.gate_id == "shared-product-workflow"
    )
    assert shared.satisfies_rules == ("data-semantics", "ui-visible")
    positions = {gate_id: index for index, gate_id in enumerate(plan.execution_ids)}
    for execution in plan.executions:
        assert all(
            positions[dependency] < positions[execution.gate_id]
            for dependency in execution.dependencies
        )


def test_unknown_or_incomplete_catalog_remains_fail_closed() -> None:
    catalog = _catalog()
    catalog.pop("complete-regression")
    plan = plan_validation(
        _descriptor(claim=ClaimLevel.PRODUCT_PR),
        ["unowned/new_surface.xyz"],
        gate_catalog=catalog,
    )

    assert plan.risk_level is RiskLevel.CRITICAL
    assert plan.ready is False
    assert "product-regression" in plan.unresolved_rule_ids
    assert "unknown-change" in plan.unresolved_rule_ids
    assert plan.unknown_paths == ("unowned/new_surface.xyz",)


def test_unknown_path_remains_not_ready_even_when_a_broad_gate_can_run() -> None:
    plan = plan_validation(
        _descriptor(),
        ["unowned/new_surface.xyz"],
        gate_catalog=_catalog(),
    )

    assert "complete-regression" in plan.execution_ids
    assert plan.ready is False


def test_plan_without_changed_paths_is_not_executable() -> None:
    plan = plan_validation(
        _descriptor(layers=frozenset({Layer.BACKEND_DOMAIN})),
        [],
        gate_catalog=_catalog(),
    )

    assert plan.ready is False


@pytest.mark.parametrize(
    ("intent", "expected_rule", "minimum_risk"),
    [
        (ChangeIntent.PERFORMANCE, "performance-resource", RiskLevel.HIGH),
        (ChangeIntent.SECURITY, "security-privacy", RiskLevel.CRITICAL),
        (ChangeIntent.TESTS, "test-infrastructure", RiskLevel.HIGH),
        (ChangeIntent.CI, "ci-validation", RiskLevel.CRITICAL),
    ],
)
def test_change_intent_contributes_rules_and_risk_without_downgrading_paths(
    intent: ChangeIntent,
    expected_rule: str,
    minimum_risk: RiskLevel,
) -> None:
    catalog = _catalog()
    catalog["performance-resource"] = {
        "tags": {"performance-resource"},
        "dependencies": ("focused-contract",),
        "expensive": True,
    }
    plan = plan_validation(
        _descriptor(intent=intent),
        ["XBrainLab/backend/utils/logger.py"],
        gate_catalog=catalog,
    )

    assert expected_rule in plan.required_rule_ids
    assert plan.risk_level >= minimum_risk


def test_plan_and_receipt_have_stable_json_and_digest_roundtrips() -> None:
    descriptor = _descriptor(
        intent=ChangeIntent.FEATURE,
        claim=ClaimLevel.HANDOFF,
        layers=frozenset({Layer.UI_PRESENTATION}),
    )
    first = plan_validation(
        descriptor,
        ["XBrainLab/ui/components/status_card.py", "docs/current.md"],
        gate_catalog=_catalog(),
    )
    second = plan_validation(
        descriptor,
        ["docs/current.md", "XBrainLab/ui/components/status_card.py"],
        gate_catalog=dict(reversed(tuple(_catalog().items()))),
    )

    assert ChangeDescriptor.from_json(descriptor.to_json()) == descriptor
    assert (
        descriptor.digest() == ChangeDescriptor.from_json(descriptor.to_json()).digest()
    )
    assert first == second
    assert ValidationPlan.from_json(first.to_json()) == first
    assert first.digest() == second.digest()

    receipt = ValidationReceipt(
        plan_digest=first.digest(),
        source_sha="a" * 40,
        completed_gate_ids=first.execution_ids,
        failed_gate_ids=(),
        evidence_digests=(("handoff-dashboard", "b" * 64),),
    )
    assert ValidationReceipt.from_json(receipt.to_json()) == receipt
    assert receipt.digest() == ValidationReceipt.from_json(receipt.to_json()).digest()


def test_receipt_preserves_execution_order_and_rejects_duplicate_gate_ids() -> None:
    receipt = ValidationReceipt(
        plan_digest="a" * 64,
        source_sha="b" * 40,
        completed_gate_ids=("z-last-by-name", "a-first-by-name"),
        failed_gate_ids=("a-first-by-name",),
    )

    assert receipt.completed_gate_ids == ("z-last-by-name", "a-first-by-name")
    assert receipt.failed_gate_ids == ("a-first-by-name",)
    with pytest.raises(ValueError, match="repeats completed"):
        ValidationReceipt(
            plan_digest="a" * 64,
            source_sha="b" * 40,
            completed_gate_ids=("same", "same"),
        )
    with pytest.raises(ValueError, match="repeats evidence"):
        ValidationReceipt(
            plan_digest="a" * 64,
            source_sha="b" * 40,
            completed_gate_ids=("same",),
            evidence_digests=(("same", "c" * 64), ("same", "c" * 64)),
        )


def test_plan_can_be_bound_to_exact_source_and_change_set() -> None:
    unbound = plan_validation(
        _descriptor(layers=frozenset({Layer.BACKEND_DOMAIN})),
        ["XBrainLab/backend/utils/logger.py"],
        gate_catalog=_catalog(),
    )
    bound = bind_validation_plan(
        unbound,
        source_sha="a" * 40,
        base_sha="b" * 40,
        target_sha="c" * 40,
    )

    assert unbound.source_sha is None
    assert bound.source_sha == "a" * 40
    assert bound.base_sha == "b" * 40
    assert bound.target_sha == "c" * 40
    assert bound.change_set_digest is not None
    assert len(bound.change_set_digest) == 64
    assert bound.digest() != unbound.digest()
    assert ValidationPlan.from_json(bound.to_json()) == bound


def test_authorized_target_is_part_of_the_plan_digest() -> None:
    unbound = plan_validation(
        _descriptor(layers=frozenset({Layer.BACKEND_DOMAIN})),
        ["XBrainLab/backend/utils/logger.py"],
        gate_catalog=_catalog(),
    )
    first = bind_validation_plan(
        unbound,
        source_sha="a" * 40,
        base_sha="b" * 40,
        target_sha="c" * 40,
    )
    second = bind_validation_plan(
        unbound,
        source_sha="a" * 40,
        base_sha="b" * 40,
        target_sha="d" * 40,
    )

    assert first.digest() != second.digest()


def test_explicit_blank_authorized_target_does_not_fall_back_to_merge_base() -> None:
    unbound = plan_validation(
        _descriptor(layers=frozenset({Layer.BACKEND_DOMAIN})),
        ["XBrainLab/backend/utils/logger.py"],
        gate_catalog=_catalog(),
    )

    with pytest.raises(ValueError, match="plan target SHA"):
        bind_validation_plan(
            unbound,
            source_sha="a" * 40,
            base_sha="b" * 40,
            target_sha="",
        )


def test_binding_requires_an_explicit_authorized_target_tip() -> None:
    unbound = plan_validation(
        _descriptor(layers=frozenset({Layer.BACKEND_DOMAIN})),
        ["XBrainLab/backend/utils/logger.py"],
        gate_catalog=_catalog(),
    )

    with pytest.raises(TypeError, match="target_sha"):
        bind_validation_plan(  # type: ignore[call-arg]
            unbound,
            source_sha="a" * 40,
            base_sha="b" * 40,
        )


def test_receipt_verdict_requires_exact_plan_coverage_and_evidence() -> None:
    plan = plan_validation(
        _descriptor(layers=frozenset({Layer.BACKEND_DOMAIN})),
        ["XBrainLab/backend/utils/logger.py"],
        gate_catalog=_catalog(),
    )
    evidence = tuple((gate_id, "b" * 64) for gate_id in plan.execution_ids)
    complete = ValidationReceipt(
        plan_digest=plan.digest(),
        source_sha="a" * 40,
        completed_gate_ids=plan.execution_ids,
        evidence_digests=evidence,
    )
    missing = ValidationReceipt(
        plan_digest=plan.digest(),
        source_sha="a" * 40,
        completed_gate_ids=plan.execution_ids[:-1],
        evidence_digests=evidence[:-1],
    )

    assert evaluate_validation_receipt(plan, complete).status is VerdictStatus.PASSED
    missing_verdict = evaluate_validation_receipt(plan, missing)
    assert missing_verdict.status is VerdictStatus.BLOCKED
    assert missing_verdict.missing_gate_ids == (plan.execution_ids[-1],)


def test_bound_plan_receipt_requires_the_same_source_sha() -> None:
    plan = plan_validation(
        _descriptor(layers=frozenset({Layer.BACKEND_DOMAIN})),
        ["XBrainLab/backend/utils/logger.py"],
        gate_catalog=_catalog(),
    )
    plan = bind_validation_plan(
        plan,
        source_sha="a" * 40,
        base_sha="b" * 40,
        target_sha="b" * 40,
    )
    receipt = ValidationReceipt(
        plan_digest=plan.digest(),
        source_sha="c" * 40,
        completed_gate_ids=plan.execution_ids,
        evidence_digests=tuple((gate_id, "d" * 64) for gate_id in plan.execution_ids),
    )

    verdict = evaluate_validation_receipt(plan, receipt)

    assert verdict.status is VerdictStatus.BLOCKED
    assert "source-sha-mismatch" in verdict.reasons


def test_failed_gate_produces_failed_verdict_not_a_partial_pass() -> None:
    plan = plan_validation(
        _descriptor(layers=frozenset({Layer.BACKEND_DOMAIN})),
        ["XBrainLab/backend/utils/logger.py"],
        gate_catalog=_catalog(),
    )
    failed_gate = plan.execution_ids[-1]
    receipt = ValidationReceipt(
        plan_digest=plan.digest(),
        source_sha="a" * 40,
        completed_gate_ids=plan.execution_ids,
        failed_gate_ids=(failed_gate,),
        evidence_digests=tuple((gate_id, "b" * 64) for gate_id in plan.execution_ids),
    )

    verdict = evaluate_validation_receipt(plan, receipt)

    assert verdict.status is VerdictStatus.FAILED
    assert verdict.failed_gate_ids == (failed_gate,)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("plan_digest", "not-a-digest"),
        ("source_sha", "short"),
    ],
)
def test_receipt_rejects_invalid_lineage_hashes(field: str, value: str) -> None:
    kwargs = {
        "plan_digest": "a" * 64,
        "source_sha": "b" * 40,
        "completed_gate_ids": ("ruff-check",),
        "evidence_digests": (("ruff-check", "c" * 64),),
    }
    kwargs[field] = value

    with pytest.raises(ValueError, match=r"digest|SHA"):
        ValidationReceipt(**kwargs)  # type: ignore[arg-type]


def test_invalid_catalog_cycle_is_rejected_instead_of_reordered_arbitrarily() -> None:
    catalog = _catalog()
    catalog["git-diff-check"] = {
        "tags": {"identity"},
        "dependencies": ("ruff-check",),
    }

    with pytest.raises(ValueError, match="cycle"):
        plan_validation(
            _descriptor(),
            ["XBrainLab/backend/utils/logger.py"],
            gate_catalog=catalog,
        )
