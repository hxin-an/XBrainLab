"""Data Interpretation command coordinator.

This module owns the Data Interpretation lifecycle state and application logic
that used to live inside ``ApplicationService``. ``ApplicationService`` remains
the command/result envelope and capability gate.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from XBrainLab.backend.utils.logger import logger

from .commands import (
    ApplyInterpretationCommand,
    Command,
    LabelImportPlan,
    PreviewInterpretationCommand,
    ReloadInterpretationRecipeCommand,
    ReviewInterpretationCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
)
from .data_interpretation import (
    AppliedInterpretation,
    InterpretationCandidate,
    InterpretationDecision,
    ValidationDecision,
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
from .errors import ApplicationError, ConfirmationRequiredError, PreconditionError
from .pipeline_transaction import PipelineStateSnapshot, PipelineStateTransaction
from .resource_guard import check_import_resource_preflight
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
        pipeline_transaction: PipelineStateTransaction | None = None,
    ) -> None:
        self.dataset = dataset_controller
        self._data_filename = data_filename
        self._data_filepath = data_filepath
        self._pipeline_transaction = pipeline_transaction
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
            label_sources=command.label_sources,
        )
        self.state.record_scan(scan)
        return (
            f"Scanned source and found {len(scan.eeg_files)} EEG file(s).",
            {
                "payload_type": "scan_result",
                "scan_result": scan.to_dict(),
            },
        )

    def handle_review_interpretation(self, command: Command) -> HandlerResult:
        """Scan, preview, and validate one Data Interpretation candidate."""
        if not isinstance(command, ReviewInterpretationCommand):
            raise TypeError("Invalid command for review_interpretation")
        scan_id = self.state.next_id("scan")
        scan = scan_source_path(
            scan_id=scan_id,
            source_path=command.source_path,
            source_hint=command.source_hint,
            label_sources=command.label_sources,
        )
        self.state.record_scan(scan)

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

        decision = validate_interpretation_candidate(candidate)
        self.state.record_validation(candidate.candidate_id, decision)
        return (
            f"Interpretation review: {decision.decision}.",
            {
                "payload_type": "interpretation_review",
                "scan_result": scan.to_dict(),
                "candidate": candidate.to_dict(),
                "preview": preview.to_dict(),
                "validation_decision": decision.to_dict(),
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
        self._ensure_candidate_can_apply(command, decision)
        snapshot = self._snapshot_raw_state()
        state_checkpoint = self.state.checkpoint_apply_state()
        try:
            count, errors = self._replace_active_raw_data(
                candidate.selected_eeg_files,
            )
            loaded_files = self._loaded_filepaths() or list(
                candidate.selected_eeg_files
            )
            interpretation_id = self.state.next_id("interpretation")
            applied = self._build_applied_interpretation(
                interpretation_id=interpretation_id,
                candidate=candidate,
                decision=decision,
                loaded_files=loaded_files,
            )
            self.state.record_applied(applied)
            metadata_apply = self.apply_service.apply_candidate_metadata_to_loaded_data(
                candidate,
            )
            label_apply = self.apply_service.apply_label_carriers(candidate)
            internal_epoch_hints = self.apply_service.record_internal_epoch_hints(
                candidate,
            )
            self._ensure_label_apply_succeeded(candidate, label_apply)
        except Exception:
            self.state.restore_apply_state(state_checkpoint)
            self._restore_raw_state(snapshot)
            raise
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
        elif label_apply.get("status") == "skipped" and candidate.label_carrier_plan:
            label_message = (
                f" Reviewed labels still need setup: "
                f"{label_apply.get('reason', 'manual review required')}."
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
                "internal_epoch_hints": internal_epoch_hints,
            },
        )

    def _ensure_candidate_can_apply(
        self,
        command: ApplyInterpretationCommand,
        decision: ValidationDecision,
    ) -> None:
        """Enforce the target candidate's own validation decision."""
        if decision.decision == InterpretationDecision.BLOCKED.value:
            blocked = (
                "; ".join(decision.blocked_reasons) or "Interpretation is blocked."
            )
            raise PreconditionError(blocked)
        if self._has_active_raw_data() and not command.confirmed:
            raise ConfirmationRequiredError(
                "Confirm replacing the currently loaded EEG data.",
            )
        if (
            decision.decision == InterpretationDecision.NEEDS_CONFIRMATION.value
            and not command.confirmed
        ):
            raise ConfirmationRequiredError(
                "Confirm this interpretation before applying it.",
            )

    def _replace_active_raw_data(
        self,
        paths: list[str],
    ) -> tuple[int, list[str]]:
        """Replace active raw data before importing reviewed interpretation files."""
        expected_count = len(paths)
        preflight = check_import_resource_preflight(paths)
        if not preflight.ok:
            raise PreconditionError(
                preflight.message,
                diagnostics={"resource_preflight": preflight.diagnostics},
            )
        loaded_files = list(self.dataset.get_loaded_data_list() or [])
        if self._pipeline_transaction is not None:
            self._pipeline_transaction.prepare_raw_replacement()
        else:
            clean_dataset = getattr(self.dataset, "clean_dataset", None)
            if loaded_files and callable(clean_dataset):
                clean_dataset()
        count, errors = self.dataset.import_files(paths)
        if errors or count != expected_count:
            diagnostics = {
                "errors": errors,
                "success_count": count,
                "expected_count": expected_count,
            }
            raise ApplicationError(
                message=(
                    "Failed to apply interpretation without changing the active "
                    f"dataset: loaded {count}/{expected_count} file(s)"
                    + (f"; errors: {errors}" if errors else ".")
                ),
                error_type=ErrorType.RUNTIME,
                recoverable=True,
                diagnostics=diagnostics,
            )
        return count, errors

    @staticmethod
    def _label_apply_blocks_interpretation(
        candidate: InterpretationCandidate,
        label_apply: dict[str, Any],
    ) -> bool:
        if not candidate.label_carrier_plan:
            return False
        if bool(candidate.choices.get("skip_labels")):
            return False
        return str(label_apply.get("status") or "") != "applied"

    @classmethod
    def _ensure_label_apply_succeeded(
        cls,
        candidate: InterpretationCandidate,
        label_apply: dict[str, Any],
    ) -> None:
        if not cls._label_apply_blocks_interpretation(candidate, label_apply):
            return
        raise ApplicationError(
            message=(
                "Failed to apply interpretation without changing the active "
                "dataset: "
                + str(label_apply.get("reason") or "label application failed")
            ),
            error_type=ErrorType.VALIDATION,
            recoverable=True,
            diagnostics={"label_apply": dict(label_apply)},
        )

    def _has_active_raw_data(self) -> bool:
        return bool(list(self.dataset.get_loaded_data_list() or []))

    def _loaded_filepaths(self) -> list[str]:
        return [
            self._data_filepath(data)
            for data in list(self.dataset.get_loaded_data_list() or [])
        ]

    def _snapshot_raw_state(self) -> PipelineStateSnapshot | dict[str, Any]:
        """Capture active raw state so failed interpretation apply can roll back."""
        if self._pipeline_transaction is not None:
            return self._pipeline_transaction.capture()
        return {
            "kind": "generic",
            "loaded": list(getattr(self.dataset, "loaded", [])),
            "imported_paths": list(getattr(self.dataset, "imported_paths", [])),
        }

    def _restore_raw_state(
        self,
        snapshot: PipelineStateSnapshot | dict[str, Any],
    ) -> None:
        """Restore raw state captured before a failed interpretation apply."""
        if isinstance(snapshot, PipelineStateSnapshot):
            if self._pipeline_transaction is None:
                raise RuntimeError("Pipeline transaction is unavailable for restore.")
            self._pipeline_transaction.restore(snapshot)
        elif snapshot.get("kind") == "generic":
            if hasattr(self.dataset, "loaded"):
                self.dataset.loaded = list(snapshot["loaded"])
            if hasattr(self.dataset, "imported_paths"):
                self.dataset.imported_paths = list(snapshot["imported_paths"])
        notify = getattr(self.dataset, "notify", None)
        if callable(notify):
            try:
                notify("data_changed")
            except Exception:
                logger.warning(
                    "Failed to notify observers after restoring EEG data.",
                    exc_info=True,
                )

    @staticmethod
    def _build_applied_interpretation(
        *,
        interpretation_id: str,
        candidate: InterpretationCandidate,
        decision: ValidationDecision,
        loaded_files: list[str],
    ) -> AppliedInterpretation:
        confirmations = (
            list(decision.required_confirmations)
            if decision.decision == InterpretationDecision.NEEDS_CONFIRMATION.value
            else []
        )
        return AppliedInterpretation(
            interpretation_id=interpretation_id,
            candidate_id=candidate.candidate_id,
            source_path=candidate.source_path,
            source_kind=candidate.source_kind,
            loaded_files=list(loaded_files),
            label_sources=list(candidate.label_sources),
            label_carriers=list(candidate.label_carriers),
            bids=dict(candidate.bids),
            label_carrier_plan=[dict(item) for item in candidate.label_carrier_plan],
            metadata=list(candidate.metadata),
            format_capabilities=[dict(item) for item in candidate.format_capabilities],
            skip_labels=bool(candidate.choices.get("skip_labels")),
            label_carrier=str(candidate.choices.get("label_carrier") or ""),
            excluded_label_carriers=[
                str(item)
                for item in candidate.choices.get("excluded_label_carriers", [])
                if str(item).strip()
            ],
            validation_decision=decision.decision,
            confirmations=confirmations,
            event_roles=dict(candidate.event_roles),
            class_map=dict(candidate.class_map),
            internal_event_selection=dict(candidate.internal_event_selection),
            run_event_mappings={
                str(key): dict(value)
                for key, value in candidate.run_event_mappings.items()
            },
            recipe_trace=[
                *candidate.recipe_trace,
                f"validation:{decision.decision}",
                f"applied:{interpretation_id}",
            ],
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
            label_sources=recipe.label_sources,
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
