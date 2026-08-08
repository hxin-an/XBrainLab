"""Data Interpretation command coordinator.

This module owns the Data Interpretation lifecycle state and application logic
that used to live inside ``ApplicationService``. ``ApplicationService`` remains
the command/result envelope and capability gate.
"""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

from XBrainLab.backend.services.dataset_state_service import DatasetInterpretationPort

from .bids_subject_catalog import inspect_bids_subject_catalog
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
    resolve_interpretation_resource_scope,
    scan_source_path,
    validate_interpretation_candidate,
)
from .data_interpretation_apply import DataInterpretationApplyService
from .data_interpretation_bids_resources import BidsEventsJsonReader
from .data_interpretation_candidate import InterpretationResourceScope
from .data_interpretation_content_identity import (
    assert_review_content_unchanged,
    identity_paths,
)
from .data_interpretation_path_identity import normalized_path_identity
from .data_interpretation_placement import placement_blocked_reasons
from .data_interpretation_recipe import (
    IMPORT_RECIPE_MAX_BYTES,
    ImportRecipeTooLargeError,
)
from .data_interpretation_resource_reader import AdmittedResourceReader
from .data_interpretation_resource_receipt import (
    DataInterpretationResourceReceiptAuthority,
)
from .data_interpretation_scan import (
    ScanPreflightScope,
    discover_explicit_file_preflight_scope,
    discover_source_preflight_scope,
)
from .data_interpretation_state import DataInterpretationSessionState
from .errors import ApplicationError, ConfirmationRequiredError, PreconditionError
from .label_resource_admission import (
    AdmittedLabelResourceSession,
    LabelResourceSpec,
    session_from_resource_preflight,
)
from .pipeline_transaction import PipelineStateSnapshot, PipelineStateTransaction
from .resource_guard import (
    RAM_WARNING_RATIO,
    ResourceConfirmationRequiredError,
    ResourcePreflightResult,
    ResourceRiskLevel,
    available_ram_bytes,
    check_import_resource_preflight,
    enforce_resource_preflight,
)
from .resource_receipt import (
    DEFAULT_RESOURCE_RECEIPT_LIMIT,
    DEFAULT_RESOURCE_RECEIPT_TTL_SECONDS,
    ResourceReceiptAuthority,
    ResourceReceiptRecord,
    fingerprint_resource_preflight,
    fingerprint_resource_scope,
)
from .results import ErrorType
from .state import InterpretationStateSnapshot

HandlerResult = str | tuple[str, dict[str, Any]]

IMPORT_PREFLIGHT_RECEIPT_TTL_SECONDS = DEFAULT_RESOURCE_RECEIPT_TTL_SECONDS
IMPORT_PREFLIGHT_RECEIPT_LIMIT = DEFAULT_RESOURCE_RECEIPT_LIMIT


def _deduplicate_resource_paths(paths: list[str]) -> list[str]:
    """Preserve display spelling while collapsing filesystem-equivalent paths."""
    result: list[str] = []
    seen: set[str] = set()
    for path in paths:
        identity = normalized_path_identity(path)
        if not identity or identity in seen:
            continue
        seen.add(identity)
        result.append(path)
    return result


_ImportPreflightReceipt = ResourceReceiptRecord[ResourcePreflightResult]


@dataclass(frozen=True)
class _PreviewResourceAdmission:
    """Authoritative preview preflight plus its bounded sidecar reader."""

    preflight: ResourcePreflightResult
    resource_reader: AdmittedResourceReader
    bids_events_json_reader: BidsEventsJsonReader
    resource_scope: InterpretationResourceScope
    scan_preflight_scope: ScanPreflightScope | None = None
    confirmation_receipt_reused: bool = False
    admission_cache_reused: bool = False
    reusable_content_identities: dict[str, dict[str, Any]] | None = None

    def to_diagnostics(self) -> dict[str, Any]:
        diagnostics = self.preflight.to_diagnostics()
        diagnostics["parser_admission"] = self.resource_reader.diagnostics()
        diagnostics["bids_events_json"] = self.bids_events_json_reader.diagnostics()
        diagnostics["confirmation_receipt_reused"] = self.confirmation_receipt_reused
        diagnostics["admission_cache_reused"] = self.admission_cache_reused
        return diagnostics


class DataInterpretationCommandService:
    """Handle Data Interpretation commands and related recipe state."""

    def __init__(
        self,
        dataset_controller: DatasetInterpretationPort,
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
        self._import_preflight_receipts = ResourceReceiptAuthority[
            ResourcePreflightResult
        ](
            command_name="apply_interpretation",
            ttl_seconds=IMPORT_PREFLIGHT_RECEIPT_TTL_SECONDS,
            max_receipts=IMPORT_PREFLIGHT_RECEIPT_LIMIT,
            clock=lambda: time.monotonic(),
        )
        self._preview_preflight_receipts = DataInterpretationResourceReceiptAuthority(
            command_name="preview_interpretation",
        )
        self._review_preflight_receipts = DataInterpretationResourceReceiptAuthority(
            command_name="review_interpretation",
        )
        self._reload_preflight_receipts = DataInterpretationResourceReceiptAuthority(
            command_name="reload_interpretation_recipe",
        )
        self._safe_preview_admissions: dict[
            tuple[str, str, tuple[str, ...]],
            _PreviewResourceAdmission,
        ] = {}

    def handle_scan_source(self, command: Command) -> HandlerResult:
        """Scan a file, folder, BIDS root, device export, or recipe source."""
        if not isinstance(command, ScanSourceCommand):
            raise TypeError("Invalid command for scan_source")
        if command.catalog_only:
            if str(command.source_hint).strip().casefold() != "bids":
                raise ValueError("Catalog-only discovery requires a BIDS source.")
            catalog = inspect_bids_subject_catalog(command.source_path)
            return (
                f"Found {catalog['subject_count']} BIDS subject(s).",
                {
                    "payload_type": "bids_subject_catalog",
                    "bids_subject_catalog": catalog,
                },
            )
        scan_id = self.state.next_id("scan")
        scope = discover_source_preflight_scope(
            source_path=command.source_path,
            source_hint=command.source_hint,
            label_sources=command.label_sources,
            selected_bids_subjects=command.selected_bids_subjects,
        )
        preflight = check_import_resource_preflight(scope.paths)
        resource_reader = AdmittedResourceReader.from_resource_preflight(
            scope.paths,
            preflight,
        )
        scan = scan_source_path(
            scan_id=scan_id,
            source_path=command.source_path,
            source_hint=command.source_hint,
            label_sources=command.label_sources,
            preflight_scope=scope,
            materialize_metadata=False,
            resource_reader=resource_reader,
        )
        preview_scope = resolve_interpretation_resource_scope(scan, {})
        preview_scope_is_admitted = all(
            resource_reader.admits(path) for path in preview_scope.paths
        )
        if (
            preflight.risk_level is ResourceRiskLevel.SAFE
            and bool(scan.bids.get("is_bids"))
            and preview_scope_is_admitted
        ):
            preview_admission = _PreviewResourceAdmission(
                preflight=preflight,
                resource_reader=resource_reader,
                bids_events_json_reader=BidsEventsJsonReader.from_resource_preflight(
                    preview_scope.bids_events_json_files,
                    preflight,
                ),
                resource_scope=preview_scope,
                scan_preflight_scope=scope,
            )
            self._remember_safe_preview_admission(
                self._preview_admission_cache_key(
                    receipt_authority=self._preview_preflight_receipts,
                    scan=scan,
                    resource_paths=preview_scope.paths,
                ),
                preview_admission,
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
        scan, admission = self._scan_after_resource_preflight(
            scan_id=None,
            source_path=command.source_path,
            source_hint=command.source_hint,
            label_sources=command.label_sources,
            choices=command.choices,
            confirmed=command.resource_preflight_confirmed,
            token=command.resource_preflight_token,
            receipt_authority=self._review_preflight_receipts,
            configuration_scope={"choices": command.choices},
        )
        candidate_id = self.state.next_id("candidate")
        preview_id = self.state.next_id("preview")
        candidate = build_interpretation_candidate(
            candidate_id=candidate_id,
            scan=scan,
            choices=command.choices,
            bids_events_json_reader=admission.bids_events_json_reader,
            resource_reader=admission.resource_reader,
            resource_scope=admission.resource_scope,
            admitted_content_identities=admission.reusable_content_identities,
        )
        preview = build_interpretation_preview(
            preview_id=preview_id,
            candidate=candidate,
            scan=scan,
            resource_preflight=admission.to_diagnostics(),
        )
        self.state.record_scan(scan)
        self.state.record_preview(candidate, preview)

        # Candidate construction just bound the exact admitted carrier content.
        # Explicit Validate and Apply commands perform the later freshness checks.
        decision = validate_interpretation_candidate(
            candidate,
            recheck_content_identity=False,
        )
        self.state.record_validation(candidate.candidate_id, decision)
        return (
            f"Interpretation review: {decision.decision}.",
            {
                "payload_type": "interpretation_review",
                "scan_result": scan.to_dict(),
                "candidate": candidate.to_public_dict(),
                "preview": preview.to_dict(),
                "validation_decision": decision.to_dict(),
                "resource_preflight": admission.to_diagnostics(),
            },
        )

    def handle_preview_interpretation(self, command: Command) -> HandlerResult:
        """Build a reviewable interpretation candidate and preview."""
        if not isinstance(command, PreviewInterpretationCommand):
            raise TypeError("Invalid command for preview_interpretation")
        scan = self.state.resolve_scan(command.scan_id)
        replace_scan = False
        preserve_discovery_scan = False
        selected_eeg_files = self._explicit_selected_eeg_files(command.choices)
        scanned_eeg_files = {
            str(Path(path).expanduser().resolve(strict=False))
            for path in list(getattr(scan, "eeg_files", []) or [])
        }
        selected_scope_changed = any(
            str(Path(path).expanduser().resolve(strict=False)) not in scanned_eeg_files
            for path in selected_eeg_files
        )
        if not bool(scan.bids.get("metadata_materialized")) or selected_scope_changed:
            preserve_discovery_scan = self._preview_narrows_discovered_scope(
                scan,
                command.choices,
            )
            cached_materialization = self._materialize_cached_bids_scan(
                scan=scan,
                choices=command.choices,
            )
            if cached_materialization is not None:
                scan, admission = cached_materialization
            else:
                scan, admission = self._scan_after_resource_preflight(
                    scan_id=scan.scan_id,
                    source_path=scan.source_path,
                    source_hint=scan.source_hint,
                    label_sources=list(scan.label_sources),
                    choices=command.choices,
                    confirmed=command.resource_preflight_confirmed,
                    token=command.resource_preflight_token,
                    receipt_authority=self._preview_preflight_receipts,
                    configuration_scope={"choices": command.choices},
                )
            replace_scan = True
        else:
            admission = self._resolve_preview_resource_preflight(
                scan=scan,
                choices=command.choices,
                confirmed=command.resource_preflight_confirmed,
                token=command.resource_preflight_token,
                receipt_authority=self._preview_preflight_receipts,
                configuration_scope={"choices": command.choices},
                receipt_candidate_id=scan.scan_id,
            )
        candidate_id = self.state.next_id("candidate")
        preview_id = self.state.next_id("preview")
        candidate = build_interpretation_candidate(
            candidate_id=candidate_id,
            scan=scan,
            choices=command.choices,
            bids_events_json_reader=admission.bids_events_json_reader,
            resource_reader=admission.resource_reader,
            resource_scope=admission.resource_scope,
            admitted_content_identities=admission.reusable_content_identities,
        )
        preview = build_interpretation_preview(
            preview_id=preview_id,
            candidate=candidate,
            scan=scan,
            resource_preflight=admission.to_diagnostics(),
        )
        if replace_scan and not preserve_discovery_scan:
            self.state.record_scan(scan)
        self.state.record_preview(candidate, preview)
        return (
            "Interpretation preview ready.",
            {
                "payload_type": "interpretation_preview",
                "candidate": candidate.to_public_dict(),
                "preview": preview.to_dict(),
                "resource_preflight": admission.to_diagnostics(),
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
        self._ensure_candidate_can_apply(command, candidate, decision)
        preflight, _preflight_receipt, receipt_reused = (
            self._resolve_apply_resource_preflight(
                command=command,
                candidate=candidate,
            )
        )
        self._ensure_reviewed_label_content_is_current(candidate)
        training_boundary = (
            self._pipeline_transaction.begin_raw_replacement()
            if self._pipeline_transaction is not None
            else None
        )
        snapshot = self._snapshot_raw_state()
        state_checkpoint = self.state.checkpoint_apply_state()
        try:
            count, errors = self._replace_active_raw_data(
                candidate.selected_eeg_files,
            )
            loaded_files = self._loaded_filepaths() or list(
                candidate.selected_eeg_files
            )
            source_identity_apply = self.apply_service.bind_source_content_identity(
                candidate,
            )
            channels_apply = self.apply_service.apply_bids_channels(candidate)
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
            label_resources = self._admitted_reviewed_label_resources(
                candidate,
                preflight,
            )
            label_apply = self.apply_service.apply_label_carriers(
                candidate,
                label_resources,
            )
            internal_epoch_hints = self.apply_service.record_internal_epoch_hints(
                candidate,
            )
            # Recheck inside the transaction so a carrier changed while raw/labels
            # were being loaded cannot become applied workflow truth.
            self._ensure_reviewed_label_content_is_current(candidate)
            self._ensure_label_apply_succeeded(candidate, label_apply)
            trainer_retired = (
                self._pipeline_transaction.commit_pipeline_invalidation(
                    training_boundary,
                )
                if self._pipeline_transaction is not None
                and training_boundary is not None
                else False
            )
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
                "source_identity_apply": source_identity_apply,
                "channels_apply": channels_apply,
                "label_carriers_pending": list(candidate.label_carriers),
                "label_apply": label_apply,
                "internal_epoch_hints": internal_epoch_hints,
                "trainer_retired": trainer_retired,
                "resource_preflight": {
                    **preflight.to_diagnostics(),
                    "confirmation_receipt_reused": receipt_reused,
                },
            },
        )

    @staticmethod
    def _ensure_reviewed_label_content_is_current(
        candidate: InterpretationCandidate,
    ) -> None:
        assert_review_content_unchanged(
            expected=candidate.content_identity,
            label_carrier_plan=candidate.label_carrier_plan,
            selected_eeg_files=candidate.selected_eeg_files,
            class_map=candidate.class_map,
            event_roles=candidate.event_roles,
            run_event_mappings=candidate.run_event_mappings,
            candidate_id=candidate.candidate_id,
        )

    @staticmethod
    def _admitted_reviewed_label_resources(
        candidate: InterpretationCandidate,
        preflight: ResourcePreflightResult,
    ) -> AdmittedLabelResourceSession | None:
        specs: list[LabelResourceSpec] = []
        for plan in candidate.label_carrier_plan:
            path = str(plan.get("path") or "").strip()
            if not path:
                continue
            time_model = str(plan.get("time_model") or "").strip().lower()
            placement = str(plan.get("placement_method") or "").strip().lower()
            sequence_only = time_model == "trial_order"
            uses_anchor = not sequence_only and bool(
                str(plan.get("selected_anchor") or "").strip()
            )
            uses_duration = placement != "event_code" and uses_anchor
            specs.append(
                LabelResourceSpec(
                    path=path,
                    label_field=str(plan.get("selected_label_field") or "").strip()
                    or None,
                    anchor=(
                        str(plan.get("selected_anchor") or "").strip()
                        if uses_anchor
                        else None
                    ),
                    duration_field=(
                        str(plan.get("selected_duration_field") or "").strip() or None
                        if uses_duration
                        else None
                    ),
                    sequence_only=sequence_only,
                )
            )
        if not specs:
            return None
        return session_from_resource_preflight(specs, preflight)

    def _resolve_apply_resource_preflight(
        self,
        *,
        command: ApplyInterpretationCommand,
        candidate: InterpretationCandidate,
    ) -> tuple[
        ResourcePreflightResult,
        _ImportPreflightReceipt | None,
        bool,
    ]:
        """Return one current preflight without trusting stale UI confirmation."""
        resource_paths = self._candidate_resource_paths(candidate)
        fingerprint = self._resource_scope_fingerprint(resource_paths)
        preflight = check_import_resource_preflight(resource_paths)
        preflight_fingerprint = fingerprint_resource_preflight(preflight)
        receipt = self._matching_import_preflight_receipt(
            command=command,
            candidate_id=candidate.candidate_id,
            scope_fingerprint=fingerprint,
            preflight_fingerprint=preflight_fingerprint,
        )
        if receipt is not None:
            if receipt.payload.requires_confirmation and not (
                command.resource_preflight_confirmed
            ):
                raise self._resource_confirmation_error(receipt)
            enforce_resource_preflight(
                preflight,
                confirmed=command.resource_preflight_confirmed,
            )
            consumed = self._import_preflight_receipts.consume(
                receipt.challenge.challenge_id,
                scope_fingerprint=receipt.challenge.scope_fingerprint,
                candidate_id=receipt.challenge.candidate_id,
                preflight_fingerprint=receipt.challenge.preflight_fingerprint,
            )
            if consumed is None:
                refreshed = self._store_import_preflight_receipt(
                    candidate_id=candidate.candidate_id,
                    scope_fingerprint=fingerprint,
                    preflight=check_import_resource_preflight(resource_paths),
                )
                raise self._resource_confirmation_error(refreshed)
            # Consume before the import mutation so one consent cannot authorize
            # multiple attempts after a downstream loader failure.
            return preflight, consumed, True

        pending_receipt = self._pending_import_preflight_receipt(
            candidate_id=candidate.candidate_id,
            scope_fingerprint=fingerprint,
            preflight_fingerprint=preflight_fingerprint,
        )
        if pending_receipt is not None and not command.resource_preflight_token:
            raise self._resource_confirmation_error(pending_receipt)

        if preflight.requires_confirmation:
            receipt = self._store_import_preflight_receipt(
                candidate_id=candidate.candidate_id,
                scope_fingerprint=fingerprint,
                preflight=preflight,
            )
            raise self._resource_confirmation_error(receipt)
        enforce_resource_preflight(
            preflight,
            confirmed=False,
        )
        return preflight, None, False

    def _resolve_preview_resource_preflight(
        self,
        *,
        scan: Any,
        choices: dict[str, Any],
        confirmed: bool,
        token: str | None,
        receipt_authority: DataInterpretationResourceReceiptAuthority,
        configuration_scope: dict[str, Any],
        receipt_candidate_id: str | None = None,
        additional_paths: list[str] | None = None,
    ) -> _PreviewResourceAdmission:
        """Check all payloads before candidate preview may materialize labels."""
        scope = resolve_interpretation_resource_scope(scan, choices)
        resource_paths = _deduplicate_resource_paths(
            [*scope.paths, *(additional_paths or [])]
        )
        cache_key = self._preview_admission_cache_key(
            receipt_authority=receipt_authority,
            scan=scan,
            resource_paths=(
                scope.paths
                if receipt_authority.command_name
                in {"preview_interpretation", "review_interpretation"}
                else resource_paths
            ),
        )
        cached_admission = self._reusable_safe_preview_admission(
            cache_key=cache_key,
            scope=scope,
        )
        preflight = (
            cached_admission.preflight
            if cached_admission is not None
            else check_import_resource_preflight(resource_paths)
        )
        configuration_fingerprint = fingerprint_resource_scope(
            configuration_scope,
        )
        preflight_fingerprint = fingerprint_resource_preflight(preflight)
        context = {
            "scan_id": str(getattr(scan, "scan_id", "") or ""),
            "source_path": str(getattr(scan, "source_path", "") or ""),
            "source_hint": str(getattr(scan, "source_hint", "") or ""),
            "source_kind": str(getattr(scan, "source_kind", "") or ""),
            "label_sources": list(getattr(scan, "label_sources", []) or []),
        }
        scope_fingerprint = (
            self._interpretation_command_scope_fingerprint(
                command_name=receipt_authority.command_name,
                paths=resource_paths,
                context=context,
            )
            if preflight.requires_confirmation
            else fingerprint_resource_scope(
                {
                    "command": receipt_authority.command_name,
                    "context": context,
                    "resources": list(cache_key[2]),
                }
            )
        )
        receipt_reused = receipt_authority.authorize(
            confirmed=confirmed,
            token=token,
            preflight=preflight,
            scope_fingerprint=scope_fingerprint,
            configuration_fingerprint=configuration_fingerprint,
            preflight_fingerprint=preflight_fingerprint,
            candidate_id=receipt_candidate_id,
        )
        if cached_admission is not None:
            return replace(
                cached_admission,
                confirmation_receipt_reused=receipt_reused,
            )
        bids_events_json_reader = BidsEventsJsonReader.from_resource_preflight(
            scope.bids_events_json_files,
            preflight,
        )
        sidecar_paths = {
            normalized_path_identity(path) for path in scope.bids_events_json_files
        }
        resource_reader = AdmittedResourceReader.from_resource_preflight(
            [
                path
                for path in resource_paths
                if normalized_path_identity(path) not in sidecar_paths
            ],
            preflight,
            dependent_files=scope.eeg_dependencies_by_file,
        )
        admission = _PreviewResourceAdmission(
            preflight=preflight,
            resource_reader=resource_reader,
            bids_events_json_reader=bids_events_json_reader,
            resource_scope=scope,
            confirmation_receipt_reused=receipt_reused,
        )
        if preflight.risk_level is ResourceRiskLevel.SAFE:
            self._remember_safe_preview_admission(cache_key, admission)
        return admission

    @staticmethod
    def _preview_admission_cache_key(
        *,
        receipt_authority: DataInterpretationResourceReceiptAuthority,
        scan: Any,
        resource_paths: list[str],
    ) -> tuple[str, str, tuple[str, ...]]:
        normalized_paths = {
            identity
            for path in resource_paths
            if (identity := normalized_path_identity(path))
        }
        return (
            receipt_authority.command_name,
            str(getattr(scan, "scan_id", "") or ""),
            tuple(sorted(normalized_paths)),
        )

    def _materialize_cached_bids_scan(
        self,
        *,
        scan: Any,
        choices: dict[str, Any],
    ) -> tuple[Any, _PreviewResourceAdmission] | None:
        """Materialize one unchanged BIDS scan without repeating discovery."""
        if not bool(getattr(scan, "bids", {}).get("is_bids")):
            return None
        scope = resolve_interpretation_resource_scope(scan, choices)
        cache_key = self._preview_admission_cache_key(
            receipt_authority=self._preview_preflight_receipts,
            scan=scan,
            resource_paths=scope.paths,
        )
        admission = self._reusable_safe_preview_admission(
            cache_key=cache_key,
            scope=scope,
        )
        preflight_scope = (
            admission.scan_preflight_scope if admission is not None else None
        )
        if admission is None or preflight_scope is None:
            return None
        materialized_scan = scan_source_path(
            scan_id=scan.scan_id,
            source_path=scan.source_path,
            source_hint=scan.source_hint,
            label_sources=list(scan.label_sources),
            preflight_scope=preflight_scope,
            materialize_metadata=True,
            resource_reader=admission.resource_reader,
        )
        return materialized_scan, replace(
            admission,
            resource_scope=resolve_interpretation_resource_scope(
                materialized_scan,
                choices,
            ),
        )

    def _reusable_safe_preview_admission(
        self,
        *,
        cache_key: tuple[str, str, tuple[str, ...]],
        scope: InterpretationResourceScope,
    ) -> _PreviewResourceAdmission | None:
        cached = self._safe_preview_admissions.get(cache_key)
        if cached is None or cached.preflight.risk_level is not ResourceRiskLevel.SAFE:
            return None
        diagnostics = dict(cached.preflight.diagnostics)
        required = diagnostics.get("required_memory_bytes")
        available = available_ram_bytes()
        if (
            isinstance(required, bool)
            or not isinstance(required, int)
            or required < 0
            or available is None
            or required > available * RAM_WARNING_RATIO
        ):
            self._safe_preview_admissions.pop(cache_key, None)
            return None
        try:
            for path in cached.resource_reader.admitted_files:
                cached.resource_reader.assert_unchanged(
                    path,
                    purpose="cached Data Interpretation preview",
                )
            cached.bids_events_json_reader.content_identities(
                scope.bids_events_json_files
            )
        except (ApplicationError, OSError):
            self._safe_preview_admissions.pop(cache_key, None)
            return None

        diagnostics["available_memory_bytes"] = available
        diagnostics["available_ram_bytes"] = available
        diagnostics["required_to_available_ratio"] = (
            float(required / available) if available else None
        )
        total = diagnostics.get("total_memory_bytes")
        if isinstance(total, int) and not isinstance(total, bool):
            diagnostics["used_memory_bytes"] = max(total - available, 0)
        reusable_content_identities = self._latest_admitted_content_identities(
            cached,
            expected_scan_id=cache_key[1],
        )
        return replace(
            cached,
            preflight=replace(cached.preflight, diagnostics=diagnostics),
            resource_scope=scope,
            admission_cache_reused=True,
            reusable_content_identities=reusable_content_identities,
        )

    def _latest_admitted_content_identities(
        self,
        admission: _PreviewResourceAdmission,
        *,
        expected_scan_id: str,
    ) -> dict[str, dict[str, Any]]:
        try:
            candidate = self.state.resolve_candidate(None)
        except PreconditionError:
            return {}
        if candidate.scan_id != expected_scan_id:
            return {}
        admitted_paths = {
            *admission.resource_reader.admitted_files,
            *admission.bids_events_json_reader.admitted_files,
        }
        identities: dict[str, dict[str, Any]] = {}
        for row in candidate.content_identity.get("files", []) or []:
            if not isinstance(row, dict):
                continue
            path = str(row.get("path") or "").strip()
            file_bytes = row.get("file_bytes")
            sha256 = str(row.get("sha256") or "").strip()
            if (
                path not in admitted_paths
                or isinstance(file_bytes, bool)
                or not isinstance(file_bytes, int)
                or file_bytes < 0
                or len(sha256) != 64
            ):
                continue
            identities[path] = {
                "file_bytes": file_bytes,
                "sha256": sha256,
            }
        return identities

    def _remember_safe_preview_admission(
        self,
        cache_key: tuple[str, str, tuple[str, ...]],
        admission: _PreviewResourceAdmission,
    ) -> None:
        self._safe_preview_admissions[cache_key] = admission
        while len(self._safe_preview_admissions) > 8:
            self._safe_preview_admissions.pop(next(iter(self._safe_preview_admissions)))

    def _scan_after_resource_preflight(
        self,
        *,
        scan_id: str | None,
        source_path: str,
        source_hint: str,
        label_sources: list[str],
        choices: dict[str, Any],
        confirmed: bool,
        token: str | None,
        receipt_authority: DataInterpretationResourceReceiptAuthority,
        configuration_scope: dict[str, Any],
        receipt_candidate_id: str | None = None,
        additional_admission_paths: list[str] | None = None,
    ) -> tuple[Any, _PreviewResourceAdmission]:
        """Admit scan payloads and metadata before BIDS tables are parsed."""
        selected_eeg_files = self._explicit_selected_eeg_files(choices)
        if str(source_hint).strip().lower() == "file" and selected_eeg_files:
            scope = discover_explicit_file_preflight_scope(
                source_path=source_path,
                selected_eeg_files=selected_eeg_files,
                label_sources=label_sources,
            )
        else:
            scope = discover_source_preflight_scope(
                source_path=source_path,
                source_hint=source_hint,
                label_sources=label_sources,
                selected_bids_subjects=self._selected_bids_subjects(choices),
            )
        provisional_scan_id = scan_id or "resource-preflight"
        admission = self._resolve_preview_resource_preflight(
            scan=scope.selection_scan_result(scan_id=provisional_scan_id),
            choices=choices,
            confirmed=confirmed,
            token=token,
            receipt_authority=receipt_authority,
            configuration_scope=configuration_scope,
            receipt_candidate_id=receipt_candidate_id or scan_id,
            additional_paths=[
                *scope.metadata_files,
                *(additional_admission_paths or []),
            ],
        )
        admitted_scan_id = scan_id or self.state.next_id("scan")
        scan = scan_source_path(
            scan_id=admitted_scan_id,
            source_path=source_path,
            source_hint=source_hint,
            label_sources=label_sources,
            preflight_scope=scope,
            materialize_metadata=True,
            resource_reader=admission.resource_reader,
        )
        # The provisional preflight scope intentionally carries only bounded
        # path metadata.  Candidate construction must use the BIDS review that
        # was materialized by the admitted scan, while retaining the same
        # verified readers and resource preflight.
        return scan, replace(
            admission,
            resource_scope=resolve_interpretation_resource_scope(scan, choices),
        )

    @staticmethod
    def _explicit_selected_eeg_files(choices: dict[str, Any]) -> list[str]:
        """Return selected EEG paths after applying an optional recipe remap."""
        raw_selected = choices.get(
            "eeg_files",
            choices.get("selected_eeg_files", []),
        )
        if not isinstance(raw_selected, (list, tuple)):
            return []
        raw_remap = choices.get("eeg_file_remap")
        remap = raw_remap if isinstance(raw_remap, dict) else {}
        selected: list[str] = []
        for value in raw_selected:
            source = str(value).strip()
            if not source:
                continue
            target = str(remap.get(source, source)).strip()
            if target and target not in selected:
                selected.append(target)
        return selected

    @staticmethod
    def _selected_bids_subjects(choices: dict[str, Any]) -> list[str]:
        raw_subjects = choices.get("selected_bids_subjects", [])
        if not isinstance(raw_subjects, (list, tuple)):
            return []
        return [str(value).strip() for value in raw_subjects if str(value).strip()]

    @classmethod
    def _preview_narrows_discovered_scope(
        cls,
        scan: Any,
        choices: dict[str, Any],
    ) -> bool:
        """Keep the full discovery scope available when a preview selects a subset."""
        if not cls._explicit_selected_eeg_files(choices):
            return False
        selected_scope = resolve_interpretation_resource_scope(scan, choices)
        discovered_files = {
            str(Path(path).expanduser().resolve(strict=False))
            for path in list(getattr(scan, "eeg_files", []) or [])
        }
        selected_files = {
            str(Path(path).expanduser().resolve(strict=False))
            for path in selected_scope.materializable_eeg_files
        }
        return bool(discovered_files and selected_files != discovered_files)

    @staticmethod
    def _candidate_resource_paths(candidate: InterpretationCandidate) -> list[str]:
        """Return the deduplicated EEG and external-label apply scope."""
        return _deduplicate_resource_paths(
            [
                *candidate.selected_eeg_files,
                *candidate.label_carriers,
                *identity_paths(candidate.content_identity),
            ]
        )

    def _matching_import_preflight_receipt(
        self,
        *,
        command: ApplyInterpretationCommand,
        candidate_id: str,
        scope_fingerprint: str,
        preflight_fingerprint: str,
    ) -> _ImportPreflightReceipt | None:
        token = str(command.resource_preflight_token or "").strip()
        if not token:
            return None
        return self._import_preflight_receipts.peek(
            token,
            scope_fingerprint=scope_fingerprint,
            candidate_id=candidate_id,
            preflight_fingerprint=preflight_fingerprint,
        )

    def _pending_import_preflight_receipt(
        self,
        *,
        candidate_id: str,
        scope_fingerprint: str,
        preflight_fingerprint: str,
    ) -> _ImportPreflightReceipt | None:
        return self._import_preflight_receipts.pending(
            scope_fingerprint=scope_fingerprint,
            candidate_id=candidate_id,
            preflight_fingerprint=preflight_fingerprint,
        )

    def _store_import_preflight_receipt(
        self,
        *,
        candidate_id: str,
        scope_fingerprint: str,
        preflight: ResourcePreflightResult,
    ) -> _ImportPreflightReceipt:
        preflight_fingerprint = fingerprint_resource_preflight(preflight)
        challenge = self._import_preflight_receipts.issue(
            payload=preflight,
            candidate_id=candidate_id,
            scope_fingerprint=scope_fingerprint,
            preflight_fingerprint=preflight_fingerprint,
        )
        receipt = self._import_preflight_receipts.peek(
            challenge.challenge_id,
            candidate_id=candidate_id,
            scope_fingerprint=scope_fingerprint,
            preflight_fingerprint=preflight_fingerprint,
        )
        if receipt is None:  # pragma: no cover - issue and lookup share one authority
            raise RuntimeError("Issued import resource challenge was not stored.")
        return receipt

    @staticmethod
    def _resource_confirmation_error(
        receipt: _ImportPreflightReceipt,
    ) -> ResourceConfirmationRequiredError:
        return ResourceConfirmationRequiredError(
            receipt.payload,
            challenge=receipt.challenge,
        )

    @staticmethod
    def _resource_scope_fingerprint(paths: list[str]) -> str:
        """Fingerprint selected files without reading their EEG sample payload."""
        return fingerprint_resource_scope(
            DataInterpretationCommandService._resource_scope_entries(paths),
        )

    @staticmethod
    def _interpretation_command_scope_fingerprint(
        *,
        command_name: str,
        paths: list[str],
        context: dict[str, Any],
    ) -> str:
        """Bind a receipt to one command, source context, and exact file scope."""
        return fingerprint_resource_scope(
            {
                "command": command_name,
                "context": context,
                "resources": DataInterpretationCommandService._resource_scope_entries(
                    paths,
                ),
            },
        )

    @staticmethod
    def _resource_scope_entries(paths: list[str]) -> list[dict[str, Any]]:
        """Return deterministic file identities without reading EEG payloads."""
        entries: list[dict[str, Any]] = []
        normalized_paths = sorted(
            {
                str(Path(raw_path).expanduser().resolve(strict=False))
                for raw_path in paths
            },
        )
        for raw_path in normalized_paths:
            path = Path(raw_path).expanduser()
            resolved = str(path.resolve(strict=False))
            try:
                stat = path.stat()
            except OSError as exc:
                entries.append(
                    {
                        "path": resolved,
                        "status": "unavailable",
                        "error": exc.__class__.__name__,
                    },
                )
                continue
            entries.append(
                {
                    "path": resolved,
                    "status": "available",
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "ctime_ns": stat.st_ctime_ns,
                    "device": stat.st_dev,
                    "inode": stat.st_ino,
                },
            )
        return entries

    @staticmethod
    def _bounded_recipe_content_fingerprint(recipe_path: str) -> str:
        """Hash one bounded recipe so a path alone never authorizes reload."""
        path = Path(recipe_path)
        digest = hashlib.sha256()
        total = 0
        try:
            with path.open("rb") as handle:
                opened = os.fstat(handle.fileno())
                while chunk := handle.read(65_536):
                    total += len(chunk)
                    if total > IMPORT_RECIPE_MAX_BYTES:
                        raise DataInterpretationCommandService._oversized_recipe_error(
                            path=path,
                            file_bytes=total,
                            file_bytes_is_lower_bound=True,
                        )
                    digest.update(chunk)
                finished = os.fstat(handle.fileno())
            current = path.stat()
        except PreconditionError:
            raise
        except OSError as exc:
            raise PreconditionError(
                f"Import recipe is unavailable: {path}.",
                diagnostics={
                    "recipe_input": {
                        "risk_level": "blocking",
                        "path": str(path),
                        "message": str(exc),
                    },
                },
            ) from exc
        identity_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(
            getattr(opened, field) != getattr(finished, field)
            or getattr(opened, field) != getattr(current, field)
            for field in identity_fields
        ):
            raise PreconditionError(
                f"Import recipe changed while it was being identified: {path}.",
                diagnostics={
                    "code": "interpretation_recipe_changed_during_fingerprint",
                    "path": str(path),
                },
            )
        return digest.hexdigest()

    def _ensure_candidate_can_apply(
        self,
        command: ApplyInterpretationCommand,
        candidate: InterpretationCandidate,
        decision: ValidationDecision,
    ) -> None:
        """Enforce the target candidate's own validation decision."""
        if not bool(candidate.choices.get("skip_labels")):
            placement_reasons = placement_blocked_reasons(
                candidate.label_carrier_plan,
            )
            if placement_reasons:
                raise PreconditionError("; ".join(placement_reasons))
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
            compatibility_dataset = cast(Any, self.dataset)
            if hasattr(compatibility_dataset, "loaded"):
                compatibility_dataset.loaded = list(snapshot["loaded"])
            if hasattr(compatibility_dataset, "imported_paths"):
                compatibility_dataset.imported_paths = list(snapshot["imported_paths"])

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
            content_identity=candidate.content_identity,
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
        recipe_path = self._validate_recipe_input(command.recipe_path)
        recipe_content_fingerprint = self._bounded_recipe_content_fingerprint(
            recipe_path,
        )
        recipe_preflight = check_import_resource_preflight([recipe_path])
        # Recipe JSON is hard-capped at 1 MiB. Enforce a blocking result before
        # parsing, then include the recipe in the one authoritative combined
        # preview check below so one UI consent never has to cross two challenges.
        if recipe_preflight.blocking:
            enforce_resource_preflight(recipe_preflight, confirmed=False)
        recipe_reader = AdmittedResourceReader.from_resource_preflight(
            [recipe_path],
            recipe_preflight,
        )
        try:
            with recipe_reader.guard(
                [recipe_path],
                purpose="import recipe reload",
            ):
                recipe = load_import_recipe(recipe_path)
        except ImportRecipeTooLargeError as exc:
            raise self._oversized_recipe_error(
                path=Path(recipe_path),
                file_bytes=exc.file_bytes_at_least,
                file_bytes_is_lower_bound=True,
            ) from exc
        choices = choices_from_import_recipe(recipe)
        scan, admission = self._scan_after_resource_preflight(
            scan_id=None,
            source_path=recipe.source_path,
            source_hint=recipe.source_kind or "recipe",
            label_sources=recipe.label_sources,
            choices=choices,
            confirmed=command.resource_preflight_confirmed,
            token=command.resource_preflight_token,
            receipt_authority=self._reload_preflight_receipts,
            configuration_scope={
                "stage": "source_preview",
                "recipe_content_sha256": recipe_content_fingerprint,
                "recipe": recipe.to_dict(),
                "choices": choices,
            },
            receipt_candidate_id=recipe.recipe_id,
            additional_admission_paths=[recipe_path],
        )
        candidate_id = self.state.next_id("candidate")
        candidate = build_interpretation_candidate(
            candidate_id=candidate_id,
            scan=scan,
            choices=choices,
            bids_events_json_reader=admission.bids_events_json_reader,
            resource_reader=admission.resource_reader,
            resource_scope=admission.resource_scope,
            admitted_content_identities=admission.reusable_content_identities,
        )
        preview_id = self.state.next_id("preview")
        preview = build_interpretation_preview(
            preview_id=preview_id,
            candidate=candidate,
            scan=scan,
            recipe=recipe,
            resource_preflight=admission.to_diagnostics(),
        )
        # Reload built a fresh candidate from newly admitted content. The saved
        # recipe diff remains reviewable; a later Validate/Apply rechecks bytes.
        decision = validate_interpretation_candidate(
            candidate,
            recheck_content_identity=False,
        )
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
                "candidate": candidate.to_public_dict(),
                "preview": preview.to_dict(),
                "validation_decision": decision.to_dict(),
                "resource_preflight": admission.to_diagnostics(),
            },
        )

    @staticmethod
    def _validate_recipe_input(recipe_path: str) -> str:
        """Resolve a recipe whose size is safe for the existing JSON loader."""
        path = Path(recipe_path).expanduser()
        try:
            stat = path.stat()
        except OSError as exc:
            raise PreconditionError(
                f"Import recipe is unavailable: {path}.",
                diagnostics={
                    "recipe_input": {
                        "risk_level": "blocking",
                        "path": str(path),
                        "message": str(exc),
                    },
                },
            ) from exc
        if not path.is_file():
            raise PreconditionError(
                f"Import recipe must be a JSON file: {path}.",
                diagnostics={
                    "recipe_input": {
                        "risk_level": "blocking",
                        "path": str(path),
                        "message": "The selected recipe path is not a file.",
                    },
                },
            )
        resolved = path.resolve()
        file_bytes = max(int(stat.st_size), 0)
        if file_bytes > IMPORT_RECIPE_MAX_BYTES:
            raise DataInterpretationCommandService._oversized_recipe_error(
                path=resolved,
                file_bytes=file_bytes,
            )
        return str(resolved)

    @staticmethod
    def _oversized_recipe_error(
        *,
        path: Path,
        file_bytes: int,
        file_bytes_is_lower_bound: bool = False,
    ) -> PreconditionError:
        qualifier = "at least " if file_bytes_is_lower_bound else ""
        message = (
            f"Import recipe is {qualifier}{file_bytes} bytes, above the bounded "
            f"{IMPORT_RECIPE_MAX_BYTES}-byte input limit. Choose a smaller recipe "
            "JSON file."
        )
        diagnostics: dict[str, Any] = {
            "risk_level": "blocking",
            "path": str(path),
            "max_bytes": IMPORT_RECIPE_MAX_BYTES,
            "message": message,
        }
        size_key = "file_bytes_at_least" if file_bytes_is_lower_bound else "file_bytes"
        diagnostics[size_key] = file_bytes
        return PreconditionError(
            message,
            diagnostics={"recipe_input": diagnostics},
        )

    def snapshot(self) -> InterpretationStateSnapshot:
        """Return the current Data Interpretation state snapshot."""
        return self.state.snapshot()

    def current_review(self) -> dict[str, Any]:
        """Return the exact pending review without rescanning its resources."""
        return self.state.current_review()

    def clear(self) -> None:
        """Clear Data Interpretation lifecycle state."""
        self.state.clear()
        self._clear_resource_receipts()

    def invalidate_for_legacy_raw_mutation(self) -> bool:
        """Invalidate reviewed import truth after a compatibility raw edit."""
        invalidated = self.state.invalidate_for_legacy_raw_mutation()
        self._clear_resource_receipts()
        return invalidated

    def _clear_resource_receipts(self) -> None:
        self._import_preflight_receipts.clear()
        self._preview_preflight_receipts.clear()
        self._review_preflight_receipts.clear()
        self._reload_preflight_receipts.clear()
        self._safe_preview_admissions.clear()

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
