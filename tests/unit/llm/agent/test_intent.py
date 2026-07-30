import pytest

from XBrainLab.backend.application import CommandName
from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS
from XBrainLab.llm.agent.intent import (
    INTENT_TO_COMMAND,
    command_for_intent,
    infer_user_intent,
    is_explicit_workflow_continuation,
    path_label_for_intent,
    resolve_blocked_explanation_intent,
)


def test_intent_to_command_compatibility_view_does_not_drift_from_registry():
    expected = {
        "scan_source": CommandName.SCAN_SOURCE,
        "preview_interpretation": CommandName.PREVIEW_INTERPRETATION,
        "validate_interpretation": CommandName.VALIDATE_INTERPRETATION,
        "apply_interpretation": CommandName.APPLY_INTERPRETATION,
        "save_interpretation_recipe": CommandName.SAVE_INTERPRETATION_RECIPE,
        "reload_interpretation_recipe": CommandName.RELOAD_INTERPRETATION_RECIPE,
        "load_data": CommandName.LOAD_DATA,
        "preprocess": CommandName.PREPROCESS,
        "reset_preprocess": CommandName.RESET_PREPROCESS,
        "create_epoch": CommandName.CREATE_EPOCH,
        "generate_dataset": CommandName.GENERATE_DATASET,
        "configure_training": CommandName.CONFIGURE_TRAINING,
        "train": CommandName.TRAIN,
        "stop_training": CommandName.STOP_TRAINING,
        "evaluate": CommandName.EVALUATE,
        "reset_session": CommandName.RESET_SESSION,
        "query_state": CommandName.QUERY_STATE,
        "visualize": CommandName.VISUALIZE,
        "saliency": CommandName.SALIENCY,
    }

    assert expected == INTENT_TO_COMMAND
    assert AGENT_ACTION_CONTRACTS.intent_to_command() == INTENT_TO_COMMAND


def test_infers_blocked_workflow_intents():
    assert infer_user_intent("Train an EEGNet model now.") == "train"
    assert (
        infer_user_intent("Train it now; if blocked just configure training.")
        == "train"
    )
    assert infer_user_intent("Evaluate the trained model.") == "evaluate"
    assert infer_user_intent("Show visualization readiness after training.") == (
        "visualize"
    )
    assert infer_user_intent("Preview the data interpretation.") == (
        "preview_interpretation"
    )
    assert infer_user_intent("Scan a data source.") == "scan_source"
    assert infer_user_intent("List the files in /data/eeg") == "browse_files"
    assert infer_user_intent("Apply a 1 to 30 Hz bandpass filter.") == "preprocess"


def test_infers_preview_metadata_intents():
    assert infer_user_intent("Preview with session ses-01 override.") == (
        "preview_interpretation"
    )
    assert infer_user_intent("Preview with task motor run 02 override.") == (
        "preview_interpretation"
    )
    assert infer_user_intent("Preview with event role stimulus.") == (
        "preview_interpretation"
    )


def test_infers_product_language_data_import_chain() -> None:
    assert (
        infer_user_intent(
            "Find the EEG recording at /tmp/source.fif and prepare it for review."
        )
        == "scan_source"
    )
    assert (
        infer_user_intent(
            "Show me how XBrainLab understands the selected recording before "
            "it is imported."
        )
        == "preview_interpretation"
    )
    assert infer_user_intent("Import the reviewed recording now.") == (
        "apply_interpretation"
    )
    assert (
        infer_user_intent(
            "Build an individual training dataset with a trial-based split."
        )
        == "generate_dataset"
    )


@pytest.mark.parametrize(
    "text",
    (
        "Explain how the model understands loading and standard preprocessing.",
        "Compare how XBrainLab understands preprocessing and training.",
    ),
)
def test_explanatory_understanding_language_does_not_authorize_mutation(text):
    assert infer_user_intent(text) == "no_tool"


def test_infers_multilingual_no_call_and_clarification_boundaries():
    assert infer_user_intent("Load /data/A01T.gdf") == "scan_source"
    assert infer_user_intent("Import my EEG folder /data/session01") == "scan_source"
    assert infer_user_intent("幫我讀這份腦波資料 /data/A01T.gdf") == "scan_source"
    assert infer_user_intent("幫我 scan 這個 BIDS root /data/bids") == ("scan_source")
    assert infer_user_intent("現在為什麼不能 train?") == "train"
    assert infer_user_intent("什麼是 epoch?") == "no_tool"
    assert infer_user_intent("幫我處理資料") == "ask_clarification"
    assert infer_user_intent("幫我貼標籤") == "ask_clarification"
    assert infer_user_intent("幫我切 epoch event 769") == "create_epoch"


@pytest.mark.parametrize(
    "text",
    (
        "Either visualize the result or compute saliency; ask me which one.",
        "視覺化結果或計算顯著圖都可以, 先問我選哪一個。",
    ),
)
def test_unresolved_equal_rank_endpoint_choice_requires_clarification(
    text: str,
) -> None:
    assert infer_user_intent(text) == "ask_clarification"


@pytest.mark.parametrize(
    ("text", "expected_intent", "expected_command"),
    (
        (
            "Why can't I preprocess the loaded data?",
            "preprocess",
            CommandName.PREPROCESS,
        ),
        (
            "Why is epoch creation blocked?",
            "create_epoch",
            CommandName.CREATE_EPOCH,
        ),
        (
            "Why can't I build the training dataset?",
            "generate_dataset",
            CommandName.GENERATE_DATASET,
        ),
        ("為什麼現在不能訓練?", "train", CommandName.TRAIN),
        ("為什麼訓練不能開始?", "train", CommandName.TRAIN),
        ("為什麼無法評估模型?", "evaluate", CommandName.EVALUATE),
        ("為什麼不能開啟視覺化?", "visualize", CommandName.VISUALIZE),
        ("為什麼不能查看顯著性?", "saliency", CommandName.SALIENCY),
    ),
)
def test_blocked_explanation_resolves_exact_workflow_target(
    text: str,
    expected_intent: str,
    expected_command: CommandName,
) -> None:
    resolution = resolve_blocked_explanation_intent(text)

    assert resolution is not None
    assert resolution.target_intent == expected_intent
    assert resolution.target_command is expected_command
    assert resolution.ambiguous is False
    assert infer_user_intent(text) == expected_intent


@pytest.mark.parametrize(
    ("text", "expected_intent"),
    (
        ("Why can't I scan the EEG data source?", "scan_source"),
        (
            "Why is the interpretation preview blocked?",
            "preview_interpretation",
        ),
        (
            "Why is interpretation candidate validation blocked?",
            "validate_interpretation",
        ),
        (
            "Why can't I apply the reviewed interpretation?",
            "apply_interpretation",
        ),
        (
            "Why can't I save the interpretation recipe?",
            "save_interpretation_recipe",
        ),
        (
            "Why can't I reload the interpretation recipe?",
            "reload_interpretation_recipe",
        ),
        ("Why can't I use legacy load_data?", "load_data"),
        ("Why can't I reset preprocessing?", "reset_preprocess"),
        ("Why can't I configure training?", "configure_training"),
        ("Why can't I stop training?", "stop_training"),
        ("Why can't I query workflow state?", "query_state"),
        ("Why can't I reset the session?", "reset_session"),
    ),
)
def test_blocked_explanation_covers_agent_command_intents(
    text: str,
    expected_intent: str,
) -> None:
    resolution = resolve_blocked_explanation_intent(text)

    assert resolution is not None
    assert resolution.target_intent == expected_intent
    assert resolution.target_command is command_for_intent(expected_intent)
    assert resolution.ambiguous is False


@pytest.mark.parametrize(
    "text",
    (
        "Why can't the current workflow step continue?",
        "Why can't I preprocess or train?",
        "為什麼目前步驟不能繼續?",
    ),
)
def test_blocked_explanation_without_one_target_fails_closed(text: str) -> None:
    resolution = resolve_blocked_explanation_intent(text)

    assert resolution is not None
    assert resolution.target_intent is None
    assert resolution.target_command is None
    assert resolution.ambiguous is True
    assert infer_user_intent(text) == "ask_clarification"


@pytest.mark.parametrize(
    "text",
    (
        "Why are EEG epochs useful?",
        "Why does bandpass filtering reduce drift?",
        "Why can't EEG preprocessing remove every artifact?",
        "Why can't alpha waves be visualized directly?",
        "為什麼 EEG 前處理很重要?",
        "什麼是 saliency?",
    ),
)
def test_knowledge_why_questions_do_not_become_workflow_explanations(
    text: str,
) -> None:
    assert resolve_blocked_explanation_intent(text) is None
    assert infer_user_intent(text) == "no_tool"


@pytest.mark.parametrize(
    "text",
    (
        "Compare standard preprocessing and training settings.",
        "I want to understand loading and standard preprocessing.",
        "I am trying to understand loading and preprocessing.",
        "請比較標準前處理和訓練設定",
        "我想了解載入和標準前處理",
        "想了解載入和標準前處理",
        "了解載入和前處理的差異",
    ),
)
def test_comparison_or_understanding_requests_do_not_authorize_mutation(
    text: str,
) -> None:
    assert infer_user_intent(text) == "no_tool"


@pytest.mark.parametrize(
    ("text", "expected_intent"),
    (
        (
            "Apply this blocked interpretation anyway.",
            "apply_interpretation",
        ),
        (
            "Train it now; if blocked just configure training.",
            "train",
        ),
        (
            "已經切好 epoch 了, 幫我套用新的資料解讀; "
            "如果 blocked 就 scan /data/new_subject.gdf",
            "apply_interpretation",
        ),
    ),
)
def test_blocked_word_in_an_action_does_not_become_an_explanation(
    text: str,
    expected_intent: str,
) -> None:
    assert resolve_blocked_explanation_intent(text) is None
    assert infer_user_intent(text) == expected_intent


def test_natural_guided_recording_request_routes_to_scan_source():
    assert (
        infer_user_intent(
            "Use the EEG recording at /tmp/session/raw.fif to prepare the data "
            "for analysis. Continue through safe steps."
        )
        == "scan_source"
    )


@pytest.mark.parametrize(
    "text",
    (
        "Continue",
        "Continue with the reviewed recording.",
        "Proceed to the next step.",
        "繼續目前流程",
    ),
)
def test_recognizes_explicit_workflow_continuation(text: str) -> None:
    assert is_explicit_workflow_continuation(text) is True


@pytest.mark.parametrize(
    "text",
    (
        "Continue explaining what saliency means.",
        "Can you continue the earlier explanation?",
        "Proceed with a new unrelated file.",
        "繼續解釋這個概念",
    ),
)
def test_does_not_widen_explanatory_text_into_workflow_permission(text: str) -> None:
    assert is_explicit_workflow_continuation(text) is False


def test_workflow_readiness_questions_take_priority_over_explanatory_markers():
    assert infer_user_intent("What is ready now?") == "query_state"
    assert (
        infer_user_intent("Check what is ready in the current XBrainLab workflow.")
        == "query_state"
    )


def test_legacy_direct_load_requires_explicit_compatibility_intent():
    assert infer_user_intent("Use legacy load_data for /data/A01T.gdf") == "load_data"
    assert infer_user_intent("Direct load compatibility path /data/A01T.gdf") == (
        "load_data"
    )


def test_maps_intent_to_application_command():
    assert command_for_intent("train") == CommandName.TRAIN
    assert command_for_intent("evaluate") == CommandName.EVALUATE
    assert command_for_intent("scan_source") == CommandName.SCAN_SOURCE
    assert command_for_intent("no_tool") is None
    assert command_for_intent("ask_clarification") is None
    assert command_for_intent("unknown") is None


@pytest.mark.parametrize(
    "text",
    (
        "Reset preprocessing.",
        "Clear the preprocessing results.",
        "重設前處理",
        "清除預處理結果",
    ),
)
def test_reset_preprocessing_maps_to_narrow_lifecycle_command(text: str) -> None:
    intent = infer_user_intent(text)

    assert intent == "reset_preprocess"
    assert command_for_intent(intent) is CommandName.RESET_PREPROCESS


@pytest.mark.parametrize(
    "text",
    (
        "Stop training.",
        "Cancel the current training run.",
        "停止訓練",
        "中止目前的訓練",
    ),
)
def test_stop_training_maps_to_execution_control_command(text: str) -> None:
    intent = infer_user_intent(text)

    assert intent == "stop_training"
    assert command_for_intent(intent) is CommandName.STOP_TRAINING


def test_path_label_for_intent():
    assert path_label_for_intent("load_data") == "file path"
    assert path_label_for_intent("scan_source") == "source path"
    assert path_label_for_intent("unknown") is None
