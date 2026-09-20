"""Approved, pinned research composition; never extends the product catalog.

These module-level factories can cross Windows spawn. The existing process,
backend, controller and command owners retain all execution responsibilities.
"""

from __future__ import annotations

from functools import partial

from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.model_catalog import LOCAL_MODEL_SPECS, LocalModelSpec
from XBrainLab.llm.core.runtime_selection import (
    AssistantRuntimeBackend,
    AssistantRuntimeLaunchSpec,
    AssistantRuntimeSelectionOutcome,
    AssistantRuntimeSettingsSnapshot,
)

PILOT_SEED = 0
_RESEARCH = (
    (
        "microsoft/Phi-4-mini-instruct",
        "cfbefacb99257ffa30c83adab238a50856ac3083",  # pragma: allowlist secret
        "Microsoft",
        "MIT",
        "3.8B",
        7.70,
        10.5,
        True,
    ),
    (
        "meta-llama/Llama-3.2-3B-Instruct",
        "0cb88a4f764b7a12671c53f0838cd831a0843b95",  # pragma: allowlist secret
        "Meta",
        "llama3.2",
        "3B",
        6.45,
        9.0,
        True,
    ),
    (
        "google/gemma-3-4b-it",
        "093f9f388b31de276ce2de164bdc2081324b9767",  # pragma: allowlist secret
        "Google",
        "gemma",
        "4B",
        8.65,
        12.0,
        False,
    ),
)


def research_model_spec(model_id: str) -> LocalModelSpec:
    """Resolve only the five approved research identities, with no fallback."""
    for spec in LOCAL_MODEL_SPECS:
        if spec.repo_id == model_id:
            return spec
    for (
        repo,
        revision,
        provider,
        license_name,
        parameters,
        size,
        vram,
        consecutive,
    ) in _RESEARCH:
        if repo == model_id:
            return LocalModelSpec(
                repo_id=repo,
                revision=revision,
                label=repo,
                provider=provider,
                role="research",
                license=license_name,
                parameters=parameters,
                context_tokens=131_072,
                estimated_download_gb=size,
                estimated_vram_gb=vram,
                quantization=(
                    "bitsandbytes NF4 4-bit weights; BF16 compute; no double quantization"
                    if repo == "google/gemma-3-4b-it"
                    else "BF16 safetensors; no quantization"
                ),
                estimated_4bit_vram_gb=11.0 if repo == "google/gemma-3-4b-it" else None,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype="bfloat16",
                runtime_context_tokens=8192,
                supports_system_role=True,
                supports_consecutive_user_roles=consecutive,
                preferred_cuda_dtype="bfloat16",
                source_url=f"https://huggingface.co/{repo}",
            )
    raise ValueError("Unapproved research model")


def research_template_kwargs(model_id: str) -> tuple[tuple[str, str], ...]:
    """Fix native-template wall-clock input before any observed result."""
    research_model_spec(model_id)
    return (("date_string", "21 Sep 2026"),) if model_id == _RESEARCH[1][0] else ()


def make_launch_spec(
    model_id: str, cache_dir: str, *, device: str = "cuda"
) -> AssistantRuntimeLaunchSpec:
    """Freeze a research launch; this does not certify cache or hardware readiness."""
    spec = research_model_spec(model_id)
    quantized = spec.estimated_4bit_vram_gb is not None
    if quantized and not device.startswith("cuda"):
        raise ValueError("Approved quantized research configuration requires CUDA")
    config = LLMConfig(
        model_name=model_id,
        cache_dir=cache_dir,
        device=device,
        max_new_tokens=512,
        timeout=120,
        temperature=0.7,
        top_p=0.9,
        do_sample=False,
        load_in_4bit=quantized,
        local_model_enabled=True,
    )
    return AssistantRuntimeLaunchSpec(
        backend=AssistantRuntimeBackend.LOCAL,
        requested_backend_id="local",
        requested_model_id=model_id,
        model_id=model_id,
        outcome=AssistantRuntimeSelectionOutcome.EXACT,
        selection_detail="Exact research runtime selection; readiness checked separately.",
        settings=AssistantRuntimeSettingsSnapshot.from_config(config),
    )


def build_frozen_config(launch_spec: AssistantRuntimeLaunchSpec) -> LLMConfig:
    """Return a fresh isolated config without reading or saving daily settings."""
    research_model_spec(launch_spec.model_id)
    config = launch_spec.build_config()
    config.local_runtime_notice_acknowledged = True
    return config


def build_research_engine(config: LLMConfig):
    """Construct the ordinary engine/backend inside the existing owned child."""
    spec = research_model_spec(config.model_name)
    if config.load_in_4bit != (spec.estimated_4bit_vram_gb is not None):
        raise ValueError("Research quantization configuration changed after selection")
    from transformers import set_seed

    from XBrainLab.llm.core.backends.local import LocalBackend
    from XBrainLab.llm.core.engine import LLMEngine

    set_seed(PILOT_SEED)
    return LLMEngine(
        config,
        backend_factory=partial(
            LocalBackend,
            model_spec=spec,
            template_kwargs=research_template_kwargs(config.model_name),
        ),
    )


def build_research_worker(launch_spec: AssistantRuntimeLaunchSpec):
    """Keep the worker/process lifecycle and inject only frozen dependencies."""
    from XBrainLab.llm.agent.worker import AgentWorker

    research_model_spec(launch_spec.model_id)
    return AgentWorker(
        engine_factory=build_research_engine,
        generation_config_loader=partial(build_frozen_config, launch_spec),
    )
