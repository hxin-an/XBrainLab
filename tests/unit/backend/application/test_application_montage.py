"""Application boundary: montage behavior."""

from __future__ import annotations

from threading import Event
from typing import Any, cast
from unittest.mock import MagicMock

import numpy as np
import pytest

from tests.unit.backend.application.application_test_support import (
    _positive_epoch_data,
    _raw_mock,
)
from XBrainLab.backend.application import (
    ApplicationService,
    ApplyMontageCommand,
    ClearDatasetsCommand,
    CommandName,
    RemoveFilesCommand,
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
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import (
    Trainer,
)


def test_apply_montage_command_routes_confirmed_positions():
    service = ApplicationService(Study())
    raw = _raw_mock()
    raw.get_mne.return_value.ch_names = ["C3", "Cz", "C4"]
    service.study.data_manager.loaded_data_list = [raw]

    result = service.execute(
        ApplyMontageCommand(
            channels=["C3", "Cz", "C4"],
            positions=[(-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)],
            montage_name="standard_1020",
        ),
    )

    assert result.ok is True
    assert result.command_name == CommandName.APPLY_MONTAGE.value
    effective = service.bids_montage_preparation.effective_montage()
    assert effective is not None
    assert effective.channel_names == ("C3", "Cz", "C4")


@pytest.mark.parametrize(
    ("command", "name"),
    [
        (RemoveFilesCommand(indices=[0]), CommandName.REMOVE_FILES),
    ],
)
def test_data_inventory_changes_refresh_optional_montage_preparation(
    command,
    name,
) -> None:
    service = ApplicationService(Study())
    raw = _raw_mock()
    raw.get_mne.return_value.get_channel_types.return_value = ["eeg", "eeg"]
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw])
    coordinator = MagicMock()
    coordinator.synchronize_loaded_recordings.return_value = (
        MontagePreparationSnapshot.pending(
            generation=1,
            recording_paths=("/tmp/sample.fif",),
        )
    )
    service.bids_montage_preparation = coordinator

    diagnostics = service._update_montage_preparation_after_command(
        command=command,
        name=name,
        diagnostics={},
    )

    coordinator.synchronize_loaded_recordings.assert_called_once_with([raw])
    assert diagnostics["montage_preparation"]["state"] == "pending"


def test_clear_datasets_preserves_epoch_scoped_manual_montage() -> None:
    service = ApplicationService(Study())
    service.study.data_manager.epoch_data = _positive_epoch_data()
    service.study.data_manager.datasets = [MagicMock()]
    service.bids_montage_preparation.select_manual(
        ManualMontageOverride(
            name="manual",
            channel_names=("C3", "C4"),
            positions_m=((0.0, 0.1, 0.0), (0.0, -0.1, 0.0)),
            coordinate_frame="head",
        )
    )
    service.get_state()

    result = service.execute(ClearDatasetsCommand(confirmed=True))

    assert result.ok is True
    assert result.state.dataset.available is False
    assert result.state.epoch.available is True
    assert result.state.visualization.montage_source == "manual"
    effective = service.bids_montage_preparation.effective_montage()
    assert effective is not None
    assert effective.source == "manual"
    service.close()


def test_bids_montage_refresh_failure_retains_candidate_until_view_recovers() -> None:
    service = ApplicationService(Study())
    service.study.data_manager.epoch_data = _positive_epoch_data()
    service.get_state()
    request = BidsMontageRecordingRequest(
        recording_path="/tmp/sub-01_task-rest_eeg.fif",
        channel_names=("C3", "C4"),
        channel_types=("eeg", "eeg"),
    )

    def admit(recordings) -> BidsMontageResourceReceipt:
        return BidsMontageResourceReceipt(
            recording_resources=tuple((item.recording_path, ()) for item in recordings)
        )

    def prepare(recordings, *, generation, **_kwargs):
        paths = tuple(item.recording_path for item in recordings)
        return MontagePreparationSnapshot(
            state="ready",
            generation=generation,
            requested_recording_paths=paths,
            recordings=tuple(
                RecordingMontagePreparation(
                    recording_path=item.recording_path,
                    state="ready",
                    recording_channel_names=item.channel_names,
                    channel_names=item.channel_names,
                    positions_m=((0.1, 0.0, 0.0), (-0.1, 0.0, 0.0)),
                    coordinate_system="CapTrak",
                    coordinate_frame="head",
                    coordinate_units="m",
                    source_coordinate_units="m",
                )
                for item in recordings
            ),
            aggregate=AggregateMontageCompatibility(
                compatible=True,
                channel_names=("C3", "C4"),
                positions_m=((0.1, 0.0, 0.0), (-0.1, 0.0, 0.0)),
                coordinate_frame="head",
                coordinate_units="m",
            ),
        )

    service.bids_montage_preparation._admit = admit
    service.bids_montage_preparation._prepare = prepare
    build_state = service.state_snapshot.build
    refresh_attempted = Event()
    attempt_count = 0

    def fail_once(*args, **kwargs):
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count == 1:
            refresh_attempted.set()
            raise RuntimeError("forced montage refresh failure")
        return build_state(*args, **kwargs)

    service.state_snapshot.build = fail_once
    pending = service.bids_montage_preparation.start((request,))
    assert pending.state == "pending"
    assert refresh_attempted.wait(timeout=2.0)
    assert service.bids_montage_preparation.wait_for_idle(timeout=2.0)

    failed_view = service._committed_view_publication()
    assert failed_view.usable is False
    assert service.bids_montage_preparation.snapshot().state == "pending"

    recovered = service.get_view_publication()

    assert recovered.usable is True
    assert recovered.state.visualization.montage_preparation_state == "ready"
    assert recovered.state.visualization.montage_source == "bids"
    assert service.bids_montage_preparation.snapshot().state == "ready"
    service.close()


def test_apply_montage_rejects_partial_layout_without_changing_epoch_identity():
    class EpochWithChannels:
        def __init__(self) -> None:
            self.channels = ["C3", "C4"]

        def get_channel_names(self) -> list[str]:
            return list(self.channels)

        def set_channels(self, channels, _positions) -> None:
            self.channels = list(channels)

        def set_channel_positions(self, positions) -> None:
            self.positions = dict(positions)

    study = Study()
    epoch = EpochWithChannels()
    study.data_manager.epoch_data = cast(Any, epoch)
    raw = _raw_mock()
    study.data_manager.loaded_data_list = [raw]
    service = ApplicationService(study)

    result = service.execute(
        ApplyMontageCommand(
            channels=["C3"],
            positions=[(0.0, 0.0, 1.0)],
        ),
    )

    assert result.failed is True
    assert epoch.channels == ["C3", "C4"]
    assert not hasattr(epoch, "positions")


def test_apply_montage_rejects_partial_current_channel_mapping_atomically() -> None:
    study = Study()
    raw = _raw_mock()
    raw.get_mne.return_value.ch_names = ["C3", "Cz", "C4"]
    study.data_manager.loaded_data_list = [raw]
    service = ApplicationService(study)
    service.bids_montage_preparation.select_manual(
        ManualMontageOverride(
            name="existing",
            channel_names=("C3",),
            positions_m=((0.0, 0.0, 1.0),),
            coordinate_frame="head",
        )
    )

    result = service.execute(
        ApplyMontageCommand(
            channels=["C3", "Cz"],
            electrode_names=["C3", "Cz"],
            positions=[(-1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        )
    )

    assert result.failed is True
    effective = service.bids_montage_preparation.effective_montage()
    assert effective is not None
    assert effective.name == "existing"


def test_apply_montage_accepts_complete_topographic_current_channel_mapping() -> None:
    study = Study()
    raw = _raw_mock()
    raw.get_mne.return_value.ch_names = ["C3", "Cz", "C4"]
    study.data_manager.loaded_data_list = [raw]
    service = ApplicationService(study)

    result = service.execute(
        ApplyMontageCommand(
            channels=["C3", "Cz", "C4"],
            electrode_names=["C3", "Cz", "C4"],
            positions=[(-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)],
        )
    )

    assert result.ok is True
    effective = service.bids_montage_preparation.effective_montage()
    assert effective is not None
    assert effective.channel_names == ("C3", "Cz", "C4")


def test_restore_bids_rejects_partial_retained_geometry_atomically() -> None:
    study = Study()
    raw = _raw_mock()
    raw.get_mne.return_value.ch_names = ["C3", "Cz", "C4"]
    study.data_manager.loaded_data_list = [raw]
    service = ApplicationService(study)
    request = BidsMontageRecordingRequest(
        recording_path="/tmp/sub-01_task-rest_eeg.fif",
        channel_names=("C3", "Cz"),
        channel_types=("eeg", "eeg"),
    )
    work = service.bids_montage_preparation._lifecycle.begin((request,))
    admitted_request = work.recordings[0]
    retained = MontagePreparationSnapshot(
        state="ready",
        generation=work.generation,
        requested_recording_paths=(admitted_request.recording_path,),
        recordings=(
            RecordingMontagePreparation(
                recording_path=admitted_request.recording_path,
                state="ready",
                recording_channel_names=request.channel_names,
                channel_names=request.channel_names,
                positions_m=((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
                coordinate_system="CapTrak",
                coordinate_frame="head",
                coordinate_units="m",
                source_coordinate_units="m",
            ),
        ),
        aggregate=AggregateMontageCompatibility(
            compatible=True,
            channel_names=request.channel_names,
            positions_m=((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
            coordinate_frame="head",
            coordinate_units="m",
        ),
    )
    assert service.bids_montage_preparation._lifecycle.publish(work, retained).accepted
    assert service.execute(
        ApplyMontageCommand(
            channels=["C3", "Cz", "C4"],
            electrode_names=["C3", "Cz", "C4"],
            positions=[
                (-1.0, 0.0, 0.0),
                (0.0, 1.0, 0.0),
                (1.0, 0.0, 0.0),
            ],
        )
    ).ok
    before_snapshot = service.bids_montage_preparation.snapshot()
    before_effective = service.bids_montage_preparation.effective_montage()

    result = service.execute(ApplyMontageCommand(restore_bids=True))

    assert result.failed is True
    assert service.bids_montage_preparation.snapshot() == before_snapshot
    assert service.bids_montage_preparation.effective_montage() == before_effective


def test_restore_bids_accepts_complete_retained_topographic_geometry() -> None:
    study = Study()
    raw = _raw_mock()
    raw.get_mne.return_value.ch_names = ["C3", "Cz", "C4"]
    study.data_manager.loaded_data_list = [raw]
    service = ApplicationService(study)
    request = BidsMontageRecordingRequest(
        recording_path="/tmp/sub-01_task-rest_eeg.fif",
        channel_names=("C3", "Cz", "C4"),
        channel_types=("eeg", "eeg", "eeg"),
    )
    positions = ((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0))
    work = service.bids_montage_preparation._lifecycle.begin((request,))
    admitted_request = work.recordings[0]
    retained = MontagePreparationSnapshot(
        state="ready",
        generation=work.generation,
        requested_recording_paths=(admitted_request.recording_path,),
        recordings=(
            RecordingMontagePreparation(
                recording_path=admitted_request.recording_path,
                state="ready",
                recording_channel_names=request.channel_names,
                channel_names=request.channel_names,
                positions_m=positions,
                coordinate_system="CapTrak",
                coordinate_frame="head",
                coordinate_units="m",
                source_coordinate_units="m",
            ),
        ),
        aggregate=AggregateMontageCompatibility(
            compatible=True,
            channel_names=request.channel_names,
            positions_m=positions,
            coordinate_frame="head",
            coordinate_units="m",
        ),
    )
    assert service.bids_montage_preparation._lifecycle.publish(work, retained).accepted
    assert service.execute(
        ApplyMontageCommand(
            channels=list(request.channel_names),
            electrode_names=list(request.channel_names),
            positions=list(positions),
        )
    ).ok

    result = service.execute(ApplyMontageCommand(restore_bids=True))

    assert result.ok is True
    effective = service.bids_montage_preparation.effective_montage()
    assert effective is not None
    assert effective.source == "bids"
    assert effective.channel_names == request.channel_names


def test_apply_montage_malformed_epoch_keeps_existing_layout_atomic() -> None:
    class MalformedEpoch:
        def get_channel_names(self) -> list[str]:
            return ["C3", "C4"]

        def get_data(self):
            return np.zeros((2, 10))

    study = Study()
    raw = _raw_mock()
    study.data_manager.loaded_data_list = [raw]
    study.data_manager.epoch_data = MalformedEpoch()
    service = ApplicationService(study)
    service.bids_montage_preparation.select_manual(
        ManualMontageOverride(
            name="existing",
            channel_names=("C3",),
            positions_m=((0.0, 0.0, 0.0),),
            coordinate_frame="head",
        )
    )

    result = service.execute(
        ApplyMontageCommand(channels=["C4"], positions=[(0.1, 0.2, 0.3)])
    )

    assert result.failed is True
    assert service.bids_montage_preparation.effective_montage().name == "existing"


@pytest.mark.parametrize(
    "command",
    [
        ApplyMontageCommand(channels=["C3", "C3"], positions=[(0, 0, 0), (0, 0, 0)]),
        ApplyMontageCommand(
            channels=["C3"], positions=[(0, 0, 0)], electrode_names=[""]
        ),
        ApplyMontageCommand(
            channels=["C3", "C4"],
            positions=[(0, 0, 0), (0, 0, 0)],
            electrode_names=["Cz", "Cz"],
        ),
        ApplyMontageCommand(channels=[" C3"], positions=[(0, 0, 0)]),
        ApplyMontageCommand(channels=["C3"], positions=[(float("nan"), 0, 0)]),
        ApplyMontageCommand(channels=["C3"], positions=[(float("inf"), 0, 0)]),
        ApplyMontageCommand(channels=["C3"], positions=[(0, 0, 0)], electrode_names=[]),
    ],
)
def test_invalid_montage_payload_preserves_existing_effective_layout(command) -> None:
    study = Study()
    study.data_manager.loaded_data_list = [_raw_mock()]
    service = ApplicationService(study)
    service.bids_montage_preparation.select_manual(
        ManualMontageOverride(
            name="existing",
            channel_names=("C4",),
            positions_m=((0.1, 0.2, 0.3),),
            coordinate_frame="head",
        )
    )

    result = service.execute(command)

    assert result.failed is True
    effective = service.bids_montage_preparation.effective_montage()
    assert effective is not None
    assert effective.name == "existing"
    assert effective.channel_names == ("C4",)
    assert effective.positions_m == ((0.1, 0.2, 0.3),)


def test_apply_montage_trainer_allows_first_attach_then_freezes_layout() -> None:
    study = Study()
    raw = _raw_mock()
    raw.get_mne.return_value.ch_names = ["C3", "Cz", "C4"]
    study.data_manager.loaded_data_list = [raw]
    study.training_manager.trainer = Trainer([])
    service = ApplicationService(study)
    command = ApplyMontageCommand(
        channels=["C3", "Cz", "C4"],
        positions=[(-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)],
        montage_name="first",
    )

    first = service.execute(command)
    exact = service.execute(command)
    replacement = service.execute(
        ApplyMontageCommand(
            channels=["C3", "Cz", "C4"],
            positions=[(-0.9, 0.0, 0.0), (0.0, 1.1, 0.0), (0.9, 0.0, 0.0)],
            montage_name="other",
        )
    )

    assert first.ok is True
    assert exact.ok is True
    assert exact.diagnostics["layout_noop"] is True
    assert replacement.failed is True
    effective = service.bids_montage_preparation.effective_montage()
    assert effective is not None
    assert effective.channel_names == ("C3", "Cz", "C4")


def _service_with_retained_bids_layout() -> ApplicationService:
    study = Study()
    raw = _raw_mock()
    raw.get_mne.return_value.ch_names = ["C3", "Cz", "C4"]
    study.data_manager.loaded_data_list = [raw]
    epoch = _positive_epoch_data()
    epoch.data = np.zeros((len(epoch.label), 3, 16), dtype=np.float32)
    epoch.ch_names = ["C3", "Cz", "C4"]
    study.data_manager.epoch_data = epoch
    service = ApplicationService(study)
    request = BidsMontageRecordingRequest(
        recording_path="/tmp/sub-01_task-rest_eeg.fif",
        channel_names=("C3", "Cz", "C4"),
        channel_types=("eeg", "eeg", "eeg"),
    )
    work = service.bids_montage_preparation._lifecycle.begin((request,))
    admitted_request = work.recordings[0]
    snapshot = MontagePreparationSnapshot(
        state="ready",
        generation=work.generation,
        requested_recording_paths=(admitted_request.recording_path,),
        recordings=(
            RecordingMontagePreparation(
                recording_path=admitted_request.recording_path,
                state="ready",
                recording_channel_names=request.channel_names,
                channel_names=request.channel_names,
                positions_m=((-0.1, 0.0, 0.0), (0.0, 0.1, 0.0), (0.1, 0.0, 0.0)),
                coordinate_system="CapTrak",
                coordinate_frame="head",
                coordinate_units="m",
                source_coordinate_units="m",
            ),
        ),
        aggregate=AggregateMontageCompatibility(
            compatible=True,
            channel_names=request.channel_names,
            positions_m=((-0.1, 0.0, 0.0), (0.0, 0.1, 0.0), (0.1, 0.0, 0.0)),
            coordinate_frame="head",
            coordinate_units="m",
        ),
    )
    assert service.bids_montage_preparation._lifecycle.publish(work, snapshot).accepted
    manual = service.execute(
        ApplyMontageCommand(
            channels=["C3", "Cz", "C4"],
            positions=[(-0.1, 0.0, 0.0), (0.0, -0.1, 0.0), (0.1, 0.0, 0.0)],
            montage_name="manual",
        )
    )
    assert manual.ok
    return service


def test_restore_bids_rejects_mixed_manual_payload_without_replacing_manual() -> None:
    service = _service_with_retained_bids_layout()
    try:
        result = service.execute(
            ApplyMontageCommand(
                channels=["C3"],
                positions=[(0.0, 0.0, 0.1)],
                restore_bids=True,
            )
        )

        assert result.failed is True
        assert service.bids_montage_preparation.effective_montage().source == "manual"  # type: ignore[union-attr]
    finally:
        service.close()


def test_restore_bids_without_snapshot_preserves_manual_layout() -> None:
    study = Study()
    raw = _raw_mock()
    raw.get_mne.return_value.ch_names = ["C3", "Cz", "C4"]
    study.data_manager.loaded_data_list = [raw]
    epoch = _positive_epoch_data()
    epoch.data = np.zeros((len(epoch.label), 3, 16), dtype=np.float32)
    epoch.ch_names = ["C3", "Cz", "C4"]
    study.data_manager.epoch_data = epoch
    service = ApplicationService(study)
    try:
        assert service.execute(
            ApplyMontageCommand(
                channels=["C3", "Cz", "C4"],
                positions=[(-0.1, 0.0, 0.0), (0.0, 0.1, 0.0), (0.1, 0.0, 0.0)],
                montage_name="manual",
            )
        ).ok

        result = service.execute(ApplyMontageCommand(restore_bids=True))

        assert result.failed is True
        assert service.bids_montage_preparation.effective_montage().source == "manual"  # type: ignore[union-attr]
    finally:
        service.close()


def test_restore_bids_is_blocked_by_trainer_without_replacing_manual() -> None:
    service = _service_with_retained_bids_layout()
    service.study.training_manager.trainer = Trainer([])
    try:
        result = service.execute(ApplyMontageCommand(restore_bids=True))

        assert result.failed is True
        assert service.bids_montage_preparation.effective_montage().source == "manual"  # type: ignore[union-attr]
    finally:
        service.close()


def test_restore_bids_publishes_retained_geometry_and_projects_it_to_epoch() -> None:
    service = _service_with_retained_bids_layout()
    try:
        result = service.execute(ApplyMontageCommand(restore_bids=True))

        assert result.ok is True
        assert result.state.electrode_layout.source == "bids"
        effective = service.bids_montage_preparation.effective_montage()
        assert effective is not None
        assert effective.positions_m == (
            (-0.1, 0.0, 0.0),
            (0.0, 0.1, 0.0),
            (0.1, 0.0, 0.0),
        )
        assert service.study.epoch_data.channel_position == [
            (-0.1, 0.0, 0.0),
            (0.0, 0.1, 0.0),
            (0.1, 0.0, 0.0),
        ]
    finally:
        service.close()
