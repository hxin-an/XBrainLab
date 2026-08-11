"""Host-owned execution scope for one admitted assistant turn."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from XBrainLab.backend.application import CommandName
from XBrainLab.llm.agent.turn import (
    AssistantTurnCorrelation,
    AssistantTurnRequest,
    AssistantTurnScope,
)
from XBrainLab.llm.agent.turn_scope import resolve_assistant_turn_scope


@pytest.mark.parametrize(
    "text",
    (
        "Explain the current settings.",
        "What is ready now?",
        "Set the batch size to 16.",
        "Configure training with batch size 32 and learning rate 0.001.",
        "Configure EEGNet for 10 epochs with batch size 32 and learning rate 0.001.",
        "Start training.",
        "Explain how loading, preprocessing, and training fit together.",
        "Compare standard preprocessing and training settings.",
        "I am trying to understand loading and preprocessing.",
        "What would happen if I load and preprocess this recording?",
        "Do not load and preprocess this recording.",
        "Complete the entire workflow.",
        "解釋目前設定",
        "請比較標準前處理和訓練設定",
        "我想了解載入和標準前處理",
        "想了解載入和標準前處理",
        "了解載入和前處理的差異",
        "現在可以做什麼?",
        "開始訓練",
        "如果載入後再前處理會發生什麼?",
        "不要載入並前處理這份資料",
        "完成整個流程",
    ),
)
def test_atomic_or_ambiguous_requests_remain_single_action(text: str) -> None:
    resolution = resolve_assistant_turn_scope(text)

    assert resolution.scope is AssistantTurnScope.SINGLE_ACTION
    assert resolution.terminal_command is None


@pytest.mark.parametrize(
    "text",
    (
        "Load the data but not preprocess it.",
        "Load the data but avoid preprocessing it.",
        "Load every stage except preprocessing.",
        "Load the data and skip preprocessing.",
        "Load and preprocess this recording without resampling, then create epochs.",
        "Do not load this recording, preprocess it, and create epochs.",
        "Load this recording, but do not create epochs.",
        "Load and preprocess this recording, but do not generate a dataset.",
        "Load and preprocess this recording, but do not configure training.",
        "Load and preprocess this recording, but do not start training.",
        "Load and train this recording, but do not evaluate it.",
        "Load and evaluate this recording, but do not visualize it.",
        "載入資料但不前處理",
        "載入資料但不要前處理",
        "載入資料並略過前處理",
        "不要重採樣, 載入資料並完成前處理後建立 epochs",
        "不要載入這份資料並建立 epochs",
        "載入資料, 但不要建立 epochs",
        "載入並前處理資料, 但不要建立資料集",
        "載入並前處理資料, 但不要設定訓練",
        "載入並前處理資料, 但不要開始訓練",
        "載入並訓練資料, 但不要評估",
        "載入並評估資料, 但不要視覺化",
    ),
)
def test_excluded_workflow_stage_never_expands_guided_scope(text: str) -> None:
    resolution = resolve_assistant_turn_scope(text)

    assert resolution.scope is AssistantTurnScope.SINGLE_ACTION
    assert resolution.terminal_command is None


@pytest.mark.parametrize(
    "text",
    (
        "Load the data, but don't apply preprocessing.",
        "Load the data without doing preprocessing.",
        "Load the data and avoid using preprocessing.",
    ),
)
def test_preprocess_exclusion_is_preserved_as_typed_turn_policy(text: str) -> None:
    resolution = resolve_assistant_turn_scope(text)

    assert resolution.scope is AssistantTurnScope.SINGLE_ACTION
    assert resolution.terminal_command is None
    assert resolution.excluded_commands == (CommandName.PREPROCESS,)

    request = AssistantTurnRequest(
        correlation=AssistantTurnCorrelation(generation=1, turn_id=1),
        text=text,
        scope=resolution.scope,
        terminal_command=resolution.terminal_command,
        excluded_commands=resolution.excluded_commands,
    )

    assert request.excluded_commands == (CommandName.PREPROCESS,)


def test_hypothetical_request_still_preserves_its_execution_exclusion() -> None:
    resolution = resolve_assistant_turn_scope(
        "What would happen if I load this file without doing preprocessing?"
    )

    assert resolution.scope is AssistantTurnScope.SINGLE_ACTION
    assert resolution.excluded_commands == (CommandName.PREPROCESS,)


@pytest.mark.parametrize(
    ("text", "command"),
    (
        (
            "Do not preview the interpretation.",
            CommandName.PREVIEW_INTERPRETATION,
        ),
        (
            "Do not validate the interpretation candidate.",
            CommandName.VALIDATE_INTERPRETATION,
        ),
        (
            "Do not apply the interpretation.",
            CommandName.APPLY_INTERPRETATION,
        ),
        ("Do not stop training.", CommandName.STOP_TRAINING),
        ("Do not compute saliency.", CommandName.SALIENCY),
        ("不要預覽資料解讀", CommandName.PREVIEW_INTERPRETATION),
        ("不要驗證資料解讀", CommandName.VALIDATE_INTERPRETATION),
        ("不要套用資料解讀", CommandName.APPLY_INTERPRETATION),
        ("不要停止訓練", CommandName.STOP_TRAINING),
        ("不要計算顯著圖", CommandName.SALIENCY),
    ),
)
def test_every_executable_workflow_stage_preserves_explicit_exclusion(
    text: str,
    command: CommandName,
) -> None:
    resolution = resolve_assistant_turn_scope(text)

    assert resolution.scope is AssistantTurnScope.SINGLE_ACTION
    assert resolution.terminal_command is None
    assert resolution.excluded_commands == (command,)


@pytest.mark.parametrize(
    "text",
    (
        "Continue with the reviewed recording.",
        "Proceed to the next step.",
        "Load this recording and continue until a decision is needed.",
        "繼續目前流程",
        "下一步",
        "載入這份資料並繼續到需要我確認為止",
    ),
)
def test_explicit_continuation_uses_bounded_guided_scope(text: str) -> None:
    resolution = resolve_assistant_turn_scope(text)

    assert resolution.scope is AssistantTurnScope.GUIDED_WORKFLOW
    assert resolution.terminal_command is None


@pytest.mark.parametrize(
    ("text", "terminal"),
    (
        (
            "Load this recording, preprocess it, and create epochs.",
            CommandName.CREATE_EPOCH.value,
        ),
        (
            "Create epochs after you load and preprocess this recording.",
            CommandName.CREATE_EPOCH.value,
        ),
        (
            "Not only load this recording but also preprocess it.",
            CommandName.PREPROCESS.value,
        ),
        (
            "Import this dataset and finish the data import workflow.",
            CommandName.APPLY_INTERPRETATION.value,
        ),
        (
            "Prepare this EEG dataset for training.",
            CommandName.CONFIGURE_DATASET_SPLIT.value,
        ),
        (
            "載入資料、完成前處理並建立 epochs",
            CommandName.CREATE_EPOCH.value,
        ),
        (
            "不只載入資料, 也要完成前處理",
            CommandName.PREPROCESS.value,
        ),
        (
            "完成這份資料的匯入流程",
            CommandName.APPLY_INTERPRETATION.value,
        ),
        (
            "幫我把這份 EEG 資料準備到可以訓練",
            CommandName.CONFIGURE_DATASET_SPLIT.value,
        ),
        (
            "There are no external labels; load this recording, preprocess it, "
            "and create epochs.",
            CommandName.CREATE_EPOCH.value,
        ),
        (
            "這份資料沒有外部標籤, 載入資料並完成前處理後建立 epochs",
            CommandName.CREATE_EPOCH.value,
        ),
    ),
)
def test_explicit_multi_stage_goal_has_a_host_enforced_endpoint(
    text: str,
    terminal: str,
) -> None:
    resolution = resolve_assistant_turn_scope(text)

    assert resolution.scope is AssistantTurnScope.GUIDED_WORKFLOW
    assert resolution.terminal_command == terminal


@pytest.mark.parametrize(
    "text",
    (
        "Train the model and then stop training.",
        "Load the data, train it, then stop training.",
        "開始訓練, 然後停止訓練",
        "載入資料、開始訓練, 最後停止訓練",
    ),
)
def test_explicit_stop_training_endpoint_is_resolved_without_crashing(
    text: str,
) -> None:
    resolution = resolve_assistant_turn_scope(text)

    assert resolution.scope is AssistantTurnScope.GUIDED_WORKFLOW
    assert resolution.terminal_command == CommandName.STOP_TRAINING.value


@pytest.mark.parametrize(
    ("text", "terminal"),
    (
        (
            "Load the data, visualize it, then compute saliency.",
            CommandName.SALIENCY.value,
        ),
        (
            "Load the data, compute saliency, then visualize it.",
            CommandName.VISUALIZE.value,
        ),
        (
            "載入資料、視覺化結果, 最後計算顯著圖",
            CommandName.SALIENCY.value,
        ),
        (
            "載入資料、計算顯著圖, 最後視覺化結果",
            CommandName.VISUALIZE.value,
        ),
    ),
)
def test_equal_rank_endpoint_uses_last_textual_mention(
    text: str,
    terminal: str,
) -> None:
    resolution = resolve_assistant_turn_scope(text)

    assert resolution.scope is AssistantTurnScope.GUIDED_WORKFLOW
    assert resolution.terminal_command == terminal


@pytest.mark.parametrize("hash_seed", ("1", "2", "17", "101"))
def test_equal_rank_endpoint_is_stable_across_hash_seeds(hash_seed: str) -> None:
    script = """
from XBrainLab.llm.agent.turn_scope import resolve_assistant_turn_scope

resolution = resolve_assistant_turn_scope(
    "Load the data, visualize it, then compute saliency."
)
print(resolution.terminal_command)
"""
    environment = {**os.environ, "PYTHONHASHSEED": hash_seed}

    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        env=environment,
        text=True,
        timeout=20,
    )

    assert completed.stdout.strip() == CommandName.SALIENCY.value


@pytest.mark.parametrize(
    "text",
    (
        "Load the data, then either visualize it or compute saliency; ask me which.",
        "載入資料後, 視覺化或計算顯著圖都可以, 先問我選哪一個。",
    ),
)
def test_unresolved_endpoint_choice_does_not_expand_workflow_scope(text: str) -> None:
    resolution = resolve_assistant_turn_scope(text)

    assert resolution.scope is AssistantTurnScope.SINGLE_ACTION
    assert resolution.terminal_command is None
