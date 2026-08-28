from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from XBrainLab.backend.application import (
    data_interpretation_label_carriers,
    data_interpretation_parsed_cache,
)
from XBrainLab.backend.application.data_interpretation_bids import _read_events_rows
from XBrainLab.backend.application.data_interpretation_bids_resources import (
    BidsEventsJsonReader,
)
from XBrainLab.backend.application.data_interpretation_metadata import (
    BidsMetadataReadBudget,
    _read_bids_dataset_description,
)
from XBrainLab.backend.application.data_interpretation_parsed_cache import (
    ParsedContentCache,
    default_parsed_content_cache,
)
from XBrainLab.backend.application.data_interpretation_resource_reader import (
    AdmittedResourceReader,
    _current_identity,
)
from XBrainLab.backend.application.resource_guard import ResourcePreflightResult


@pytest.fixture(autouse=True)
def _clear_default_cache() -> Iterator[None]:
    default_parsed_content_cache().clear()
    yield
    default_parsed_content_cache().clear()


def test_json_cache_key_binds_parser_schema_and_full_content_identity() -> None:
    cache = ParsedContentCache(max_entries=8, max_retained_bytes=4096)
    payload = b'{"Name":"Example","BIDSVersion":"1.9.0"}'

    first, first_key = cache.json_value_from_verified_bytes(
        payload,
        parser_id="dataset-description",
        schema_version=1,
    )
    repeated, repeated_key = cache.json_value_from_verified_bytes(
        payload,
        parser_id="dataset-description",
        schema_version=1,
    )
    _changed_schema, changed_schema_key = cache.json_value_from_verified_bytes(
        payload,
        parser_id="dataset-description",
        schema_version=2,
    )

    assert first == repeated
    assert first_key == repeated_key
    assert first_key.content_bytes == len(payload)
    assert first_key.content_sha256 == hashlib.sha256(payload).hexdigest()
    assert changed_schema_key != first_key
    assert cache.diagnostics()["parse_count"] == 2
    assert cache.diagnostics()["hit_count"] == 1


def test_returned_json_cannot_mutate_cached_truth() -> None:
    cache = ParsedContentCache(max_entries=4, max_retained_bytes=4096)
    payload = b'{"trial_type":{"Levels":{"1":"Left"}}}'

    first, _key = cache.json_value_from_verified_bytes(
        payload,
        parser_id="events-json",
        schema_version=1,
    )
    first["trial_type"]["Levels"]["1"] = "mutated"
    repeated, _key = cache.json_value_from_verified_bytes(
        payload,
        parser_id="events-json",
        schema_version=1,
    )

    assert repeated["trial_type"]["Levels"]["1"] == "Left"


def test_path_cache_reuses_unchanged_bytes_and_invalidates_changed_file(
    tmp_path: Path,
) -> None:
    cache = ParsedContentCache(max_entries=8, max_retained_bytes=16_384)
    path = tmp_path / "events.tsv"
    path.write_text("onset\ttrial_type\n0\tleft\n", encoding="utf-8")

    first = cache.delimited_table_from_path(
        path,
        delimiter="\t",
        parser_id="bids-events-table",
        schema_version=1,
    )
    repeated = cache.delimited_table_from_path(
        path,
        delimiter="\t",
        parser_id="bids-events-table",
        schema_version=1,
    )
    assert first.dict_rows() == repeated.dict_rows()
    assert cache.diagnostics()["file_read_count"] == 1
    projected = first.dict_rows()
    projected[0]["trial_type"] = "mutated"
    assert repeated.dict_rows()[0]["trial_type"] == "left"

    path.write_text("onset\ttrial_type\n0\tfoot\n", encoding="utf-8")
    changed = cache.delimited_table_from_path(
        path,
        delimiter="\t",
        parser_id="bids-events-table",
        schema_version=1,
    )

    assert changed.dict_rows()[0]["trial_type"] == "foot"
    assert cache.diagnostics()["file_read_count"] == 2
    assert cache.diagnostics()["parse_count"] == 2


def test_stable_descriptor_with_different_metadata_is_accepted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "sidecar.json"
    path.write_text('{"Name":"Example"}', encoding="utf-8")
    real_fstat = os.fstat
    real_lstat = Path.lstat

    def _different_path_metadata(value: Path) -> SimpleNamespace:
        observed = real_lstat(value)
        if value != path:
            return observed
        return SimpleNamespace(
            st_mode=observed.st_mode,
            st_size=observed.st_size,
            st_dev=observed.st_dev + 10,
            st_ino=observed.st_ino + 10,
            st_mtime_ns=observed.st_mtime_ns + 10,
            st_ctime_ns=observed.st_ctime_ns + 10,
            st_file_attributes=0,
        )

    def _different_descriptor_metadata(fd: int) -> SimpleNamespace:
        observed = real_fstat(fd)
        return SimpleNamespace(
            st_mode=observed.st_mode,
            st_size=observed.st_size,
            st_dev=observed.st_dev + 1,
            st_ino=observed.st_ino + 1,
            st_mtime_ns=observed.st_mtime_ns + 1,
            st_ctime_ns=observed.st_ctime_ns + 1,
        )

    monkeypatch.setattr(os, "fstat", _different_descriptor_metadata)
    monkeypatch.setattr(Path, "lstat", _different_path_metadata)

    payload, identity = data_interpretation_parsed_cache._stable_file_bytes(
        path,
        max_file_bytes=1024,
    )
    probe_identity = data_interpretation_parsed_cache._path_identity(path)

    assert payload == b'{"Name":"Example"}'
    assert identity.file_bytes == len(payload)
    assert probe_identity.content_probe_sha256


def test_parsed_cache_rejects_actual_growth_beyond_bounded_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "sidecar.json"
    path.write_bytes(b"1234")
    real_open = os.open

    def _grow_after_entry_stat(*args, **kwargs) -> int:
        descriptor = real_open(*args, **kwargs)
        path.write_bytes(b"12345")
        return descriptor

    monkeypatch.setattr(os, "open", _grow_after_entry_stat)

    with pytest.raises(data_interpretation_parsed_cache.ParsedContentTooLargeError):
        data_interpretation_parsed_cache._stable_file_bytes(path, max_file_bytes=4)


def test_cache_retention_is_bounded_by_entries_and_bytes() -> None:
    cache = ParsedContentCache(max_entries=2, max_retained_bytes=190)
    for index in range(5):
        cache.json_value_from_verified_bytes(
            json.dumps({"value": f"row-{index}"}).encode(),
            parser_id="bounded-json",
            schema_version=1,
        )

    diagnostics = cache.diagnostics()
    assert diagnostics["entry_count"] <= 2
    assert diagnostics["retained_bytes"] <= 190
    assert diagnostics["eviction_count"] >= 3


def test_cache_parses_one_key_once_under_concurrency(monkeypatch) -> None:
    from XBrainLab.backend.application import data_interpretation_parsed_cache

    cache = ParsedContentCache(max_entries=8, max_retained_bytes=4096)
    payload = b'{"Name":"Concurrent"}'
    parse_count = 0
    original = data_interpretation_parsed_cache._parse_json_value

    def _counted_parse(encoded: bytes):
        nonlocal parse_count
        parse_count += 1
        return original(encoded)

    monkeypatch.setattr(
        data_interpretation_parsed_cache,
        "_parse_json_value",
        _counted_parse,
    )
    with ThreadPoolExecutor(max_workers=8) as executor:
        values = list(
            executor.map(
                lambda _index: cache.json_value_from_verified_bytes(
                    payload,
                    parser_id="threaded-json",
                    schema_version=1,
                )[0],
                range(32),
            )
        )

    assert all(value == {"Name": "Concurrent"} for value in values)
    assert parse_count == 1


def test_match_labels_reuses_one_complete_events_table(
    tmp_path: Path,
) -> None:
    events = tmp_path / "sub-01_task-mi_events.tsv"
    events.write_text(
        "onset\tduration\ttrial_type\tvalue\n0\t1\tleft\t1\n1\t1\tright\t2\n",
        encoding="utf-8",
    )

    first = data_interpretation_label_carriers.build_label_carrier_plan(
        [str(events)],
        {},
        recommend_bids_label_field=True,
    )
    repeated = data_interpretation_label_carriers.build_label_carrier_plan(
        [str(events)],
        {events.name: {"label_field": "trial_type"}},
        recommend_bids_label_field=True,
    )

    assert first[0]["label_value_counts"] == repeated[0]["label_value_counts"]
    assert default_parsed_content_cache().diagnostics()["file_read_count"] == 1


def test_changed_events_table_invalidates_match_labels_projection(
    tmp_path: Path,
) -> None:
    events = tmp_path / "sub-01_task-mi_events.tsv"
    events.write_text(
        "onset\tduration\ttrial_type\n0\t1\tleft\n",
        encoding="utf-8",
    )
    first = data_interpretation_label_carriers.build_label_carrier_plan(
        [str(events)],
        {events.name: {"label_field": "trial_type"}},
    )

    events.write_text(
        "onset\tduration\ttrial_type\n0\t1\tfoot\n",
        encoding="utf-8",
    )
    changed = data_interpretation_label_carriers.build_label_carrier_plan(
        [str(events)],
        {events.name: {"label_field": "trial_type"}},
    )

    assert first[0]["label_value_counts"] == {"left": 1}
    assert changed[0]["label_value_counts"] == {"foot": 1}
    assert default_parsed_content_cache().diagnostics()["file_read_count"] == 2


def test_windows_guard_does_not_reuse_same_size_middle_rewrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = ParsedContentCache(max_entries=8, max_retained_bytes=64_000)
    path = tmp_path / "events.tsv"
    original = (
        "onset\ttrial_type\n"
        + ("1\tpadding\n" * 512)
        + "0\tleft\n"
        + ("2\tpadding\n" * 512)
        + "3\tright\n"
    )
    changed = original.replace("0\tleft", "0\tfoot")
    assert len(changed.encode()) == len(original.encode())
    path.write_text(original, encoding="utf-8")
    first = cache.delimited_table_from_path(
        path,
        delimiter="\t",
        parser_id="windows-middle-rewrite",
    )
    admitted_stat = path.stat()
    path.write_text(changed, encoding="utf-8")
    os.utime(
        path,
        ns=(admitted_stat.st_atime_ns, admitted_stat.st_mtime_ns),
    )
    monkeypatch.setattr(
        data_interpretation_parsed_cache,
        "_STAT_CHANGE_TIME_IS_RELIABLE",
        False,
    )

    with data_interpretation_parsed_cache.verified_parsed_content_paths(
        {path: _current_identity(path)}
    ):
        observed = cache.delimited_table_from_path(
            path,
            delimiter="\t",
            parser_id="windows-middle-rewrite",
        )

    assert first.dict_rows()[512]["trial_type"] == "left"
    assert observed.dict_rows()[512]["trial_type"] == "foot"
    assert cache.diagnostics()["file_read_count"] == 2


def test_new_admission_identity_cannot_reuse_an_old_same_path_binding(
    tmp_path: Path,
) -> None:
    cache = ParsedContentCache(max_entries=8, max_retained_bytes=64_000)
    path = tmp_path / "events.tsv"
    path.write_text("onset\ttrial_type\n0\tleft\n", encoding="utf-8")
    first = cache.delimited_table_from_path(
        path,
        delimiter="\t",
        parser_id="new-admission",
    )

    path.write_text("onset\ttrial_type\n0\tfoot\n", encoding="utf-8")
    with data_interpretation_parsed_cache.verified_parsed_content_paths(
        {path: _current_identity(path)}
    ):
        changed = cache.delimited_table_from_path(
            path,
            delimiter="\t",
            parser_id="new-admission",
        )

    assert first.dict_rows()[0]["trial_type"] == "left"
    assert changed.dict_rows()[0]["trial_type"] == "foot"
    assert cache.diagnostics()["file_read_count"] == 2


def test_label_plan_and_strict_bids_review_share_one_table_parse(
    tmp_path: Path,
) -> None:
    events = tmp_path / "sub-01_task-mi_events.tsv"
    events.write_text(
        "onset\tduration\ttrial_type\n0\t1\tleft\n",
        encoding="utf-8",
    )

    data_interpretation_label_carriers.build_label_carrier_plan(
        [str(events)],
        {events.name: {"label_field": "trial_type"}},
    )
    rows, columns, issue = _read_events_rows(events)

    assert issue is None
    assert rows == [{"onset": "0", "duration": "1", "trial_type": "left"}]
    assert columns == {
        "onset": "onset",
        "duration": "duration",
        "trial_type": "trial_type",
    }
    diagnostics = default_parsed_content_cache().diagnostics()
    assert diagnostics["file_read_count"] == 1
    assert diagnostics["parse_count"] == 1


def test_admitted_review_groups_avoid_per_projection_file_reopens(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = tmp_path / "sub-01_task-mi_events.tsv"
    events.write_text(
        "onset\tduration\ttrial_type\tvalue\n0\t1\tleft\t1\n1\t1\tright\t2\n",
        encoding="utf-8",
    )
    resolved = str(events.resolve())
    reader = AdmittedResourceReader.from_resource_preflight(
        [resolved],
        ResourcePreflightResult(
            (),
            {
                "risk_level": "safe",
                "files": [
                    {
                        "path": resolved,
                        "file_bytes": events.stat().st_size,
                    }
                ],
            },
        ),
    )
    real_open = os.open
    open_count = 0

    def _counted_open(path, flags, *args, **kwargs):
        nonlocal open_count
        if os.path.abspath(os.fspath(path)) == resolved:
            open_count += 1
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", _counted_open)

    data_interpretation_label_carriers.build_label_carrier_plan(
        [resolved],
        {},
        resource_reader=reader,
        recommend_bids_label_field=True,
    )
    data_interpretation_label_carriers.build_label_carrier_plan(
        [resolved],
        {events.name: {"label_field": "trial_type"}},
        resource_reader=reader,
        recommend_bids_label_field=True,
    )

    # First recommendation guard + first carrier guard + repeated carrier
    # guard account for six freshness probes; only the first parse reads the
    # complete table.  Individual projections add no descriptor opens.
    assert open_count == 7
    diagnostics = default_parsed_content_cache().diagnostics()
    assert diagnostics["file_read_count"] == 1
    assert diagnostics["parse_count"] == 1


def test_dataset_description_reuses_parse_and_changed_content_invalidates(
    tmp_path: Path,
) -> None:
    description = tmp_path / "dataset_description.json"
    description.write_text(
        '{"Name":"First","BIDSVersion":"1.9.0"}',
        encoding="utf-8",
    )

    first, first_issue = _read_bids_dataset_description(
        description,
        BidsMetadataReadBudget(),
    )
    repeated, repeated_issue = _read_bids_dataset_description(
        description,
        BidsMetadataReadBudget(),
    )
    description.write_text(
        '{"Name":"Other","BIDSVersion":"1.9.0"}',
        encoding="utf-8",
    )
    changed, changed_issue = _read_bids_dataset_description(
        description,
        BidsMetadataReadBudget(),
    )

    assert first_issue == repeated_issue == changed_issue == ""
    assert first == repeated
    assert changed["Name"] == "Other"
    diagnostics = default_parsed_content_cache().diagnostics()
    assert diagnostics["file_read_count"] == 2
    assert diagnostics["parse_count"] == 2


def test_independent_events_json_readers_reuse_schema_parse(tmp_path: Path) -> None:
    sidecar = tmp_path / "task-mi_events.json"
    sidecar.write_text(
        '{"trial_type":{"Levels":{"left":"Left hand"}}}',
        encoding="utf-8",
    )
    first_reader = BidsEventsJsonReader.from_paths([str(sidecar)])
    second_reader = BidsEventsJsonReader.from_paths([str(sidecar)])

    first = first_reader.read_object(sidecar)
    second = second_reader.read_object(sidecar)

    assert first == second
    assert first is not second
    assert default_parsed_content_cache().diagnostics()["parse_count"] == 1


def test_events_json_reader_returns_fresh_projection_after_caller_mutation(
    tmp_path: Path,
) -> None:
    sidecar = tmp_path / "task-mi_events.json"
    sidecar.write_text(
        '{"trial_type":{"Levels":{"left":"Left hand"}}}',
        encoding="utf-8",
    )
    reader = BidsEventsJsonReader.from_paths([str(sidecar)])

    first = reader.read_object(sidecar)
    first["trial_type"]["Levels"]["left"] = "Caller mutation"
    repeated = reader.read_object(sidecar)

    assert repeated["trial_type"]["Levels"]["left"] == "Left hand"
    assert first is not repeated
    assert default_parsed_content_cache().diagnostics()["parse_count"] == 1


def test_product_parsers_share_backend_owned_cache_source_guard() -> None:
    root = Path(__file__).parents[4] / "XBrainLab" / "backend" / "application"
    migrated = {
        "data_interpretation_label_carriers.py": "parsed_delimited_table(",
        "data_interpretation_metadata.py": "parsed_json_value(",
        "data_interpretation_bids.py": "parsed_delimited_table(",
        "data_interpretation_bids_channels.py": "parsed_delimited_table(",
        "data_interpretation_bids_resources.py": ("json_value_from_verified_bytes("),
        "data_interpretation_resource_reader.py": ("verified_parsed_content_paths("),
    }

    for filename, required_call in migrated.items():
        source = (root / filename).read_text(encoding="utf-8")
        assert "data_interpretation_parsed_cache" in source
        assert required_call in source
        assert "@lru_cache" not in source
        assert "functools.cache" not in source
    cache_owners = [
        path.name
        for path in root.glob("data_interpretation*.py")
        if "ParsedContentCache(" in path.read_text(encoding="utf-8")
    ]
    assert cache_owners == ["data_interpretation_parsed_cache.py"]
    cache_source = (root / "data_interpretation_parsed_cache.py").read_text(
        encoding="utf-8"
    )
    assert "mne" not in cache_source.casefold()
    assert "numpy" not in cache_source.casefold()
    assert "dataset_name" not in cache_source
