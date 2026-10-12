"""Public preprocessing command admission, cancellation and transaction tests."""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from threading import Event, Thread
from typing import Any, cast
from unittest.mock import MagicMock, patch

import mne
import numpy as np
import pytest

from tests.unit.backend.application.preprocess_test_support import (
    _apply_reviewed_epoch_fixture,
    _minimal_raw,
    _write_reviewed_epoch_fixture,
)
from XBrainLab.backend.application import (
    ApplicationService,
    ApplyMontageCommand,
    ChangedState,
    CommandResult,
    CreateEpochCommand,
    ErrorType,
    PreprocessCommand,
    PreprocessOperation,
    UpdateMetadataCommand,
)
from XBrainLab.backend.application.bids_montage_preparation import (
    MontagePreparationSnapshot,
)
from XBrainLab.backend.application.owned_work import OwnedWorkPhase
from XBrainLab.backend.application.preprocess_preparation import (
    ApplicationPreprocessBoundary,
)
from XBrainLab.backend.application.resource_guard import (
    ResourceChecker,
    ResourceCheckResult,
)
from XBrainLab.backend.exceptions import StaleTrainingPipelineMutationError
from XBrainLab.backend.load_data.raw import Raw
from XBrainLab.backend.preprocessor.channel_selection import ChannelSelection
from XBrainLab.backend.preprocessor.normalize import Normalize
from XBrainLab.backend.preprocessor.time_epoch import TimeEpoch
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import Trainer

THREAD_WATCHDOG_SECONDS = 5.0


@pytest.mark.parametrize("frequency", (50.0, 60.0))
def test_notch_at_or_above_lowest_source_nyquist_preserves_pipeline(
    frequency: float,
) -> None:
    study = Study()
    raw = _minimal_raw(Path("low-rate-recording.fif"), sfreq=100.0)
    study.set_loaded_data_list([raw], force_update=True)
    service = ApplicationService(study)
    before = service.get_view_publication()
    original_data = study.preprocessed_data_list
    prepare_filter = MagicMock(wraps=service.preprocess.prepare_filter)
    service.preprocess.prepare_filter = prepare_filter
    commit_prepared = MagicMock(wraps=service.preprocess.commit_prepared)
    service.preprocess.commit_prepared = commit_prepared

    result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.NOTCH,
            notch_freq=frequency,
        )
    )

    assert result.failed
    assert result.error_type is ErrorType.PRECONDITION
    assert f"{frequency:g} Hz" in result.message
    assert "100 Hz" in result.message
    assert "Nyquist limit 50 Hz" in result.message
    assert "reset preprocessing" in result.message.lower()
    assert result.changed_state == ChangedState(error_changed=True)
    assert result.state.pipeline_stage == before.state.pipeline_stage
    assert result.state.raw == before.state.raw
    assert result.state.preprocessed == before.state.preprocessed
    assert result.state.epoch == before.state.epoch
    assert result.diagnostics["code"] == "notch_frequency_at_or_above_nyquist"
    assert result.diagnostics["requested_frequency"] == frequency
    assert result.diagnostics["sampling_rate"] == 100.0
    assert result.diagnostics["nyquist"] == 50.0
    assert result.diagnostics["state_preserved"] is True
    assert prepare_filter.call_count == 0
    assert commit_prepared.call_count == 0
    assert study.preprocessed_data_list is original_data
    assert raw.get_preprocess_history() == []


def test_notch_below_lowest_source_nyquist_uses_existing_prepare_and_commit() -> None:
    study = Study()
    raw = _minimal_raw(Path("low-rate-recording.fif"), sfreq=100.0)
    study.set_loaded_data_list([raw], force_update=True)
    service = ApplicationService(study)
    prepare_filter = MagicMock(wraps=service.preprocess.prepare_filter)
    service.preprocess.prepare_filter = prepare_filter
    commit_prepared = MagicMock(wraps=service.preprocess.commit_prepared)
    service.preprocess.commit_prepared = commit_prepared

    result = service.execute(
        PreprocessCommand(operation=PreprocessOperation.NOTCH, notch_freq=40.0)
    )

    assert result.ok
    assert prepare_filter.call_count == 1
    assert commit_prepared.call_count == 1
    assert (
        "notch 40 hz"
        in study.preprocessed_data_list[0].get_preprocess_history()[-1].lower()
    )


@pytest.mark.parametrize("frequency", (50.0, 60.0))
def test_bandpass_at_or_above_lowest_source_nyquist_preserves_pipeline(
    frequency: float,
) -> None:
    """Reject cutoffs before detached filtering can mutate the pipeline."""
    study = Study()
    raw = _minimal_raw(Path("low-rate-recording.fif"), sfreq=100.0)
    study.set_loaded_data_list([raw], force_update=True)
    service = ApplicationService(study)
    before = service.get_view_publication()
    original_data = study.preprocessed_data_list
    prepare_filter = MagicMock(wraps=service.preprocess.prepare_filter)
    service.preprocess.prepare_filter = prepare_filter
    commit_prepared = MagicMock(wraps=service.preprocess.commit_prepared)
    service.preprocess.commit_prepared = commit_prepared

    result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.BANDPASS,
            low_freq=1.0,
            high_freq=frequency,
        )
    )

    assert result.failed
    assert result.error_type is ErrorType.PRECONDITION
    assert f"{frequency:g} Hz" in result.message
    assert "100 Hz" in result.message
    assert "Nyquist limit 50 Hz" in result.message
    assert "reset preprocessing" in result.message.lower()
    assert result.changed_state == ChangedState(error_changed=True)
    assert result.state.pipeline_stage == before.state.pipeline_stage
    assert result.state.raw == before.state.raw
    assert result.state.preprocessed == before.state.preprocessed
    assert result.state.epoch == before.state.epoch
    assert result.diagnostics["code"] == "bandpass_high_frequency_at_or_above_nyquist"
    assert result.diagnostics["requested_frequency"] == frequency
    assert result.diagnostics["sampling_rate"] == 100.0
    assert result.diagnostics["nyquist"] == 50.0
    assert result.diagnostics["state_preserved"] is True
    assert prepare_filter.call_count == 0
    assert commit_prepared.call_count == 0
    assert study.preprocessed_data_list is original_data
    assert raw.get_preprocess_history() == []


def test_bandpass_uses_lowest_reliable_sampling_rate_across_recordings() -> None:
    study = Study()
    high_rate = _minimal_raw(Path("high-rate.fif"), sfreq=200.0)
    low_rate = _minimal_raw(Path("low-rate.fif"), sfreq=100.0)
    study.set_loaded_data_list([high_rate, low_rate], force_update=True)
    service = ApplicationService(study)

    result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.BANDPASS,
            low_freq=1.0,
            high_freq=60.0,
        )
    )

    assert result.failed
    assert result.error_type is ErrorType.PRECONDITION
    assert result.diagnostics["requested_frequency"] == 60.0
    assert result.diagnostics["sampling_rate"] == 100.0
    assert result.diagnostics["nyquist"] == 50.0
    assert high_rate.get_preprocess_history() == []
    assert low_rate.get_preprocess_history() == []


def test_bandpass_uses_the_resampled_rate_for_its_nyquist_limit() -> None:
    study = Study()
    raw = _minimal_raw(Path("resampled-recording.fif"), sfreq=200.0)
    study.set_loaded_data_list([raw], force_update=True)
    service = ApplicationService(study)

    assert service.execute(
        PreprocessCommand(operation=PreprocessOperation.RESAMPLE, rate=100.0)
    ).ok
    resampled_data = study.preprocessed_data_list
    resampled_history = list(resampled_data[0].get_preprocess_history())
    result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.BANDPASS,
            low_freq=1.0,
            high_freq=50.0,
        )
    )

    assert result.failed
    assert result.error_type is ErrorType.PRECONDITION
    assert result.diagnostics["sampling_rate"] == 100.0
    assert result.diagnostics["nyquist"] == 50.0
    assert study.preprocessed_data_list is resampled_data
    assert study.preprocessed_data_list[0].get_preprocess_history() == resampled_history


def test_bandpass_below_lowest_source_nyquist_uses_existing_prepare_and_commit() -> (
    None
):
    study = Study()
    raw = _minimal_raw(Path("low-rate-recording.fif"), sfreq=100.0)
    study.set_loaded_data_list([raw], force_update=True)
    service = ApplicationService(study)

    result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.BANDPASS,
            low_freq=1.0,
            high_freq=40.0,
        )
    )

    assert result.ok
    assert (
        "filtering 1.0 ~ 40.0 hz"
        in study.preprocessed_data_list[0].get_preprocess_history()[-1].lower()
    )


def test_notch_uses_lowest_reliable_sampling_rate_across_recordings() -> None:
    study = Study()
    high_rate = _minimal_raw(Path("high-rate.fif"), sfreq=200.0)
    low_rate = _minimal_raw(Path("low-rate.fif"), sfreq=100.0)
    study.set_loaded_data_list([high_rate, low_rate], force_update=True)
    service = ApplicationService(study)

    result = service.execute(
        PreprocessCommand(operation=PreprocessOperation.NOTCH, notch_freq=60.0)
    )

    assert result.failed
    assert result.error_type is ErrorType.PRECONDITION
    assert result.diagnostics["requested_frequency"] == 60.0
    assert result.diagnostics["sampling_rate"] == 100.0
    assert result.diagnostics["nyquist"] == 50.0
    assert high_rate.get_preprocess_history() == []
    assert low_rate.get_preprocess_history() == []


def test_notch_skips_unreadable_sampling_rate_and_uses_existing_prepare_path() -> None:
    study = Study()
    raw = _minimal_raw(Path("unreadable-rate.fif"), sfreq=100.0)
    raw.get_sfreq = MagicMock(side_effect=RuntimeError("unreadable sampling rate"))
    study.set_loaded_data_list([raw], force_update=True)
    service = ApplicationService(study)
    prepare_filter = MagicMock(wraps=service.preprocess.prepare_filter)
    service.preprocess.prepare_filter = prepare_filter

    result = service.execute(
        PreprocessCommand(operation=PreprocessOperation.NOTCH, notch_freq=40.0)
    )

    assert result.error_type is not ErrorType.PRECONDITION
    assert prepare_filter.call_count == 1


@pytest.mark.parametrize(
    ("event_ids", "accepted"),
    [
        (["Left hand", "Right hand"], True),
        (["Artifact"], False),
        ({"Artifact": 99}, False),
    ],
    ids=("display-aliases", "unreviewed-list", "unreviewed-dict"),
)
def test_prepared_epoch_uses_reviewed_display_aliases_and_rejects_unreviewed_targets(
    tmp_path: Path,
    event_ids: list[str] | dict[str, int],
    accepted: bool,
) -> None:
    path = tmp_path / "display-aliases_raw.fif"
    _write_reviewed_epoch_fixture(
        path,
        event_rows=np.asarray([[100, 0, 769], [250, 0, 770], [400, 0, 769]], dtype=int),
        event_desc={769: "769", 770: "770"},
    )
    service = ApplicationService(Study())
    try:
        _apply_reviewed_epoch_fixture(
            service,
            path,
            internal_event_codes=("769", "770"),
            class_map={"769": "Left hand", "770": "Right hand"},
        )
        original_loaded = list(service.study.loaded_data_list)
        original_preprocessed = service.study.preprocessed_data_list
        original_samples = [
            raw.get_mne().get_data().copy() for raw in original_preprocessed
        ]

        result = service.execute(
            CreateEpochCommand(t_min=0.0, t_max=0.2, event_ids=event_ids)
        )

        if accepted:
            assert result.ok, result.message
            assert result.state.epoch.event_names == ["Left hand", "Right hand"]
            assert set(result.state.epoch.event_ids or {}) == {
                "Left hand",
                "Right hand",
            }
            epoch_data = service.study.epoch_data
            assert epoch_data is not None
            assert epoch_data.get_data_length() == 3
            assert epoch_data.get_label_map() == {
                0: "Left hand",
                1: "Right hand",
            }
            assert [
                epoch_data.get_label_name(int(label))
                for label in epoch_data.get_label_list()
            ] == ["Left hand", "Right hand", "Left hand"]
            assert np.bincount(epoch_data.get_label_list()).tolist() == [2, 1]
            assert service.study.is_locked() is True
        else:
            assert result.failed is True
            assert result.error_type is ErrorType.PRECONDITION
            assert result.message == (
                "EEG epoch target is not in the reviewed import labels: Artifact."
            )
            assert service.study.preprocessed_data_list is original_preprocessed
            assert all(
                current is original
                for current, original in zip(
                    service.study.loaded_data_list, original_loaded, strict=True
                )
            )
            for raw, samples in zip(
                service.study.preprocessed_data_list, original_samples, strict=True
            ):
                np.testing.assert_array_equal(raw.get_mne().get_data(), samples)
            assert service.study.epoch_data is None
            assert service.study.is_locked() is False
    finally:
        service.close()


@pytest.mark.parametrize(
    ("event_count", "recording_count", "accepted"),
    [(100, 1, True), (99, 1, False), (100, 3, True)],
    ids=(
        "one-percent-boundary-drop-accepted",
        "above-one-percent-rejected",
        "multi-recording-below-one-percent-accepted",
    ),
)
def test_prepared_epoch_boundary_limit_uses_real_reviewed_events(
    tmp_path: Path,
    event_count: int,
    recording_count: int,
    accepted: bool,
) -> None:
    paths: list[Path] = []
    for recording_index in range(recording_count):
        path = tmp_path / f"boundary-{event_count}-{recording_index}-events_raw.fif"
        has_boundary_event = recording_count == 1 or recording_index < 2
        events = np.asarray(
            [
                [
                    0
                    if has_boundary_event and index == 0
                    else 50 + (index - int(has_boundary_event)) * 5,
                    0,
                    1 if index % 2 == 0 else 2,
                ]
                for index in range(event_count)
            ],
            dtype=int,
        )
        _write_reviewed_epoch_fixture(path, event_rows=events)
        paths.append(path)
    service = ApplicationService(Study())
    try:
        _apply_reviewed_epoch_fixture(service, paths[0], tuple(paths[1:]))
        loaded_sources = list(service.study.loaded_data_list)
        original_preprocessed = service.study.preprocessed_data_list
        original_samples = [
            item.get_mne().get_data().copy() for item in original_preprocessed
        ]

        result = service.execute(
            CreateEpochCommand(
                t_min=-0.1,
                t_max=0.2,
                event_ids=["left", "right"],
            )
        )

        excluded = 1 if recording_count == 1 else 2
        selected = event_count * recording_count
        boundary = result.diagnostics["epoch_boundary_check"]
        assert boundary == {
            "selected_event_count": selected,
            "excluded_event_count": excluded,
            "remaining_event_count": selected - excluded,
            "affected_recording_count": excluded,
            "recording_count": recording_count,
            "excluded_ratio": pytest.approx(excluded / selected),
        }
        for raw, samples, loaded in zip(
            original_preprocessed, original_samples, loaded_sources, strict=True
        ):
            np.testing.assert_array_equal(raw.get_mne().get_data(), samples)
            assert raw is loaded
        current_loaded = service.study.loaded_data_list
        assert len(current_loaded) == recording_count
        assert all(
            current is expected
            for current, expected in zip(current_loaded, loaded_sources, strict=True)
        )
        if accepted:
            assert result.ok, result.message
            assert result.message == (
                f"Created EEG epochs from -0.1s to 0.2s. Excluded {excluded} boundary "
                "event(s) that could not contain the complete window."
            )
            assert service.study.preprocessed_data_list is not original_preprocessed
            epoch_data = service.study.epoch_data
            assert epoch_data is not None
            assert epoch_data.get_data_length() == selected - excluded
            assert (
                sum(
                    len(item.get_mne()) for item in service.study.preprocessed_data_list
                )
                == selected - excluded
            )
            assert service.study.is_locked() is True
        else:
            assert result.failed is True
            assert result.message == (
                "The selected epoch window would exclude 1 of 99 selected events "
                "because they are too close to a recording boundary. Shorten the "
                "epoch window or review the selected events."
            )
            assert service.study.preprocessed_data_list is original_preprocessed
            assert service.study.epoch_data is None
            assert service.study.is_locked() is False
    finally:
        service.close()


def test_prepared_epoch_ram_denial_precedes_eeg_copy_and_publication(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ram-denied-epoch_raw.fif"
    _write_reviewed_epoch_fixture(path)
    service = ApplicationService(Study())
    blocking = ResourceCheckResult(
        required_memory_bytes=10_000,
        available_memory_bytes=1_000,
        total_memory_bytes=2_000,
        used_memory_bytes=1_000,
        risk_level="blocking",
        message="EEG epoch data is too large for available RAM.",
        details={"estimate_status": "blocking", "source_count": 1},
    )
    try:
        _apply_reviewed_epoch_fixture(service, path)
        original_loaded = list(service.study.loaded_data_list)
        original_preprocessed = service.study.preprocessed_data_list
        original_samples = [
            raw.get_mne().get_data().copy() for raw in original_preprocessed
        ]
        copy_spy = MagicMock(side_effect=AssertionError("EEG deepcopy must not run"))

        with (
            patch.object(
                ResourceChecker,
                "check_epoch_materialization_safe",
                return_value=blocking,
            ),
            patch("XBrainLab.backend.preprocessor.base.deepcopy", copy_spy),
        ):
            result = service.execute(
                CreateEpochCommand(
                    t_min=-0.1,
                    t_max=0.2,
                    event_ids=["left", "right"],
                )
            )

        assert result.failed is True
        assert result.error_type is ErrorType.PRECONDITION
        assert result.message == blocking.message
        assert result.diagnostics["resource_preflight"] == blocking.to_diagnostics()
        copy_spy.assert_not_called()
        assert service.study.preprocessed_data_list is original_preprocessed
        assert len(service.study.loaded_data_list) == len(original_loaded)
        assert all(
            current is original
            for current, original in zip(
                service.study.loaded_data_list, original_loaded, strict=True
            )
        )
        for raw, samples in zip(
            service.study.preprocessed_data_list, original_samples, strict=True
        ):
            np.testing.assert_array_equal(raw.get_mne().get_data(), samples)
        assert service.study.epoch_data is None
        assert service.study.is_locked() is False
    finally:
        service.close()


def test_preprocess_heavy_prepare_releases_command_lock_and_cancel_can_retry() -> None:
    study = Study()
    rows = [_minimal_raw(Path(f"recording-{index}.fif")) for index in range(2)]
    study.set_loaded_data_list(rows, force_update=True)
    service = ApplicationService(study)
    original = study.preprocessed_data_list
    before = service.get_view_publication()
    processing_started = Event()
    release_processing = Event()
    should_block = Event()
    should_block.set()

    class _BlockingNormalize(Normalize):
        def data_preprocess(self, norm: str) -> list[Raw]:
            if should_block.is_set():
                processing_started.set()
                assert release_processing.wait(timeout=THREAD_WATCHDOG_SECONDS)
            return super().data_preprocess(norm)

    original_provider = service.preprocess._processor_provider
    service.preprocess._processor_provider = (
        lambda name: _BlockingNormalize
        if name == "Normalize"
        else original_provider(name)
    )
    command = PreprocessCommand(
        operation=PreprocessOperation.NORMALIZE,
        method="z-score",
    )
    operation = service.begin_owned_operation(command)
    results: list[CommandResult] = []
    worker = Thread(
        target=lambda: results.append(
            service.execute(command, operation_id=operation.operation_id)
        ),
        name="preprocess-cancel",
    )

    worker.start()
    assert processing_started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    progress = service.get_owned_operation(operation.operation_id)
    command_lock_available = service._command_lock.acquire(blocking=False)
    if command_lock_available:
        service._command_lock.release()
    started_at = time.monotonic()
    cancelled = service.cancel_owned_operation(operation.operation_id)
    cancel_elapsed = time.monotonic() - started_at
    release_processing.set()
    worker.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not worker.is_alive()
    assert command_lock_available is True
    assert cancelled is True
    assert cancel_elapsed < 0.1
    assert progress.stage == "Preparing working EEG recordings"
    assert progress.completed == 2
    assert progress.total == 2
    assert len(results) == 1
    cancelled_result = results[0]
    assert cancelled_result.failed
    assert cancelled_result.error_type is ErrorType.CANCELLED
    assert cancelled_result.changed_state == ChangedState()
    assert cancelled_result.state == before.state
    assert service._last_error is None
    assert service.get_owned_operation(operation.operation_id).phase is (
        OwnedWorkPhase.CANCELLED
    )
    assert study.preprocessed_data_list is original
    assert all(not row.get_preprocess_history() for row in original)

    should_block.clear()
    retry = service.begin_owned_operation(command)
    retried = service.execute(command, operation_id=retry.operation_id)

    assert retried.ok
    assert service.get_owned_operation(retry.operation_id).phase is (
        OwnedWorkPhase.COMPLETED
    )
    assert study.preprocessed_data_list is not original
    assert all(
        "normalization requested" in row.get_preprocess_history()[-1]
        for row in study.preprocessed_data_list
    )


@pytest.mark.parametrize(
    ("failure_mode", "expected_error"),
    [
        ("stale", ErrorType.PRECONDITION),
        ("error", ErrorType.INTERNAL),
    ],
)
def test_preprocess_prepare_after_concurrent_mutation_preserves_current_truth(
    failure_mode: str,
    expected_error: ErrorType,
) -> None:
    study = Study()
    raw = _minimal_raw(Path("recording.fif"))
    study.set_loaded_data_list([raw], force_update=True)
    service = ApplicationService(study)
    processing_started = Event()
    release_processing = Event()

    class _BlockingNormalize(Normalize):
        def data_preprocess(self, norm: str) -> list[Raw]:
            processing_started.set()
            assert release_processing.wait(timeout=THREAD_WATCHDOG_SECONDS)
            if failure_mode == "error":
                raise RuntimeError("detached preprocessing failed")
            return super().data_preprocess(norm)

    original_provider = service.preprocess._processor_provider
    service.preprocess._processor_provider = (
        lambda name: _BlockingNormalize
        if name == "Normalize"
        else original_provider(name)
    )
    command = PreprocessCommand(
        operation=PreprocessOperation.NORMALIZE,
        method="z-score",
    )
    operation = service.begin_owned_operation(command)
    results: list[CommandResult] = []
    worker = Thread(
        target=lambda: results.append(
            service.execute(command, operation_id=operation.operation_id)
        ),
        name="preprocess-stale-prepare",
    )
    concurrent_results: list[CommandResult] = []
    concurrent_done = Event()

    def _update_metadata() -> None:
        concurrent_results.append(
            service.execute(UpdateMetadataCommand(index=0, subject="S99"))
        )
        concurrent_done.set()

    worker.start()
    assert processing_started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    command_lock_available = service._command_lock.acquire(blocking=False)
    if command_lock_available:
        service._command_lock.release()
    concurrent_worker = Thread(target=_update_metadata, name="concurrent-metadata")
    concurrent_worker.start()
    concurrent_committed_while_prepare_blocked = concurrent_done.wait(timeout=0.5)
    release_processing.set()
    worker.join(timeout=THREAD_WATCHDOG_SECONDS)
    concurrent_worker.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not worker.is_alive()
    assert not concurrent_worker.is_alive()
    assert command_lock_available is True
    assert concurrent_committed_while_prepare_blocked is True
    assert len(concurrent_results) == 1
    assert concurrent_results[0].ok
    assert study.loaded_data_list[0].get_subject_name() == "S99"
    assert len(results) == 1
    failed = results[0]
    assert failed.failed
    assert failed.error_type is expected_error
    assert failed.changed_state == ChangedState()
    assert failed.state == concurrent_results[0].state
    if failure_mode == "stale":
        assert failed.diagnostics["stale_prepared_preprocess"] is True
    else:
        assert (
            failed.diagnostics["detached_prepare_failed_after_concurrent_change"]
            is True
        )
        assert failed.diagnostics["state_preserved"] is True
        assert service.get_view_publication().state == concurrent_results[0].state
        assert service._last_error is None
    assert service.get_owned_operation(operation.operation_id).phase is (
        OwnedWorkPhase.FAILED
    )
    assert all(
        "normalization requested" not in " ".join(row.get_preprocess_history())
        for row in study.preprocessed_data_list
    )


def test_preprocess_allows_background_montage_status_to_settle_during_prepare() -> None:
    study = Study()
    raw = _minimal_raw(Path("recording.fif"))
    study.set_loaded_data_list([raw], force_update=True)
    service = ApplicationService(study)
    processing_started = Event()
    release_processing = Event()

    class _BlockingNormalize(Normalize):
        def data_preprocess(self, norm: str) -> list[Raw]:
            processing_started.set()
            assert release_processing.wait(timeout=THREAD_WATCHDOG_SECONDS)
            return super().data_preprocess(norm)

    original_provider = service.preprocess._processor_provider
    service.preprocess._processor_provider = (
        lambda name: _BlockingNormalize
        if name == "Normalize"
        else original_provider(name)
    )
    montage_status = [
        MontagePreparationSnapshot.pending(
            generation=1,
            recording_paths=("recording.fif",),
        )
    ]
    service.state_snapshot.montage_snapshot_provider = lambda: montage_status[0]
    pending_state = service.get_state()
    assert pending_state.visualization.montage_preparation_state == "pending"

    command = PreprocessCommand(
        operation=PreprocessOperation.NORMALIZE,
        method="z-score",
    )
    operation = service.begin_owned_operation(command)
    results: list[CommandResult] = []
    worker = Thread(
        target=lambda: results.append(
            service.execute(command, operation_id=operation.operation_id)
        ),
        name="preprocess-montage-status-transition",
    )

    worker.start()
    assert processing_started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    montage_status[0] = MontagePreparationSnapshot.not_applicable(
        generation=1,
        reason="No BIDS electrode-position sidecars apply to this recording.",
    )
    settled_state = service.get_state()
    assert settled_state.visualization.montage_preparation_state == "not_applicable"
    release_processing.set()
    worker.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not worker.is_alive()
    assert len(results) == 1
    completed = results[0]
    assert completed.ok
    assert completed.state.visualization.montage_preparation_state == "not_applicable"
    assert service.get_owned_operation(operation.operation_id).phase is (
        OwnedWorkPhase.COMPLETED
    )
    assert all(
        "normalization requested" in row.get_preprocess_history()[-1]
        for row in study.preprocessed_data_list
    )


def test_channel_selection_allows_reviewed_montage_settle_before_admission() -> None:
    study = Study()
    raw = Raw(
        "channels.fif",
        mne.io.RawArray(
            np.zeros((2, 500)),
            mne.create_info(["C3", "C4"], sfreq=100.0, ch_types="eeg"),
            verbose="ERROR",
        ),
    )
    study.set_loaded_data_list([raw], force_update=True)
    service = ApplicationService(study)
    montage_status = [
        MontagePreparationSnapshot.pending(
            generation=1,
            recording_paths=("channels.fif",),
        )
    ]
    service.state_snapshot.montage_snapshot_provider = lambda: montage_status[0]
    reviewed = service._view_coordinator.refresh_opportunistic()
    reviewed_boundary = ApplicationPreprocessBoundary(
        publication_generation=reviewed.generation,
        publication_revision=reviewed.revision,
        state=reviewed.state,
    )
    montage_status[0] = MontagePreparationSnapshot(
        state="ready",
        generation=1,
        requested_recording_paths=("channels.fif",),
    )
    current = service._view_coordinator.refresh_opportunistic()
    assert current.generation > reviewed.generation
    loaded_publications = 0
    original_set_loaded_data_list = study.set_loaded_data_list

    def set_loaded_data_list_once(rows, force_update=False) -> None:
        nonlocal loaded_publications
        loaded_publications += 1
        original_set_loaded_data_list(rows, force_update=force_update)

    study.set_loaded_data_list = set_loaded_data_list_once

    result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.SELECT_CHANNELS,
            channels=["C3"],
        ),
        expected_publication_generation=reviewed.generation,
        reviewed_preprocess_boundary=reviewed_boundary,
    )

    assert result.ok
    assert loaded_publications == 1
    assert study.loaded_data_list[0].get_mne().ch_names == ["C3"]
    assert study.preprocessed_data_list[0] is study.loaded_data_list[0]
    assert study.data_manager.backup_loaded_data_list is not None
    assert study.data_manager.backup_loaded_data_list[0].get_mne().ch_names == [
        "C3",
        "C4",
    ]


def test_channel_selection_reviewed_boundary_rejects_material_state_change() -> None:
    study = Study()
    raw = Raw(
        "channels.fif",
        mne.io.RawArray(
            np.zeros((2, 500)),
            mne.create_info(["C3", "C4"], sfreq=100.0, ch_types="eeg"),
            verbose="ERROR",
        ),
    )
    study.set_loaded_data_list([raw], force_update=True)
    service = ApplicationService(study)
    reviewed = service.get_view_publication()
    reviewed_boundary = ApplicationPreprocessBoundary(
        publication_generation=reviewed.generation,
        publication_revision=reviewed.revision,
        state=reviewed.state,
    )
    changed = service.execute(UpdateMetadataCommand(index=0, subject="S99"))
    assert changed.ok

    result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.SELECT_CHANNELS,
            channels=["C3"],
        ),
        expected_publication_generation=reviewed.generation,
        reviewed_preprocess_boundary=reviewed_boundary,
    )

    assert result.failed
    assert result.error_type is ErrorType.PRECONDITION
    assert result.diagnostics["stale_publication"] is True
    assert study.loaded_data_list[0].get_subject_name() == "S99"
    assert study.loaded_data_list[0].get_mne().ch_names == ["C3", "C4"]
    assert study.data_manager.backup_loaded_data_list is None
    assert study.is_locked() is False


def test_channel_selection_reviewed_boundary_rejects_unusable_publication() -> None:
    study = Study()
    raw = Raw(
        "channels.fif",
        mne.io.RawArray(
            np.zeros((2, 500)),
            mne.create_info(["C3", "C4"], sfreq=100.0, ch_types="eeg"),
            verbose="ERROR",
        ),
    )
    study.set_loaded_data_list([raw], force_update=True)
    service = ApplicationService(study)
    reviewed = service.get_view_publication()
    reviewed_boundary = ApplicationPreprocessBoundary(
        publication_generation=reviewed.generation,
        publication_revision=reviewed.revision,
        state=reviewed.state,
    )
    service._view_coordinator.mark_stale("publication unavailable")

    result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.SELECT_CHANNELS,
            channels=["C3"],
        ),
        expected_publication_generation=reviewed.generation,
        reviewed_preprocess_boundary=reviewed_boundary,
    )

    assert result.failed
    assert result.error_type is ErrorType.PRECONDITION
    assert result.diagnostics["publication_usable"] is False
    assert study.loaded_data_list[0].get_mne().ch_names == ["C3", "C4"]
    assert study.data_manager.backup_loaded_data_list is None
    assert study.is_locked() is False


def test_preprocess_commit_failure_rolls_back_complete_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    study = Study()
    raw = _minimal_raw(Path("recording.fif"))
    study.set_loaded_data_list([raw], force_update=True)
    service = ApplicationService(study)
    snapshot = service.pipeline_transaction.capture()
    original_set = study.set_preprocessed_data_list

    def _mutate_then_fail(
        rows: list[Raw],
        force_update: bool = False,
    ) -> None:
        original_set(rows, force_update=force_update)
        raise RuntimeError("preprocess publication failed")

    monkeypatch.setattr(study, "set_preprocessed_data_list", _mutate_then_fail)

    result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.NORMALIZE,
            method="z-score",
        )
    )

    assert result.failed
    assert result.error_type is ErrorType.INTERNAL
    assert "preprocess publication failed" in result.message
    restored = service.pipeline_transaction.capture()
    assert restored.loaded_data == snapshot.loaded_data
    assert restored.backup_loaded_data == snapshot.backup_loaded_data
    assert restored.preprocessed_data == snapshot.preprocessed_data
    assert restored.epoch_data is snapshot.epoch_data
    assert restored.datasets == snapshot.datasets
    assert restored.dataset_generator is snapshot.dataset_generator
    assert restored.dataset_locked is snapshot.dataset_locked
    assert all(not row.get_preprocess_history() for row in study.preprocessed_data_list)


def test_preprocess_retirement_failure_restores_pipeline_and_training_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    study = Study()
    raw = _minimal_raw(Path("recording.fif"))
    study.set_loaded_data_list([raw], force_update=True)
    trainer = Trainer([])
    history_holder = MagicMock(name="completed_training_history")
    trainer.training_plan_holders = cast(Any, [history_holder])
    study.training_manager.trainer = trainer
    service = ApplicationService(study)
    pipeline_before = service.pipeline_transaction.capture()
    publication_before = service.get_view_publication()

    def _mutate_training_then_fail(expected, *, publish) -> bool:
        del expected
        publish()
        trainer.clear_history()
        study.training_manager.trainer = None
        raise RuntimeError("trainer retirement failed after cleanup")

    monkeypatch.setattr(
        study.training_manager,
        "commit_pipeline_replacement",
        _mutate_training_then_fail,
    )

    result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.NORMALIZE,
            method="z-score",
        )
    )

    assert result.failed
    assert result.error_type is ErrorType.INTERNAL
    assert "trainer retirement failed after cleanup" in result.message
    pipeline_after = service.pipeline_transaction.capture()
    assert pipeline_after == pipeline_before
    assert study.training_manager.trainer is trainer
    assert trainer.get_training_plan_holders() == [history_holder]
    publication_after = service.get_view_publication()
    assert (
        replace(
            publication_after.state.training,
            read_generation=publication_before.state.training.read_generation,
        )
        == publication_before.state.training
    )
    assert publication_after.training_history == publication_before.training_history


def test_preprocess_stale_training_boundary_preserves_newer_training_truth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    study = Study()
    raw = _minimal_raw(Path("recording.fif"))
    study.set_loaded_data_list([raw], force_update=True)
    previous_trainer = Trainer([])
    replacement_trainer = Trainer([])
    study.training_manager.trainer = previous_trainer
    service = ApplicationService(study)
    pipeline_before = service.pipeline_transaction.capture()
    restore_training = MagicMock(
        side_effect=AssertionError("stale boundary must not restore old training"),
    )
    monkeypatch.setattr(
        study.training_manager,
        "restore_startup_rollback_snapshot",
        restore_training,
    )

    def _replace_training_then_reject(expected, *, publish) -> bool:
        del expected, publish
        study.training_manager.trainer = replacement_trainer
        raise StaleTrainingPipelineMutationError

    monkeypatch.setattr(
        study.training_manager,
        "commit_pipeline_replacement",
        _replace_training_then_reject,
    )

    result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.NORMALIZE,
            method="z-score",
        )
    )

    assert result.failed
    assert result.error_type is ErrorType.PRECONDITION
    assert result.diagnostics["code"] == "training_pipeline_boundary_changed"
    assert service.pipeline_transaction.capture() == pipeline_before
    assert study.training_manager.trainer is replacement_trainer
    assert result.state.training.has_trainer is True
    restore_training.assert_not_called()


def test_preprocess_base_exception_survives_best_effort_rollback_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _SentinelControlFlow(BaseException):
        pass

    study = Study()
    raw = _minimal_raw(Path("recording.fif"))
    study.set_loaded_data_list([raw], force_update=True)
    study.training_manager.trainer = Trainer([])
    service = ApplicationService(study)
    pipeline_before = service.pipeline_transaction.capture()
    sentinel = _SentinelControlFlow("stop command execution")

    def _publish_then_abort(expected, *, publish) -> bool:
        del expected
        publish()
        raise sentinel

    monkeypatch.setattr(
        study.training_manager,
        "commit_pipeline_replacement",
        _publish_then_abort,
    )
    restore_training = MagicMock(
        side_effect=RuntimeError("training rollback failed"),
    )
    monkeypatch.setattr(
        study.training_manager,
        "restore_startup_rollback_snapshot",
        restore_training,
    )
    restore_pipeline = MagicMock(wraps=service.pipeline_transaction.restore)
    monkeypatch.setattr(
        service.pipeline_transaction,
        "restore",
        restore_pipeline,
    )

    with pytest.raises(_SentinelControlFlow) as exc_info:
        service.execute(
            PreprocessCommand(
                operation=PreprocessOperation.NORMALIZE,
                method="z-score",
            )
        )

    assert exc_info.value is sentinel
    restore_training.assert_called_once()
    restore_pipeline.assert_called_once()
    assert service.pipeline_transaction.capture() == pipeline_before


def test_channel_selection_heavy_prepare_cancel_preserves_and_can_retry() -> None:
    study = Study()
    raw = Raw(
        "channels.fif",
        mne.io.RawArray(
            np.zeros((2, 500)),
            mne.create_info(["C3", "C4"], sfreq=100.0, ch_types="eeg"),
            verbose="ERROR",
        ),
    )
    study.set_loaded_data_list([raw], force_update=True)
    service = ApplicationService(study)
    original_loaded = study.loaded_data_list
    original_preprocessed = study.preprocessed_data_list
    before = service.get_view_publication()
    processing_started = Event()
    release_processing = Event()
    should_block = Event()
    should_block.set()

    class _BlockingChannelSelection(ChannelSelection):
        def data_preprocess(self, selected_channels: list[str]) -> list[Raw]:
            if should_block.is_set():
                processing_started.set()
                assert release_processing.wait(timeout=THREAD_WATCHDOG_SECONDS)
            return super().data_preprocess(selected_channels)

    service.dataset._channel_selection_provider = lambda: _BlockingChannelSelection
    command = PreprocessCommand(
        operation=PreprocessOperation.CHANNEL_SELECTION,
        channels=["C3"],
    )
    operation = service.begin_owned_operation(command)
    results: list[CommandResult] = []
    worker = Thread(
        target=lambda: results.append(
            service.execute(command, operation_id=operation.operation_id)
        ),
        name="channel-selection-cancel",
    )

    worker.start()
    assert processing_started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    command_lock_available = service._command_lock.acquire(blocking=False)
    if command_lock_available:
        service._command_lock.release()
    started_at = time.monotonic()
    cancelled = service.cancel_owned_operation(operation.operation_id)
    cancel_elapsed = time.monotonic() - started_at
    release_processing.set()
    worker.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not worker.is_alive()
    assert command_lock_available is True
    assert cancelled is True
    assert cancel_elapsed < 0.1
    assert len(results) == 1
    assert results[0].error_type is ErrorType.CANCELLED
    assert results[0].changed_state == ChangedState()
    assert results[0].state == before.state
    assert service._last_error is None
    assert study.loaded_data_list is original_loaded
    assert study.preprocessed_data_list is original_preprocessed
    assert study.data_manager.backup_loaded_data_list is None
    assert study.loaded_data_list[0].get_mne().ch_names == ["C3", "C4"]
    assert study.is_locked() is False

    should_block.clear()
    retry = service.begin_owned_operation(command)
    retried = service.execute(command, operation_id=retry.operation_id)

    assert retried.ok
    assert service.get_owned_operation(retry.operation_id).phase is (
        OwnedWorkPhase.COMPLETED
    )
    assert study.loaded_data_list is not original_loaded
    assert study.loaded_data_list[0].get_mne().ch_names == ["C3"]
    assert study.preprocessed_data_list[0] is study.loaded_data_list[0]
    assert study.data_manager.backup_loaded_data_list is not None
    assert study.data_manager.backup_loaded_data_list[0].get_mne().ch_names == [
        "C3",
        "C4",
    ]
    assert study.is_locked() is True


def test_channel_selection_rejects_prepare_staled_by_concurrent_metadata() -> None:
    study = Study()
    raw = Raw(
        "channels.fif",
        mne.io.RawArray(
            np.zeros((2, 500)),
            mne.create_info(["C3", "C4"], sfreq=100.0, ch_types="eeg"),
            verbose="ERROR",
        ),
    )
    study.set_loaded_data_list([raw], force_update=True)
    service = ApplicationService(study)
    processing_started = Event()
    release_processing = Event()

    class _BlockingChannelSelection(ChannelSelection):
        def data_preprocess(self, selected_channels: list[str]) -> list[Raw]:
            processing_started.set()
            assert release_processing.wait(timeout=THREAD_WATCHDOG_SECONDS)
            return super().data_preprocess(selected_channels)

    service.dataset._channel_selection_provider = lambda: _BlockingChannelSelection
    command = PreprocessCommand(
        operation=PreprocessOperation.SELECT_CHANNELS,
        channels=["C3"],
    )
    operation = service.begin_owned_operation(command)
    results: list[CommandResult] = []
    worker = Thread(
        target=lambda: results.append(
            service.execute(command, operation_id=operation.operation_id)
        ),
        name="channel-selection-stale",
    )

    worker.start()
    assert processing_started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    assert service._command_lock.acquire(blocking=False) is True
    service._command_lock.release()
    concurrent = service.execute(UpdateMetadataCommand(index=0, subject="S99"))
    assert concurrent.ok
    release_processing.set()
    worker.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not worker.is_alive()
    assert len(results) == 1
    stale = results[0]
    assert stale.failed
    assert stale.error_type is ErrorType.PRECONDITION
    assert stale.diagnostics["stale_prepared_preprocess"] is True
    assert stale.changed_state == ChangedState()
    assert stale.state == concurrent.state
    assert study.loaded_data_list[0].get_subject_name() == "S99"
    assert study.loaded_data_list[0].get_mne().ch_names == ["C3", "C4"]
    assert study.data_manager.backup_loaded_data_list is None
    assert study.is_locked() is False


def test_channel_selection_commit_failure_restores_backup_and_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    study = Study()
    raw = Raw(
        "channels.fif",
        mne.io.RawArray(
            np.zeros((2, 500)),
            mne.create_info(["C3", "C4"], sfreq=100.0, ch_types="eeg"),
            verbose="ERROR",
        ),
    )
    study.set_loaded_data_list([raw], force_update=True)
    service = ApplicationService(study)
    snapshot = service.pipeline_transaction.capture()
    original_set = study.set_loaded_data_list

    def _mutate_then_fail(
        rows: list[Raw],
        force_update: bool = False,
    ) -> None:
        original_set(rows, force_update=force_update)
        study.data_manager.backup_loaded_data_list = list(rows)
        raise RuntimeError("channel publication failed")

    monkeypatch.setattr(study, "set_loaded_data_list", _mutate_then_fail)

    result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.CHANNEL_SELECTION,
            channels=["C3"],
        )
    )

    assert result.failed
    assert result.error_type is ErrorType.INTERNAL
    assert "channel publication failed" in result.message
    restored = service.pipeline_transaction.capture()
    assert restored.loaded_data == snapshot.loaded_data
    assert restored.backup_loaded_data == snapshot.backup_loaded_data
    assert restored.preprocessed_data == snapshot.preprocessed_data
    assert restored.epoch_data is snapshot.epoch_data
    assert restored.datasets == snapshot.datasets
    assert restored.dataset_generator is snapshot.dataset_generator
    assert restored.dataset_locked is snapshot.dataset_locked
    assert study.loaded_data_list[0].get_mne().ch_names == ["C3", "C4"]


def test_epoch_heavy_prepare_releases_command_lock_and_cancel_can_retry(
    tmp_path: Path,
) -> None:
    path = tmp_path / "reviewed-epoch_raw.fif"
    _write_reviewed_epoch_fixture(path)
    service = ApplicationService(Study())
    _apply_reviewed_epoch_fixture(service, path)
    original = service.study.preprocessed_data_list
    before = service.get_view_publication()
    processing_started = Event()
    release_processing = Event()
    should_block = Event()
    should_block.set()

    class _BlockingTimeEpoch(TimeEpoch):
        def data_preprocess(
            self,
            baseline,
            selected_event_names,
            tmin,
            tmax,
            allow_boundary_drop=False,
            *,
            event_label_aliases_by_source=None,
        ) -> list[Raw]:
            if should_block.is_set():
                processing_started.set()
                assert release_processing.wait(timeout=THREAD_WATCHDOG_SECONDS)
            return super().data_preprocess(
                baseline,
                selected_event_names,
                tmin,
                tmax,
                allow_boundary_drop,
                event_label_aliases_by_source=event_label_aliases_by_source,
            )

    original_provider = service.preprocess._processor_provider
    service.preprocess._processor_provider = (
        lambda name: _BlockingTimeEpoch
        if name == "TimeEpoch"
        else original_provider(name)
    )
    command = CreateEpochCommand(
        t_min=0.0,
        t_max=0.2,
        event_ids=["left", "right"],
    )
    operation = service.begin_owned_operation(command)
    results: list[CommandResult] = []
    worker = Thread(
        target=lambda: results.append(
            service.execute(command, operation_id=operation.operation_id)
        ),
        name="epoch-cancel",
    )

    worker.start()
    assert processing_started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    command_lock_available = service._command_lock.acquire(blocking=False)
    if command_lock_available:
        service._command_lock.release()
    started_at = time.monotonic()
    cancelled = service.cancel_owned_operation(operation.operation_id)
    cancel_elapsed = time.monotonic() - started_at
    release_processing.set()
    worker.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not worker.is_alive()
    assert command_lock_available is True
    assert cancelled is True
    assert cancel_elapsed < 0.1
    assert len(results) == 1
    cancelled_result = results[0]
    assert cancelled_result.failed
    assert cancelled_result.error_type is ErrorType.CANCELLED
    assert cancelled_result.changed_state == ChangedState()
    assert cancelled_result.state == before.state
    assert service._last_error is None
    assert service.get_owned_operation(operation.operation_id).phase is (
        OwnedWorkPhase.CANCELLED
    )
    assert service.study.preprocessed_data_list is original
    assert service.study.epoch_data is None
    assert service.study.is_locked() is False

    should_block.clear()
    retry = service.begin_owned_operation(command)
    retried = service.execute(command, operation_id=retry.operation_id)

    assert retried.ok
    assert service.get_owned_operation(retry.operation_id).phase is (
        OwnedWorkPhase.COMPLETED
    )
    assert service.study.preprocessed_data_list is not original
    assert service.study.epoch_data is not None
    assert service.study.is_locked() is True


def test_raw_layout_projects_after_prepared_epoch_commit_without_reordering(
    tmp_path: Path,
) -> None:
    path = tmp_path / "layout-before-epoch_raw.fif"
    _write_reviewed_epoch_fixture(path, ("C3", "Cz", "C4"))
    service = ApplicationService(Study())
    _apply_reviewed_epoch_fixture(service, path)

    layout = service.execute(
        ApplyMontageCommand(
            channels=["C3", "Cz", "C4"],
            positions=[(-0.08, 0.0, 0.0), (0.0, 0.08, 0.0), (0.08, 0.0, 0.0)],
            montage_name="manual",
        )
    )
    created = service.execute(
        CreateEpochCommand(t_min=0.0, t_max=0.2, event_ids=["left", "right"])
    )

    assert layout.ok is True
    assert created.ok is True
    assert created.state.epoch.channel_names == ["C3", "Cz", "C4"]
    epoch = service.study.epoch_data
    assert epoch is not None
    assert epoch.get_channel_names() == ["C3", "Cz", "C4"]
    assert epoch.channel_position == [
        (-0.08, 0.0, 0.0),
        (0.0, 0.08, 0.0),
        (0.08, 0.0, 0.0),
    ]


def test_epoch_rejects_prepare_staled_by_concurrent_mutation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stale-epoch_raw.fif"
    _write_reviewed_epoch_fixture(path)
    service = ApplicationService(Study())
    _apply_reviewed_epoch_fixture(service, path)
    processing_started = Event()
    release_processing = Event()

    class _BlockingTimeEpoch(TimeEpoch):
        def data_preprocess(
            self,
            baseline,
            selected_event_names,
            tmin,
            tmax,
            allow_boundary_drop=False,
            *,
            event_label_aliases_by_source=None,
        ) -> list[Raw]:
            processing_started.set()
            assert release_processing.wait(timeout=THREAD_WATCHDOG_SECONDS)
            return super().data_preprocess(
                baseline,
                selected_event_names,
                tmin,
                tmax,
                allow_boundary_drop,
                event_label_aliases_by_source=event_label_aliases_by_source,
            )

    original_provider = service.preprocess._processor_provider
    service.preprocess._processor_provider = (
        lambda name: _BlockingTimeEpoch
        if name == "TimeEpoch"
        else original_provider(name)
    )
    command = CreateEpochCommand(
        t_min=0.0,
        t_max=0.2,
        event_ids=["left", "right"],
    )
    operation = service.begin_owned_operation(command)
    results: list[CommandResult] = []
    worker = Thread(
        target=lambda: results.append(
            service.execute(command, operation_id=operation.operation_id)
        ),
        name="epoch-stale-prepare",
    )

    worker.start()
    assert processing_started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    assert service._command_lock.acquire(blocking=False) is True
    service._command_lock.release()
    concurrent = service.execute(UpdateMetadataCommand(index=0, subject="S99"))
    assert concurrent.ok
    release_processing.set()
    worker.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not worker.is_alive()
    assert len(results) == 1
    stale = results[0]
    assert stale.failed
    assert stale.error_type is ErrorType.PRECONDITION
    assert stale.diagnostics["stale_prepared_preprocess"] is True
    assert stale.changed_state == ChangedState()
    assert stale.state == concurrent.state
    assert service.study.loaded_data_list[0].get_subject_name() == "S99"
    assert service.study.epoch_data is None
    assert service.study.is_locked() is False
    assert service.get_owned_operation(operation.operation_id).phase is (
        OwnedWorkPhase.FAILED
    )
