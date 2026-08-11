"""Real Qt/ApplicationService capture for the compact MOABB journeys."""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat

from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    collect_source_identity,
)
from scripts.dev.moabb_user_journeys.evidence import artifact_record
from scripts.dev.moabb_user_journeys.product import run_dataset_journey
from scripts.dev.moabb_user_journeys.registry import (
    REPO_ROOT,
    materialize_dataset,
    registry_sha256,
)
from scripts.dev.moabb_user_journeys.storage import write_json_atomic

from .contract import (
    build_capture_manifest,
    dataset_revision,
    validate_capture_manifest,
    write_capture_manifest,
)

WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 800
IMPORT_WIDTH = 1180
IMPORT_HEIGHT = 760
VISIBLE_FORBIDDEN = (
    "ApplicationService",
    "BackendFacade",
    "Traceback",
    "scan_source",
    "preview_interpretation",
    "validate_interpretation",
)


class _RetainedApplicationService:
    """Delegate to a real service while deferring runner-owned final close."""

    def __init__(self, service: Any) -> None:
        self.service = service

    def __getattr__(self, name: str) -> Any:
        return getattr(self.service, name)

    def close(self) -> None:
        """Keep the final publication alive until Qt screenshots are complete."""

    def wait_for_background_tasks(self, *, timeout: float | None = None) -> bool:
        """Preserve the runner wait while making its deferred close non-owning."""
        if timeout == 30.0:
            return True
        return bool(self.service.wait_for_background_tasks(timeout=timeout))


def capture_all_datasets(
    *,
    app: Any,
    registry: dict[str, Any],
    registry_path: Path,
    plan: dict[str, Any],
    cache: dict[str, Any],
    output_dir: Path,
    run_id: str,
    profile: str,
    mode: str,
    confirm_resource_plan: bool,
) -> dict[str, Any]:
    """Capture all declared datasets after exact-source cache validation."""
    if mode not in {"complete", "import-review"}:
        raise ValueError("mode must be complete or import-review")
    source_at_start = collect_source_identity(REPO_ROOT, refresh=True)
    failures: list[dict[str, Any]] = []
    source_by_dataset = _source_artifacts_by_dataset(plan, cache)
    data_root = Path(plan["data_root"])
    records: list[dict[str, Any]] = []
    output_dir.mkdir(parents=True, exist_ok=True)

    for registry_dataset in registry["datasets"]:
        dataset = materialize_dataset(registry_dataset, data_root=data_root)
        dataset_id = str(dataset["id"])
        dataset_dir = output_dir / dataset_id
        dataset_dir.mkdir(parents=True, exist_ok=True)
        source_artifacts = source_by_dataset.get(dataset_id, [])
        record = _empty_dataset_record(
            registry_dataset,
            source_artifacts=source_artifacts,
            plan_id=str(plan["plan_id"]),
            profile=profile,
        )

        try:
            record["stages"]["import_review"] = _capture_import_review(
                app,
                dataset,
                dataset_dir=dataset_dir,
                output_root=output_dir,
            )
        except Exception as exc:
            failure = _failure(dataset_id, "import_review", exc)
            failures.append(failure)
            record["limitations"].append(failure["message"])

        if mode == "import-review":
            record["execution"] = {
                "profile": profile,
                "status": "not_run",
                "evidence_sha256": "",
                "quality_evidence_status": "pending",
            }
            records.append(record)
            continue

        try:
            _capture_finished_journey(
                app,
                dataset,
                dataset_dir=dataset_dir,
                output_root=output_dir,
                source_artifacts=source_artifacts,
                execution_profile=profile,
                confirm_resource_plan=confirm_resource_plan,
                record=record,
            )
        except Exception as exc:
            failure = _failure(dataset_id, "finished_journey", exc)
            failures.append(failure)
            record["limitations"].append(failure["message"])
        records.append(record)

    source_at_completion = collect_source_identity(REPO_ROOT, refresh=True)
    payload = build_capture_manifest(
        run_id=run_id,
        registry_sha256=registry_sha256(registry_path),
        registry_profile=str(registry["profile_id"]),
        plan_id=str(plan["plan_id"]),
        application_source=source_at_completion,
        application_source_at_start=source_at_start,
        qt_platform=str(app.platformName()),
        datasets=records,
        failures=failures,
    )
    ok, reason = validate_capture_manifest(payload, output_dir=output_dir)
    if not ok:
        payload["status"] = "failed"
        payload["site_qualification"] = {
            "eligible": False,
            "publication_status_ceiling": "unverified",
            "reason_codes": ["capture_manifest_validation_failed"],
        }
        payload["failures"].append(
            {
                "dataset_id": None,
                "stage": "manifest_validation",
                "type": "EvidenceValidationError",
                "message": reason,
            }
        )
    write_capture_manifest(output_dir, payload)
    return payload


def _empty_dataset_record(
    registry_dataset: Mapping[str, Any],
    *,
    source_artifacts: Sequence[Mapping[str, Any]],
    plan_id: str,
    profile: str,
) -> dict[str, Any]:
    dataset_id = str(registry_dataset["id"])
    return {
        "dataset_id": dataset_id,
        "dataset_revision": dataset_revision(registry_dataset),
        "exact_source": {
            "status": "verified",
            "plan_id": plan_id,
            "files": [dict(item) for item in source_artifacts],
        },
        "execution": {
            "profile": profile,
            "status": "pending",
            "evidence_sha256": "",
            "quality_evidence_status": "pending",
        },
        "stages": {
            "import_review": _unverified_stage(
                "Qt import/review capture did not complete."
            ),
            "evaluation": _unverified_stage(
                "ApplicationService evaluation evidence is unavailable."
            ),
            "saliency": _unverified_stage(
                "ApplicationService saliency evidence is unavailable."
            ),
        },
        "limitations": list(registry_dataset.get("claim_boundary") or []),
    }


def _capture_import_review(
    app: Any,
    dataset: Mapping[str, Any],
    *,
    dataset_dir: Path,
    output_root: Path,
) -> dict[str, Any]:
    from XBrainLab.backend.application import (
        PreviewInterpretationCommand,
        ScanSourceCommand,
        ValidateInterpretationCommand,
        get_application_service,
    )
    from XBrainLab.backend.study import Study
    from XBrainLab.ui.dialogs.dataset import (
        DataInterpretationPreviewDialog,
    )

    study = Study()
    service = get_application_service(study)
    dialog = None
    commands: list[str] = []
    try:
        scan = _execute_required(
            service,
            ScanSourceCommand(
                source_path=str(dataset["import"]["source_path"]),
                source_hint=str(dataset["import"]["source_hint"]),
            ),
        )
        commands.append(str(scan.command_name))
        preview = _execute_required(
            service,
            PreviewInterpretationCommand(
                choices=dict(dataset["import"]["choices"]),
            ),
        )
        commands.append(str(preview.command_name))
        validation = _execute_required(service, ValidateInterpretationCommand())
        commands.append(str(validation.command_name))
        scan_result = _required_diagnostic(scan, "scan_result")
        preview_result = _required_diagnostic(preview, "preview")
        validation_decision = _required_diagnostic(validation, "validation_decision")
        dialog = DataInterpretationPreviewDialog(
            parent=None,
            scan_result=scan_result,
            preview=preview_result,
            validation_decision=validation_decision,
            choices=dict(dataset["import"]["choices"]),
        )
        dialog.resize(IMPORT_WIDTH, IMPORT_HEIGHT)
        dialog.show()
        _process_events(app, 250)
        step_titles = list(getattr(dialog, "_step_titles", []))
        if "Review and Import" not in step_titles:
            raise RuntimeError("Product dialog has no Review and Import stage.")
        dialog._go_to_step(step_titles.index("Review and Import"))
        _process_events(app, 500)
        visible_text = _visible_label_text(dialog)
        _assert_product_language(visible_text)
        screenshot_path = dataset_dir / "import-review.png"
        _capture_widget(dialog, screenshot_path, app=app)
        screenshot_path = _content_address(screenshot_path)
        return {
            "status": "observed",
            "application_service_commands": commands,
            "decision": str(validation_decision.get("decision") or ""),
            "selected_eeg_files": list(preview_result.get("selected_eeg_files") or []),
            "visible_text": visible_text,
            "application_state": service.get_state().to_dict(),
            "screenshot": _screenshot_record(
                screenshot_path,
                output_root=output_root,
            ),
        }
    finally:
        if dialog is not None:
            dialog.close()
            dialog.deleteLater()
            _process_events(app, 100)
        service.close()


def _capture_finished_journey(
    app: Any,
    dataset: dict[str, Any],
    *,
    dataset_dir: Path,
    output_root: Path,
    source_artifacts: list[dict[str, Any]],
    execution_profile: str,
    confirm_resource_plan: bool,
    record: dict[str, Any],
) -> None:
    from XBrainLab.backend.application import get_application_service
    from XBrainLab.backend.study import Study

    study = Study()
    service = get_application_service(study)
    retained = _RetainedApplicationService(service)
    journey_root = dataset_dir / "application-service"
    evidence = run_dataset_journey(
        dataset,
        run_root=journey_root,
        source_artifacts=source_artifacts,
        execution_profile=execution_profile,
        confirm_resource_plan=confirm_resource_plan,
        attempt=1,
        previous_failure=None,
        service_factory=lambda: retained,
    )
    evidence_path = dataset_dir / "journey-evidence.json"
    try:
        if evidence.get("failures"):
            write_json_atomic(evidence_path, evidence)
            record["execution"] = _execution_record(
                evidence,
                evidence_path=evidence_path,
                output_root=output_root,
                profile=execution_profile,
            )
            messages = [
                str(item.get("message") or "Journey execution failed.")
                for item in evidence["failures"]
                if isinstance(item, Mapping)
            ]
            record["limitations"].extend(messages)
            return

        evaluation, saliency, capture_limitations = _capture_final_panels(
            app,
            study=study,
            dataset=dataset,
            evidence=evidence,
            dataset_dir=dataset_dir,
            output_root=output_root,
        )
        record["stages"]["evaluation"] = evaluation
        record["stages"]["saliency"] = saliency
        record["limitations"].extend(capture_limitations)
        evidence["screenshots"] = [
            artifact_record(
                output_root / stage["screenshot"]["path"],
                kind="qt_screenshot",
                stage=stage_name,
            )
            for stage_name, stage in (
                ("evaluation", evaluation),
                ("saliency", saliency),
            )
            if stage.get("status") in {"observed", "bounded"}
        ]
        write_json_atomic(evidence_path, evidence)
        record["execution"] = _execution_record(
            evidence,
            evidence_path=evidence_path,
            output_root=output_root,
            profile=execution_profile,
        )
    finally:
        service.close()
        _process_events(app, 100)


def _capture_final_panels(
    app: Any,
    *,
    study: Any,
    dataset: Mapping[str, Any],
    evidence: Mapping[str, Any],
    dataset_dir: Path,
    output_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    from XBrainLab.ui.main_window import MainWindow

    window = MainWindow(study)
    window.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    window.show()
    _process_events(app, 350)
    evaluation_stage = _unverified_stage("EvaluationPanel capture did not complete.")
    saliency_stage = _unverified_stage(
        "VisualizationPanel saliency capture did not complete."
    )
    limitations: list[str] = []
    try:
        try:
            evaluation_stage = _capture_evaluation_panel(
                app,
                window=window,
                dataset=dataset,
                evidence=evidence,
                dataset_dir=dataset_dir,
                output_root=output_root,
            )
        except Exception as exc:
            reason = _stage_limitation("Evaluation", exc)
            evaluation_stage = _unverified_stage(reason)
            limitations.append(reason)

        try:
            saliency_stage = _capture_saliency_panel(
                app,
                window=window,
                dataset=dataset,
                evidence=evidence,
                dataset_dir=dataset_dir,
                output_root=output_root,
            )
        except Exception as exc:
            reason = _stage_limitation("Saliency", exc)
            saliency_stage = _unverified_stage(reason)
            limitations.append(reason)
        return evaluation_stage, saliency_stage, limitations
    finally:
        window.close()
        _process_events(app, 500)
        window.deleteLater()
        _process_events(app, 100)


def _capture_evaluation_panel(
    app: Any,
    *,
    window: Any,
    dataset: Mapping[str, Any],
    evidence: Mapping[str, Any],
    dataset_dir: Path,
    output_root: Path,
) -> dict[str, Any]:
    from scripts.dev.capture_visualization_render_walkthrough import (
        _capture_fully_rendered_window,
    )
    from scripts.dev.ui_navigation import open_workflow_panel

    panel = open_workflow_panel(window, 3, timeout_ms=30_000)
    panel.mark_refresh_dirty()
    panel.update_panel()
    _select_combo_data(panel.split_combo, "test")
    panel.update_views()
    _process_events(app, 750)
    publication = getattr(panel, "_evaluation_render", None)
    if publication is None:
        raise RuntimeError("EvaluationPanel did not publish a final render.")
    render_data = publication.data
    if render_data.evaluation_split != "test" or len(render_data.labels) < 1:
        raise RuntimeError("EvaluationPanel did not render held-out test results.")
    matrix_canvas = getattr(panel.matrix_widget, "canvas", None)
    bar_canvas = getattr(panel.bar_chart, "canvas", None)
    if not _matplotlib_canvas_ready(matrix_canvas) or not _matplotlib_canvas_ready(
        bar_canvas
    ):
        raise RuntimeError("EvaluationPanel charts did not finish rendering.")
    screenshot_path = dataset_dir / "evaluation.png"
    code = _capture_fully_rendered_window(
        window,
        screenshot_path,
        capture_method="qt_widget_grab",
    )
    if code != 0:
        raise RuntimeError("EvaluationPanel screenshot capture failed.")
    screenshot_path = _content_address(screenshot_path)
    expected_labels = _expected_route_class_labels(dataset)
    observed_labels = [
        str(value) for _, value in sorted(render_data.class_labels.items())
    ]
    return {
        "status": "bounded",
        "application_service_commands": _trace_commands(
            evidence,
            stages={"evaluate", "training_history"},
            required_fallback="evaluate",
        ),
        "split": str(render_data.evaluation_split),
        "sample_count": len(render_data.labels),
        "class_count": len(render_data.class_labels),
        "expected_class_labels": expected_labels,
        "observed_class_labels": observed_labels,
        "route_semantics_match": set(observed_labels) == set(expected_labels),
        "screenshot": _screenshot_record(
            screenshot_path,
            output_root=output_root,
        ),
    }


def _capture_saliency_panel(
    app: Any,
    *,
    window: Any,
    dataset: Mapping[str, Any],
    evidence: Mapping[str, Any],
    dataset_dir: Path,
    output_root: Path,
) -> dict[str, Any]:
    from scripts.dev.capture_visualization_render_walkthrough import (
        _capture_render_tab,
    )
    from scripts.dev.ui_navigation import open_workflow_panel

    panel = open_workflow_panel(window, 4, timeout_ms=30_000)
    panel.mark_refresh_dirty()
    panel.update_panel()
    _process_events(app, 300)
    render = _capture_render_tab(
        app,
        window,
        dataset_dir,
        {
            "tab": "Saliency Map",
            "screenshot": "saliency.png",
            "expected_context": "True class · Mean over EEG epochs",
        },
    )
    if not render.get("ok"):
        raise RuntimeError(
            str(render.get("failure_reason") or "Saliency render failed.")
        )
    screenshot_path = _resolve_generated_screenshot(render.get("screenshot"))
    expected_labels = _expected_route_class_labels(dataset)
    observed_labels = _held_out_class_labels(evidence)
    return {
        "status": "bounded",
        "application_service_commands": _trace_commands(
            evidence,
            stages={"configure_saliency", "saliency_query"},
            required_fallback="saliency",
        ),
        "method": str(panel.method_combo.currentText()),
        "source_split": _first_saliency_source_split(evidence),
        "route_semantics_match": set(observed_labels) == set(expected_labels),
        "render_evidence": {
            "axes_count": int(render.get("axes_count") or 0),
            "image_count": int(render.get("image_count") or 0),
            "canvas_visible": bool(render.get("canvas_visible")),
            "explanation_context": str(render.get("explanation_context") or ""),
        },
        "screenshot": _screenshot_record(
            screenshot_path,
            output_root=output_root,
        ),
    }


def _source_artifacts_by_dataset(
    plan: Mapping[str, Any],
    cache: Mapping[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    plan_files = {
        str(Path(item["cache_path"]).resolve()): item
        for item in plan.get("files", [])
        if isinstance(item, Mapping)
    }
    grouped: dict[str, list[dict[str, Any]]] = {}
    for artifact in cache.get("files", []):
        if not isinstance(artifact, Mapping):
            continue
        path = str(Path(str(artifact["path"])).resolve())
        planned = plan_files.get(path)
        if planned is None:
            raise ValueError(f"Validated cache file is absent from plan: {path}")
        dataset_id = str(planned["dataset_id"])
        grouped.setdefault(dataset_id, []).append(dict(artifact))
    return grouped


def _execute_required(service: Any, command: Any) -> Any:
    result = service.execute(command)
    if not result.ok:
        raise RuntimeError(
            str(result.error_message or result.message or "Product command failed.")
        )
    return result


def _required_diagnostic(result: Any, name: str) -> dict[str, Any]:
    value = result.diagnostics.get(name)
    if not isinstance(value, dict):
        raise RuntimeError(f"ApplicationService did not publish {name} diagnostics.")
    return value


def _capture_widget(widget: Any, path: Path, *, app: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    widget.ensurePolished()
    widget.update()
    _process_events(app, 100)
    pixmap = widget.grab()
    if pixmap.isNull() or not pixmap.save(str(path), "PNG"):
        raise RuntimeError(f"Qt could not capture {path.name}.")
    _assert_useful_image(path)


def _assert_useful_image(path: Path) -> None:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        stats = ImageStat.Stat(rgb)
        variance = sum(float(value) for value in stats.var)
        if image.width < 320 or image.height < 240 or variance < 3.0:
            raise RuntimeError(f"Screenshot is blank or too small: {path.name}.")


def _content_address(path: Path) -> Path:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    destination = path.with_name(f"{path.stem}-{digest[:12]}{path.suffix}")
    path.replace(destination)
    return destination


def _screenshot_record(path: Path, *, output_root: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    root = output_root.resolve()
    relative = resolved.relative_to(root).as_posix()
    content = resolved.read_bytes()
    with Image.open(resolved) as image:
        dimensions = [int(image.width), int(image.height)]
        image_format = str(image.format or "")
        image.verify()
    return {
        "path": relative,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "dimensions": dimensions,
        "format": image_format,
    }


def _visible_label_text(widget: Any) -> list[str]:
    from PyQt6.QtWidgets import QLabel

    return [
        " ".join(str(label.text()).split())
        for label in widget.findChildren(QLabel)
        if label.isVisible() and str(label.text()).strip()
    ]


def _assert_product_language(values: Sequence[str]) -> None:
    text = "\n".join(values)
    findings = [marker for marker in VISIBLE_FORBIDDEN if marker in text]
    if findings:
        raise RuntimeError(
            "Import/review UI exposes internal product language: " + ", ".join(findings)
        )


def _process_events(app: Any, wait_ms: int) -> None:
    deadline = time.monotonic() + max(0, wait_ms) / 1000.0
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()


def _select_combo_data(combo: Any, value: object) -> None:
    for index in range(combo.count()):
        if combo.itemData(index) == value:
            combo.setCurrentIndex(index)
            return
    raise RuntimeError(f"Product control does not expose required selection: {value}")


def _matplotlib_canvas_ready(canvas: Any) -> bool:
    if canvas is None or not canvas.isVisible():
        return False
    draw = getattr(canvas, "draw", None)
    if not callable(draw):
        return False
    draw()
    figure = getattr(canvas, "figure", None)
    axes = list(getattr(figure, "axes", []) or [])
    return bool(axes)


def _trace_commands(
    evidence: Mapping[str, Any],
    *,
    stages: set[str],
    required_fallback: str,
) -> list[str]:
    commands = [
        str(item.get("command") or "")
        for item in evidence.get("command_trace", [])
        if isinstance(item, Mapping) and str(item.get("stage") or "") in stages
    ]
    return [command for command in commands if command] or [required_fallback]


def _first_saliency_source_split(evidence: Mapping[str, Any]) -> str:
    artifacts = evidence.get("saliency", {}).get("artifacts", [])
    for artifact in artifacts:
        if isinstance(artifact, Mapping) and artifact.get("source_split"):
            return str(artifact["source_split"])
    return ""


def _held_out_class_labels(evidence: Mapping[str, Any]) -> list[str]:
    evaluations = evidence.get("metrics", {}).get("held_out_evaluations", [])
    for evaluation in evaluations:
        if not isinstance(evaluation, Mapping):
            continue
        labels = evaluation.get("class_labels")
        if isinstance(labels, Mapping):
            return [str(value) for _, value in sorted(labels.items())]
    return []


def _expected_route_class_labels(dataset: Mapping[str, Any]) -> list[str]:
    choices = dataset.get("import", {}).get("choices", {})
    mappings = choices.get("run_event_mappings", {})
    labels = (
        {
            str(label)
            for mapping in mappings.values()
            if isinstance(mapping, Mapping)
            for label in mapping.values()
            if str(label)
        }
        if isinstance(mappings, Mapping)
        else set()
    )
    if labels:
        return sorted(labels)
    return [str(item) for item in dataset["workflow"]["epoch"]["event_ids"]]


def _resolve_generated_screenshot(value: object) -> Path:
    path = Path(str(value or ""))
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve(strict=True)


def _execution_record(
    evidence: Mapping[str, Any],
    *,
    evidence_path: Path,
    output_root: Path,
    profile: str,
) -> dict[str, Any]:
    digest = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    return {
        "profile": profile,
        "status": "failed" if evidence.get("failures") else "completed",
        "evidence_path": evidence_path.resolve()
        .relative_to(output_root.resolve())
        .as_posix(),
        "evidence_sha256": digest,
        "quality_evidence_status": str(
            evidence.get("quality_evidence_status") or "pending"
        ),
    }


def _unverified_stage(reason: str) -> dict[str, Any]:
    return {"status": "unverified", "reason": str(reason)}


def _failure(dataset_id: str, stage: str, exc: Exception) -> dict[str, Any]:
    message = re.sub(r"\s+", " ", str(exc)).strip() or type(exc).__name__
    return {
        "dataset_id": dataset_id,
        "stage": stage,
        "type": type(exc).__name__,
        "message": message,
    }


def _stage_limitation(stage: str, exc: Exception) -> str:
    message = re.sub(r"\s+", " ", str(exc)).strip() or type(exc).__name__
    return f"{stage} product capture unavailable: {message}"
