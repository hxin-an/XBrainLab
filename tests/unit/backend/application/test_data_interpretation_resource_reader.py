"""Resource-admission identity regressions for Data Interpretation parsers."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.unit.backend.path_assertions import (
    assert_filesystem_path_lists_equal,
    assert_filesystem_paths_equal,
)
from XBrainLab.backend.application import data_interpretation_resource_reader
from XBrainLab.backend.application.data_interpretation_resource_reader import (
    AdmittedResourceReader,
)
from XBrainLab.backend.application.errors import PreconditionError
from XBrainLab.backend.application.resource_guard import (
    ResourceChecker,
    check_import_resource_preflight,
)


def _preflight(paths: list[str], monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 10**12,
                "total_bytes": 10**12,
                "used_bytes": 0,
            }
        ),
    )
    return check_import_resource_preflight(paths)


def _identity_stat(*, ctime_ns: int, inode: int = 101) -> SimpleNamespace:
    return SimpleNamespace(
        st_mode=0o100644,
        st_dev=11,
        st_ino=inode,
        st_size=32,
        st_mtime_ns=1_700_000_000_000_000_000,
        st_ctime_ns=ctime_ns,
    )


def test_current_identity_allows_stable_path_and_descriptor_channels_with_distinct_ctime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NTFS may report different ctime values for path and descriptor channels."""
    path = tmp_path / "recording.set"
    path.write_bytes(b"x" * 32)
    path_stats = iter([_identity_stat(ctime_ns=100), _identity_stat(ctime_ns=100)])
    descriptor_stats = iter(
        [_identity_stat(ctime_ns=200), _identity_stat(ctime_ns=200)]
    )
    monkeypatch.setattr(Path, "lstat", lambda _path: next(path_stats))
    monkeypatch.setattr(os, "fstat", lambda _descriptor: next(descriptor_stats))

    identity = data_interpretation_resource_reader._current_identity(path)

    assert identity.device == 11
    assert identity.inode == 101
    assert identity.ctime_ns == 200


@pytest.mark.parametrize(
    ("path_ctimes", "descriptor_ctimes"),
    [((100, 101), (200, 200)), ((100, 100), (200, 201))],
)
def test_current_identity_rejects_metadata_change_within_either_observation_channel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    path_ctimes: tuple[int, int],
    descriptor_ctimes: tuple[int, int],
) -> None:
    """A real ctime transition still fails even though channel ctimes may differ."""
    path = tmp_path / "recording.set"
    path.write_bytes(b"x" * 32)
    path_stats = iter([_identity_stat(ctime_ns=value) for value in path_ctimes])
    descriptor_stats = iter(
        [_identity_stat(ctime_ns=value) for value in descriptor_ctimes]
    )
    monkeypatch.setattr(Path, "lstat", lambda _path: next(path_stats))
    monkeypatch.setattr(os, "fstat", lambda _descriptor: next(descriptor_stats))

    with pytest.raises(PreconditionError) as raised:
        data_interpretation_resource_reader._current_identity(path)

    assert raised.value.diagnostics["code"] == "interpretation_resource_unavailable"


def test_reader_rejects_same_size_replacement_after_admission(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "events.tsv"
    path.write_text("onset\ttrial_type\n0\tleft\n", encoding="utf-8")
    reader = AdmittedResourceReader.from_resource_preflight(
        [str(path)],
        _preflight([str(path)], monkeypatch),
    )
    admitted_stat = path.stat()

    path.write_text("onset\ttrial_type\n0\trght\n", encoding="utf-8")
    os.utime(
        path,
        ns=(admitted_stat.st_atime_ns, admitted_stat.st_mtime_ns + 1_000_000_000),
    )

    with pytest.raises(PreconditionError) as raised:
        reader.assert_unchanged(path, purpose="BIDS events table")

    assert raised.value.diagnostics["code"] == (
        "interpretation_resource_changed_after_admission"
    )
    assert "mtime_ns" in raised.value.diagnostics["changed_fields"]


def test_guard_rejects_a_file_changed_during_parser_materialization(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "labels.csv"
    path.write_text("label\nleft\n", encoding="utf-8")
    reader = AdmittedResourceReader.from_resource_preflight(
        [str(path)],
        _preflight([str(path)], monkeypatch),
    )

    with (
        pytest.raises(PreconditionError) as raised,
        reader.guard([path], purpose="label carrier"),
    ):
        path.write_text("label\nchanged\n", encoding="utf-8")

    assert raised.value.diagnostics["parse_started"] is True


def test_reader_content_probe_rejects_same_size_change_without_timestamp_assumption(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "participants.tsv"
    path.write_text("participant_id\nsub-01\n", encoding="utf-8")
    reader = AdmittedResourceReader.from_resource_preflight(
        [str(path)],
        _preflight([str(path)], monkeypatch),
    )

    path.write_text("participant_id\nsub-02\n", encoding="utf-8")

    with pytest.raises(PreconditionError) as raised:
        reader.assert_unchanged(path, purpose="BIDS metadata materialization")

    assert "content_probe_sha256" in raised.value.diagnostics["changed_fields"]


def test_reader_rejects_paths_missing_from_authoritative_preflight(
    tmp_path,
    monkeypatch,
) -> None:
    admitted = tmp_path / "admitted.csv"
    missing = tmp_path / "missing.csv"
    admitted.write_text("label\n1\n", encoding="utf-8")
    missing.write_text("label\n2\n", encoding="utf-8")

    with pytest.raises(PreconditionError) as raised:
        AdmittedResourceReader.from_resource_preflight(
            [str(admitted), str(missing)],
            _preflight([str(admitted)], monkeypatch),
        )

    assert raised.value.diagnostics["code"] == "interpretation_resource_not_admitted"


def test_guard_expands_eeglab_set_to_its_admitted_external_data_file(
    tmp_path,
    monkeypatch,
) -> None:
    from scipy.io import savemat

    set_path = tmp_path / "subject.set"
    fdt_path = tmp_path / "Arbitrary-Data.FDT"
    fdt_path.write_bytes(b"\0" * (2 * 10 * 4))
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
        do_compression=True,
    )
    paths = [str(set_path), str(fdt_path)]
    reader = AdmittedResourceReader.from_resource_preflight(
        paths,
        _preflight(paths, monkeypatch),
    )

    fdt_path.write_bytes(b"1" * fdt_path.stat().st_size)

    with (
        pytest.raises(PreconditionError) as raised,
        reader.guard([set_path], purpose="embedded EEG event preview"),
    ):
        pass

    assert_filesystem_paths_equal(raised.value.diagnostics["path"], fdt_path)
    assert raised.value.diagnostics["purpose"] == "embedded EEG event preview"


def test_reader_exposes_admitted_recording_bounds_without_loading_signal_data(
    tmp_path,
    monkeypatch,
) -> None:
    import mne
    import numpy as np

    fif_path = tmp_path / "subject_raw.fif"
    raw = mne.io.RawArray(
        np.zeros((2, 10)),
        mne.create_info(["C3", "C4"], sfreq=100.0, ch_types="eeg"),
        verbose="ERROR",
    )
    raw.save(fif_path, overwrite=True, verbose="ERROR")
    paths = [str(fif_path)]

    reader = AdmittedResourceReader.from_resource_preflight(
        paths,
        _preflight(paths, monkeypatch),
    )
    bounds = reader.recording_bounds_for(fif_path)

    assert bounds is not None
    assert bounds.sample_count == 10
    assert bounds.sampling_frequency_hz == 100.0
    rebound = reader.with_dependent_files({})
    assert rebound.recording_bounds_for(fif_path) == bounds


def test_reader_reuses_an_admitted_canonical_path_without_resolving_again(
    tmp_path,
    monkeypatch,
) -> None:
    path = (tmp_path / "events.tsv").resolve()
    path.write_text("onset\tvalue\n0\tleft\n", encoding="utf-8")
    reader = AdmittedResourceReader.from_resource_preflight(
        [str(path)],
        _preflight([str(path)], monkeypatch),
    )
    original_resolve = Path.resolve
    resolve_calls = 0

    def _counted_resolve(self, *args, **kwargs):
        nonlocal resolve_calls
        resolve_calls += 1
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", _counted_resolve)

    reader.assert_unchanged(path, purpose="BIDS events table")
    reader.assert_unchanged(path, purpose="BIDS events table")

    assert resolve_calls == 0


def test_reader_rejects_symlink_replacement_without_opening_its_target(
    tmp_path,
    monkeypatch,
) -> None:
    path = (tmp_path / "events.tsv").resolve()
    outside = (tmp_path / "outside.tsv").resolve()
    path.write_text("onset\tvalue\n0\tleft\n", encoding="utf-8")
    outside.write_text("onset\tvalue\n0\tEVIL\n", encoding="utf-8")
    reader = AdmittedResourceReader.from_resource_preflight(
        [str(path)],
        _preflight([str(path)], monkeypatch),
    )
    path.unlink()
    try:
        path.symlink_to(outside)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symbolic links are unavailable: {exc}")

    opened_replacement: list[Path] = []
    original_open = Path.open

    def _observed_open(candidate: Path, *args, **kwargs):
        if candidate == path:
            opened_replacement.append(candidate)
        return original_open(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "open", _observed_open)

    with pytest.raises(PreconditionError) as raised:
        reader.assert_unchanged(path, purpose="cached Data Interpretation preview")

    assert raised.value.diagnostics["code"] == (
        "interpretation_resource_changed_after_admission"
    )
    assert opened_replacement == []


def test_reader_rejects_open_race_before_reading_replacement_target(
    tmp_path,
    monkeypatch,
) -> None:
    path = (tmp_path / "events.tsv").resolve()
    outside = (tmp_path / "outside.tsv").resolve()
    path.write_text("onset\tvalue\n0\tleft\n", encoding="utf-8")
    outside.write_text("onset\tvalue\n0\tEVIL\n", encoding="utf-8")
    reader = AdmittedResourceReader.from_resource_preflight(
        [str(path)],
        _preflight([str(path)], monkeypatch),
    )
    original_open = os.open

    def _raced_open(candidate, flags, *args, **kwargs):
        if Path(candidate) == path:
            return original_open(outside, flags, *args, **kwargs)
        return original_open(candidate, flags, *args, **kwargs)

    probe_reads: list[bool] = []

    def _observed_probe(handle, file_bytes):
        probe_reads.append(True)
        return "unreachable"

    monkeypatch.setattr(os, "open", _raced_open)
    monkeypatch.setattr(
        data_interpretation_resource_reader,
        "_content_probe_sha256",
        _observed_probe,
    )

    with pytest.raises(PreconditionError) as raised:
        reader.assert_unchanged(path, purpose="cached Data Interpretation preview")

    assert raised.value.diagnostics["code"] == (
        "interpretation_resource_changed_after_admission"
    )
    assert probe_reads == []


def test_guard_expands_explicit_brainvision_parser_dependencies(
    tmp_path,
    monkeypatch,
) -> None:
    vhdr_path = tmp_path / "subject.vhdr"
    eeg_path = tmp_path / "subject.eeg"
    vmrk_path = tmp_path / "subject.vmrk"
    vhdr_path.write_bytes(b"header")
    eeg_path.write_bytes(b"signal")
    vmrk_path.write_bytes(b"marker")
    paths = [str(vhdr_path), str(eeg_path), str(vmrk_path)]
    reader = AdmittedResourceReader.from_resource_preflight(
        paths,
        _preflight(paths, monkeypatch),
        dependent_files={
            str(vhdr_path): [str(eeg_path), str(vmrk_path)],
        },
    )

    vmrk_path.write_bytes(b"Marker")

    with (
        pytest.raises(PreconditionError) as raised,
        reader.guard([vhdr_path], purpose="embedded EEG event preview"),
    ):
        pass

    assert_filesystem_paths_equal(raised.value.diagnostics["path"], vmrk_path)
    assert raised.value.diagnostics["purpose"] == "embedded EEG event preview"


def test_rebinding_parser_dependencies_rejects_a_new_unadmitted_reference(
    tmp_path,
    monkeypatch,
) -> None:
    vhdr_path = tmp_path / "subject.vhdr"
    admitted_eeg_path = tmp_path / "subject.eeg"
    changed_eeg_path = tmp_path / "changed.eeg"
    vhdr_path.write_bytes(b"header")
    admitted_eeg_path.write_bytes(b"admitted signal")
    changed_eeg_path.write_bytes(b"changed signal")
    admitted_paths = [str(vhdr_path), str(admitted_eeg_path)]
    reader = AdmittedResourceReader.from_resource_preflight(
        admitted_paths,
        _preflight(admitted_paths, monkeypatch),
        dependent_files={str(vhdr_path): [str(admitted_eeg_path)]},
    )

    with pytest.raises(PreconditionError) as raised:
        reader.with_dependent_files(
            {str(vhdr_path): [str(changed_eeg_path)]},
        )

    assert raised.value.diagnostics["code"] == "interpretation_resource_not_admitted"
    assert_filesystem_paths_equal(raised.value.diagnostics["owner_path"], vhdr_path)
    assert_filesystem_path_lists_equal(
        raised.value.diagnostics["missing_paths"],
        [changed_eeg_path],
    )
