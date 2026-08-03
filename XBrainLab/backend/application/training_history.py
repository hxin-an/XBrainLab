"""Detached training-history rows for application and compatibility readers."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

MetricValue = float | None
_LOSS_KEY = "loss"
_ACCURACY_KEY = "accuracy"
_AUC_KEY = "auc"
_LEARNING_RATE_KEY = "lr"
_TIME_KEY = "time"


@dataclass(frozen=True, slots=True)
class TrainingHistoryRowIdentity:
    """Stable plan/run indexes within one training-history publication."""

    plan_index: int
    run_index: int

    def to_dict(self) -> dict[str, int]:
        """Return the primitive identity consumed by Qt selection state."""
        return {
            "plan_index": self.plan_index,
            "run_index": self.run_index,
        }


@dataclass(frozen=True, slots=True)
class TrainingHistoryRow:
    """Immutable application projection of one mutable training record."""

    identity: TrainingHistoryRowIdentity
    group_name: str
    run_name: str
    model_name: str
    status: str
    status_detail: str | None
    epoch: int
    max_epochs: int
    is_active: bool
    is_current_run: bool
    start_timestamp: float | None
    end_timestamp: float | None
    train_loss: tuple[MetricValue, ...]
    train_accuracy: tuple[MetricValue, ...]
    train_auc: tuple[MetricValue, ...]
    train_lr: tuple[MetricValue, ...]
    train_time: tuple[MetricValue, ...]
    validation_loss: tuple[MetricValue, ...]
    validation_accuracy: tuple[MetricValue, ...]
    validation_auc: tuple[MetricValue, ...]
    test_accuracy: tuple[MetricValue, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a detached, strictly JSON-safe row."""
        return {
            "identity": self.identity.to_dict(),
            "group_name": self.group_name,
            "run_name": self.run_name,
            "model_name": self.model_name,
            "status": self.status,
            "status_detail": self.status_detail,
            "epoch": self.epoch,
            "max_epochs": self.max_epochs,
            "is_active": self.is_active,
            "is_current_run": self.is_current_run,
            "start_timestamp": self.start_timestamp,
            "end_timestamp": self.end_timestamp,
            "metrics": {
                "train": {
                    _LOSS_KEY: list(self.train_loss),
                    _ACCURACY_KEY: list(self.train_accuracy),
                    _AUC_KEY: list(self.train_auc),
                    _LEARNING_RATE_KEY: list(self.train_lr),
                    _TIME_KEY: list(self.train_time),
                },
                "validation": {
                    _LOSS_KEY: list(self.validation_loss),
                    _ACCURACY_KEY: list(self.validation_accuracy),
                    _AUC_KEY: list(self.validation_auc),
                },
                "test": {
                    _ACCURACY_KEY: list(self.test_accuracy),
                },
            },
        }


def project_training_history_rows(rows: Iterable[Any]) -> list[dict[str, Any]]:
    """Detach mutable plan/record rows into primitive application read data."""
    projected: list[dict[str, Any]] = []
    fallback_plan_indexes: dict[int, int] = {}
    next_run_index: dict[int, int] = {}

    for source_row in rows:
        if not isinstance(source_row, Mapping):
            continue
        plan = source_row.get("plan")
        record = source_row.get("record")
        plan_index = _row_plan_index(
            source_row,
            plan,
            fallback_plan_indexes,
        )
        run_index = _row_run_index(source_row, plan_index, next_run_index)
        projected.append(
            _project_training_history_row(
                source_row,
                plan=plan,
                record=record,
                identity=TrainingHistoryRowIdentity(
                    plan_index=plan_index,
                    run_index=run_index,
                ),
            ).to_dict()
        )
    return projected


def _project_training_history_row(
    source_row: Mapping[str, Any],
    *,
    plan: Any,
    record: Any,
    identity: TrainingHistoryRowIdentity,
) -> TrainingHistoryRow:
    epoch = _record_epoch(record, source_row)
    max_epochs = _maximum_epochs(plan, record, source_row)
    is_current_run = bool(source_row.get("is_current_run", False))
    train_metrics, validation_metrics, test_metrics = _metric_sources(
        source_row,
        record,
    )
    status = _training_status(
        plan,
        record,
        source_row,
        epoch=epoch,
        is_current_run=is_current_run,
    )
    return TrainingHistoryRow(
        identity=identity,
        group_name=str(source_row.get("group_name", "")),
        run_name=str(source_row.get("run_name", "")),
        model_name=str(source_row.get("model_name", "")),
        status=status,
        status_detail=_training_status_detail(plan, source_row, status=status),
        epoch=epoch,
        max_epochs=max_epochs,
        is_active=bool(source_row.get("is_active", False)),
        is_current_run=is_current_run,
        start_timestamp=_finite_float(
            source_row.get(
                "start_timestamp",
                getattr(record, "start_timestamp", None),
            )
        ),
        end_timestamp=_finite_float(
            source_row.get(
                "end_timestamp",
                getattr(record, "end_timestamp", None),
            )
        ),
        train_loss=_copy_metric_series(train_metrics, _LOSS_KEY),
        train_accuracy=_copy_metric_series(train_metrics, _ACCURACY_KEY),
        train_auc=_copy_metric_series(train_metrics, _AUC_KEY),
        train_lr=_copy_metric_series(train_metrics, _LEARNING_RATE_KEY),
        train_time=_copy_metric_series(train_metrics, _TIME_KEY),
        validation_loss=_copy_metric_series(validation_metrics, _LOSS_KEY),
        validation_accuracy=_copy_metric_series(validation_metrics, _ACCURACY_KEY),
        validation_auc=_copy_metric_series(validation_metrics, _AUC_KEY),
        test_accuracy=_copy_metric_series(test_metrics, _ACCURACY_KEY),
    )


def _row_plan_index(
    source_row: Mapping[str, Any],
    plan: Any,
    fallback_plan_indexes: dict[int, int],
) -> int:
    explicit = _non_negative_int(source_row.get("plan_index"))
    if explicit is not None:
        return explicit
    plan_key = id(plan) if plan is not None else id(source_row)
    if plan_key not in fallback_plan_indexes:
        fallback_plan_indexes[plan_key] = len(fallback_plan_indexes)
    return fallback_plan_indexes[plan_key]


def _row_run_index(
    source_row: Mapping[str, Any],
    plan_index: int,
    next_run_index: dict[int, int],
) -> int:
    explicit = _non_negative_int(source_row.get("run_index"))
    if explicit is not None:
        next_run_index[plan_index] = max(
            next_run_index.get(plan_index, 0),
            explicit + 1,
        )
        return explicit
    run_index = next_run_index.get(plan_index, 0)
    next_run_index[plan_index] = run_index + 1
    return run_index


def _record_epoch(record: Any, source_row: Mapping[str, Any]) -> int:
    explicit = _non_negative_int(source_row.get("epoch"))
    if explicit is not None:
        return explicit
    getter = getattr(record, "get_epoch", None)
    value = getter() if callable(getter) else getattr(record, "epoch", 0)
    return _non_negative_int(value) or 0


def _maximum_epochs(
    plan: Any,
    record: Any,
    source_row: Mapping[str, Any],
) -> int:
    explicit = _non_negative_int(source_row.get("max_epochs"))
    if explicit is not None:
        return explicit
    plan_option = getattr(plan, "option", None)
    record_option = getattr(record, "option", None)
    value = getattr(plan_option, "epoch", getattr(record_option, "epoch", 0))
    return _non_negative_int(value) or 0


def _training_status(
    plan: Any,
    record: Any,
    source_row: Mapping[str, Any],
    *,
    epoch: int,
    is_current_run: bool,
) -> str:
    plan_status = ""
    getter = getattr(plan, "get_training_status", None)
    if callable(getter):
        try:
            plan_status = str(getter() or "")
        except Exception:
            plan_status = ""
    status_lower = plan_status.lower()
    if "out of memory" in status_lower or status_lower.startswith("failed"):
        return "Failed"
    finished = False
    is_finished = getattr(record, "is_finished", None)
    if callable(is_finished):
        try:
            finished = bool(is_finished())
        except Exception:
            finished = False
    if finished:
        return "Completed"
    if is_current_run:
        return "Running"
    if epoch == 0:
        return "Pending"
    source_status = source_row.get("status")
    return str(source_status) if isinstance(source_status, str) else "Stopped"


def _training_status_detail(
    plan: Any,
    source_row: Mapping[str, Any],
    *,
    status: str,
) -> str | None:
    """Detach the terminal explanation for the row that actually failed."""
    if status != "Failed":
        return None
    explicit = source_row.get("status_detail")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    error = getattr(plan, "error", None)
    if isinstance(error, str) and error.strip():
        return error.strip()
    return None


def _metric_sources(
    source_row: Mapping[str, Any],
    record: Any,
) -> tuple[Any, Any, Any]:
    metrics = source_row.get("metrics")
    if isinstance(metrics, Mapping):
        return (
            metrics.get("train", {}),
            metrics.get("validation", {}),
            metrics.get("test", {}),
        )
    return (
        getattr(record, "train", {}),
        getattr(record, "val", {}),
        _final_test_metrics(record),
    )


def _final_test_metrics(record: Any) -> dict[str, list[float]]:
    """Return the completed held-out test summary without exposing live objects."""
    evaluation_records = getattr(record, "evaluation_records", None)
    if not isinstance(evaluation_records, Mapping):
        return {}
    test_record = evaluation_records.get("test")
    if test_record is None or getattr(test_record, "evaluation_split", None) != "test":
        return {}
    get_accuracy = getattr(test_record, "get_acc", None)
    if not callable(get_accuracy):
        return {}
    accuracy = _finite_float(get_accuracy())
    if accuracy is None:
        return {}
    return {_ACCURACY_KEY: [accuracy * 100.0]}


def _copy_metric_series(source: Any, key: str) -> tuple[MetricValue, ...]:
    values = source.get(key, ()) if hasattr(source, "get") else ()
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        return ()
    return tuple(_finite_float(value) for value in values)


def _finite_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        integer = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return integer if integer >= 0 else None


__all__ = [
    "TrainingHistoryRow",
    "TrainingHistoryRowIdentity",
    "project_training_history_rows",
]
