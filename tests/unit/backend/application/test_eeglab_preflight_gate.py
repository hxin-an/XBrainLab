"""Independent semantic gate for bounded EEGLAB SET RAM preflight."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from scipy.io import savemat

from XBrainLab.backend.application.eeglab_set_preflight import (
    MAT_STREAM_CHUNK_BYTES,
    inspect_eeglab_set_header,
)
from XBrainLab.backend.application.resource_guard import (
    ResourceChecker,
    check_import_resource_preflight,
)


class _TrackingBinaryFile:
    """Track physical reads while preserving seek-based bounded inspection."""

    def __init__(self, handle: Any) -> None:
        self._handle = handle
        self.read_sizes: list[int] = []

    def __enter__(self) -> _TrackingBinaryFile:
        self._handle.__enter__()
        return self

    def __exit__(self, *args: object) -> object:
        return self._handle.__exit__(*args)

    def read(self, size: int = -1) -> bytes:
        data = self._handle.read(size)
        self.read_sizes.append(len(data))
        return data

    def __getattr__(self, name: str) -> Any:
        return getattr(self._handle, name)


def _write_embedded_set(
    path: Path,
    *,
    data: np.ndarray,
    compressed: bool,
) -> None:
    savemat(
        path,
        {
            "EEG": {
                "data": data,
                "nbchan": float(data.shape[0]),
                "pnts": float(data.shape[1]),
                "trials": 1.0,
                "srate": 250.0,
            }
        },
        do_compression=compressed,
    )


def _detail_for(path: Path) -> dict[str, Any]:
    estimate = ResourceChecker.estimate_dataset_ram([str(path)])
    return next(row for row in estimate["files"] if row["path"] == str(path))


@pytest.mark.parametrize("compressed", [False, True])
def test_mat_v5_embedded_inspector_reads_only_bounded_header_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    compressed: bool,
) -> None:
    set_path = tmp_path / f"embedded-{compressed}.set"
    signal = np.random.default_rng(20260716).standard_normal(
        (4, 100_000),
        dtype=np.float32,
    )
    _write_embedded_set(set_path, data=signal, compressed=compressed)
    del signal

    original_open = Path.open
    tracked: list[_TrackingBinaryFile] = []

    def _tracking_open(path: Path, *args: Any, **kwargs: Any) -> Any:
        handle = original_open(path, *args, **kwargs)
        if path == set_path:
            wrapper = _TrackingBinaryFile(handle)
            tracked.append(wrapper)
            return wrapper
        return handle

    monkeypatch.setattr(Path, "open", _tracking_open)

    inspection = inspect_eeglab_set_header(set_path)

    assert inspection.bound_known is True
    assert inspection.storage_mode == "embedded"
    assert inspection.source_shape == (4, 100_000)
    assert inspection.source_dtype == "float32"
    assert len(tracked) == 1
    assert sum(tracked[0].read_sizes) <= 128 + 8 + MAT_STREAM_CHUNK_BYTES
    assert sum(tracked[0].read_sizes) < set_path.stat().st_size // 4


def test_external_nested_arbitrary_fdt_reference_uses_exact_sidecar_size(
    tmp_path: Path,
) -> None:
    signal_dir = tmp_path / "Signals"
    signal_dir.mkdir()
    fdt_path = signal_dir / "Run-07-Signal.FdT"
    channels, points, trials = 3, 17, 2
    fdt_path.write_bytes(b"\0" * channels * points * trials * 4)
    set_path = tmp_path / "subject.set"
    savemat(
        set_path,
        {
            "EEG": {
                "data": "signals/run-07-signal.fdt",
                "nbchan": float(channels),
                "pnts": float(points),
                "trials": float(trials),
            }
        },
        do_compression=True,
    )

    inspection = inspect_eeglab_set_header(set_path)
    detail = _detail_for(set_path)

    assert inspection.bound_known is True
    assert inspection.storage_mode == "external"
    assert inspection.external_data_file == str(fdt_path.resolve())
    assert inspection.external_data_file_bytes == fdt_path.stat().st_size
    assert inspection.source_shape == (channels, points, trials)
    assert detail["estimated_raw_bytes"] == fdt_path.stat().st_size * 2
    assert detail["materializes_signal_data"] is False


def test_bids_external_fdt_resolution_uses_index_without_directory_walk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from XBrainLab.backend.application.bids_dataset_index import (
        build_bids_dataset_index,
    )

    eeg_dir = tmp_path / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    (tmp_path / "dataset_description.json").write_text(
        '{"Name":"eeglab","BIDSVersion":"1.11.0"}',
        encoding="utf-8",
    )
    fdt_path = eeg_dir / "sub-01_task-rest_eeg.fdt"
    fdt_path.write_bytes(b"\0" * (2 * 20 * 4))
    set_path = eeg_dir / "sub-01_task-rest_eeg.set"
    savemat(
        set_path,
        {
            "EEG": {
                "data": fdt_path.name,
                "nbchan": 2.0,
                "pnts": 20.0,
                "trials": 1.0,
            }
        },
        do_compression=True,
    )
    build_bids_dataset_index(tmp_path)

    def _forbid_rewalk(_path: Path):
        pytest.fail("EEGLAB dependency resolver walked an indexed BIDS directory")

    monkeypatch.setattr(Path, "iterdir", _forbid_rewalk)

    inspection = inspect_eeglab_set_header(set_path)

    assert inspection.external_data_file == str(fdt_path.resolve())


def test_nested_bids_eeglab_falls_back_when_parent_index_does_not_own_recording(
    tmp_path: Path,
) -> None:
    from XBrainLab.backend.application.bids_dataset_index import (
        build_bids_dataset_index,
    )

    parent_root = tmp_path / "parent-bids"
    nested_root = parent_root / "sourcedata" / "nested-bids"
    eeg_dir = nested_root / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    (parent_root / "dataset_description.json").write_text(
        '{"Name":"parent","BIDSVersion":"1.11.0"}',
        encoding="utf-8",
    )
    (nested_root / "dataset_description.json").write_text(
        '{"Name":"nested","BIDSVersion":"1.11.0"}',
        encoding="utf-8",
    )
    fdt_path = eeg_dir / "sub-01_task-rest_eeg.fdt"
    fdt_path.write_bytes(b"\0" * (2 * 20 * 4))
    set_path = eeg_dir / "sub-01_task-rest_eeg.set"
    savemat(
        set_path,
        {
            "EEG": {
                "data": fdt_path.name,
                "nbchan": 2.0,
                "pnts": 20.0,
                "trials": 1.0,
            }
        },
        do_compression=True,
    )
    parent_index = build_bids_dataset_index(parent_root)
    assert parent_index.contains_recording(set_path) is False

    inspection = inspect_eeglab_set_header(set_path)

    assert inspection.external_data_file == str(fdt_path.resolve())


@pytest.mark.parametrize(
    ("sidecar_bytes", "reason_code", "partial_raw_bytes"),
    [
        (None, "eeglab_external_reference_unsafe", 0),
        (2 * 20 * 4 - 4, "eeglab_external_shape_size_mismatch", 312),
        (2 * 20 * 4 + 4, "eeglab_external_shape_size_mismatch", 328),
    ],
)
def test_missing_or_mismatched_external_sidecar_fails_closed(
    tmp_path: Path,
    sidecar_bytes: int | None,
    reason_code: str,
    partial_raw_bytes: int,
) -> None:
    set_path = tmp_path / "external.set"
    fdt_path = tmp_path / "actual-signal.fdt"
    if sidecar_bytes is not None:
        fdt_path.write_bytes(b"\0" * sidecar_bytes)
    savemat(
        set_path,
        {
            "EEG": {
                "data": fdt_path.name,
                "nbchan": 2.0,
                "pnts": 20.0,
                "trials": 1.0,
            }
        },
    )

    preflight = check_import_resource_preflight([str(set_path)])
    detail = preflight.diagnostics["files"][0]

    assert preflight.blocking is True
    assert preflight.diagnostics["estimated_ram_working_set_bytes"] is None
    assert detail["size_bound_known"] is False
    assert detail["reason_code"] == reason_code
    assert detail["estimated_raw_bytes"] == partial_raw_bytes


@pytest.mark.parametrize("reference", ["../escape.fdt", "/tmp/absolute.fdt"])
def test_unsafe_external_fdt_reference_fails_closed(
    tmp_path: Path,
    reference: str,
) -> None:
    set_path = tmp_path / "unsafe.set"
    savemat(
        set_path,
        {
            "EEG": {
                "data": reference,
                "nbchan": 2.0,
                "pnts": 20.0,
                "trials": 1.0,
            }
        },
    )

    inspection = inspect_eeglab_set_header(set_path)

    assert inspection.bound_known is False
    assert inspection.reason_code == "eeglab_external_reference_unsafe"


def test_mat_v73_and_unsupported_headers_fail_closed(tmp_path: Path) -> None:
    v73_path = tmp_path / "v73.set"
    v73_path.write_bytes(b"MATLAB 7.3 MAT-file".ljust(128, b"\0"))
    unsupported_path = tmp_path / "unsupported.set"
    unsupported_path.write_bytes(b"not-a-mat-file".ljust(128, b"\0"))

    v73 = inspect_eeglab_set_header(v73_path)
    unsupported = inspect_eeglab_set_header(unsupported_path)

    assert v73.bound_known is False
    assert v73.mat_format == "mat_v7.3"
    assert v73.reason_code == "mat_v73_not_bounded"
    assert unsupported.bound_known is False
    assert unsupported.reason_code == "mat_header_unsupported"


def test_complex_embedded_signal_fails_closed(tmp_path: Path) -> None:
    set_path = tmp_path / "complex.set"
    _write_embedded_set(
        set_path,
        data=np.zeros((2, 100), dtype=np.complex64),
        compressed=False,
    )

    inspection = inspect_eeglab_set_header(set_path)

    assert inspection.bound_known is False
    assert inspection.reason_code == "mat_header_unsupported"


def test_hostile_embedded_dimensions_do_not_underestimate_signal(
    tmp_path: Path,
) -> None:
    set_path = tmp_path / "hostile-dimensions.set"
    _write_embedded_set(
        set_path,
        data=np.zeros((2, 1_000), dtype=np.float32),
        compressed=False,
    )
    payload = set_path.read_bytes()
    dimensions = struct.pack("<ii", 2, 1_000)
    offset = payload.find(dimensions)
    assert offset >= 0
    hostile = struct.pack("<ii", 2_000_000_000, 2_000_000_000)
    set_path.write_bytes(payload[:offset] + hostile + payload[offset + 8 :])

    preflight = check_import_resource_preflight([str(set_path)])
    detail = preflight.diagnostics["files"][0]

    assert preflight.blocking is True
    assert detail["size_bound_known"] is False
    assert detail["estimated_raw_bytes"] == 0
    assert detail["reason_code"] == "mat_header_invalid"


@pytest.mark.parametrize("compressed", [False, True])
def test_embedded_set_with_declared_but_missing_signal_payload_fails_closed(
    tmp_path: Path,
    compressed: bool,
) -> None:
    valid_path = tmp_path / f"valid-{compressed}.set"
    _write_embedded_set(
        valid_path,
        data=np.zeros((2, 1_000), dtype=np.float32),
        compressed=compressed,
    )
    valid_bytes = valid_path.read_bytes()
    valid_inspection = inspect_eeglab_set_header(valid_path)
    assert valid_inspection.bound_known is True

    truncated_path = tmp_path / f"truncated-{compressed}.set"
    if compressed:
        type_code, compressed_bytes = struct.unpack("<II", valid_bytes[128:136])
        assert type_code == 15
        decoded = zlib.decompress(valid_bytes[136 : 136 + compressed_bytes])
        header_only = decoded[: valid_inspection.decoded_header_bytes]
        recompressed = zlib.compress(header_only)
        truncated_bytes = (
            valid_bytes[:128]
            + struct.pack("<II", 15, len(recompressed))
            + recompressed
            + b"\0" * (-len(recompressed) % 8)
        )
    else:
        truncated_bytes = valid_bytes[:512]
    truncated_path.write_bytes(truncated_bytes)

    preflight = check_import_resource_preflight([str(truncated_path)])
    detail = preflight.diagnostics["files"][0]

    assert preflight.blocking is True
    assert preflight.diagnostics["estimated_ram_working_set_bytes"] is None
    assert detail["size_bound_known"] is False
    assert detail["estimated_raw_bytes"] == 0
