from __future__ import annotations

import json

import pytest

from scripts.dev.validation_control_plane import (
    ChangeIntent,
    ClaimLevel,
    Layer,
    RiskLevel,
)
from scripts.dev.validation_pr_declaration import descriptor_from_github_event


def test_pull_request_requires_explicit_validation_intent(tmp_path) -> None:
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"body": "## Summary\nFix it"}}))

    with pytest.raises(ValueError, match="Validation-Intent"):
        descriptor_from_github_event("pull_request", event)


def test_pull_request_declaration_builds_monotonic_descriptor(tmp_path) -> None:
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps(
            {
                "pull_request": {
                    "body": """
## Validation declaration
Validation-Intent: performance
Validation-Risk: high
Validation-Layers: backend-domain, native-lifecycle
Validation-Rules: performance-resource
"""
                }
            }
        )
    )

    descriptor = descriptor_from_github_event("pull_request", event)

    assert descriptor.intent is ChangeIntent.PERFORMANCE
    assert descriptor.claim_level is ClaimLevel.PRODUCT_PR
    assert descriptor.declared_risk is RiskLevel.HIGH
    assert descriptor.declared_layers == frozenset(
        {Layer.BACKEND_DOMAIN, Layer.NATIVE_LIFECYCLE}
    )
    assert descriptor.required_rule_ids == frozenset({"performance-resource"})


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ("Validation-Intent: made-up", "intent"),
        ("Validation-Intent: bug-fix\nValidation-Risk: tiny", "risk"),
        ("Validation-Intent: bug-fix\nValidation-Layers: backend-domain,wat", "layer"),
        (
            "Validation-Intent: bug-fix\nValidation-Intent: feature",
            "duplicate",
        ),
    ],
)
def test_invalid_or_ambiguous_declarations_fail_closed(
    tmp_path,
    line: str,
    message: str,
) -> None:
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"body": line}}))

    with pytest.raises(ValueError, match=message):
        descriptor_from_github_event("pull_request", event)


def test_push_uses_conservative_ci_intent_without_pr_body(tmp_path) -> None:
    event = tmp_path / "event.json"
    event.write_text("{}")

    descriptor = descriptor_from_github_event("push", event)

    assert descriptor.intent is ChangeIntent.CI
    assert descriptor.claim_level is ClaimLevel.PRODUCT_PR
    assert descriptor.declared_risk is RiskLevel.CRITICAL
