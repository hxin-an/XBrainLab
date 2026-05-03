from XBrainLab.llm.agent.tool_call_normalizer import normalize_tool_call


def test_normalizes_workflow_command_aliases_to_registered_tools():
    assert normalize_tool_call("create_epoch", {"t_min": 0, "t_max": 1}) == (
        "epoch_data",
        {"t_min": 0, "t_max": 1},
    )
    assert normalize_tool_call("train", {}) == ("start_training", {})


def test_normalizes_standard_preprocess_bandpass_arguments_from_user_intent():
    tool_name, params = normalize_tool_call(
        "apply_bandpass_filter",
        {"low_freq": 8, "high_freq": 30},
        latest_user_text="Apply preprocessing with 8 to 30 Hz bandpass.",
    )

    assert tool_name == "apply_standard_preprocess"
    assert params["l_freq"] == 8
    assert params["h_freq"] == 30


def test_normalizes_generate_dataset_defaults_and_training_mode_alias():
    tool_name, params = normalize_tool_call(
        "generate_dataset",
        {"split_strategy": "individual", "test_ratio": 0.2},
    )

    assert tool_name == "generate_dataset"
    assert params == {
        "split_strategy": "trial",
        "training_mode": "individual",
        "test_ratio": 0.2,
        "val_ratio": 0.2,
    }


def test_normalizes_epoch_event_ids_to_strings():
    tool_name, params = normalize_tool_call(
        "epoch_data",
        {"t_min": -0.2, "t_max": 0.8, "event_id": [769]},
    )

    assert tool_name == "epoch_data"
    assert params["event_id"] == ["769"]


def test_normalizes_bids_scan_hint_from_source_path():
    tool_name, params = normalize_tool_call(
        "scan_source",
        {"source_path": "/data/bids_mi"},
    )

    assert tool_name == "scan_source"
    assert params["source_hint"] == "bids"


def test_normalizes_subject_override_into_preview_choices():
    tool_name, params = normalize_tool_call(
        "preview_interpretation",
        {"scan_id": "S01", "choices": {}},
        latest_user_text="Preview with subject S01 override.",
    )

    assert tool_name == "preview_interpretation"
    assert params == {"choices": {"subject": "S01"}}


def test_normalizes_training_setup_substitute_when_user_requested_start():
    tool_name, params = normalize_tool_call(
        "configure_training",
        {"epoch": 10},
        latest_user_text="Start training.",
    )

    assert tool_name == "start_training"
    assert params == {}


def test_drops_schema_object_recipe_path_for_default_save():
    tool_name, params = normalize_tool_call(
        "save_interpretation_recipe",
        {"recipe_path": {"type": "string"}},
    )

    assert tool_name == "save_interpretation_recipe"
    assert params == {}


def test_latest_intent_scan_turn_rejects_preview_substitute():
    tool_name, params = normalize_tool_call(
        "preview_interpretation",
        {},
        latest_user_text="Scan a data source.",
    )

    assert tool_name == "scan_source"
    assert params == {}


def test_latest_intent_preview_turn_rejects_repeat_scan():
    tool_name, params = normalize_tool_call(
        "scan_source",
        {"source_path": "/data/bids_mi"},
        latest_user_text="Preview the scanned interpretation.",
    )

    assert tool_name == "preview_interpretation"
    assert params == {}


def test_latest_intent_apply_turn_rejects_repeat_validate():
    tool_name, params = normalize_tool_call(
        "validate_interpretation",
        {"candidate_id": "latest"},
        latest_user_text="Apply it.",
    )

    assert tool_name == "apply_interpretation"
    assert params == {"candidate_id": "latest"}


def test_latest_intent_validate_turn_rejects_repeat_reload():
    tool_name, params = normalize_tool_call(
        "reload_interpretation_recipe",
        {"recipe_path": "/recipes/import_recipe.json"},
        latest_user_text="Validate the reloaded candidate.",
    )

    assert tool_name == "validate_interpretation"
    assert params == {}
