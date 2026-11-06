"""Dataset generator module for creating train/val/test splits from epoch data."""

from collections.abc import Callable, Iterator
from typing import NoReturn
from uuid import uuid4

import numpy as np

from ..utils import validate_type
from ..utils.filesystem_identity import validate_filesystem_metadata
from .data_splitter import DataSplittingConfig
from .dataset import Dataset, Epochs
from .option import (
    VALIDATION_SPLIT_TYPES,
    SplitByType,
    SplitUnit,
    TrainingType,
    ValSplitByType,
)

MAX_CV_LOCAL_REPAIR_ATTEMPTS = 256


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
        validation = self._active_validation_splitter()
        if (
            self.config.train_type == TrainingType.IND
            and test_splitter.split_type == SplitByType.SUBJECT
        ):
            raise ValueError("Individual training cannot split by Subject")
        if (
            validation is not None
            and validation.split_type.value
            not in (VALIDATION_SPLIT_TYPES[test_splitter.split_type.value])
        ):
            raise ValueError("Validation must use the same or a finer unit than Test")
        scopes = (
            [scope]
            if test_splitter.split_type == SplitByType.SUBJECT
            else self._subject_scopes(scope)
        )
        combined_folds: list[tuple[np.ndarray, np.ndarray]] = []
        for allocation_scope in scopes:
            try:
                subject_folds = self._scope_folds(test_splitter, allocation_scope)
            except ValueError as error:
                self._raise_scope_error(allocation_scope, error)
            if not combined_folds:
                combined_folds = subject_folds
            else:
                for (test, validation), (subject_test, subject_validation) in zip(
                    combined_folds, subject_folds, strict=True
                ):
                    np.logical_or(test, subject_test, out=test)
                    np.logical_or(validation, subject_validation, out=validation)
        cross_validation_cohort_id = (
            uuid4().hex if self.config.is_cross_validation else None
        )
        for group_idx, (test_mask, validation_mask) in enumerate(combined_folds):
            self._raise_if_interrupted()
            dataset = Dataset(self.epoch_data, self.config)
            dataset.set_name(f"{name_prefix}_{group_idx}")
            if cross_validation_cohort_id is not None:
                dataset.set_cross_validation_cohort_id(cross_validation_cohort_id)
            if dataset_hook:
                dataset_hook(dataset)
            dataset.set_test(test_mask)
            if validation_mask.any():
                dataset.set_val(validation_mask)
            dataset.set_remaining_to_train()
            self._validate_partition(dataset, scope)
            self.datasets.append(dataset)

    def _subject_scopes(self, scope: np.ndarray) -> Iterator[np.ndarray]:
        subjects = self.epoch_data.get_subject_list()
        for subject in np.unique(subjects[scope]):
            self._raise_if_interrupted()
            yield scope & (subjects == subject)

    def _raise_scope_error(self, scope: np.ndarray, error: ValueError) -> NoReturn:
        subjects = np.unique(self.epoch_data.get_subject_list()[scope])
        context = (
            f"Subject {self.epoch_data.get_subject_name(int(subjects[0]))}"
            if len(subjects) == 1
            else "Full subject scope"
        )
        raise ValueError(f"{context}: {error}") from error

    def _scope_folds(
        self, splitter, scope: np.ndarray
    ) -> list[tuple[np.ndarray, np.ndarray]]:
        fold_count = self._fold_count(splitter, scope)
        if fold_count == 1 and self._active_validation_splitter() is not None:
            folds = [self._paired_masks(scope)]
        else:
            folds = [
                (test, self._validation_mask(scope, test))
                for test in self._test_folds(splitter, scope, fold_count)
            ]
        labels = self.epoch_data.get_label_list()
        for test, validation in folds:
            train = scope & ~test & ~validation
            if not test.any() or not train.any():
                raise ValueError("Test and train partitions must be non-empty")
            if set(labels[train].tolist()) != set(labels[scope].tolist()):
                raise ValueError("Training split is missing one or more classes")
        return folds

    def _ordered_keys(self, splitter, scope: np.ndarray) -> list[int]:
        subjects = self.epoch_data.get_subject_list()[scope]
        seed = np.random.SeedSequence([self.config.seed, int(subjects.min())])
        return (
            np.random.default_rng(seed)
            .permutation(self._keys(splitter, scope))
            .tolist()
        )

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
            # Allocation scopes isolate subjects; equal labels on different
            # subjects never force them into the same partition. Runs are not sessions.
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
        keys = self._ordered_keys(splitter, scope)
        if fold_count == 1:
            selected = self._select_with_retries(splitter, scope, None, "test")
            return [self._mask_for_keys(splitter, scope, selected)]
        # Keep exact group capacities while minimizing deviation from the
        # source class proportions. Seeded group order settles remaining ties.
        # Feasibility repair below remains bounded; this is not a solver.
        base, remainder = divmod(len(keys), fold_count)
        capacities = [base + int(index < remainder) for index in range(fold_count)]
        partitions: list[list[int]] = [[] for _ in range(fold_count)]
        label_counts: list[dict[int, int]] = [{} for _ in range(fold_count)]
        labels = self.epoch_data.get_label_list()
        source_labels, source_counts = np.unique(labels[scope], return_counts=True)
        proportions = source_counts / source_counts.sum()
        for key in keys:
            self._raise_if_interrupted()
            group_labels = labels[self._mask_for_keys(splitter, scope, [key])]
            choices = [
                index
                for index in range(fold_count)
                if len(partitions[index]) < capacities[index]
            ]
            group_counts = np.asarray(
                [np.count_nonzero(group_labels == label) for label in source_labels]
            )

            scores = []
            for index in choices:
                proposed = group_counts + np.asarray(
                    [label_counts[index].get(int(label), 0) for label in source_labels]
                )
                deviation = float(np.abs(proposed - proposed.sum() * proportions).sum())
                scores.append((deviation, len(partitions[index]), index))

            fold_index = min(scores)[2]
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

    def _requested_count(self, splitter, scope: np.ndarray) -> int:
        total = len(self._keys(splitter, scope))
        unit = splitter.get_split_unit()
        if unit == SplitUnit.NUMBER:
            count = int(splitter.get_value())
        elif unit == SplitUnit.RATIO:
            count = max(1, int(float(splitter.get_value()) * total))
        else:
            raise ValueError("Only Ratio and Number are valid outside K Fold")
        if count >= total:
            raise ValueError(
                f"Requested {count} groups but scope contains {total}; "
                "train must retain at least one group"
            )
        return count

    def _selection_offsets(
        self,
        splitter,
        scope: np.ndarray,
        excluded: np.ndarray | None = None,
    ) -> list[int]:
        """Try distinct class supports before spending retries on equivalent starts."""
        values = self._target_values(splitter)
        candidates = self._ordered_keys(splitter, scope)
        if excluded is not None:
            blocked_keys = set(values[scope & excluded].tolist())
            candidates = [key for key in candidates if key not in blocked_keys]
        supports: dict[int, set[int]] = {key: set() for key in candidates}
        labels = self.epoch_data.get_label_list()
        for key, label in zip(values[scope], labels[scope], strict=True):
            if int(key) in supports:
                supports[int(key)].add(int(label))
        seen = set()
        diverse, repeated = [], []
        for index, key in enumerate(candidates):
            support = frozenset(supports[key])
            # Zero means the ordinary proportional greedy pass; len(candidates)
            # forces the first seeded key after rotating back to its position.
            offset = index or len(candidates)
            if support in seen:
                repeated.append(offset)
            else:
                diverse.append(offset)
                seen.add(support)
        return [0, *diverse, *repeated][:32]

    def _select_with_retries(
        self,
        splitter,
        scope: np.ndarray,
        excluded: np.ndarray | None,
        partition: str,
        requested_count: int | None = None,
    ) -> list[int]:
        last_error = None
        for offset in self._selection_offsets(splitter, scope, excluded):
            self._raise_if_interrupted()
            try:
                return self._select_non_cv_keys(
                    splitter,
                    scope,
                    excluded,
                    partition,
                    requested_count=requested_count,
                    candidate_offset=offset,
                )
            except ValueError as error:
                last_error = error
        raise ValueError(
            f"{partition.title()} split is infeasible at the requested group count "
            f"while preserving all training classes: {last_error}"
        ) from last_error

    def _select_non_cv_keys(
        self,
        splitter,
        scope: np.ndarray,
        excluded: np.ndarray | None,
        partition: str,
        requested_count: int | None = None,
        candidate_offset: int = 0,
    ) -> list[int]:
        desired = (
            self._requested_count(splitter, scope)
            if requested_count is None
            else requested_count
        )
        values = self._target_values(splitter)
        candidates = self._ordered_keys(splitter, scope)
        if excluded is not None:
            blocked_keys = set(values[scope & excluded].tolist())
            candidates = [key for key in candidates if key not in blocked_keys]
        if candidates and candidate_offset:
            offset = candidate_offset % len(candidates)
            candidates = candidates[offset:] + candidates[:offset]
        candidate_rank = {key: index for index, key in enumerate(candidates)}
        if desired <= 0 or desired >= len(candidates):
            raise ValueError(
                f"{partition.title()} cannot allocate {desired} of "
                f"{len(candidates)} available groups and keep train non-empty"
            )
        labels = self.epoch_data.get_label_list()
        all_labels = sorted(set(labels[scope].tolist()))
        label_positions = {label: index for index, label in enumerate(all_labels)}
        candidate_positions = {key: index for index, key in enumerate(candidates)}
        group_label_counts = np.zeros((len(candidates), len(all_labels)), dtype=int)
        group_sizes = np.zeros(len(candidates), dtype=int)
        remaining_label_counts = np.zeros(len(all_labels), dtype=int)
        excluded_scope = np.zeros_like(scope) if excluded is None else excluded
        # Summarize once: candidates are disjoint and never overlap Test.
        # Subtracting their counts checks train class coverage without rebuilding
        # one full epoch mask per candidate at every allocation step.
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
        selected: list[int] = []
        selected_positions: set[int] = set()
        selected_label_counts = np.zeros(len(all_labels), dtype=int)
        candidate_ranks = np.asarray(
            [candidate_rank[key] for key in candidates], dtype=int
        )
        # Same-unit validation retains the original source distribution; finer
        # validation receives a remainder scope from _validation_mask.
        _, source_counts = np.unique(labels[scope], return_counts=True)
        source_proportions = source_counts / source_counts.sum()

        def select_if_class_complete(candidate_position: int) -> bool:
            nonlocal remaining_label_counts
            proposed_remaining = (
                remaining_label_counts - group_label_counts[candidate_position]
            )
            if np.any(proposed_remaining <= 0):
                return False
            remaining_label_counts = proposed_remaining
            selected_label_counts[:] += group_label_counts[candidate_position]
            selected_positions.add(candidate_position)
            selected.append(candidates[candidate_position])
            return True

        # Retry a different first group when proportional greedy selection gets
        # stuck. Counts stay fixed; this is a bounded repair, not a solver.
        if candidate_offset and not select_if_class_complete(0):
            raise ValueError(
                f"{partition.title()} split is infeasible while preserving "
                "all training classes",
            )
        while len(selected) < desired:
            self._raise_if_interrupted()
            # Train class coverage is a hard admission constraint.  Vectorized
            # scoring preserves source class proportions while allowing prompt
            # cancellation at each allocation boundary.
            class_complete = np.all(
                remaining_label_counts - group_label_counts > 0,
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
            expected_counts = (
                proposed_label_counts.sum(axis=1, keepdims=True) * source_proportions
            )
            class_imbalance = np.abs(proposed_label_counts - expected_counts).sum(
                axis=1
            )
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
        """Retry group choices with fixed targets; never change requested ratios."""
        test = self._required_test_splitter()
        validation = self._active_validation_splitter()
        if validation is None:
            raise ValueError("Paired allocation requires validation")
        test_count = self._requested_count(test, scope)
        same_unit = test.split_type.value == validation.split_type.value
        if same_unit:
            validation_count = self._requested_count(validation, scope)
            if test_count + validation_count >= len(self._keys(test, scope)):
                raise ValueError(
                    "Requested test and validation groups cannot leave non-empty train"
                )
        last_error = None
        for offset in self._selection_offsets(test, scope):
            self._raise_if_interrupted()
            try:
                test_keys = self._select_non_cv_keys(
                    test,
                    scope,
                    None,
                    "test",
                    requested_count=test_count,
                    candidate_offset=offset,
                )
                test_mask = self._mask_for_keys(test, scope, test_keys)
                return test_mask, self._validation_mask(scope, test_mask)
            except ValueError as error:
                last_error = error
        raise ValueError(
            "Test / validation split is infeasible at the requested group counts "
            f"while preserving all training classes: {last_error}"
        ) from last_error

    def _validation_mask(self, scope: np.ndarray, test_mask: np.ndarray) -> np.ndarray:
        splitter = self._active_validation_splitter()
        if splitter is None:
            return np.zeros_like(scope)
        if splitter.get_split_unit() not in (SplitUnit.RATIO, SplitUnit.NUMBER):
            raise ValueError("Validation supports only Ratio or Number")
        test = self._required_test_splitter()
        same_unit = splitter.split_type.value == test.split_type.value
        remainder = scope & ~test_mask
        # A finer validation unit counts the remaining data. Under Subject Test,
        # Trial / Session validation still owns one independent scope per person.
        scopes = (
            self._subject_scopes(remainder)
            if test.split_type == SplitByType.SUBJECT and not same_unit
            else [scope if same_unit else remainder]
        )
        result = np.zeros_like(scope)
        for validation_scope in scopes:
            try:
                selected = self._select_with_retries(
                    splitter,
                    validation_scope,
                    test_mask,
                    "validation",
                )
            except ValueError as error:
                self._raise_scope_error(validation_scope, error)
            result |= self._mask_for_keys(splitter, validation_scope, selected)
        if not result.any():
            raise ValueError("Validation partition must be non-empty")
        return result

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
        self.datasets = pending_datasets
        try:
            Dataset.SEQ = 0
            self._raise_if_interrupted()
            self._populate_pending_datasets()
        except BaseException:
            self.datasets = committed_datasets
            Dataset.SEQ = initial_dataset_sequence
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
