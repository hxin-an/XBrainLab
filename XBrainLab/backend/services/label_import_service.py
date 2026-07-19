"""Label import service for applying external labels to loaded EEG data files."""

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias

import numpy as np
from numpy.typing import NDArray

from XBrainLab.backend.event_semantics import mark_gdf_rejected_trials
from XBrainLab.backend.load_data import EventLoader, Raw
from XBrainLab.backend.utils.logger import logger

LabelPayload: TypeAlias = Sequence[Any] | NDArray[Any]
LabelOperation: TypeAlias = tuple[
    Any,
    LabelPayload,
    dict[Any, str],
    set[str] | None,
    bool,
]
TimestampLabelOperation: TypeAlias = tuple[Raw, LabelPayload, dict[Any, str]]
AtomicLabelFailurePhase: TypeAlias = Literal["preparation", "commit"]


@dataclass(frozen=True)
class AtomicLabelRollbackFailure:
    """One failed compensation after an atomic label commit error."""

    target_path: str
    exception_type: str
    message: str


class AtomicLabelStateUnknownError(RuntimeError):
    """Raised when a failed label commit cannot restore every live target."""

    state_unknown = True
    recoverable = False

    def __init__(
        self,
        *,
        operation_name: str,
        commit_error: Exception,
        rollback_failures: list[AtomicLabelRollbackFailure],
    ) -> None:
        self.operation_name = operation_name
        self.commit_error = commit_error
        self.rollback_failures = tuple(rollback_failures)
        rollback_summary = "; ".join(
            f"{failure.target_path}: {failure.message}" for failure in rollback_failures
        )
        super().__init__(
            f"Atomic {operation_name} commit failed ({commit_error}) and rollback "
            f"was incomplete ({rollback_summary}). Active label state is unknown; "
            "do not retry automatically."
        )


class AtomicLabelApplyError(RuntimeError):
    """Recoverable atomic failure with a bounded user-facing explanation."""

    state_unknown = False
    recoverable = True

    def __init__(
        self,
        *,
        operation_name: str,
        phase: AtomicLabelFailurePhase,
        cause: Exception,
    ) -> None:
        self.operation_name = operation_name
        self.phase = phase
        self.cause = cause
        if isinstance(cause, ValueError) and str(cause).strip():
            self.error_code = "label_validation_failed"
            self.user_message = str(cause).strip()
        else:
            self.error_code = "label_application_failed"
            self.user_message = (
                "Reviewed labels could not be applied safely; no labels were changed."
            )
        super().__init__(f"Atomic label {phase} failed.")


class LabelImportService:
    """Service for handling label import operations.

    Encapsulates logic for mapping label files to data files, filtering
    and synchronizing events, and applying labels to ``Raw`` objects.
    Supports batch mapping, sequential label distribution, and explicit
    force-import compatibility mode.
    """

    _FORCE_IMPORT_FALLBACK_EPOCHS = 100
    """Legacy default epoch count used when the actual count is unknown."""

    def apply_labels_batch(
        self,
        target_files: list[Any],
        label_map: dict[str, LabelPayload],
        file_mapping: dict[str, str],
        mapping: dict[Any, str],
        selected_event_names: set[str] | None = None,
    ) -> int:
        """Apply labels to multiple files based on a file-to-label mapping.

        Args:
            target_files: List of Raw data objects to label.
            label_map: Mapping from label filename to its label array.
            file_mapping: Mapping from data filepath to label filename.
            mapping: Mapping from numeric label code to human-readable name.
            selected_event_names: Optional set of event names to filter by.

        Returns:
            Number of files successfully updated.

        """
        matched = self._mapped_label_targets(target_files, label_map, file_mapping)
        if len(matched) != len(target_files):
            logger.error(
                "Atomic label batches require one valid label mapping for every "
                "target; no labels were applied."
            )
            return 0
        timestamp_matches = [
            item for item in matched if self._is_timestamp_labels(item[2])
        ]
        if timestamp_matches and (
            len(timestamp_matches) != len(matched)
            or not all(isinstance(data, Raw) for data, _name, _labels in matched)
        ):
            logger.error(
                "Timestamp label batches cannot mix placement modes or non-Raw "
                "targets; no labels were applied."
            )
            return 0
        mode = "timestamp" if timestamp_matches else "sequence"
        operations = [
            (target, labels, mapping, selected_event_names, False)
            for target, _label_name, labels in matched
        ]
        try:
            return self._apply_label_operations_atomically(
                operations,
                operation_name=f"{mode} label batch",
                success_count=len(matched),
            )
        except AtomicLabelApplyError:
            return 0

    @staticmethod
    def _mapped_label_targets(
        target_files: list[Any],
        label_map: dict[str, LabelPayload],
        file_mapping: dict[str, str],
    ) -> list[tuple[Any, str, LabelPayload]]:
        matched: list[tuple[Any, str, LabelPayload]] = []
        for data in target_files:
            data_path = data.get_filepath()
            label_name = file_mapping.get(data_path)
            if label_name is None or label_name not in label_map:
                continue
            matched.append((data, label_name, label_map[label_name]))
        return matched

    @staticmethod
    def _is_timestamp_labels(labels: LabelPayload) -> bool:
        try:
            return len(labels) > 0 and isinstance(labels[0], dict)
        except (KeyError, TypeError):
            return False

    def apply_timestamp_labels_atomically(
        self,
        operations: Sequence[TimestampLabelOperation],
        *,
        operation_name: str = "reviewed timestamp label batch",
    ) -> int:
        """Stage every timestamp target, then commit through one strict path."""
        if not operations:
            return 0
        unsupported = [
            type(target).__name__
            for target, _labels, _mapping in operations
            if not isinstance(target, Raw)
        ]
        if unsupported:
            target_types = ", ".join(sorted(set(unsupported)))
            raise TypeError(
                "Atomic timestamp label application requires Raw targets; "
                f"received: {target_types}."
            )
        prepared: list[LabelOperation] = [
            (target, labels, mapping, None, False)
            for target, labels, mapping in operations
        ]
        return self._apply_label_operations_atomically(
            prepared,
            operation_name=operation_name,
            success_count=len(prepared),
        )

    def _apply_label_operations_atomically(
        self,
        operations: list[LabelOperation],
        *,
        operation_name: str,
        success_count: int,
    ) -> int:
        staged: list[tuple[Any, Any]] = []
        try:
            for (
                target,
                labels,
                mapping,
                selected_event_names,
                force_import,
            ) in operations:
                staged_target = self._copy_label_target(target)
                if force_import:
                    self._force_apply_single(
                        staged_target,
                        list(labels),
                        mapping,
                        selected_event_names,
                    )
                else:
                    self.apply_labels_to_single_file(
                        staged_target,
                        labels,
                        mapping,
                        selected_event_names,
                    )
                staged.append((target, staged_target))
            snapshots = [
                (target, self._copy_label_target(target))
                for target, _staged_target in staged
            ]
        except Exception as exc:
            logger.error(
                "Atomic %s preparation failed: %s",
                operation_name,
                exc,
                exc_info=True,
            )
            raise AtomicLabelApplyError(
                operation_name=operation_name,
                phase="preparation",
                cause=exc,
            ) from exc

        try:
            self._commit_staged_label_states_atomically(
                staged,
                snapshots,
                operation_name=operation_name,
            )
        except AtomicLabelStateUnknownError:
            raise
        except Exception as exc:
            logger.error(
                "Atomic %s commit failed: %s",
                operation_name,
                exc,
                exc_info=True,
            )
            raise AtomicLabelApplyError(
                operation_name=operation_name,
                phase="commit",
                cause=exc,
            ) from exc
        return success_count

    def _commit_staged_label_states_atomically(
        self,
        staged: list[tuple[Any, Any]],
        snapshots: list[tuple[Any, Any]],
        *,
        operation_name: str,
    ) -> None:
        try:
            for target, staged_target in staged:
                self._replace_raw_label_state(target, staged_target)
        except Exception as commit_error:
            rollback_failures = self._rollback_label_states(snapshots)
            if rollback_failures:
                raise AtomicLabelStateUnknownError(
                    operation_name=operation_name,
                    commit_error=commit_error,
                    rollback_failures=rollback_failures,
                ) from commit_error
            raise

    @staticmethod
    def _copy_label_target(target: Any) -> Any:
        staged_target = target.copy()
        if staged_target is target:
            raise RuntimeError("Label target copy returned the original object.")
        return staged_target

    def _rollback_label_states(
        self,
        snapshots: list[tuple[Any, Any]],
    ) -> list[AtomicLabelRollbackFailure]:
        failures: list[AtomicLabelRollbackFailure] = []
        for target, snapshot in snapshots:
            try:
                self._replace_raw_label_state(target, snapshot)
            except Exception as rollback_error:  # noqa: PERF203
                failure = AtomicLabelRollbackFailure(
                    target_path=self._label_target_path(target),
                    exception_type=type(rollback_error).__name__,
                    message=str(rollback_error),
                )
                failures.append(failure)
                logger.error(
                    "Failed to restore atomic label state for %s: %s",
                    failure.target_path,
                    rollback_error,
                    exc_info=True,
                )
        return failures

    @staticmethod
    def _label_target_path(target: Any) -> str:
        getter = getattr(target, "get_filepath", None)
        if callable(getter):
            try:
                return str(getter())
            except Exception:
                return f"<{type(target).__name__}>"
        return f"<{type(target).__name__}>"

    @staticmethod
    def _replace_raw_label_state(target: Any, source: Any) -> None:
        target.set_mne(source.get_mne().copy())
        target.raw_events = (
            source.raw_events.copy() if source.raw_events is not None else None
        )
        target.raw_event_id = (
            source.raw_event_id.copy() if source.raw_event_id is not None else None
        )
        target.set_labels_imported(source.is_labels_imported())

    def apply_labels_sequence(
        self,
        target_files: list[Any],
        labels: list[Any],
        mapping: dict[Any, str],
        selected_event_names: set[str] | None = None,
        force_import: bool = False,
    ) -> int:
        """Apply a flat label list sequentially across multiple files.

        Distributes labels based on each file's epoch count. Falls back
        to force-import mode if a count mismatch occurs and ``force_import``
        is True.

        Args:
            target_files: List of Raw data objects.
            labels: Flat list of labels to distribute.
            mapping: Mapping from numeric label code to human-readable name.
            selected_event_names: Optional set of event names to filter by.
            force_import: If True, ignore mismatches and force application.

        Returns:
            Number of files successfully updated, or 0 on mismatch
            without force.

        """
        label_count = len(labels)
        total_epochs = sum(
            self.get_epoch_count_for_file(d, selected_event_names) for d in target_files
        )

        if label_count == total_epochs and total_epochs > 0:
            current_idx = 0
            operations: list[LabelOperation] = []
            for data in target_files:
                n = self.get_epoch_count_for_file(data, selected_event_names)
                file_labels = labels[current_idx : current_idx + n]
                current_idx += n

                if n > 0:
                    operations.append(
                        (
                            data,
                            file_labels,
                            mapping,
                            selected_event_names,
                            False,
                        )
                    )
            try:
                return self._apply_label_operations_atomically(
                    operations,
                    operation_name="distributed sequence label batch",
                    success_count=len(target_files),
                )
            except AtomicLabelApplyError:
                return 0

        if force_import:
            # Force Import Logic
            current_idx = 0
            operations = []
            for data in target_files:
                # In force mode, we might not trust the filter, but let's try to
                # estimate size or just take chunks. The original UI logic used
                # get_epoch_count_for_file(data, None)
                n = self.get_epoch_count_for_file(data, None)
                if n == 0:
                    n = self._FORCE_IMPORT_FALLBACK_EPOCHS

                if current_idx + n <= len(labels):
                    file_labels = labels[current_idx : current_idx + n]
                    current_idx += n
                    operations.append(
                        (
                            data,
                            file_labels,
                            mapping,
                            selected_event_names,
                            True,
                        )
                    )
                    continue
                logger.warning(
                    "Forced sequence label import cannot cover every target; "
                    "no labels were applied."
                )
                return 0
            try:
                return self._apply_label_operations_atomically(
                    operations,
                    operation_name="forced sequence label batch",
                    success_count=len(target_files),
                )
            except AtomicLabelApplyError:
                return 0

        # Mismatch and not forced
        logger.warning(
            "Sequential label import skipped due to count mismatch: labels=%d, "
            "expected_epochs=%d, files=%d, filtered_events=%s",
            label_count,
            total_epochs,
            len(target_files),
            selected_event_names,
        )
        return 0

    def apply_labels_to_single_file(
        self,
        data: Any,
        labels: LabelPayload,
        mapping: dict[Any, str],
        selected_event_names: set[str] | None = None,
    ):
        """Apply labels to a single data object.

        Detects whether labels are in Timestamp Mode (list of dicts) or
        Sequence Mode (list of ints) and delegates accordingly.

        Args:
            data: Raw data object to apply labels to.
            labels: Labels to apply (ints for Sequence, dicts for Timestamp).
            mapping: Mapping from numeric label code to human-readable name.
            selected_event_names: Optional set of event names to filter by
                when creating events in Sequence Mode.

        """
        logger.info(
            f"Applying labels to {data.get_filename()}. Label count: {len(labels)}",
        )

        loader = EventLoader(data)
        loader.label_list = list(labels)  # type: ignore[assignment]

        # Check Mode
        is_timestamp_mode = (
            isinstance(labels, list) and len(labels) > 0 and isinstance(labels[0], dict)
        )

        if is_timestamp_mode:
            # Timestamp Mode: No filtering needed, just create events
            loader.create_event(mapping)
        else:
            # Sequence Mode: Handle filtering if names provided
            selected_ids = None
            if data.is_raw():
                events, event_id_map = data.get_event_list()
                if event_id_map:
                    if selected_event_names is not None:
                        selected_ids = _selected_event_ids(
                            event_id_map,
                            selected_event_names,
                        )
                        evidence = f"selected names: {selected_event_names}"
                    else:
                        selected_ids = infer_event_ids_for_label_count(
                            events,
                            event_id_map,
                            len(labels),
                        )
                        evidence = f"label row count: {len(labels)}"
                    if selected_ids is not None:
                        logger.info(
                            "Filtered IDs for %s: %s (from %s)",
                            data.get_filename(),
                            selected_ids,
                            evidence,
                        )

            loader.create_event(mapping, selected_event_ids=selected_ids)

        mark_gdf_rejected_trials(data)
        loader.apply()
        data.set_labels_imported(True)
        logger.info("Successfully applied labels to %s", data.get_filename())

    def _force_apply_single(
        self,
        data: Any,
        labels: list[Any],
        mapping: dict[Any, str],
        selected_event_names: set[str] | None = None,
    ):
        """Force-apply labels to a single data object without validation.

        Args:
            data: Raw data object to apply labels to.
            labels: Integer labels to force-apply.
            mapping: Mapping from numeric label code to human-readable name.
            selected_event_names: Optional set of event names to filter by.

        """
        loader = EventLoader(data)
        loader.label_list = list(labels)  # type: ignore[assignment]

        # Handle filtering if names provided
        selected_ids = None
        if selected_event_names is not None and data.is_raw():
            _, event_id_map = data.get_event_list()
            if event_id_map:
                selected_ids = _selected_event_ids(
                    event_id_map,
                    selected_event_names,
                )
                logger.info(
                    f"Force Import: Filtered IDs for {data.get_filename()}: "
                    f"{selected_ids}",
                )

        loader.create_event(mapping, selected_event_ids=selected_ids)
        loader.apply()

        data.set_labels_imported(True)

    def get_epoch_count_for_file(
        self,
        data: Any,
        selected_event_names: set[str] | None,
    ) -> int:
        """Calculate the number of epochs or events in a file matching a filter.

        Args:
            data: Raw data object to inspect.
            selected_event_names: Optional set of event names to count.
                If None, all events are counted.

        Returns:
            Number of matching epochs or events.

        """
        if data.is_raw():
            events, event_id_map = data.get_event_list()
            if selected_event_names is not None and event_id_map:
                relevant_ids = _selected_event_ids(
                    event_id_map,
                    selected_event_names,
                )
                if relevant_ids:
                    mask = np.isin(events[:, -1], relevant_ids)
                    return int(np.sum(mask))
                return 0
            return len(events)
        return data.get_epochs_length()


def _selected_event_ids(
    event_id_map: dict[str, int],
    selected_event_names: set[str],
) -> list[int]:
    selected = {
        " ".join(str(item).strip().split()).casefold()
        for item in selected_event_names
        if str(item).strip()
    }
    if not selected:
        return []

    ids: list[int] = []
    seen: set[int] = set()
    for name, event_id in event_id_map.items():
        aliases = _event_selection_aliases(name, event_id)
        if selected.isdisjoint(aliases):
            continue
        if event_id in seen:
            continue
        ids.append(event_id)
        seen.add(event_id)
    return ids


def _event_selection_aliases(name: str, event_id: int) -> set[str]:
    text = " ".join(str(name or "").strip().split())
    aliases = {text.casefold(), str(event_id).casefold()}
    if not text:
        return aliases
    normalized = text.casefold()
    if normalized.startswith(
        (
            "stimulus/s",
            "response/r",
            "event/e",
            "annotation/",
            "trigger/",
        )
    ):
        match = re.search(r"\b\d+\b", text)
        if match:
            aliases.add(str(int(match.group(0))).casefold())
    return aliases


def infer_event_ids_for_label_count(
    events: Any,
    event_id_map: dict[str, int],
    label_count: int,
) -> list[int] | None:
    """Infer an unambiguous event group from label-row count evidence."""
    if label_count <= 0:
        return None
    counts = Counter(int(value) for value in np.asarray(events)[:, -1])
    ids_by_frequency: dict[int, list[int]] = {}
    for event_id in set(event_id_map.values()):
        count = counts.get(int(event_id), 0)
        if count > 0:
            ids_by_frequency.setdefault(count, []).append(int(event_id))

    balanced_groups = [
        sorted(ids_)
        for frequency, ids_ in ids_by_frequency.items()
        if 2 <= len(ids_) <= 12 and frequency * len(ids_) == label_count
    ]
    if len(balanced_groups) == 1:
        return balanced_groups[0]
    if balanced_groups:
        return None

    exact_single_ids = sorted(
        event_id for event_id, count in counts.items() if count == label_count
    )
    return exact_single_ids if len(exact_single_ids) == 1 else None
