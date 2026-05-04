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
    assert params == {}


def test_latest_intent_validate_turn_rejects_repeat_reload():
    tool_name, params = normalize_tool_call(
        "reload_interpretation_recipe",
        {"recipe_path": "/recipes/import_recipe.json"},
        latest_user_text="Validate the reloaded candidate.",
    )

    assert tool_name == "validate_interpretation"
    assert params == {}


def test_latest_intent_create_epoch_rejects_generate_dataset_substitute():
    tool_name, params = normalize_tool_call(
        "generate_dataset",
        {"split_strategy": "trial"},
        latest_user_text="Create epochs for event BAD_EVENT from -0.1 to 0.5 seconds.",
    )

    assert tool_name == "epoch_data"
    assert params == {
        "event_id": ["BAD_EVENT"],
        "t_min": -0.1,
        "t_max": 0.5,
    }


def test_epoch_without_window_uses_safe_defaults_from_latest_intent():
    tool_name, params = normalize_tool_call(
        "epoch_data",
        {"t_min": 0, "t_max": 1000, "event_id": [770]},
        latest_user_text="Create epochs for event 770.",
    )

    assert tool_name == "epoch_data"
    assert params == {"event_id": ["770"], "t_min": -0.1, "t_max": 1.0}


def test_epoch_extracts_multiple_event_ids_from_latest_intent():
    tool_name, params = normalize_tool_call(
        "epoch_data",
        {},
        latest_user_text="Create epochs for events left and right from 0.0 to 0.25 seconds.",
    )

    assert tool_name == "epoch_data"
    assert params == {"event_id": ["left", "right"], "t_min": 0.0, "t_max": 0.25}


def test_bandpass_without_arguments_extracts_frequency_range_from_text():
    tool_name, params = normalize_tool_call(
        "apply_bandpass_filter",
        {},
        latest_user_text="Apply 8 to 30 Hz bandpass.",
    )

    assert tool_name == "apply_bandpass_filter"
    assert params == {"low_freq": 8.0, "high_freq": 30.0}


def test_bandpass_only_demotes_standard_preprocess_substitute():
    tool_name, params = normalize_tool_call(
        "apply_standard_preprocess",
        {"l_freq": 1.0, "h_freq": 45.0},
        latest_user_text="Apply 1 to 45 Hz bandpass.",
    )

    assert tool_name == "apply_bandpass_filter"
    assert params == {"low_freq": 1.0, "high_freq": 45.0}


def test_scan_intent_promotes_legacy_load_data_to_scan_source():
    tool_name, params = normalize_tool_call(
        "load_data",
        {"paths": ["/data/A01T.gdf"]},
        latest_user_text="Scan data source /data/A01T.gdf",
    )

    assert tool_name == "scan_source"
    assert params == {"source_path": "/data/A01T.gdf"}


def test_reload_recipe_intent_promotes_scan_source_to_recipe_reload():
    tool_name, params = normalize_tool_call(
        "scan_source",
        {"source_path": "/recipes/import_recipe.json"},
        latest_user_text="Reload recipe /recipes/import_recipe.json",
    )

    assert tool_name == "reload_interpretation_recipe"
    assert params == {"recipe_path": "/recipes/import_recipe.json"}


def test_preview_normalizes_flat_metadata_choices():
    tool_name, params = normalize_tool_call(
        "preview_interpretation",
        {"session": "ses-01"},
        latest_user_text="Preview with subject S01 session ses-01 task motor run 02.",
    )

    assert tool_name == "preview_interpretation"
    assert params == {
        "choices": {
            "session": "ses-01",
            "subject": "S01",
            "task": "motor",
            "run": "02",
        }
    }


def test_preview_drops_placeholder_scan_id_for_latest_state():
    tool_name, params = normalize_tool_call(
        "preview_interpretation",
        {"scan_id": "latest_scan_id"},
        latest_user_text="Preview the latest Data Interpretation candidate.",
    )

    assert tool_name == "preview_interpretation"
    assert params == {}


def test_preview_keeps_backend_generated_scan_id():
    tool_name, params = normalize_tool_call(
        "preview_interpretation",
        {"scan_id": "scan-2"},
        latest_user_text="Preview scan-2.",
    )

    assert tool_name == "preview_interpretation"
    assert params == {"scan_id": "scan-2"}


def test_validate_drops_placeholder_candidate_id_for_latest_state():
    tool_name, params = normalize_tool_call(
        "validate_interpretation",
        {"candidate_id": "current_candidate"},
        latest_user_text="Validate the latest Data Interpretation candidate.",
    )

    assert tool_name == "validate_interpretation"
    assert params == {}


def test_generate_dataset_normalizes_split_and_training_mode_from_text():
    tool_name, params = normalize_tool_call(
        "generate_dataset",
        {},
        latest_user_text="Generate a group dataset with subject split.",
    )

    assert tool_name == "generate_dataset"
    assert params == {
        "split_strategy": "subject",
        "training_mode": "group",
        "val_ratio": 0.2,
    }


def test_generate_dataset_moves_group_split_to_training_mode():
    tool_name, params = normalize_tool_call(
        "generate_dataset",
        {"split_strategy": "group", "training_mode": "group", "test_ratio": 0.2},
        latest_user_text="Generate a group training dataset with 20% test split.",
    )

    assert tool_name == "generate_dataset"
    assert params == {
        "split_strategy": "trial",
        "training_mode": "group",
        "test_ratio": 0.2,
        "val_ratio": 0.2,
    }


def test_apply_interpretation_adds_confirmed_from_latest_text():
    tool_name, params = normalize_tool_call(
        "apply_interpretation",
        {},
        latest_user_text="Yes, apply it.",
    )

    assert tool_name == "apply_interpretation"
    assert params == {"confirmed": True}


def test_scan_source_removes_invalid_source_hint_and_fills_path():
    tool_name, params = normalize_tool_call(
        "scan_source",
        {"source_hint": "session"},
        latest_user_text="Scan data source /data/session01",
    )

    assert tool_name == "scan_source"
    assert params == {"source_path": "/data/session01"}


def test_model_selection_promotes_empty_configure_training_to_set_model():
    tool_name, params = normalize_tool_call(
        "configure_training",
        {"epoch": None, "batch_size": None, "learning_rate": None},
        latest_user_text="Use EEGNet as the model.",
    )

    assert tool_name == "set_model"
    assert params == {"model_name": "EEGNet"}
