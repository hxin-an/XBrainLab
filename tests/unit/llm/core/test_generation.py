import pytest

from XBrainLab.llm.core.generation import (
    STRUCTURED_DECISION_MAX_NEW_TOKENS,
    GenerationProfile,
    ResolvedGenerationOptions,
    resolve_generation_options,
)


def test_structured_decision_is_greedy_and_code_capped():
    options = resolve_generation_options(
        profile=GenerationProfile.STRUCTURED_DECISION,
        max_new_tokens=8192,
        do_sample=True,
        temperature=0.7,
        top_p=0.9,
    )

    assert options == ResolvedGenerationOptions(
        max_new_tokens=STRUCTURED_DECISION_MAX_NEW_TOKENS,
        do_sample=False,
    )


def test_informational_text_preserves_valid_sampling_preferences():
    options = resolve_generation_options(
        profile=GenerationProfile.INFORMATIONAL_TEXT,
        max_new_tokens=768,
        do_sample=True,
        temperature=0.4,
        top_p=0.85,
    )

    assert options == ResolvedGenerationOptions(
        max_new_tokens=768,
        do_sample=True,
        temperature=0.4,
        top_p=0.85,
    )


@pytest.mark.parametrize(
    ("do_sample", "temperature"),
    [(False, 0.7), (True, 0.0)],
)
def test_informational_greedy_mode_omits_sampling_parameters(
    do_sample,
    temperature,
):
    options = resolve_generation_options(
        profile=GenerationProfile.INFORMATIONAL_TEXT,
        max_new_tokens=256,
        do_sample=do_sample,
        temperature=temperature,
        top_p=0.9,
    )

    assert options == ResolvedGenerationOptions(
        max_new_tokens=256,
        do_sample=False,
    )


def test_resolved_options_reject_sampling_without_positive_temperature():
    with pytest.raises(ValueError, match="positive temperature"):
        ResolvedGenerationOptions(
            max_new_tokens=128,
            do_sample=True,
            temperature=0.0,
            top_p=0.9,
        )
