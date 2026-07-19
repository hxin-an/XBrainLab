"""Dataset-generation command handlers for the application command spine."""

from __future__ import annotations

from collections.abc import Callable
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
from XBrainLab.backend.utils.logger import logger

from .commands import (
    ClearDatasetsCommand,
    Command,
    DatasetGenerationMode,
    GenerateDatasetCommand,
)
from .errors import ApplicationError, PreconditionError, map_exception
from .pipeline_transaction import PipelineStateSnapshot, PipelineStateTransaction
from .results import ErrorType

HandlerResult = str | tuple[str, dict[str, Any]]


class DatasetGenerationCommandService:
    """Handle dataset generation, split auditing, and dataset cleanup commands."""

    def __init__(
        self,
        *,
        study: Any,
        training: Any,
        has_trainer: Callable[[], bool],
        pipeline_transaction: PipelineStateTransaction | None = None,
    ) -> None:
        self.study = study
        self.training = training
        self._has_trainer = has_trainer
        self._pipeline_transaction = pipeline_transaction or PipelineStateTransaction(
            study,
        )

    def handle_generate_dataset(self, command: Command) -> HandlerResult:
        if not isinstance(command, GenerateDatasetCommand):
            raise TypeError("Invalid command for generate_dataset")
        snapshot = self._pipeline_transaction.capture()
        training_boundary = self._pipeline_transaction.begin_downstream_replacement()
        previous_trainer_present = (
            training_boundary.read_boundary.trainer_identity is not None
        )
        replacement_required = bool(
            snapshot.datasets
            or snapshot.dataset_generator is not None
            or previous_trainer_present
        )
        replacement_mode = self._replacement_mode(command)
        if (
            replacement_required
            and replacement_mode is not DatasetGenerationMode.REPLACE_EXISTING
        ):
            raise PreconditionError(
                "Existing datasets or training history require an explicit "
                "replacement command.",
                diagnostics={"replacement_required": True},
            )
        try:
            config = self._build_data_splitting_config(command)
            generator = self.study.get_datasets_generator(config)
            datasets = self._prepare_datasets(generator)
            count = len(datasets)
            protocol = self._split_protocol_for_config(config, command)
            audit = audit_dataset_splits(
                cast(list[Any], datasets),
                protocol=protocol,
            )
            audit_payload = audit.to_dict()
            blocking_issues = [
                issue
                for issue in audit.issues
                if issue.severity == "error" or " split is empty" in issue.message
            ]
        except Exception as exc:
            self._raise_rolled_back_generation_error(
                exc,
                snapshot=snapshot,
                replacement_mode=replacement_mode,
                replacement_required=replacement_required,
                previous_trainer_present=previous_trainer_present,
            )

        split_summary = self.dataset_split_summary(datasets, protocol=protocol)
        if blocking_issues:
            self._raise_rolled_back_generation_error(
                ApplicationError(
                    message=(
                        "Generated dataset failed split audit; fix split coverage, "
                        "source-coordinate provenance, or leakage before training."
                    ),
                    error_type=ErrorType.DATA_MISMATCH,
                    recoverable=True,
                    diagnostics={
                        "dataset_count": count,
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
                        "split_audit": audit_payload,
                        "split_summary": split_summary,
                    },
                ),
                snapshot=snapshot,
                replacement_mode=replacement_mode,
                replacement_required=replacement_required,
                previous_trainer_present=previous_trainer_present,
            )

        try:
            trainer_retired = self._pipeline_transaction.commit_dataset_replacement(
                datasets,
                generator,
                expected=training_boundary,
            )
        except Exception as exc:
            self._raise_rolled_back_generation_error(
                exc,
                snapshot=snapshot,
                replacement_mode=replacement_mode,
                replacement_required=replacement_required,
                previous_trainer_present=previous_trainer_present,
            )
        self._notify_dataset_generation()
        return (
            f"Generated {count} dataset(s).",
            {
                "dataset_count": count,
                "replacement_mode": replacement_mode.value,
                "replaced_existing": replacement_required,
                "previous_dataset_count": len(snapshot.datasets),
                "previous_trainer_present": previous_trainer_present,
                "trainer_retired": trainer_retired,
                "protocol": protocol,
                "split_audit": audit_payload,
                "split_summary": split_summary,
            },
        )

    def handle_clear_datasets(self, command: Command) -> HandlerResult:
        if not isinstance(command, ClearDatasetsCommand):
            raise TypeError("Invalid command for clear_datasets")
        dataset_count = len(getattr(self.study, "datasets", []) or [])
        trainer_present = self._has_trainer()
        self.training.clean_datasets(force_update=True)
        return (
            "Datasets and dependent training plans cleared.",
            {
                "dataset_count_before": dataset_count,
                "trainer_cleared": trainer_present,
            },
        )

    def _raise_rolled_back_generation_error(
        self,
        exc: Exception,
        *,
        snapshot: PipelineStateSnapshot,
        replacement_mode: DatasetGenerationMode,
        replacement_required: bool,
        previous_trainer_present: bool,
    ) -> NoReturn:
        try:
            self._pipeline_transaction.restore(snapshot)
        except Exception as rollback_exc:
            raise ApplicationError(
                message=(
                    "Dataset generation failed and the previous training state "
                    "could not be restored safely."
                ),
                error_type=ErrorType.INTERNAL,
                recoverable=False,
                diagnostics={
                    "rolled_back": False,
                    "rollback_error": str(rollback_exc),
                    "generation_error": str(exc),
                    "replacement_mode": replacement_mode.value,
                },
            ) from rollback_exc

        mapped = map_exception(exc)
        raise ApplicationError(
            message=mapped.message,
            error_type=mapped.error_type,
            recoverable=mapped.recoverable,
            diagnostics={
                **mapped.diagnostics,
                "rolled_back": True,
                "replacement_mode": replacement_mode.value,
                "replacement_required": replacement_required,
                "previous_dataset_count": len(snapshot.datasets),
                "previous_trainer_present": previous_trainer_present,
            },
        ) from exc

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
    def dataset_split_summary(
        datasets: list[Any],
        *,
        protocol: str = "trial-wise",
    ) -> dict[str, Any]:
        if not datasets:
            return {}
        summary: dict[str, Any] = {"count": len(datasets)}
        first = datasets[0]
        for mask_name in ("train_mask", "val_mask", "test_mask"):
            mask = getattr(first, mask_name, None)
            if mask is not None and hasattr(mask, "sum"):
                try:
                    summary[mask_name.replace("_mask", "_count")] = int(mask.sum())
                except Exception as exc:
                    logger.debug("Failed to summarize %s: %s", mask_name, exc)
                    continue
        try:
            audit = audit_dataset_splits(
                cast(list[Any], datasets),
                protocol=protocol,
            )
            summary["audit"] = audit.to_dict()
        except Exception:
            logger.debug("Failed to audit dataset splits", exc_info=True)
        return summary

    @staticmethod
    def _build_data_splitting_config(
        command: GenerateDatasetCommand,
    ) -> DataSplittingConfig:
        if command.split_config:
            return DatasetGenerationCommandService._config_from_payload(
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
    def _replacement_mode(command: GenerateDatasetCommand) -> DatasetGenerationMode:
        try:
            return DatasetGenerationMode(command.replacement_mode)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Unknown dataset replacement mode: {command.replacement_mode}",
            ) from exc

    @staticmethod
    def _config_from_payload(payload: dict[str, Any]) -> DataSplittingConfig:
        train_type = DatasetGenerationCommandService._enum_from_value(
            TrainingType,
            payload.get("train_type"),
            default=TrainingType.IND,
        )
        return DataSplittingConfig(
            train_type=train_type,
            is_cross_validation=bool(payload.get("is_cross_validation", False)),
            val_splitter_list=DatasetGenerationCommandService._splitters_from_payload(
                payload.get("val_splitters"),
                ValSplitByType,
            ),
            test_splitter_list=DatasetGenerationCommandService._splitters_from_payload(
                payload.get("test_splitters"),
                SplitByType,
            ),
        )

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
            split_type = DatasetGenerationCommandService._enum_from_value(
                split_type_enum,
                raw.get("split_type"),
            )
            split_unit = DatasetGenerationCommandService._enum_from_value(
                SplitUnit,
                raw.get("split_unit"),
            )
            value = raw.get("value")
            if value is None:
                value = raw.get("value_var")
            splitter = DataSplitter(
                split_type=split_type,
                value_var=str(value) if value is not None else None,
                split_unit=split_unit,
                is_option=bool(raw.get("is_option", True)),
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

    @staticmethod
    def _split_protocol(split_strategy: str) -> str:
        normalized = str(split_strategy or "trial").strip().lower()
        if normalized in {"subject", "subject-wise", "subjectwise"}:
            return "subject-wise"
        if normalized in {"session", "session-wise", "sessionwise"}:
            return "session-wise"
        return "trial-wise"

    def _split_protocol_for_config(
        self,
        config: DataSplittingConfig,
        command: GenerateDatasetCommand,
    ) -> str:
        splitters = list(config.test_splitter_list or [])
        if splitters:
            split_type = getattr(splitters[0], "split_type", None)
            if split_type in {SplitByType.SUBJECT, SplitByType.SUBJECT_IND}:
                return "subject-wise"
            if split_type in {SplitByType.SESSION, SplitByType.SESSION_IND}:
                return "session-wise"
            if split_type in {SplitByType.TRIAL, SplitByType.TRIAL_IND}:
                return "trial-wise"
        return self._split_protocol(command.split_strategy)
