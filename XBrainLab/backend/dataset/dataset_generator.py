"""Dataset generator module for creating train/val/test splits from epoch data."""

from collections.abc import Callable
from copy import deepcopy
from typing import TYPE_CHECKING
from uuid import uuid4

import numpy as np

from ..utils import validate_type
from ..utils.filesystem_identity import validate_filesystem_metadata
from .data_splitter import DataSplittingConfig
from .dataset import Dataset, Epochs
from .option import SplitByType, SplitUnit, TrainingType, ValSplitByType

MAX_CV_LOCAL_REPAIR_ATTEMPTS = 256

if TYPE_CHECKING:  # pragma: no cover
    from ..study import Study


class DatasetGenerator:
    """Generator for creating datasets from epoch data and splitting configuration.

    Orchestrates the full dataset generation pipeline including test/validation
    splitting, cross-validation fold management, and Individual/Full schemes.

    Attributes:
        epoch_data: Epoch data to be split.
        config: Splitting configuration defining train/val/test partitioning.
        datasets: List of generated datasets.
        interrupted: Whether the dataset generation was interrupted.
        preview_failed: Whether the preview generation failed.
        test_splitter_list: List of splitters for the test set.
        val_splitter_list: List of splitters for the validation set.

    """

    def __init__(
        self,
        epoch_data: Epochs,
        config: DataSplittingConfig,
        datasets: list[Dataset] | None = None,
    ):
        """Initialize the dataset generator.

        Args:
            epoch_data: Epoch data to split into datasets.
            config: Splitting configuration for partitioning.
            datasets: Initial list of datasets. Must be empty or None.

        Raises:
            ValueError: If datasets list is non-empty.

        """
        validate_type(epoch_data, Epochs, "epoch_data")
        validate_type(config, DataSplittingConfig, "config")
        if datasets is None:
            datasets = []
        elif len(datasets) != 0:
            raise ValueError("Initial datasets list must be empty or None")
        self.epoch_data = epoch_data
        self.config = config
        self.test_splitter_list = config.test_splitter_list
        self.val_splitter_list = config.val_splitter_list

        self.datasets = datasets
        self.interrupted = False
        self.preview_failed = False
        self.done = False

    def handle_ind(self) -> None:
        """Wrapper for generating datasets for individual scheme.
        Called by :func:`generate`.
        """
        subject_names = [
            self.epoch_data.get_subject_name(subject_idx)
            for subject_idx in range(len(self.epoch_data.get_subject_index_list()))
        ]
        for subject_name in subject_names:
            validate_filesystem_metadata(subject_name, field="subject metadata")

        for subject_idx, subject_name in enumerate(subject_names):
            self._raise_if_interrupted()
            name_prefix = f"Subject-{subject_name}"

            def hook(dataset, subject_idx=subject_idx):
                dataset.set_remaining_by_subject_idx(subject_idx)

            self.handle(name_prefix, hook)

    def handle_full(self) -> None:
        """Wrapper for generating datasets for full scheme.
        Called by :func:`generate`.
        """
        name_prefix = "Fold"
        self.handle(name_prefix)

    def handle(self, name_prefix: str, dataset_hook: Callable | None = None) -> None:
        """Generate datasets for a given name prefix and optional hook.

        Creates one or more datasets depending on whether cross-validation
        is enabled. Each dataset is split into test, validation, and train
        partitions.

        Args:
            name_prefix: Prefix for naming generated datasets (e.g. ``"Fold"``).
            dataset_hook: Optional callable applied to each dataset before
                splitting, used to filter epochs for specific schemes
                (e.g. restricting to a single subject).

        """
        self._raise_if_interrupted()
        scope = np.ones(self.epoch_data.get_data_length(), dtype=bool)
        if dataset_hook is not None:
            probe = Dataset(self.epoch_data, self.config)
            dataset_hook(probe)
            scope = probe.get_remaining_mask()
        if not scope.any():
            raise ValueError("Split scope is empty")
        test_splitter = self._required_test_splitter()
        fold_count = self._fold_count(test_splitter, scope)
        cross_validation_cohort_id = (
            uuid4().hex if self.config.is_cross_validation else None
        )
        validation = self._active_validation_splitter()
        paired_validation_masks: list[np.ndarray] | None = None
        if fold_count == 1 and validation is not None:
            test_mask, validation_mask = self._paired_masks(scope)
            test_folds = [test_mask]
            paired_validation_masks = [validation_mask]
        else:
            test_folds = self._test_folds(test_splitter, scope, fold_count)
        for group_idx, test_mask in enumerate(test_folds):
            self._raise_if_interrupted()
            dataset = Dataset(self.epoch_data, self.config)
            dataset.set_name(f"{name_prefix}_{group_idx}")
            if cross_validation_cohort_id is not None:
                dataset.set_cross_validation_cohort_id(cross_validation_cohort_id)
            if dataset_hook:
                dataset_hook(dataset)
            dataset.set_test(test_mask)
            validation_mask = (
                paired_validation_masks[group_idx]
                if paired_validation_masks is not None
                else self._validation_mask(scope, test_mask)
            )
            if validation_mask.any():
                dataset.set_val(validation_mask)
            dataset.set_remaining_to_train()
            self._validate_partition(dataset, scope)
            self.datasets.append(dataset)

    def _required_test_splitter(self):
        """Return the one admitted test rule.

        Application admission owns the public strategy matrix.  This guard
        keeps direct domain callers from silently materializing a different
        workflow when they bypass that command path.
        """
        active = [item for item in self.test_splitter_list if item.is_option]
        if len(active) != 1:
            raise ValueError("Exactly one active test split rule is required")
        splitter = active[0]
        if not splitter.is_valid():
            raise ValueError("Preview failed")
        return splitter

    def _active_validation_splitter(self):
        active = [item for item in self.val_splitter_list if item.is_option]
        if len(active) > 1:
            raise ValueError("At most one active validation split rule is allowed")
        if not active or active[0].split_type == ValSplitByType.DISABLE:
            return None
        splitter = active[0]
        if not splitter.is_valid():
            raise ValueError("Preview failed")
        return splitter

    def _target_values(self, splitter) -> np.ndarray:
        split_type = splitter.split_type
        if split_type in (SplitByType.TRIAL, ValSplitByType.TRIAL):
            return self.epoch_data.get_trial_group_list()
        if split_type in (SplitByType.SESSION, ValSplitByType.SESSION):
            # Session ids are dataset-global labels, never subject-session
            # pairs.  The BIDS run identifier is deliberately not consulted.
            return self.epoch_data.get_session_list()
        if split_type in (SplitByType.SUBJECT, ValSplitByType.SUBJECT):
            return self.epoch_data.get_subject_list()
        raise ValueError(f"Unsupported split type: {split_type.value}")

    def _keys(self, splitter, scope: np.ndarray) -> list[int]:
        return sorted(
            int(value) for value in np.unique(self._target_values(splitter)[scope])
        )

    def _mask_for_keys(
        self, splitter, scope: np.ndarray, keys: list[int]
    ) -> np.ndarray:
        return scope & np.isin(self._target_values(splitter), keys)

    def _fold_count(self, splitter, scope: np.ndarray) -> int:
        if not self.config.is_cross_validation:
            if splitter.get_split_unit() == SplitUnit.KFOLD:
                raise ValueError("K Fold requires cross-validation")
            return 1
        if splitter.get_split_unit() != SplitUnit.KFOLD:
            raise ValueError("Cross-validation test split must use K Fold")
        count = int(splitter.get_value())
        groups = self._keys(splitter, scope)
        if count < 2 or count > len(groups):
            if splitter.split_type == SplitByType.TRIAL:
                raise ValueError(
                    f"K-fold trial split requires at least {count} atomic groups; "
                    f"found {len(groups)}.",
                )
            raise ValueError(
                f"K Fold requires 2 to {len(groups)} groups in every split scope",
            )
        return count

    def _test_folds(
        self, splitter, scope: np.ndarray, fold_count: int
    ) -> list[np.ndarray]:
        keys = self._keys(splitter, scope)
        if fold_count == 1:
            last_error: ValueError | None = None
            for (
                _score,
                test_count,
                _validation_count,
            ) in self._paired_non_cv_count_candidates(scope):
                try:
                    selected = self._select_non_cv_keys(
                        splitter,
                        scope,
                        None,
                        "test",
                        requested_count=test_count,
                    )
                    return [self._mask_for_keys(splitter, scope, selected)]
                except ValueError as error:
                    last_error = error
            raise ValueError(
                "Test split is infeasible while preserving all training classes"
            ) from last_error
        # Bounded deterministic balancing: assign each atomic group to the
        # fold where its labels are currently least represented, while holding
        # the exact group capacities fixed.  This is deliberately not a
        # solver; stable keys settle all remaining ties.
        base, remainder = divmod(len(keys), fold_count)
        capacities = [base + int(index < remainder) for index in range(fold_count)]
        partitions: list[list[int]] = [[] for _ in range(fold_count)]
        label_counts: list[dict[int, int]] = [{} for _ in range(fold_count)]
        labels = self.epoch_data.get_label_list()
        for key in keys:
            self._raise_if_interrupted()
            group_labels = labels[self._mask_for_keys(splitter, scope, [key])]
            choices = [
                index
                for index in range(fold_count)
                if len(partitions[index]) < capacities[index]
            ]
            fold_index = min(
                choices,
                key=lambda index: (
                    sum(
                        label_counts[index].get(int(label), 0) for label in group_labels
                    ),
                    len(partitions[index]),
                    index,
                ),
            )
            partitions[fold_index].append(key)
            for label in group_labels:
                label_counts[fold_index][int(label)] = (
                    label_counts[fold_index].get(int(label), 0) + 1
                )
        all_labels = set(labels[scope].tolist())

        def complete_fold_count(candidate: list[list[int]]) -> int:
            complete = 0
            for fold_keys in candidate:
                test_mask = self._mask_for_keys(splitter, scope, fold_keys)
                if set(labels[scope & ~test_mask].tolist()) != all_labels:
                    continue
                try:
                    validation_mask = self._validation_mask(scope, test_mask)
                except ValueError:
                    continue
                if (
                    set(labels[scope & ~test_mask & ~validation_mask].tolist())
                    == all_labels
                ):
                    complete += 1
            return complete

        # A bounded stable swap repairs greedy placements that preserve local
        # label balance yet leave a fold's train complement class-incomplete.
        # It is intentionally a local alternative, not a combinatorial solver.
        current_complete = complete_fold_count(partitions)
        attempts = 0
        while current_complete < fold_count and attempts < MAX_CV_LOCAL_REPAIR_ATTEMPTS:
            self._raise_if_interrupted()
            repaired = False
            incomplete = []
            for index, fold_keys in enumerate(partitions):
                test_mask = self._mask_for_keys(splitter, scope, fold_keys)
                try:
                    validation_mask = self._validation_mask(scope, test_mask)
                except ValueError:
                    incomplete.append(index)
                    continue
                if (
                    set(labels[scope & ~test_mask & ~validation_mask].tolist())
                    != all_labels
                ):
                    incomplete.append(index)
            for left in incomplete:
                for right in range(fold_count):
                    if left == right:
                        continue
                    for left_index, left_key in enumerate(partitions[left]):
                        for right_index, right_key in enumerate(partitions[right]):
                            if attempts >= MAX_CV_LOCAL_REPAIR_ATTEMPTS:
                                break
                            attempts += 1
                            candidate = [list(item) for item in partitions]
                            candidate[left][left_index] = right_key
                            candidate[right][right_index] = left_key
                            candidate_complete = complete_fold_count(candidate)
                            if candidate_complete > current_complete:
                                partitions = candidate
                                current_complete = candidate_complete
                                repaired = True
                                break
                        if repaired or attempts >= MAX_CV_LOCAL_REPAIR_ATTEMPTS:
                            break
                    if repaired or attempts >= MAX_CV_LOCAL_REPAIR_ATTEMPTS:
                        break
                if repaired or attempts >= MAX_CV_LOCAL_REPAIR_ATTEMPTS:
                    break
            if not repaired:
                break
        return [self._mask_for_keys(splitter, scope, group) for group in partitions]

    def _requested_count(self, splitter, scope: np.ndarray) -> tuple[int, bool]:
        keys = self._keys(splitter, scope)
        unit = splitter.get_split_unit()
        value = splitter.get_value()
        if unit == SplitUnit.MANUAL:
            if len(value) != len(set(value)):
                raise ValueError("Manual split contains duplicate selections")
            if splitter.split_type in (SplitByType.TRIAL, ValSplitByType.TRIAL):
                invalid = [
                    index
                    for index in value
                    if index < 0 or index >= len(scope) or not scope[index]
                ]
                if invalid:
                    raise ValueError(
                        f"Manual trial indices are outside scope: {invalid}"
                    )
                groups = self.epoch_data.get_trial_group_list()
                selected_groups = [int(groups[index]) for index in value]
                if len(selected_groups) != len(set(selected_groups)):
                    raise ValueError(
                        "Manual trial indices select the same atomic group"
                    )
                return len(selected_groups), True
            missing = sorted(set(value) - set(keys))
            if missing:
                raise ValueError(
                    f"Manual split selections are outside scope: {missing}"
                )
            return len(value), True
        if unit == SplitUnit.NUMBER:
            count = int(value)
            if count > len(keys):
                raise ValueError(
                    f"Requested {count} groups but scope contains {len(keys)} groups",
                )
            return count, True
        if unit == SplitUnit.RATIO:
            return max(1, int(float(value) * len(keys))), False
        raise ValueError("Only Ratio, Number, and Manual are valid outside K Fold")

    def _paired_non_cv_count_candidates(
        self,
        scope: np.ndarray,
    ) -> list[tuple[tuple[int, int, int, int], int, int | None]]:
        """Return bounded count pairs in the published objective order."""
        test = self._required_test_splitter()
        validation = self._active_validation_splitter()
        test_requested, test_exact = self._requested_count(test, scope)
        radius = 16

        def bounded_counts(total: int, target: int, exact: bool) -> list[int]:
            if exact:
                return [target]
            if total <= 64:
                return list(range(1, total))
            return sorted(
                {
                    1,
                    total - 2,
                    *range(max(1, target - radius), min(total, target + radius + 1)),
                },
            )

        test_total = len(self._keys(test, scope))
        if validation is None:
            return sorted(
                (
                    (
                        (
                            abs(test_count - test_requested),
                            -(test_total - test_count),
                            abs(test_count - test_requested),
                            test_count,
                        ),
                        test_count,
                        None,
                    )
                    for test_count in bounded_counts(
                        test_total,
                        test_requested,
                        test_exact,
                    )
                ),
            )
        validation_requested, validation_exact = self._requested_count(
            validation, scope
        )
        candidates: list[tuple[tuple[int, int, int, int], int, int | None]] = []
        validation_total = len(self._keys(validation, scope))
        same_unit = validation.split_type.value == test.split_type.value
        for test_count in bounded_counts(test_total, test_requested, test_exact):
            for validation_count in bounded_counts(
                validation_total,
                validation_requested,
                validation_exact,
            ):
                if same_unit and test_count + validation_count >= test_total:
                    continue
                if test_exact and test_count != test_requested:
                    continue
                if validation_exact and validation_count != validation_requested:
                    continue
                score = (
                    abs(test_count - test_requested)
                    + abs(validation_count - validation_requested),
                    -((test_total - test_count - validation_count) if same_unit else 0),
                    abs(test_count - test_requested),
                    test_count,
                )
                candidates.append((score, test_count, validation_count))
        if not candidates:
            raise ValueError(
                "Split capacities cannot leave non-empty train, validation, "
                "and test groups"
            )
        return sorted(candidates)

    def _select_non_cv_keys(
        self,
        splitter,
        scope: np.ndarray,
        excluded: np.ndarray | None,
        partition: str,
        requested_count: int | None = None,
        candidate_offset: int = 0,
    ) -> list[int]:
        desired, exact = self._requested_count(splitter, scope)
        if requested_count is not None:
            desired = requested_count
        values = self._target_values(splitter)
        candidates = self._keys(splitter, scope)
        if candidates and candidate_offset:
            offset = candidate_offset % len(candidates)
            candidates = candidates[offset:] + candidates[:offset]
        candidate_rank = {key: index for index, key in enumerate(candidates)}
        if splitter.get_split_unit() == SplitUnit.MANUAL:
            requested = [int(value) for value in splitter.get_value()]
            if splitter.split_type in (SplitByType.TRIAL, ValSplitByType.TRIAL):
                groups = self.epoch_data.get_trial_group_list()
                selected = sorted({int(groups[index]) for index in requested})
            else:
                selected = sorted(requested)
            selected_mask = self._mask_for_keys(splitter, scope, selected)
            if excluded is not None:
                test = self._required_test_splitter()
                if (
                    np.any(selected_mask & excluded)
                    and splitter.split_type.value == test.split_type.value
                ):
                    raise ValueError(
                        f"{partition.title()} manual split overlaps test isolation",
                    )
                residual_mask = selected_mask & ~excluded
                if not residual_mask.any():
                    raise ValueError(
                        f"{partition.title()} manual split is empty after "
                        "test isolation"
                    )
                if any(
                    not np.any(self._mask_for_keys(splitter, scope, [key]) & ~excluded)
                    for key in selected
                ):
                    raise ValueError(
                        f"{partition.title()} manual selection has no residual "
                        "after test isolation"
                    )
                labels = self.epoch_data.get_label_list()
                blocked = selected_mask | excluded
                if set(labels[scope & ~blocked].tolist()) != set(
                    labels[scope].tolist()
                ):
                    raise ValueError(
                        f"{partition.title()} split is infeasible while preserving "
                        "all training classes",
                    )
                return selected
            if not selected_mask.any():
                raise ValueError(
                    f"{partition.title()} manual split is empty after test isolation"
                )
            return selected
        if excluded is not None:
            test = self._required_test_splitter()
            if (
                splitter.split_type.value == test.split_type.value
                or splitter.split_type == ValSplitByType.TRIAL
            ):
                candidates = [
                    key
                    for key in candidates
                    if not np.any((scope & (values == key)) & excluded)
                ]
            else:
                candidates = [
                    key
                    for key in candidates
                    if np.any((scope & (values == key)) & ~excluded)
                ]
        if desired <= 0:
            raise ValueError(
                f"{partition.title()} split must select at least one group"
            )
        if desired > len(candidates):
            if exact:
                raise ValueError(
                    f"{partition.title()} split cannot select requested groups"
                )
            desired = len(candidates)
        labels = self.epoch_data.get_label_list()
        all_labels = sorted(set(labels[scope].tolist()))
        label_positions = {label: index for index, label in enumerate(all_labels)}
        candidate_positions = {key: index for index, key in enumerate(candidates)}
        group_label_counts = np.zeros((len(candidates), len(all_labels)), dtype=int)
        effective_group_label_counts = np.zeros_like(group_label_counts)
        group_sizes = np.zeros(len(candidates), dtype=int)
        remaining_label_counts = np.zeros(len(all_labels), dtype=int)
        excluded_scope = np.zeros_like(scope) if excluded is None else excluded
        # The former implementation re-materialized a full row mask for every
        # proposed group at every greedy step.  Summarize the fixed scope once
        # instead: target values are disjoint, so subtracting one group's
        # non-excluded label counts is exactly the same class-coverage check.
        for value, label, is_excluded in zip(
            values[scope], labels[scope], excluded_scope[scope], strict=True
        ):
            label_position = label_positions[label]
            if not is_excluded:
                remaining_label_counts[label_position] += 1
            candidate_position = candidate_positions.get(int(value))
            if candidate_position is None:
                continue
            group_sizes[candidate_position] += 1
            group_label_counts[candidate_position, label_position] += 1
            if not is_excluded:
                effective_group_label_counts[candidate_position, label_position] += 1
        selected: list[int] = []
        selected_positions: set[int] = set()
        selected_label_counts = np.zeros(len(all_labels), dtype=int)
        candidate_ranks = np.asarray(
            [candidate_rank[key] for key in candidates], dtype=int
        )

        def select_if_class_complete(candidate_position: int) -> bool:
            nonlocal remaining_label_counts
            proposed_remaining = (
                remaining_label_counts
                - effective_group_label_counts[candidate_position]
            )
            if np.any(proposed_remaining <= 0):
                return False
            remaining_label_counts = proposed_remaining
            selected_label_counts[:] += group_label_counts[candidate_position]
            selected_positions.add(candidate_position)
            selected.append(candidates[candidate_position])
            return True

        # A paired retry must explore a different first admissible atomic
        # group, rather than merely use the rotated order as a final tie-break.
        # Normal materialization keeps the existing class-balanced selection.
        if candidate_offset and not select_if_class_complete(0):
            raise ValueError(
                f"{partition.title()} split is infeasible while preserving "
                "all training classes",
            )
        while len(selected) < desired:
            self._raise_if_interrupted()
            # Train class coverage is a hard admission constraint.  Vectorized
            # scoring keeps the exact greedy score tuple while making one
            # allocation boundary inexpensive enough for prompt cancellation.
            class_complete = np.all(
                remaining_label_counts - effective_group_label_counts > 0,
                axis=1,
            )
            if selected_positions:
                class_complete[list(selected_positions)] = False
            if not np.any(class_complete):
                raise ValueError(
                    f"{partition.title()} split is infeasible while preserving "
                    "all training classes",
                )
            proposed_label_counts = selected_label_counts + group_label_counts
            class_imbalance = np.ptp(proposed_label_counts, axis=1)
            admissible_positions = np.flatnonzero(class_complete)
            position = admissible_positions[
                np.lexsort(
                    (
                        candidate_ranks[admissible_positions],
                        group_sizes[admissible_positions],
                        class_imbalance[admissible_positions],
                    )
                )[0]
            ]
            select_if_class_complete(int(position))
        return selected

    def _paired_masks(self, scope: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Allocate non-CV test and validation together with bounded retries."""
        test = self._required_test_splitter()
        validation = self._active_validation_splitter()
        if validation is None:
            raise ValueError("Paired allocation requires validation")
        test_attempts = (
            1
            if test.get_split_unit() == SplitUnit.MANUAL
            else len(self._keys(test, scope))
        )
        validation_attempts = (
            1
            if validation.get_split_unit() == SplitUnit.MANUAL
            else len(self._keys(validation, scope))
        )
        attempt_count = min(32, test_attempts * validation_attempts)
        last_error: ValueError | None = None
        for (
            _score,
            test_count,
            validation_count,
        ) in self._paired_non_cv_count_candidates(scope):
            for attempt in range(max(1, attempt_count)):
                self._raise_if_interrupted()
                test_offset = attempt % test_attempts
                validation_offset = (attempt // test_attempts) % validation_attempts
                try:
                    test_keys = self._select_non_cv_keys(
                        test,
                        scope,
                        None,
                        "test",
                        requested_count=test_count,
                        candidate_offset=test_offset,
                    )
                    test_mask = self._mask_for_keys(test, scope, test_keys)
                    validation_keys = self._select_non_cv_keys(
                        validation,
                        scope,
                        test_mask,
                        "validation",
                        requested_count=validation_count,
                        candidate_offset=validation_offset,
                    )
                    validation_mask = (
                        self._mask_for_keys(
                            validation,
                            scope,
                            validation_keys,
                        )
                        & ~test_mask
                    )
                    remaining = scope & ~test_mask & ~validation_mask
                    labels = self.epoch_data.get_label_list()
                    if set(labels[remaining].tolist()) == set(labels[scope].tolist()):
                        return test_mask, validation_mask
                    last_error = ValueError(
                        "Training split is missing one or more classes"
                    )
                except ValueError as error:
                    if (
                        test.get_split_unit() == SplitUnit.MANUAL
                        and validation.get_split_unit() == SplitUnit.MANUAL
                        and "manual" in str(error).lower()
                    ):
                        raise
                    last_error = error
        raise ValueError(
            "Paired split is infeasible while preserving all training classes"
        ) from last_error

    def _validation_mask(self, scope: np.ndarray, test_mask: np.ndarray) -> np.ndarray:
        splitter = self._active_validation_splitter()
        if splitter is None:
            return np.zeros_like(scope)
        if self.config.is_cross_validation and splitter.get_split_unit() in (
            SplitUnit.MANUAL,
            SplitUnit.KFOLD,
        ):
            raise ValueError(
                "Cross-validation validation supports only Ratio or Number"
            )
        if (
            self.config.is_cross_validation
            and splitter.get_split_unit() == SplitUnit.RATIO
        ):
            requested_count, _exact = self._requested_count(splitter, scope)
            last_error: ValueError | None = None
            for candidate_count in range(requested_count, 0, -1):
                self._raise_if_interrupted()
                try:
                    selected = self._select_non_cv_keys(
                        splitter,
                        scope,
                        test_mask,
                        "validation",
                        requested_count=candidate_count,
                    )
                    return self._mask_for_keys(splitter, scope, selected) & ~test_mask
                except ValueError as error:
                    last_error = error
            raise ValueError(
                "Validation ratio is infeasible while preserving training classes"
            ) from last_error
        selected = self._select_non_cv_keys(
            splitter,
            scope,
            test_mask,
            "validation",
        )
        return self._mask_for_keys(splitter, scope, selected) & ~test_mask

    def _validate_partition(self, dataset: Dataset, scope: np.ndarray) -> None:
        if not dataset.test_mask.any() or not dataset.train_mask.any():
            raise ValueError("Test and train partitions must be non-empty")
        if (
            self._active_validation_splitter() is not None
            and not dataset.val_mask.any()
        ):
            raise ValueError("Validation partition must be non-empty")
        labels = self.epoch_data.get_label_list()
        if set(labels[dataset.train_mask].tolist()) != set(labels[scope].tolist()):
            raise ValueError("Training split is missing one or more classes")

    def generate(self) -> list[Dataset]:
        """Execute the dataset generation pipeline.

        Delegates to the appropriate handler based on the training type
        (individual or full-data scheme).

        Returns:
            List of generated datasets.

        Raises:
            ValueError: If the generator is not clean or no datasets were created.
            NotImplementedError: If an unsupported training type is encountered.

        """
        if not self.is_clean():
            raise ValueError(
                "Dataset generation is not clean. Reset the generator and try again.",
            )
        if self.datasets:
            return self.datasets
        committed_datasets = self.datasets
        pending_datasets: list[Dataset] = []
        initial_dataset_sequence = Dataset.SEQ
        evidence_reference = self.epoch_data.trial_selection_evidence
        initial_evidence = deepcopy(evidence_reference)
        initial_evidence_dropped = self.epoch_data.trial_selection_evidence_dropped
        self.datasets = pending_datasets
        try:
            Dataset.SEQ = 0
            self.epoch_data.reset_trial_selection_evidence()
            self._raise_if_interrupted()
            self._populate_pending_datasets()
        except BaseException:
            self.datasets = committed_datasets
            Dataset.SEQ = initial_dataset_sequence
            evidence_reference[:] = initial_evidence
            self.epoch_data.trial_selection_evidence = evidence_reference
            self.epoch_data.trial_selection_evidence_dropped = initial_evidence_dropped
            self.preview_failed = True
            raise
        else:
            committed_datasets.extend(pending_datasets)
            self.datasets = committed_datasets

        return self.datasets

    def _populate_pending_datasets(self) -> None:
        """Populate the transaction-local dataset list or fail before commit."""
        if self.config.train_type == TrainingType.IND:
            self.handle_ind()
        elif self.config.train_type == TrainingType.FULL:
            self.handle_full()
        else:
            raise NotImplementedError
        if not self.datasets:
            raise ValueError("No datasets were generated.")

    def set_interrupt(self) -> None:
        """Set the interrupt flag to break the dataset generation."""
        self.preview_failed = True
        self.interrupted = True

    def _raise_if_interrupted(self) -> None:
        """Stop at bounded allocation boundaries after an owner cancellation."""
        if self.interrupted:
            raise KeyboardInterrupt

    def prepare_result(self) -> list:
        """Generate datasets and filter out unselected ones.

        Returns:
            List of selected datasets.

        Raises:
            ValueError: If no valid datasets remain after filtering.

        """
        self.generate()
        # Filter out unselected datasets efficiently
        self.datasets = [d for d in self.datasets if d.is_selected]

        # check if dataset is empty
        if len(self.datasets) == 0:
            raise ValueError("No valid dataset is generated")
        self.done = True
        return self.datasets

    def is_clean(self) -> bool:
        """Check whether the generator is in a clean state for generation.

        Returns:
            True if the generator has completed or has not been interrupted.

        """
        return self.done or (not self.interrupted and not self.preview_failed)

    def reset(self) -> None:
        """Reset the dataset generator."""
        self.datasets = []
        self.interrupted = False
        self.preview_failed = False
        Dataset.SEQ = 0

    def apply(self, study: "Study") -> None:
        """Apply the generated datasets to the study.

        Args:
            study: Study instance to receive the generated datasets.

        Raises:
            TypeError: If study is not a valid Study instance.
            ValueError: If no valid datasets were generated.

        """
        from ..study import Study

        validate_type(study, Study, "study")
        self.prepare_result()
        study.set_datasets(self.datasets)
        study.dataset_generator = self
