from typing import Any, cast

from XBrainLab.llm.agent.verifier import (
    FrequencyRangeValidator,
    PathExistsValidator,
    PlaceholderArgumentValidator,
    ToolSchemaValidator,
    TrainingParamValidator,
    VerificationLayer,
    VerificationResult,
)


def _error_message(result: VerificationResult) -> str:
    assert result.error_message is not None
    return result.error_message


def test_verification_script_syntax():
    """Test that Verifier catches basic syntax errors in tool calls."""
    verifier = VerificationLayer()

    # Valid call
    valid_call = ("load_data", {"paths": ["test.csv"]})
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

    def test_epoch_too_large(self):
        v = TrainingParamValidator()
        r = v.validate("configure_training", {"epoch": 99999})
        assert not r.is_valid
        assert "suspiciously large" in _error_message(r)

    def test_epoch_non_numeric(self):
        v = TrainingParamValidator()
        r = v.validate("configure_training", {"epoch": "lots"})
        assert not r.is_valid

    def test_lr_zero_rejected(self):
        v = TrainingParamValidator()
        r = v.validate("configure_training", {"learning_rate": 0})
        assert not r.is_valid

    def test_lr_ge_one_rejected(self):
        v = TrainingParamValidator()
        r = v.validate("configure_training", {"learning_rate": 1.0})
        assert not r.is_valid

    def test_batch_size_zero_rejected(self):
        v = TrainingParamValidator()
        r = v.validate("configure_training", {"batch_size": 0})
        assert not r.is_valid

    def test_ignores_unrelated_tools(self):
        v = TrainingParamValidator()
        r = v.validate("load_data", {"epoch": -1})
        assert r.is_valid


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


# ---------------------------------------------------------------------------
# Path Exists Validator
# ---------------------------------------------------------------------------


class TestPathExistsValidator:
    def test_existing_path_passes(self, tmp_path):
        v = PathExistsValidator()
        r = v.validate("load_data", {"file_path": str(tmp_path)})
        assert r.is_valid

    def test_nonexistent_path_rejected(self):
        v = PathExistsValidator()
        r = v.validate("load_data", {"file_path": "/nonexistent/path/xyz"})
        assert not r.is_valid
        assert "does not exist" in _error_message(r)

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
