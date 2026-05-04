from XBrainLab.backend.application import CommandName
from XBrainLab.llm.agent.intent import (
    command_for_intent,
    infer_user_intent,
    path_label_for_intent,
)


def test_infers_blocked_workflow_intents():
    assert infer_user_intent("Train an EEGNet model now.") == "train"
    assert infer_user_intent("Evaluate the trained model.") == "evaluate"
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


def test_maps_intent_to_application_command():
    assert command_for_intent("train") == CommandName.TRAIN
    assert command_for_intent("evaluate") == CommandName.EVALUATE
    assert command_for_intent("scan_source") == CommandName.SCAN_SOURCE
    assert command_for_intent("unknown") is None


def test_path_label_for_intent():
    assert path_label_for_intent("load_data") == "file path"
    assert path_label_for_intent("scan_source") == "source path"
    assert path_label_for_intent("unknown") is None
