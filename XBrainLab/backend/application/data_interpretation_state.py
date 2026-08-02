"""Session state boundary for Data Interpretation commands."""

from __future__ import annotations

import logging
import os
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

from XBrainLab.backend.supervised_readiness import (
    has_minimum_usable_classes,
    insufficient_usable_classes_message,
    usable_class_labels,
)

from .commands import LabelImportPlan
from .data_interpretation import (
    AppliedInterpretation,
    ImportRecipe,
    InterpretationCandidate,
    InterpretationDecision,
    InterpretationPreview,
    ScanResult,
    ValidationDecision,
    build_interpretation_preview,
    validate_interpretation_candidate,
)
from .data_interpretation_content_identity import build_review_content_identity
from .data_interpretation_event_values import (
    build_event_catalog,
    class_targets_from_event_catalog,
    derive_class_views,
    unresolved_values_for_plan,
)
from .data_interpretation_placement import (
    annotate_label_carrier_placements,
    placement_blocked_reasons,
    placement_confirmation_items,
)
from .epoch_handoff_blockers import (
    EpochHandoffBlocker,
    EpochHandoffBlockerCode,
    serialize_epoch_handoff_blockers,
)
from .errors import PreconditionError
from .state import InterpretationStateSnapshot

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InterpretationApplyCheckpoint:
    """Interpretation records that must roll back with an apply failure."""

    applied_interpretations: dict[str, AppliedInterpretation]
    recipes: dict[str, ImportRecipe]
    latest_interpretation_id: str | None
    latest_recipe_id: str | None
    latest_recipe_path: str | None


@dataclass(frozen=True)
class InterpretationLabelImportCheckpoint:
    """Interpretation records changed by a post-load label import."""

    candidates: dict[str, InterpretationCandidate]
    previews: dict[str, InterpretationPreview]
    validation_decisions: dict[str, ValidationDecision]
    applied_interpretations: dict[str, AppliedInterpretation]
    recipes: dict[str, ImportRecipe]


class DataInterpretationSessionState:
    """Own Data Interpretation lifecycle objects, IDs, and snapshots."""

    def __init__(self, *, data_filepath: Callable[[Any], str]) -> None:
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

    def next_id(self, prefix: str) -> str:
        """Return the next lifecycle identifier for a Data Interpretation object."""
        self._interpretation_counter += 1
        return f"{prefix}-{self._interpretation_counter}"

    def record_scan(self, scan: ScanResult) -> None:
        """Store a scan result and make it the latest review source."""
        self._scan_results[scan.scan_id] = scan
        self._latest_scan_id = scan.scan_id
        self._latest_candidate_id = None
        self._latest_preview_id = None

    def record_preview(
        self,
        candidate: InterpretationCandidate,
        preview: InterpretationPreview,
    ) -> None:
        """Store a candidate/preview pair and make it the latest review state."""
        self._candidates[candidate.candidate_id] = candidate
        self._previews[preview.preview_id] = preview
        self._latest_candidate_id = candidate.candidate_id
        self._latest_preview_id = preview.preview_id

    def record_validation(
        self,
        candidate_id: str,
        decision: ValidationDecision,
    ) -> None:
        """Store a validation decision for a candidate."""
        self._validation_decisions[candidate_id] = decision

    def record_applied(self, applied: AppliedInterpretation) -> None:
        """Store an applied interpretation as downstream workflow truth."""
        self._applied_interpretations[applied.interpretation_id] = applied
        self._latest_interpretation_id = applied.interpretation_id

    def discard_applied(self, interpretation_id: str) -> None:
        """Remove an applied interpretation that failed during post-load apply."""
        self._applied_interpretations.pop(interpretation_id, None)
        if self._latest_interpretation_id == interpretation_id:
            self._latest_interpretation_id = next(
                reversed(self._applied_interpretations),
                None,
            )

    def checkpoint_apply_state(self) -> InterpretationApplyCheckpoint:
        """Capture interpretation records changed by the apply transaction."""
        return InterpretationApplyCheckpoint(
            applied_interpretations=dict(self._applied_interpretations),
            recipes=dict(self._recipes),
            latest_interpretation_id=self._latest_interpretation_id,
            latest_recipe_id=self._latest_recipe_id,
            latest_recipe_path=self._latest_recipe_path,
        )

    def restore_apply_state(self, checkpoint: InterpretationApplyCheckpoint) -> None:
        """Restore interpretation records after an apply transaction fails."""
        self._applied_interpretations = dict(checkpoint.applied_interpretations)
        self._recipes = dict(checkpoint.recipes)
        self._latest_interpretation_id = checkpoint.latest_interpretation_id
        self._latest_recipe_id = checkpoint.latest_recipe_id
        self._latest_recipe_path = checkpoint.latest_recipe_path

    def record_recipe(
        self,
        recipe: ImportRecipe,
        *,
        recipe_path: str | None,
    ) -> None:
        """Store a saved/reloaded recipe and optional artifact path."""
        self._recipes[recipe.recipe_id] = recipe
        self._latest_recipe_id = recipe.recipe_id
        if recipe_path:
            self._latest_recipe_path = recipe_path

    def record_recipe_reload(
        self,
        *,
        recipe: ImportRecipe,
        scan: ScanResult,
        candidate: InterpretationCandidate,
        preview: InterpretationPreview,
        decision: ValidationDecision,
        recipe_path: str,
    ) -> None:
        """Store lifecycle objects produced by reloading a recipe."""
        self._scan_results[scan.scan_id] = scan
        self._candidates[candidate.candidate_id] = candidate
        self._previews[preview.preview_id] = preview
        self._validation_decisions[candidate.candidate_id] = decision
        self._recipes[recipe.recipe_id] = recipe
        self._latest_scan_id = scan.scan_id
        self._latest_candidate_id = candidate.candidate_id
        self._latest_preview_id = preview.preview_id
        self._latest_recipe_id = recipe.recipe_id
        self._latest_recipe_path = recipe_path

    def resolve_scan(self, scan_id: str | None) -> ScanResult:
        """Return a requested or latest scan result."""
        target_id = scan_id or self._latest_scan_id
        if not target_id or target_id not in self._scan_results:
            raise PreconditionError(
                "Scan a data source before previewing interpretation.",
            )
        return self._scan_results[target_id]

    def resolve_candidate(
        self,
        candidate_id: str | None,
    ) -> InterpretationCandidate:
        """Return a requested or latest interpretation candidate."""
        target_id = candidate_id or self._latest_candidate_id
        if not target_id or target_id not in self._candidates:
            raise PreconditionError("Preview an interpretation candidate first.")
        return self._candidates[target_id]

    def resolve_validation_decision(
        self,
        candidate_id: str,
    ) -> ValidationDecision | None:
        """Return the validation decision recorded for a candidate."""
        return self._validation_decisions.get(candidate_id)

    def resolve_applied_interpretation(self) -> AppliedInterpretation:
        """Return the latest applied interpretation."""
        target_id = self._latest_interpretation_id
        if not target_id or target_id not in self._applied_interpretations:
            raise PreconditionError("Apply an interpretation before saving a recipe.")
        return self._applied_interpretations[target_id]

    def resolve_recipe(self, recipe_id: str | None) -> ImportRecipe:
        """Return a requested or latest import recipe."""
        target_id = recipe_id or self._latest_recipe_id
        if not target_id or target_id not in self._recipes:
            raise PreconditionError("Save or reload an interpretation recipe first.")
        return self._recipes[target_id]

    def current_review(self) -> dict[str, Any]:
        """Return a detached payload for reopening the exact pending review."""
        scan = self._latest_scan()
        candidate = self._latest_candidate()
        preview = self._latest_preview()
        if scan is None or candidate is None or preview is None:
            raise PreconditionError("No Data Import review is ready to open.")
        decision = self._validation_decisions.get(candidate.candidate_id)
        if decision is None:
            raise PreconditionError(
                "Validate the Data Import review before opening it."
            )

        candidate_payload = candidate.to_dict()
        choices = candidate_payload.get("choices", {})
        return {
            "source_path": scan.source_path,
            "source_hint": scan.source_hint,
            "label_sources": list(scan.label_sources),
            "choices": dict(choices) if isinstance(choices, dict) else {},
            "scan_result": scan.to_dict(),
            "candidate": candidate_payload,
            "preview": preview.to_dict(),
            "validation_decision": decision.to_dict(),
        }

    def snapshot(self) -> InterpretationStateSnapshot:
        """Return the current Data Interpretation state snapshot."""
        scan = self._latest_scan()
        candidate = self._latest_candidate()
        preview = self._latest_preview()
        decision = (
            self._validation_decisions.get(self._latest_candidate_id)
            if self._latest_candidate_id
            else None
        )
        applied = self._latest_applied()
        applied_review = self._applied_for_current_review(
            applied=applied,
            scan=scan,
            candidate=candidate,
            preview=preview,
        )
        candidate_review = None if applied_review is not None else candidate
        preview_review = None if applied_review is not None else preview
        source_path, source_kind = self._source_identity(scan, candidate)
        warnings = self._warnings(scan, preview)
        action_items = self._action_items(preview, decision)
        label_carrier_plan = self._label_carrier_plan(
            candidate_review,
            preview_review,
            applied_review,
        )
        format_capabilities = self._format_capabilities(
            candidate_review,
            preview_review,
            scan,
            applied_review,
        )
        event_roles = self._event_roles(
            candidate_review,
            preview_review,
            applied_review,
        )
        class_map = self._class_map(candidate_review, preview_review, applied_review)
        run_event_mappings = self._run_event_mappings(candidate_review, applied_review)
        # Epoching operates on the data already loaded into the active pipeline.
        # A newly opened scan/recipe review is pending state and must not replace
        # the applied interpretation until the user explicitly applies it.
        epoch_handoff = self._epoch_handoff(candidate_review, applied)
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
            label_sources=list(
                applied_review.label_sources
                if applied_review is not None
                else candidate.label_sources
                if candidate is not None
                else scan.label_sources
                if scan is not None
                else applied.label_sources
                if applied is not None
                else []
            ),
            validation_decision=decision.decision if decision else None,
            pending_confirmation=(
                decision is not None
                and decision.decision == InterpretationDecision.NEEDS_CONFIRMATION.value
                and applied_review is None
            ),
            blocked_reasons=list(decision.blocked_reasons if decision else []),
            warnings=warnings,
            action_items=action_items,
            summary=preview.summary if preview else None,
            metadata_preview=list(preview.metadata_preview if preview else []),
            label_carriers=list(
                applied_review.label_carriers
                if applied_review is not None
                else candidate.label_carriers
                if candidate is not None
                else scan.label_carriers
                if scan is not None
                else applied.label_carriers
                if applied is not None
                else []
            ),
            bids=dict(
                applied_review.bids
                if applied_review is not None
                else candidate.bids
                if candidate is not None
                else preview.bids
                if preview is not None
                else scan.bids
                if scan is not None
                else applied.bids
                if applied is not None
                else {}
            ),
            label_carrier_plan=[dict(item) for item in label_carrier_plan],
            format_capabilities=[dict(item) for item in format_capabilities],
            event_roles=dict(event_roles),
            class_map=dict(class_map),
            run_event_mappings=run_event_mappings,
            epoch_handoff=epoch_handoff,
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

    def invalidate_for_legacy_raw_mutation(self) -> bool:
        """Drop interpretation truth that no longer describes the active raw data."""
        had_lifecycle_state = any(
            (
                self._scan_results,
                self._candidates,
                self._previews,
                self._validation_decisions,
                self._applied_interpretations,
                self._recipes,
                self._latest_scan_id,
                self._latest_candidate_id,
                self._latest_preview_id,
                self._latest_interpretation_id,
                self._latest_recipe_id,
                self._latest_recipe_path,
            )
        )
        self.clear()
        return had_lifecycle_state

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
        if success_count <= 0 or success_count != len(target_files):
            return None
        if not self._latest_interpretation_id:
            return None
        applied = self._applied_interpretations.get(self._latest_interpretation_id)
        if applied is None:
            return None

        checkpoint = self._checkpoint_label_import_state()
        try:
            return self._record_label_import_transaction(
                plan=plan,
                mode=mode,
                target_files=target_files,
                file_mapping=file_mapping,
                selected_event_names=selected_event_names,
                success_count=success_count,
                applied=applied,
            )
        except Exception:
            self._restore_label_import_state(checkpoint)
            raise

    def _record_label_import_transaction(
        self,
        *,
        plan: LabelImportPlan,
        mode: str,
        target_files: list[Any],
        file_mapping: dict[str, str],
        selected_event_names: set[str] | None,
        success_count: int,
        applied: AppliedInterpretation,
    ) -> dict[str, Any]:
        """Stage every interpretation projection before committing any of them."""
        label_carriers = sorted(
            {
                self._label_path_key(path)
                for path in (file_mapping.values() or plan.label_paths)
            }
        )
        label_configs = self._label_configs_for_recipe(plan, label_carriers)
        class_map = self._label_mapping_for_recipe(plan.mapping)
        imported_carrier_plan = self._label_import_carrier_plan(
            label_carriers=label_carriers,
            label_configs=label_configs,
            file_mapping=file_mapping,
            class_map=class_map,
            mode=mode,
            selected_event_names=selected_event_names,
            target_files=target_files,
        )
        record = {
            "mode": mode,
            "label_carriers": label_carriers,
            "label_configs": label_configs,
            "target_files": [self._data_filepath(item) for item in target_files],
            "file_mapping": {
                str(key): str(value) for key, value in file_mapping.items()
            },
            "selected_event_names": sorted(selected_event_names or []),
            "class_map": class_map,
            "success_count": int(success_count),
        }
        label_import_trace = f"label_import:{mode}:{success_count}"
        candidate = self._candidates.get(applied.candidate_id)
        scan = (
            self._scan_results.get(candidate.scan_id) if candidate is not None else None
        )
        if candidate is not None:
            imported_carrier_plan = self._bind_inferred_target_events(
                imported_carrier_plan,
                candidate.internal_event_preview,
            )
        replace_skipped_label_truth = bool(applied.skip_labels)
        superseded_carriers = (
            sorted(
                {
                    self._label_path_key(path)
                    for path in scan.label_carriers
                    if self._label_path_key(path) not in set(label_carriers)
                }
            )
            if replace_skipped_label_truth and scan is not None
            else []
        )
        updated_carrier_plan = (
            imported_carrier_plan
            if replace_skipped_label_truth
            else self._merge_label_carrier_plans(
                applied.label_carrier_plan,
                imported_carrier_plan,
            )
        )
        if candidate is not None:
            updated_carrier_plan = annotate_label_carrier_placements(
                updated_carrier_plan,
                candidate.internal_event_preview,
            )
        updated_event_roles = self._post_load_event_roles(applied, candidate)
        updated_class_map = class_map or dict(applied.class_map)
        updated_draft = replace(
            applied,
            skip_labels=False,
            label_sources=(
                label_carriers
                if replace_skipped_label_truth
                else sorted({*applied.label_sources, *label_carriers})
            ),
            label_carriers=(
                label_carriers
                if replace_skipped_label_truth
                else sorted({*applied.label_carriers, *label_carriers})
            ),
            label_carrier_plan=updated_carrier_plan,
            label_carrier="external_files",
            excluded_label_carriers=sorted(
                {
                    *applied.excluded_label_carriers,
                    *superseded_carriers,
                }
                - set(label_carriers)
            ),
            event_roles=updated_event_roles,
            class_map=updated_class_map,
            label_imports=[*applied.label_imports, record],
            recipe_trace=[*applied.recipe_trace, label_import_trace],
        )
        content_identity = self._post_load_content_identity(
            candidate=candidate,
            applied=updated_draft,
        )
        placement_confirmations = placement_confirmation_items(updated_carrier_plan)
        placement_blockers = placement_blocked_reasons(updated_carrier_plan)
        updated_candidate = (
            replace(
                candidate,
                label_sources=list(updated_draft.label_sources),
                label_carriers=list(updated_draft.label_carriers),
                label_carrier_plan=[
                    dict(item) for item in updated_draft.label_carrier_plan
                ],
                event_roles=dict(updated_draft.event_roles),
                class_map=dict(updated_draft.class_map),
                class_map_source="label_import",
                confirmation_items=placement_confirmations,
                blocked_reasons=placement_blockers,
                choices=self._post_load_label_choices(
                    candidate.choices,
                    applied=updated_draft,
                ),
                content_identity=content_identity,
                recipe_trace=[*candidate.recipe_trace, label_import_trace],
            )
            if candidate is not None
            else None
        )
        updated_decision = (
            validate_interpretation_candidate(updated_candidate)
            if updated_candidate is not None
            else None
        )
        updated = replace(
            updated_draft,
            validation_decision=(
                updated_decision.decision
                if updated_decision is not None
                else updated_draft.validation_decision
            ),
            confirmations=list(applied.confirmations),
        )
        preview = (
            self._preview_for_candidate(updated_candidate.candidate_id)
            if updated_candidate is not None
            else None
        )
        recipe = (
            self._recipes.get(self._latest_recipe_id)
            if self._latest_recipe_id
            else None
        )
        updated_recipe = (
            replace(
                recipe,
                skip_labels=False,
                label_sources=list(updated.label_sources),
                label_carriers=list(updated.label_carriers),
                label_carrier_plan=[dict(item) for item in updated.label_carrier_plan],
                label_carrier=updated.label_carrier,
                excluded_label_carriers=list(updated.excluded_label_carriers),
                event_roles=dict(updated.event_roles),
                class_map=dict(updated.class_map),
                validation_decision=updated.validation_decision,
                confirmations=list(updated.confirmations),
                label_imports=[*recipe.label_imports, record],
                content_identity=content_identity or dict(recipe.content_identity),
                recipe_trace=[*recipe.recipe_trace, label_import_trace],
            )
            if recipe is not None
            and recipe.interpretation_id == updated.interpretation_id
            else None
        )
        updated_preview = (
            build_interpretation_preview(
                preview_id=preview.preview_id,
                candidate=updated_candidate,
                scan=scan,
                recipe=updated_recipe or recipe,
                resource_preflight=preview.resource_preflight,
            )
            if preview is not None and updated_candidate is not None
            else None
        )

        if updated_candidate is not None:
            self._candidates[updated_candidate.candidate_id] = updated_candidate
        if updated_preview is not None:
            self._previews[updated_preview.preview_id] = updated_preview
        if updated_decision is not None:
            self._validation_decisions[updated_decision.candidate_id] = updated_decision
        self._applied_interpretations[updated.interpretation_id] = updated
        if updated_recipe is not None and self._latest_recipe_id is not None:
            self._recipes[self._latest_recipe_id] = updated_recipe
        return record

    def _checkpoint_label_import_state(
        self,
    ) -> InterpretationLabelImportCheckpoint:
        return InterpretationLabelImportCheckpoint(
            candidates=dict(self._candidates),
            previews=dict(self._previews),
            validation_decisions=dict(self._validation_decisions),
            applied_interpretations=dict(self._applied_interpretations),
            recipes=dict(self._recipes),
        )

    def _restore_label_import_state(
        self,
        checkpoint: InterpretationLabelImportCheckpoint,
    ) -> None:
        self._candidates = dict(checkpoint.candidates)
        self._previews = dict(checkpoint.previews)
        self._validation_decisions = dict(checkpoint.validation_decisions)
        self._applied_interpretations = dict(checkpoint.applied_interpretations)
        self._recipes = dict(checkpoint.recipes)

    def _preview_for_candidate(
        self,
        candidate_id: str,
    ) -> InterpretationPreview | None:
        for preview in reversed(list(self._previews.values())):
            if preview.candidate_id == candidate_id:
                return preview
        return None

    def _latest_scan(self) -> ScanResult | None:
        if not self._latest_scan_id:
            return None
        return self._scan_results.get(self._latest_scan_id)

    def _latest_candidate(self) -> InterpretationCandidate | None:
        if not self._latest_candidate_id:
            return None
        return self._candidates.get(self._latest_candidate_id)

    def _latest_preview(self) -> InterpretationPreview | None:
        if not self._latest_preview_id:
            return None
        return self._previews.get(self._latest_preview_id)

    def _latest_applied(self) -> AppliedInterpretation | None:
        if not self._latest_interpretation_id:
            return None
        return self._applied_interpretations.get(self._latest_interpretation_id)

    @staticmethod
    def _source_identity(
        scan: ScanResult | None,
        candidate: InterpretationCandidate | None,
    ) -> tuple[str | None, str | None]:
        if candidate is not None:
            return candidate.source_path, candidate.source_kind
        if scan is not None:
            return scan.source_path, scan.source_kind
        return None, None

    @staticmethod
    def _applied_for_current_review(
        *,
        applied: AppliedInterpretation | None,
        scan: ScanResult | None,
        candidate: InterpretationCandidate | None,
        preview: InterpretationPreview | None,
    ) -> AppliedInterpretation | None:
        if applied is None:
            return None
        if candidate is not None:
            return applied if candidate.candidate_id == applied.candidate_id else None
        if preview is not None:
            return applied if preview.candidate_id == applied.candidate_id else None
        if scan is not None:
            return None
        return applied

    @staticmethod
    def _warnings(
        scan: ScanResult | None,
        preview: InterpretationPreview | None,
    ) -> list[str]:
        if preview is not None:
            return list(preview.warnings)
        if scan is not None:
            return list(scan.warnings)
        return []

    @staticmethod
    def _action_items(
        preview: InterpretationPreview | None,
        decision: ValidationDecision | None,
    ) -> list[dict[str, str]]:
        if decision is not None and decision.action_items:
            return [dict(item) for item in decision.action_items]
        if preview is not None:
            return [dict(item) for item in preview.action_items]
        return []

    @staticmethod
    def _label_carrier_plan(
        candidate: InterpretationCandidate | None,
        preview: InterpretationPreview | None,
        applied: AppliedInterpretation | None,
    ) -> list[dict[str, Any]]:
        if candidate is not None:
            return list(candidate.label_carrier_plan)
        if preview is not None:
            return list(preview.label_carrier_preview)
        if applied is not None:
            return list(applied.label_carrier_plan)
        return []

    @staticmethod
    def _format_capabilities(
        candidate: InterpretationCandidate | None,
        preview: InterpretationPreview | None,
        scan: ScanResult | None,
        applied: AppliedInterpretation | None,
    ) -> list[dict[str, Any]]:
        if candidate is not None:
            return list(candidate.format_capabilities)
        if preview is not None:
            return list(preview.format_capabilities)
        if scan is not None:
            return list(scan.format_capabilities)
        if applied is not None:
            return list(applied.format_capabilities)
        return []

    @staticmethod
    def _event_roles(
        candidate: InterpretationCandidate | None,
        preview: InterpretationPreview | None,
        applied: AppliedInterpretation | None,
    ) -> dict[str, str]:
        if candidate is not None:
            return dict(candidate.event_roles)
        if preview is not None:
            return dict(preview.event_roles)
        if applied is not None:
            return dict(applied.event_roles)
        return {}

    @staticmethod
    def _class_map(
        candidate: InterpretationCandidate | None,
        preview: InterpretationPreview | None,
        applied: AppliedInterpretation | None,
    ) -> dict[str, str]:
        if candidate is not None:
            return dict(candidate.class_map)
        if preview is not None:
            return dict(preview.class_map)
        if applied is not None:
            return dict(applied.class_map)
        return {}

    @staticmethod
    def _run_event_mappings(
        candidate: InterpretationCandidate | None,
        applied: AppliedInterpretation | None,
    ) -> dict[str, dict[str, str]]:
        source = candidate if candidate is not None else applied
        if source is None:
            return {}
        return {
            str(key): dict(value)
            for key, value in getattr(source, "run_event_mappings", {}).items()
        }

    @staticmethod
    def _epoch_handoff(
        candidate: InterpretationCandidate | None,
        applied: AppliedInterpretation | None,
    ) -> dict[str, Any]:
        source = applied if applied is not None else candidate
        if source is None:
            return {}
        label_imports = [
            dict(item) for item in getattr(applied, "label_imports", []) or []
        ]
        carrier_plan = [
            dict(item) for item in getattr(source, "label_carrier_plan", []) or []
        ]
        has_value_contract = any(
            isinstance(item.get("value_decisions"), dict) for item in carrier_plan
        )
        event_catalog = build_event_catalog(carrier_plan) if has_value_contract else []
        class_targets = (
            class_targets_from_event_catalog(event_catalog)
            if has_value_contract
            else []
        )
        placement_modes = sorted(
            {
                str(item.get("placement_method") or "").strip()
                for item in carrier_plan
                if str(item.get("placement_method") or "").strip()
            }
        )
        internal_event_selection = dict(
            getattr(source, "internal_event_selection", {}) or {}
        )
        internal_event_codes = DataInterpretationSessionState._sorted_event_names(
            {
                str(name)
                for name in internal_event_selection.get("label_event_codes", [])
                if str(name).strip()
            }
        )
        selected_event_names = DataInterpretationSessionState._sorted_event_names(
            {
                str(name)
                for item in label_imports
                for name in item.get("selected_event_names", [])
                if str(name).strip()
            }
            | set(internal_event_codes)
        )
        global_class_map = {
            str(key): str(value)
            for key, value in getattr(source, "class_map", {}).items()
        }
        if has_value_contract:
            global_class_map, run_class_maps = derive_class_views(carrier_plan)
        else:
            run_class_maps = DataInterpretationSessionState._run_class_maps(
                carrier_plan
            )
        run_class_signatures = {
            tuple(sorted(mapping.items())) for mapping in run_class_maps.values()
        }
        run_dependent_carrier_mapping = len(run_class_signatures) > 1
        source_event_roles = dict(getattr(source, "event_roles", {}) or {})
        run_dependent_internal_mapping = "run_dependent_events" in source_event_roles
        run_dependent_mapping = (
            run_dependent_carrier_mapping or run_dependent_internal_mapping
        )
        class_map = {} if run_dependent_mapping else global_class_map
        event_label_aliases = (
            {}
            if run_dependent_internal_mapping
            else {
                event_code: str(class_map.get(event_code) or event_code).strip()
                for event_code in internal_event_codes
                if str(class_map.get(event_code) or event_code).strip()
            }
        )
        has_label_imports = bool(label_imports)
        has_internal_selection = (
            DataInterpretationSessionState._has_internal_label_selection(
                internal_event_selection,
            )
        )
        run_event_mappings = {
            str(key): dict(value)
            for key, value in getattr(source, "run_event_mappings", {}).items()
        }
        label_source = DataInterpretationSessionState._epoch_label_source(source)
        default_epoch_events = selected_event_names
        if has_value_contract:
            default_epoch_events = DataInterpretationSessionState._sorted_event_names(
                {
                    str(target.get("event") or "")
                    for target in class_targets
                    if str(target.get("event") or "").strip()
                }
            )
        elif applied is not None and run_class_maps and has_label_imports:
            default_epoch_events = DataInterpretationSessionState._sorted_event_names(
                {
                    str(name)
                    for mapping in run_class_maps.values()
                    for name in mapping.values()
                    if str(name).strip()
                }
            )
        elif applied is not None and class_map and has_label_imports:
            default_epoch_events = DataInterpretationSessionState._class_names_from_map(
                class_map
            )
        elif applied is not None and has_internal_selection:
            default_epoch_events = internal_event_codes
        if has_value_contract:
            usable_classes = usable_class_labels(
                (
                    target.get("class_name") or target.get("event"),
                    target.get("count"),
                )
                for target in class_targets
            )
        elif has_internal_selection:
            internal_aliases = {
                str(code): str(global_class_map.get(str(code)) or code).strip()
                for code in internal_event_codes
            }
            internal_event_counts = internal_event_selection.get("label_event_counts")
            usable_internal_codes = set(internal_event_codes)
            if isinstance(internal_event_counts, dict):
                usable_internal_codes = set(
                    usable_class_labels(
                        (code, internal_event_counts.get(code))
                        for code in internal_event_codes
                    )
                )
            mapping_values = {
                str(label).strip()
                for mapping in getattr(source, "run_event_mappings", {}).values()
                if isinstance(mapping, dict)
                for code, label in mapping.items()
                if str(code) in usable_internal_codes and str(label).strip()
            }
            usable_classes = tuple(
                sorted(
                    mapping_values
                    or {
                        label
                        for code, label in internal_aliases.items()
                        if code in usable_internal_codes
                        if str(label).strip()
                    },
                    key=str.casefold,
                )
            )
        else:
            usable_classes = tuple(default_epoch_events)
        supervised_blocker_records = (
            DataInterpretationSessionState._epoch_supervised_blockers(
                applied=applied,
                carrier_plan=carrier_plan,
                label_imports=label_imports,
                internal_event_selection=internal_event_selection,
                has_value_contract=has_value_contract,
                event_catalog=event_catalog,
                class_targets=class_targets,
                usable_classes=usable_classes,
            )
        )
        supervised_blockers, supervised_blocker_codes = (
            serialize_epoch_handoff_blockers(supervised_blocker_records)
        )
        supervised_ready = bool(default_epoch_events) and not supervised_blockers
        epoch_targets = DataInterpretationSessionState._epoch_targets_from_events(
            default_epoch_events,
            label_source=label_source,
            event_label_aliases=event_label_aliases,
        )
        handoff: dict[str, Any] = {
            "ready": bool(applied is not None and not supervised_blockers),
            "supervised_ready": supervised_ready,
            "supervised_blockers": supervised_blockers,
            "supervised_blocker_codes": supervised_blocker_codes,
            "label_source": label_source,
            "source": "applied_interpretation" if applied is not None else "candidate",
            "placement_modes": placement_modes,
            "class_map": class_map,
            "usable_class_labels": list(usable_classes),
            "usable_class_count": len(usable_classes),
            "default_epoch_events": default_epoch_events,
            "epoch_targets": epoch_targets,
            "selected_event_names": selected_event_names,
            "run_event_mappings": run_event_mappings,
            "run_dependent_mapping": run_dependent_mapping,
        }
        if has_value_contract:
            handoff["event_catalog"] = event_catalog
            handoff["class_targets"] = class_targets
        if run_class_maps:
            handoff["run_class_maps"] = run_class_maps
        if event_label_aliases:
            handoff["event_label_aliases"] = event_label_aliases
        bids = getattr(source, "bids", {}) or {}
        if isinstance(bids, dict) and bids:
            handoff["bids"] = dict(bids)
        if internal_event_selection:
            handoff["internal_event_selection"] = internal_event_selection
        if label_imports:
            handoff["label_imports"] = label_imports
        if carrier_plan:
            handoff["label_carrier_plan"] = [
                {
                    key: item.get(key)
                    for key in (
                        "path",
                        "selected_target_file",
                        "selected_label_field",
                        "selected_anchor",
                        "selected_duration_field",
                        "placement_method",
                        "time_model",
                        "value_decisions",
                        "run_class_map",
                    )
                    if item.get(key) not in (None, "")
                }
                for item in carrier_plan
            ]
        return handoff

    @staticmethod
    def _epoch_label_source(source: Any) -> str:
        if str(getattr(source, "source_kind", "") or "") == "bids":
            for item in getattr(source, "label_carrier_plan", []) or []:
                if str(item.get("format") or "") == "BIDS events":
                    return "bids_events"
        if (
            getattr(source, "internal_event_selection", {})
            or str(getattr(source, "label_carrier", "") or "") == "embedded_events"
        ):
            return "internal_events"
        if getattr(source, "label_carrier_plan", []) or getattr(
            source,
            "label_imports",
            [],
        ):
            return "loaded_label_files"
        return "none"

    @staticmethod
    def _epoch_supervised_blockers(
        *,
        applied: AppliedInterpretation | None,
        carrier_plan: list[dict[str, Any]],
        label_imports: list[dict[str, Any]],
        internal_event_selection: dict[str, Any],
        has_value_contract: bool = False,
        event_catalog: list[dict[str, Any]] | None = None,
        class_targets: list[dict[str, Any]] | None = None,
        usable_classes: tuple[str, ...] = (),
    ) -> list[EpochHandoffBlocker]:
        if applied is None:
            return [
                EpochHandoffBlocker(
                    EpochHandoffBlockerCode.IMPORT_NOT_APPLIED,
                    "Apply the reviewed import before creating supervised EEG epochs.",
                )
            ]
        if has_value_contract:
            unresolved = sorted(
                {
                    raw_value
                    for plan in carrier_plan
                    for raw_value in unresolved_values_for_plan(plan)
                }
            )
            if unresolved:
                return [
                    EpochHandoffBlocker(
                        EpochHandoffBlockerCode.UNRESOLVED_EXTERNAL_VALUES,
                        "External event values remain unresolved: "
                        + ", ".join(unresolved)
                        + ".",
                    )
                ]
            if not class_targets:
                return [
                    EpochHandoffBlocker(
                        EpochHandoffBlockerCode.MISSING_REVIEWED_TARGET,
                        "No reviewed class target is available for supervised "
                        "EEG epoch defaults.",
                    )
                ]
            if carrier_plan and not label_imports:
                return [
                    EpochHandoffBlocker(
                        EpochHandoffBlockerCode.LABELS_NOT_APPLIED,
                        "Reviewed labels were not applied to the loaded EEG data.",
                    )
                ]
        else:
            has_internal_selection = (
                DataInterpretationSessionState._has_internal_label_selection(
                    internal_event_selection,
                )
            )
            if not label_imports and not has_internal_selection:
                if carrier_plan:
                    return [
                        EpochHandoffBlocker(
                            EpochHandoffBlockerCode.LABELS_NOT_APPLIED,
                            "Reviewed labels were not applied to the loaded EEG data.",
                        )
                    ]
                return [
                    EpochHandoffBlocker(
                        EpochHandoffBlockerCode.MISSING_CLASS_LABELS,
                        "No class labels are available for supervised EEG "
                        "epoch defaults.",
                    )
                ]
        if not has_minimum_usable_classes(usable_classes):
            return [
                EpochHandoffBlocker(
                    EpochHandoffBlockerCode.INSUFFICIENT_USABLE_CLASSES,
                    insufficient_usable_classes_message(usable_classes),
                )
            ]
        return []

    @staticmethod
    def _has_internal_label_selection(
        internal_event_selection: dict[str, Any],
    ) -> bool:
        return bool(internal_event_selection.get("label_event_codes"))

    @staticmethod
    def _class_names_from_map(class_map: dict[str, str]) -> list[str]:
        result: list[str] = []
        for key in DataInterpretationSessionState._sorted_event_names(set(class_map)):
            value = str(class_map.get(key) or "").strip()
            if value and value not in result:
                result.append(value)
        return result

    @staticmethod
    def _run_class_maps(
        carrier_plan: list[dict[str, Any]],
    ) -> dict[str, dict[str, str]]:
        result: dict[str, dict[str, str]] = {}
        for item in carrier_plan:
            mapping = item.get("run_class_map")
            if not isinstance(mapping, dict) or not mapping:
                continue
            target = str(
                item.get("selected_target_file") or item.get("path") or ""
            ).strip()
            if not target:
                continue
            result[target] = {
                str(code): str(label)
                for code, label in mapping.items()
                if str(code).strip() and str(label).strip()
            }
        return result

    @staticmethod
    def _epoch_targets_from_events(
        events: list[str],
        *,
        label_source: str,
        event_label_aliases: dict[str, str],
    ) -> list[dict[str, str]]:
        targets: list[dict[str, str]] = []
        for event_name in events:
            target = {"event": event_name, "source": label_source}
            alias = str(event_label_aliases.get(event_name) or "").strip()
            if alias and alias != event_name:
                target["label"] = alias
            targets.append(target)
        return targets

    @staticmethod
    def _label_mapping_for_recipe(mapping: Any) -> dict[str, str]:
        if not isinstance(mapping, dict):
            return {}
        return {str(key): str(value) for key, value in mapping.items()}

    @staticmethod
    def _label_configs_for_recipe(
        plan: LabelImportPlan,
        label_carriers: list[str],
    ) -> dict[str, dict[str, Any]]:
        allowed_fields = {
            "label_field",
            "anchor",
            "duration_field",
            "sequence_only",
        }
        result: dict[str, dict[str, Any]] = {}
        raw_configs = plan.label_configs if isinstance(plan.label_configs, dict) else {}
        configs_by_path = {
            DataInterpretationSessionState._label_path_key(path): config
            for path, config in raw_configs.items()
            if isinstance(config, dict)
        }
        for carrier in label_carriers:
            raw_config = configs_by_path.get(
                DataInterpretationSessionState._label_path_key(carrier)
            )
            if not isinstance(raw_config, dict):
                continue
            config = {
                str(key): value
                for key, value in raw_config.items()
                if str(key) in allowed_fields and value not in (None, "")
            }
            if config:
                result[carrier] = config
        return result

    @staticmethod
    def _label_path_key(path: Any) -> str:
        return os.path.normcase(str(Path(str(path)).expanduser().resolve()))

    @staticmethod
    def _label_import_carrier_plan(
        *,
        label_carriers: list[str],
        label_configs: dict[str, dict[str, Any]],
        file_mapping: dict[str, str],
        class_map: dict[str, str],
        mode: str,
        selected_event_names: set[str] | None,
        target_files: list[Any],
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        class_counts_by_target = DataInterpretationSessionState._class_counts_by_target(
            target_files
        )
        value_decisions = {
            raw_value: {
                "role": "stimulus",
                "keep_event": True,
                "use_as_class": True,
                "class_name": class_name,
                "suggested_name": class_name,
                "decision": "resolved",
                "decision_source": "external_label_mapping",
                "provenance": "label_import",
            }
            for raw_value, class_name in class_map.items()
        }
        normalized_mode = str(mode or "").strip().lower()
        target_event_codes = sorted(
            str(value).strip()
            for value in (selected_event_names or set())
            if str(value).strip()
        )
        for carrier in label_carriers:
            config = label_configs.get(carrier, {})
            targets = sorted(
                str(target)
                for target, mapped_carrier in file_mapping.items()
                if str(mapped_carrier) == carrier
            )
            carrier_class_counts = DataInterpretationSessionState._shared_class_counts(
                targets=targets,
                class_counts_by_target=class_counts_by_target,
            )
            carrier_value_decisions = {
                raw_value: {
                    **decision,
                    **(
                        {"count": carrier_class_counts[class_name]}
                        if class_name in carrier_class_counts
                        else {}
                    ),
                }
                for raw_value, decision in value_decisions.items()
                for class_name in [str(decision.get("class_name") or "")]
            }
            label_row_count = (
                sum(carrier_class_counts.values()) if carrier_class_counts else None
            )
            applied_event_counts_by_target = {
                target: sum(
                    class_counts_by_target[
                        DataInterpretationSessionState._label_path_key(target)
                    ].values()
                )
                for target in targets
                if DataInterpretationSessionState._label_path_key(target)
                in class_counts_by_target
            }
            selected_anchor = str(config.get("anchor") or "")
            if normalized_mode != "timestamp" and not selected_anchor:
                selected_anchor = (
                    target_event_codes[0] if target_event_codes else "trial order"
                )
            item: dict[str, Any] = {
                "path": carrier,
                "format": DataInterpretationSessionState._label_carrier_format(carrier),
                "selected_target_file": targets[0] if len(targets) == 1 else "",
                "selected_target_files": targets,
                "selected_target_event_codes": target_event_codes,
                "selected_label_field": str(config.get("label_field") or ""),
                "selected_anchor": selected_anchor,
                "selected_duration_field": str(config.get("duration_field") or ""),
                "label_row_count": label_row_count,
                "applied_event_counts_by_target": applied_event_counts_by_target,
                "placement_method": (
                    "time_field" if normalized_mode == "timestamp" else "eeg_event"
                ),
                "time_model": (
                    "seconds" if normalized_mode == "timestamp" else "trial_order"
                ),
                "granularity": "trial",
                "role": "external labels",
                "value_decisions": carrier_value_decisions,
                "run_class_map": dict(class_map),
            }
            result.append(item)
        return result

    @staticmethod
    def _bind_inferred_target_events(
        carrier_plan: list[dict[str, Any]],
        internal_event_preview: dict[str, Any],
    ) -> list[dict[str, Any]]:
        rows = [
            dict(item)
            for item in internal_event_preview.get("candidate_label_events", [])
            if isinstance(item, Mapping)
            and str(item.get("event_code") or item.get("code") or "").strip()
        ]
        if not rows:
            return [dict(item) for item in carrier_plan]

        event_codes = [
            str(row.get("event_code") or row.get("code") or "").strip() for row in rows
        ]
        result: list[dict[str, Any]] = []
        for plan in carrier_plan:
            item = dict(plan)
            if item.get("selected_target_event_codes"):
                result.append(item)
                continue
            label_rows = item.get("label_row_count")
            targets = [
                str(path)
                for path in item.get("selected_target_files", [])
                if str(path).strip()
            ]
            if not isinstance(label_rows, int) or label_rows <= 0 or not targets:
                result.append(item)
                continue
            target_totals = [
                sum(
                    DataInterpretationSessionState._event_count_for_target(
                        row,
                        target,
                        target_count=len(targets),
                    )
                    for row in rows
                )
                for target in targets
            ]
            if target_totals and all(total == label_rows for total in target_totals):
                item["selected_target_event_codes"] = event_codes
                item["selected_anchor"] = event_codes[0]
            result.append(item)
        return result

    @staticmethod
    def _event_count_for_target(
        row: dict[str, Any],
        target_path: str,
        *,
        target_count: int,
    ) -> int:
        file_counts = row.get("file_counts")
        if isinstance(file_counts, Mapping):
            target_key = DataInterpretationSessionState._label_path_key(target_path)
            normalized_counts = {
                DataInterpretationSessionState._label_path_key(path): count
                for path, count in file_counts.items()
            }
            count = normalized_counts.get(target_key)
            if isinstance(count, int):
                return count
            if target_count == 1:
                basename_matches = [
                    value
                    for path, value in file_counts.items()
                    if Path(str(path)).name == Path(target_path).name
                    and isinstance(value, int)
                ]
                if len(basename_matches) == 1:
                    return basename_matches[0]
            return 0
        event_count = row.get("event_count")
        return (
            int(event_count)
            if target_count == 1 and isinstance(event_count, int)
            else 0
        )

    @staticmethod
    def _post_load_label_choices(
        existing: dict[str, Any],
        *,
        applied: AppliedInterpretation,
    ) -> dict[str, Any]:
        choices = dict(existing)
        choices.pop("class_map", None)
        choices.update(
            {
                "skip_labels": False,
                "label_sources": list(applied.label_sources),
                "label_carrier": "external_files",
                "required_label_carriers": list(applied.label_carriers),
                "excluded_label_carriers": list(applied.excluded_label_carriers),
                "label_carrier_choices": {
                    str(item.get("path") or ""): {
                        "label_field": str(item.get("selected_label_field") or ""),
                        "anchor": str(item.get("selected_anchor") or ""),
                        "duration_field": str(
                            item.get("selected_duration_field") or ""
                        ),
                        "placement_method": str(item.get("placement_method") or ""),
                        "time_model": str(item.get("time_model") or ""),
                        "granularity": str(item.get("granularity") or ""),
                        "target_file": str(item.get("selected_target_file") or ""),
                        "target_files": list(item.get("selected_target_files") or []),
                        "target_event_codes": list(
                            item.get("selected_target_event_codes") or []
                        ),
                        "value_decisions": dict(item.get("value_decisions") or {}),
                    }
                    for item in applied.label_carrier_plan
                    if str(item.get("path") or "").strip()
                },
            }
        )
        return choices

    def _post_load_content_identity(
        self,
        *,
        candidate: InterpretationCandidate | None,
        applied: AppliedInterpretation,
    ) -> dict[str, Any]:
        if candidate is None or not candidate.content_identity:
            return {}
        previous_identity = candidate.content_identity
        previous_files = [
            dict(item)
            for item in previous_identity.get("files", [])
            if isinstance(item, Mapping)
        ]
        admitted_file_identities = {
            str(item.get("path") or ""): {
                "file_bytes": item.get("file_bytes"),
                "sha256": item.get("sha256"),
            }
            for item in previous_files
            if str(item.get("path") or "").strip()
            and str(item.get("role") or "") != "label_carrier"
        }
        parser_dependencies = {
            str(item.get("path") or ""): [
                str(path) for path in item.get("dependencies", []) if str(path).strip()
            ]
            for item in previous_identity.get("parser_dependencies", [])
            if isinstance(item, Mapping)
            and str(item.get("path") or "").strip()
            and isinstance(item.get("dependencies"), list)
        }
        return build_review_content_identity(
            label_carrier_plan=applied.label_carrier_plan,
            selected_eeg_files=candidate.selected_eeg_files,
            eeg_parser_dependencies=parser_dependencies,
            bids_events_json_files=[
                str(item.get("path") or "")
                for item in previous_files
                if item.get("role") == "bids_events_json"
            ],
            bids_channels_files=[
                str(item.get("path") or "")
                for item in previous_files
                if item.get("role") == "bids_channels"
            ],
            admitted_file_identities=admitted_file_identities,
            class_map=applied.class_map,
            event_roles=applied.event_roles,
            run_event_mappings=applied.run_event_mappings,
        )

    @staticmethod
    def _post_load_event_roles(
        applied: AppliedInterpretation,
        candidate: InterpretationCandidate | None,
    ) -> dict[str, str]:
        roles = dict(applied.event_roles)
        roles["label_carrier"] = "external label or event source"
        if candidate is None:
            return roles
        if candidate.bids.get("is_bids"):
            roles.update(
                {
                    "onset": "time anchor",
                    "duration": "event duration",
                    "trial_type": "class label candidate",
                }
            )
            return roles
        extensions = {
            Path(path).suffix.casefold() for path in candidate.selected_eeg_files
        }
        if extensions & {".gdf", ".edf", ".bdf", ".set", ".vhdr"}:
            roles["internal_events"] = "event role candidates"
        return roles

    @staticmethod
    def _class_counts_by_target(
        target_files: list[Any],
    ) -> dict[str, dict[str, int]]:
        result: dict[str, dict[str, int]] = {}
        for target in target_files:
            get_event_list = getattr(target, "get_event_list", None)
            get_filepath = getattr(target, "get_filepath", None)
            if not callable(get_event_list) or not callable(get_filepath):
                continue
            try:
                events, event_id = cast(
                    Callable[
                        [],
                        tuple[Iterable[Sequence[Any]], Mapping[str, int]],
                    ],
                    get_event_list,
                )()
            except Exception:
                logger.debug(
                    "Could not derive post-load class counts for recipe identity.",
                    exc_info=True,
                )
                continue
            if not isinstance(event_id, Mapping):
                continue
            event_counts = Counter(int(row[-1]) for row in events if len(row) >= 1)
            result[DataInterpretationSessionState._label_path_key(get_filepath())] = {
                str(class_name): int(event_counts.get(int(event_code), 0))
                for class_name, event_code in event_id.items()
            }
        return result

    @staticmethod
    def _shared_class_counts(
        *,
        targets: list[str],
        class_counts_by_target: dict[str, dict[str, int]],
    ) -> dict[str, int]:
        observed = [
            class_counts_by_target[
                DataInterpretationSessionState._label_path_key(target)
            ]
            for target in targets
            if DataInterpretationSessionState._label_path_key(target)
            in class_counts_by_target
        ]
        if len(observed) != len(targets) or not observed:
            return {}
        return observed[0] if all(item == observed[0] for item in observed[1:]) else {}

    @staticmethod
    def _label_carrier_format(path: str) -> str:
        carrier = Path(path)
        if carrier.name.endswith("_events.tsv") or carrier.name == "events.tsv":
            return "BIDS events"
        suffix = carrier.suffix.casefold()
        return {
            ".mat": "MAT",
            ".csv": "CSV",
            ".tsv": "TSV",
            ".txt": "TXT",
        }.get(suffix, suffix.lstrip(".").upper() or "Unknown")

    @staticmethod
    def _merge_label_carrier_plans(
        existing: list[dict[str, Any]],
        imported: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result = [dict(item) for item in existing]
        by_path = {
            str(item.get("path") or ""): index
            for index, item in enumerate(result)
            if str(item.get("path") or "")
        }
        for item in imported:
            path = str(item.get("path") or "")
            index = by_path.get(path)
            if index is None:
                by_path[path] = len(result)
                result.append(dict(item))
                continue
            merged = dict(result[index])
            authoritative_fields = {
                "selected_target_file",
                "selected_target_files",
                "selected_target_event_codes",
            }
            reviewed_parser_fields = {
                "selected_label_field",
                "selected_anchor",
                "selected_duration_field",
            }
            for key, value in item.items():
                if key in {"value_decisions", "run_class_map"}:
                    imported_mapping = dict(value) if isinstance(value, dict) else {}
                    raw_reviewed_mapping = merged.get(key)
                    reviewed_mapping = (
                        dict(raw_reviewed_mapping)
                        if isinstance(raw_reviewed_mapping, dict)
                        else {}
                    )
                    merged[key] = {
                        **imported_mapping,
                        **reviewed_mapping,
                    }
                    continue
                if (
                    key == "selected_anchor"
                    and value == "trial order"
                    and merged.get(key) not in (None, "")
                ):
                    continue
                if (
                    key in authoritative_fields
                    or (key in reviewed_parser_fields and value not in (None, ""))
                    or key not in merged
                    or merged[key] in (None, "")
                ):
                    merged[key] = value
            result[index] = merged
        return result

    @staticmethod
    def _sorted_event_names(values: set[str]) -> list[str]:
        def sort_key(value: str) -> tuple[int, int | str]:
            text = str(value).strip()
            return (0, int(text)) if text.isdigit() else (1, text.casefold())

        return sorted(
            {str(item).strip() for item in values if str(item).strip()}, key=sort_key
        )
