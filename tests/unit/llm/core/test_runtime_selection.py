"""Behavior tests for the single assistant runtime selection owner."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.runtime_selection import (
    AssistantRuntimeBackend,
    AssistantRuntimeLaunchResolver,
    AssistantRuntimeSelectionFailureCode,
    AssistantRuntimeSelectionOutcome,
)


def _runtime_config(
    monkeypatch: pytest.MonkeyPatch,
    *,
    model_id: str | None = None,
    ready_models: set[str] | None = None,
) -> LLMConfig:
    config = LLMConfig(
        model_name=model_id or LLMConfig.default_local_model_id(),
    )
    ready = ready_models or {config.model_name}
    monkeypatch.setattr(
        config,
        "local_backend_ready",
        lambda candidate=None: (candidate or config.model_name) in ready,
    )
    monkeypatch.setattr(
        config,
        "local_backend_status_message",
        lambda candidate=None: (
            "Local runtime ready."
            if (candidate or config.model_name) in ready
            else f"Model cache not found for {candidate or config.model_name}."
        ),
    )
    monkeypatch.setattr(config, "local_backend_cpu_fallback_reason", lambda: None)
    return config


def test_resolver_freezes_the_exact_launch_selection_and_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = LLMConfig.default_local_model_id()
    config = _runtime_config(monkeypatch, model_id=primary)
    config.temperature = 0.25

    resolution = AssistantRuntimeLaunchResolver().resolve(config)

    assert resolution.available is True
    assert resolution.failure is None
    spec = resolution.launch_spec
    assert spec is not None
    assert spec.backend is AssistantRuntimeBackend.LOCAL
    assert spec.requested_model_id == primary
    assert spec.model_id == primary
    assert spec.outcome is AssistantRuntimeSelectionOutcome.EXACT
    assert spec.fallback_used is False

    config.model_name = "microsoft/Phi-4-mini-instruct"
    config.temperature = 1.75

    launch_config = spec.build_config()
    assert launch_config.model_name == primary
    assert launch_config.temperature == 0.25
    with pytest.raises(FrozenInstanceError):
        setattr(  # noqa: B010 - exercise frozen guard.
            spec,
            "model_id",
            "microsoft/Phi-4-mini-instruct",
        )


@pytest.mark.parametrize(
    "model_id",
    [
        "ibm-granite/granite-4.0-micro",
        "ibm-granite/granite-3.3-2b-instruct",
    ],
)
def test_resolver_accepts_each_catalog_model_exactly_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
    model_id: str,
) -> None:
    config = _runtime_config(monkeypatch, model_id=model_id)

    resolution = AssistantRuntimeLaunchResolver().resolve(config)

    assert resolution.launch_spec is not None
    assert resolution.launch_spec.requested_model_id == model_id
    assert resolution.launch_spec.model_id == model_id
    assert resolution.launch_spec.outcome is AssistantRuntimeSelectionOutcome.EXACT
    assert resolution.launch_spec.fallback_used is False


def test_resolver_makes_cuda_to_cpu_fallback_explicit_before_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _runtime_config(monkeypatch)
    config.device = "cuda:0"
    config.load_in_4bit = True
    monkeypatch.setattr(
        config,
        "local_backend_cpu_fallback_reason",
        lambda: "CUDA is not available",
    )
    monkeypatch.setattr(
        config,
        "local_backend_status_message",
        lambda candidate=None: (
            "Local runtime ready. GPU execution is unavailable in this "
            "environment, so startup will fall back to CPU and disable "
            "4-bit loading."
        ),
    )

    resolution = AssistantRuntimeLaunchResolver().resolve(config)

    assert resolution.launch_spec is not None
    spec = resolution.launch_spec
    assert spec.settings.device == "cpu"
    assert spec.settings.load_in_4bit is False
    assert spec.execution_device == "cpu"
    assert spec.device_fallback_reason == "CUDA is not available"
    assert config.device == "cuda:0"
    assert config.load_in_4bit is True


def test_persisted_first_run_notice_is_not_copied_into_engine_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _runtime_config(monkeypatch)
    config.local_runtime_notice_acknowledged = True

    resolution = AssistantRuntimeLaunchResolver().resolve(config)

    assert resolution.launch_spec is not None
    launch_config = resolution.launch_spec.build_config()
    assert config.local_runtime_notice_acknowledged is True
    assert launch_config.local_runtime_notice_acknowledged is False
    assert not hasattr(
        resolution.launch_spec.settings,
        "local_runtime_notice_acknowledged",
    )


def test_resolver_fails_visibly_without_checking_catalog_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = LLMConfig.default_local_model_id()
    unsupported_cached_model = "unsupported/cache-only-model"
    config = _runtime_config(
        monkeypatch,
        model_id=primary,
        ready_models={unsupported_cached_model},
    )
    readiness_calls: list[str | None] = []
    status_calls: list[str | None] = []
    monkeypatch.setattr(
        config,
        "local_backend_ready",
        lambda candidate=None: (
            readiness_calls.append(candidate) or candidate == unsupported_cached_model
        ),
    )
    monkeypatch.setattr(
        config,
        "local_backend_status_message",
        lambda candidate=None: (
            status_calls.append(candidate)
            or f"Model cache not found for {candidate or config.model_name}."
        ),
    )

    resolution = AssistantRuntimeLaunchResolver().resolve(config)

    assert resolution.available is False
    assert resolution.launch_spec is None
    assert resolution.failure is not None
    assert resolution.failure.code is (
        AssistantRuntimeSelectionFailureCode.RUNTIME_UNAVAILABLE
    )
    assert resolution.failure.requested_model_id == primary
    assert primary in resolution.failure.message
    assert unsupported_cached_model not in resolution.failure.message
    assert readiness_calls == [primary]
    assert status_calls == [primary]


@pytest.mark.parametrize(
    "legacy_model",
    [
        "microsoft/Phi-4-mini-instruct",
        "microsoft/Phi-3.5-mini-instruct",
    ],
)
def test_resolver_rejects_retired_phi_models_with_migration_message(
    monkeypatch: pytest.MonkeyPatch,
    legacy_model: str,
) -> None:
    config = _runtime_config(
        monkeypatch,
        model_id=legacy_model,
        ready_models={legacy_model},
    )

    resolution = AssistantRuntimeLaunchResolver().resolve(config)

    assert resolution.available is False
    assert resolution.launch_spec is None
    assert resolution.failure is not None
    assert resolution.failure.code is AssistantRuntimeSelectionFailureCode.UNKNOWN_MODEL
    assert resolution.failure.requested_model_id == legacy_model
    assert "no longer available" in resolution.failure.message
    assert LLMConfig.default_local_model_id() in resolution.failure.message


@pytest.mark.parametrize("backend_id", ["", "gemini", "unknown-runtime"])
def test_resolver_typed_fails_unknown_backend_ids_without_defaulting(
    monkeypatch: pytest.MonkeyPatch,
    backend_id: str,
) -> None:
    config = _runtime_config(monkeypatch)

    resolution = AssistantRuntimeLaunchResolver().resolve(
        config,
        requested_backend_id=backend_id,
    )

    assert resolution.available is False
    assert resolution.launch_spec is None
    assert resolution.failure is not None
    assert resolution.failure.code is (
        AssistantRuntimeSelectionFailureCode.UNKNOWN_BACKEND
    )
    assert resolution.failure.requested_backend_id == backend_id


@pytest.mark.parametrize("model_id", ["", "gpt-4o", "unknown/model"])
def test_resolver_typed_fails_unknown_model_ids_before_readiness(
    monkeypatch: pytest.MonkeyPatch,
    model_id: str,
) -> None:
    config = _runtime_config(monkeypatch)
    readiness_calls: list[str | None] = []
    monkeypatch.setattr(
        config,
        "local_backend_ready",
        lambda candidate=None: readiness_calls.append(candidate) or True,
    )

    resolution = AssistantRuntimeLaunchResolver().resolve(
        config,
        requested_model_id=model_id,
    )

    assert resolution.available is False
    assert resolution.launch_spec is None
    assert resolution.failure is not None
    assert resolution.failure.code is (
        AssistantRuntimeSelectionFailureCode.UNKNOWN_MODEL
    )
    assert resolution.failure.requested_model_id == model_id
    assert readiness_calls == []


def test_resolver_typed_fails_a_disabled_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _runtime_config(monkeypatch)
    config.local_model_enabled = False

    resolution = AssistantRuntimeLaunchResolver().resolve(config)

    assert resolution.available is False
    assert resolution.failure is not None
    assert resolution.failure.code is (
        AssistantRuntimeSelectionFailureCode.RUNTIME_DISABLED
    )
