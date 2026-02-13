import pytest

from XBrainLab.llm.agent.verifier import VerificationLayer, VerificationResult


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
    # This might be caught by type hinting but let's see if verifier checks it.
    with pytest.raises(ValueError):  # Or return invalid
        verifier.verify_tool_call(
            ("not a tuple",), 0.9
        )  # Fix tool call arg to be tuple but wrong length or structure

    # Valid structure
    res = verifier.verify_tool_call(("tool", {}), 0.9)
    assert res.is_valid
