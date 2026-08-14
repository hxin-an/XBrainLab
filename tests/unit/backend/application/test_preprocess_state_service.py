"""Focused contracts for the Study-owned Preprocess product port."""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Callable
from threading import Event, Thread
from typing import Any

import mne
import numpy as np
import pytest

from XBrainLab.backend.application import (
    ApplicationService,
    PreprocessCommand,
    PreprocessOperation,
)
from XBrainLab.backend.application.owned_work import (
    OwnedOperationCancelledError,
    OwnedWorkKind,
    OwnedWorkPhase,
    OwnedWorkRegistry,
)
from XBrainLab.backend.controller.preprocess_controller import PreprocessController
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.services.dataset_state_service import DatasetStateService
from XBrainLab.backend.services.preprocess_state_service import PreprocessStateService
from XBrainLab.backend.study import Study


class _Row:
    def __init__(self, history: list[str] | None = None) -> None:
        self.history = list(history or [])

    def copy(self) -> _Row:
        return _Row(self.history)


def _processor(label: str, *, fail: bool = False) -> type[Any]:
    class _Processor:
        def __init__(self, rows: list[_Row]) -> None:
            self.rows = rows

        def data_preprocess(self, *_args: Any, **_kwargs: Any) -> list[_Row]:
            for row in self.rows:
                row.history.append(label)
            if fail:
                raise RuntimeError(f"{label} failed")
            return self.rows

    return _Processor


class _Study:
    def __init__(self) -> None:
        self.preprocessed_data_list: list[Any] = [_Row(["loaded"])]
        self.commits: list[list[Any]] = []

    def set_preprocessed_data_list(
        self,
        preprocessed_data_list: list[Any],
        force_update: bool = False,
    ) -> None:
        assert force_update is True
        self.preprocessed_data_list = preprocessed_data_list
        self.commits.append(preprocessed_data_list)

    def reset_preprocess(self, force_update: bool = False) -> None:
        assert force_update is True

    def lock_dataset(self) -> None:
        pass

    def set_channels(
        self,
        chs: list[str],
        positions: list[tuple],
    ) -> None:
        del chs, positions


def test_preprocess_state_service_preserves_atomic_standard_pipeline() -> None:
    study = _Study()
    original = study.preprocessed_data_list
    notifications: list[str] = []
    processors = {
        "Filtering": _processor("filter"),
        "Resample": _processor("resample", fail=True),
    }
    service = PreprocessStateService(
        study,
        processor_provider=processors.__getitem__,
    )
    service.subscribe("preprocess_changed", lambda: notifications.append("changed"))

    try:
        service.apply_standard_pipeline(
            l_freq=4,
            h_freq=40,
            rate=128,
        )
    except RuntimeError as exc:
        assert str(exc) == "resample failed"
    else:
        raise AssertionError("Expected the failing processor to abort the recipe")

    assert study.preprocessed_data_list is original
    assert original[0].history == ["loaded"]
    assert study.commits == []
    assert notifications == []


def test_preprocess_state_service_commits_and_publishes_once() -> None:
    study = _Study()
    notifications: list[str] = []
    processors = {
        "Filtering": _processor("filter"),
        "Resample": _processor("resample"),
        "Rereference": _processor("rereference"),
        "Normalize": _processor("normalize"),
    }
    service = PreprocessStateService(
        study,
        processor_provider=processors.__getitem__,
    )
    service.subscribe("preprocess_changed", lambda: notifications.append("changed"))

    assert service.apply_standard_pipeline(
        l_freq=4,
        h_freq=40,
        notch_freq=60,
        rate=128,
        ref_channels="average",
        normalization="z score",
    )

    assert len(study.commits) == 1
    assert study.preprocessed_data_list[0].history == [
        "loaded",
        "filter",
        "filter",
        "resample",
        "rereference",
        "normalize",
    ]
    assert notifications == ["changed"]


def test_preprocess_prepare_is_detached_until_explicit_commit() -> None:
    study = _Study()
    original = study.preprocessed_data_list
    notifications: list[str] = []
    service = PreprocessStateService(
        study,
        processor_provider={"Normalize": _processor("normalize")}.__getitem__,
    )
    service.subscribe("preprocess_changed", lambda: notifications.append("changed"))

    prepared = service.prepare_normalization("z score")

    assert study.preprocessed_data_list is original
    assert original[0].history == ["loaded"]
    assert study.commits == []
    assert notifications == []
    assert prepared.source_identity == (id(original[0]),)
    assert prepared.data[0].history == ["loaded", "normalize"]

    assert service.commit_prepared(prepared) is True

    assert study.preprocessed_data_list is not original
    assert study.preprocessed_data_list[0].history == ["loaded", "normalize"]
    assert len(study.commits) == 1
    assert notifications == ["changed"]


def test_every_preprocess_prepare_path_is_structurally_publication_free() -> None:
    tree = ast.parse(textwrap.dedent(inspect.getsource(PreprocessStateService)))
    prepare_functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and (node.name.startswith("prepare_") or node.name == "_prepare_processor")
    }
    expected = {
        "prepare_epoching",
        "prepare_filter",
        "prepare_normalization",
        "prepare_resample",
        "prepare_rereference",
        "prepare_standard_pipeline",
        "_prepare_processor",
    }

    assert expected <= set(prepare_functions)
    for name in expected:
        called = {
            node.func.attr
            for node in ast.walk(prepare_functions[name])
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        } | {
            node.func.id
            for node in ast.walk(prepare_functions[name])
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert called.isdisjoint(
            {
                "commit_prepared",
                "lock_dataset",
                "owned_work_commit_boundary",
                "publish_preprocess_changed",
                "set_preprocessed_data_list",
            }
        ), name


def test_channel_selection_prepare_is_structurally_publication_free() -> None:
    prepare_tree = ast.parse(
        textwrap.dedent(
            inspect.getsource(DatasetStateService.prepare_channel_selection)
        )
    )
    commit_tree = ast.parse(
        textwrap.dedent(
            inspect.getsource(DatasetStateService.commit_prepared_channel_selection)
        )
    )
    prepare_calls = {
        node.func.attr
        for node in ast.walk(prepare_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    } | {
        node.func.id
        for node in ast.walk(prepare_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    commit_calls = {
        node.func.attr
        for node in ast.walk(commit_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    } | {
        node.func.id
        for node in ast.walk(commit_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert prepare_calls.isdisjoint(
        {
            "lock_dataset",
            "owned_work_commit_boundary",
            "set_loaded_data_list",
        }
    )
    assert "owned_work_commit_boundary" in commit_calls
    assert "set_loaded_data_list" in commit_calls
    assert "lock_dataset" in commit_calls


@pytest.mark.parametrize(
    ("operation_kind", "invoke", "expected_dataset_locked"),
    [
        (
            OwnedWorkKind.PREPROCESS,
            lambda service: service.apply_filter(4.0, 40.0),
            False,
        ),
        (
            OwnedWorkKind.EPOCH,
            lambda service: service.apply_epoching(None, None, -0.1, 0.5),
            True,
        ),
    ],
    ids=("preprocess", "epoch"),
)
def test_cancellation_before_commit_preserves_state_and_can_retry(
    operation_kind: OwnedWorkKind,
    invoke: Callable[[PreprocessStateService], bool],
    expected_dataset_locked: bool,
) -> None:
    study = Study()
    rows: list[Raw] = []
    for index in range(3):
        raw = Raw(
            f"recording-{index}.fif",
            mne.io.RawArray(
                np.zeros((1, 100)),
                mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg"),
                verbose="ERROR",
            ),
        )
        raw.add_preprocess(f"loaded-{index}")
        rows.append(raw)
    study.set_loaded_data_list(rows, force_update=True)
    original = study.preprocessed_data_list
    processing_finished = Event()
    release_processing = Event()
    should_block = Event()
    should_block.set()

    class _CancellableProcessor:
        def __init__(self, rows: list[Raw]) -> None:
            self.rows = rows

        def data_preprocess(self, *_args: Any, **_kwargs: Any) -> list[Raw]:
            for row in self.rows:
                row.add_preprocess("processed")
            if should_block.is_set():
                processing_finished.set()
                assert release_processing.wait(timeout=2.0)
            return self.rows

    service = PreprocessStateService(
        study,
        processor_provider=lambda _name: _CancellableProcessor,
    )
    notifications: list[str] = []
    service.subscribe("preprocess_changed", lambda: notifications.append("changed"))
    registry = OwnedWorkRegistry()
    operation = registry.begin(operation_kind, cancellable=True)
    cancellation_errors: list[OwnedOperationCancelledError] = []
    thread_errors: list[BaseException] = []

    def run_cancelled_attempt() -> None:
        try:
            with registry.bind(operation.operation_id):
                registry.start(operation.operation_id)
                invoke(service)
        except OwnedOperationCancelledError as exc:
            cancellation_errors.append(exc)
        except BaseException as exc:
            thread_errors.append(exc)

    worker = Thread(target=run_cancelled_attempt, daemon=True)
    worker.start()
    assert processing_finished.wait(timeout=2.0)
    assert registry.cancel(operation.operation_id) is True
    release_processing.set()
    worker.join(timeout=2.0)

    assert not worker.is_alive()
    assert thread_errors == []
    assert len(cancellation_errors) == 1
    assert registry.snapshot(operation.operation_id).phase is OwnedWorkPhase.CANCELLED
    assert study.preprocessed_data_list is original
    assert [row.get_preprocess_history() for row in original] == [
        ["loaded-0"],
        ["loaded-1"],
        ["loaded-2"],
    ]
    assert study.dataset_locked is False
    assert notifications == []

    should_block.clear()
    retry = registry.begin(operation_kind, cancellable=True)
    with registry.bind(retry.operation_id):
        registry.start(retry.operation_id)
        assert invoke(service) is True
        registry.complete(retry.operation_id)

    assert registry.snapshot(retry.operation_id).phase is OwnedWorkPhase.COMPLETED
    assert study.preprocessed_data_list is not original
    assert [row.get_preprocess_history() for row in study.preprocessed_data_list] == [
        ["loaded-0", "processed"],
        ["loaded-1", "processed"],
        ["loaded-2", "processed"],
    ]
    assert study.dataset_locked is expected_dataset_locked
    assert notifications == ["changed"]


def test_cancel_after_commit_admission_is_rejected_and_commit_completes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    study = Study()
    raw = Raw(
        "recording.fif",
        mne.io.RawArray(
            np.zeros((1, 100)),
            mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg"),
            verbose="ERROR",
        ),
    )
    raw.add_preprocess("loaded")
    study.set_loaded_data_list([raw], force_update=True)
    original = study.preprocessed_data_list
    commit_admitted = Event()
    release_commit = Event()
    original_commit = study.set_preprocessed_data_list

    def _blocking_commit(rows: list[Raw], force_update: bool = False) -> None:
        commit_admitted.set()
        assert release_commit.wait(timeout=2.0)
        original_commit(rows, force_update=force_update)

    monkeypatch.setattr(study, "set_preprocessed_data_list", _blocking_commit)

    class _Processor:
        def __init__(self, rows: list[Raw]) -> None:
            self.rows = rows

        def data_preprocess(self, *_args: Any, **_kwargs: Any) -> list[Raw]:
            for row in self.rows:
                row.add_preprocess("processed")
            return self.rows

    service = PreprocessStateService(
        study,
        processor_provider=lambda _name: _Processor,
    )
    registry = OwnedWorkRegistry()
    operation = registry.begin(OwnedWorkKind.PREPROCESS, cancellable=True)
    thread_errors: list[BaseException] = []

    def _run() -> None:
        try:
            with registry.bind(operation.operation_id):
                registry.start(operation.operation_id)
                assert service.apply_filter(4.0, 40.0) is True
                registry.complete(operation.operation_id)
        except BaseException as exc:
            thread_errors.append(exc)

    worker = Thread(target=_run, daemon=True)
    worker.start()
    assert commit_admitted.wait(timeout=2.0)

    assert registry.snapshot(operation.operation_id).cancellable is False
    assert registry.cancel(operation.operation_id) is False
    assert study.preprocessed_data_list is original

    release_commit.set()
    worker.join(timeout=2.0)

    assert not worker.is_alive()
    assert thread_errors == []
    assert registry.snapshot(operation.operation_id).phase is OwnedWorkPhase.COMPLETED
    assert study.preprocessed_data_list is not original
    assert study.preprocessed_data_list[0].get_preprocess_history() == [
        "loaded",
        "processed",
    ]


def test_application_preprocess_composition_never_resolves_controller(
    monkeypatch,
) -> None:
    study = Study()
    original_get_controller = study.get_controller
    resolved_names: list[str] = []

    def reject_preprocess_controller(name: str) -> Any:
        resolved_names.append(name)
        if name == "preprocess":
            raise AssertionError("Application composition resolved a UI controller")
        return original_get_controller(name)

    monkeypatch.setattr(study, "get_controller", reject_preprocess_controller)

    service = ApplicationService(study)
    result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.BANDPASS,
            low_freq=4,
            high_freq=40,
        )
    )

    assert result.failed is True
    assert service.preprocess is study.preprocess_state_service
    assert "preprocess" not in resolved_names


def test_preprocess_controller_relays_shared_service_publication_once() -> None:
    study = Study()
    controller = PreprocessController(study)
    notifications: list[str] = []
    controller.subscribe("preprocess_changed", lambda: notifications.append("changed"))

    study.preprocess_state_service.reset_preprocess()

    assert notifications == ["changed"]
