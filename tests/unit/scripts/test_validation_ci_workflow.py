from __future__ import annotations

from pathlib import Path

import yaml

from scripts.dev.ci_gate_ownership import CI_GATE_OWNERS
from scripts.dev.handoff_gate_spec import HANDOFF_GATE_SPECS
from scripts.dev.validation_ci_plan import build_ci_validation_plan
from scripts.dev.validation_control_plane import (
    ChangeDescriptor,
    ChangeIntent,
    ClaimLevel,
    Layer,
    bind_validation_plan,
    plan_validation,
)
from scripts.dev.validation_gate_catalog import (
    CONTROL_PLANE_RULE_TAGS,
    HANDOFF_VALIDATION_GATE_CATALOG,
)

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"
DOCS_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "docs-pages.yml"


def _workflow() -> tuple[str, dict[str, object]]:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    return text, yaml.safe_load(text)


def test_ci_verdict_is_receipt_backed_and_explicitly_capability_only() -> None:
    text, workflow = _workflow()
    jobs = workflow["jobs"]

    assert "claim-verdict" not in jobs
    assert jobs["ci-capability-verdict"]["name"] == "CI Capability Verdict"
    assert "run_validation_ci_owner.py verify" in text
    assert "--receipt-dir build/ci-owner-receipts" in text
    assert "validation claim passed" not in text
    assert "Validation Claim Verdict" not in text


def test_docs_pages_does_not_duplicate_pull_request_portal_validation() -> None:
    text = DOCS_WORKFLOW_PATH.read_text(encoding="utf-8")
    trigger_block = text.split("permissions:", maxsplit=1)[0]

    assert "pull_request:" not in trigger_block
    assert "push:" in trigger_block
    assert "workflow_dispatch:" in trigger_block


def test_ci_owner_dependencies_and_exact_head_are_fail_closed() -> None:
    text, workflow = _workflow()
    jobs = workflow["jobs"]

    assert jobs["linux-shard"]["needs"] == ["validation_plan", "registered-gates"]
    assert jobs["risk-gates"]["needs"] == [
        "validation_plan",
        "registered-gates",
        "docs-validation",
        "linux-test",
    ]
    assert "ref: ${{ github.event.pull_request.head.sha || github.sha }}" in text
    assert "validation_pr_declaration.py" in text
    assert '--event-path "$GITHUB_EVENT_PATH"' in text
    assert '[[ "$SOURCE_SHA" == "$EXPECTED_SHA" ]]' in text
    assert "types: [opened, synchronize, reopened, edited]" in text
    assert "target_sha: ${{ steps.base.outputs.target_sha }}" in text
    assert "TARGET_SHA: ${{ needs.validation_plan.outputs.target_sha }}" in text
    assert 'failures+=("target-sha:mismatch")' in text
    assert 'failures+=("first-push-target:unavailable")' in text
    assert "git rev-list --max-parents=0 HEAD" not in text
    assert (
        text.count('--target-sha "${{ needs.validation_plan.outputs.target_sha }}"')
        == 5
    )


def test_public_and_other_risk_gates_execute_the_registered_owner_only() -> None:
    text, workflow = _workflow()
    risk = workflow["jobs"]["risk-gates"]

    assert risk["strategy"]["matrix"]["owner"] == (
        "${{ fromJSON(needs.validation_plan.outputs.risk_owners) }}"
    )
    assert "matrix.owner == 'public-data'" in text
    assert "poetry run -- python scripts/dev/run_validation_ci_owner.py run" in text
    assert "scripts/dev/fetch_public_eeg_fixtures.py" not in text
    assert "tests/integration/io/test_public_bids_fixture.py" not in text
    condition = risk["if"]
    assert "outputs.run_product != 'true'" in condition
    assert "outputs.run_lint != 'true'" in condition
    assert "outputs.run_focused != 'true'" in condition
    assert "outputs.run_docs != 'true'" in condition
    assert "docs-validation.result == 'success'" in condition


def test_docs_selected_gates_use_registry_runner_not_blanket_recording() -> None:
    text, workflow = _workflow()
    docs = workflow["jobs"]["docs-validation"]
    rendered = yaml.safe_dump(docs)

    assert "--owner docs" in rendered
    assert "run_validation_ci_owner.py run" in rendered
    assert "run_validation_ci_owner.py record" not in rendered
    assert "poetry install --only docs,test,dev --no-root" in text


def test_registry_receipts_and_dossiers_are_uploaded_and_downloaded_separately() -> (
    None
):
    text, workflow = _workflow()
    jobs = workflow["jobs"]
    docs_upload = next(
        step
        for step in jobs["docs-validation"]["steps"]
        if step.get("name") == "Upload documentation owner receipt"
    )
    risk_receipt_upload = next(
        step
        for step in jobs["risk-gates"]["steps"]
        if step.get("name") == "Upload risk owner receipt"
    )

    assert docs_upload["with"]["path"] == "build/ci-owner-receipts/docs.json"
    assert risk_receipt_upload["with"]["path"] == (
        "build/ci-owner-receipts/${{ matrix.owner }}.json"
    )
    assert "ci-registry-evidence-registered-" in text
    assert "ci-registry-evidence-docs-" in text
    assert "ci-registry-evidence-${{ matrix.owner }}-" in text
    assert "--registry-evidence-dir build/downloaded-ci-registry-evidence" in text
    assert "name: test-results-ubuntu-latest-py3.11" in text


def test_risk_owner_budget_covers_registered_sequential_timeouts() -> None:
    _text, workflow = _workflow()
    budget_seconds = workflow["jobs"]["risk-gates"]["timeout-minutes"] * 60
    setup_margin_seconds = 30 * 60

    for owner in ("ui", "native", "public-data"):
        registered_seconds = sum(
            HANDOFF_GATE_SPECS[gate_id].timeout_seconds
            for gate_id, gate_owner in CI_GATE_OWNERS.items()
            if gate_owner == owner
        )
        assert registered_seconds + setup_margin_seconds <= budget_seconds


def test_all_semantic_rule_upgrades_are_owned_or_fail_closed_as_local_only() -> None:
    supported_ci_owners = {
        "docs",
        "focused",
        "lint",
        "native",
        "plan",
        "product",
        "public-data",
        "ui",
    }
    cases = (
        ("docs/current.md", Layer.GUIDANCE_DOCS),
        ("XBrainLab/backend/utils/logger.py", Layer.BACKEND_DOMAIN),
    )

    for path, layer in cases:
        for rule_id in sorted(CONTROL_PLANE_RULE_TAGS):
            plan = plan_validation(
                ChangeDescriptor(
                    intent=ChangeIntent.BUG_FIX,
                    claim_level=ClaimLevel.PRODUCT_PR,
                    declared_layers=frozenset({layer}),
                    required_rule_ids=frozenset({rule_id}),
                ),
                [path],
                gate_catalog=HANDOFF_VALIDATION_GATE_CATALOG,
            )
            plan = bind_validation_plan(
                plan,
                source_sha="a" * 40,
                base_sha="b" * 40,
                target_sha="b" * 40,
            )
            unowned = set(plan.execution_ids).difference(CI_GATE_OWNERS)
            if unowned:
                try:
                    build_ci_validation_plan(plan, source_sha="a" * 40)
                except ValueError as error:
                    assert "no CI execution owner" in str(error)
                else:
                    raise AssertionError(f"unowned gates were accepted: {unowned}")
                continue
            ci_plan = build_ci_validation_plan(plan, source_sha="a" * 40)
            assert set(ci_plan.required_owners) <= supported_ci_owners


def test_linux_aggregate_does_not_start_after_missing_or_failed_shards() -> None:
    _text, workflow = _workflow()

    assert workflow["jobs"]["linux-test"]["if"] == (
        "always() && needs.validation_plan.outputs.run_product == 'true' && "
        "needs.linux-shard.result == 'success'"
    )


def test_final_verdict_runs_on_failed_dependencies_but_not_cancelled_workflows() -> (
    None
):
    _text, workflow = _workflow()

    assert workflow["jobs"]["ci-capability-verdict"]["if"] == (
        "always() && !cancelled()"
    )


def test_workflow_uses_the_v2_cancellation_protocol_group() -> None:
    _text, workflow = _workflow()

    assert workflow["concurrency"]["group"] == (
        "${{ github.workflow }}-validation-plan-v2-${{ github.ref }}"
    )
