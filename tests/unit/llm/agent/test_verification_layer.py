from XBrainLab.llm.agent.verifier import (
    FrequencyRangeValidator,
    PathExistsValidator,
    TrainingParamValidator,
    VerificationLayer,
    VerificationResult,
)


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
    assert "Confidence too low" in result.error_message


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
    result = verifier.verify_tool_call(("not a tuple",), 0.9)
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
        assert "must be <" in r.error_message

    def test_equal_rejected(self):
        v = FrequencyRangeValidator()
        r = v.validate("apply_bandpass_filter", {"low_freq": 10.0, "high_freq": 10.0})
        assert not r.is_valid

    def test_negative_rejected(self):
        v = FrequencyRangeValidator()
        r = v.validate("apply_bandpass_filter", {"low_freq": -1, "high_freq": 40})
        assert not r.is_valid
        assert "positive" in r.error_message

    def test_non_numeric_rejected(self):
        v = FrequencyRangeValidator()
        r = v.validate("apply_bandpass_filter", {"low_freq": "abc", "high_freq": 40})
        assert not r.is_valid
        assert "numeric" in r.error_message

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
        assert "suspiciously large" in r.error_message

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
        assert "does not exist" in r.error_message

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
# VerificationLayer integration with validators
# ---------------------------------------------------------------------------


class TestVerificationLayerWithValidators:
    def test_validators_run_on_valid_structure(self):
        v = VerificationLayer()
        r = v.verify_tool_call(
            ("apply_bandpass_filter", {"low_freq": 50, "high_freq": 10})
        )
        assert not r.is_valid
        assert "must be <" in r.error_message

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
