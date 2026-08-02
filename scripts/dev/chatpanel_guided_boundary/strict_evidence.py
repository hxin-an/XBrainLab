"""Strict exact-model evidence publication for the Guided walkthrough."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from scripts.dev.chatpanel_guided_boundary.evidence import (
    render_guided_boundary_markdown,
)
from scripts.dev.chatpanel_guided_boundary.runtime import (
    DEFAULT_OUTPUT_DIR,
    JSON_ARTIFACT,
    MARKDOWN_ARTIFACT,
)
from scripts.dev.local_assistant_capture_runtime import (
    collect_capture_source_identity,
    finalize_strict_capture_evidence,
)
from XBrainLab.llm.core.config import LLMConfig


def run_with_strict_evidence(
    guided_runner: Callable[[], int],
    argv: list[str],
) -> int:
    """Run Guided capture, then bind successful output to strict evidence."""
    output_dir = output_dir_from_argv(argv)
    source_identity_at_start = collect_capture_source_identity(refresh=True)
    returncode = guided_runner()
    if returncode != 0:
        return returncode
    return attach_guided_strict_evidence(
        output_dir,
        source_identity_at_start=source_identity_at_start,
    )


def output_dir_from_argv(argv: list[str]) -> Path:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args, _unknown = parser.parse_known_args(argv)
    return Path(args.output_dir).expanduser().resolve()


def attach_guided_strict_evidence(
    output_dir: Path,
    *,
    source_identity_at_start: dict[str, object],
) -> int:
    """Attach the shared strict Granite identity without altering guided semantics."""
    json_path = output_dir / JSON_ARTIFACT
    markdown_path = output_dir / MARKDOWN_ARTIFACT
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Strict Guided evidence could not be read: {exc}", file=sys.stderr)
        return 1
    if not isinstance(payload, dict):
        print("Strict Guided evidence root is not an object.", file=sys.stderr)
        return 1

    runtime = payload.get("runtime")
    runtime_payload = dict(runtime) if isinstance(runtime, dict) else {}
    requested_model = str(runtime_payload.get("requested_model_id") or "")
    loaded_model = str(runtime_payload.get("loaded_model_id") or "")
    strict_payload: dict[str, Any] = {
        "status": payload.get("status"),
        "runtime": runtime_payload,
        "hf_offline": dict(payload.get("hf_offline") or {}),
        "screenshots": dict(payload.get("screenshots") or {}),
        "turns": [],
        "confirmation_events": [],
        "shutdown": dict(payload.get("shutdown") or {}),
    }
    config = LLMConfig()
    ok, reason = finalize_strict_capture_evidence(
        strict_payload,
        requested_model_id=requested_model,
        runtime_snapshot={
            "phase": runtime_payload.get("phase"),
            "initialized": runtime_payload.get("initialized"),
            "model_id": loaded_model,
        },
        cache_dir=config.cache_dir,
        artifact_root=output_dir,
        source_identity_at_start=source_identity_at_start,
        host_actions=(
            "continued parameter-free safe tools under deterministic host policy",
            "opened and cancelled the typed workflow handoff dialog",
        ),
    )
    payload["strict_evidence"] = {
        key: strict_payload[key]
        for key in (
            "status",
            "runtime",
            "hf_offline",
            "shutdown",
            "source_identity",
            "capture_source",
            "host_assistance",
            "screenshot_artifacts",
        )
        if key in strict_payload
    }
    if not ok:
        payload["status"] = "failed"
        payload["failure_reason"] = reason
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    markdown = render_guided_boundary_markdown(payload)
    markdown += _render_strict_identity(strict_payload, ok=ok, reason=reason)
    markdown_path.write_text(markdown, encoding="utf-8")
    if not ok:
        print(f"Strict Guided evidence rejected: {reason}", file=sys.stderr)
        return 1
    return 0


def _render_strict_identity(
    payload: dict[str, Any],
    *,
    ok: bool,
    reason: str,
) -> str:
    runtime = dict(payload.get("runtime") or {})
    model = dict(runtime.get("model_identity") or {})
    source = dict(payload.get("source_identity") or {})
    screenshots = dict(payload.get("screenshot_artifacts") or {})
    return "\n".join(
        [
            "",
            "## Strict Evidence Identity",
            "",
            f"- status: `{'passed' if ok else 'failed'}`",
            f"- failure reason: {reason or 'none'}",
            f"- requested model: `{runtime.get('requested_model_id', '')}`",
            f"- loaded model: `{runtime.get('loaded_model_id', '')}`",
            f"- loaded revision: `{model.get('loaded_revision', '')}`",
            f"- model snapshot digest: `{model.get('snapshot_manifest_sha256', '')}`",
            f"- source commit: `{source.get('commit_sha', '')}`",
            f"- source identity: `{source.get('identity_sha256', '')}`",
            f"- screenshot aggregate: `{screenshots.get('aggregate_sha256', '')}`",
            f"- shutdown: `{dict(payload.get('shutdown') or {}).get('status', '')}`",
            "",
        ]
    )
