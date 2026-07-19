"""CLI/runtime composition for the real-model Guided Workflow walkthrough."""

from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from scripts.dev.capture_chatpanel_local_pipeline_chain_walkthrough import (
    SettingsFileSnapshot,
    _structured_value,
    _turn_metrics_evidence,
    approve_product_dialog,
    assistant_surface_ready,
    collect_model_proposals,
    publication_evidence,
    runtime_evidence,
)
from scripts.dev.capture_chatpanel_local_tool_chain_walkthrough import (
    _capture_current_window,
    _clear_saved_main_window_geometry,
    _force_offline_hf_runtime,
    _load_capture_config,
    _runtime_summary,
    _set_baseline_window_geometry,
    write_synthetic_raw_fif,
)
from scripts.dev.capture_chatpanel_local_walkthrough import (
    collect_executed_tools,
    collect_visible_messages,
    has_raw_debug_text,
)
from scripts.dev.capture_chatpanel_local_workflow_walkthrough import (
    _has_runtime_error_text,
)
from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    collect_source_identity,
)
from scripts.dev.chatpanel_guided_boundary.artifact_runner import (
    create_guided_boundary_staging_dir,
    publish_guided_boundary_artifact_run,
)
from scripts.dev.chatpanel_guided_boundary.contracts import GuidedBoundaryHooks
from scripts.dev.chatpanel_guided_boundary.driver import GuidedBoundaryDriver
from scripts.dev.chatpanel_guided_boundary.evidence import (
    GuidedBoundaryEvidenceAssembler,
)
from scripts.dev.chatpanel_guided_boundary.state import GuidedBoundaryState
from scripts.dev.chatpanel_guided_boundary.tool_trace import GuidedToolTraceRecorder
from scripts.dev.chatpanel_guided_boundary.validation import (
    DEFAULT_MODEL_ID,
    build_guided_prompts,
    validate_guided_boundary_artifact_root,
)
from scripts.dev.inspect_local_assistant_runtime import classify_runtime
from XBrainLab.config import AppConfig

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "ui" / "chatpanel-guided-boundary"
JSON_ARTIFACT = "chatpanel-local-guided-boundary-walkthrough.json"
MARKDOWN_ARTIFACT = "chatpanel-local-guided-boundary-walkthrough.md"


def cli_main(argv: list[str] | None = None) -> int:
    """Parse the stable CLI, execute one proof, and write terminal evidence."""
    args = _build_parser().parse_args(argv)
    output_dir = Path(args.output_dir).expanduser().resolve()
    run_id, staging_dir = create_guided_boundary_staging_dir(output_dir)
    source_identity_at_start = collect_source_identity(ROOT, refresh=True)
    settings_path = Path(AppConfig.BASE_DIR) / "settings.json"
    settings_snapshot = SettingsFileSnapshot.capture(settings_path)
    runtime_summary: dict[str, object] = {
        "classification": "unknown",
        "model_id": args.model,
        "cache_usage": "unknown",
    }
    source_path: Path | None = None
    try:
        _enforce_offline_runtime()
        config = _load_capture_config(args.model)
        config.save_to_file(str(settings_path))
        runtime = classify_runtime(config)
        runtime_summary = _runtime_summary(runtime)
        runtime_summary["model_id"] = args.model
        if args.model != DEFAULT_MODEL_ID:
            payload = _terminal_payload(
                status="blocked",
                reason=f"Guided proof requires exact model {DEFAULT_MODEL_ID}.",
                model_id=args.model,
                runtime_summary=runtime_summary,
            )
            return_code = 2
        elif runtime.get("classification") != "gpu-ready":
            payload = _terminal_payload(
                status="blocked",
                reason=str(
                    runtime.get("message")
                    or "Exact Phi-4 local GPU runtime is not ready."
                ),
                model_id=args.model,
                runtime_summary=runtime_summary,
            )
            return_code = 2
        else:
            source_path = write_synthetic_raw_fif()
            app = QApplication(sys.argv)
            app.setStyle("Fusion")
            app.setProperty("model_override", args.model)
            payload = run_guided_boundary_walkthrough(
                app,
                output_dir=staging_dir,
                source_path=source_path,
                model_id=args.model,
                timeout_seconds=args.timeout_seconds,
                initial_runtime=runtime_summary,
            )
            return_code = 0 if payload.get("status") == "passed" else 1
    except Exception as exc:
        payload = _terminal_payload(
            status="failed",
            reason=f"Guided walkthrough harness failed: {exc}",
            model_id=args.model,
            runtime_summary=runtime_summary,
            source_path=source_path,
            exception=traceback.format_exc(),
        )
        return_code = 1
    finally:
        settings_snapshot.restore()

    # settings.json is part of source identity. Freeze only after the temporary
    # runtime selection has been restored; artifact paths are generated output.
    frozen_source_identity = collect_source_identity(refresh=True)
    if not _record_guided_source_stability(
        payload,
        started=source_identity_at_start,
        completed=frozen_source_identity,
    ):
        return_code = 1
    published_dir, payload = publish_guided_boundary_artifact_run(
        staging_dir=staging_dir,
        current_root=output_dir,
        payload=payload,
        frozen_source_identity=frozen_source_identity,
        run_id=run_id,
        json_name=JSON_ARTIFACT,
        markdown_name=MARKDOWN_ARTIFACT,
    )
    if payload.get("status") == "passed":
        valid, reason = validate_guided_boundary_artifact_root(
            published_dir,
            canonical_root=output_dir,
        )
        if not valid:
            print(f"Current Guided evidence rejected: {reason}", file=sys.stderr)
            return_code = 1
    print(f"Wrote {published_dir / JSON_ARTIFACT}")
    print(f"Wrote {published_dir / MARKDOWN_ARTIFACT}")
    return return_code


def _record_guided_source_stability(
    payload: dict[str, Any],
    *,
    started: dict[str, Any],
    completed: dict[str, Any],
) -> bool:
    """Reject a run when capture-relevant source changes during execution."""
    started_digest = str(started.get("source_digest") or "")
    completed_digest = str(completed.get("source_digest") or "")
    stable = bool(started_digest and started_digest == completed_digest)
    payload["capture_source"] = {
        "source_digest_at_start": started_digest,
        "source_digest_at_completion": completed_digest,
        "stable": stable,
    }
    if stable:
        return True
    payload["status"] = "failed"
    payload["failure_reason"] = (
        "Product source changed during Guided capture; discard this run."
    )
    return False


def run_guided_boundary_walkthrough(
    app: QApplication,
    *,
    output_dir: Path,
    source_path: Path,
    model_id: str,
    timeout_seconds: int,
    initial_runtime: dict[str, object],
) -> dict[str, Any]:
    """Compose real product owners around the one-turn UI handoff driver."""
    from XBrainLab.backend.application import get_application_service
    from XBrainLab.backend.study import Study
    from XBrainLab.ui.main_window import MainWindow

    _clear_saved_main_window_geometry()
    study = Study()
    service = get_application_service(study)
    window = MainWindow(study)
    _set_baseline_window_geometry(window)
    window.show()
    state = GuidedBoundaryState(
        source_path=str(source_path.resolve()),
        model_id=model_id,
        prompts=build_guided_prompts(source_path),
        started_at=time.monotonic(),
    )
    tool_trace = GuidedToolTraceRecorder(_structured_value)
    hooks = GuidedBoundaryHooks(
        capture=_capture_current_window,
        handle_setup_dialog=_handle_setup_dialog,
        assistant_surface_ready=assistant_surface_ready,
        collect_visible_messages=collect_visible_messages,
        collect_executed_tools=collect_executed_tools,
        collect_model_proposals=collect_model_proposals,
        attach_tool_trace=tool_trace.attach,
        detach_tool_trace=tool_trace.detach,
        collect_tool_attempt_traces=tool_trace.snapshot,
        publication_evidence=publication_evidence,
        runtime_evidence=runtime_evidence,
        structured_value=_structured_value,
        turn_metrics_evidence=_turn_metrics_evidence,
        has_raw_debug_text=has_raw_debug_text,
        has_runtime_error_text=_has_runtime_error_text,
        schedule=lambda delay, callback: QTimer.singleShot(delay, callback),
        now=time.monotonic,
    )
    return GuidedBoundaryDriver(
        app=app,
        window=window,
        service=service,
        output_dir=output_dir,
        timeout_seconds=timeout_seconds,
        state=state,
        hooks=hooks,
    ).run(initial_runtime)


def _handle_setup_dialog(widget: Any) -> dict[str, Any] | None:
    if str(widget.windowTitle()).casefold() != "local assistant runtime":
        return None
    return approve_product_dialog(widget)


def _terminal_payload(
    *,
    status: str,
    reason: str,
    model_id: str,
    runtime_summary: dict[str, object],
    source_path: Path | None = None,
    exception: str = "",
) -> dict[str, Any]:
    source = source_path or Path("/unavailable/source.fif")
    state = GuidedBoundaryState(
        source_path=str(source),
        model_id=model_id,
        prompts=build_guided_prompts(source),
        started_at=time.monotonic(),
        status=status,
        failure_reason=reason,
        exception=exception,
    )
    return GuidedBoundaryEvidenceAssembler(
        state=state,
        initial_runtime=runtime_summary,
        runtime_evidence=runtime_evidence,
        structured_value=_structured_value,
    ).build()


def _enforce_offline_runtime() -> None:
    _force_offline_hf_runtime()
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a real local Phi-4 Guided Workflow until the typed Data Import "
            "handoff, capture the wizard, cancel it, and prove state did not mutate."
        )
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL_ID,
        help="Exact local model id; this proof accepts Phi-4 only.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for screenshots and JSON/Markdown evidence.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=480,
        help="Maximum time for startup, one turn, UI cancellation, and shutdown.",
    )
    return parser
