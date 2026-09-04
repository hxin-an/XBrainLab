"""Detached dataset-splitting context and speculative preview publications."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from copy import copy, deepcopy
from dataclasses import dataclass
from threading import Lock
from typing import Any

import numpy as np

from XBrainLab.backend.dataset.split_audit import (
    materialization_digest,
    split_preview_rows,
)

from .errors import PreconditionError
from .view_publication import ApplicationViewPublication

DATASET_SPLIT_PREVIEW_ROW_LIMIT = 50
_MISSING = object()


@dataclass(frozen=True, slots=True)
class DatasetSplitContextRequest:
    """Request split choices from one exact application publication."""

    publication_generation: int

    def __post_init__(self) -> None:
        _validate_generation(self.publication_generation)


@dataclass(frozen=True, slots=True)
class DatasetSplitChoice:
    """One detached value/label pair suitable for a UI selector."""

    value: str | int
    label: str

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, (str, int)):
            raise TypeError("Dataset split choice values must be strings or integers")
        label = str(self.label).strip()
        if not label:
            raise ValueError("Dataset split choice labels cannot be empty")
        object.__setattr__(self, "label", label)


@dataclass(frozen=True, slots=True)
class DatasetSplitContext:
    """Detached facts required to configure dataset splitting."""

    epoch_available: bool
    subject_count: int = 0
    session_count: int = 0
    label_count: int = 0
    trial_count: int = 0
    trial_group_count: int = 0
    subject_choices: tuple[DatasetSplitChoice, ...] = ()
    session_choices: tuple[DatasetSplitChoice, ...] = ()
    label_choices: tuple[DatasetSplitChoice, ...] = ()
    full_test_strategies: tuple[str, ...] = (
        "By Trial",
        "By Session",
        "By Subject",
    )
    individual_test_strategies: tuple[str, ...] = ("By Trial", "By Session")
    full_validation_strategies: tuple[str, ...] = (
        "Disable",
        "By Trial",
        "By Session",
        "By Subject",
    )
    individual_validation_strategies: tuple[str, ...] = (
        "Disable",
        "By Trial",
        "By Session",
    )
    non_cv_split_units: tuple[str, ...] = ("Ratio", "Number", "Manual")
    cv_test_split_units: tuple[str, ...] = ("K Fold",)
    cv_validation_split_units: tuple[str, ...] = ("Ratio", "Number")
    individual_subject_unavailable_reason: str = (
        "Individual training cannot hold out whole subjects."
    )

    def __post_init__(self) -> None:
        if type(self.epoch_available) is not bool:
            raise TypeError("epoch_available must be a bool")
        for field_name in (
            "subject_count",
            "session_count",
            "label_count",
            "trial_count",
            "trial_group_count",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if any(
            not isinstance(choice, DatasetSplitChoice)
            for choice in (
                *self.subject_choices,
                *self.session_choices,
                *self.label_choices,
            )
        ):
            raise TypeError("Dataset split choices must be DatasetSplitChoice values")
        if not self.epoch_available and any(
            (
                self.subject_count,
                self.session_count,
                self.label_count,
                self.trial_count,
                self.trial_group_count,
                self.subject_choices,
                self.session_choices,
                self.label_choices,
            )
        ):
            raise ValueError("Missing epoch context cannot publish dataset details")


@dataclass(frozen=True, slots=True)
class DatasetSplitContextPublication:
    """One detached dataset-splitting context tied to a verified generation."""

    request: DatasetSplitContextRequest
    generation: int
    context: DatasetSplitContext

    def __post_init__(self) -> None:
        if not isinstance(self.request, DatasetSplitContextRequest):
            raise TypeError("request must be a DatasetSplitContextRequest")
        if self.generation != self.request.publication_generation:
            raise ValueError("context generation must match its request")
        if not isinstance(self.context, DatasetSplitContext):
            raise TypeError("context must be DatasetSplitContext")


@dataclass(frozen=True, slots=True)
class DatasetSplitRule:
    """One serializable validation or test split rule."""

    split_type: str
    split_unit: str | None
    value: str | None
    is_option: bool = True

    def __post_init__(self) -> None:
        split_type = str(self.split_type).strip()
        if not split_type:
            raise ValueError("split_type cannot be empty")
        split_unit = (
            None if self.split_unit is None else str(self.split_unit).strip() or None
        )
        value = None if self.value is None else str(self.value)
        if type(self.is_option) is not bool:
            raise TypeError("is_option must be a bool")
        object.__setattr__(self, "split_type", split_type)
        object.__setattr__(self, "split_unit", split_unit)
        object.__setattr__(self, "value", value)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> DatasetSplitRule:
        """Normalize one external splitter payload."""
        if not isinstance(payload, Mapping):
            raise TypeError("Dataset split rules must be objects")
        value = payload.get("value")
        if value is None:
            value = payload.get("value_var")
        return cls(
            split_type=str(payload.get("split_type") or ""),
            split_unit=(
                None
                if payload.get("split_unit") is None
                else str(payload.get("split_unit"))
            ),
            value=None if value is None else str(value),
            is_option=_strict_bool(payload.get("is_option", True), "is_option"),
        )

    def to_payload(self) -> dict[str, Any]:
        """Return a fresh payload accepted by the command service."""
        return {
            "split_type": self.split_type,
            "split_unit": self.split_unit,
            "value": self.value,
            "is_option": self.is_option,
        }


@dataclass(frozen=True, slots=True)
class DatasetSplitSpecification:
    """Immutable split configuration shared by preview and final generation."""

    train_type: str
    is_cross_validation: bool
    val_splitters: tuple[DatasetSplitRule, ...] = ()
    test_splitters: tuple[DatasetSplitRule, ...] = ()

    def __post_init__(self) -> None:
        train_type = str(self.train_type).strip()
        if not train_type:
            raise ValueError("train_type cannot be empty")
        if type(self.is_cross_validation) is not bool:
            raise TypeError("is_cross_validation must be a bool")
        if any(
            not isinstance(rule, DatasetSplitRule)
            for rule in (*self.val_splitters, *self.test_splitters)
        ):
            raise TypeError("splitters must contain DatasetSplitRule values")
        object.__setattr__(self, "train_type", train_type)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> DatasetSplitSpecification:
        """Copy an external split payload into immutable value objects."""
        if not isinstance(payload, Mapping):
            raise TypeError("Dataset split configuration must be an object")
        return cls(
            train_type=str(payload.get("train_type") or "Individual"),
            is_cross_validation=_strict_bool(
                payload.get("is_cross_validation", False),
                "is_cross_validation",
            ),
            val_splitters=_rules_from_payload(payload.get("val_splitters")),
            test_splitters=_rules_from_payload(payload.get("test_splitters")),
        )

    def to_payload(self) -> dict[str, Any]:
        """Return a fresh payload for the authoritative generation command."""
        return {
            "train_type": self.train_type,
            "is_cross_validation": self.is_cross_validation,
            "val_splitters": [rule.to_payload() for rule in self.val_splitters],
            "test_splitters": [rule.to_payload() for rule in self.test_splitters],
        }

    @property
    def fingerprint(self) -> str:
        """Return a stable identity without reading EEG or generated masks."""
        payload = json.dumps(
            self.to_payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii")
        return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class DatasetSplitPreviewRequest:
    """Request one speculative preview for an exact application generation."""

    request_id: str
    publication_generation: int
    specification: DatasetSplitSpecification

    def __post_init__(self) -> None:
        request_id = str(self.request_id).strip()
        if not request_id:
            raise ValueError("request_id cannot be empty")
        _validate_generation(self.publication_generation)
        if not isinstance(self.specification, DatasetSplitSpecification):
            raise TypeError("specification must be DatasetSplitSpecification")
        object.__setattr__(self, "request_id", request_id)


@dataclass(frozen=True, slots=True)
class DatasetSplitPreviewRow:
    """Detached counts for one generated training split."""

    name: str
    train_count: int
    validation_count: int
    test_count: int
    test_scope_group_count: int = 0
    test_selected_group_count: int = 0
    test_requested_unit: str | None = None
    test_requested_value: str | None = None
    validation_scope_group_count: int = 0
    validation_selected_group_count: int = 0
    validation_requested_unit: str | None = None
    validation_requested_value: str | None = None
    test_missing_class_names: tuple[str, ...] = ()
    validation_missing_class_names: tuple[str, ...] = ()
    saliency_source: str = "unavailable"

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        if not name:
            raise ValueError("Dataset preview row names cannot be empty")
        for field_name in ("train_count", "validation_count", "test_count"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        object.__setattr__(self, "name", name)


@dataclass(frozen=True, slots=True)
class DatasetSplitPreviewPublication:
    """Detached speculative rows tied to one request and generation."""

    request: DatasetSplitPreviewRequest
    generation: int
    rows: tuple[DatasetSplitPreviewRow, ...]
    epoch_token: int = 1
    total_count: int | None = None
    truncated_count: int = 0
    train_count: int | None = None
    validation_count: int | None = None
    test_count: int | None = None
    materialization_digest: str = "unbound"

    def __post_init__(self) -> None:
        if not isinstance(self.request, DatasetSplitPreviewRequest):
            raise TypeError("request must be a DatasetSplitPreviewRequest")
        if self.generation != self.request.publication_generation:
            raise ValueError("preview generation must match its request")
        if isinstance(self.epoch_token, bool) or not isinstance(self.epoch_token, int):
            raise TypeError("epoch_token must be an integer")
        if self.epoch_token < 1:
            raise ValueError("epoch_token must be positive")
        if not self.rows:
            raise ValueError("A dataset split preview must contain at least one row")
        if any(not isinstance(row, DatasetSplitPreviewRow) for row in self.rows):
            raise TypeError("rows must contain DatasetSplitPreviewRow values")
        if len(self.rows) > DATASET_SPLIT_PREVIEW_ROW_LIMIT:
            raise ValueError("Dataset split preview rows exceed the fixed row limit")
        _normalize_preview_totals(self)
        _validate_materialization_digest(self.materialization_digest)

    @property
    def receipt(self) -> DatasetSplitPreviewReceipt:
        """Detach the exact preview evidence that may accompany split saving."""
        return DatasetSplitPreviewReceipt(
            request_id=self.request.request_id,
            publication_generation=self.generation,
            epoch_token=self.epoch_token,
            specification=self.request.specification,
            specification_fingerprint=self.request.specification.fingerprint,
            rows=self.rows,
            total_count=self.total_count,
            truncated_count=self.truncated_count,
            train_count=self.train_count,
            validation_count=self.validation_count,
            test_count=self.test_count,
            materialization_digest=self.materialization_digest,
        )


@dataclass(frozen=True, slots=True)
class DatasetSplitPreviewReceipt:
    """Generation-bound detached evidence from one completed split preview."""

    request_id: str
    publication_generation: int
    epoch_token: int
    specification: DatasetSplitSpecification
    specification_fingerprint: str
    rows: tuple[DatasetSplitPreviewRow, ...]
    total_count: int | None = None
    truncated_count: int = 0
    train_count: int | None = None
    validation_count: int | None = None
    test_count: int | None = None
    materialization_digest: str = "unbound"

    def __post_init__(self) -> None:
        request_id = str(self.request_id).strip()
        if not request_id:
            raise ValueError("request_id cannot be empty")
        _validate_generation(self.publication_generation)
        if isinstance(self.epoch_token, bool) or not isinstance(self.epoch_token, int):
            raise TypeError("epoch_token must be an integer")
        if self.epoch_token < 1:
            raise ValueError("epoch_token must be positive")
        if not isinstance(self.specification, DatasetSplitSpecification):
            raise TypeError("specification must be DatasetSplitSpecification")
        if self.specification_fingerprint != self.specification.fingerprint:
            raise ValueError("specification_fingerprint does not match specification")
        if not self.rows or any(
            not isinstance(row, DatasetSplitPreviewRow) for row in self.rows
        ):
            raise TypeError("rows must contain DatasetSplitPreviewRow values")
        if len(self.rows) > DATASET_SPLIT_PREVIEW_ROW_LIMIT:
            raise ValueError("Dataset split preview rows exceed the fixed row limit")
        _normalize_preview_totals(self)
        _validate_materialization_digest(self.materialization_digest)
        object.__setattr__(self, "request_id", request_id)

    def summary_payload(self) -> dict[str, Any]:
        """Return JSON-safe aggregate counts plus detached per-dataset rows."""
        rows = [
            {
                "name": row.name,
                "train_count": row.train_count,
                "validation_count": row.validation_count,
                "test_count": row.test_count,
                "test_scope_group_count": row.test_scope_group_count,
                "test_selected_group_count": row.test_selected_group_count,
                "test_requested_unit": row.test_requested_unit,
                "test_requested_value": row.test_requested_value,
                "validation_scope_group_count": row.validation_scope_group_count,
                "validation_selected_group_count": row.validation_selected_group_count,
                "validation_requested_unit": row.validation_requested_unit,
                "validation_requested_value": row.validation_requested_value,
                "test_missing_class_names": list(row.test_missing_class_names),
                "validation_missing_class_names": list(
                    row.validation_missing_class_names
                ),
                "saliency_source": row.saliency_source,
            }
            for row in self.rows
        ]
        return {
            "dataset_count": self.total_count,
            "total_count": self.total_count,
            "truncated_count": self.truncated_count,
            "train_count": self.train_count,
            "validation_count": self.validation_count,
            "test_count": self.test_count,
            "materialization_digest": self.materialization_digest,
            "rows": rows,
        }


def _normalize_preview_totals(publication: Any) -> None:
    rows = publication.rows
    total_count = publication.total_count
    if total_count is None:
        total_count = len(rows)
    if (
        isinstance(total_count, bool)
        or not isinstance(total_count, int)
        or total_count < len(rows)
    ):
        raise ValueError("total_count must include every published preview row")
    expected_truncated = total_count - len(rows)
    if publication.truncated_count != expected_truncated:
        raise ValueError("truncated_count must equal total_count minus row count")

    for field_name, row_field in (
        ("train_count", "train_count"),
        ("validation_count", "validation_count"),
        ("test_count", "test_count"),
    ):
        value = getattr(publication, field_name)
        if value is None:
            if expected_truncated:
                raise ValueError(
                    f"{field_name} is required when preview rows are truncated"
                )
            value = sum(getattr(row, row_field) for row in rows)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{field_name} must be a non-negative integer")
        object.__setattr__(publication, field_name, value)
    object.__setattr__(publication, "total_count", total_count)


@dataclass(slots=True)
class _ActivePreview:
    generator: Any
    cancelled: bool = False


@dataclass(frozen=True, slots=True)
class _PreviewStateSnapshot:
    dataset_sequence: int
    evidence_reference: Any
    evidence_value: Any
    evidence_dropped: Any


class DatasetSplitPreviewPublisher:
    """Keep Epochs and DatasetGenerator behind the application boundary."""

    def __init__(
        self,
        *,
        dataset: Any,
        generator_factory: Callable[[Any], Any],
        get_publication: Callable[[], ApplicationViewPublication],
        config_factory: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        self._dataset = dataset
        self._generator_factory = generator_factory
        self._get_publication = get_publication
        self._config_factory = config_factory or _canonical_config_from_payload
        self._active_lock = Lock()
        self._generation_lock = Lock()
        self._active: dict[str, _ActivePreview] = {}

    def publish_context(
        self,
        request: DatasetSplitContextRequest,
    ) -> DatasetSplitContextPublication:
        """Publish detached split facts without transferring live Epochs."""
        if not isinstance(request, DatasetSplitContextRequest):
            raise TypeError("request must be a DatasetSplitContextRequest")
        before = self._get_publication()
        self._validate_generation(request.publication_generation, before)
        epoch_data = self._dataset.get_epoch_data()
        context = self._copy_context(epoch_data)
        after = self._get_publication()
        self._validate_stable_generation(
            request.publication_generation,
            before,
            after,
        )
        return DatasetSplitContextPublication(
            request=request,
            generation=after.generation,
            context=context,
        )

    def publish_preview(
        self,
        request: DatasetSplitPreviewRequest,
    ) -> DatasetSplitPreviewPublication:
        """Generate temporary domain splits and publish detached count rows."""
        if not isinstance(request, DatasetSplitPreviewRequest):
            raise TypeError("request must be a DatasetSplitPreviewRequest")
        before = self._get_publication()
        self._validate_generation(request.publication_generation, before)
        epoch_data = self._dataset.get_epoch_data()
        if epoch_data is None:
            raise PreconditionError(
                "Create EEG epochs before previewing training-data splits."
            )

        config = self._config_factory(request.specification.to_payload())
        generator = self._generator_factory(config)
        active = _ActivePreview(generator=generator)
        self._register(request.request_id, active)
        try:
            with self._generation_lock:
                if active.cancelled:
                    raise PreconditionError(
                        "Dataset split preview was cancelled.",
                        diagnostics={"request_id": request.request_id},
                    )
                snapshot = _capture_preview_state(epoch_data)
                try:
                    _detach_generator_epoch_evidence(generator, epoch_data)
                    generated = generator.generate()
                    datasets = (
                        list(generated)
                        if isinstance(generated, Sequence)
                        else list(getattr(generator, "datasets", []) or [])
                    )
                    row_payloads = split_preview_rows(
                        datasets,
                        test_rule=request.specification.test_splitters[0],
                        validation_rule=(
                            request.specification.val_splitters[0]
                            if request.specification.val_splitters
                            else None
                        ),
                    )
                    detached_rows = [
                        DatasetSplitPreviewRow(
                            **{
                                **row,
                                "test_missing_class_names": tuple(
                                    row["test_missing_class_names"]
                                ),
                                "validation_missing_class_names": tuple(
                                    row["validation_missing_class_names"]
                                ),
                            }
                        )
                        for row in row_payloads
                    ]
                    rows = tuple(detached_rows[:DATASET_SPLIT_PREVIEW_ROW_LIMIT])
                    total_count = len(detached_rows)
                    train_count = sum(row.train_count for row in detached_rows)
                    validation_count = sum(
                        row.validation_count for row in detached_rows
                    )
                    test_count = sum(row.test_count for row in detached_rows)
                    digest = materialization_digest(datasets)
                finally:
                    _restore_preview_state(epoch_data, snapshot)
        except KeyboardInterrupt as exc:
            if active.cancelled:
                raise PreconditionError(
                    "Dataset split preview was cancelled.",
                    diagnostics={"request_id": request.request_id},
                ) from exc
            raise
        finally:
            self._unregister(request.request_id, active)

        after = self._get_publication()
        self._validate_stable_generation(
            request.publication_generation,
            before,
            after,
        )
        return DatasetSplitPreviewPublication(
            request=request,
            generation=after.generation,
            epoch_token=id(epoch_data),
            rows=rows,
            total_count=total_count,
            truncated_count=total_count - len(rows),
            train_count=train_count,
            validation_count=validation_count,
            test_count=test_count,
            materialization_digest=digest,
        )

    def cancel_preview(self, request_id: str) -> bool:
        """Interrupt one active application-owned generator."""
        normalized = str(request_id).strip()
        if not normalized:
            return False
        with self._active_lock:
            active = self._active.get(normalized)
            if active is None:
                return False
            active.cancelled = True
            generator = active.generator
        interrupt = getattr(generator, "set_interrupt", None)
        if callable(interrupt):
            interrupt()
        return True

    def cancel_all(self) -> int:
        """Interrupt every active preview without waiting on worker completion."""
        with self._active_lock:
            active_items = list(self._active.values())
            for active in active_items:
                active.cancelled = True
        for active in active_items:
            interrupt = getattr(active.generator, "set_interrupt", None)
            if callable(interrupt):
                interrupt()
        return len(active_items)

    def _register(self, request_id: str, active: _ActivePreview) -> None:
        with self._active_lock:
            if request_id in self._active:
                raise PreconditionError(
                    "A dataset split preview with this request ID is already active.",
                    diagnostics={"request_id": request_id},
                )
            self._active[request_id] = active

    def _unregister(self, request_id: str, active: _ActivePreview) -> None:
        with self._active_lock:
            if self._active.get(request_id) is active:
                del self._active[request_id]

    @staticmethod
    def _copy_context(epoch_data: Any | None) -> DatasetSplitContext:
        if epoch_data is None:
            return DatasetSplitContext(epoch_available=False)
        subject_map = _safe_group_map(epoch_data, "get_subject_map")
        session_map = _safe_group_map(epoch_data, "get_session_map")
        label_map = getattr(epoch_data, "label_map", {}) or {}
        label_count = len(label_map) if hasattr(label_map, "__len__") else 0
        trial_count = _safe_trial_count(epoch_data)
        trial_group_count = _safe_trial_group_count(epoch_data, trial_count)
        return DatasetSplitContext(
            epoch_available=True,
            subject_count=len(subject_map),
            session_count=len(session_map),
            label_count=max(0, int(label_count)),
            trial_count=trial_count,
            trial_group_count=trial_group_count,
            subject_choices=_choices_from_keys(subject_map),
            session_choices=_choices_from_keys(session_map),
            label_choices=_choices_from_keys(label_map),
        )

    @staticmethod
    def _validate_generation(
        requested_generation: int,
        publication: ApplicationViewPublication,
    ) -> None:
        if not publication.usable or publication.generation != requested_generation:
            raise PreconditionError(
                "The application data changed before dataset splitting could begin.",
                diagnostics={
                    "requested_generation": requested_generation,
                    "current_generation": publication.generation,
                },
            )

    @classmethod
    def _validate_stable_generation(
        cls,
        requested_generation: int,
        before: ApplicationViewPublication,
        after: ApplicationViewPublication,
    ) -> None:
        cls._validate_generation(requested_generation, after)
        if after.generation != before.generation:
            raise PreconditionError(
                "The application data changed while dataset splitting was prepared.",
                diagnostics={
                    "requested_generation": requested_generation,
                    "before_generation": before.generation,
                    "after_generation": after.generation,
                },
            )


def _validate_generation(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("publication_generation must be a positive integer")


def _capture_preview_state(epoch_data: Any) -> _PreviewStateSnapshot:
    from XBrainLab.backend.dataset.dataset import Dataset  # noqa: PLC0415

    evidence_reference = getattr(epoch_data, "trial_selection_evidence", _MISSING)
    evidence_value = (
        _MISSING if evidence_reference is _MISSING else deepcopy(evidence_reference)
    )
    return _PreviewStateSnapshot(
        dataset_sequence=int(Dataset.SEQ),
        evidence_reference=evidence_reference,
        evidence_value=evidence_value,
        evidence_dropped=getattr(
            epoch_data,
            "trial_selection_evidence_dropped",
            _MISSING,
        ),
    )


def _restore_preview_state(
    epoch_data: Any,
    snapshot: _PreviewStateSnapshot,
) -> None:
    from XBrainLab.backend.dataset.dataset import Dataset  # noqa: PLC0415

    Dataset.SEQ = snapshot.dataset_sequence
    if snapshot.evidence_reference is _MISSING:
        if hasattr(epoch_data, "trial_selection_evidence"):
            delattr(epoch_data, "trial_selection_evidence")
    else:
        evidence_reference = snapshot.evidence_reference
        if isinstance(evidence_reference, list):
            evidence_reference[:] = deepcopy(snapshot.evidence_value)
        epoch_data.trial_selection_evidence = evidence_reference

    if snapshot.evidence_dropped is _MISSING:
        if hasattr(epoch_data, "trial_selection_evidence_dropped"):
            delattr(epoch_data, "trial_selection_evidence_dropped")
    else:
        epoch_data.trial_selection_evidence_dropped = snapshot.evidence_dropped


def _detach_generator_epoch_evidence(generator: Any, epoch_data: Any) -> None:
    if getattr(generator, "epoch_data", None) is not epoch_data:
        return
    try:
        detached_epoch_data = copy(epoch_data)
        evidence = getattr(epoch_data, "trial_selection_evidence", _MISSING)
        if evidence is not _MISSING:
            detached_epoch_data.trial_selection_evidence = deepcopy(evidence)
        evidence_dropped = getattr(
            epoch_data,
            "trial_selection_evidence_dropped",
            _MISSING,
        )
        if evidence_dropped is not _MISSING:
            detached_epoch_data.trial_selection_evidence_dropped = evidence_dropped
        generator.epoch_data = detached_epoch_data
    except (AttributeError, TypeError):
        # The state snapshot still protects custom generators that cannot be rebound.
        return


def _canonical_config_from_payload(payload: dict[str, Any]) -> Any:
    from .dataset_generation_service import (  # noqa: PLC0415
        DatasetGenerationCommandService,
    )

    return DatasetGenerationCommandService.config_from_payload(payload)


def _rules_from_payload(raw: Any) -> tuple[DatasetSplitRule, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise TypeError("Dataset splitters must be a list")
    return tuple(DatasetSplitRule.from_payload(item) for item in raw)


def _strict_bool(value: Any, field_name: str) -> bool:
    if type(value) is not bool:
        raise TypeError(f"{field_name} must be a bool")
    return value


def _safe_group_map(epoch_data: Any, method_name: str) -> Mapping[Any, Any]:
    method = getattr(epoch_data, method_name, None)
    if not callable(method):
        return {}
    value = method()
    return value if isinstance(value, Mapping) else {}


def _choices_from_keys(mapping: Mapping[Any, Any]) -> tuple[DatasetSplitChoice, ...]:
    choices = [
        DatasetSplitChoice(
            value=(
                key
                if isinstance(key, (str, int)) and not isinstance(key, bool)
                else str(key)
            ),
            label=(
                str(value)
                if isinstance(value, (str, int)) and not isinstance(value, bool)
                else str(key)
            ),
        )
        for key, value in mapping.items()
    ]
    return tuple(
        sorted(choices, key=lambda item: (item.label.casefold(), str(item.value)))
    )


def _safe_trial_count(epoch_data: Any) -> int:
    get_length = getattr(epoch_data, "get_data_length", None)
    if callable(get_length):
        return _non_negative_count(get_length(), "trial")
    data = getattr(epoch_data, "data", ())
    try:
        return max(0, len(data))
    except TypeError:
        return 0


def _safe_trial_group_count(epoch_data: Any, trial_count: int) -> int:
    get_groups = getattr(epoch_data, "get_trial_group_list", None)
    if not callable(get_groups):
        return trial_count
    try:
        groups = np.asarray(get_groups())
        if groups.ndim != 1:
            return trial_count
        return _non_negative_count(len(set(groups.tolist())), "trial group")
    except (AttributeError, TypeError, ValueError):
        return trial_count


def _non_negative_count(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} count must be a non-negative integer")
    converted = int(value)
    if converted < 0:
        raise ValueError(f"{field_name} count must be a non-negative integer")
    return converted


def _validate_materialization_digest(value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError("materialization_digest must be a non-empty string")
