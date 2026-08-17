#!/usr/bin/env python3
"""Classify the current local-assistant runtime state for this host."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from contextlib import suppress
from pathlib import Path
from typing import Any

if __package__:
    from scripts.dev.active_checkout import assert_active_checkout_import
    from scripts.dev.sensitive_path_redaction import redact_sensitive_value
else:
    from active_checkout import assert_active_checkout_import
    from sensitive_path_redaction import redact_sensitive_value

ROOT = Path(__file__).resolve().parents[2]
assert_active_checkout_import(ROOT)

from XBrainLab.llm.agent.parser import CommandParser, ToolEnvelopeStatus
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import LLMEngine
from XBrainLab.llm.core.generation import GenerationProfile
from XBrainLab.llm.core.model_catalog import (
    MAX_TOTAL_MODEL_CACHE_GB,
    allowed_local_model_ids,
    cache_usage_bytes,
    default_local_model_id,
    disallowed_cache_candidates,
    format_bytes,
    legacy_local_model_ids,
    local_model_policy_error,
    local_model_spec,
)


def classify_runtime(config: LLMConfig) -> dict[str, Any]:
    """Return a structured classification of current local-assistant readiness."""
    selection = config.assistant_runtime_selection()
    result: dict[str, Any] = {
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
        "legacy_compatibility_models": legacy_local_model_ids(),
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


def _cache_identity(cache_dir: str) -> dict[str, object]:
    path = Path(cache_dir).expanduser()
    normalized = str(path.resolve(strict=False))
    if os.name == "nt" and path.drive:
        mount = path.drive.upper()
    elif normalized.startswith("/mnt/"):
        parts = Path(normalized).parts
        mount = "/".join(parts[:3]) if len(parts) >= 3 else "/mnt"
    else:
        mount = "local"
    return {
        "mount": mount,
        "path_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        "redacted": True,
    }


def _public_runtime_result(result: dict[str, Any]) -> dict[str, Any]:
    """Return a report-safe runtime projection without host cache paths."""
    projected = dict(result)
    cache_dir = projected.pop("cache_dir", None)
    cache_candidates = projected.pop("cache_candidates", ())
    disallowed_candidates = projected.pop("disallowed_cache_candidates", ())
    projected["cache_candidate_count"] = len(cache_candidates)
    projected["disallowed_cache_candidate_count"] = len(disallowed_candidates)
    if isinstance(cache_dir, str) and cache_dir:
        projected["cache_identity"] = _cache_identity(cache_dir)
        projected = redact_sensitive_value(
            projected,
            {cache_dir: "<redacted:model-cache>"},
        )
    return projected


def render_markdown(result: dict[str, Any]) -> str:
    """Render a human-readable host-runtime summary."""
    result = _public_runtime_result(result)
    cache_identity = result.get("cache_identity", {})
    if not isinstance(cache_identity, dict):
        cache_identity = {}
    cache_identity_summary = (
        f"{cache_identity.get('mount', 'local')} / "
        f"{str(cache_identity.get('path_sha256', 'unknown'))[:12]}"
    )
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
        "- legacy compatibility models: "
        f"`{', '.join(result['legacy_compatibility_models'])}`",
        f"- cache identity: `{cache_identity_summary}`",
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
    if result["disallowed_cache_candidate_count"]:
        lines.append(
            "- disallowed cache candidates: "
            f"`{result['disallowed_cache_candidate_count']}`"
        )
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
) -> dict[str, Any]:
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
    engine: LLMEngine | None = None
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
                ],
                profile=GenerationProfile.INFORMATIONAL_TEXT,
            )
        )
    except Exception as exc:
        return {"status": "failed", "message": str(exc), "response": ""}
    finally:
        if engine is not None:
            with suppress(Exception):
                engine.close()

    response = "".join(chunks).strip()
    return {
        "status": "passed" if response else "failed",
        "message": "Prompt-response smoke completed."
        if response
        else "Empty response.",
        "response": response[:500],
    }


def run_structured_output_smoke(config: LLMConfig) -> dict[str, Any]:
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
    engine: LLMEngine | None = None
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
                            "Return exactly "
                            '{"workflow_stage":"unavailable",'
                            '"tool_name":"query_state","parameters":{}}'
                        ),
                    },
                ],
                profile=GenerationProfile.STRUCTURED_DECISION,
            )
        )
    except Exception as exc:
        return {"status": "failed", "message": str(exc), "response": ""}
    finally:
        if engine is not None:
            with suppress(Exception):
                engine.close()

    response = "".join(chunks).strip()
    envelope = CommandParser.parse_product(response)
    if (
        envelope.status is ToolEnvelopeStatus.VALID
        and envelope.workflow_stage == "unavailable"
        and envelope.commands == (("query_state", {}),)
    ):
        return {
            "status": "passed",
            "message": "Product tool-envelope smoke completed.",
            "response": response[:500],
        }
    return {
        "status": "failed",
        "failure_type": "output_format",
        "message": "Model did not return the strict product tool envelope.",
        "response": response[:500],
        "parse_status": envelope.status.value,
        "parse_error": envelope.error,
    }


def main(argv: list[str] | None = None) -> int:
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
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when a requested runtime smoke does not pass.",
    )
    args = parser.parse_args(argv)

    previous_logging_disable = logging.root.manager.disable
    if args.format == "json":
        logging.disable(logging.INFO)
    try:
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
    finally:
        logging.disable(previous_logging_disable)

    if args.format == "json":
        print(json.dumps(_public_runtime_result(result), indent=2, ensure_ascii=False))
    else:
        print(render_markdown(result))
    requested_smokes = [
        result.get(key)
        for requested, key in (
            (args.prompt_smoke, "prompt_smoke"),
            (args.structured_smoke, "structured_output_smoke"),
        )
        if requested
    ]
    smoke_failed = any(
        not isinstance(smoke, dict) or smoke.get("status") != "passed"
        for smoke in requested_smokes
    )
    return 1 if args.strict and smoke_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
