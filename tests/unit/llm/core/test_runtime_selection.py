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
    return config


def test_resolver_freezes_the_exact_launch_selection_and_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = LLMConfig.default_local_model_id()
    alternate = LLMConfig.fallback_local_model_id()
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

    config.model_name = alternate
    config.temperature = 1.75

    launch_config = spec.build_config()
    assert launch_config.model_name == primary
    assert launch_config.temperature == 0.25
    with pytest.raises(FrozenInstanceError):
        setattr(spec, "model_id", alternate)  # noqa: B010 - exercise frozen guard.


def test_resolver_returns_an_explicit_visible_fallback_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = LLMConfig.default_local_model_id()
    fallback = LLMConfig.fallback_local_model_id()
    config = _runtime_config(
        monkeypatch,
        model_id=primary,
        ready_models={fallback},
    )

    resolution = AssistantRuntimeLaunchResolver().resolve(config)

    assert resolution.available is True
    spec = resolution.launch_spec
    assert spec is not None
    assert spec.requested_model_id == primary
    assert spec.model_id == fallback
    assert spec.outcome is AssistantRuntimeSelectionOutcome.FALLBACK
    assert spec.fallback_used is True
    assert primary in spec.selection_detail
    assert fallback in spec.selection_detail
    assert spec.build_config().model_name == fallback


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
def test_resolver_typed_fails_unknown_model_ids_before_readiness_or_fallback(
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
