from __future__ import annotations

import ast
import inspect

import pytest

from scripts.dev.capture_chatpanel_local_recovery_walkthrough import main
from scripts.dev.chatpanel_recovery.runtime import (
    _recorded_host_actions,
    _RecoveryWalkthroughDriver,
    parse_args,
)
from XBrainLab.llm.agent.turn import (
    AssistantGenerationEvent,
    AssistantGenerationEventPhase,
)
from XBrainLab.llm.core.model_catalog import PRIMARY_LOCAL_MODEL_ID


def test_recovery_cli_defaults_to_exact_granite() -> None:
    args = parse_args([])

    assert args.model == PRIMARY_LOCAL_MODEL_ID
    assert args.timeout_seconds == 600


def test_recovery_cli_rejects_any_non_product_model() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--model", "microsoft/Phi-4-mini-instruct"])


def test_strict_sealer_receives_only_recorded_host_actions() -> None:
    payload = {
        "host_assistance": {
            "actions": ["completed setup", "completed Retry click"],
        }
    }

    assert _recorded_host_actions(payload) == [
        "completed setup",
        "completed Retry click",
    ]


def test_recovery_driver_uses_typed_started_generation_after_turn_baseline() -> None:
    driver = object.__new__(_RecoveryWalkthroughDriver)
    driver.generation_events = []
    baseline = {"generation_event_count": 0}

    driver._record_generation_event(object())
    driver._record_generation_event(
        AssistantGenerationEvent(
            generation_id=17,
            phase=AssistantGenerationEventPhase.STARTED,
        )
    )

    observed = driver._started_generation_event_after(baseline)

    assert observed == AssistantGenerationEvent(
        generation_id=17,
        phase=AssistantGenerationEventPhase.STARTED,
    )


@pytest.mark.parametrize(
    "callback_name",
    (
        "_wait_for_ready",
        "_wait_for_blocked_turn",
        "_wait_for_training_recovery",
        "_wait_for_retry",
        "_wait_for_cancellable_turn",
        "_wait_for_cancelled_terminal",
    ),
)
def test_recovery_poll_callbacks_stop_after_terminal_started(
    callback_name: str,
) -> None:
    driver = object.__new__(_RecoveryWalkthroughDriver)
    driver._terminal_started = True

    getattr(driver, callback_name)()


def test_entrypoint_remains_a_thin_composition_root() -> None:
    module = inspect.getmodule(main)
    assert module is not None
    source = inspect.getsource(module)
    tree = ast.parse(source)
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]

    assert [node.name for node in functions] == ["main"]
    assert len(functions[0].body) <= 2
