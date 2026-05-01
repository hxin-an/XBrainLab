#!/usr/bin/env python3
"""Classify the current local-assistant runtime state for this host."""

from __future__ import annotations

import argparse
import json
import re

from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import LLMEngine
from XBrainLab.llm.core.model_catalog import (
    MAX_TOTAL_MODEL_CACHE_GB,
    allowed_local_model_ids,
    cache_usage_bytes,
    default_local_model_id,
    disallowed_cache_candidates,
    fallback_local_model_id,
    format_bytes,
    local_model_policy_error,
    local_model_spec,
)


def classify_runtime(config: LLMConfig) -> dict[str, object]:
    """Return a structured classification of current local-assistant readiness."""
    selection = config.assistant_runtime_selection()
    result: dict[str, object] = {
        "current_backend_mode": selection.backend_mode,
        "current_model_id": selection.model_id,
        "current_ui_active_mode": selection.ui_active_mode,
        "inspected_backend_mode": "local",
        "inspected_model_id": config.model_name,
        "classification": "",
        "message": "",
        "missing_packages": [],
        "cache_candidates": [],
        "has_local_cache": False,
        "gpu_fallback_reason": None,
        "load_in_4bit": bool(config.load_in_4bit),
        "effective_load_in_4bit": bool(config.load_in_4bit),
        "policy_error": None,
        "allowed_local_models": allowed_local_model_ids(),
        "primary_local_model": default_local_model_id(),
        "fallback_local_model": fallback_local_model_id(),
        "cache_dir": config.cache_dir,
        "cache_usage_bytes": 0,
        "cache_usage": "0.00 GB",
        "max_total_cache_gb": MAX_TOTAL_MODEL_CACHE_GB,
        "disallowed_cache_candidates": [],
        "model_estimates": {},
    }

    policy_error = local_model_policy_error(config.model_name)
    missing_packages = config.missing_local_runtime_packages()
    cache_candidates = config.local_cache_candidates(config.model_name)
    has_local_cache = config.has_local_model_cache(config.model_name)
    fallback_reason = config.local_backend_cpu_fallback_reason()
    message = config.local_backend_status_message(config.model_name)
    cache_bytes = cache_usage_bytes(config.cache_dir)
    spec = local_model_spec(config.model_name)

    result["policy_error"] = policy_error
    result["missing_packages"] = missing_packages
    result["cache_candidates"] = cache_candidates
    result["has_local_cache"] = has_local_cache
    result["gpu_fallback_reason"] = fallback_reason
    result["message"] = message
    result["cache_usage_bytes"] = cache_bytes
    result["cache_usage"] = format_bytes(cache_bytes)
    result["disallowed_cache_candidates"] = disallowed_cache_candidates(
        config.cache_dir
    )
    result["model_estimates"] = (
        {
            "estimated_download_gb": spec.estimated_download_gb,
            "estimated_vram_gb": spec.estimated_vram_gb,
            "quantization": spec.quantization,
            "provider": spec.provider,
            "license": spec.license,
        }
        if spec
        else {}
    )

    if policy_error is not None:
        result["classification"] = "policy-blocked"
        result["effective_load_in_4bit"] = False
        return result

    if missing_packages:
        result["classification"] = "missing-packages"
        result["effective_load_in_4bit"] = False
        return result

    if not has_local_cache:
        result["classification"] = "missing-cache"
        result["effective_load_in_4bit"] = False
        return result

    if fallback_reason is not None:
        result["classification"] = "cpu-fallback"
        result["effective_load_in_4bit"] = False
        return result

    result["classification"] = "gpu-ready"
    return result


def render_markdown(result: dict[str, object]) -> str:
    """Render a human-readable host-runtime summary."""
    lines = [
        "# Local Assistant Runtime Inspection",
        "",
        f"- classification: `{result['classification']}`",
        f"- current backend mode: `{result['current_backend_mode']}`",
        f"- current model id: `{result['current_model_id']}`",
        f"- current ui active mode: `{result['current_ui_active_mode']}`",
        f"- inspected backend mode: `{result['inspected_backend_mode']}`",
        f"- inspected model id: `{result['inspected_model_id']}`",
        f"- primary local model: `{result['primary_local_model']}`",
        f"- fallback local model: `{result['fallback_local_model']}`",
        f"- cache directory: `{result['cache_dir']}`",
        f"- cache usage: `{result['cache_usage']}`",
        f"- max total cache: `{result['max_total_cache_gb']} GB`",
        f"- has local cache: `{result['has_local_cache']}`",
        f"- load_in_4bit requested: `{result['load_in_4bit']}`",
        f"- effective 4-bit policy: `{result['effective_load_in_4bit']}`",
    ]

    if result["policy_error"]:
        lines.append(f"- policy error: {result['policy_error']}")
    if result["missing_packages"]:
        lines.append(f"- missing packages: `{', '.join(result['missing_packages'])}`")
    if result["gpu_fallback_reason"]:
        lines.append(f"- gpu fallback reason: `{result['gpu_fallback_reason']}`")
    if result["model_estimates"]:
        estimates = result["model_estimates"]
        lines.append(
            "- model estimate: "
            f"{estimates['estimated_download_gb']} GB download, "
            f"{estimates['estimated_vram_gb']} GB VRAM, "
            f"{estimates['quantization']}"
        )
    if result["disallowed_cache_candidates"]:
        lines.append("- disallowed cache candidates:")
        lines.extend(f"  - `{path}`" for path in result["disallowed_cache_candidates"])
    lines.append(f"- message: {result['message']}")
    if "prompt_smoke" in result:
        smoke = result["prompt_smoke"]
        if isinstance(smoke, dict):
            lines.append(f"- prompt smoke: `{smoke.get('status')}`")
            if smoke.get("message"):
                lines.append(f"  - {smoke['message']}")
    if "structured_output_smoke" in result:
        smoke = result["structured_output_smoke"]
        if isinstance(smoke, dict):
            lines.append(f"- structured-output smoke: `{smoke.get('status')}`")
            if smoke.get("message"):
                lines.append(f"  - {smoke['message']}")
    return "\n".join(lines)


def run_prompt_smoke(
    config: LLMConfig,
    *,
    prompt: str = "Reply with READY.",
) -> dict[str, object]:
    """Run a minimal local prompt-response smoke when the runtime is ready."""
    selection = config.assistant_runtime_selection()
    if selection.backend_mode != "local":
        return {
            "status": "skipped",
            "message": f"Current backend is {selection.backend_mode}, not local.",
            "response": "",
        }

    if not config.local_backend_ready(selection.model_id):
        return {
            "status": "skipped",
            "message": config.local_backend_status_message(selection.model_id),
            "response": "",
        }

    config.max_new_tokens = min(int(config.max_new_tokens), 32)
    config.do_sample = False
    try:
        engine = LLMEngine(config)
        engine.load_model()
        chunks = list(
            engine.generate_stream(
                [
                    {
                        "role": "system",
                        "content": "You are a local XBrainLab health checker.",
                    },
                    {"role": "user", "content": prompt},
                ]
            )
        )
    except Exception as exc:
        return {"status": "failed", "message": str(exc), "response": ""}

    response = "".join(chunks).strip()
    return {
        "status": "passed" if response else "failed",
        "message": "Prompt-response smoke completed."
        if response
        else "Empty response.",
        "response": response[:500],
    }


def _extract_json_object(text: str) -> dict[str, object] | None:
    """Extract the first JSON object from model output."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    candidates = [stripped]
    match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def run_structured_output_smoke(config: LLMConfig) -> dict[str, object]:
    """Check whether the local model can follow the tool-call JSON protocol."""
    selection = config.assistant_runtime_selection()
    if selection.backend_mode != "local":
        return {
            "status": "skipped",
            "message": f"Current backend is {selection.backend_mode}, not local.",
            "response": "",
        }

    if not config.local_backend_ready(selection.model_id):
        return {
            "status": "skipped",
            "message": config.local_backend_status_message(selection.model_id),
            "response": "",
        }

    config.max_new_tokens = min(int(config.max_new_tokens), 96)
    config.do_sample = False
    try:
        engine = LLMEngine(config)
        engine.load_model()
        chunks = list(
            engine.generate_stream(
                [
                    {
                        "role": "system",
                        "content": (
                            "You emit only one compact JSON object for XBrainLab "
                            "tool calls. Do not use markdown."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            'Return exactly {"tool_name":"get_state","arguments":{}}'
                        ),
                    },
                ]
            )
        )
    except Exception as exc:
        return {"status": "failed", "message": str(exc), "response": ""}

    response = "".join(chunks).strip()
    parsed = _extract_json_object(response)
    if parsed == {"tool_name": "get_state", "arguments": {}}:
        return {
            "status": "passed",
            "message": "Structured-output smoke completed.",
            "response": response[:500],
        }
    return {
        "status": "failed",
        "message": "Model did not return the expected tool-call JSON object.",
        "response": response[:500],
        "parsed": parsed,
    }


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Output format",
    )
    parser.add_argument(
        "--prompt-smoke",
        action="store_true",
        help="Load the local model and run a minimal prompt-response smoke if ready.",
    )
    parser.add_argument(
        "--structured-smoke",
        action="store_true",
        help="Run a minimal tool-call JSON protocol smoke if the local model is ready.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Inspect a specific supported local model without saving settings.",
    )
    args = parser.parse_args()

    config = LLMConfig.load_from_file() or LLMConfig()
    if args.model:
        config.apply_runtime_selection(
            "local",
            model_id=args.model,
            ui_active_mode="local",
        )
    result = classify_runtime(config)
    if args.prompt_smoke:
        result["prompt_smoke"] = run_prompt_smoke(config)
    if args.structured_smoke:
        result["structured_output_smoke"] = run_structured_output_smoke(config)
    if args.format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
