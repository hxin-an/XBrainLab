"""Contract tests for typed resource preflight views and one-shot challenges."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from XBrainLab.backend.application.resource_preflight import (
    RESOURCE_PREFLIGHT_SCHEMA_VERSION,
    ResourceConfirmationChallenge,
    ResourcePreflightContractError,
    ResourcePreflightView,
)
from XBrainLab.backend.application.resource_receipt import (
    ResourceReceiptAuthority,
)


def _challenge_ids() -> Iterator[str]:
    yield from ("challenge-1", "challenge-2", "challenge-3")


@pytest.mark.parametrize(
    ("risk_level", "requires_confirmation"),
    [
        ("safe", False),
        ("warning", True),
        ("blocking", False),
        ("unknown", True),
    ],
)
def test_preflight_view_parses_every_resource_risk(
    risk_level: str,
    requires_confirmation: bool,
) -> None:
    view = ResourcePreflightView.from_diagnostics(
        {
            "resource_preflight": {
                "schema_version": RESOURCE_PREFLIGHT_SCHEMA_VERSION,
                "risk_level": risk_level,
                "requires_confirmation": requires_confirmation,
                "message": f"Resource risk is {risk_level}.",
                "issues": ["blocked"] if risk_level == "blocking" else [],
                "warnings": ["warning"] if risk_level == "warning" else [],
                "unknowns": ["unknown"] if risk_level == "unknown" else [],
                "required_memory_bytes": 512,
                "available_memory_bytes": 1_024,
                "dataset_ram_risk_level": risk_level,
                "vram_risk_level": risk_level,
                "vram": {
                    "risk_level": risk_level,
                    "required_memory_bytes": 256,
                    "available_memory_bytes": 2_048,
                    "gpu_name": "Test GPU",
                },
            }
        }
    )

    assert view is not None
    assert view.schema_version == RESOURCE_PREFLIGHT_SCHEMA_VERSION
    assert view.risk_level == risk_level
    assert view.requires_confirmation is requires_confirmation
    assert view.dataset_ram.risk_level == risk_level
    assert view.dataset_ram.required_memory_bytes == 512
    assert view.vram.risk_level == risk_level
    assert view.vram.available_memory_bytes == 2_048
    assert view.vram.gpu_name == "Test GPU"


def test_preflight_view_round_trip_owns_challenge_serialization() -> None:
    challenge = ResourceConfirmationChallenge(
        challenge_id="challenge-1",
        command_name="start_training",
        scope_fingerprint="scope-1",
        preflight_fingerprint="preflight-1",
        configuration_fingerprint="configuration-1",
        ttl_seconds=120.0,
    )
    view = ResourcePreflightView.create(
        risk_level="warning",
        requires_confirmation=True,
        message="Training is close to available GPU memory.",
        warnings=("Training is close to available GPU memory.",),
        details={
            "model_name": "EEGNet",
            "training_batch_size": 64,
            "estimated_gpu_batch_working_set_bytes": 4_096,
            "available_vram_bytes": 8_192,
        },
        challenge=challenge,
    )

    diagnostics = {"resource_preflight": view.to_diagnostics()}
    restored = ResourcePreflightView.from_diagnostics(diagnostics)

    assert restored == view
    assert diagnostics["resource_preflight"]["schema_version"] == 1
    assert diagnostics["resource_preflight"]["confirmation_challenge"] == {
        "schema_version": 1,
        "challenge_id": "challenge-1",
        "command_name": "start_training",
        "scope_fingerprint": "scope-1",
        "ttl_seconds": 120.0,
        "candidate_id": None,
        "configuration_fingerprint": "configuration-1",
        "preflight_fingerprint": "preflight-1",
    }
    assert restored is not None
    assert restored.challenge == challenge


def test_preflight_view_rejects_unknown_schema_version() -> None:
    with pytest.raises(ResourcePreflightContractError, match="schema version"):
        ResourcePreflightView.from_diagnostics(
            {
                "resource_preflight": {
                    "schema_version": 999,
                    "risk_level": "safe",
                    "requires_confirmation": False,
                    "message": "Safe",
                }
            }
        )


@pytest.mark.parametrize(
    "diagnostics",
    [
        {"resource_preflight": "not-a-mapping"},
        {
            "resource_preflight": {
                "schema_version": RESOURCE_PREFLIGHT_SCHEMA_VERSION,
                "risk_level": "danger",
                "requires_confirmation": True,
                "message": "Invalid risk value.",
            }
        },
        {
            "resource_preflight": {
                "schema_version": RESOURCE_PREFLIGHT_SCHEMA_VERSION,
                "risk_level": "warning",
                "requires_confirmation": "false",
                "message": "Invalid boolean value.",
            }
        },
    ],
)
def test_preflight_view_rejects_malformed_contract_values(
    diagnostics: dict[str, object],
) -> None:
    with pytest.raises(ResourcePreflightContractError):
        ResourcePreflightView.from_diagnostics(diagnostics)


def test_receipt_authority_consumes_one_exact_scope_once() -> None:
    ids = _challenge_ids()
    authority = ResourceReceiptAuthority[str](
        command_name="apply_interpretation",
        ttl_seconds=120.0,
        challenge_id_factory=lambda: next(ids),
    )
    challenge = authority.issue(
        scope_fingerprint="scope-a",
        payload="warning-preflight",
        candidate_id="candidate-a",
        preflight_fingerprint="preflight-a",
    )

    consumed = authority.consume(
        challenge.challenge_id,
        scope_fingerprint="scope-a",
        candidate_id="candidate-a",
        preflight_fingerprint="preflight-a",
    )

    assert consumed is not None
    assert consumed.payload == "warning-preflight"
    assert consumed.challenge == challenge
    assert (
        authority.consume(
            challenge.challenge_id,
            scope_fingerprint="scope-a",
            candidate_id="candidate-a",
            preflight_fingerprint="preflight-a",
        )
        is None
    )


def test_receipt_authority_rejects_and_discards_mismatched_scope() -> None:
    ids = _challenge_ids()
    authority = ResourceReceiptAuthority[str](
        command_name="start_training",
        ttl_seconds=120.0,
        challenge_id_factory=lambda: next(ids),
    )
    challenge = authority.issue(
        scope_fingerprint="scope-a",
        payload="warning-preflight",
        configuration_fingerprint="config-a",
        preflight_fingerprint="preflight-a",
    )

    assert (
        authority.consume(
            challenge.challenge_id,
            scope_fingerprint="scope-b",
            configuration_fingerprint="config-a",
            preflight_fingerprint="preflight-a",
        )
        is None
    )
    assert (
        authority.consume(
            challenge.challenge_id,
            scope_fingerprint="scope-a",
            configuration_fingerprint="config-a",
            preflight_fingerprint="preflight-a",
        )
        is None
    )


def test_receipt_authority_never_overwrites_a_challenge_id_collision() -> None:
    authority = ResourceReceiptAuthority[str](
        command_name="start_training",
        challenge_id_factory=lambda: "duplicate-challenge",
    )
    authority.issue(scope_fingerprint="scope-a", payload="first")

    with pytest.raises(RuntimeError, match="challenge ID collision"):
        authority.issue(scope_fingerprint="scope-b", payload="second")

    original = authority.consume(
        "duplicate-challenge",
        scope_fingerprint="scope-a",
    )
    assert original is not None
    assert original.payload == "first"


def test_receipt_authority_rejects_expired_challenge() -> None:
    now = 10.0
    ids = _challenge_ids()
    authority = ResourceReceiptAuthority[str](
        command_name="start_training",
        ttl_seconds=5.0,
        clock=lambda: now,
        challenge_id_factory=lambda: next(ids),
    )
    challenge = authority.issue(
        scope_fingerprint="scope-a",
        payload="warning-preflight",
        preflight_fingerprint="preflight-a",
    )
    now = 15.0

    assert (
        authority.consume(
            challenge.challenge_id,
            scope_fingerprint="scope-a",
            preflight_fingerprint="preflight-a",
        )
        is None
    )


def test_import_and_training_challenges_share_one_wire_contract() -> None:
    ids = _challenge_ids()
    import_authority = ResourceReceiptAuthority[str](
        command_name="apply_interpretation",
        ttl_seconds=120.0,
        challenge_id_factory=lambda: next(ids),
    )
    training_authority = ResourceReceiptAuthority[str](
        command_name="start_training",
        ttl_seconds=120.0,
        challenge_id_factory=lambda: next(ids),
    )

    import_challenge = import_authority.issue(
        scope_fingerprint="import-scope",
        payload="import-preflight",
        candidate_id="candidate-1",
        preflight_fingerprint="import-preflight-fingerprint",
    )
    training_challenge = training_authority.issue(
        scope_fingerprint="training-scope",
        payload="training-preflight",
        configuration_fingerprint="training-config",
        preflight_fingerprint="training-preflight-fingerprint",
    )

    assert import_challenge.to_diagnostics().keys() == (
        training_challenge.to_diagnostics().keys()
    )
    assert import_challenge.command_name == "apply_interpretation"
    assert training_challenge.command_name == "start_training"
