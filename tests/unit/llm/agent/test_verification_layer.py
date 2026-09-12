import logging
from typing import Any, cast

import pytest

from XBrainLab.llm.agent.verifier import (
    FrequencyRangeValidator,
    PlaceholderArgumentValidator,
    ToolSchemaValidator,
    ValidatorStrategy,
    VerificationLayer,
    VerificationResult,
    collect_direct_parameter_reply_evidence,
    verify_direct_parameter_origins,
)


def _error_message(result: VerificationResult) -> str:
    assert result.error_message is not None
    return result.error_message


def test_missing_direct_preprocess_parameters_are_typed_schema_failures() -> None:
    from XBrainLab.llm.tools.definitions.preprocess_def import BaseBandPassFilterTool

    validator = ToolSchemaValidator(
        {"apply_bandpass_filter": BaseBandPassFilterTool().parameters},
    )

    result = validator.validate("apply_bandpass_filter", {"low_freq": 4.0})

    assert result.is_valid is False
    assert "high_freq" in _error_message(result)


def test_zero_parameter_gui_handoff_rejects_model_choices() -> None:
    from XBrainLab.llm.tools import get_all_tools

    tool = next(tool for tool in get_all_tools() if tool.name == "select_model")
    validator = ToolSchemaValidator({tool.name: tool.parameters})

    result = validator.validate("select_model", {"model_name": "EEGNet"})

    assert result.is_valid is False
    assert "Unknown parameter" in _error_message(result)


def test_normalize_method_is_limited_by_the_target_schema() -> None:
    from XBrainLab.llm.tools.definitions.preprocess_def import BaseNormalizeTool

    validator = ToolSchemaValidator(
        {"normalize_data": BaseNormalizeTool().parameters},
    )

    result = validator.validate("normalize_data", {"method": "robust"})

    assert result.is_valid is False
    assert "method must be one of" in _error_message(result)


@pytest.mark.parametrize(
    ("tool_name", "params", "latest_user_text"),
    [
        (
            "apply_bandpass_filter",
            {"low_freq": 4.0, "high_freq": 38},
            "Apply a 4\u201338 Hz bandpass filter.",
        ),
        (
            "apply_bandpass_filter",
            {"low_freq": 4, "high_freq": 38.0},
            "請帶通 4 到 38 Hz。",
        ),
        (
            "apply_notch_filter",
            {"freq": 60},
            "Use a 60 Hz notch filter.",
        ),
        (
            "resample_data",
            {"rate": 128},
            "Resample the EEG data to 128 Hz.",
        ),
        (
            "set_reference",
            {"method": "average"},
            "Set an average reference.",
        ),
        (
            "set_reference",
            {"method": "Cz"},
            "請重新參考到 Cz。",
        ),
        (
            "set_reference",
            {"method": "Cz"},
            "Set Cz as the EEG reference.",
        ),
        (
            "normalize_data",
            {"method": "z-score"},
            "Normalize the EEG epochs using z score.",
        ),
        (
            "normalize_data",
            {"method": "min-max"},
            "請用 min max 正規化。",
        ),
    ],
)
def test_direct_parameter_origins_accept_explicit_latest_user_values(
    tool_name: str,
    params: dict[str, Any],
    latest_user_text: str,
) -> None:
    result = verify_direct_parameter_origins(
        tool_name,
        params,
        latest_user_text,
    )

    assert result == VerificationResult(True)


@pytest.mark.parametrize(
    ("tool_name", "params", "latest_user_text", "expected_question"),
    [
        (
            "apply_bandpass_filter",
            {"low_freq": 4, "high_freq": 38},
            "Apply a bandpass filter.",
            "What low and high cutoff frequencies should I use for the "
            "bandpass filter?",
        ),
        (
            "apply_bandpass_filter",
            {"low_freq": 4, "high_freq": 38},
            "The recording is 16 seconds long.",
            "What low and high cutoff frequencies should I use for the "
            "bandpass filter?",
        ),
        (
            "apply_notch_filter",
            {"freq": 60},
            "The recording has 64 channels.",
            "What notch frequency should I use?",
        ),
        (
            "resample_data",
            {"rate": 128},
            "The current rate is 256 Hz.",
            "What resampling rate should I use?",
        ),
        (
            "set_reference",
            {"method": "average"},
            "Use the median amplitude.",
            "What EEG reference method should I use?",
        ),
        (
            "normalize_data",
            {"method": "z-score"},
            "Use min-max values.",
            "Which normalization method should I use: z-score or min-max?",
        ),
    ],
)
def test_direct_parameter_origins_reject_invented_or_unrelated_values(
    tool_name: str,
    params: dict[str, Any],
    latest_user_text: str,
    expected_question: str,
) -> None:
    result = verify_direct_parameter_origins(
        tool_name,
        params,
        latest_user_text,
    )

    assert result == VerificationResult(False, expected_question)


def test_direct_parameter_origins_ignore_non_direct_tools() -> None:
    result = verify_direct_parameter_origins(
        "switch_panel",
        {"panel_name": "dataset"},
        "Open the Dataset panel.",
    )

    assert result == VerificationResult(True)


def test_direct_parameter_verifiers_reject_word_number_frequency() -> None:
    params = {"freq": 50}
    text = "Apply a notch filter at fifty hertz."

    assert (
        verify_direct_parameter_origins("apply_notch_filter", params, text).is_valid
        is False
    )
    assert (
        collect_direct_parameter_reply_evidence(
            "apply_notch_filter", (), None, "fifty hertz"
        )
        is None
    )


@pytest.mark.parametrize(
    ("tool_name", "text", "expected"),
    (
        ("apply_notch_filter", "50 Hz", (("freq", 50),)),
        ("resample_data", "128 Hz", (("rate", 128),)),
        ("set_reference", "average", (("method", "average"),)),
        ("normalize_data", "z-score", (("method", "z-score"),)),
    ),
)
def test_direct_form_collects_only_current_user_values_for_single_field_tools(
    tool_name: str,
    text: str,
    expected: tuple[tuple[str, object], ...],
) -> None:
    evidence = collect_direct_parameter_reply_evidence(
        tool_name,
        (),
        None,
        text,
    )

    assert evidence == (expected, None)


def test_direct_form_collects_bare_bandpass_values_without_host_label_mapping() -> None:
    first = collect_direct_parameter_reply_evidence(
        "apply_bandpass_filter", (), None, "12"
    )
    second = collect_direct_parameter_reply_evidence(
        "apply_bandpass_filter", (), 12, "40"
    )
    same_reply = collect_direct_parameter_reply_evidence(
        "apply_bandpass_filter", (), None, "40 12"
    )
    sole_remaining = collect_direct_parameter_reply_evidence(
        "apply_bandpass_filter", (("low_freq", 12),), None, "40 Hz"
    )

    assert first == ((), 12)
    assert second == ((("low_freq", 12), ("high_freq", 40)), None)
    assert same_reply == ((("low_freq", 12), ("high_freq", 40)), None)
    assert sole_remaining == ((("low_freq", 12), ("high_freq", 40)), None)


def test_bandpass_provenance_uses_decimal_membership_not_english_labels() -> None:
    result = verify_direct_parameter_origins(
        "apply_bandpass_filter",
        {"low_freq": 10, "high_freq": 40},
        "bandpass high filter is 40 hz low is 10 hz",
    )

    assert result == VerificationResult(True)


def test_model_mapped_reversed_bandpass_remains_range_invalid() -> None:
    result = FrequencyRangeValidator().validate(
        "apply_bandpass_filter",
        {"low_freq": 40, "high_freq": 10},
    )

    assert result.is_valid is False


@pytest.mark.parametrize(
    "text",
    ("low 12 Hz and 40 Hz", "Instead, resample to 100 Hz.", "fifty hertz", "cancel"),
)
def test_direct_form_fails_closed_for_mixed_or_non_value_reply_shape(
    text: str,
) -> None:
    assert (
        collect_direct_parameter_reply_evidence(
            "apply_bandpass_filter",
            (),
            None,
            text,
        )
        is None
    )


@pytest.mark.parametrize(
    ("params", "expected_question", "text"),
    [
        (
            {"low_freq": 5, "high_freq": 38},
            "What low cutoff frequency should I use for the bandpass filter?",
            "low 4 Hz, high 38 Hz",
        ),
        (
            {"low_freq": 4, "high_freq": 40},
            "What high cutoff frequency should I use for the bandpass filter?",
            "low 4 Hz, high 38 Hz",
        ),
    ],
)
def test_bandpass_origin_question_names_only_the_unverified_cutoff(
    params: dict[str, Any],
    expected_question: str,
    text: str,
) -> None:
    result = verify_direct_parameter_origins(
        "apply_bandpass_filter",
        params,
        text,
    )

    assert result == VerificationResult(False, expected_question)


def test_verification_script_syntax(tmp_path):
    """Test that Verifier catches basic syntax errors in tool calls."""
    verifier = VerificationLayer()

    # Valid call
    source = tmp_path / "test.csv"
    source.touch()
    valid_call = ("scan_source", {"source_path": str(source)})
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
        r = v.validate("scan_source", {"source_path": "/tmp"})
        assert r.is_valid

    def test_partial_params_ok(self):
        v = FrequencyRangeValidator()
        r = v.validate("apply_bandpass_filter", {"low_freq": 1.0})
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
                "configure_dataset_split": {
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
        r = v.validate("configure_dataset_split", {"split_strategy": "individual"})
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


# ---------------------------------------------------------------------------
# Training output paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "",
        "path_to_eeg_dataset",
        "/path/to/output",
        "/path/with/output",
        "Please provide the absolute path",
        "your/recipe",
        "replace_with/output",
    ],
)
def test_training_output_rejects_placeholder_paths(path: str) -> None:
    result = PlaceholderArgumentValidator().validate(
        "configure_training", {"output_dir": path}
    )
    assert not result.is_valid
    assert _error_message(result) == (
        "Required training output directory must be an actual path "
        f"provided by the user, got placeholder {path!r}."
    )


@pytest.mark.parametrize("path", ["relative/output", "output"])
def test_training_output_requires_absolute_path(path: str) -> None:
    result = PlaceholderArgumentValidator().validate(
        "configure_training", {"output_dir": path}
    )
    assert not result.is_valid
    assert "absolute path" in _error_message(result)


@pytest.mark.parametrize("path", ["/new/output", r"C:\data\new output"])
def test_training_output_does_not_require_existing_directory(path: str) -> None:
    assert (
        PlaceholderArgumentValidator()
        .validate("configure_training", {"output_dir": path})
        .is_valid
    )


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
        r = v.verify_tool_call(
            ("configure_training", {"output_dir": "/path/to/output"})
        )
        assert not r.is_valid
        assert "actual path" in _error_message(r)


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


def test_verification_boundary_redacts_public_error_and_validator_log(
    caplog,
    capture_product_logs,
) -> None:
    verifier = VerificationLayer(validators=[_PrivateFailureValidator()])

    with capture_product_logs(
        logging.WARNING,
        logger_name="XBrainLab.llm.agent.verifier",
    ):
        result = verifier.verify_tool_call(("query_state", {}), confidence=1.0)

    assert result.is_valid is False
    public_error = _error_message(result)
    log_output = "\n".join(record.getMessage() for record in caplog.records)
    for output in (public_error, log_output):
        assert "/home/alice/private/subject-17/events.tsv" not in output
        assert "private-api-value" not in output
        assert "[REDACTED_PATH]" in output
        assert "[REDACTED_SECRET]" in output
