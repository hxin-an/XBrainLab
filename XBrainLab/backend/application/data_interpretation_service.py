"""Data Interpretation command coordinator.

This module owns the Data Interpretation lifecycle state and application logic
that used to live inside ``ApplicationService``. ``ApplicationService`` remains
the command/result envelope and capability gate.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from .commands import (
    ApplyInterpretationCommand,
    Command,
    LabelImportPlan,
    PreviewInterpretationCommand,
    ReloadInterpretationRecipeCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
)
from .data_interpretation import (
    AppliedInterpretation,
    ImportRecipe,
    InterpretationCandidate,
    InterpretationDecision,
    InterpretationPreview,
    ScanResult,
    ValidationDecision,
    build_import_recipe,
    build_interpretation_candidate,
    build_interpretation_preview,
    load_import_recipe,
    scan_source_path,
    validate_interpretation_candidate,
)
from .data_interpretation_apply import DataInterpretationApplyService
from .errors import ApplicationError, PreconditionError
from .results import ErrorType
from .state import InterpretationStateSnapshot

HandlerResult = str | tuple[str, dict[str, Any]]


class DataInterpretationCommandService:
    """Handle Data Interpretation commands and related recipe state."""

    def __init__(
        self,
        dataset_controller: Any,
        *,
        data_filename: Callable[[Any], str],
        data_filepath: Callable[[Any], str],
    ) -> None:
        self.dataset = dataset_controller
        self._data_filename = data_filename
        self._data_filepath = data_filepath
        self._scan_results: dict[str, ScanResult] = {}
        self._candidates: dict[str, InterpretationCandidate] = {}
        self._previews: dict[str, InterpretationPreview] = {}
        self._validation_decisions: dict[str, ValidationDecision] = {}
        self._applied_interpretations: dict[str, AppliedInterpretation] = {}
        self._recipes: dict[str, ImportRecipe] = {}
        self._latest_scan_id: str | None = None
        self._latest_candidate_id: str | None = None
        self._latest_preview_id: str | None = None
        self._latest_interpretation_id: str | None = None
        self._latest_recipe_id: str | None = None
        self._latest_recipe_path: str | None = None
        self._interpretation_counter = 0
        self.apply_service = DataInterpretationApplyService(
            self.dataset,
            data_filename=self._data_filename,
            data_filepath=self._data_filepath,
            record_label_import=self.record_label_import_for_recipe,
        )

    def handle_scan_source(self, command: Command) -> HandlerResult:
        """Scan a file, folder, BIDS root, device export, or recipe source."""
        if not isinstance(command, ScanSourceCommand):
            raise TypeError("Invalid command for scan_source")
        scan_id = self._next_interpretation_id("scan")
        scan = scan_source_path(
            scan_id=scan_id,
            source_path=command.source_path,
            source_hint=command.source_hint,
        )
        self._scan_results[scan_id] = scan
        self._latest_scan_id = scan_id
        self._latest_candidate_id = None
        self._latest_preview_id = None
        return (
            f"Scanned source and found {len(scan.eeg_files)} EEG file(s).",
            {
                "payload_type": "scan_result",
                "scan_result": scan.to_dict(),
            },
        )

    def handle_preview_interpretation(self, command: Command) -> HandlerResult:
        """Build a reviewable interpretation candidate and preview."""
        if not isinstance(command, PreviewInterpretationCommand):
            raise TypeError("Invalid command for preview_interpretation")
        scan = self._resolve_scan(command.scan_id)
        candidate_id = self._next_interpretation_id("candidate")
        preview_id = self._next_interpretation_id("preview")
        candidate = build_interpretation_candidate(
            candidate_id=candidate_id,
            scan=scan,
            choices=command.choices,
        )
        preview = build_interpretation_preview(
            preview_id=preview_id,
            candidate=candidate,
        )
        self._candidates[candidate_id] = candidate
        self._previews[preview_id] = preview
        self._latest_candidate_id = candidate_id
        self._latest_preview_id = preview_id
        return (
            "Interpretation preview ready.",
            {
                "payload_type": "interpretation_preview",
                "candidate": candidate.to_dict(),
                "preview": preview.to_dict(),
            },
        )

    def handle_validate_interpretation(self, command: Command) -> HandlerResult:
        """Validate an interpretation candidate against review boundaries."""
        if not isinstance(command, ValidateInterpretationCommand):
            raise TypeError("Invalid command for validate_interpretation")
        candidate = self._resolve_candidate(command.candidate_id)
        decision = validate_interpretation_candidate(candidate)
        self._validation_decisions[candidate.candidate_id] = decision
        return (
            f"Interpretation validation: {decision.decision}.",
            {
                "payload_type": "validation_decision",
                "validation_decision": decision.to_dict(),
            },
        )

    def handle_apply_interpretation(self, command: Command) -> HandlerResult:
        """Apply a validated interpretation to the active dataset."""
        if not isinstance(command, ApplyInterpretationCommand):
            raise TypeError("Invalid command for apply_interpretation")
        candidate = self._resolve_candidate(command.candidate_id)
        decision = self._validation_decisions.get(candidate.candidate_id)
        if decision is None:
            raise PreconditionError("Validate an interpretation before applying it.")
        if decision.decision == InterpretationDecision.BLOCKED.value:
            blocked = (
                "; ".join(decision.blocked_reasons) or "Interpretation is blocked."
            )
            raise PreconditionError(blocked)
        count, errors = self.dataset.import_files(candidate.selected_eeg_files)
        if count == 0 and errors:
            raise ApplicationError(
                message=f"Failed to apply interpretation: {errors}",
                error_type=ErrorType.RUNTIME,
                recoverable=True,
                diagnostics={"errors": errors},
            )
        interpretation_id = self._next_interpretation_id("interpretation")
        confirmations = (
            list(decision.required_confirmations)
            if decision.decision == InterpretationDecision.NEEDS_CONFIRMATION.value
            else []
        )
        applied = AppliedInterpretation(
            interpretation_id=interpretation_id,
            candidate_id=candidate.candidate_id,
            source_path=candidate.source_path,
            source_kind=candidate.source_kind,
            loaded_files=list(candidate.selected_eeg_files),
            label_carriers=list(candidate.label_carriers),
            label_carrier_plan=[dict(item) for item in candidate.label_carrier_plan],
            metadata=list(candidate.metadata),
            format_capabilities=[dict(item) for item in candidate.format_capabilities],
            validation_decision=decision.decision,
            confirmations=confirmations,
            event_roles=dict(candidate.event_roles),
            class_map=dict(candidate.class_map),
            recipe_trace=[
                *candidate.recipe_trace,
                f"validation:{decision.decision}",
                f"applied:{interpretation_id}",
            ],
        )
        self._applied_interpretations[interpretation_id] = applied
        self._latest_interpretation_id = interpretation_id
        metadata_apply = self.apply_service.apply_candidate_metadata_to_loaded_data(
            candidate,
        )
        label_apply = self.apply_service.apply_label_carriers(candidate)
        applied_payload = self._applied_interpretations[interpretation_id].to_dict()
        label_message = ""
        if label_apply.get("status") == "applied":
            label_message = (
                f" Imported reviewed labels for "
                f"{label_apply.get('success_count', 0)} file(s)."
            )
        elif label_apply.get("status") == "failed":
            label_message = (
                f" Reviewed labels were not applied: "
                f"{label_apply.get('reason', 'unknown error')}."
            )
        return (
            f"Applied interpretation and loaded {count} file(s).{label_message}",
            {
                "payload_type": "applied_interpretation",
                "success_count": count,
                "errors": errors,
                "applied_interpretation": applied_payload,
                "metadata_apply": metadata_apply,
                "label_carriers_pending": list(candidate.label_carriers),
                "label_apply": label_apply,
            },
        )

    def handle_save_interpretation_recipe(self, command: Command) -> HandlerResult:
        """Persist the latest applied interpretation as a reusable recipe."""
        if not isinstance(command, SaveInterpretationRecipeCommand):
            raise TypeError("Invalid command for save_interpretation_recipe")
        applied = self._resolve_applied_interpretation()
        candidate = self._candidates[applied.candidate_id]
        recipe_id = self._next_interpretation_id("recipe")
        recipe = build_import_recipe(
            recipe_id=recipe_id,
            applied=applied,
            warnings=list(candidate.warnings),
        )
        if command.recipe_path:
            recipe.write_json(command.recipe_path)
            self._latest_recipe_path = command.recipe_path
        self._recipes[recipe_id] = recipe
        self._latest_recipe_id = recipe_id
        return (
            "Interpretation recipe saved.",
            {
                "payload_type": "import_recipe",
                "recipe": recipe.to_dict(),
                "recipe_path": command.recipe_path,
            },
        )

    def handle_reload_interpretation_recipe(self, command: Command) -> HandlerResult:
        """Reload a saved recipe and rebuild scan / preview / validation state."""
        if not isinstance(command, ReloadInterpretationRecipeCommand):
            raise TypeError("Invalid command for reload_interpretation_recipe")
        if not command.recipe_path:
            raise PreconditionError("recipe_path is required.")
        recipe = load_import_recipe(command.recipe_path)
        scan_id = self._next_interpretation_id("scan")
        scan = scan_source_path(
            scan_id=scan_id,
            source_path=recipe.source_path,
            source_hint=recipe.source_kind or "recipe",
        )
        candidate_id = self._next_interpretation_id("candidate")
        candidate = build_interpretation_candidate(
            candidate_id=candidate_id,
            scan=scan,
            choices={"recipe_id": recipe.recipe_id},
        )
        preview_id = self._next_interpretation_id("preview")
        preview = build_interpretation_preview(
            preview_id=preview_id,
            candidate=candidate,
        )
        decision = validate_interpretation_candidate(candidate)
        self._scan_results[scan_id] = scan
        self._candidates[candidate_id] = candidate
        self._previews[preview_id] = preview
        self._validation_decisions[candidate_id] = decision
        self._recipes[recipe.recipe_id] = recipe
        self._latest_scan_id = scan_id
        self._latest_candidate_id = candidate_id
        self._latest_preview_id = preview_id
        self._latest_recipe_id = recipe.recipe_id
        self._latest_recipe_path = command.recipe_path
        return (
            "Interpretation recipe reloaded for review.",
            {
                "payload_type": "recipe_reload_preview",
                "recipe": recipe.to_dict(),
                "scan_result": scan.to_dict(),
                "candidate": candidate.to_dict(),
                "preview": preview.to_dict(),
                "validation_decision": decision.to_dict(),
            },
        )

    def snapshot(self) -> InterpretationStateSnapshot:
        """Return the current Data Interpretation state snapshot."""
        scan = (
            self._scan_results.get(self._latest_scan_id)
            if self._latest_scan_id
            else None
        )
        candidate = (
            self._candidates.get(self._latest_candidate_id)
            if self._latest_candidate_id
            else None
        )
        preview = (
            self._previews.get(self._latest_preview_id)
            if self._latest_preview_id
            else None
        )
        decision = (
            self._validation_decisions.get(self._latest_candidate_id)
            if self._latest_candidate_id
            else None
        )
        applied = (
            self._applied_interpretations.get(self._latest_interpretation_id)
            if self._latest_interpretation_id
            else None
        )
        source_path = None
        source_kind = None
        if candidate is not None:
            source_path = candidate.source_path
            source_kind = candidate.source_kind
        elif scan is not None:
            source_path = scan.source_path
            source_kind = scan.source_kind
        warnings = []
        if preview is not None:
            warnings = list(preview.warnings)
        elif scan is not None:
            warnings = list(scan.warnings)
        label_carrier_plan = (
            applied.label_carrier_plan
            if applied is not None
            else candidate.label_carrier_plan
            if candidate is not None
            else preview.label_carrier_preview
            if preview is not None
            else []
        )
        format_capabilities = (
            applied.format_capabilities
            if applied is not None
            else candidate.format_capabilities
            if candidate is not None
            else preview.format_capabilities
            if preview is not None
            else scan.format_capabilities
            if scan is not None
            else []
        )
        event_roles = (
            applied.event_roles
            if applied is not None
            else candidate.event_roles
            if candidate is not None
            else preview.event_roles
            if preview is not None
            else {}
        )
        class_map = (
            applied.class_map
            if applied is not None
            else candidate.class_map
            if candidate is not None
            else preview.class_map
            if preview is not None
            else {}
        )
        return InterpretationStateSnapshot(
            has_scan_result=scan is not None,
            has_candidate=candidate is not None,
            has_preview=preview is not None,
            has_validation_decision=decision is not None,
            has_applied_interpretation=applied is not None,
            has_recipe=self._latest_recipe_id is not None,
            latest_scan_id=self._latest_scan_id,
            latest_candidate_id=self._latest_candidate_id,
            latest_preview_id=self._latest_preview_id,
            latest_interpretation_id=self._latest_interpretation_id,
            latest_recipe_id=self._latest_recipe_id,
            source_path=source_path,
            source_kind=source_kind,
            validation_decision=decision.decision if decision else None,
            pending_confirmation=(
                decision is not None
                and decision.decision == InterpretationDecision.NEEDS_CONFIRMATION.value
            ),
            blocked_reasons=list(decision.blocked_reasons if decision else []),
            warnings=warnings,
            summary=preview.summary if preview else None,
            metadata_preview=list(preview.metadata_preview if preview else []),
            label_carriers=list(
                applied.label_carriers
                if applied is not None
                else candidate.label_carriers
                if candidate is not None
                else []
            ),
            label_carrier_plan=[dict(item) for item in label_carrier_plan],
            format_capabilities=[dict(item) for item in format_capabilities],
            event_roles=dict(event_roles),
            class_map=dict(class_map),
            label_import_count=len(applied.label_imports) if applied else 0,
            label_imports=[dict(item) for item in applied.label_imports]
            if applied
            else [],
            recipe_path=self._latest_recipe_path,
        )

    def clear(self) -> None:
        """Clear Data Interpretation lifecycle state."""
        self._scan_results.clear()
        self._candidates.clear()
        self._previews.clear()
        self._validation_decisions.clear()
        self._applied_interpretations.clear()
        self._recipes.clear()
        self._latest_scan_id = None
        self._latest_candidate_id = None
        self._latest_preview_id = None
        self._latest_interpretation_id = None
        self._latest_recipe_id = None
        self._latest_recipe_path = None

    def record_label_import_for_recipe(
        self,
        *,
        plan: LabelImportPlan,
        mode: str,
        target_files: list[Any],
        file_mapping: dict[str, str],
        selected_event_names: set[str] | None,
        success_count: int,
    ) -> dict[str, Any] | None:
        """Record a post-load compatibility label import into recipe state."""
        if success_count <= 0:
            return None
        if not self._latest_interpretation_id:
            return None
        applied = self._applied_interpretations.get(self._latest_interpretation_id)
        if applied is None:
            return None

        label_carriers = sorted(str(key) for key in plan.label_map)
        record = {
            "mode": mode,
            "label_carriers": label_carriers,
            "target_files": [self._data_filepath(item) for item in target_files],
            "file_mapping": {
                str(key): str(value) for key, value in file_mapping.items()
            },
            "selected_event_names": sorted(selected_event_names or []),
            "class_map": self._label_mapping_for_recipe(plan.mapping),
            "success_count": int(success_count),
        }
        label_import_trace = f"label_import:{mode}:{success_count}"
        updated = replace(
            applied,
            label_carriers=sorted({*applied.label_carriers, *label_carriers}),
            label_imports=[*applied.label_imports, record],
            recipe_trace=[*applied.recipe_trace, label_import_trace],
        )
        self._applied_interpretations[updated.interpretation_id] = updated

        if self._latest_recipe_id and self._latest_recipe_id in self._recipes:
            recipe = self._recipes[self._latest_recipe_id]
            self._recipes[self._latest_recipe_id] = replace(
                recipe,
                label_carriers=sorted({*recipe.label_carriers, *label_carriers}),
                label_imports=[*recipe.label_imports, record],
                recipe_trace=[*recipe.recipe_trace, label_import_trace],
            )
        return record

    def _next_interpretation_id(self, prefix: str) -> str:
        self._interpretation_counter += 1
        return f"{prefix}-{self._interpretation_counter}"

    def _resolve_scan(self, scan_id: str | None) -> ScanResult:
        target_id = scan_id or self._latest_scan_id
        if not target_id or target_id not in self._scan_results:
            raise PreconditionError(
                "Scan a data source before previewing interpretation.",
            )
        return self._scan_results[target_id]

    def _resolve_candidate(
        self,
        candidate_id: str | None,
    ) -> InterpretationCandidate:
        target_id = candidate_id or self._latest_candidate_id
        if not target_id or target_id not in self._candidates:
            raise PreconditionError("Preview an interpretation candidate first.")
        return self._candidates[target_id]

    def _resolve_applied_interpretation(self) -> AppliedInterpretation:
        if (
            not self._latest_interpretation_id
            or self._latest_interpretation_id not in self._applied_interpretations
        ):
            raise PreconditionError("Apply an interpretation before saving a recipe.")
        return self._applied_interpretations[self._latest_interpretation_id]

    @staticmethod
    def _label_mapping_for_recipe(mapping: Any) -> dict[str, str]:
        if not isinstance(mapping, dict):
            return {}
        return {str(key): str(value) for key, value in mapping.items()}
