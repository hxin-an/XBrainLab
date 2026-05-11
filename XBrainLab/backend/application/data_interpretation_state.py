"""Session state boundary for Data Interpretation commands."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from .commands import LabelImportPlan
from .data_interpretation import (
    AppliedInterpretation,
    ImportRecipe,
    InterpretationCandidate,
    InterpretationDecision,
    InterpretationPreview,
    ScanResult,
    ValidationDecision,
)
from .errors import PreconditionError
from .state import InterpretationStateSnapshot


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
    def _label_mapping_for_recipe(mapping: Any) -> dict[str, str]:
        if not isinstance(mapping, dict):
            return {}
        return {str(key): str(value) for key, value in mapping.items()}
