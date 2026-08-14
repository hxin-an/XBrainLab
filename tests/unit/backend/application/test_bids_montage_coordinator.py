from __future__ import annotations

import json
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from XBrainLab.backend.application import bids_montage_coordinator
from XBrainLab.backend.application.bids_dataset_index import build_bids_dataset_index
from XBrainLab.backend.application.bids_montage_coordinator import (
    BidsMontagePreparationCoordinator,
)
from XBrainLab.backend.application.bids_montage_preparation import (
    AggregateMontageCompatibility,
    BidsMontageRecordingRequest,
    BidsMontageResourceReceipt,
    MontagePreparationSnapshot,
    RecordingMontagePreparation,
)
from XBrainLab.backend.application.montage_preparation_lifecycle import (
    ManualMontageOverride,
)


def _request(path: str) -> BidsMontageRecordingRequest:
    return BidsMontageRecordingRequest(
        recording_path=path,
        channel_names=("Cz",),
    )


def _empty_receipt(recordings) -> BidsMontageResourceReceipt:
    return BidsMontageResourceReceipt(
        recording_resources=tuple(
            (str(Path(item.recording_path).resolve()), ()) for item in recordings
        )
    )


def _ready(recordings, *, generation: int) -> MontagePreparationSnapshot:
    requested = tuple(item.recording_path for item in recordings)
    return MontagePreparationSnapshot(
        state="ready",
        generation=generation,
        requested_recording_paths=requested,
        recordings=tuple(
            RecordingMontagePreparation(
                recording_path=item.recording_path,
                state="ready",
                recording_channel_names=item.channel_names,
                channel_names=("Cz",),
                positions_m=((0.0, 0.0, 0.1),),
                coordinate_system="CapTrak",
                coordinate_frame="head",
                coordinate_units="m",
                source_coordinate_units="m",
            )
            for item in recordings
        ),
        aggregate=AggregateMontageCompatibility(
            compatible=True,
            channel_names=("Cz",),
            positions_m=((0.0, 0.0, 0.1),),
            coordinate_frame="head",
            coordinate_units="m",
        ),
    )


def test_coordinator_does_not_start_idle_worker_during_construction() -> None:
    coordinator = BidsMontagePreparationCoordinator()
    try:
        assert coordinator._worker is None
    finally:
        coordinator.close()


def test_worker_start_failure_is_terminal_and_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_thread = Thread
    attempts = 0
    published: list[MontagePreparationSnapshot] = []

    class _UnstartedThread:
        def start(self) -> None:
            raise RuntimeError("fault injection: thread start failed")

        @staticmethod
        def is_alive() -> bool:
            return False

        @staticmethod
        def join(*, timeout: float | None = None) -> None:
            del timeout
            pytest.fail("an unstarted montage worker must not be retained or joined")

    def thread_factory(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return _UnstartedThread()
        return real_thread(*args, **kwargs)

    monkeypatch.setattr(bids_montage_coordinator, "Thread", thread_factory)
    coordinator = BidsMontagePreparationCoordinator(
        prepare=lambda recordings, *, generation, **_kwargs: _ready(
            recordings,
            generation=generation,
        ),
        admit=_empty_receipt,
        on_publication=published.append,
    )
    try:
        failed = coordinator.start((_request("/tmp/start-failed_eeg.fif"),))

        assert failed.state == "failed"
        assert failed.import_blocking is False
        assert failed.reason is not None and "RuntimeError" in failed.reason
        assert {item.state for item in failed.recordings} == {"failed"}
        assert coordinator.snapshot() == failed
        assert coordinator.worker_thread is None
        assert coordinator.wait_for_idle(timeout=0.0)
        assert [item.state for item in published] == ["failed"]

        retried = coordinator.start((_request("/tmp/retry_eeg.fif"),))

        assert retried.state == "pending"
        assert coordinator.wait_for_idle(timeout=2.0)
        assert coordinator.snapshot().state == "ready"
        assert [item.state for item in published] == ["failed", "ready"]
    finally:
        assert coordinator.close(timeout=2.0)


def test_application_service_closes_after_montage_worker_start_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from XBrainLab.backend.application.service import ApplicationService
    from XBrainLab.backend.study import Study

    class _UnstartedThread:
        def start(self) -> None:
            raise RuntimeError("fault injection: thread start failed")

        @staticmethod
        def is_alive() -> bool:
            return False

        @staticmethod
        def join(*, timeout: float | None = None) -> None:
            del timeout
            pytest.fail("application close must not join an unstarted montage worker")

    monkeypatch.setattr(
        bids_montage_coordinator,
        "Thread",
        lambda *_args, **_kwargs: _UnstartedThread(),
    )
    service = ApplicationService(Study())
    try:
        failed = service.bids_montage_preparation.start(
            (_request("/tmp/service-close-start-failed_eeg.fif"),)
        )

        assert failed.state == "failed"
        assert service.bids_montage_preparation.worker_thread is None
        service.close()
        assert service.is_closed is True
    finally:
        if not service.is_closed:
            service.close()


def test_coordinator_publishes_latest_ready_result_without_blocking_start() -> None:
    release = Event()
    published: list[MontagePreparationSnapshot] = []

    def prepare(recordings, *, generation, **_kwargs):
        release.wait(timeout=2.0)
        return _ready(recordings, generation=generation)

    coordinator = BidsMontagePreparationCoordinator(
        prepare=prepare,
        admit=_empty_receipt,
        on_publication=published.append,
    )
    try:
        pending = coordinator.start((_request("/tmp/sub-01_eeg.fif"),))
        assert pending.state == "pending"
        assert published == []

        release.set()
        assert coordinator.wait_for_idle(timeout=2.0)
        assert [item.state for item in published] == ["ready"]
        assert coordinator.effective_montage() is not None
    finally:
        coordinator.close()


def test_coordinator_supplies_admitted_resources_to_background_parser(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    eeg_dir = root / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    (root / "dataset_description.json").write_text(
        json.dumps({"Name": "receipt-test", "BIDSVersion": "1.11.1"}),
        encoding="utf-8",
    )
    recording = eeg_dir / "sub-01_task-rest_eeg.fif"
    recording.write_bytes(b"recording identity only")
    electrodes = eeg_dir / "sub-01_task-rest_electrodes.tsv"
    electrodes.write_text("name\tx\ty\tz\nCz\t0\t0\t1\n", encoding="utf-8")
    coordsystem = eeg_dir / "sub-01_task-rest_coordsystem.json"
    coordsystem.write_text(
        json.dumps(
            {
                "EEGCoordinateSystem": "CapTrak",
                "EEGCoordinateUnits": "m",
            }
        ),
        encoding="utf-8",
    )
    admitted = []

    def prepare(
        recordings,
        *,
        generation: int,
        resource_reader=None,
        resource_receipt=None,
    ):
        admitted.append((resource_reader, resource_receipt))
        return _ready(recordings, generation=generation)

    coordinator = BidsMontagePreparationCoordinator(prepare=prepare)
    try:
        coordinator.start((_request(str(recording)),))

        assert coordinator.wait_for_idle(timeout=2.0)
        assert len(admitted) == 1
        resource_reader, resource_receipt = admitted[0]
        assert resource_reader is not None
        assert resource_reader.admits(electrodes)
        assert resource_reader.admits(coordsystem)
        assert resource_receipt is not None
    finally:
        coordinator.close()


def test_default_coordinator_consumes_registered_index_without_tree_rewalk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "bids"
    eeg_dir = root / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    (root / "dataset_description.json").write_text(
        json.dumps({"Name": "indexed-montage", "BIDSVersion": "1.11.1"}),
        encoding="utf-8",
    )
    recording = eeg_dir / "sub-01_task-rest_eeg.fif"
    recording.write_bytes(b"recording identity only")
    (eeg_dir / "sub-01_task-rest_electrodes.tsv").write_text(
        "name\tx\ty\tz\nCz\t0\t0\t1\n",
        encoding="utf-8",
    )
    (eeg_dir / "sub-01_task-rest_coordsystem.json").write_text(
        json.dumps(
            {
                "EEGCoordinateSystem": "CapTrak",
                "EEGCoordinateUnits": "m",
            }
        ),
        encoding="utf-8",
    )
    build_bids_dataset_index(root)

    def _forbid_rewalk(_path: Path):
        pytest.fail("default montage coordinator re-walked the BIDS dataset")

    monkeypatch.setattr(Path, "iterdir", _forbid_rewalk)
    coordinator = BidsMontagePreparationCoordinator()
    try:
        coordinator.start((_request(str(recording)),))

        assert coordinator.wait_for_idle(timeout=2.0)
        assert coordinator.snapshot().state == "ready"
    finally:
        coordinator.close()


def test_coordinator_owns_loaded_recording_request_conversion() -> None:
    captured: list[tuple[BidsMontageRecordingRequest, ...]] = []

    def prepare(recordings, *, generation, **_kwargs):
        captured.append(tuple(recordings))
        return _ready(recordings, generation=generation)

    mne_data = SimpleNamespace(
        ch_names=["C3", "C4"],
        get_channel_types=lambda: ["eeg", "eeg"],
    )
    loaded = SimpleNamespace(
        get_filepath=lambda: "/tmp/sub-01_eeg.fif",
        get_mne=lambda: mne_data,
    )
    coordinator = BidsMontagePreparationCoordinator(
        prepare=prepare,
        admit=_empty_receipt,
    )
    try:
        pending = coordinator.synchronize_loaded_recordings((loaded,))

        assert pending.state == "pending"
        assert coordinator.wait_for_idle(timeout=2.0)
        assert captured[0][0].channel_names == ("C3", "C4")
        assert captured[0][0].channel_types == ("eeg", "eeg")
    finally:
        assert coordinator.close(timeout=2.0)


def test_loaded_recording_conversion_failure_invalidates_previous_montage() -> None:
    coordinator = BidsMontagePreparationCoordinator(admit=_empty_receipt)
    coordinator.select_manual(
        ManualMontageOverride(
            name="manual",
            channel_names=("Cz",),
            positions_m=((0.0, 0.0, 0.1),),
            coordinate_frame="head",
        )
    )
    previous_generation = coordinator.snapshot().generation
    broken = SimpleNamespace(
        get_filepath=lambda: "/tmp/replacement.fif",
        get_mne=lambda: (_ for _ in ()).throw(RuntimeError("broken recording")),
    )

    try:
        with pytest.raises(RuntimeError, match="broken recording"):
            coordinator.synchronize_loaded_recordings((broken,))

        assert coordinator.snapshot().generation > previous_generation
        assert coordinator.effective_montage() is None
        assert coordinator.wait_for_idle(timeout=0.1)
    finally:
        coordinator.close()


def test_loaded_recording_conversion_rejects_partial_inventory() -> None:
    valid_mne = SimpleNamespace(
        ch_names=["C3", "C4"],
        get_channel_types=lambda: ["eeg", "eeg"],
    )
    valid = SimpleNamespace(
        get_filepath=lambda: "/tmp/valid.fif",
        get_mne=lambda: valid_mne,
    )
    malformed = SimpleNamespace(get_filepath=lambda: "/tmp/malformed.fif")
    coordinator = BidsMontagePreparationCoordinator(admit=_empty_receipt)

    try:
        with pytest.raises(ValueError, match="loaded recording"):
            coordinator.synchronize_loaded_recordings((valid, malformed))

        assert coordinator.snapshot().state == "not_applicable"
        assert coordinator.effective_montage() is None
        assert coordinator.worker_thread is None
    finally:
        coordinator.close()


def test_new_request_and_manual_selection_reject_stale_background_results() -> None:
    first_started = Event()
    release = Event()
    published: list[MontagePreparationSnapshot] = []
    parsed_paths: list[str] = []

    def prepare(recordings, *, generation, **_kwargs):
        parsed_paths.append(recordings[0].recording_path)
        if generation == 1:
            first_started.set()
        release.wait(timeout=2.0)
        return _ready(recordings, generation=generation)

    coordinator = BidsMontagePreparationCoordinator(
        prepare=prepare,
        admit=_empty_receipt,
        on_publication=published.append,
    )
    try:
        coordinator.start((_request("/tmp/sub-01_eeg.fif"),))
        assert first_started.wait(timeout=2.0)
        coordinator.start((_request("/tmp/sub-02_eeg.fif"),))
        coordinator.select_manual(
            ManualMontageOverride(
                name="standard_1020",
                channel_names=("Cz",),
                positions_m=((0.0, 0.0, 0.09),),
                coordinate_frame="head",
            )
        )
        release.set()

        assert coordinator.wait_for_idle(timeout=2.0)
        assert published == []
        assert parsed_paths == [str(Path("/tmp/sub-01_eeg.fif").resolve())]
        effective = coordinator.effective_montage()
        assert effective is not None
        assert effective.source == "manual"
        assert effective.name == "standard_1020"
    finally:
        coordinator.close()


def test_latest_import_reset_and_manual_race_keeps_manual_precedence() -> None:
    first_started = Event()
    release_first = Event()
    parsed_paths: list[str] = []

    def prepare(recordings, *, generation, **_kwargs):
        parsed_paths.append(recordings[0].recording_path)
        if len(parsed_paths) == 1:
            first_started.set()
            assert release_first.wait(timeout=2.0)
        return _ready(recordings, generation=generation)

    coordinator = BidsMontagePreparationCoordinator(
        prepare=prepare,
        admit=_empty_receipt,
    )
    try:
        coordinator.start((_request("/tmp/sub-01_eeg.fif"),))
        assert first_started.wait(timeout=2.0)
        coordinator.start((_request("/tmp/sub-02_eeg.fif"),))
        coordinator.reset()
        coordinator.start((_request("/tmp/sub-03_eeg.fif"),))
        coordinator.select_manual(
            ManualMontageOverride(
                name="manual-latest",
                channel_names=("Cz",),
                positions_m=((0.0, 0.0, 0.09),),
                coordinate_frame="head",
            )
        )
        release_first.set()

        assert coordinator.wait_for_idle(timeout=2.0)
        assert parsed_paths == [str(Path("/tmp/sub-01_eeg.fif").resolve())]
        effective = coordinator.effective_montage()
        assert effective is not None
        assert effective.source == "manual"
        assert effective.name == "manual-latest"
    finally:
        release_first.set()
        coordinator.close()


def test_repeated_start_coalesces_obsolete_queued_generation() -> None:
    first_started = Event()
    release_first = Event()
    parsed_paths: list[str] = []

    def prepare(recordings, *, generation, **_kwargs):
        parsed_paths.append(recordings[0].recording_path)
        if generation == 1:
            first_started.set()
            release_first.wait(timeout=2.0)
        return _ready(recordings, generation=generation)

    coordinator = BidsMontagePreparationCoordinator(
        prepare=prepare,
        admit=_empty_receipt,
    )
    try:
        coordinator.start((_request("/tmp/sub-01_eeg.fif"),))
        assert first_started.wait(timeout=2.0)
        coordinator.start((_request("/tmp/sub-02_eeg.fif"),))
        coordinator.start((_request("/tmp/sub-03_eeg.fif"),))
        release_first.set()

        assert coordinator.wait_for_idle(timeout=2.0)
        assert parsed_paths == [
            str(Path("/tmp/sub-01_eeg.fif").resolve()),
            str(Path("/tmp/sub-03_eeg.fif").resolve()),
        ]
        assert coordinator.snapshot().requested_recording_paths == (
            str(Path("/tmp/sub-03_eeg.fif").resolve()),
        )
    finally:
        coordinator.close()


def test_reset_discards_queued_generation_before_parser_entry() -> None:
    first_started = Event()
    release_first = Event()
    parsed_paths: list[str] = []

    def prepare(recordings, *, generation, **_kwargs):
        parsed_paths.append(recordings[0].recording_path)
        if generation == 1:
            first_started.set()
            release_first.wait(timeout=2.0)
        return _ready(recordings, generation=generation)

    coordinator = BidsMontagePreparationCoordinator(
        prepare=prepare,
        admit=_empty_receipt,
    )
    try:
        first_path = "/tmp/sub-01_eeg.fif"
        second_path = "/tmp/sub-02_eeg.fif"
        coordinator.start((_request(first_path),))
        assert first_started.wait(timeout=2.0)
        coordinator.start((_request(second_path),))

        coordinator.reset()
        release_first.set()

        assert coordinator.wait_for_idle(timeout=2.0)
        assert parsed_paths == [str(Path(first_path).resolve())]
        assert coordinator.snapshot().state == "not_applicable"
    finally:
        coordinator.close()


def test_unexpected_parser_failure_becomes_nonblocking_failed_snapshot() -> None:
    published: list[MontagePreparationSnapshot] = []

    def prepare(_recordings, *, generation, **_kwargs):
        del generation
        raise RuntimeError("parser failure")

    coordinator = BidsMontagePreparationCoordinator(
        prepare=prepare,
        admit=_empty_receipt,
        on_publication=published.append,
    )
    try:
        coordinator.start((_request("/tmp/sub-01_eeg.fif"),))

        assert coordinator.wait_for_idle(timeout=2.0)
        assert [item.state for item in published] == ["failed"]
        assert published[0].import_blocking is False
        assert "RuntimeError" in str(published[0].reason)
    finally:
        coordinator.close()


def test_application_commit_callback_owns_generation_publication() -> None:
    release = Event()
    commits: list[tuple[int, bool]] = []
    coordinator: BidsMontagePreparationCoordinator

    def prepare(recordings, *, generation, **_kwargs):
        release.wait(timeout=2.0)
        return _ready(recordings, generation=generation)

    def commit(work, result) -> None:
        promoted = coordinator.promote_result(
            work,
            result,
            refresh_candidate=lambda: None,
        )
        commits.append((work.generation, promoted))

    coordinator = BidsMontagePreparationCoordinator(
        prepare=prepare,
        admit=_empty_receipt,
        commit_publication=commit,
    )
    try:
        coordinator.start((_request("/tmp/sub-01_eeg.fif"),))
        release.set()

        assert coordinator.wait_for_idle(timeout=2.0)
        assert commits == [(1, True)]
        assert coordinator.snapshot().state == "ready"
    finally:
        coordinator.close()


def test_close_discards_running_result_without_callback() -> None:
    started = Event()
    release = Event()
    commits: list[int] = []

    def prepare(recordings, *, generation, **_kwargs):
        started.set()
        release.wait(timeout=2.0)
        return _ready(recordings, generation=generation)

    coordinator = BidsMontagePreparationCoordinator(
        prepare=prepare,
        admit=_empty_receipt,
        commit_publication=lambda work, _result: commits.append(work.generation),
    )
    coordinator.start((_request("/tmp/sub-01_eeg.fif"),))
    assert started.wait(timeout=2.0)

    assert coordinator.close(timeout=0.0) is False
    release.set()

    assert coordinator.wait_for_idle(timeout=2.0)
    assert commits == []
    assert coordinator.snapshot().state == "not_applicable"
    assert coordinator.close(timeout=2.0)


def test_worker_exits_after_queue_becomes_idle() -> None:
    coordinator = BidsMontagePreparationCoordinator(
        prepare=lambda recordings, *, generation, **_kwargs: _ready(
            recordings,
            generation=generation,
        ),
        admit=_empty_receipt,
        commit_publication=lambda work, result: coordinator.promote_result(
            work,
            result,
            refresh_candidate=lambda: None,
        ),
    )

    coordinator.start((_request("/tmp/sub-01_eeg.fif"),))

    assert coordinator.wait_for_idle(timeout=2.0)
    assert coordinator.worker_thread is None
