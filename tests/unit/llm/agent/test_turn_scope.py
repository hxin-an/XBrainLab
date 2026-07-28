"""Host-owned execution scope for one admitted assistant turn."""

from __future__ import annotations

import pytest

from XBrainLab.backend.application import CommandName
from XBrainLab.llm.agent.turn import AssistantTurnScope
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
            "Import this dataset and finish the data import workflow.",
            CommandName.APPLY_INTERPRETATION.value,
        ),
        (
            "Prepare this EEG dataset for training.",
            CommandName.GENERATE_DATASET.value,
        ),
        (
            "載入資料、完成前處理並建立 epochs",
            CommandName.CREATE_EPOCH.value,
        ),
        (
            "完成這份資料的匯入流程",
            CommandName.APPLY_INTERPRETATION.value,
        ),
        (
            "幫我把這份 EEG 資料準備到可以訓練",
            CommandName.GENERATE_DATASET.value,
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
