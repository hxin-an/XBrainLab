"""Data Interpretation command coordinator.

This module owns the Data Interpretation lifecycle state and application logic
that used to live inside ``ApplicationService``. ``ApplicationService`` remains
the command/result envelope and capability gate.
"""

from __future__ import annotations

from collections.abc import Callable
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
    InterpretationDecision,
    build_import_recipe,
    build_interpretation_candidate,
    build_interpretation_preview,
    choices_from_import_recipe,
    load_import_recipe,
    scan_source_path,
    validate_interpretation_candidate,
)
from .data_interpretation_apply import DataInterpretationApplyService
from .data_interpretation_state import DataInterpretationSessionState
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
        self.state = DataInterpretationSessionState(
            data_filepath=self._data_filepath,
        )
        self.apply_service = DataInterpretationApplyService(
            self.dataset,
            data_filename=self._data_filename,
            data_filepath=self._data_filepath,
            record_label_import=self.state.record_label_import_for_recipe,
        )

    def handle_scan_source(self, command: Command) -> HandlerResult:
        """Scan a file, folder, BIDS root, device export, or recipe source."""
        if not isinstance(command, ScanSourceCommand):
            raise TypeError("Invalid command for scan_source")
        scan_id = self.state.next_id("scan")
        scan = scan_source_path(
            scan_id=scan_id,
            source_path=command.source_path,
            source_hint=command.source_hint,
        )
        self.state.record_scan(scan)
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
        scan = self.state.resolve_scan(command.scan_id)
        candidate_id = self.state.next_id("candidate")
        preview_id = self.state.next_id("preview")
        candidate = build_interpretation_candidate(
            candidate_id=candidate_id,
            scan=scan,
            choices=command.choices,
        )
        preview = build_interpretation_preview(
            preview_id=preview_id,
            candidate=candidate,
            scan=scan,
        )
        self.state.record_preview(candidate, preview)
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
        candidate = self.state.resolve_candidate(command.candidate_id)
        decision = validate_interpretation_candidate(candidate)
        self.state.record_validation(candidate.candidate_id, decision)
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
        candidate = self.state.resolve_candidate(command.candidate_id)
        decision = self.state.resolve_validation_decision(candidate.candidate_id)
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
        interpretation_id = self.state.next_id("interpretation")
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
        self.state.record_applied(applied)
        metadata_apply = self.apply_service.apply_candidate_metadata_to_loaded_data(
            candidate,
        )
        label_apply = self.apply_service.apply_label_carriers(candidate)
        applied_payload = self.state.resolve_applied_interpretation().to_dict()
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
        applied = self.state.resolve_applied_interpretation()
        candidate = self.state.resolve_candidate(applied.candidate_id)
        recipe_id = self.state.next_id("recipe")
        recipe = build_import_recipe(
            recipe_id=recipe_id,
            applied=applied,
            warnings=list(candidate.warnings),
        )
        if command.recipe_path:
            recipe.write_json(command.recipe_path)
        self.state.record_recipe(recipe, recipe_path=command.recipe_path)
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
        scan_id = self.state.next_id("scan")
        scan = scan_source_path(
            scan_id=scan_id,
            source_path=recipe.source_path,
            source_hint=recipe.source_kind or "recipe",
        )
        candidate_id = self.state.next_id("candidate")
        candidate = build_interpretation_candidate(
            candidate_id=candidate_id,
            scan=scan,
            choices=choices_from_import_recipe(recipe),
        )
        preview_id = self.state.next_id("preview")
        preview = build_interpretation_preview(
            preview_id=preview_id,
            candidate=candidate,
            scan=scan,
            recipe=recipe,
        )
        decision = validate_interpretation_candidate(candidate)
        self.state.record_recipe_reload(
            recipe=recipe,
            scan=scan,
            candidate=candidate,
            preview=preview,
            decision=decision,
            recipe_path=command.recipe_path,
        )
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
        return self.state.snapshot()

    def clear(self) -> None:
        """Clear Data Interpretation lifecycle state."""
        self.state.clear()

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
        return self.state.record_label_import_for_recipe(
            plan=plan,
            mode=mode,
            target_files=target_files,
            file_mapping=file_mapping,
            selected_event_names=selected_event_names,
            success_count=success_count,
        )
