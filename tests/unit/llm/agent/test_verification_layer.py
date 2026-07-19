import logging
from typing import Any, cast

import pytest

from XBrainLab.llm.agent.verifier import (
    FrequencyRangeValidator,
    PathExistsValidator,
    PathProvenanceVerifier,
    PlaceholderArgumentValidator,
    ToolSchemaValidator,
    TrainingParamValidator,
    ValidatorStrategy,
    VerificationLayer,
    VerificationResult,
)
from XBrainLab.llm.tools.definitions.dataset_def import (
    BaseLoadDataTool,
    BasePreviewInterpretationTool,
)
from XBrainLab.llm.tools.definitions.training_def import BaseConfigureTrainingTool


def _error_message(result: VerificationResult) -> str:
    assert result.error_message is not None
    return result.error_message


def test_verification_script_syntax(tmp_path):
    """Test that Verifier catches basic syntax errors in tool calls."""
    verifier = VerificationLayer()

    # Valid call
    source = tmp_path / "test.csv"
    source.touch()
    valid_call = ("load_data", {"paths": [str(source)]})
    result = verifier.verify_tool_call(valid_call, confidence=0.9)
    assert result.is_valid
    assert result.error_message is None

    # Invalid call (missing mandatory param - simulated by catching logic error if we had strict schema info,
    # but for now we might just check structure)
    # Actually, Verifier might simpler checks first.

    # Let's test confidence first
    result = verifier.verify_tool_call(valid_call, confidence=0.1)
    assert not result.is_valid
    assert "Confidence too low" in _error_message(result)


def test_verification_result_structure():
    """Test the result object structure."""
    res = VerificationResult(is_valid=True, error_message=None)
    assert res.is_valid

    res = VerificationResult(is_valid=False, error_message="Fail")
    assert not res.is_valid


def test_script_validation_logic():
    """
    Test custom script validation logic if any.
    For now, we verify that it accepts valid tuples.
    """
    verifier = VerificationLayer()

    # Malformed tool call (not a tuple of (name, dict))
    # Should return invalid VerificationResult (not raise)
    result = verifier.verify_tool_call(cast(Any, ("not a tuple",)), 0.9)
    assert not result.is_valid

    # Valid structure
    res = verifier.verify_tool_call(("tool", {}), 0.9)
    assert res.is_valid


# ---------------------------------------------------------------------------
# Frequency Range Validator
# ---------------------------------------------------------------------------


class TestFrequencyRangeValidator:
    def test_valid_bandpass(self):
        v = FrequencyRangeValidator()
        r = v.validate("apply_bandpass_filter", {"low_freq": 1.0, "high_freq": 40.0})
        assert r.is_valid

    def test_low_ge_high_rejected(self):
        v = FrequencyRangeValidator()
        r = v.validate("apply_bandpass_filter", {"low_freq": 50.0, "high_freq": 10.0})
        assert not r.is_valid
        assert "must be <" in _error_message(r)

    def test_equal_rejected(self):
        v = FrequencyRangeValidator()
        r = v.validate("apply_bandpass_filter", {"low_freq": 10.0, "high_freq": 10.0})
        assert not r.is_valid

    def test_negative_rejected(self):
        v = FrequencyRangeValidator()
        r = v.validate("apply_bandpass_filter", {"low_freq": -1, "high_freq": 40})
        assert not r.is_valid
        assert "positive" in _error_message(r)

    def test_non_numeric_rejected(self):
        v = FrequencyRangeValidator()
        r = v.validate("apply_bandpass_filter", {"low_freq": "abc", "high_freq": 40})
        assert not r.is_valid
        assert "numeric" in _error_message(r)

    def test_standard_preprocess_uses_l_h_freq(self):
        v = FrequencyRangeValidator()
        r = v.validate("apply_standard_preprocess", {"l_freq": 50, "h_freq": 10})
        assert not r.is_valid

    def test_ignores_unrelated_tools(self):
        v = FrequencyRangeValidator()
        r = v.validate("load_data", {"path": "/tmp"})
        assert r.is_valid

    def test_partial_params_ok(self):
        v = FrequencyRangeValidator()
        r = v.validate("apply_bandpass_filter", {"low_freq": 1.0})
        assert r.is_valid


# ---------------------------------------------------------------------------
# Training Param Validator
# ---------------------------------------------------------------------------


class TestTrainingParamValidator:
    def test_valid_params(self):
        v = TrainingParamValidator()
        r = v.validate(
            "configure_training",
            {"epoch": 10, "learning_rate": 0.001, "batch_size": 32},
        )
        assert r.is_valid

    def test_epoch_zero_rejected(self):
        v = TrainingParamValidator()
        r = v.validate("configure_training", {"epoch": 0})
        assert not r.is_valid

    def test_epoch_negative_rejected(self):
        v = TrainingParamValidator()
        r = v.validate("configure_training", {"epoch": -5})
        assert not r.is_valid

    def test_large_positive_epoch_matches_backend_contract(self):
        v = TrainingParamValidator()
        r = v.validate(
            "configure_training",
            {"epoch": 99999, "batch_size": 32, "learning_rate": 0.001},
        )
        assert r.is_valid

    def test_epoch_non_numeric(self):
        v = TrainingParamValidator()
        r = v.validate("configure_training", {"epoch": "lots"})
        assert not r.is_valid

    def test_lr_zero_rejected(self):
        v = TrainingParamValidator()
        r = v.validate("configure_training", {"learning_rate": 0})
        assert not r.is_valid

    def test_lr_one_matches_backend_positive_finite_contract(self):
        v = TrainingParamValidator()
        r = v.validate(
            "configure_training",
            {"epoch": 10, "batch_size": 32, "learning_rate": 1.0},
        )
        assert r.is_valid

    def test_missing_training_option_is_rejected(self):
        v = TrainingParamValidator()
        r = v.validate(
            "configure_training",
            {"epoch": 10, "learning_rate": 0.001},
        )
        assert not r.is_valid
        assert "batch_size" in _error_message(r)

    def test_batch_size_zero_rejected(self):
        v = TrainingParamValidator()
        r = v.validate("configure_training", {"batch_size": 0})
        assert not r.is_valid

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("repeat", 0),
            ("repeat", -1),
            ("repeat", 1.75),
            ("save_checkpoints_every", -1),
            ("save_checkpoints_every", 2.9),
        ],
    )
    def test_optional_integer_contract_matches_execution(
        self,
        field: str,
        value: object,
    ) -> None:
        validator = TrainingParamValidator()
        params: dict[str, object] = {
            "epoch": 10,
            "batch_size": 32,
            "learning_rate": 0.001,
            field: value,
        }

        result = validator.validate("configure_training", params)

        assert not result.is_valid
        assert field in _error_message(result)

    def test_ignores_unrelated_tools(self):
        v = TrainingParamValidator()
        r = v.validate("load_data", {"epoch": -1})
        assert r.is_valid


def test_training_schema_requires_native_json_numeric_values():
    verifier = VerificationLayer(
        tool_schemas={
            "configure_training": BaseConfigureTrainingTool().parameters,
        }
    )

    string_result = verifier.verify_tool_call(
        (
            "configure_training",
            {"epoch": "10", "batch_size": 32.0, "learning_rate": "0.001"},
        )
    )
    typed_result = verifier.verify_tool_call(
        (
            "configure_training",
            {"epoch": 10, "batch_size": 32, "learning_rate": 0.001},
        )
    )

    assert not string_result.is_valid
    assert typed_result.is_valid


# ---------------------------------------------------------------------------
# Tool Schema Validator
# ---------------------------------------------------------------------------


class TestToolSchemaValidator:
    def test_missing_required_param_rejected(self):
        v = ToolSchemaValidator(
            {
                "scan_source": {
                    "type": "object",
                    "properties": {"source_path": {"type": "string"}},
                    "required": ["source_path"],
                }
            }
        )
        r = v.validate("scan_source", {})
        assert not r.is_valid
        assert "Missing required" in _error_message(r)

    def test_type_mismatch_rejected(self):
        v = ToolSchemaValidator(
            {
                "epoch_data": {
                    "type": "object",
                    "properties": {"event_id": {"type": "array"}},
                }
            }
        )
        r = v.validate("epoch_data", {"event_id": 769})
        assert not r.is_valid
        assert "event_id must be array" in _error_message(r)

    def test_enum_mismatch_rejected(self):
        v = ToolSchemaValidator(
            {
                "generate_dataset": {
                    "type": "object",
                    "properties": {
                        "split_strategy": {
                            "type": "string",
                            "enum": ["trial", "session", "subject"],
                        }
                    },
                }
            }
        )
        r = v.validate("generate_dataset", {"split_strategy": "individual"})
        assert not r.is_valid
        assert "split_strategy must be one of" in _error_message(r)

    @pytest.mark.parametrize(
        ("schema", "value"),
        [
            ({"type": ["integer", "number", "string"], "minimum": 1}, 0),
            ({"type": ["number", "string"], "exclusiveMinimum": 0}, 0),
            ({"type": ["number", "string"], "maximum": 1}, 2),
            ({"type": ["number", "string"], "exclusiveMaximum": 1}, 1),
        ],
    )
    def test_numeric_bounds_are_enforced(
        self,
        schema: dict[str, object],
        value: object,
    ) -> None:
        validator = ToolSchemaValidator(
            {
                "configure": {
                    "type": "object",
                    "properties": {"value": schema},
                }
            }
        )

        result = validator.validate("configure", {"value": value})

        assert not result.is_valid
        assert "value" in _error_message(result)

    def test_enum_accepts_case_variants(self):
        v = ToolSchemaValidator(
            {
                "set_model": {
                    "type": "object",
                    "properties": {
                        "model_name": {
                            "type": "string",
                            "enum": ["EEGNet", "ShallowConvNet", "SCCNet"],
                        }
                    },
                }
            }
        )
        r = v.validate("set_model", {"model_name": "eegnet"})
        assert r.is_valid

    def test_unknown_tool_rejected(self):
        v = ToolSchemaValidator({"scan_source": {"type": "object"}})
        r = v.validate("create_epoch", {})
        assert not r.is_valid
        assert "not registered" in _error_message(r)

    def test_unknown_root_parameter_rejected_by_default(self):
        v = ToolSchemaValidator(
            {
                "scan_source": {
                    "type": "object",
                    "properties": {"source_path": {"type": "string"}},
                    "required": ["source_path"],
                }
            }
        )
        r = v.validate(
            "scan_source",
            {"source_path": "/data/A01T.gdf", "unexpected": True},
        )
        assert not r.is_valid
        assert "Unknown parameter" in _error_message(r)

    def test_nested_object_schema_rejects_unknown_preview_choice(self):
        v = ToolSchemaValidator(
            {
                "preview_interpretation": {
                    "type": "object",
                    "properties": {
                        "choices": {
                            "type": "object",
                            "properties": {"subject": {"type": "string"}},
                            "additionalProperties": False,
                        }
                    },
                }
            }
        )
        r = v.validate(
            "preview_interpretation",
            {"choices": {"subject": "S01", "debug_trace": "x"}},
        )
        assert not r.is_valid
        assert "choices" in _error_message(r)

    def test_preview_choice_schema_accepts_recipe_remap_mappings(self):
        v = ToolSchemaValidator(
            {"preview_interpretation": BasePreviewInterpretationTool().parameters}
        )

        r = v.validate(
            "preview_interpretation",
            {
                "choices": {
                    "eeg_file_remap": {
                        "/recipe/sub-01_task-mi_raw.fif": "/data/sub-01_raw.fif",
                    },
                    "label_carrier_remap": {
                        "/recipe/events.tsv": "/data/events.tsv",
                    },
                    "label_carrier_choices": {
                        "/data/events.tsv": {
                            "label_field": "trial_type",
                            "anchor": "onset",
                            "time_model": "seconds",
                            "granularity": "trial",
                            "target_file": "/data/sub-01_raw.fif",
                        }
                    },
                }
            },
        )

        assert r.is_valid


# ---------------------------------------------------------------------------
# Path Exists Validator
# ---------------------------------------------------------------------------


class TestPathExistsValidator:
    def test_existing_load_data_paths_pass(self, tmp_path):
        first = tmp_path / "subject-a.edf"
        second = tmp_path / "subject-b.fif"
        first.touch()
        second.touch()
        v = PathExistsValidator()
        r = v.validate("load_data", {"paths": [str(first), str(second)]})
        assert r.is_valid

    def test_mixed_existing_and_nonexistent_load_data_paths_are_rejected(
        self,
        tmp_path,
    ):
        existing = tmp_path / "recording.set"
        missing = tmp_path / "missing.vhdr"
        existing.touch()
        v = PathExistsValidator()
        r = v.validate("load_data", {"paths": [str(existing), str(missing)]})
        assert not r.is_valid
        assert "does not exist" in _error_message(r)
        assert str(missing) in _error_message(r)

    def test_each_nonexistent_load_data_path_is_rejected(self, tmp_path):
        first = tmp_path / "missing-a.gdf"
        second = tmp_path / "missing-b.cnt"
        v = PathExistsValidator()

        for missing in (first, second):
            r = v.validate("load_data", {"paths": [str(missing)]})

            assert not r.is_valid
            assert str(missing) in _error_message(r)

    @pytest.mark.parametrize(
        ("tool_name", "field_name", "filename"),
        [
            ("list_files", "directory", "missing-session"),
            ("scan_source", "source_path", "missing-source.edf"),
            (
                "reload_interpretation_recipe",
                "recipe_path",
                "missing-recipe.json",
            ),
        ],
    )
    def test_nonexistent_scalar_input_paths_are_rejected(
        self,
        tmp_path,
        tool_name: str,
        field_name: str,
        filename: str,
    ) -> None:
        missing = tmp_path / filename

        result = PathExistsValidator().validate(
            tool_name,
            {field_name: str(missing)},
        )

        assert not result.is_valid
        assert str(missing) in _error_message(result)

    def test_directory_param(self, tmp_path):
        v = PathExistsValidator()
        r = v.validate("list_files", {"directory": str(tmp_path)})
        assert r.is_valid

    def test_ignores_unrelated_tools(self):
        v = PathExistsValidator()
        r = v.validate("configure_training", {"path": "/nonexistent"})
        assert r.is_valid

    def test_no_path_param_passes(self):
        v = PathExistsValidator()
        r = v.validate("load_data", {"other": "value"})
        assert r.is_valid


class TestPathProvenanceVerifier:
    def test_accepts_path_explicitly_provided_in_latest_user_turn(self, tmp_path):
        source = tmp_path / "A01T.gdf"
        source.touch()

        result = PathProvenanceVerifier().validate(
            "scan_source",
            {"source_path": str(source)},
            latest_user_text=f"Import `{source}`",
            state=None,
        )

        assert result.is_valid

    def test_rejects_model_invented_existing_absolute_path(self, tmp_path):
        invented = tmp_path / "private"
        invented.mkdir()

        result = PathProvenanceVerifier().validate(
            "list_files",
            {"directory": str(invented)},
            latest_user_text="Show my EEG files",
            state=None,
        )

        assert not result.is_valid
        assert "choose a file or folder" in _error_message(result).lower()

    def test_accepts_descendant_of_backend_selected_source_root(self, tmp_path):
        selected = tmp_path / "selected"
        nested = selected / "sub-01"
        nested.mkdir(parents=True)
        state = {
            "interpretation": {
                "source_path": str(selected),
                "source_kind": "folder",
            }
        }

        result = PathProvenanceVerifier().validate(
            "list_files",
            {"directory": str(nested)},
            latest_user_text="Show the selected source files",
            state=state,
        )

        assert result.is_valid

    def test_selected_file_does_not_authorize_sibling_path(self, tmp_path):
        selected = tmp_path / "A01T.gdf"
        sibling = tmp_path / "secret.txt"
        selected.touch()
        sibling.touch()
        state = {
            "interpretation": {
                "source_path": str(selected),
                "source_kind": "file",
            }
        }

        result = PathProvenanceVerifier().validate(
            "scan_source",
            {"source_path": str(sibling)},
            latest_user_text="Rescan the selected EEG file",
            state=state,
        )

        assert not result.is_valid

    def test_windows_path_comparison_is_case_insensitive(self):
        result = PathProvenanceVerifier().validate(
            "scan_source",
            {"source_path": r"C:\Data\Subject01\A01T.gdf"},
            latest_user_text=r"Import C:\DATA\Subject01\A01T.gdf",
            state=None,
        )

        assert result.is_valid

    def test_latest_turn_exact_spaced_path_satisfies_provenance(self, tmp_path):
        source = tmp_path / "subject one" / "A01T.gdf"
        source.parent.mkdir()
        source.touch()

        result = PathProvenanceVerifier().validate(
            "scan_source",
            {"source_path": str(source)},
            latest_user_text=f"Import {source} now",
            state=None,
        )

        assert result.is_valid

    def test_user_path_prefix_does_not_authorize_shorter_path(self):
        result = PathProvenanceVerifier().validate(
            "list_files",
            {"directory": "/home"},
            latest_user_text="List files in /homeevil",
            state=None,
        )

        assert not result.is_valid

    def test_mixed_approved_and_unapproved_load_paths_fail_closed(self, tmp_path):
        approved = tmp_path / "approved.edf"
        protected = tmp_path / "protected.edf"
        approved.touch()
        protected.touch()

        result = PathProvenanceVerifier().validate(
            "load_data",
            {"paths": [str(approved), str(protected)]},
            latest_user_text=f"Load {approved}",
            state=None,
        )

        assert not result.is_valid
        assert "choose a file or folder" in _error_message(result).lower()

    @pytest.mark.parametrize(
        ("tool_name", "params"),
        [
            ("list_files", {"directory": "/protected/session"}),
            ("scan_source", {"source_path": "/protected/source.edf"}),
            (
                "preview_interpretation",
                {"choices": {"selected_eeg_files": ["/protected/preview.fif"]}},
            ),
            (
                "save_interpretation_recipe",
                {"recipe_path": "/protected/output-recipe.json"},
            ),
            (
                "reload_interpretation_recipe",
                {"recipe_path": "/protected/input-recipe.json"},
            ),
            ("load_data", {"paths": ["/protected/recording.gdf"]}),
            (
                "attach_labels",
                {"mapping": {"recording.gdf": "/protected/labels.tsv"}},
            ),
        ],
    )
    def test_each_path_bearing_tool_schema_rejects_unapproved_paths(
        self,
        tool_name: str,
        params: dict[str, object],
    ) -> None:
        result = PathProvenanceVerifier().validate(
            tool_name,
            params,
            latest_user_text="Use the current dataset",
            state=None,
        )

        assert not result.is_valid
        assert "choose a file or folder" in _error_message(result).lower()

    @pytest.mark.parametrize(
        "choices",
        [
            {"selected_eeg_files": ["/private/selected.edf"]},
            {"label_sources": ["/private/external-events.tsv"]},
            {"required_label_carriers": ["/private/required-events.csv"]},
            {"excluded_label_carriers": ["/private/excluded-events.mat"]},
            {"eeg_file_remap": {"/private/saved.edf": "current.edf"}},
            {"eeg_file_remap": {"saved.edf": "/private/current.edf"}},
            {"label_carrier_remap": {"/private/saved-events.tsv": "events.tsv"}},
            {
                "label_carrier_remap": {
                    "saved-events.tsv": "/private/current-events.tsv"
                }
            },
            {
                "label_carrier_choices": {
                    "/private/events.tsv": {"label_field": "trial_type"}
                }
            },
            {
                "label_carrier_choices": {
                    "events.tsv": {"target_file": "/private/target.fif"}
                }
            },
            {"run_event_mappings": {"/private/run.gdf": {"769": "left"}}},
            {"metadata_overrides": {"/private/session.set": {"subject": "01"}}},
        ],
    )
    def test_preview_path_containers_preserve_fail_closed_provenance(
        self,
        choices: dict[str, object],
    ) -> None:
        result = PathProvenanceVerifier().validate(
            "preview_interpretation",
            {"choices": choices},
            latest_user_text="Preview the current import choices",
            state=None,
        )

        assert not result.is_valid
        assert "choose a file or folder" in _error_message(result).lower()


# ---------------------------------------------------------------------------
# Placeholder Argument Validator
# ---------------------------------------------------------------------------


class TestPlaceholderArgumentValidator:
    def test_rejects_placeholder_scan_source_path(self):
        v = PlaceholderArgumentValidator()
        r = v.validate("scan_source", {"source_path": "path_to_eeg_dataset"})
        assert not r.is_valid
        assert "actual path" in _error_message(r)

    def test_rejects_blank_scan_source_path(self):
        v = PlaceholderArgumentValidator()
        r = v.validate("scan_source", {"source_path": ""})
        assert not r.is_valid
        assert "actual path" in _error_message(r)

    def test_rejects_placeholder_load_data_path_list(self):
        v = PlaceholderArgumentValidator()
        r = v.validate(
            "load_data",
            {"paths": ["/path/to/your/eeg/file.gdf"]},
        )
        assert not r.is_valid
        assert "actual path" in _error_message(r)

    def test_rejects_placeholder_after_real_load_data_path(self, tmp_path):
        existing = tmp_path / "real.edf"
        existing.touch()
        v = PlaceholderArgumentValidator()

        r = v.validate(
            "load_data",
            {"paths": [str(existing), "/path/to/your/recording.edf"]},
        )

        assert not r.is_valid
        assert "actual path" in _error_message(r)

    def test_rejects_natural_language_placeholder_absolute_path(self):
        v = PlaceholderArgumentValidator()
        r = v.validate(
            "scan_source",
            {"source_path": "/path/with/EEG/file"},
        )

        assert not r.is_valid
        assert "actual path" in _error_message(r)

    def test_rejects_placeholder_recipe_path(self):
        v = PlaceholderArgumentValidator()
        r = v.validate(
            "reload_interpretation_recipe",
            {"recipe_path": "path_to_recipe.json"},
        )
        assert not r.is_valid

    def test_rejects_relative_scan_source_path(self):
        v = PlaceholderArgumentValidator()
        r = v.validate("scan_source", {"source_path": "datasets/session01"})
        assert not r.is_valid
        assert "absolute path" in _error_message(r)

    def test_rejects_relative_recipe_path(self):
        v = PlaceholderArgumentValidator()
        r = v.validate(
            "reload_interpretation_recipe",
            {"recipe_path": "import_recipe.json"},
        )
        assert not r.is_valid
        assert "absolute path" in _error_message(r)

    def test_rejects_path_to_your_recipe(self):
        v = PlaceholderArgumentValidator()
        r = v.validate(
            "reload_interpretation_recipe",
            {"recipe_path": "path/to/your/recipe.json"},
        )
        assert not r.is_valid

    def test_rejects_instruction_text_in_path_field(self):
        v = PlaceholderArgumentValidator()
        r = v.validate(
            "scan_source",
            {"source_path": "Please provide the absolute path to your EEG dataset."},
        )
        assert not r.is_valid

    def test_allows_realistic_absolute_path(self):
        v = PlaceholderArgumentValidator()
        r = v.validate("scan_source", {"source_path": "/data/S01.gdf"})
        assert r.is_valid

    def test_allows_windows_absolute_source_path(self):
        v = PlaceholderArgumentValidator()
        r = v.validate("scan_source", {"source_path": r"C:\data\S01.gdf"})
        assert r.is_valid

    def test_rejects_placeholder_preview_recipe_remap_target(self):
        v = PlaceholderArgumentValidator()
        r = v.validate(
            "preview_interpretation",
            {
                "choices": {
                    "eeg_file_remap": {
                        "missing saved EEG file": (
                            "current replacement EEG file path/name"
                        )
                    }
                }
            },
        )

        assert not r.is_valid
        assert r.error_message is not None
        assert "remap target" in r.error_message

    @pytest.mark.parametrize(
        ("tool_name", "params"),
        [
            ("list_files", {"directory": "/path/to/files"}),
            (
                "scan_source",
                {
                    "source_path": "/data/source.edf",
                    "label_sources": ["/path/to/labels.tsv"],
                },
            ),
            (
                "preview_interpretation",
                {
                    "choices": {
                        "label_carrier_remap": {
                            "saved-events.tsv": "/path/to/current-events.tsv"
                        }
                    }
                },
            ),
            (
                "save_interpretation_recipe",
                {"recipe_path": "/path/to/output-recipe.json"},
            ),
            (
                "reload_interpretation_recipe",
                {"recipe_path": "/path/to/input-recipe.json"},
            ),
            ("load_data", {"paths": ["/path/to/recording.gdf"]}),
            (
                "attach_labels",
                {"mapping": {"recording.gdf": "/path/to/labels.csv"}},
            ),
        ],
    )
    def test_each_path_bearing_tool_schema_rejects_placeholder_values(
        self,
        tool_name: str,
        params: dict[str, object],
    ) -> None:
        result = PlaceholderArgumentValidator().validate(tool_name, params)

        assert not result.is_valid
        assert "path" in _error_message(result).lower()

    def test_ignores_non_path_values(self):
        v = PlaceholderArgumentValidator()
        r = v.validate("epoch_data", {"event_id": ["BAD_EVENT"]})
        assert r.is_valid


# ---------------------------------------------------------------------------
# VerificationLayer integration with validators
# ---------------------------------------------------------------------------


class TestVerificationLayerWithValidators:
    def test_validators_run_on_valid_structure(self):
        v = VerificationLayer()
        r = v.verify_tool_call(
            ("apply_bandpass_filter", {"low_freq": 50, "high_freq": 10})
        )
        assert not r.is_valid
        assert "must be <" in _error_message(r)

    def test_custom_validators(self):
        v = VerificationLayer(validators=[FrequencyRangeValidator()])
        r = v.verify_tool_call(
            ("apply_bandpass_filter", {"low_freq": 1, "high_freq": 40})
        )
        assert r.is_valid

    def test_empty_validators(self):
        v = VerificationLayer(validators=[])
        r = v.verify_tool_call(("anything", {"epoch": -999}))
        assert r.is_valid  # no validators = no parameter rejection

    def test_tool_schema_validation_runs_before_execution_validators(self):
        v = VerificationLayer(
            validators=[],
            tool_schemas={
                "scan_source": {
                    "type": "object",
                    "properties": {"source_path": {"type": "string"}},
                    "required": ["source_path"],
                }
            },
        )
        r = v.verify_tool_call(("scan_source", {}))
        assert not r.is_valid
        assert "Missing required" in _error_message(r)

    def test_default_validators_reject_placeholder_paths(self):
        v = VerificationLayer()
        r = v.verify_tool_call(("scan_source", {"source_path": "/path/to/eeg/data"}))
        assert not r.is_valid
        assert "actual path" in _error_message(r)

    def test_load_data_schema_rejects_unsupported_file_path_key(self, tmp_path):
        source = tmp_path / "source.edf"
        source.touch()
        v = VerificationLayer(
            tool_schemas={"load_data": BaseLoadDataTool().parameters},
        )

        r = v.verify_tool_call(
            (
                "load_data",
                {"paths": [str(source)], "file_path": str(source)},
            )
        )

        assert not r.is_valid
        assert "Unknown parameter for load_data: file_path" in _error_message(r)

    def test_load_data_file_path_cannot_replace_required_paths(self, tmp_path):
        source = tmp_path / "source.edf"
        source.touch()
        v = VerificationLayer(
            tool_schemas={"load_data": BaseLoadDataTool().parameters},
        )

        r = v.verify_tool_call(("load_data", {"file_path": str(source)}))

        assert not r.is_valid
        assert "Missing required parameter(s) for load_data: paths" in _error_message(r)


class _PrivateFailureValidator(ValidatorStrategy):
    def validate(self, name: str, params: dict[str, Any]) -> VerificationResult:
        del name, params
        return VerificationResult(
            False,
            (
                "Could not open /home/alice/private/subject-17/events.tsv; "
                "API key: private-api-value"
            ),
        )


def test_verification_boundary_redacts_public_error_and_validator_log(caplog) -> None:
    verifier = VerificationLayer(validators=[_PrivateFailureValidator()])

    with caplog.at_level(logging.WARNING, logger="XBrainLab.llm.agent.verifier"):
        result = verifier.verify_tool_call(("query_state", {}), confidence=1.0)

    assert result.is_valid is False
    public_error = _error_message(result)
    log_output = "\n".join(record.getMessage() for record in caplog.records)
    for output in (public_error, log_output):
        assert "/home/alice/private/subject-17/events.tsv" not in output
        assert "private-api-value" not in output
        assert "[REDACTED_PATH]" in output
        assert "[REDACTED_SECRET]" in output
