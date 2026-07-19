"""Focused tests for RAM/VRAM resource safety checks."""

from __future__ import annotations

import tracemalloc
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from XBrainLab.backend.application import resource_guard
from XBrainLab.backend.application import resource_label_estimation as label_estimation


class _ArrayLike:
    def __init__(
        self,
        *,
        nbytes: int,
        shape: tuple[int, ...],
        dtype: Any | None = None,
    ) -> None:
        self.nbytes = nbytes
        self.shape = shape
        if dtype is not None:
            self.dtype = dtype


class _EpochData:
    def __init__(self, data: Any, labels: Any) -> None:
        self.data = data
        self.labels = labels

    def get_data(self) -> Any:
        return self.data

    def get_label_list(self) -> Any:
        return self.labels

    def get_model_args(self) -> dict[str, int]:
        return {"n_channels": 22, "n_times": 301, "n_classes": 4}


class _Dataset:
    def __init__(self, epoch_data: _EpochData) -> None:
        self.epoch_data = epoch_data
        self.train_mask = [True] * 20
        self.val_mask = [True] * 4
        self.test_mask = [True] * 4

    def get_epoch_data(self) -> _EpochData:
        return self.epoch_data


class _Parameter:
    def numel(self) -> int:
        return 1_000

    def element_size(self) -> int:
        return 4


class _Model:
    def parameters(self):
        return [_Parameter()]

    def cpu(self) -> None:
        return None


class _ModelHolder:
    target_model = type("EEGNet", (), {})

    def get_model(self, _args):
        return _Model()


def _gpu_status(*, available_bytes: int | None) -> dict[str, Any]:
    return {
        "gpu_name": "Test GPU",
        "available_bytes": available_bytes,
        "total_bytes": 2_000,
        "used_bytes": None if available_bytes is None else 2_000 - available_bytes,
        "allocated_bytes": 0,
        "reserved_bytes": 0,
        "reason": None,
    }


def _training_estimate(required_bytes: int) -> dict[str, Any]:
    return {
        "estimated_vram_bytes": required_bytes,
        "estimated_gpu_batch_working_set_bytes": required_bytes,
        "model_parameter_estimate_reliable": True,
    }


class _EpochSource:
    def __init__(self) -> None:
        import numpy as np

        self._events = np.array(
            [
                [100, 0, 1],
                [200, 0, 2],
                [300, 0, 1],
                [400, 0, 1],
                [500, 0, 2],
            ],
            dtype=int,
        )

    def get_event_list(self):
        return self._events, {"left": 1, "right": 2}

    def get_nchan(self) -> int:
        return 2

    def get_sfreq(self) -> float:
        return 100.0

    def get_filename(self) -> str:
        return "epoch-source.fif"


def test_epoch_ram_estimate_uses_selected_events_channels_window_and_dtype() -> None:
    estimate = resource_guard.ResourceChecker.estimate_epoch_ram(
        [_EpochSource()],
        selected_event_names=["left"],
        tmin=-0.2,
        tmax=0.8,
    )

    payload_bytes = 3 * 2 * 101 * resource_guard.EPOCH_DTYPE_BYTES
    expected = int(
        payload_bytes
        * (
            resource_guard.EPOCH_COPY_BUFFER_FACTOR
            + resource_guard.EPOCH_PRELOAD_BUFFER_FACTOR
        )
        * resource_guard.EPOCH_RAM_SAFETY_MARGIN
    )
    assert estimate["selected_event_count"] == 3
    assert estimate["channel_samples"] == 3 * 2 * 101
    assert estimate["epoch_payload_bytes"] == payload_bytes
    assert estimate["estimated_ram_working_set_bytes"] == expected
    assert estimate["formula"] == (
        "selected_events * channels * window_samples * dtype_bytes * "
        "(copy_buffer_factor + preload_buffer_factor) * safety_margin"
    )


def test_epoch_ram_check_blocks_at_available_memory_threshold(monkeypatch) -> None:
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 10_000,
                "total_bytes": 20_000,
                "used_bytes": 10_000,
            }
        ),
    )

    result = resource_guard.ResourceChecker.check_epoch_materialization_safe(
        [_EpochSource()],
        selected_event_names=["left"],
        tmin=-0.2,
        tmax=0.8,
    )

    assert result.risk_level == resource_guard.RISK_BLOCKING
    assert result.required_memory_bytes is not None
    assert result.required_memory_bytes > int(
        10_000 * resource_guard.RAM_BLOCKING_RATIO
    )
    assert "epochs" in result.message.lower()


def test_dataset_ram_check_blocks_large_file_size_fallback(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "large.unknown"
    path.write_bytes(b"0" * 100)
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {"available_bytes": 400, "total_bytes": 1_000, "used_bytes": 600}
        ),
    )

    result = resource_guard.ResourceChecker.check_dataset_load_safe([str(path)])

    assert result.risk_level == resource_guard.RISK_BLOCKING
    assert result.required_memory_bytes is not None
    assert result.required_memory_bytes > int(400 * resource_guard.RAM_BLOCKING_RATIO)
    assert "lazy" not in result.message.lower()
    assert "memory mapping" not in result.message.lower()


def test_embedded_eeglab_set_preflight_never_invokes_mne_reader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real embedded EEGLAB MAT payload must stay on the bounded path."""
    import mne
    import numpy as np
    from scipy.io import savemat

    set_path = tmp_path / "embedded.set"
    savemat(
        set_path,
        {
            "EEG": {
                "data": np.zeros((2, 1_000), dtype=np.float32),
                "setname": "embedded-preflight-regression",
                "nbchan": 2.0,
                "pnts": 1_000.0,
                "trials": 1.0,
                "srate": 100.0,
                "xmin": 0.0,
                "xmax": 9.99,
                "ref": "common",
                "chanlocs": np.array([], dtype=object),
                "event": np.array([], dtype=object),
            }
        },
        do_compression=False,
    )

    reader_calls: list[Path] = []

    def _materializing_reader(path, **_kwargs):
        reader_calls.append(Path(path))
        pytest.fail("EEGLAB RAM preflight invoked the materializing MNE reader")

    monkeypatch.setattr(mne.io, "read_raw_eeglab", _materializing_reader)

    real_import_module = resource_guard.import_module

    def _reject_mne_import(name: str):
        if name == "mne":
            pytest.fail("EEGLAB RAM preflight attempted to invoke the MNE reader")
        return real_import_module(name)

    monkeypatch.setattr(resource_guard, "import_module", _reject_mne_import)

    estimate = resource_guard.ResourceChecker.estimate_dataset_ram([str(set_path)])

    [detail] = estimate["files"]
    assert detail["estimate_source"] == "eeglab_mat_header_embedded"
    assert detail["materializes_signal_data"] is False
    assert detail["file_bytes"] == set_path.stat().st_size
    assert detail["channels"] == 2
    assert detail["time_samples"] == 1_000
    assert detail["trials"] == 1
    assert detail["source_dtype"] == "float32"
    assert detail["estimated_raw_bytes"] == 2 * 1_000 * 8
    assert reader_calls == []


def test_compressed_embedded_eeglab_uses_signal_shape_instead_of_fixed_floor(
    tmp_path: Path,
) -> None:
    """A reachable compressed matrix header gives an exact decoded shape bound."""
    import numpy as np
    from scipy.io import savemat

    set_path = tmp_path / "compressed.set"
    savemat(
        set_path,
        {
            "EEG": {
                "data": np.zeros((8, 250_000), dtype=np.float32),
                "nbchan": 8.0,
                "pnts": 250_000.0,
                "trials": 1.0,
                "srate": 250.0,
            }
        },
        do_compression=True,
    )

    estimate = resource_guard.ResourceChecker.estimate_dataset_ram([str(set_path)])

    [detail] = estimate["files"]
    assert detail["estimate_source"] == "eeglab_mat_header_embedded"
    assert detail["channels"] == 8
    assert detail["time_samples"] == 250_000
    assert detail["trials"] == 1
    assert detail["source_dtype"] == "float32"
    assert detail["estimated_raw_bytes"] == 8 * 250_000 * 8
    assert detail["materializes_signal_data"] is False


def test_compressed_eeglab_without_reachable_data_header_blocks_before_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bounded preflight must not guess when compressed structure hides data."""
    import numpy as np
    from scipy.io import savemat

    set_path = tmp_path / "opaque-compressed.set"
    savemat(
        set_path,
        {
            "EEG": {
                "opaque": np.zeros(3_000_000, dtype=np.uint8),
                "data": np.zeros((2, 100), dtype=np.float32),
                "nbchan": 2.0,
                "pnts": 100.0,
                "trials": 1.0,
            }
        },
        do_compression=True,
    )
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 10**12,
                "total_bytes": 10**12,
                "used_bytes": 0,
            }
        ),
    )

    preflight = resource_guard.check_import_resource_preflight([str(set_path)])

    assert preflight.blocking is True
    assert preflight.risk_level is resource_guard.ResourceRiskLevel.BLOCKING
    [detail] = preflight.diagnostics["files"]
    assert detail["estimate_source"] == "eeglab_header_unknown"
    assert detail["size_bound_known"] is False
    assert detail["materializes_signal_data"] is False
    assert "could not be bounded" in preflight.message.lower()
    with pytest.raises(resource_guard.PreconditionError):
        resource_guard.enforce_resource_preflight(preflight, confirmed=True)


def test_complex_embedded_eeglab_data_is_blocking_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import numpy as np
    from scipy.io import savemat

    set_path = tmp_path / "complex.set"
    savemat(
        set_path,
        {
            "EEG": {
                "data": np.zeros((2, 100), dtype=np.complex64),
                "nbchan": 2.0,
                "pnts": 100.0,
                "trials": 1.0,
            }
        },
        do_compression=False,
    )
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 10**12,
                "total_bytes": 10**12,
                "used_bytes": 0,
            }
        ),
    )

    preflight = resource_guard.check_import_resource_preflight([str(set_path)])

    assert preflight.blocking is True
    [detail] = preflight.diagnostics["files"]
    assert detail["size_bound_known"] is False
    assert detail["reason_code"] == "mat_header_unsupported"


def test_eeglab_preflight_discovers_arbitrary_external_fdt_reference(
    tmp_path: Path,
) -> None:
    from scipy.io import savemat

    set_path = tmp_path / "subject.SET"
    fdt_path = tmp_path / "Run-01-Signal.FdT"
    decoy_path = tmp_path / "subject.fdt"
    channels = 3
    points = 11
    trials = 2
    fdt_path.write_bytes(b"\0" * (channels * points * trials * 4))
    decoy_path.write_bytes(b"\0" * 4_096)
    savemat(
        set_path,
        {
            "EEG": {
                "data": fdt_path.name.lower(),
                "nbchan": float(channels),
                "pnts": float(points),
                "trials": float(trials),
                "srate": 250.0,
            }
        },
        do_compression=True,
    )

    estimate = resource_guard.ResourceChecker.estimate_dataset_ram([str(set_path)])

    set_detail = next(row for row in estimate["files"] if row["path"] == str(set_path))
    assert set_detail["estimate_source"] == "eeglab_mat_header_external_fdt"
    assert set_detail["associated_data_file"] == str(fdt_path)
    assert set_detail["associated_data_file_bytes"] == fdt_path.stat().st_size
    assert set_detail["channels"] == channels
    assert set_detail["time_samples"] == points
    assert set_detail["trials"] == trials
    assert set_detail["source_dtype"] == "float32"
    assert set_detail["source_shape"] == [channels, points, trials]
    assert set_detail["estimated_raw_bytes"] == channels * points * trials * 8
    assert str(decoy_path) not in {str(row.get("path")) for row in estimate["files"]}


def test_eeglab_external_fdt_shape_size_mismatch_is_blocking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scipy.io import savemat

    set_path = tmp_path / "subject.set"
    fdt_path = tmp_path / "actual-data.fdt"
    fdt_path.write_bytes(b"\0" * (2 * 10 * 4 + 4))
    savemat(
        set_path,
        {
            "EEG": {
                "data": fdt_path.name,
                "nbchan": 2.0,
                "pnts": 10.0,
                "trials": 1.0,
            }
        },
        do_compression=False,
    )
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 10**12,
                "total_bytes": 10**12,
                "used_bytes": 0,
            }
        ),
    )

    preflight = resource_guard.check_import_resource_preflight([str(set_path)])

    assert preflight.blocking is True
    [set_detail, dependency_detail] = preflight.diagnostics["files"]
    assert set_detail["reason_code"] == "eeglab_external_shape_size_mismatch"
    assert set_detail["size_bound_known"] is False
    assert dependency_detail["path"] == str(fdt_path)


def test_eeglab_preflight_accounts_for_conventional_fdt_sidecar(
    tmp_path: Path,
) -> None:
    import numpy as np
    from scipy.io import savemat

    set_path = tmp_path / "external.set"
    fdt_path = tmp_path / "external.fdt"
    fdt_path.write_bytes(b"0" * 10_000)
    savemat(
        set_path,
        {
            "EEG": {
                "data": fdt_path.name,
                "nbchan": 10.0,
                "pnts": 250.0,
                "trials": 1.0,
                "srate": 250.0,
                "chanlocs": np.array([], dtype=object),
            }
        },
        do_compression=False,
    )

    estimate = resource_guard.ResourceChecker.estimate_dataset_ram([str(set_path)])

    detail = next(row for row in estimate["files"] if row["path"] == str(set_path))
    assert detail["estimate_source"] == "eeglab_mat_header_external_fdt"
    assert detail["associated_data_file"] == str(fdt_path)
    assert detail["associated_data_file_bytes"] == fdt_path.stat().st_size
    assert detail["estimated_raw_bytes"] == (
        fdt_path.stat().st_size * resource_guard.EEGLAB_FDT_TO_FLOAT64_MULTIPLIER
    )


@pytest.mark.parametrize(
    ("required_bytes", "expected_risk"),
    [
        (600, resource_guard.RISK_SAFE),
        (601, resource_guard.RISK_WARNING),
        (800, resource_guard.RISK_WARNING),
        (801, resource_guard.RISK_BLOCKING),
    ],
)
def test_dataset_ram_thresholds_use_strict_greater_than_semantics(
    required_bytes: int,
    expected_risk: str,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "estimate_dataset_ram",
        staticmethod(
            lambda _paths: {"estimated_ram_working_set_bytes": required_bytes}
        ),
    )
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 1_000,
                "total_bytes": 2_000,
                "used_bytes": 1_000,
            }
        ),
    )

    result = resource_guard.ResourceChecker.check_dataset_load_safe(["test.edf"])

    assert result.risk_level == expected_risk
    assert result.details["warning_ratio"] == resource_guard.RAM_WARNING_RATIO
    assert result.details["blocking_ratio"] == resource_guard.RAM_BLOCKING_RATIO


@pytest.mark.parametrize(
    ("required_bytes", "expected_risk"),
    [
        (750, resource_guard.RISK_SAFE),
        (751, resource_guard.RISK_WARNING),
        (900, resource_guard.RISK_WARNING),
        (901, resource_guard.RISK_BLOCKING),
    ],
)
def test_training_vram_thresholds_use_strict_greater_than_semantics(
    required_bytes: int,
    expected_risk: str,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "estimate_training_vram",
        staticmethod(
            lambda _datasets, _option, _holder=None: _training_estimate(required_bytes)
        ),
    )
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_gpu_vram_status",
        staticmethod(lambda _gpu_idx=None: _gpu_status(available_bytes=1_000)),
    )
    option = SimpleNamespace(use_cpu=False, gpu_idx=0, bs=8, optim=object)

    result = resource_guard.ResourceChecker.check_training_config_safe(
        [],
        option,
        _ModelHolder(),
    )

    assert result.risk_level == expected_risk
    assert result.details["warning_ratio"] == resource_guard.VRAM_WARNING_RATIO
    assert result.details["blocking_ratio"] == resource_guard.VRAM_BLOCKING_RATIO


def test_dataset_ram_estimate_includes_deduplicated_external_label_carriers(
    tmp_path,
) -> None:
    eeg_path = tmp_path / "recording.unknown"
    tsv_path = tmp_path / "events.tsv"
    mat_path = tmp_path / "labels.mat"
    eeg_path.write_bytes(b"e" * 10)
    tsv_path.write_bytes(b"t" * 20)
    mat_path.write_bytes(b"m" * 30)

    estimate = resource_guard.ResourceChecker.estimate_dataset_ram(
        [
            str(eeg_path),
            str(tsv_path),
            str(mat_path),
            str(tsv_path),
        ],
    )

    expected_persistent_bytes = int(
        20 * label_estimation.LABEL_CARRIER_PERSISTENT_MULTIPLIERS[".tsv"]
        + 30 * label_estimation.LABEL_CARRIER_PERSISTENT_MULTIPLIERS[".mat"]
    )
    expected_parser_transient_bytes = int(
        max(
            20 * label_estimation.LABEL_CARRIER_PARSER_TRANSIENT_MULTIPLIERS[".tsv"],
            label_estimation.TABULAR_MINIMUM_WORKING_SET_BYTES,
            30 * label_estimation.LABEL_CARRIER_PARSER_TRANSIENT_MULTIPLIERS[".mat"],
            label_estimation.MAT_LABEL_MINIMUM_WORKING_SET_BYTES,
        )
    )
    expected_label_working_set = (
        expected_persistent_bytes + expected_parser_transient_bytes
    )
    assert label_estimation.LABEL_CARRIER_FILE_SIZE_MULTIPLIERS[".tsv"] >= 16.0
    assert label_estimation.LABEL_CARRIER_FILE_SIZE_MULTIPLIERS[".mat"] >= 64.0
    assert estimate["eeg_path_count"] == 1
    assert estimate["label_carrier_count"] == 2
    assert estimate["label_carrier_file_bytes"] == 50
    assert estimate["label_carrier_working_set_bytes"] == expected_label_working_set
    assert estimate["path_count"] == 3
    assert estimate["raw_import_dtype"] == "float64"
    assert estimate["raw_import_dtype_bytes"] == resource_guard.RAW_IMPORT_DTYPE_BYTES
    assert "preprocessing_intermediate" in estimate["ram_formula"]
    label_details = [
        item for item in estimate["files"] if item["resource_kind"] == "label_carrier"
    ]
    assert {item["path"] for item in label_details} == {
        str(tsv_path),
        str(mat_path),
    }
    details_by_format = {item["format"]: item for item in label_details}
    assert details_by_format[".tsv"]["estimate_source"] == (
        "tabular_parser_plus_returned_objects"
    )
    assert details_by_format[".mat"]["estimate_source"] == (
        "mat_file_size_or_minimum_fallback"
    )


def test_mat_label_estimate_uses_uncompressed_matrix_size_from_bounded_header(
    tmp_path,
) -> None:
    import numpy as np
    from scipy.io import savemat

    mat_path = tmp_path / "compressed-labels.mat"
    labels = np.zeros(1_000_000, dtype=np.int16)
    confidence = np.ones(10_000, dtype=np.float32)
    savemat(
        mat_path,
        {"classlabel": labels, "confidence": confidence},
        do_compression=True,
    )
    assert mat_path.stat().st_size < labels.nbytes

    estimate = resource_guard.ResourceChecker.estimate_dataset_ram([str(mat_path)])

    [detail] = estimate["files"]
    assert detail["estimate_source"] == "mat_header_or_file_size_multiplier"
    assert detail["mat_uncompressed_bytes"] >= labels.nbytes + confidence.nbytes
    assert detail["estimated_working_set_bytes"] >= (
        labels.nbytes * label_estimation.MAT_LABEL_UNCOMPRESSED_MEMORY_MULTIPLIER
    )


def test_csv_tsv_estimate_dominates_measured_adversarial_pandas_loader_peak(
    tmp_path,
) -> None:
    for suffix, delimiter in ((".csv", ","), (".tsv", "\t")):
        path = tmp_path / f"high-overhead{suffix}"
        rows = [delimiter.join(("event", "label", "description"))]
        rows.extend(
            delimiter.join((str(index), f"c{index:05x}", f"value-{index:05x}"))
            for index in range(30_000)
        )
        path.write_text("\n".join(rows) + "\n", encoding="utf-8")

        tracemalloc.start()
        frame = pd.read_csv(path, sep=delimiter)
        _current_bytes, measured_peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        returned_object_bytes = int(frame.memory_usage(index=True, deep=True).sum())

        estimate, details = label_estimation.estimate_label_carrier_working_set(
            str(path),
            suffix=suffix,
            file_bytes=path.stat().st_size,
        )

        assert estimate >= max(measured_peak_bytes, returned_object_bytes)
        assert details["parser_working_set_bytes"] > 0
        assert details["returned_object_bytes"] >= returned_object_bytes
        assert details["estimate_source"] == "tabular_parser_plus_returned_objects"


def test_mat_preflight_enforces_one_global_byte_read_budget(
    tmp_path,
    monkeypatch,
) -> None:
    import numpy as np
    from scipy.io import savemat

    mat_path = tmp_path / "bounded-labels.mat"
    savemat(
        mat_path,
        {"classlabel": np.zeros(200_000, dtype=np.int16)},
        do_compression=True,
    )
    byte_budget = 144
    monkeypatch.setattr(
        label_estimation,
        "MAT_LABEL_PREFLIGHT_READ_BUDGET_BYTES",
        byte_budget,
    )

    _estimate, details = label_estimation.estimate_label_carrier_working_set(
        str(mat_path),
        suffix=".mat",
        file_bytes=mat_path.stat().st_size,
    )

    assert 0 < details["mat_preflight_bytes_read"] <= byte_budget
    assert details["mat_preflight_read_budget_bytes"] == byte_budget


def test_import_preflight_shares_one_mat_byte_budget_across_300_files(
    tmp_path,
    monkeypatch,
) -> None:
    import numpy as np
    from scipy.io import savemat

    template = tmp_path / "template.mat"
    savemat(
        template,
        {"classlabel": np.zeros(5_000, dtype=np.int16)},
        do_compression=True,
    )
    encoded = template.read_bytes()
    mat_paths = []
    for index in range(300):
        path = tmp_path / f"labels-{index:03d}.mat"
        path.write_bytes(encoded)
        mat_paths.append(str(path))
    mat_path_set = set(mat_paths)
    byte_budget = 4_096
    real_open = open
    physical_bytes_read = 0

    class _ObservedReader:
        def __init__(self, handle):
            self._handle = handle

        def __enter__(self):
            self._handle.__enter__()
            return self

        def __exit__(self, *args):
            return self._handle.__exit__(*args)

        def read(self, *args, **kwargs):
            nonlocal physical_bytes_read
            payload = self._handle.read(*args, **kwargs)
            physical_bytes_read += len(payload)
            return payload

        def __getattr__(self, name):
            return getattr(self._handle, name)

    def _observed_open(path, *args, **kwargs):
        handle = real_open(path, *args, **kwargs)
        if str(path) in mat_path_set:
            return _ObservedReader(handle)
        return handle

    monkeypatch.setattr(
        label_estimation,
        "MAT_LABEL_PREFLIGHT_READ_BUDGET_BYTES",
        byte_budget,
    )
    monkeypatch.setattr(label_estimation, "open", _observed_open, raising=False)
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 10**12,
                "total_bytes": 10**12,
                "used_bytes": 0,
            }
        ),
    )

    preflight = resource_guard.check_import_resource_preflight(mat_paths)
    diagnostics = preflight.to_diagnostics()
    per_file_reads = [item["mat_preflight_bytes_read"] for item in diagnostics["files"]]

    assert diagnostics["mat_preflight_read_budget_bytes"] == byte_budget
    assert diagnostics["mat_preflight_bytes_read"] == byte_budget
    assert physical_bytes_read == byte_budget
    assert sum(per_file_reads) == byte_budget
    assert max(per_file_reads) < byte_budget
    assert 0 in per_file_reads
    assert diagnostics["mat_preflight_budget_exhausted"] is True


def test_dataset_ram_check_warns_for_external_label_working_set(
    tmp_path,
    monkeypatch,
) -> None:
    eeg_path = tmp_path / "recording.unknown"
    label_path = tmp_path / "events.tsv"
    eeg_path.write_bytes(b"e" * 10)
    label_path.write_bytes(b"t" * 100_000)
    paths = [str(eeg_path), str(label_path)]
    estimate = resource_guard.ResourceChecker.estimate_dataset_ram(paths)
    required = estimate["estimated_ram_working_set_bytes"]
    available = int(required / 0.70)
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": available,
                "total_bytes": available * 2,
                "used_bytes": available,
            }
        ),
    )

    result = resource_guard.ResourceChecker.check_dataset_load_safe(paths)

    assert result.risk_level == resource_guard.RISK_WARNING
    assert result.details["label_carrier_count"] == 1
    assert result.details["label_carrier_file_bytes"] == label_path.stat().st_size
    assert result.details["label_carrier_working_set_bytes"] > label_path.stat().st_size


def test_large_txt_label_estimate_covers_measured_eager_loader_peak(
    tmp_path: Path,
) -> None:
    label_path = tmp_path / "large-labels.txt"
    label_path.write_bytes((b"1 " * 1_000_000) + b"\n")

    estimate = resource_guard.ResourceChecker.estimate_dataset_ram([str(label_path)])

    assert label_path.stat().st_size == 2_000_001
    assert estimate["estimated_ram_working_set_bytes"] >= 40_993_719


def test_many_tiny_csv_labels_share_one_sequential_parser_transient(
    tmp_path: Path,
) -> None:
    paths: list[str] = []
    for index in range(300):
        path = tmp_path / f"labels-{index:03d}.csv"
        path.write_text("label\n1\n", encoding="utf-8")
        paths.append(str(path))

    estimate = resource_guard.ResourceChecker.estimate_dataset_ram(paths)

    assert estimate["label_carrier_count"] == 300
    assert estimate["estimated_ram_working_set_bytes"] < 100 * 1024 * 1024
    assert estimate["label_parser_transient_peak_bytes"] > 0
    assert estimate["label_carrier_persistent_bytes"] > 0


def test_dataset_ram_check_warns_without_blocking(tmp_path, monkeypatch) -> None:
    path = tmp_path / "warning.unknown"
    path.write_bytes(b"0" * 100)
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 2_000_000,
                "total_bytes": 4_000_000,
                "used_bytes": 2_000_000,
            }
        ),
    )

    preflight = resource_guard.check_import_resource_preflight([str(path)])

    assert preflight.ok is True
    assert preflight.warnings
    assert preflight.diagnostics["risk_level"] == resource_guard.RISK_WARNING


def test_resource_preflight_exposes_typed_confirmation_contract(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "warning.unknown"
    path.write_bytes(b"0" * 100)
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 2_000_000,
                "total_bytes": 4_000_000,
                "used_bytes": 2_000_000,
            }
        ),
    )

    preflight = resource_guard.check_import_resource_preflight([str(path)])

    assert preflight.risk_level is resource_guard.ResourceRiskLevel.WARNING
    assert preflight.requires_confirmation is True
    assert preflight.blocking is False
    assert preflight.to_diagnostics()["risk_level"] == "warning"
    assert preflight.to_diagnostics()["requires_confirmation"] is True


def test_resource_preflight_keeps_unknown_explicit(monkeypatch) -> None:
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": None,
                "total_bytes": None,
                "used_bytes": None,
            }
        ),
    )

    preflight = resource_guard.check_import_resource_preflight(["missing.edf"])

    assert preflight.risk_level is resource_guard.ResourceRiskLevel.UNKNOWN
    assert preflight.requires_confirmation is True
    assert preflight.unknowns
    assert preflight.to_diagnostics()["risk_level"] == "unknown"


def test_safe_resource_preflight_proceeds_without_confirmation(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "safe.unknown"
    path.write_bytes(b"0" * 100)
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 10_000_000,
                "total_bytes": 12_000_000,
                "used_bytes": 2_000_000,
            }
        ),
    )

    preflight = resource_guard.check_import_resource_preflight([str(path)])

    assert preflight.risk_level is resource_guard.ResourceRiskLevel.SAFE
    assert preflight.requires_confirmation is False
    resource_guard.enforce_resource_preflight(preflight, confirmed=False)


def test_training_preflight_keeps_warning_and_unknown_details(monkeypatch) -> None:
    data = _ArrayLike(nbytes=10_000, shape=(10, 1_000))
    labels = _ArrayLike(nbytes=1_000, shape=(10,))
    datasets = [_Dataset(_EpochData(data, labels))]
    option = SimpleNamespace(use_cpu=False, gpu_idx=0, bs=4, optim=object)
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 90_000,
                "total_bytes": 180_000,
                "used_bytes": 90_000,
            }
        ),
    )
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_gpu_vram_status",
        staticmethod(lambda _gpu_idx=None: {"available_bytes": None, "gpu_name": None}),
    )

    preflight = resource_guard.check_training_resource_preflight(
        datasets,
        option,
        _ModelHolder(),
    )

    assert preflight.risk_level is resource_guard.ResourceRiskLevel.WARNING
    assert preflight.requires_confirmation is True
    assert preflight.warnings
    assert preflight.unknowns
    assert "available RAM" in preflight.message
    assert "GPU memory" in preflight.message


def test_training_preflight_materializes_dataset_iterable_once(monkeypatch) -> None:
    data = _ArrayLike(nbytes=10_000, shape=(10, 1_000))
    labels = _ArrayLike(nbytes=1_000, shape=(10,))
    dataset = _Dataset(_EpochData(data, labels))
    option = SimpleNamespace(use_cpu=False, gpu_idx=0, bs=4, optim=object)
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 10_000_000,
                "total_bytes": 20_000_000,
                "used_bytes": 10_000_000,
            }
        ),
    )
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_gpu_vram_status",
        staticmethod(
            lambda _gpu_idx=None: {
                "available_bytes": 10_000_000,
                "total_bytes": 20_000_000,
                "used_bytes": 10_000_000,
                "allocated_bytes": 0,
                "reserved_bytes": 0,
                "gpu_name": "Test GPU",
            }
        ),
    )

    preflight = resource_guard.check_training_resource_preflight(
        (item for item in [dataset]),
        option,
    )

    assert preflight.diagnostics["dataset_count"] == 1
    assert preflight.diagnostics["vram"]["dataset_count"] == 1


def test_training_vram_check_uses_peak_batch_not_fold_sum(monkeypatch) -> None:
    data = _ArrayLike(nbytes=40_000, shape=(10, 1_000))
    labels = _ArrayLike(nbytes=80, shape=(10,))
    datasets = [_Dataset(_EpochData(data, labels)), _Dataset(_EpochData(data, labels))]
    option = SimpleNamespace(use_cpu=False, gpu_idx=0, bs=5, optim=object)
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_gpu_vram_status",
        staticmethod(
            lambda _gpu_idx=None: {
                "available_bytes": 100_000_000,
                "total_bytes": 120_000_000,
                "used_bytes": 20_000_000,
                "allocated_bytes": 0,
                "reserved_bytes": 0,
                "gpu_name": "Test GPU",
            },
        ),
    )
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 10_000_000,
                "total_bytes": 20_000_000,
                "used_bytes": 10_000_000,
            },
        ),
    )

    result = resource_guard.ResourceChecker.check_training_config_safe(
        datasets,
        option,
        _ModelHolder(),
    )

    assert result.risk_level == resource_guard.RISK_WARNING
    assert result.details["dataset_count"] == 2
    assert result.details["peak_input_batch_bytes"] < 40_000
    assert result.details["runtime_workspace_bytes"] == (
        resource_guard.TRAINING_RUNTIME_WORKSPACE_BYTES
    )
    assert result.details["model_parameter_estimate_source"] == "instantiated"


def test_training_vram_estimate_does_not_multiply_folds_or_repeats() -> None:
    data = _ArrayLike(nbytes=40_000, shape=(10, 1_000))
    labels = _ArrayLike(nbytes=80, shape=(10,))
    shared_epoch_data = _EpochData(data, labels)
    one_fold = [_Dataset(shared_epoch_data)]
    five_folds = [_Dataset(shared_epoch_data) for _index in range(5)]
    one_repeat = SimpleNamespace(bs=5, optim=object, repeat_num=1)
    nine_repeats = SimpleNamespace(bs=5, optim=object, repeat_num=9)

    baseline = resource_guard.estimate_training_resources(
        one_fold,
        one_repeat,
        model_holder=_ModelHolder(),
    )
    repeated = resource_guard.estimate_training_resources(
        five_folds,
        nine_repeats,
        model_holder=_ModelHolder(),
    )

    assert (
        repeated["estimated_gpu_batch_working_set_bytes"]
        == baseline["estimated_gpu_batch_working_set_bytes"]
    )
    assert repeated["dataset_bytes"] == baseline["dataset_bytes"]
    assert repeated["fold_count"] == 5
    assert repeated["repeat_count"] == 9
    assert repeated["peak_execution_scope"] == "one_fold_one_repeat_one_batch"
    assert repeated["folds_repeats_concurrent"] is False


def test_training_ram_estimate_includes_retained_fold_repeat_records() -> None:
    data = _ArrayLike(nbytes=40_000, shape=(10, 1_000))
    labels = _ArrayLike(nbytes=80, shape=(10,))
    shared_epoch_data = _EpochData(data, labels)
    one_fold = [_Dataset(shared_epoch_data)]
    five_folds = [_Dataset(shared_epoch_data) for _index in range(5)]

    baseline = resource_guard.estimate_training_resources(
        one_fold,
        SimpleNamespace(bs=5, optim=object, repeat_num=1),
        model_holder=_ModelHolder(),
    )
    repeated = resource_guard.estimate_training_resources(
        five_folds,
        SimpleNamespace(bs=5, optim=object, repeat_num=9),
        model_holder=_ModelHolder(),
    )

    assert repeated["training_record_count"] == 45
    assert repeated["retained_model_bytes"] == 4_000 * 45
    assert repeated["retained_gradient_bytes"] == 4_000 * 45
    assert repeated["retained_optimizer_state_bytes"] == 6_000 * 45
    assert repeated["retained_checkpoint_bytes"] == 12_000 * 45
    assert repeated["retained_training_record_bytes"] == 26_000 * 45
    assert (
        repeated["retained_training_record_bytes"]
        > baseline["retained_training_record_bytes"]
    )
    assert (
        repeated["estimated_ram_working_set_bytes"]
        > baseline["estimated_ram_working_set_bytes"]
    )
    assert (
        repeated["estimated_gpu_batch_working_set_bytes"]
        == baseline["estimated_gpu_batch_working_set_bytes"]
    )


def test_training_ram_preflight_blocks_retained_plan_history(
    monkeypatch,
) -> None:
    data = _ArrayLike(nbytes=40_000, shape=(10, 1_000))
    labels = _ArrayLike(nbytes=80, shape=(10,))
    shared_epoch_data = _EpochData(data, labels)
    datasets = [_Dataset(shared_epoch_data) for _index in range(5)]
    option = SimpleNamespace(
        use_cpu=True,
        bs=5,
        optim=object,
        repeat_num=9,
    )
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 1_000_000,
                "total_bytes": 2_000_000,
                "used_bytes": 1_000_000,
            }
        ),
    )

    preflight = resource_guard.check_training_resource_preflight(
        datasets,
        option,
        _ModelHolder(),
    )

    assert preflight.issues
    assert preflight.diagnostics["dataset_ram_risk_level"] == (
        resource_guard.RISK_BLOCKING
    )
    assert preflight.diagnostics["training_record_count"] == 45


def test_training_vram_formula_uses_one_peak_batch() -> None:
    data = _ArrayLike(nbytes=40_000, shape=(10, 1_000))
    labels = _ArrayLike(nbytes=80, shape=(10,))
    estimate = resource_guard.estimate_training_resources(
        [_Dataset(_EpochData(data, labels))],
        SimpleNamespace(bs=5, optim=object, repeat_num=3),
        model_holder=_ModelHolder(),
    )

    expected_peak_batch = max(
        estimate["peak_input_batch_bytes"],
        estimate["peak_validation_batch_bytes"],
    )
    expected_before_margin = sum(
        estimate[key]
        for key in (
            "model_parameter_bytes",
            "gradient_bytes",
            "optimizer_state_bytes",
            "evaluation_model_bytes",
            "peak_batch_bytes",
            "activation_bytes",
            "logits_bytes",
            "runtime_workspace_bytes",
        )
    )

    assert estimate["peak_batch_bytes"] == expected_peak_batch
    assert estimate["estimated_gpu_before_margin_bytes"] == expected_before_margin
    assert estimate["estimated_gpu_batch_working_set_bytes"] == int(
        expected_before_margin * resource_guard.VRAM_SAFETY_MARGIN
    )
    assert estimate["training_dtype"] == "float32"
    assert estimate["mixed_precision_applied"] is False


def test_training_vram_check_is_unknown_when_model_cannot_be_estimated(
    monkeypatch,
) -> None:
    data = _ArrayLike(nbytes=40_000, shape=(10, 1_000))
    labels = _ArrayLike(nbytes=80, shape=(10,))
    datasets = [_Dataset(_EpochData(data, labels))]
    option = SimpleNamespace(use_cpu=False, gpu_idx=0, bs=5, optim=object)
    model_holder = SimpleNamespace(
        target_model=type("BrokenModel", (), {}),
        get_model=lambda _args: (_ for _ in ()).throw(ValueError("bad model args")),
    )
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_gpu_vram_status",
        staticmethod(
            lambda _gpu_idx=None: {
                "available_bytes": 1_000_000_000,
                "total_bytes": 2_000_000_000,
                "used_bytes": 1_000_000_000,
                "allocated_bytes": 0,
                "reserved_bytes": 0,
                "gpu_name": "Test GPU",
            }
        ),
    )

    result = resource_guard.ResourceChecker.check_training_config_safe(
        datasets,
        option,
        model_holder,
    )

    assert result.risk_level == resource_guard.RISK_UNKNOWN
    assert result.details["model_parameter_estimate_source"] == "fallback"
    assert result.details["model_parameter_estimate_reliable"] is False
    assert result.required_memory_bytes is not None
    assert result.required_memory_bytes > 0


def test_training_vram_check_unknown_when_cuda_memory_unavailable(monkeypatch) -> None:
    option = SimpleNamespace(use_cpu=False, gpu_idx=0, bs=32, optim=object)
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_gpu_vram_status",
        staticmethod(lambda _gpu_idx=None: {"available_bytes": None, "gpu_name": None}),
    )

    result = resource_guard.ResourceChecker.check_training_config_safe([], option)

    assert result.risk_level == resource_guard.RISK_UNKNOWN
    assert "Unable to estimate GPU memory" in result.message


def test_gpu_status_explains_cuda_unavailable(monkeypatch) -> None:
    cuda = SimpleNamespace(is_available=lambda: False)
    monkeypatch.setattr(
        resource_guard,
        "_torch_module",
        lambda: SimpleNamespace(cuda=cuda),
    )

    result = resource_guard.ResourceChecker.get_gpu_vram_status(0)

    assert result["available_bytes"] is None
    assert result["reason"] == "cuda_not_available"


def test_gpu_status_rejects_invalid_device_before_memory_query(monkeypatch) -> None:
    memory_queries: list[int] = []
    cuda = SimpleNamespace(
        is_available=lambda: True,
        device_count=lambda: 1,
        mem_get_info=lambda index: memory_queries.append(index),
    )
    monkeypatch.setattr(
        resource_guard,
        "_torch_module",
        lambda: SimpleNamespace(cuda=cuda),
    )

    result = resource_guard.ResourceChecker.get_gpu_vram_status(3)

    assert result["available_bytes"] is None
    assert result["reason"] == "invalid_gpu_index"
    assert result["gpu_index"] == 3
    assert result["device_count"] == 1
    assert memory_queries == []


def test_gpu_status_explains_memory_query_failure(monkeypatch) -> None:
    def _raise_query(_index: int) -> tuple[int, int]:
        raise RuntimeError("driver query failed")

    cuda = SimpleNamespace(
        is_available=lambda: True,
        device_count=lambda: 1,
        mem_get_info=_raise_query,
        memory_allocated=lambda _index: 0,
        memory_reserved=lambda _index: 0,
        get_device_name=lambda _index: "Test GPU",
    )
    monkeypatch.setattr(
        resource_guard,
        "_torch_module",
        lambda: SimpleNamespace(cuda=cuda),
    )

    result = resource_guard.ResourceChecker.get_gpu_vram_status(0)

    assert result["available_bytes"] is None
    assert result["reason"] == "gpu_memory_query_failed"
    assert result["query_error_type"] == "RuntimeError"


def test_cuda_oom_detection_matches_common_runtime_errors(monkeypatch) -> None:
    calls: list[str] = []
    cuda = SimpleNamespace(
        is_available=lambda: True,
        empty_cache=lambda: calls.append("empty"),
    )
    monkeypatch.setattr(
        resource_guard,
        "_torch_module",
        lambda: SimpleNamespace(cuda=cuda),
    )

    assert resource_guard.is_cuda_oom_error(RuntimeError("CUDA out of memory")) is True
    assert (
        resource_guard.is_cuda_oom_error(RuntimeError("CUBLAS_STATUS_ALLOC_FAILED"))
        is True
    )
    assert resource_guard.is_cuda_oom_error(MemoryError("out of memory")) is False
    assert resource_guard.is_cuda_oom_error(RuntimeError("CPU out of memory")) is False

    resource_guard.release_cuda_cache()

    assert calls == ["empty"]
