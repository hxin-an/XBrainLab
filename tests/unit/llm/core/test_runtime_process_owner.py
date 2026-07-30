"""Deterministic contract tests for the owned local-model process."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator

import pytest

from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.generation import GenerationProfile
from XBrainLab.llm.core.runtime_process import (
    LocalRuntimeProcessOwner,
    LocalRuntimeRestartRequiredError,
    LocalRuntimeTurnBusyError,
)


class _CooperativeEngine:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self._cancelled = threading.Event()

    def load_model(self) -> None:
        return None

    def generate_stream(
        self,
        messages: list[dict[str, str]],
        *,
        profile: GenerationProfile,
    ) -> Iterator[str]:
        del messages, profile
        self._cancelled.clear()
        yield "started"
        while not self._cancelled.wait(0.01):
            yield "working"

    def cancel_generation(self, wait_timeout: float = 0.25) -> bool:
        del wait_timeout
        self._cancelled.set()
        return True

    def close(self) -> bool:
        return True


class _FiniteEngine(_CooperativeEngine):
    def generate_stream(
        self,
        messages: list[dict[str, str]],
        *,
        profile: GenerationProfile,
    ) -> Iterator[str]:
        del messages, profile
        yield "one"
        yield "two"


class _StubbornEngine(_CooperativeEngine):
    def generate_stream(
        self,
        messages: list[dict[str, str]],
        *,
        profile: GenerationProfile,
    ) -> Iterator[str]:
        del messages, profile
        while True:
            time.sleep(10)
            yield "unreachable"

    def cancel_generation(self, wait_timeout: float = 0.25) -> bool:
        del wait_timeout
        return False

    def close(self) -> bool:
        time.sleep(10)
        return False


class _StubbornLoadEngine(_FiniteEngine):
    def load_model(self) -> None:
        time.sleep(10)


def _config() -> LLMConfig:
    config = LLMConfig()
    config.device = "cpu"
    config.timeout = 1
    return config


def _messages() -> list[dict[str, str]]:
    return [{"role": "user", "content": "bounded runtime probe"}]


def _start_generation(
    owner: LocalRuntimeProcessOwner,
) -> tuple[threading.Thread, list[str], list[BaseException]]:
    chunks: list[str] = []
    errors: list[BaseException] = []

    def _run() -> None:
        try:
            chunks.extend(
                owner.generate_stream(
                    _messages(),
                    profile=GenerationProfile.INFORMATIONAL_TEXT,
                )
            )
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=_run)
    thread.start()
    assert owner.wait_until_generation_active(timeout=2.0)
    return thread, chunks, errors


def test_process_owner_rejects_overlapping_turns() -> None:
    owner = LocalRuntimeProcessOwner(
        _config(),
        engine_factory=_CooperativeEngine,
        startup_timeout=3.0,
    )
    owner.load_model()
    thread, _, errors = _start_generation(owner)

    try:
        with pytest.raises(LocalRuntimeTurnBusyError):
            list(
                owner.generate_stream(
                    _messages(),
                    profile=GenerationProfile.INFORMATIONAL_TEXT,
                )
            )
        assert owner.cancel_generation(wait_timeout=0.5) is True
        thread.join(timeout=1.0)
        assert thread.is_alive() is False
        assert errors == []
    finally:
        assert owner.close(wait_timeout=0.2) is True


def test_cooperative_cancel_keeps_process_ready_for_next_turn() -> None:
    owner = LocalRuntimeProcessOwner(
        _config(),
        engine_factory=_CooperativeEngine,
        startup_timeout=3.0,
    )
    owner.load_model()
    first_thread, first_chunks, errors = _start_generation(owner)

    try:
        assert owner.cancel_generation(wait_timeout=0.5) is True
        first_thread.join(timeout=1.0)

        assert first_thread.is_alive() is False
        assert errors == []
        assert first_chunks in ([], ["started"]) or first_chunks[0] == "started"
        assert owner.restart_required is False
        assert owner.is_alive is True
    finally:
        assert owner.close(wait_timeout=0.2) is True


def test_stubborn_generation_is_terminated_and_fenced_after_grace() -> None:
    owner = LocalRuntimeProcessOwner(
        _config(),
        engine_factory=_StubbornEngine,
        startup_timeout=3.0,
        termination_timeout=0.2,
    )
    owner.load_model()
    owned_pid = owner.pid
    thread, chunks, errors = _start_generation(owner)

    started = time.monotonic()
    assert owner.cancel_generation(wait_timeout=0.1) is True
    elapsed = time.monotonic() - started
    thread.join(timeout=1.0)

    assert elapsed < 0.8
    assert owned_pid is not None
    assert owner.last_terminated_pid == owned_pid
    assert owner.is_alive is False
    assert owner.restart_required is True
    assert thread.is_alive() is False
    assert chunks == []
    assert len(errors) == 1
    assert isinstance(errors[0], LocalRuntimeRestartRequiredError)
    with pytest.raises(LocalRuntimeRestartRequiredError):
        list(
            owner.generate_stream(
                _messages(),
                profile=GenerationProfile.INFORMATIONAL_TEXT,
            )
        )


def test_close_terminates_only_owned_stubborn_process_within_bound() -> None:
    owner = LocalRuntimeProcessOwner(
        _config(),
        engine_factory=_StubbornEngine,
        startup_timeout=3.0,
        termination_timeout=0.2,
    )
    owner.load_model()
    owned_pid = owner.pid
    thread, _, errors = _start_generation(owner)

    started = time.monotonic()
    assert owner.close(wait_timeout=0.1) is True
    elapsed = time.monotonic() - started
    thread.join(timeout=1.0)

    assert elapsed < 0.8
    assert owned_pid is not None
    assert owner.last_terminated_pid == owned_pid
    assert owner.is_alive is False
    assert thread.is_alive() is False
    assert len(errors) == 1
    assert isinstance(errors[0], LocalRuntimeRestartRequiredError)


def test_clean_generation_and_close_do_not_require_restart() -> None:
    owner = LocalRuntimeProcessOwner(
        _config(),
        engine_factory=_FiniteEngine,
        startup_timeout=3.0,
    )
    owner.load_model()

    assert list(
        owner.generate_stream(
            _messages(),
            profile=GenerationProfile.INFORMATIONAL_TEXT,
        )
    ) == ["one", "two"]
    assert owner.close(wait_timeout=0.5) is True
    assert owner.restart_required is False


def test_close_during_model_load_terminates_owned_process_within_bound() -> None:
    owner = LocalRuntimeProcessOwner(
        _config(),
        engine_factory=_StubbornLoadEngine,
        startup_timeout=10.0,
        termination_timeout=0.2,
    )
    load_errors: list[BaseException] = []

    def _load() -> None:
        try:
            owner.load_model()
        except BaseException as exc:
            load_errors.append(exc)

    load_thread = threading.Thread(target=_load)
    load_thread.start()
    assert owner.wait_until_process_started(timeout=8.0)
    owned_pid = owner.pid

    started = time.monotonic()
    assert owner.close(wait_timeout=0.1) is True
    elapsed = time.monotonic() - started
    load_thread.join(timeout=1.0)

    assert elapsed < 0.8
    assert owned_pid is not None
    assert owner.last_terminated_pid == owned_pid
    assert owner.is_alive is False
    assert load_thread.is_alive() is False
    assert len(load_errors) == 1
