#!/usr/bin/env python3
"""Preflight local assistant model downloads without downloading anything."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.model_catalog import (
    allowed_local_model_ids,
    default_local_model_id,
    fallback_local_model_id,
    format_bytes,
    local_model_spec,
    plan_model_download,
)


def build_plan(model_id: str | None = None) -> dict[str, object]:
    """Return a machine-readable download plan for a local model."""
    config = LLMConfig.load_from_file() or LLMConfig()
    selected_model = model_id or config.model_name or default_local_model_id()
    preflight = plan_model_download(selected_model, config.cache_dir)
    spec = local_model_spec(selected_model)

    result: dict[str, object] = {
        "ok": preflight.ok,
        "model_id": selected_model,
        "cache_dir": config.cache_dir,
        "primary_model": default_local_model_id(),
        "fallback_model": fallback_local_model_id(),
        "allowed_models": allowed_local_model_ids(),
        "message": preflight.message,
        "estimated_download": format_bytes(preflight.estimated_download_bytes),
        "current_cache": format_bytes(preflight.current_cache_bytes),
        "projected_cache": format_bytes(preflight.projected_cache_bytes),
        "available_disk": format_bytes(preflight.available_disk_bytes),
        "max_single_model": format_bytes(preflight.max_single_model_bytes),
        "max_total_cache": format_bytes(preflight.max_total_cache_bytes),
        "cleanup_candidates": list(preflight.cleanup_candidates),
        "preflight": asdict(preflight),
        "model_spec": asdict(spec) if spec else None,
    }
    return result


def render_markdown(plan: dict[str, object]) -> str:
    """Render a concise human-readable preflight report."""
    lines = [
        "# Local Model Download Preflight",
        "",
        f"- ok: `{plan['ok']}`",
        f"- model: `{plan['model_id']}`",
        f"- primary model: `{plan['primary_model']}`",
        f"- fallback model: `{plan['fallback_model']}`",
        f"- cache directory: `{plan['cache_dir']}`",
        f"- estimated download: `{plan['estimated_download']}`",
        f"- current cache: `{plan['current_cache']}`",
        f"- projected cache: `{plan['projected_cache']}`",
        f"- available disk: `{plan['available_disk']}`",
        f"- max single model: `{plan['max_single_model']}`",
        f"- max total cache: `{plan['max_total_cache']}`",
        f"- message: {plan['message']}",
    ]
    spec = plan.get("model_spec")
    if isinstance(spec, dict):
        lines.extend(
            [
                f"- provider: `{spec['provider']}`",
                f"- license: `{spec['license']}`",
                f"- parameters: `{spec['parameters']}`",
                f"- context tokens: `{spec['context_tokens']}`",
                f"- VRAM estimate: `{spec['estimated_vram_gb']} GB`",
                f"- quantization: {spec['quantization']}",
                f"- source: {spec['source_url']}",
            ]
        )
    cleanup = plan.get("cleanup_candidates")
    if cleanup:
        lines.append("- cleanup candidates:")
        lines.extend(f"  - `{path}`" for path in cleanup)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None, help="Hugging Face model repo ID")
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Output format",
    )
    args = parser.parse_args()

    plan = build_plan(args.model)
    if args.format == "json":
        print(json.dumps(plan, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(plan))
    return 0 if plan["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
