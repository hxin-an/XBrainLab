from XBrainLab.backend.application import CommandName
from XBrainLab.llm.agent.intent import (
    command_for_intent,
    infer_user_intent,
    path_label_for_intent,
)


def test_infers_blocked_workflow_intents():
    assert infer_user_intent("Train an EEGNet model now.") == "train"
    assert infer_user_intent("Evaluate the trained model.") == "evaluate"
    assert infer_user_intent("Show visualization readiness after training.") == (
        "visualize"
    )
    assert infer_user_intent("Preview the data interpretation.") == (
        "preview_interpretation"
    )
    assert infer_user_intent("Scan a data source.") == "scan_source"
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


def test_infers_multilingual_no_call_and_clarification_boundaries():
    assert infer_user_intent("Load /data/A01T.gdf") == "scan_source"
    assert infer_user_intent("Import my EEG folder /data/session01") == "scan_source"
    assert infer_user_intent("幫我讀這份腦波資料 /data/A01T.gdf") == "scan_source"
    assert infer_user_intent("幫我 scan 這個 BIDS root /data/bids") == ("scan_source")
    assert infer_user_intent("現在為什麼不能 train?") == "no_tool"
    assert infer_user_intent("什麼是 epoch?") == "no_tool"
    assert infer_user_intent("幫我處理資料") == "ask_clarification"
    assert infer_user_intent("幫我切 epoch event 769") == "create_epoch"


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


def test_path_label_for_intent():
    assert path_label_for_intent("load_data") == "file path"
    assert path_label_for_intent("scan_source") == "source path"
    assert path_label_for_intent("unknown") is None
