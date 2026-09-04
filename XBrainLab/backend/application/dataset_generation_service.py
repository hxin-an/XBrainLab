"""Dataset-generation command handlers for the application command spine."""

from __future__ import annotations

import re
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, NoReturn, cast

from XBrainLab.backend.dataset import (
    DataSplitter,
    DataSplittingConfig,
    SplitByType,
    SplitUnit,
    TrainingType,
    ValSplitByType,
    audit_dataset_splits,
)
from XBrainLab.backend.dataset.split_audit import (
    materialization_digest,
    split_preview_rows,
)
from XBrainLab.backend.exceptions import StaleTrainingPipelineMutationError
from XBrainLab.backend.training_state_contract import TrainingPipelineMutationBoundary
from XBrainLab.backend.utils.logger import logger

from .commands import (
    ClearDatasetsCommand,
    Command,
    SaveDatasetSplitCommand,
)
from .dataset_split_preview import (
    DatasetSplitPreviewReceipt,
    DatasetSplitSpecification,
)
from .errors import ApplicationError, PreconditionError, map_exception
from .pipeline_transaction import (
    DatasetPublicationSnapshot,
    PipelineStateTransaction,
)
from .results import ErrorType
from .state import DatasetSplitLifecycle

HandlerResult = str | tuple[str, dict[str, Any]]
_UNOBSERVED_EPOCH = object()
_MAX_FAILED_AUDIT_ISSUES = 20
_MAX_FAILED_AUDIT_INDICES = 10
_MAX_FAILED_DETAIL_ITEMS = 10


class _DatasetReplacementMode(str, Enum):
    CREATE = "create"
    REPLACE_EXISTING = "replace_existing"


@dataclass(frozen=True)
class _SavedSplit:
    specification: DatasetSplitSpecification
    fingerprint: str
    epoch_revision: int
    preview_summary: dict[str, Any]


@dataclass(frozen=True)
class _ActiveSplit:
    fingerprint: str
    epoch_revision: int
    dataset_identity: tuple[tuple[int, int, int, int, int, int], ...]
    summary: dict[str, Any]


@dataclass(frozen=True)
class PreparedDatasetSplitCandidate:
    """Audited split candidate held privately until training admission succeeds."""

    candidate_id: str
    fingerprint: str
    epoch_revision: int
    datasets: tuple[Any, ...]
    generator: Any
    training_boundary: TrainingPipelineMutationBoundary | None
    previous_publication: DatasetPublicationSnapshot | None
    candidate_publication: DatasetPublicationSnapshot | None
    previous_trainer_startup_snapshot: Any | None
    previous_active_split: _ActiveSplit | None
    protocol: str
    summary: dict[str, Any]
    already_committed: bool = False


class DatasetGenerationCommandService:
    """Handle dataset generation, split auditing, and dataset cleanup commands."""

    def __init__(
        self,
        *,
        study: Any,
        training: Any,
        has_trainer: Callable[[], bool],
        pipeline_transaction: PipelineStateTransaction | None = None,
        get_publication_generation: Callable[[], int] | None = None,
    ) -> None:
        self.study = study
        self.training = training
        self._has_trainer = has_trainer
        self._pipeline_transaction = pipeline_transaction or PipelineStateTransaction(
            study,
        )
        self._get_publication_generation = get_publication_generation
        self._observed_epoch: Any = _UNOBSERVED_EPOCH
        self._epoch_revision = 0
        self._saved_split: _SavedSplit | None = None
        self._active_split: _ActiveSplit | None = None
        self._prepared_candidate: PreparedDatasetSplitCandidate | None = None
        self._materializing_key: tuple[int, str] | None = None
        self._last_split_attempt: dict[str, Any] = {}

    def handle_save_dataset_split(self, command: Command) -> HandlerResult:
        if not isinstance(command, SaveDatasetSplitCommand):
            raise TypeError("Invalid command for configure_dataset_split")
        specification = self._specification_from_command(command)
        config = self.config_from_payload(specification.to_payload())
        self._validate_split_config(config)
        preview_summary = self._validated_preview_summary(
            command.preview_receipt,
            specification=specification,
        )

        epoch_revision = self._observe_epoch()
        datasets = list(getattr(self.study, "datasets", []) or [])
        reuse_verified = self._active_matches(
            fingerprint=specification.fingerprint,
            epoch_revision=epoch_revision,
            datasets=datasets,
        )
        self._saved_split = _SavedSplit(
            specification=specification,
            fingerprint=specification.fingerprint,
            epoch_revision=epoch_revision,
            preview_summary=deepcopy(preview_summary),
        )
        if not (
            self._prepared_candidate is not None
            and self._prepared_candidate.fingerprint == specification.fingerprint
            and self._prepared_candidate.epoch_revision == epoch_revision
        ):
            self._prepared_candidate = None
        self._last_split_attempt = {}
        self._notify_dataset_generation()
        return (
            "Data splitting specification saved.",
            {
                "split_specification": specification.to_payload(),
                "split_specification_fingerprint": specification.fingerprint,
                "split_epoch_revision": epoch_revision,
                "split_preview_summary": deepcopy(preview_summary),
                "materialized": reuse_verified,
                "verified_split_reused": reuse_verified,
                "existing_dataset_count": len(datasets),
                "existing_trainer_preserved": self._has_trainer(),
            },
        )

    def prepare_saved_split_candidate(self) -> PreparedDatasetSplitCandidate:
        """Materialize and audit without publishing or retiring training state."""
        epoch_revision = self._observe_epoch()
        saved = self._saved_split
        if saved is None or saved.epoch_revision != epoch_revision:
            raise PreconditionError(
                "Save a valid data splitting specification before training."
            )

        datasets = list(getattr(self.study, "datasets", []) or [])
        if self._active_matches(
            fingerprint=saved.fingerprint,
            epoch_revision=epoch_revision,
            datasets=datasets,
        ):
            active = self._active_split
            if active is None:
                raise RuntimeError("Verified dataset split cache is unavailable.")
            return PreparedDatasetSplitCandidate(
                candidate_id=(
                    f"active:{epoch_revision}:{saved.fingerprint}:{id(active)}"
                ),
                fingerprint=saved.fingerprint,
                epoch_revision=epoch_revision,
                datasets=tuple(datasets),
                generator=getattr(self.study, "dataset_generator", None),
                training_boundary=None,
                previous_publication=(
                    self._pipeline_transaction.capture_dataset_publication()
                ),
                candidate_publication=(
                    self._pipeline_transaction.capture_dataset_publication()
                ),
                previous_trainer_startup_snapshot=(
                    self._pipeline_transaction.capture_training_startup_snapshot()
                ),
                previous_active_split=active,
                protocol=str(active.summary.get("protocol") or "trial-wise"),
                summary=deepcopy(active.summary),
                already_committed=True,
            )

        cached = self._prepared_candidate
        if cached is not None and self._candidate_matches_current_state(cached, saved):
            return cached

        previous_publication = self._pipeline_transaction.capture_dataset_publication()
        training_boundary = self._pipeline_transaction.begin_downstream_replacement()
        previous_trainer_present = (
            training_boundary.read_boundary.trainer_identity is not None
        )
        replacement_required = bool(
            previous_publication.datasets
            or previous_publication.dataset_generator is not None
            or previous_trainer_present
        )
        replacement_mode = (
            _DatasetReplacementMode.REPLACE_EXISTING
            if replacement_required
            else _DatasetReplacementMode.CREATE
        )
        speculative_snapshot = self._pipeline_transaction.capture()
        candidate_publication: DatasetPublicationSnapshot | None = None
        self._materializing_key = (epoch_revision, saved.fingerprint)
        try:
            config = self.config_from_payload(saved.specification.to_payload())
            generator = self.study.get_datasets_generator(config)
            datasets = self._prepare_datasets(generator)
            expected_digest = str(
                saved.preview_summary.get("materialization_digest") or ""
            )
            actual_digest = materialization_digest(datasets)
            if expected_digest and expected_digest != actual_digest:
                raise PreconditionError(  # noqa: TRY301
                    "Dataset split materialization differs from its reviewed preview. "
                    "Review the split again before training.",
                    diagnostics={
                        "expected_materialization_digest": expected_digest,
                        "actual_materialization_digest": actual_digest,
                        "state_preserved": True,
                    },
                )
            protocols = self._split_protocols_for_config(config)
            protocol = protocols["test"]
            self._require_preview_evidence_matches(
                saved.preview_summary,
                datasets,
                config,
            )
            audit = audit_dataset_splits(
                cast(list[Any], datasets),
                protocol=protocol,
                protocols=protocols,
            )
            required_empty_splits = {"train", "test"}
            if saved.specification.val_splitters:
                required_empty_splits.add("validation")
            blocking_issues = [
                issue
                for issue in audit.issues
                if issue.severity == "error"
                or any(
                    f"{split_name} split is empty" in issue.message.lower()
                    for split_name in required_empty_splits
                )
            ]
            candidate_publication = replace(
                self._pipeline_transaction.capture_dataset_publication(),
                datasets=tuple(datasets),
                dataset_generator=generator,
            )
        except Exception as exc:
            self._raise_preserved_generation_error(
                exc,
                replacement_mode=replacement_mode,
                replacement_required=replacement_required,
                previous_trainer_present=previous_trainer_present,
            )
        finally:
            self._materializing_key = None
            self._pipeline_transaction.restore(speculative_snapshot)

        if blocking_issues:
            bounded_audit = self._bounded_audit(audit)
            failed_split_summary = self._build_split_summary(
                datasets,
                audit_payload=bounded_audit,
            )
            self._prepared_candidate = None
            self._last_split_attempt = {
                "status": DatasetSplitLifecycle.FAILED.value,
                "split_epoch_revision": epoch_revision,
                "split_specification_fingerprint": saved.fingerprint,
                "split_summary": deepcopy(failed_split_summary),
                "audit": deepcopy(bounded_audit),
            }
            self._raise_preserved_generation_error(
                ApplicationError(
                    message=(
                        "Generated dataset failed split audit; fix split coverage, "
                        "source-coordinate provenance, or leakage before training."
                    ),
                    error_type=ErrorType.DATA_MISMATCH,
                    recoverable=True,
                    diagnostics={
                        "dataset_count": len(datasets),
                        "replacement_mode": replacement_mode.value,
                        "replacement_required": replacement_required,
                        "protocol": protocol,
                        "state_preserved": True,
                        "blocking_issue_kinds": sorted(
                            {
                                str(issue.details.get("kind") or "unspecified")
                                for issue in blocking_issues
                            },
                        ),
                        "split_audit": bounded_audit,
                        "split_summary": failed_split_summary,
                    },
                ),
                replacement_mode=replacement_mode,
                replacement_required=replacement_required,
                previous_trainer_present=previous_trainer_present,
            )

        audit_payload = self._bounded_audit(audit)
        split_summary = self._build_split_summary(
            datasets,
            audit_payload=audit_payload,
        )
        candidate = PreparedDatasetSplitCandidate(
            candidate_id=(
                f"candidate:{epoch_revision}:{saved.fingerprint}:{id(generator)}"
            ),
            fingerprint=saved.fingerprint,
            epoch_revision=epoch_revision,
            datasets=tuple(datasets),
            generator=generator,
            training_boundary=training_boundary,
            previous_publication=previous_publication,
            candidate_publication=candidate_publication,
            previous_trainer_startup_snapshot=(
                self._pipeline_transaction.capture_training_startup_snapshot()
            ),
            previous_active_split=self._active_split,
            protocol=protocol,
            summary=deepcopy(split_summary),
        )
        self._prepared_candidate = candidate
        self._last_split_attempt = {}
        return candidate

    def commit_prepared_split(
        self,
        candidate: PreparedDatasetSplitCandidate,
    ) -> dict[str, Any]:
        """Atomically publish one still-current candidate after train admission."""
        if not isinstance(candidate, PreparedDatasetSplitCandidate):
            raise TypeError("candidate must be a PreparedDatasetSplitCandidate")
        epoch_revision = self._observe_epoch()
        saved = self._saved_split
        datasets = list(getattr(self.study, "datasets", []) or [])
        if saved is None or saved.epoch_revision != epoch_revision:
            raise PreconditionError(
                "Save a valid data splitting specification before training."
            )
        if candidate.already_committed and self._active_matches(
            fingerprint=saved.fingerprint,
            epoch_revision=epoch_revision,
            datasets=datasets,
        ):
            return self._preparation_diagnostics(
                candidate,
                materialized=False,
                cache_reused=True,
                trainer_retired=False,
            )
        if (
            candidate is not self._prepared_candidate
            or candidate.fingerprint != saved.fingerprint
            or candidate.epoch_revision != epoch_revision
            or not self._candidate_matches_current_state(candidate, saved)
            or candidate.training_boundary is None
            or candidate.previous_publication is None
            or candidate.candidate_publication is None
        ):
            self._prepared_candidate = None
            raise PreconditionError(
                "Data split preparation became stale before training could start. "
                "Retry training to prepare it again.",
                diagnostics={"state_preserved": True, "retryable": True},
            )

        try:
            trainer_retired = self._pipeline_transaction.commit_dataset_replacement(
                candidate.candidate_publication,
                expected=candidate.training_boundary,
            )
        except Exception as exc:
            rollback_errors: list[str] = []
            stale_boundary = self._is_stale_pipeline_boundary_error(exc)
            if not stale_boundary:
                try:
                    self._pipeline_transaction.restore_training_startup_snapshot(
                        candidate.previous_trainer_startup_snapshot,
                    )
                except Exception as rollback_exc:
                    logger.error(
                        "Failed to restore training state after split commit failure.",
                        exc_info=True,
                    )
                    rollback_errors.append(str(map_exception(rollback_exc).message))
                try:
                    self._pipeline_transaction.restore_dataset_publication(
                        candidate.previous_publication
                    )
                except Exception as rollback_exc:
                    logger.error(
                        "Failed to restore dataset state after split commit failure.",
                        exc_info=True,
                    )
                    rollback_errors.append(str(map_exception(rollback_exc).message))
            self._prepared_candidate = None
            if rollback_errors:
                mapped = map_exception(exc)
                raise ApplicationError(
                    message=mapped.message,
                    error_type=mapped.error_type,
                    recoverable=mapped.recoverable,
                    diagnostics={
                        **mapped.diagnostics,
                        "state_preserved": False,
                        "rollback_failed": True,
                        "rollback_errors": rollback_errors,
                    },
                ) from exc
            self._raise_preserved_generation_error(
                exc,
                replacement_mode=_DatasetReplacementMode.REPLACE_EXISTING,
                replacement_required=True,
                previous_trainer_present=(
                    candidate.training_boundary.read_boundary.trainer_identity
                    is not None
                ),
            )

        committed = list(candidate.datasets)
        self._active_split = _ActiveSplit(
            fingerprint=saved.fingerprint,
            epoch_revision=epoch_revision,
            dataset_identity=self._dataset_identity(committed),
            summary=deepcopy(candidate.summary),
        )
        self._prepared_candidate = None
        self._last_split_attempt = {}
        self._notify_dataset_generation()
        return self._preparation_diagnostics(
            candidate,
            materialized=True,
            cache_reused=False,
            trainer_retired=trainer_retired,
        )

    @staticmethod
    def _is_stale_pipeline_boundary_error(exc: Exception) -> bool:
        if isinstance(exc, StaleTrainingPipelineMutationError):
            return True
        return bool(
            isinstance(exc, PreconditionError)
            and exc.diagnostics.get("code") == "training_pipeline_boundary_changed"
        )

    def discard_prepared_split(self) -> bool:
        """Release one speculative candidate without changing active state."""
        discarded = self._prepared_candidate is not None
        self._prepared_candidate = None
        self._materializing_key = None
        return discarded

    def restore_committed_candidate(
        self,
        candidate: PreparedDatasetSplitCandidate,
    ) -> None:
        """Restore active data and history when admitted training cannot start."""
        if not isinstance(candidate, PreparedDatasetSplitCandidate):
            raise TypeError("candidate must be a PreparedDatasetSplitCandidate")
        if candidate.previous_publication is None:
            raise RuntimeError("Committed split candidate has no rollback publication.")
        self._pipeline_transaction.restore_training_startup_snapshot(
            candidate.previous_trainer_startup_snapshot,
        )
        self._pipeline_transaction.restore_dataset_publication(
            candidate.previous_publication
        )
        self._active_split = candidate.previous_active_split
        self._prepared_candidate = None
        self._materializing_key = None
        self._last_split_attempt = {}
        self._notify_dataset_generation()

    def handle_clear_datasets(self, command: Command) -> HandlerResult:
        if not isinstance(command, ClearDatasetsCommand):
            raise TypeError("Invalid command for clear_datasets")
        dataset_count = len(getattr(self.study, "datasets", []) or [])
        trainer_present = self._has_trainer()
        self.training.clean_datasets(force_update=True)
        self._saved_split = None
        self._active_split = None
        self._prepared_candidate = None
        self._materializing_key = None
        self._last_split_attempt = {}
        return (
            "Datasets and dependent training plans cleared.",
            {
                "dataset_count_before": dataset_count,
                "trainer_cleared": trainer_present,
            },
        )

    def _raise_preserved_generation_error(
        self,
        exc: Exception,
        *,
        replacement_mode: _DatasetReplacementMode,
        replacement_required: bool,
        previous_trainer_present: bool,
    ) -> NoReturn:
        mapped = map_exception(exc)
        raise ApplicationError(
            message=mapped.message,
            error_type=mapped.error_type,
            recoverable=mapped.recoverable,
            diagnostics={
                **mapped.diagnostics,
                "state_preserved": True,
                "replacement_mode": replacement_mode.value,
                "replacement_required": replacement_required,
                "previous_trainer_present": previous_trainer_present,
            },
        ) from exc

    @staticmethod
    def _preparation_diagnostics(
        candidate: PreparedDatasetSplitCandidate,
        *,
        materialized: bool,
        cache_reused: bool,
        trainer_retired: bool,
    ) -> dict[str, Any]:
        audit = candidate.summary.get("audit")
        return {
            "candidate_id": candidate.candidate_id,
            "materialized": materialized,
            "cache_reused": cache_reused,
            "dataset_count": len(candidate.datasets),
            "trainer_retired": trainer_retired,
            "protocol": candidate.protocol,
            "split_audit": deepcopy(audit) if isinstance(audit, dict) else {},
            "split_epoch_revision": candidate.epoch_revision,
            "split_specification_fingerprint": candidate.fingerprint,
            "split_summary": deepcopy(candidate.summary),
        }

    def _notify_dataset_generation(self) -> None:
        notify = getattr(self.training, "notify", None)
        if not callable(notify):
            return
        try:
            notify("config_changed")
        except Exception:
            logger.debug("Dataset generation notification failed", exc_info=True)

    @staticmethod
    def _prepare_datasets(generator: Any) -> list[Any]:
        prepare_result = getattr(generator, "prepare_result", None)
        if not callable(prepare_result):
            raise RuntimeError("Dataset generator cannot prepare a speculative result.")
        prepared = prepare_result()
        if not isinstance(prepared, list):
            raise RuntimeError("Dataset generator returned an invalid prepared result.")
        return list(prepared)

    @staticmethod
    def _build_split_summary(
        datasets: list[Any],
        *,
        audit_payload: dict[str, Any],
    ) -> dict[str, Any]:
        if not datasets:
            return {}
        summary: dict[str, Any] = {
            "count": len(datasets),
            "audit": deepcopy(audit_payload),
        }
        for mask_name in ("train_mask", "val_mask", "test_mask"):
            total = 0
            observed = False
            for dataset in datasets:
                mask = getattr(dataset, mask_name, None)
                if mask is None or not hasattr(mask, "sum"):
                    continue
                try:
                    total += int(mask.sum())
                    observed = True
                except Exception as exc:
                    logger.debug("Failed to summarize %s: %s", mask_name, exc)
                    continue
            if observed:
                summary[mask_name.replace("_mask", "_count")] = total
        return summary

    def active_split_summary(self, datasets: list[Any]) -> dict[str, Any]:
        """Return only the summary verified for the currently active datasets."""
        active = self._active_split
        if (
            active is None
            or not datasets
            or active.dataset_identity != self._dataset_identity(datasets)
        ):
            return {}
        return deepcopy(active.summary)

    def dataset_split_state(self, datasets: list[Any]) -> dict[str, Any]:
        """Return detached saved/materialized state for ApplicationService snapshots."""
        epoch_revision = self._observe_epoch()
        saved = self._saved_split
        if saved is None or saved.epoch_revision != epoch_revision:
            return {
                "split_spec_saved": False,
                "split_specification": {},
                "split_specification_fingerprint": None,
                "split_epoch_revision": None,
                "split_preview_summary": {},
                "split_lifecycle": DatasetSplitLifecycle.UNCONFIGURED,
                "split_materialized": False,
                "active_split_summary": self.active_split_summary(datasets),
                "last_split_attempt": {},
            }
        materialized = self._active_matches(
            fingerprint=saved.fingerprint,
            epoch_revision=saved.epoch_revision,
            datasets=datasets,
        )
        lifecycle = DatasetSplitLifecycle.SAVED
        if self._materializing_key == (saved.epoch_revision, saved.fingerprint):
            lifecycle = DatasetSplitLifecycle.MATERIALIZING
        elif self._last_split_attempt:
            lifecycle = DatasetSplitLifecycle.FAILED
        elif materialized:
            lifecycle = DatasetSplitLifecycle.VERIFIED
        return {
            "split_spec_saved": True,
            "split_specification": saved.specification.to_payload(),
            "split_specification_fingerprint": saved.fingerprint,
            "split_epoch_revision": saved.epoch_revision,
            "split_preview_summary": deepcopy(saved.preview_summary),
            "split_lifecycle": lifecycle,
            "split_materialized": materialized,
            "active_split_summary": self.active_split_summary(datasets),
            "last_split_attempt": deepcopy(self._last_split_attempt),
        }

    def _specification_from_command(
        self,
        command: SaveDatasetSplitCommand,
    ) -> DatasetSplitSpecification:
        if command.split_config is not None:
            return DatasetSplitSpecification.from_payload(command.split_config)
        config = self._build_data_splitting_config(command)
        return DatasetSplitSpecification.from_payload(
            self._config_payload(config),
        )

    @staticmethod
    def _config_payload(config: DataSplittingConfig) -> dict[str, Any]:
        def splitter_payload(splitter: DataSplitter) -> dict[str, Any]:
            split_type = getattr(splitter, "split_type", None)
            split_unit = getattr(splitter, "split_unit", None)
            return {
                "split_type": getattr(split_type, "value", split_type),
                "split_unit": getattr(split_unit, "value", split_unit),
                "value": getattr(splitter, "value_var", None),
                "is_option": bool(getattr(splitter, "is_option", True)),
            }

        return {
            "train_type": config.train_type.value,
            "is_cross_validation": bool(config.is_cross_validation),
            "val_splitters": [
                splitter_payload(splitter) for splitter in config.val_splitter_list
            ],
            "test_splitters": [
                splitter_payload(splitter) for splitter in config.test_splitter_list
            ],
        }

    @staticmethod
    def _validate_split_config(config: DataSplittingConfig) -> None:
        DatasetGenerationCommandService._validate_split_contract(config)
        splitters = [
            *list(config.val_splitter_list or []),
            *list(config.test_splitter_list or []),
        ]
        for splitter in splitters:
            if not bool(getattr(splitter, "is_option", True)):
                continue
            split_unit = getattr(splitter, "split_unit", None)
            value = getattr(splitter, "value_var", None)
            if split_unit is None or value is None or not str(value).strip():
                raise ValueError(
                    "Enabled dataset split rules require a unit and amount."
                )
            if not splitter.is_valid():
                raise ValueError("Dataset split rule has an invalid unit or amount.")
            if split_unit is SplitUnit.RATIO:
                try:
                    ratio = float(value)
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        "Dataset split ratios must be numeric values between 0 and 1."
                    ) from exc
                if not 0 < ratio < 1:
                    raise ValueError(
                        "Dataset split ratios must be numeric values between 0 and 1."
                    )

    @staticmethod
    def _validate_split_contract(config: DataSplittingConfig) -> None:
        """Reject configurations the supported workflow cannot materialize."""
        test_rules = [
            rule for rule in config.test_splitter_list if bool(rule.is_option)
        ]
        val_rules = [rule for rule in config.val_splitter_list if bool(rule.is_option)]
        if len(test_rules) != 1:
            raise ValueError(
                "Dataset splitting requires exactly one supported test rule."
            )
        if len(val_rules) > 1:
            raise ValueError("Dataset splitting supports at most one validation rule.")

        test_rule = test_rules[0]
        allowed_test = {SplitByType.TRIAL, SplitByType.SESSION, SplitByType.SUBJECT}
        if test_rule.split_type not in allowed_test:
            raise ValueError("Test split strategy is not supported by this workflow.")
        allowed_val = {
            ValSplitByType.TRIAL,
            ValSplitByType.SESSION,
            ValSplitByType.SUBJECT,
        }
        if val_rules and val_rules[0].split_type not in allowed_val:
            raise ValueError(
                "Validation split strategy is not supported by this workflow."
            )

        if config.train_type is TrainingType.IND and (
            test_rule.split_type is SplitByType.SUBJECT
            or (val_rules and val_rules[0].split_type is ValSplitByType.SUBJECT)
        ):
            raise ValueError("Individual training does not support By Subject splits.")

        if config.is_cross_validation:
            if test_rule.split_unit is not SplitUnit.KFOLD:
                raise ValueError("Cross-validation test split must use K Fold.")
            if val_rules and val_rules[0].split_unit not in {
                SplitUnit.RATIO,
                SplitUnit.NUMBER,
            }:
                raise ValueError(
                    "Cross-validation validation split cannot use Manual or K Fold."
                )
        elif test_rule.split_unit is SplitUnit.KFOLD:
            raise ValueError("K Fold test splits require cross-validation.")
        if val_rules and val_rules[0].split_unit is SplitUnit.KFOLD:
            raise ValueError("Validation split cannot use K Fold.")

    def _validated_preview_summary(
        self,
        receipt: DatasetSplitPreviewReceipt | None,
        *,
        specification: DatasetSplitSpecification,
    ) -> dict[str, Any]:
        if receipt is None:
            return {}
        if not isinstance(receipt, DatasetSplitPreviewReceipt):
            raise PreconditionError("Dataset split preview receipt is invalid.")
        if (
            receipt.specification != specification
            or receipt.specification_fingerprint != specification.fingerprint
        ):
            raise PreconditionError(
                "Dataset split preview receipt does not match the saved specification."
            )
        if self._get_publication_generation is not None:
            current_generation = self._get_publication_generation()
            if receipt.publication_generation != current_generation:
                raise PreconditionError(
                    "Dataset split preview receipt is stale. Review the split again."
                )
        current_epoch = getattr(
            getattr(self.study, "data_manager", None),
            "epoch_data",
            None,
        )
        if receipt.epoch_token != id(current_epoch):
            raise PreconditionError(
                "Dataset split preview receipt is stale for the current EEG epochs."
            )
        if not re.fullmatch(r"[0-9a-f]{64}", receipt.materialization_digest):
            raise PreconditionError(
                "Dataset split preview receipt lacks a canonical materialization "
                "digest. Review the split again."
            )
        return deepcopy(receipt.summary_payload())

    def _observe_epoch(self) -> int:
        epoch = getattr(getattr(self.study, "data_manager", None), "epoch_data", None)
        if self._observed_epoch is _UNOBSERVED_EPOCH:
            self._observed_epoch = epoch
            self._epoch_revision = 1
            return self._epoch_revision
        if epoch is self._observed_epoch:
            return self._epoch_revision
        self._observed_epoch = epoch
        self._epoch_revision += 1
        self._saved_split = None
        self._active_split = None
        self._prepared_candidate = None
        self._materializing_key = None
        self._last_split_attempt = {}
        return self._epoch_revision

    @staticmethod
    def _dataset_identity(
        datasets: list[Any],
    ) -> tuple[tuple[int, int, int, int, int, int], ...]:
        """Build a cheap token without invoking dataset or epoch accessors."""
        return tuple(
            (
                id(dataset),
                id(getattr(dataset, "epoch_data", None)),
                id(getattr(dataset, "train_mask", None)),
                id(getattr(dataset, "val_mask", None)),
                id(getattr(dataset, "test_mask", None)),
                int(getattr(dataset, "_resource_fingerprint_revision", 0)),
            )
            for dataset in datasets
        )

    def _active_matches(
        self,
        *,
        fingerprint: str,
        epoch_revision: int,
        datasets: list[Any],
    ) -> bool:
        active = self._active_split
        return bool(
            active is not None
            and datasets
            and active.fingerprint == fingerprint
            and active.epoch_revision == epoch_revision
            and active.dataset_identity == self._dataset_identity(datasets)
        )

    def _candidate_matches_current_state(
        self,
        candidate: PreparedDatasetSplitCandidate,
        saved: _SavedSplit,
    ) -> bool:
        if (
            candidate.already_committed
            or candidate.fingerprint != saved.fingerprint
            or candidate.epoch_revision != saved.epoch_revision
            or candidate.previous_publication is None
            or candidate.training_boundary is None
        ):
            return False
        current = self._pipeline_transaction.capture_dataset_publication()
        if current != candidate.previous_publication:
            return False
        try:
            boundary = self._pipeline_transaction.begin_downstream_replacement()
        except Exception:
            return False
        return boundary == candidate.training_boundary

    @staticmethod
    def _bounded_audit(audit: Any) -> dict[str, Any]:
        """Keep command and snapshot diagnostics bounded by fixed limits."""
        issues = list(getattr(audit, "issues", []) or [])
        bounded_issues: list[dict[str, Any]] = []
        for issue in issues[:_MAX_FAILED_AUDIT_ISSUES]:
            raw_details = getattr(issue, "details", {})
            details = (
                {
                    str(key): DatasetGenerationCommandService._bounded_detail(value)
                    for key, value in list(raw_details.items())[
                        :_MAX_FAILED_DETAIL_ITEMS
                    ]
                }
                if isinstance(raw_details, dict)
                else {}
            )
            indices = getattr(issue, "indices", [])
            bounded_issues.append(
                {
                    "dataset_name": str(getattr(issue, "dataset_name", ""))[:200],
                    "severity": str(getattr(issue, "severity", ""))[:40],
                    "message": str(getattr(issue, "message", ""))[:500],
                    "indices": list(indices[:_MAX_FAILED_AUDIT_INDICES])
                    if isinstance(indices, (list, tuple))
                    else [],
                    "details": details,
                }
            )
        return {
            "ok": bool(getattr(audit, "ok", False)),
            "dataset_count": int(getattr(audit, "dataset_count", 0)),
            "issues": bounded_issues,
            "truncated_issue_count": max(
                0,
                len(issues) - len(bounded_issues),
            ),
        }

    @staticmethod
    def _bounded_detail(value: Any) -> Any:
        if value is None or type(value) in {bool, int, float}:
            return value
        if isinstance(value, str):
            return value[:500]
        if isinstance(value, (list, tuple)):
            return [
                DatasetGenerationCommandService._bounded_detail(item)
                for item in value[:_MAX_FAILED_DETAIL_ITEMS]
            ]
        if isinstance(value, dict):
            return {
                str(key): DatasetGenerationCommandService._bounded_detail(item)
                for key, item in list(value.items())[:_MAX_FAILED_DETAIL_ITEMS]
            }
        return str(type(value).__name__)

    @staticmethod
    def _build_data_splitting_config(
        command: SaveDatasetSplitCommand,
    ) -> DataSplittingConfig:
        if command.split_config is not None:
            return DatasetGenerationCommandService.config_from_payload(
                command.split_config,
            )

        split_strategy = command.split_strategy.lower()
        split_by = {
            "trial": SplitByType.TRIAL,
            "session": SplitByType.SESSION,
            "subject": SplitByType.SUBJECT,
        }.get(split_strategy)
        if split_by is None:
            raise ValueError(f"Unknown split strategy: {command.split_strategy}")

        val_split_by = {
            SplitByType.TRIAL: ValSplitByType.TRIAL,
            SplitByType.SESSION: ValSplitByType.SESSION,
            SplitByType.SUBJECT: ValSplitByType.SUBJECT,
        }[split_by]
        training_mode = command.training_mode.lower()
        training_type = {
            "individual": TrainingType.IND,
            "group": TrainingType.FULL,
        }.get(training_mode)
        if training_type is None:
            raise ValueError(f"Unknown training mode: {command.training_mode}")

        return DataSplittingConfig(
            train_type=training_type,
            is_cross_validation=False,
            val_splitter_list=[
                DataSplitter(
                    split_type=val_split_by,
                    value_var=str(command.val_ratio),
                    split_unit=SplitUnit.RATIO,
                ),
            ],
            test_splitter_list=[
                DataSplitter(
                    split_type=split_by,
                    value_var=str(command.test_ratio),
                    split_unit=SplitUnit.RATIO,
                ),
            ],
        )

    @staticmethod
    def config_from_payload(payload: dict[str, Any]) -> DataSplittingConfig:
        """Build the canonical domain config from a detached UI payload."""
        train_type = DatasetGenerationCommandService._enum_from_value(
            TrainingType,
            payload.get("train_type"),
            default=TrainingType.IND,
        )
        is_cross_validation = payload.get("is_cross_validation", False)
        if type(is_cross_validation) is not bool:
            raise ValueError("split_config is_cross_validation must be a bool.")
        config = DataSplittingConfig(
            train_type=train_type,
            is_cross_validation=is_cross_validation,
            val_splitter_list=DatasetGenerationCommandService._splitters_from_payload(
                payload.get("val_splitters"),
                ValSplitByType,
            ),
            test_splitter_list=DatasetGenerationCommandService._splitters_from_payload(
                payload.get("test_splitters"),
                SplitByType,
            ),
        )
        DatasetGenerationCommandService._validate_split_config(config)
        return config

    @staticmethod
    def _splitters_from_payload(
        raw_splitters: Any,
        split_type_enum: type[SplitByType] | type[ValSplitByType],
    ) -> list[DataSplitter]:
        if raw_splitters is None:
            return []
        if not isinstance(raw_splitters, list):
            raise ValueError("split_config must include at least one splitter.")
        if not raw_splitters:
            return []
        splitters: list[DataSplitter] = []
        for raw in raw_splitters:
            if not isinstance(raw, dict):
                raise ValueError("split_config splitters must be objects.")
            try:
                split_type = DatasetGenerationCommandService._enum_from_value(
                    split_type_enum,
                    raw.get("split_type"),
                )
            except ValueError as error:
                raise ValueError(
                    "Unsupported split strategy; reconfigure data splitting."
                ) from error
            split_unit = DatasetGenerationCommandService._enum_from_value(
                SplitUnit,
                raw.get("split_unit"),
            )
            value = raw.get("value")
            if value is None:
                value = raw.get("value_var")
            is_option = raw.get("is_option", True)
            if type(is_option) is not bool:
                raise ValueError("split_config is_option must be a bool.")
            splitter = DataSplitter(
                split_type=split_type,
                value_var=str(value) if value is not None else None,
                split_unit=split_unit,
                is_option=is_option,
            )
            splitters.append(splitter)
        return splitters

    @staticmethod
    def _enum_from_value(
        enum_type: Any,
        value: Any,
        *,
        default: Any | None = None,
    ) -> Any:
        if value is None and default is not None:
            return default
        text = str(value or "").strip()
        for item in enum_type:
            enum_repr = f"{item.__class__.__name__}.{item.name}"
            if text in {item.value, item.name, enum_repr}:
                return item
        raise ValueError(f"Unknown {enum_type.__name__} value: {value}")

    @classmethod
    def _split_protocols_for_config(
        cls,
        config: DataSplittingConfig,
    ) -> dict[str, str]:
        test_rule = next(rule for rule in config.test_splitter_list if rule.is_option)
        protocols = {"test": cls._split_protocol_for_rule(test_rule)}
        validation_rule = next(
            (rule for rule in config.val_splitter_list if rule.is_option), None
        )
        if validation_rule is not None:
            protocols["validation"] = cls._split_protocol_for_rule(validation_rule)
        return protocols

    @staticmethod
    def _split_protocol_for_rule(rule: Any) -> str:
        split_type = getattr(rule, "split_type", None)
        if split_type in {SplitByType.SUBJECT, ValSplitByType.SUBJECT}:
            return "subject-wise"
        if split_type in {SplitByType.SESSION, ValSplitByType.SESSION}:
            return "session-wise"
        return "trial-wise"

    def _require_preview_evidence_matches(
        self,
        preview_summary: dict[str, Any],
        datasets: list[Any],
        config: DataSplittingConfig,
    ) -> None:
        expected_rows = preview_summary.get("rows")
        if not expected_rows:
            return
        test_rule = next(rule for rule in config.test_splitter_list if rule.is_option)
        validation_rule = next(
            (rule for rule in config.val_splitter_list if rule.is_option), None
        )
        actual_rows = split_preview_rows(
            datasets,
            test_rule=test_rule,
            validation_rule=validation_rule,
        )
        actual_summary = {
            "total_count": len(actual_rows),
            "truncated_count": len(actual_rows) - len(expected_rows),
            "train_count": sum(row["train_count"] for row in actual_rows),
            "validation_count": sum(row["validation_count"] for row in actual_rows),
            "test_count": sum(row["test_count"] for row in actual_rows),
            "rows": actual_rows[: len(expected_rows)],
        }
        if any(
            preview_summary.get(key) != value for key, value in actual_summary.items()
        ):
            raise PreconditionError(
                "Dataset split evidence differs from its reviewed preview. "
                "Review the split again before training.",
                diagnostics={"state_preserved": True},
            )
