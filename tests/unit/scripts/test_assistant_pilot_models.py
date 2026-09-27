"""Research configuration is pinned, isolated and not a product catalog change."""

import pickle
from functools import partial

import pytest

from scripts.dev.assistant_pilot_models import (
    build_frozen_config,
    build_research_engine,
    make_launch_spec,
    research_model_spec,
    research_template_kwargs,
)
from XBrainLab.llm.core.generation import GenerationProfile, resolve_generation_options
from XBrainLab.llm.core.model_catalog import allowed_local_model_ids

PINS = {
    "ibm-granite/granite-4.0-micro": (
        "56111ae135df9c53a78c99028e7bc24035a9e979"  # pragma: allowlist secret
    ),
    "ibm-granite/granite-3.3-2b-instruct": (
        "707f574c62054322f6b5b04b6d075f0a8f05e0f0"  # pragma: allowlist secret
    ),
    "microsoft/Phi-4-mini-instruct": (
        "cfbefacb99257ffa30c83adab238a50856ac3083"  # pragma: allowlist secret
    ),
    "meta-llama/Llama-3.2-3B-Instruct": (
        "0cb88a4f764b7a12671c53f0838cd831a0843b95"  # pragma: allowlist secret
    ),
    "google/gemma-3-4b-it": (
        "093f9f388b31de276ce2de164bdc2081324b9767"  # pragma: allowlist secret
    ),
}


@pytest.mark.parametrize("model,revision", PINS.items())
def test_exact_research_pins_keep_product_catalog_unchanged(model, revision):
    spec = research_model_spec(model)
    assert spec.repo_id == model
    assert spec.revision == revision
    assert spec.runtime_context_tokens == 8192
    assert spec.preferred_cuda_dtype == "bfloat16"
    assert len(allowed_local_model_ids()) == 2
    assert all(name.startswith("ibm-granite/") for name in allowed_local_model_ids())


@pytest.mark.parametrize(
    "model", ["unknown/model", "", "microsoft/Phi-3.5-mini-instruct"]
)
def test_unapproved_model_is_not_normalized_or_substituted(model):
    with pytest.raises(ValueError, match="research model"):
        research_model_spec(model)


def test_frozen_settings_rebuild_without_daily_file_or_shared_mutation(monkeypatch):
    from XBrainLab.llm.core.config import LLMConfig

    def forbidden(*args, **kwargs):
        pytest.fail("Research configuration must not access daily settings")

    monkeypatch.setattr(LLMConfig, "load_from_file", forbidden)
    monkeypatch.setattr(LLMConfig, "save_to_file", forbidden)
    launch = make_launch_spec("google/gemma-3-4b-it", "D:/approved-cache")
    first = build_frozen_config(launch)
    first.temperature = 0.99
    first.model_name = "changed"
    second = build_frozen_config(launch)
    assert second.model_name == launch.model_id == "google/gemma-3-4b-it"
    assert second.temperature == 0.7
    assert second.timeout == 120
    assert second.load_in_4bit is True
    assert second.local_runtime_notice_acknowledged is True
    assert second.cache_dir == "D:/approved-cache"
    resolved = resolve_generation_options(
        profile=GenerationProfile.STRUCTURED_DECISION,
        max_new_tokens=second.max_new_tokens,
        do_sample=second.do_sample,
        temperature=second.temperature,
        top_p=second.top_p,
    )
    assert resolved.max_new_tokens == 512 and resolved.do_sample is False


def test_frozen_factory_can_cross_windows_spawn_boundary():
    launch = make_launch_spec(
        "microsoft/Phi-4-mini-instruct", "D:/approved-cache", device="cpu"
    )
    # Only deserialize bytes created immediately from this trusted fixture.
    factory = pickle.loads(pickle.dumps(partial(build_frozen_config, launch)))  # noqa: S301
    assert factory().model_name == launch.model_id
    assert pickle.loads(pickle.dumps(build_research_engine)) is build_research_engine  # noqa: S301


def test_template_date_and_role_capabilities_are_explicit():
    assert research_template_kwargs("meta-llama/Llama-3.2-3B-Instruct") == (
        ("date_string", "21 Sep 2026"),
    )
    assert research_template_kwargs("google/gemma-3-4b-it") == ()
    gemma = research_model_spec("google/gemma-3-4b-it")
    assert gemma.supports_consecutive_user_roles is False


@pytest.mark.parametrize("model", PINS)
def test_only_approved_gemma_launch_uses_frozen_quantization(model):
    config = build_frozen_config(make_launch_spec(model, "D:/approved-cache"))
    assert config.load_in_4bit is (model == "google/gemma-3-4b-it")


def test_quantized_research_rejects_cpu_and_precision_drift():
    with pytest.raises(ValueError, match="CUDA"):
        make_launch_spec("google/gemma-3-4b-it", "D:/approved-cache", device="cpu")
    config = build_frozen_config(
        make_launch_spec("google/gemma-3-4b-it", "D:/approved-cache")
    )
    config.load_in_4bit = False
    with pytest.raises(ValueError, match="quantization"):
        build_research_engine(config)
