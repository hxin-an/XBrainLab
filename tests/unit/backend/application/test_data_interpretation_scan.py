import json
from pathlib import Path

import pytest

from XBrainLab.backend.application import data_interpretation_metadata
from XBrainLab.backend.application import data_interpretation_scan as scan_module
from XBrainLab.backend.application.data_interpretation_candidate import (
    build_interpretation_candidate,
    resolve_interpretation_resource_scope,
)
from XBrainLab.backend.application.data_interpretation_resource_reader import (
    AdmittedResourceReader,
)
from XBrainLab.backend.application.data_interpretation_scan import (
    ScanResult,
    discover_source_preflight_scope,
    scan_source_path,
)
from XBrainLab.backend.application.errors import PreconditionError
from XBrainLab.backend.application.resource_guard import (
    check_import_resource_preflight,
)


def _write_valid_bids_description(root: Path) -> None:
    (root / "dataset_description.json").write_text(
        '{"Name": "scan-test", "BIDSVersion": "1.11.1"}',
        encoding="utf-8",
    )


def _write_minimal_edf_header(
    path: Path,
    signal_labels: list[str],
    *,
    samples_per_record: int = 1,
) -> None:
    signal_count = len(signal_labels)
    header_bytes = 256 + signal_count * 256
    fixed_header = bytearray(b" " * 256)
    fixed_header[:8] = b"0       "
    fixed_header[184:192] = f"{header_bytes:<8}".encode("ascii")
    fixed_header[236:244] = b"1       "
    fixed_header[244:252] = b"1       "
    fixed_header[252:256] = f"{signal_count:<4}".encode("ascii")
    labels = b"".join(f"{label:<16}".encode("ascii") for label in signal_labels)
    signal_header = b"".join(
        (
            labels,
            b" " * (signal_count * 80),
            b"uV      " * signal_count,
            b"-100    " * signal_count,
            b"100     " * signal_count,
            b"-32768  " * signal_count,
            b"32767   " * signal_count,
            b" " * (signal_count * 80),
            f"{samples_per_record:<8}".encode("ascii") * signal_count,
            b" " * (signal_count * 32),
        )
    )
    payload = b"\0" * (signal_count * samples_per_record * 2)
    path.write_bytes(bytes(fixed_header) + signal_header + payload)


def _scan_folder_with_admitted_resources(root: Path) -> ScanResult:
    scope = discover_source_preflight_scope(
        source_path=str(root),
        source_hint="folder",
    )
    reader = AdmittedResourceReader.from_resource_preflight(
        scope.paths,
        check_import_resource_preflight(scope.paths),
    )
    return scan_source_path(
        scan_id="scan-1",
        source_path=str(root),
        source_hint="folder",
        preflight_scope=scope,
        resource_reader=reader,
    )


def test_scan_source_path_collects_bids_files_labels_and_metadata(tmp_path: Path):
    _write_valid_bids_description(tmp_path)
    eeg_file = (
        tmp_path / "sub-01" / "ses-01" / "eeg" / "sub-01_ses-01_task-mi_run-1_raw.fif"
    )
    events_file = (
        tmp_path
        / "sub-01"
        / "ses-01"
        / "eeg"
        / "sub-01_ses-01_task-mi_run-1_events.tsv"
    )
    channels_file = (
        tmp_path
        / "sub-01"
        / "ses-01"
        / "eeg"
        / "sub-01_ses-01_task-mi_run-1_channels.tsv"
    )
    eeg_file.parent.mkdir(parents=True)
    (tmp_path / "participants.tsv").write_text(
        "participant_id\nsub-01\n",
        encoding="utf-8",
    )
    eeg_file.write_text("", encoding="utf-8")
    events_file.write_text("onset\tduration\ttrial_type\n", encoding="utf-8")
    channels_file.write_text("name\tstatus\nC3\tgood\n", encoding="utf-8")

    scan = scan_source_path(scan_id="scan-1", source_path=str(tmp_path))

    assert isinstance(scan, ScanResult)
    assert scan.source_kind == "bids"
    assert scan.eeg_files == [str(eeg_file)]
    assert scan.label_carriers == [str(events_file)]
    assert scan.metadata[0].subject.value == "01"
    assert scan.bids["is_bids"] is True
    assert scan.bids["events_files"] == [str(events_file)]
    assert scan.bids["channels_files"] == [str(channels_file)]
    assert scan.bids["participants_file"] == str(tmp_path / "participants.tsv")


def test_strict_bids_scope_excludes_other_datatypes_and_derivatives(
    tmp_path: Path,
) -> None:
    _write_valid_bids_description(tmp_path)
    raw_eeg_1 = tmp_path / "sub-01/eeg/sub-01_task-mi_run-1_eeg.edf"
    raw_eeg_2 = tmp_path / "sub-01/eeg/sub-01_task-mi_run-2_eeg.edf"
    raw_events_1 = tmp_path / "sub-01/eeg/sub-01_task-mi_run-1_events.tsv"
    raw_events_2 = tmp_path / "sub-01/eeg/sub-01_task-mi_run-2_events.tsv"
    meg_file = tmp_path / "sub-01/meg/sub-01_task-mi_meg.fif"
    ieeg_file = tmp_path / "sub-01/ieeg/sub-01_task-mi_ieeg.edf"
    beh_file = tmp_path / "sub-01/beh/sub-01_task-mi_beh.edf"
    derivative_eeg = (
        tmp_path
        / "derivatives/clean/sub-01/eeg/sub-01_task-mi_run-1_desc-clean_eeg.edf"
    )
    derivative_events = (
        tmp_path
        / "derivatives/clean/sub-01/eeg/sub-01_task-mi_run-1_desc-clean_events.tsv"
    )
    for path in (
        raw_eeg_1,
        raw_eeg_2,
        meg_file,
        ieeg_file,
        beh_file,
        derivative_eeg,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"header only")
    for path in (raw_events_1, raw_events_2, derivative_events):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "onset\tduration\ttrial_type\n0\t1\tleft\n",
            encoding="utf-8",
        )

    scan = scan_source_path(
        scan_id="scan-mixed-bids",
        source_path=str(tmp_path),
        source_hint="bids",
    )

    assert scan.eeg_files == [str(raw_eeg_1.resolve()), str(raw_eeg_2.resolve())]
    assert scan.label_carriers == [
        str(raw_events_1.resolve()),
        str(raw_events_2.resolve()),
    ]
    assert scan.bids["datatypes"] == ["eeg"]
    assert scan.bids["eeg_file_count"] == 2
    assert not any("derivatives" in path for path in scan.eeg_files)
    assert not any(
        f"/{datatype}/" in path
        for path in scan.eeg_files
        for datatype in ("meg", "ieeg", "beh")
    )

    selected_scope = resolve_interpretation_resource_scope(
        scan,
        {"selected_eeg_files": [str(raw_eeg_2)]},
    )

    assert selected_scope.selected_eeg_files == [str(raw_eeg_2.resolve())]
    assert selected_scope.materializable_eeg_files == [str(raw_eeg_2.resolve())]
    assert selected_scope.label_carriers == [str(raw_events_2.resolve())]


def test_multiple_eeg_files_are_not_a_warning_without_a_concrete_ambiguity(
    tmp_path: Path,
) -> None:
    for name in ("subject01_run01.edf", "subject02_run01.edf"):
        (tmp_path / name).write_bytes(b"header only")

    scan = scan_source_path(
        scan_id="scan-multiple-explicit-files",
        source_path=str(tmp_path),
        source_hint="folder",
    )

    assert len(scan.eeg_files) == 2
    assert not any("Multiple EEG files" in warning for warning in scan.warnings)


def test_bids_preflight_scope_discovers_all_scan_materialization_paths_without_tsv_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_valid_bids_description(tmp_path)
    eeg_file = tmp_path / "sub-01" / "eeg" / "sub-01_task-mi_eeg.fif"
    events_file = tmp_path / "sub-01" / "eeg" / "sub-01_task-mi_events.tsv"
    events_json = tmp_path / "sub-01" / "eeg" / "sub-01_task-mi_events.json"
    channels_file = tmp_path / "sub-01" / "eeg" / "sub-01_task-mi_channels.tsv"
    participants_file = tmp_path / "participants.tsv"
    eeg_file.parent.mkdir(parents=True)
    eeg_file.write_bytes(b"header only")
    events_file.write_text("onset\ttrial_type\n0\tleft\n", encoding="utf-8")
    events_json.write_text(
        json.dumps({"trial_type": {"Description": "Task condition"}}),
        encoding="utf-8",
    )
    channels_file.write_text("name\tstatus\nC3\tgood\n", encoding="utf-8")
    participants_file.write_text("participant_id\nsub-01\n", encoding="utf-8")

    def _must_not_read_tsv(_path: Path) -> list[dict[str, str]]:
        pytest.fail("bounded preflight discovery materialized a BIDS TSV")

    monkeypatch.setattr(
        data_interpretation_metadata, "_read_tsv_rows", _must_not_read_tsv
    )

    scope = discover_source_preflight_scope(
        source_path=str(tmp_path),
        source_hint="bids",
    )

    assert scope.eeg_files == [str(eeg_file.resolve())]
    assert scope.label_carriers == [str(events_file.resolve())]
    assert scope.metadata_files == [
        str((tmp_path / "dataset_description.json").resolve()),
        str(participants_file.resolve()),
        str(channels_file.resolve()),
        str(events_json.resolve()),
    ]
    assert set(scope.paths) == {
        str(eeg_file.resolve()),
        str(events_file.resolve()),
        str((tmp_path / "dataset_description.json").resolve()),
        str(participants_file.resolve()),
        str(channels_file.resolve()),
        str(events_json.resolve()),
    }


def test_bids_preflight_rejects_dataset_description_symlink_outside_selected_root(
    tmp_path: Path,
) -> None:
    selected_root = tmp_path / "selected"
    eeg_file = selected_root / "sub-01" / "eeg" / "sub-01_task-mi_eeg.fif"
    eeg_file.parent.mkdir(parents=True)
    eeg_file.write_bytes(b"header only")
    outside_description = tmp_path / "outside-dataset-description.json"
    outside_description.write_text(
        '{"Name": "outside", "BIDSVersion": "1.11.1"}',
        encoding="utf-8",
    )
    description_link = selected_root / "dataset_description.json"
    description_link.symlink_to(outside_description)

    scope = discover_source_preflight_scope(
        source_path=str(selected_root),
        source_hint="bids",
    )

    escaped_description = str(outside_description.resolve())
    assert scope.bids["looks_like_bids"] is False
    assert scope.bids["is_bids"] is False
    assert escaped_description not in scope.metadata_files
    assert escaped_description not in scope.paths
    assert scope.bids["dataset_description"] is None
    assert any(
        "Skipped symbolic link" in warning for warning in scope.discovery_warnings
    )


def test_folder_preflight_does_not_discover_bids_metadata_from_parent(
    tmp_path: Path,
) -> None:
    _write_valid_bids_description(tmp_path)
    selected_root = tmp_path / "selected"
    selected_root.mkdir()
    eeg_file = selected_root / "subject.gdf"
    eeg_file.write_bytes(b"header only")

    scope = discover_source_preflight_scope(
        source_path=str(selected_root),
        source_hint="folder",
    )

    assert scope.bids["root"] == str(selected_root.resolve())
    assert scope.bids["dataset_description"] is None
    assert scope.metadata_files == []
    assert str((tmp_path / "dataset_description.json").resolve()) not in scope.paths


def test_bids_provisional_discovery_rejects_windows_datatype_reparse_point(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_root = tmp_path / "selected"
    selected_root.mkdir()
    _write_valid_bids_description(selected_root)
    datatype_junction = selected_root / "sub-01" / "eeg"
    datatype_junction.mkdir(parents=True)
    junction_visible_eeg = datatype_junction / "sub-01_task-mi_eeg.fif"
    junction_visible_eeg.write_bytes(b"outside through junction")
    original_lstat = Path.lstat

    class _ReparseDirectoryStat:
        def __init__(self, value):
            self._value = value
            self.st_file_attributes = scan_module._WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT

        def __getattr__(self, name: str):
            return getattr(self._value, name)

    def _lstat_with_simulated_reparse_point(path: Path):
        value = original_lstat(path)
        if path == datatype_junction:
            return _ReparseDirectoryStat(value)
        return value

    monkeypatch.setattr(Path, "lstat", _lstat_with_simulated_reparse_point)

    scope = discover_source_preflight_scope(
        source_path=str(selected_root),
        source_hint="bids",
    )

    assert scope.bids["looks_like_bids"] is False
    assert scope.bids["is_bids"] is False
    assert scope.eeg_files == []
    assert str(junction_visible_eeg.resolve()) not in scope.paths
    assert any(
        "directory junction or reparse point" in warning
        for warning in scope.discovery_warnings
    )


def test_bids_preflight_rejects_metadata_symlinks_outside_selected_root(
    tmp_path: Path,
) -> None:
    selected_root = tmp_path / "selected"
    selected_root.mkdir()
    _write_valid_bids_description(selected_root)
    eeg_file = selected_root / "sub-01" / "eeg" / "sub-01_task-mi_eeg.fif"
    eeg_file.parent.mkdir(parents=True)
    eeg_file.write_bytes(b"header only")
    outside_root = tmp_path / "outside"
    outside_root.mkdir()
    outside_participants = outside_root / "participants.tsv"
    outside_channels = outside_root / "sub-01_task-mi_channels.tsv"
    outside_participants.write_text("participant_id\nsub-99\n", encoding="utf-8")
    outside_channels.write_text("name\tstatus\nC3\tbad\n", encoding="utf-8")
    (selected_root / "participants.tsv").symlink_to(outside_participants)
    (eeg_file.parent / "sub-01_task-mi_channels.tsv").symlink_to(outside_channels)

    scope = discover_source_preflight_scope(
        source_path=str(selected_root),
        source_hint="bids",
    )
    reader = AdmittedResourceReader.from_resource_preflight(
        scope.paths,
        check_import_resource_preflight(scope.paths),
    )
    scan = scan_source_path(
        scan_id="scan-external-metadata",
        source_path=str(selected_root),
        source_hint="bids",
        preflight_scope=scope,
        materialize_metadata=False,
    )

    description = str((selected_root / "dataset_description.json").resolve())
    escaped_paths = {
        str(outside_participants.resolve()),
        str(outside_channels.resolve()),
    }
    assert scope.metadata_files == [description]
    assert escaped_paths.isdisjoint(scope.paths)
    assert reader.admits(outside_participants) is False
    assert reader.admits(outside_channels) is False
    assert scope.bids["participants_file"] is None
    assert scope.bids["channels_files"] == []
    assert scan.bids["participants_file"] is None
    assert scan.bids["channels_files"] == []


def test_bids_metadata_materialization_rejects_changed_admitted_file(
    tmp_path: Path,
) -> None:
    _write_valid_bids_description(tmp_path)
    eeg_file = tmp_path / "sub-01" / "eeg" / "sub-01_task-mi_eeg.fif"
    events_file = tmp_path / "sub-01" / "eeg" / "sub-01_task-mi_events.tsv"
    participants_file = tmp_path / "participants.tsv"
    eeg_file.parent.mkdir(parents=True)
    eeg_file.write_bytes(b"header only")
    events_file.write_text("onset\ttrial_type\n0\tleft\n", encoding="utf-8")
    participants_file.write_text("participant_id\nsub-01\n", encoding="utf-8")
    scope = discover_source_preflight_scope(
        source_path=str(tmp_path),
        source_hint="bids",
    )
    reader = AdmittedResourceReader.from_resource_preflight(
        scope.paths,
        check_import_resource_preflight(scope.paths),
    )
    participants_file.write_text("participant_id\nsub-02\n", encoding="utf-8")

    with pytest.raises(PreconditionError) as raised:
        scan_source_path(
            scan_id="scan-changed-metadata",
            source_path=str(tmp_path),
            source_hint="bids",
            preflight_scope=scope,
            resource_reader=reader,
        )

    assert raised.value.diagnostics["purpose"] == "BIDS metadata materialization"


@pytest.mark.parametrize(
    ("source_hint", "expected_surface"),
    [("bids", "blocked"), ("auto", "warning")],
)
def test_oversized_dataset_description_is_bounded_before_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_hint: str,
    expected_surface: str,
) -> None:
    eeg_file = tmp_path / "sub-01" / "eeg" / "sub-01_task-mi_eeg.fif"
    eeg_file.parent.mkdir(parents=True)
    eeg_file.write_bytes(b"header only")
    description = tmp_path / "dataset_description.json"
    description.write_text("{}", encoding="utf-8")
    with description.open("ab") as handle:
        handle.truncate(scan_module.DATASET_DESCRIPTION_DISCOVERY_MAX_BYTES + 1)
    original_read_text = Path.read_text

    def _guarded_read_text(path: Path, *args, **kwargs):
        if path == description:
            pytest.fail("dataset_description.json used unbounded read_text")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _guarded_read_text)

    scan = scan_source_path(
        scan_id="scan-oversized-description",
        source_path=str(tmp_path),
        source_hint=source_hint,
        materialize_metadata=False,
    )

    issue = scan.bids["root_validation_issue"]
    assert "exceeds the bounded discovery limit" in issue
    assert str(scan_module.DATASET_DESCRIPTION_DISCOVERY_MAX_BYTES) in issue
    if expected_surface == "blocked":
        assert any(issue in item for item in scan.blocked_reasons)
    else:
        assert scan.blocked_reasons == []
        assert issue in scan.warnings


def test_nested_bids_roots_share_one_metadata_budget_without_payload_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    per_description_bytes = scan_module.DATASET_DESCRIPTION_DISCOVERY_MAX_BYTES // 8
    description_paths: set[Path] = set()
    for index in range(12):
        nested_root = tmp_path / f"nested-{index:02d}"
        eeg_file = nested_root / "sub-01" / "eeg" / "sub-01_task-mi_eeg.fif"
        eeg_file.parent.mkdir(parents=True)
        eeg_file.write_bytes(b"header only")
        description = nested_root / "dataset_description.json"
        encoded = b'{"Name":"nested","BIDSVersion":"1.10.0"}'
        description.write_bytes(
            encoded + b" " * (per_description_bytes - len(encoded)),
        )
        description_paths.add(description.resolve())
    real_path_open = Path.open
    metadata_bytes_read = 0

    class _ObservedReader:
        def __init__(self, handle):
            self._handle = handle

        def __enter__(self):
            self._handle.__enter__()
            return self

        def __exit__(self, *args):
            return self._handle.__exit__(*args)

        def read(self, *args, **kwargs):
            nonlocal metadata_bytes_read
            payload = self._handle.read(*args, **kwargs)
            metadata_bytes_read += len(payload)
            return payload

        def __getattr__(self, name):
            return getattr(self._handle, name)

    def _observed_open(path: Path, *args, **kwargs):
        handle = real_path_open(path, *args, **kwargs)
        mode = str(args[0] if args else kwargs.get("mode", "r"))
        if path.resolve() in description_paths and "r" in mode:
            return _ObservedReader(handle)
        return handle

    monkeypatch.setattr(Path, "open", _observed_open)

    scope = discover_source_preflight_scope(
        source_path=str(tmp_path),
        source_hint="folder",
    )

    discovery = scope.bids["metadata_discovery"]
    assert len(scope.skipped_nested_bids_roots) == 12
    assert metadata_bytes_read == 0
    assert discovery["bytes_read"] == 0
    assert discovery["candidate_bytes"] == per_description_bytes * 12
    assert discovery["budget_bytes"] == (
        scan_module.DATASET_DESCRIPTION_DISCOVERY_MAX_BYTES
    )
    assert discovery["budget_exhausted"] is True
    assert any(
        "shared BIDS metadata byte budget" in warning
        for warning in scope.discovery_warnings
    )


def test_scan_explicit_folder_on_bids_root_does_not_enter_bids_mode(tmp_path: Path):
    _write_valid_bids_description(tmp_path)
    eeg_file = tmp_path / "sub-01" / "ses-01" / "eeg" / "sub-01_ses-01_task-mi_raw.fif"
    events_file = (
        tmp_path / "sub-01" / "ses-01" / "eeg" / "sub-01_ses-01_task-mi_events.tsv"
    )
    eeg_file.parent.mkdir(parents=True)
    eeg_file.write_text("", encoding="utf-8")
    events_file.write_text("onset\tduration\ttrial_type\n", encoding="utf-8")

    scan = scan_source_path(
        scan_id="scan-1",
        source_path=str(tmp_path),
        source_hint="folder",
    )

    assert scan.source_kind == "folder"
    assert scan.bids["is_bids"] is False
    assert scan.bids["looks_like_bids"] is True
    assert scan.label_carriers == [str(events_file.resolve())]
    assert any("Use Import BIDS folder" in item for item in scan.warnings)


def test_scan_explicit_bids_hint_blocks_non_bids_folder(tmp_path: Path):
    eeg_file = tmp_path / "subject_raw.fif"
    eeg_file.write_text("", encoding="utf-8")

    scan = scan_source_path(
        scan_id="scan-1",
        source_path=str(tmp_path),
        source_hint="bids",
    )

    assert scan.source_kind == "bids"
    assert scan.bids["is_bids"] is False
    assert scan.eeg_files == [str(eeg_file.resolve())]
    assert scan.bids["root_validation_issue"] == (
        "dataset_description.json is missing from the selected BIDS root."
    )
    assert scan.blocked_reasons == [
        "dataset_description.json is missing from the selected BIDS root. "
        "Use Import folder for regular EEG files."
    ]


def test_scan_regular_folder_with_sub_prefixed_file_is_not_bids(tmp_path: Path):
    eeg_file = tmp_path / "sub-01_task-mi_raw.fif"
    eeg_file.write_bytes(b"not loaded during scan")

    scan = scan_source_path(scan_id="scan-1", source_path=str(tmp_path))

    assert scan.source_kind == "folder"
    assert scan.bids["is_bids"] is False
    assert scan.eeg_files == [str(eeg_file.resolve())]
    assert not any("BIDS folder has no events.tsv" in item for item in scan.warnings)


@pytest.mark.parametrize(
    "dataset_description",
    [None, "{not-json", "{}"],
    ids=["missing", "malformed", "missing-required-fields"],
)
def test_bids_shaped_folder_without_valid_description_stays_regular_folder(
    tmp_path: Path,
    dataset_description: str | None,
) -> None:
    eeg_file = tmp_path / "sub-01" / "eeg" / "sub-01_task-mi_eeg.fif"
    eeg_file.parent.mkdir(parents=True)
    eeg_file.write_bytes(b"not loaded during scan")
    if dataset_description is not None:
        (tmp_path / "dataset_description.json").write_text(
            dataset_description,
            encoding="utf-8",
        )

    scan = scan_source_path(scan_id="scan-1", source_path=str(tmp_path))

    assert scan.source_kind == "folder"
    assert scan.bids["looks_like_bids"] is False
    assert scan.bids["is_bids"] is False
    assert scan.eeg_files == [str(eeg_file.resolve())]
    assert scan.blocked_reasons == []
    assert any("dataset_description.json" in warning for warning in scan.warnings)


@pytest.mark.parametrize(
    "dataset_description",
    [None, "{not-json", "{}"],
    ids=["missing", "malformed", "missing-required-fields"],
)
def test_explicit_bids_import_blocks_invalid_dataset_root(
    tmp_path: Path,
    dataset_description: str | None,
) -> None:
    eeg_file = tmp_path / "sub-01" / "eeg" / "sub-01_task-mi_eeg.fif"
    eeg_file.parent.mkdir(parents=True)
    eeg_file.write_bytes(b"not loaded during scan")
    if dataset_description is not None:
        (tmp_path / "dataset_description.json").write_text(
            dataset_description,
            encoding="utf-8",
        )

    scan = scan_source_path(
        scan_id="scan-1",
        source_path=str(tmp_path),
        source_hint="bids",
    )

    assert scan.source_kind == "bids"
    assert scan.bids["is_bids"] is False
    assert len(scan.blocked_reasons) == 1
    assert "dataset_description.json" in scan.blocked_reasons[0]
    assert "Use Import folder" in scan.blocked_reasons[0]


def test_scan_regular_folder_skips_nested_bids_dataset(tmp_path: Path):
    first_gdf = tmp_path / "A01T.gdf"
    second_gdf = tmp_path / "A02T.gdf"
    nested_bids = tmp_path / "bids"
    nested_eeg = (
        nested_bids / "sub-01" / "ses-01" / "eeg" / "sub-01_ses-01_task-rest_eeg.vhdr"
    )
    nested_events = (
        nested_bids / "sub-01" / "ses-01" / "eeg" / "sub-01_ses-01_task-rest_events.tsv"
    )
    first_gdf.write_bytes(b"not loaded during scan")
    second_gdf.write_bytes(b"not loaded during scan")
    nested_eeg.parent.mkdir(parents=True)
    _write_valid_bids_description(nested_bids)
    nested_eeg.write_text("", encoding="utf-8")
    nested_events.write_text("onset\tduration\ttrial_type\n", encoding="utf-8")

    scan = scan_source_path(
        scan_id="scan-1",
        source_path=str(tmp_path),
        source_hint="folder",
    )

    assert scan.source_kind == "folder"
    assert scan.eeg_files == [str(first_gdf.resolve()), str(second_gdf.resolve())]
    assert str(nested_eeg.resolve()) not in scan.eeg_files
    assert str(nested_events.resolve()) not in scan.label_carriers
    assert any("Nested BIDS folder was skipped" in warning for warning in scan.warnings)


def test_scan_source_path_blocks_stream_export_without_selectable_eeg(tmp_path: Path):
    xdf_file = tmp_path / "session.xdf"
    xdf_file.write_text("", encoding="utf-8")

    scan = scan_source_path(scan_id="scan-1", source_path=str(tmp_path))

    assert scan.eeg_files == []
    assert scan.source_kind == "folder"
    assert len(scan.blocked_reasons) == 1
    assert "XDF / LSL stream selection is not available" in scan.blocked_reasons[0]


def test_scan_source_path_respects_explicit_file_hint(tmp_path: Path):
    eeg_file = tmp_path / "subject.fif"
    eeg_file.write_text("", encoding="utf-8")

    scan = scan_source_path(
        scan_id="scan-1",
        source_path=str(eeg_file),
        source_hint="file",
    )

    assert scan.source_kind == "file"
    assert scan.source_path == str(eeg_file.resolve())
    assert scan.eeg_files == [str(eeg_file.resolve())]


def test_scan_source_path_for_single_eeg_file_does_not_select_siblings(
    tmp_path: Path,
) -> None:
    selected_eeg = tmp_path / "selected.fif"
    sibling_eeg = tmp_path / "sibling.fif"
    selected_eeg.write_bytes(b"not loaded during scan")
    sibling_eeg.write_bytes(b"not part of explicit file scan")

    scan = scan_source_path(scan_id="scan-1", source_path=str(selected_eeg))
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=scan,
        choices={},
    )

    assert scan.source_kind == "file"
    assert scan.source_path == str(selected_eeg.resolve())
    assert scan.eeg_files == [str(selected_eeg.resolve())]
    assert str(sibling_eeg.resolve()) not in scan.eeg_files
    assert candidate.selected_eeg_files == [str(selected_eeg.resolve())]


def test_folder_scan_does_not_treat_annotation_only_edf_as_eeg(
    tmp_path: Path,
) -> None:
    psg = tmp_path / "subject-PSG.edf"
    hypnogram = tmp_path / "subject-Hypnogram.edf"
    _write_minimal_edf_header(psg, ["EEG Fpz-Cz", "EOG horizontal"])
    _write_minimal_edf_header(hypnogram, ["EDF Annotations"])

    preflight_scope = discover_source_preflight_scope(
        source_path=str(tmp_path),
        source_hint="folder",
    )
    assert str(hypnogram.resolve()) in preflight_scope.eeg_files

    scan = _scan_folder_with_admitted_resources(tmp_path)

    assert scan.eeg_files == [str(psg.resolve())]
    hypnogram_capability = next(
        item
        for item in scan.format_capabilities
        if item["path"] == str(hypnogram.resolve())
    )
    assert hypnogram_capability["format"] == "EDF+ annotations"
    assert hypnogram_capability["role"] == "sidecar"
    assert hypnogram_capability["status"] == "limited"


def test_discovery_scan_classifies_admitted_annotation_only_edf_from_header(
    tmp_path: Path,
) -> None:
    psg = tmp_path / "subject-PSG.edf"
    hypnogram = tmp_path / "subject-Hypnogram.edf"
    _write_minimal_edf_header(psg, ["EEG Fpz-Cz", "EOG horizontal"])
    _write_minimal_edf_header(hypnogram, ["EDF Annotations"])
    scope = discover_source_preflight_scope(
        source_path=str(tmp_path),
        source_hint="folder",
    )
    reader = AdmittedResourceReader.from_resource_preflight(
        scope.paths,
        check_import_resource_preflight(scope.paths),
    )

    scan = scan_source_path(
        scan_id="scan-discovery",
        source_path=str(tmp_path),
        source_hint="folder",
        preflight_scope=scope,
        materialize_metadata=False,
        resource_reader=reader,
    )

    hypnogram_capability = next(
        item
        for item in scan.format_capabilities
        if item["path"] == str(hypnogram.resolve())
    )
    assert scan.eeg_files == [str(psg.resolve())]
    assert hypnogram_capability["format"] == "EDF+ annotations"
    assert hypnogram_capability["role"] == "sidecar"
    assert hypnogram_capability["status"] == "limited"


@pytest.mark.parametrize(
    "signal_labels",
    (
        ["EEG Fpz-Cz", "EDF Annotations"],
        ["EOG horizontal", "EDF Annotations"],
    ),
)
def test_edf_with_physiological_and_annotation_signals_remains_eeg(
    tmp_path: Path,
    signal_labels: list[str],
) -> None:
    mixed_edf = tmp_path / "mixed.edf"
    _write_minimal_edf_header(mixed_edf, signal_labels)

    scan = _scan_folder_with_admitted_resources(tmp_path)

    assert scan.eeg_files == [str(mixed_edf.resolve())]


@pytest.mark.parametrize(
    "payload",
    (
        b"short",
        bytes(bytearray(b" " * 252)),
        bytes(bytearray(b" " * 256) + b"EDF Annotations "),
    ),
)
def test_malformed_or_truncated_edf_is_not_misclassified_as_annotation_only(
    tmp_path: Path,
    payload: bytes,
) -> None:
    malformed = tmp_path / "malformed.edf"
    malformed.write_bytes(payload)

    scan = _scan_folder_with_admitted_resources(tmp_path)

    assert scan.eeg_files == [str(malformed.resolve())]


def test_edf_with_complete_header_but_truncated_payload_is_not_annotation_sidecar(
    tmp_path: Path,
) -> None:
    malformed = tmp_path / "truncated-annotations.edf"
    _write_minimal_edf_header(
        malformed,
        ["EDF Annotations"],
        samples_per_record=10,
    )
    malformed.write_bytes(malformed.read_bytes()[:-1])

    scan = _scan_folder_with_admitted_resources(tmp_path)

    assert scan.eeg_files == [str(malformed.resolve())]


def test_folder_scan_does_not_treat_human_readable_summary_as_label_sequence(
    tmp_path: Path,
) -> None:
    eeg_file = tmp_path / "subject.edf"
    summary = tmp_path / "subject-summary.txt"
    eeg_file.write_bytes(b"header")
    summary.write_text(
        "File Name: subject.edf\nNumber of Seizures in File: 1\n",
        encoding="utf-8",
    )

    scan = scan_source_path(
        scan_id="scan-1",
        source_path=str(tmp_path),
        source_hint="folder",
    )

    assert scan.eeg_files == [str(eeg_file.resolve())]
    assert scan.label_carriers == []
    summary_capability = next(
        item
        for item in scan.format_capabilities
        if item["path"] == str(summary.resolve())
    )
    assert summary_capability["format"] == "Text metadata / report"
    assert summary_capability["role"] == "sidecar"
    assert summary_capability["status"] == "limited"


def test_explicit_summary_named_txt_file_is_respected_as_a_label_source(
    tmp_path: Path,
) -> None:
    eeg_file = tmp_path / "subject.edf"
    explicit_labels = tmp_path / "run-summary.txt"
    eeg_file.write_bytes(b"header")
    explicit_labels.write_text("left\nright\nleft\n", encoding="utf-8")

    scan = scan_source_path(
        scan_id="scan-1",
        source_path=str(eeg_file),
        source_hint="file",
        label_sources=[str(explicit_labels)],
    )

    assert scan.label_sources == [str(explicit_labels.resolve())]
    assert scan.label_carriers == [str(explicit_labels.resolve())]
    assert scan.label_carrier_sources[str(explicit_labels.resolve())] == str(
        explicit_labels.resolve()
    )
    assert not any(
        "did not contain a supported label/event file" in warning
        for warning in scan.warnings
    )


def test_chbmit_seizure_binary_is_visible_as_an_unsupported_sidecar(
    tmp_path: Path,
) -> None:
    eeg_file = tmp_path / "chb01_03.edf"
    seizure_sidecar = tmp_path / "chb01_03.edf.seizures"
    eeg_file.write_bytes(b"header")
    seizure_sidecar.write_bytes(b"\x00CHB-MIT seizure annotations")

    scan = scan_source_path(
        scan_id="scan-1",
        source_path=str(tmp_path),
        source_hint="folder",
    )

    assert scan.eeg_files == [str(eeg_file.resolve())]
    assert scan.label_carriers == []
    capability = next(
        item
        for item in scan.format_capabilities
        if item["path"] == str(seizure_sidecar.resolve())
    )
    assert capability["format"] == "Seizure annotation sidecar"
    assert capability["role"] == "sidecar"
    assert capability["status"] == "unsupported"


def test_scan_source_path_for_single_eeg_file_detects_same_stem_label_carriers(
    tmp_path: Path,
) -> None:
    selected_eeg = tmp_path / "A01T.gdf"
    sibling_eeg = tmp_path / "A02T.gdf"
    matching_label = tmp_path / "A01T.mat"
    sibling_label = tmp_path / "A02T.mat"
    selected_eeg.write_bytes(b"not loaded during scan")
    sibling_eeg.write_bytes(b"not part of explicit file scan")
    matching_label.write_bytes(b"label")
    sibling_label.write_bytes(b"label")

    scan = scan_source_path(scan_id="scan-1", source_path=str(selected_eeg))

    assert scan.source_kind == "file"
    assert scan.eeg_files == [str(selected_eeg.resolve())]
    assert str(sibling_eeg.resolve()) not in scan.eeg_files
    assert scan.label_carriers == [str(matching_label.resolve())]
    assert str(sibling_label.resolve()) not in scan.label_carriers


def test_scan_source_path_for_single_eeg_file_detects_label_subfolder(
    tmp_path: Path,
) -> None:
    selected_eeg = tmp_path / "A01T.gdf"
    labels_dir = tmp_path / "label"
    labels_dir.mkdir()
    matching_label = labels_dir / "A01T.mat"
    sibling_label = labels_dir / "A02T.mat"
    selected_eeg.write_bytes(b"not loaded during scan")
    matching_label.write_bytes(b"label")
    sibling_label.write_bytes(b"label")

    scan = scan_source_path(scan_id="scan-1", source_path=str(selected_eeg))

    assert scan.source_kind == "file"
    assert scan.eeg_files == [str(selected_eeg.resolve())]
    assert scan.label_carriers == [str(matching_label.resolve())]
    assert str(sibling_label.resolve()) not in scan.label_carriers


def test_single_file_nearby_label_scan_rejects_windows_directory_reparse_point(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_root = tmp_path / "selected"
    selected_root.mkdir()
    selected_eeg = selected_root / "A01T.gdf"
    selected_eeg.write_bytes(b"header only")
    junction = selected_root / "labels"
    junction.mkdir()
    junction_child = junction / "A01T.mat"
    junction_child.write_bytes(b"junction-visible label")
    outside_root = tmp_path / "private"
    outside_root.mkdir()
    escaped_label = outside_root / "A01T.mat"
    escaped_label.write_bytes(b"outside label")
    original_iterdir = Path.iterdir
    original_lstat = Path.lstat
    original_resolve = Path.resolve
    enumerated_directories: list[Path] = []

    class _ReparseDirectoryStat:
        def __init__(self, value):
            self._value = value
            self.st_file_attributes = scan_module._WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT

        def __getattr__(self, name: str):
            return getattr(self._value, name)

    def _track_directory_enumeration(path: Path):
        enumerated_directories.append(path)
        return original_iterdir(path)

    def _lstat_with_simulated_reparse_point(path: Path):
        value = original_lstat(path)
        if path == junction:
            return _ReparseDirectoryStat(value)
        return value

    def _resolve_junction_child(path: Path, strict: bool = False) -> Path:
        if path == junction_child:
            return original_resolve(escaped_label, strict=strict)
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "iterdir", _track_directory_enumeration)
    monkeypatch.setattr(Path, "lstat", _lstat_with_simulated_reparse_point)
    monkeypatch.setattr(Path, "resolve", _resolve_junction_child)

    scope = discover_source_preflight_scope(source_path=str(selected_eeg))
    reader = AdmittedResourceReader.from_resource_preflight(
        scope.paths,
        check_import_resource_preflight(scope.paths),
    )

    escaped_path = str(original_resolve(escaped_label))
    assert junction not in enumerated_directories
    assert escaped_path not in scope.label_carriers
    assert escaped_path not in scope.all_files
    assert escaped_path not in scope.paths
    assert reader.admits(escaped_label) is False
    assert scope.discovery_warnings == [
        f"Skipped directory junction or reparse point during source scan: {junction}."
    ]


@pytest.mark.parametrize("directory_name", ["labels", "events"])
def test_single_file_nearby_label_subdir_uses_shared_lazy_scan_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    directory_name: str,
) -> None:
    selected_eeg = tmp_path / "A01T.gdf"
    nearby_dir = tmp_path / directory_name
    nearby_dir.mkdir()
    matching_label = nearby_dir / "A01T.mat"
    selected_eeg.write_bytes(b"header only")
    matching_label.write_bytes(b"label")
    original_iterdir = Path.iterdir
    yielded = 0

    def _bomb_after_budget():
        nonlocal yielded
        for _index in range(scan_module._MAX_SCAN_FILES):
            yielded += 1
            yield matching_label
        raise AssertionError("nearby label discovery consumed past the shared budget")

    def _bounded_iterdir(path: Path):
        if path == nearby_dir:
            return _bomb_after_budget()
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", _bounded_iterdir)

    scope = discover_source_preflight_scope(source_path=str(selected_eeg))

    assert scope.label_carriers == [str(matching_label.resolve())]
    assert yielded < scan_module._MAX_SCAN_FILES
    assert any("scan budget" in warning.lower() for warning in scope.discovery_warnings)


def test_scan_source_path_merges_external_label_sources(tmp_path: Path):
    eeg_dir = tmp_path / "eeg"
    label_dir = tmp_path / "labels"
    eeg_dir.mkdir()
    label_dir.mkdir()
    eeg_file = eeg_dir / "sub-01_task-mi_raw.fif"
    nearby_events = eeg_dir / "sub-01_task-mi_events.tsv"
    external_events = label_dir / "sub-01_task-mi_labels.tsv"
    eeg_file.write_bytes(b"not loaded during scan")
    nearby_events.write_text("onset\ttrial_type\n0.0\tleft\n", encoding="utf-8")
    external_events.write_text("onset\ttrial_type\n0.0\tright\n", encoding="utf-8")

    scan = scan_source_path(
        scan_id="scan-1",
        source_path=str(eeg_dir),
        label_sources=[str(label_dir)],
    )

    assert scan.eeg_files == [str(eeg_file.resolve())]
    assert scan.label_sources == [str(label_dir.resolve())]
    assert scan.label_carriers == [
        str(nearby_events.resolve()),
        str(external_events.resolve()),
    ]
    assert scan.label_carrier_sources[str(nearby_events.resolve())] == "auto"
    assert scan.label_carrier_sources[str(external_events.resolve())] == (
        str(label_dir.resolve())
    )


def test_scan_source_path_skips_symbolic_links(tmp_path: Path):
    eeg_file = tmp_path / "A01T.gdf"
    eeg_file.write_bytes(b"not loaded during scan")
    link_path = tmp_path / "linked.gdf"
    try:
        link_path.symlink_to(eeg_file)
    except OSError:
        return

    scan = scan_source_path(scan_id="scan-1", source_path=str(tmp_path))

    assert scan.eeg_files == [str(eeg_file.resolve())]
    assert any("Skipped symbolic link" in warning for warning in scan.warnings)


def test_regular_folder_scan_rejects_changed_parent_directory_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_root = tmp_path / "selected"
    selected_root.mkdir()
    substituted_child = selected_root / "substituted.gdf"
    substituted_child.write_bytes(b"inside before resolution")
    original_lstat = Path.lstat
    root_observations = 0

    def _changed_parent_identity(path: Path):
        nonlocal root_observations
        status = original_lstat(path)
        if path != selected_root:
            return status
        root_observations += 1
        if root_observations == 1:
            return status
        values = list(status)
        values[1] += 1
        return status.__class__(values)

    monkeypatch.setattr(Path, "lstat", _changed_parent_identity)

    scope = discover_source_preflight_scope(
        source_path=str(selected_root),
        source_hint="folder",
    )

    assert scope.eeg_files == []
    assert scope.all_files == []
    assert any(
        "directory identity changed" in warning for warning in scope.discovery_warnings
    )


def test_regular_folder_scan_rejects_post_enumeration_outside_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_root = tmp_path / "selected"
    selected_root.mkdir()
    outside_eeg = tmp_path / "outside.gdf"
    outside_eeg.write_bytes(b"outside")
    original_iterdir = Path.iterdir

    def _iterdir_with_outside_entry(path: Path):
        if path == selected_root:
            return iter([outside_eeg])
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", _iterdir_with_outside_entry)

    scope = discover_source_preflight_scope(
        source_path=str(selected_root),
        source_hint="folder",
    )

    assert scope.eeg_files == []
    assert scope.all_files == []
    assert any(
        "outside the selected source root after directory enumeration" in warning
        for warning in scope.discovery_warnings
    )


def test_regular_folder_scan_rejects_simulated_windows_directory_reparse_point(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_root = tmp_path / "selected"
    junction = selected_root / "junction"
    junction.mkdir(parents=True)
    escaped_eeg = junction / "outside.gdf"
    escaped_eeg.write_bytes(b"outside through junction")
    original_lstat = Path.lstat

    class _ReparseDirectoryStat:
        def __init__(self, value):
            self._value = value
            self.st_file_attributes = scan_module._WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT

        def __getattr__(self, name: str):
            return getattr(self._value, name)

    def _lstat_with_simulated_reparse_point(path: Path):
        value = original_lstat(path)
        if path == junction:
            return _ReparseDirectoryStat(value)
        return value

    monkeypatch.setattr(Path, "lstat", _lstat_with_simulated_reparse_point)

    scope = discover_source_preflight_scope(
        source_path=str(selected_root),
        source_hint="folder",
    )

    assert scope.eeg_files == []
    assert scope.all_files == []
    assert any(
        "directory junction or reparse point" in warning
        for warning in scope.discovery_warnings
    )


def test_scan_source_path_warns_when_folder_depth_budget_is_reached(tmp_path: Path):
    current = tmp_path
    for index in range(10):
        current = current / f"level-{index}"
        current.mkdir()
    deep_eeg = current / "A01T.gdf"
    deep_eeg.write_bytes(b"not loaded during scan")

    scan = scan_source_path(scan_id="scan-1", source_path=str(tmp_path))

    assert str(deep_eeg.resolve()) not in scan.eeg_files
    assert any("deeper than" in warning for warning in scan.warnings)
