"""Dataset-generation command handlers for the application command spine."""

from __future__ import annotations

from typing import Any, cast

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

from .commands import ClearDatasetsCommand, Command, GenerateDatasetCommand
from .errors import ApplicationError
from .results import ErrorType

HandlerResult = str | tuple[str, dict[str, Any]]


class DatasetGenerationCommandService:
    """Handle dataset generation, split auditing, and dataset cleanup commands."""

    def __init__(
        self,
        *,
        study: Any,
        training: Any,
    ) -> None:
        self.study = study
        self.training = training

    def handle_generate_dataset(self, command: Command) -> HandlerResult:
        if not isinstance(command, GenerateDatasetCommand):
            raise TypeError("Invalid command for generate_dataset")
        generator = command.generator
        if generator is None:
            config = self._build_data_splitting_config(command)
            generator = self.study.get_datasets_generator(config)
        previous_datasets = list(getattr(self.study, "datasets", []) or [])
        previous_generator = getattr(self.study, "dataset_generator", None)
        previous_trainer = getattr(self.study, "trainer", None)
        try:
            self.training.apply_data_splitting(generator)
            datasets = list(getattr(self.study, "datasets", []) or [])
            count = len(datasets)
            protocol = self._split_protocol_for_generation(command, generator)
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
        except Exception:
            self.restore_generation_state(
                datasets=previous_datasets,
                generator=previous_generator,
                trainer=previous_trainer,
            )
            raise

        if not blocking_issues:
            return (
                f"Generated {count} dataset(s).",
                {
                    "dataset_count": count,
                    "protocol": protocol,
                    "split_audit": audit_payload,
                    "split_summary": self.dataset_split_summary(datasets),
                },
            )

        split_summary = self.dataset_split_summary(datasets)
        self.restore_generation_state(
            datasets=previous_datasets,
            generator=previous_generator,
            trainer=previous_trainer,
        )
        raise ApplicationError(
            message=(
                "Generated dataset failed split audit; fix empty splits or "
                "leakage before training."
            ),
            error_type=ErrorType.DATA_MISMATCH,
            recoverable=True,
            diagnostics={
                "dataset_count": count,
                "protocol": protocol,
                "rolled_back": True,
                "split_audit": audit_payload,
                "split_summary": split_summary,
            },
        )

    def handle_clear_datasets(self, command: Command) -> HandlerResult:
        if not isinstance(command, ClearDatasetsCommand):
            raise TypeError("Invalid command for clear_datasets")
        dataset_count = len(getattr(self.study, "datasets", []) or [])
        trainer_present = getattr(self.study, "trainer", None) is not None
        self.training.clean_datasets(force_update=True)
        return (
            "Datasets and dependent training plans cleared.",
            {
                "dataset_count_before": dataset_count,
                "trainer_cleared": trainer_present,
            },
        )

    def restore_generation_state(
        self,
        *,
        datasets: list[Any],
        generator: Any,
        trainer: Any,
    ) -> None:
        data_manager = getattr(self.study, "data_manager", None)
        if data_manager is not None:
            data_manager.datasets = datasets
            data_manager.dataset_generator = generator
        else:
            self.study.datasets = datasets
            self.study.dataset_generator = generator

        training_manager = getattr(self.study, "training_manager", None)
        if training_manager is not None:
            training_manager.trainer = trainer
        else:
            self.study.trainer = trainer

    @staticmethod
    def dataset_split_summary(datasets: list[Any]) -> dict[str, Any]:
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
            audit = audit_dataset_splits(cast(list[Any], datasets))
            summary["audit"] = audit.to_dict()
        except Exception:
            logger.debug("Failed to audit dataset splits", exc_info=True)
        return summary

    @staticmethod
    def _build_data_splitting_config(
        command: GenerateDatasetCommand,
    ) -> DataSplittingConfig:
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
    def _split_protocol(split_strategy: str) -> str:
        normalized = str(split_strategy or "trial").strip().lower()
        if normalized in {"subject", "subject-wise", "subjectwise"}:
            return "subject-wise"
        if normalized in {"session", "session-wise", "sessionwise"}:
            return "session-wise"
        return "trial-wise"

    def _split_protocol_for_generation(
        self,
        command: GenerateDatasetCommand,
        generator: Any,
    ) -> str:
        if command.generator is None:
            return self._split_protocol(command.split_strategy)

        splitters = getattr(generator, "test_splitter_list", None)
        if splitters is None:
            config = getattr(generator, "config", None)
            splitters = getattr(config, "test_splitter_list", None)
        if splitters:
            split_type = getattr(splitters[0], "split_type", None)
            if split_type in {SplitByType.SUBJECT, SplitByType.SUBJECT_IND}:
                return "subject-wise"
            if split_type in {SplitByType.SESSION, SplitByType.SESSION_IND}:
                return "session-wise"
            if split_type in {SplitByType.TRIAL, SplitByType.TRIAL_IND}:
                return "trial-wise"
        return self._split_protocol(command.split_strategy)
