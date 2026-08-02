"""Focused behavior tests for deterministic product-turn responses."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest

from XBrainLab.backend.application.capabilities import (
    CapabilityPolicy,
    CommandCapability,
)
from XBrainLab.backend.application.commands import CommandName
from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.application.view_publication import ApplicationViewPublication
from XBrainLab.backend.study import Study
from XBrainLab.llm.agent.product_turn_policy import (
    ProductTurnKind,
    ProductTurnPolicy,
)

GREETING_COPY = (
    "Hello. I can help you move through the EEG workflow: import raw data, "
    "prepare preprocessing, create EEG epochs, build a training dataset, configure "
    "training, and explain why a step is blocked. To begin, choose EEG files or "
    "ask what is ready now."
)
CLARIFICATION_COPY = (
    "Tell me which step you want to do next: import data, preview labels and "
    "metadata, preprocess, create EEG epochs, build a dataset, train, evaluate, or "
    "inspect saliency."
)
HISTORICAL_REFERENCE_CLARIFICATION_COPY = (
    "I cannot safely tell which earlier option you mean. Name the workflow step "
    "you want, such as preprocess, create EEG epochs, build a dataset, train, evaluate, "
    "or inspect saliency."
)


def _publication(
    command: CommandName,
    capability: CommandCapability | None,
    *,
    verified: bool = True,
    stale: bool = False,
) -> ApplicationViewPublication:
    capabilities = {} if capability is None else {command.value: capability}
    return ApplicationViewPublication(
        generation=7,
        state=ApplicationStateSnapshot.empty(),
        capabilities=CapabilityPolicy(capabilities),
        verified=verified,
        stale=stale,
    )


def _policy(
    publication_reader: Callable[[], ApplicationViewPublication],
) -> ProductTurnPolicy:
    return ProductTurnPolicy(object(), publication_reader=publication_reader)


@pytest.mark.parametrize("text", ("hello", "Hi!", "你好。", "您好"))
def test_greeting_returns_stable_product_copy_without_reading_publication(
    text: str,
) -> None:
    def unexpected_read() -> ApplicationViewPublication:
        raise AssertionError("greetings must not read workflow state")

    decision = _policy(unexpected_read).evaluate(text)

    assert decision is not None
    assert decision.kind is ProductTurnKind.GREETING
    assert decision.message == GREETING_COPY


def test_clarification_uses_current_publication_for_contextual_next_step() -> None:
    publication = _publication(
        CommandName.PREPROCESS,
        CommandCapability(
            command_name=CommandName.PREPROCESS.value,
            enabled=True,
        ),
    )
    publication = ApplicationViewPublication(
        generation=publication.generation,
        state=replace(publication.state, pipeline_stage="data_loaded"),
        capabilities=publication.capabilities,
    )

    decision = _policy(lambda: publication).evaluate("幫我處理資料")

    assert decision is not None
    assert decision.kind is ProductTurnKind.CLARIFICATION
    assert decision.message == CLARIFICATION_COPY
    assert decision.contextual_command is CommandName.PREPROCESS


def test_clarification_fails_closed_when_publication_is_unavailable() -> None:
    def unavailable_read() -> ApplicationViewPublication:
        raise RuntimeError("publication unavailable")

    decision = _policy(unavailable_read).evaluate("幫我處理資料")

    assert decision is not None
    assert decision.kind is ProductTurnKind.CLARIFICATION
    assert decision.contextual_command is None


def test_ordinary_no_tool_question_remains_for_language_generation() -> None:
    def unexpected_read() -> ApplicationViewPublication:
        raise AssertionError("ordinary no-tool questions must not read workflow state")

    assert _policy(unexpected_read).evaluate("什麼是 epoch?") is None


@pytest.mark.parametrize(
    "text",
    (
        "Use the first option mentioned earlier.",
        "Do the one above.",
        "Use the option you mentioned earlier.",
        "Do what you suggested before.",
        "Pick the previous recommendation.",
        "Go with your earlier suggestion.",
        "Run the action from before.",
        "Can you do the one you suggested before?",
        "Let's use that one.",
        "Could you apply that recommendation?",
        "Let us run the previous action.",
        "Apply it.",
        "Use it.",
        "Use that.",
        "This.",
        "That.",
        "Use the first option in the previous dialog.",
        "Use the option in the Data Import dialog mentioned earlier.",
        "Use the option mentioned earlier in the Data Import dialog.",
        "Apply the setting suggested before in the preprocessing dialog.",
        "Apply the setting in the preprocessing dialog from before.",
        "就用剛剛那個",
        "套用它",
        "使用它",
        "這個",
        "用前面提到的第一個選項",
        "執行你之前建議的操作",
        "選先前的建議",
        "就照前面那個做",
        "使用資料匯入對話框裡剛才提到的選項",
        "套用剛才資料匯入對話框裡提到的選項",
        "使用先前在前處理對話框中建議的設定",
        "選擇之前訓練對話框裡提過的模型",
        "套用前處理對話框中先前建議的設定",
        "選擇訓練對話框裡之前提過的模型",
        "那就用剛才那個選項",
        "可以幫我執行剛剛那個嗎",
        "能不能幫我做之前那個步驟",
        "就照剛才的",
        "採用前一個",
    ),
)
def test_historical_action_reference_clarifies_without_reading_or_guessing_state(
    text: str,
) -> None:
    def unexpected_read() -> ApplicationViewPublication:
        raise AssertionError("historical references must not guess workflow state")

    decision = _policy(unexpected_read).evaluate(text)

    assert decision is not None
    assert decision.kind is ProductTurnKind.CLARIFICATION
    assert decision.message == HISTORICAL_REFERENCE_CLARIFICATION_COPY
    assert decision.contextual_command is None


@pytest.mark.parametrize(
    "text",
    (
        "Why is that useful?",
        "Why did you suggest the earlier option?",
        "Continue the workflow.",
        "Continue with the reviewed recording.",
        "Open the option above 30 Hz.",
        "Use the first option in the current dialog.",
        "Select the first option above in the Data Import dialog",
        "Use the previous option in the current import wizard.",
        "Select the first option above in the Data Import wizard.",
        "Choose the previous row in the preprocessing panel.",
        "Apply the 1-30 Hz setting in the current preprocessing dialog.",
        "為什麼你剛才建議那個選項?",
        "繼續目前流程",
        "選擇資料匯入對話框上面的第一個選項",
        "選擇目前匯入精靈上面的前一個選項",
        "選擇資料匯入精靈上面的第一個選項",
        "選擇前處理面板上方的第二個選項",
        "套用目前前處理對話框中的 1-30 Hz 設定",
    ),
)
def test_information_and_current_workflow_continue_to_normal_admission(
    text: str,
) -> None:
    def unexpected_read() -> ApplicationViewPublication:
        raise AssertionError("these turns must continue to normal admission")

    assert _policy(unexpected_read).evaluate(text) is None


@pytest.mark.parametrize(
    "text",
    (
        "Why can't I train?",
        "Why is training blocked?",
        "為什麼現在不能訓練?",
    ),
)
def test_training_blocker_uses_backend_capability_reasons(text: str) -> None:
    publication = _publication(
        CommandName.TRAIN,
        CommandCapability(
            command_name=CommandName.TRAIN.value,
            enabled=False,
            reasons=[
                "Generate datasets before training.",
                "Select a model before training.",
            ],
        ),
    )

    decision = _policy(lambda: publication).evaluate(text)

    assert decision is not None
    assert decision.kind is ProductTurnKind.WORKFLOW_BLOCKED
    assert decision.message == (
        "Training is not ready yet: Generate datasets before training.; "
        "Select a model before training."
    )


def test_default_policy_reads_real_application_service_publication() -> None:
    decision = ProductTurnPolicy(Study()).evaluate("Why can't I train?")

    assert decision is not None
    assert decision.kind is ProductTurnKind.WORKFLOW_BLOCKED
    assert "Load raw data before training." in decision.message
    assert "Generate datasets before training." in decision.message
    assert "Select a model before training." in decision.message


def test_enabled_command_reports_no_blocker_from_published_capability() -> None:
    publication = _publication(
        CommandName.TRAIN,
        CommandCapability(
            command_name=CommandName.TRAIN.value,
            enabled=True,
            reasons=[],
            long_running=True,
            requires_confirmation=True,
        ),
    )

    decision = _policy(lambda: publication).evaluate("Why is training blocked?")

    assert decision is not None
    assert decision.kind is ProductTurnKind.WORKFLOW_READY
    assert decision.message == (
        "Training is available in the current workflow. It still requires "
        "confirmation before execution."
    )


@pytest.mark.parametrize(
    ("text", "command", "subject", "reason"),
    (
        (
            "Why can't I preprocess?",
            CommandName.PREPROCESS,
            "Preprocessing",
            "Load raw data before preprocessing.",
        ),
        (
            "Why is epoch creation blocked?",
            CommandName.CREATE_EPOCH,
            "EEG epoch creation",
            "Preprocess data before creating EEG epochs.",
        ),
        (
            "Why can't I build a dataset?",
            CommandName.GENERATE_DATASET,
            "Dataset generation",
            "Create EEG epochs before building the training dataset.",
        ),
        (
            "為什麼現在不能訓練?",
            CommandName.TRAIN,
            "Training",
            "Generate datasets before training.",
        ),
        (
            "為什麼無法評估模型?",
            CommandName.EVALUATE,
            "Evaluation",
            "Complete at least one training run before evaluating results.",
        ),
        (
            "為什麼不能開啟視覺化?",
            CommandName.VISUALIZE,
            "Visualization",
            "Complete training before opening visualization views.",
        ),
        (
            "為什麼不能查看顯著性?",
            CommandName.SALIENCY,
            "Saliency analysis",
            "Complete evaluation before configuring saliency.",
        ),
    ),
)
def test_blocked_explanation_is_generic_over_target_command(
    text: str,
    command: CommandName,
    subject: str,
    reason: str,
) -> None:
    reads = 0
    publication = _publication(
        command,
        CommandCapability(
            command_name=command.value,
            enabled=False,
            reasons=[reason],
        ),
    )

    def read_once() -> ApplicationViewPublication:
        nonlocal reads
        reads += 1
        return publication

    decision = _policy(read_once).evaluate(text)

    assert decision is not None
    assert decision.kind is ProductTurnKind.WORKFLOW_BLOCKED
    assert decision.message == f"{subject} is not ready yet: {reason}"
    assert reads == 1


@pytest.mark.parametrize(
    "publication_reader",
    (
        lambda: _publication(CommandName.TRAIN, None),
        lambda: _publication(
            CommandName.TRAIN,
            CommandCapability(
                command_name=CommandName.TRAIN.value,
                enabled=True,
            ),
            verified=False,
            stale=True,
        ),
    ),
)
def test_incomplete_or_unusable_publication_fails_closed(
    publication_reader: Callable[[], ApplicationViewPublication],
) -> None:
    decision = _policy(publication_reader).evaluate("Why can't I train?")

    assert decision is not None
    assert decision.kind is ProductTurnKind.WORKFLOW_UNAVAILABLE
    assert decision.message == (
        "I could not verify whether training is ready because the application "
        "state is temporarily unavailable. No training action was started. Try "
        "again after the current operation finishes."
    )


def test_publication_read_exception_fails_closed_instead_of_reporting_ready() -> None:
    def unavailable() -> ApplicationViewPublication:
        raise RuntimeError("publication unavailable")

    decision = _policy(unavailable).evaluate("Why can't I train?")

    assert decision is not None
    assert decision.kind is ProductTurnKind.WORKFLOW_UNAVAILABLE
    assert "could not verify whether training is ready" in decision.message
    assert "available in the current workflow" not in decision.message


@pytest.mark.parametrize(
    "text",
    (
        "Why can't the current workflow step continue?",
        "Why can't I preprocess or train?",
        "為什麼目前步驟不能繼續?",
    ),
)
def test_ambiguous_blocked_explanation_asks_for_one_step_without_state_read(
    text: str,
) -> None:
    def unexpected_read() -> ApplicationViewPublication:
        raise AssertionError("ambiguous targets must not read or guess workflow state")

    decision = _policy(unexpected_read).evaluate(text)

    assert decision is not None
    assert decision.kind is ProductTurnKind.BLOCKED_EXPLANATION_AMBIGUOUS
    assert decision.message == (
        "Which XBrainLab workflow step do you mean: import data, preprocess, "
        "create EEG epochs, build a dataset, configure training, train, evaluate, "
        "visualize, or inspect saliency?"
    )
