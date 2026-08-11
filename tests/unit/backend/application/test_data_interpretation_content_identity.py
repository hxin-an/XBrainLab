import hashlib
import threading
from pathlib import Path

import pytest

from tests.unit.backend.path_assertions import (
    assert_filesystem_path_lists_equal,
)
from XBrainLab.backend.application import data_interpretation_content_identity
from XBrainLab.backend.application.data_interpretation_bids_resources import (
    BidsEventsJsonReader,
)
from XBrainLab.backend.application.data_interpretation_content_identity import (
    assert_review_content_unchanged,
    build_review_content_identity,
)
from XBrainLab.backend.application.errors import PreconditionError


def _plan(path: Path, *, label_field: str = "trial_type") -> dict[str, str]:
    return {
        "path": str(path),
        "format": "TSV",
        "selected_label_field": label_field,
        "selected_anchor": "onset",
        "selected_duration_field": "duration",
        "time_model": "seconds",
        "placement_method": "interval",
    }


def test_review_identity_preserves_path_spelling_with_windows_identity_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    labels = tmp_path / "ExternalLabels" / "A01T.mat"
    labels.parent.mkdir()
    labels.write_bytes(b"reviewed labels")
    resolved = str(labels.resolve())
    monkeypatch.setattr(
        data_interpretation_content_identity.os.path,
        "normcase",
        lambda value: str(value).casefold(),
    )

    identity = build_review_content_identity(
        label_carrier_plan=[{"path": resolved, "format": "MAT"}],
    )

    assert identity["bindings"][0]["path"] == resolved
    assert identity["files"][0]["path"] == resolved


def test_identity_paths_normalizes_each_stored_path_a_bounded_number_of_times(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Large admitted scopes must not resolve every prior row again per file."""
    paths = [tmp_path / f"run-{index:03d}.set" for index in range(64)]
    identity = {
        "files": [
            {
                "path": str(path),
                "role": "selected_eeg",
                "file_bytes": index,
                "sha256": f"{index:064x}",
            }
            for index, path in enumerate(paths)
        ]
    }
    original_path_key = data_interpretation_content_identity._path_key
    path_key_calls = 0

    def _counted_path_key(path, *, path_identity_scope=None):
        nonlocal path_key_calls
        path_key_calls += 1
        return original_path_key(
            path,
            path_identity_scope=path_identity_scope,
        )

    monkeypatch.setattr(
        data_interpretation_content_identity,
        "_path_key",
        _counted_path_key,
    )

    observed = data_interpretation_content_identity.identity_paths(identity)

    assert_filesystem_path_lists_equal(observed, paths)
    assert path_key_calls <= len(paths) * 2


def test_freshness_check_reuses_the_reviewed_canonical_path_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_files = [tmp_path / f"run-{index:02d}.set" for index in range(12)]
    for index, path in enumerate(eeg_files):
        path.write_bytes(f"reviewed-eeg-{index}".encode())
    expected = build_review_content_identity(
        label_carrier_plan=[],
        selected_eeg_files=[str(path) for path in eeg_files],
    )
    resolved_calls = 0
    original_value = data_interpretation_content_identity.resolved_path_value
    original_identity = data_interpretation_content_identity.resolved_path_identity

    def _counted_value(path):
        nonlocal resolved_calls
        resolved_calls += 1
        return original_value(path)

    def _counted_identity(path):
        nonlocal resolved_calls
        resolved_calls += 1
        return original_identity(path)

    monkeypatch.setattr(
        data_interpretation_content_identity,
        "resolved_path_value",
        _counted_value,
    )
    monkeypatch.setattr(
        data_interpretation_content_identity,
        "resolved_path_identity",
        _counted_identity,
    )

    observed = assert_review_content_unchanged(
        expected=expected,
        label_carrier_plan=[],
        selected_eeg_files=[str(path) for path in eeg_files],
        candidate_id="candidate-bounded-path-scope",
    )

    assert observed == expected
    assert resolved_calls == 0


def test_review_identity_binds_interpretation_choices_not_only_file_bytes(
    tmp_path: Path,
) -> None:
    events = tmp_path / "events.tsv"
    events.write_text(
        "onset\tduration\ttrial_type\tvalue\n1\t0\tleft\t1\n",
        encoding="utf-8",
    )
    expected = build_review_content_identity(label_carrier_plan=[_plan(events)])

    with pytest.raises(PreconditionError) as raised:
        assert_review_content_unchanged(
            expected=expected,
            label_carrier_plan=[_plan(events, label_field="value")],
        )

    assert raised.value.diagnostics["reason"] == (
        "reviewed_content_or_contract_changed"
    )
    assert raised.value.diagnostics["changed_paths"] == []
    assert (
        raised.value.diagnostics["expected_scope_sha256"]
        != (raised.value.diagnostics["observed_scope_sha256"])
    )


def test_selected_eeg_review_without_content_identity_fails_closed(
    tmp_path: Path,
) -> None:
    eeg = tmp_path / "subject.fif"
    eeg.write_bytes(b"reviewed EEG payload")

    with pytest.raises(PreconditionError) as raised:
        assert_review_content_unchanged(
            expected={},
            label_carrier_plan=[],
            selected_eeg_files=[str(eeg)],
            candidate_id="candidate-legacy",
        )

    assert raised.value.diagnostics["reason"] == ("reviewed_content_identity_missing")
    assert_filesystem_path_lists_equal(
        raised.value.diagnostics["changed_paths"],
        [eeg],
    )
    assert raised.value.diagnostics["next_action"] == "preview_and_review_again"


def test_review_identity_binds_selected_eeg_and_every_parser_dependency(
    tmp_path: Path,
) -> None:
    vhdr_path = tmp_path / "subject.vhdr"
    eeg_path = tmp_path / "subject.eeg"
    vmrk_path = tmp_path / "subject.vmrk"
    vhdr_path.write_bytes(b"reviewed header")
    eeg_path.write_bytes(b"reviewed signal payload")
    vmrk_path.write_bytes(b"reviewed marker payload")

    identity = build_review_content_identity(
        label_carrier_plan=[],
        selected_eeg_files=[str(vhdr_path)],
        eeg_parser_dependencies={
            str(vhdr_path): [str(eeg_path), str(vmrk_path)],
        },
    )

    assert identity["scope"] == (
        "selected_eeg_parser_dependencies_label_carriers_and_local_bids_sidecars"
    )
    assert identity["parser_dependencies"] == [
        {
            "path": str(vhdr_path.resolve()),
            "dependencies": [
                str(eeg_path.resolve()),
                str(vmrk_path.resolve()),
            ],
        }
    ]
    assert {row["path"]: row["role"] for row in identity["files"]} == {
        str(vhdr_path.resolve()): "selected_eeg",
        str(eeg_path.resolve()): "eeg_parser_dependency",
        str(vmrk_path.resolve()): "eeg_parser_dependency",
    }


def test_selected_eeg_identity_streams_content_without_materializing_with_read_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = tmp_path / "large.fif"
    payload = b"x" * (
        data_interpretation_content_identity.CONTENT_HASH_CHUNK_BYTES + 17
    )
    eeg_path.write_bytes(payload)

    def _unexpected_read_bytes(_path: Path) -> bytes:
        raise AssertionError("selected EEG identity must stream instead of read_bytes")

    monkeypatch.setattr(Path, "read_bytes", _unexpected_read_bytes)

    identity = build_review_content_identity(
        label_carrier_plan=[],
        selected_eeg_files=[str(eeg_path)],
    )

    assert identity["files"] == [
        {
            "path": str(eeg_path.resolve()),
            "role": "selected_eeg",
            "file_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    ]


def test_review_identity_hashes_independent_files_concurrently_in_stable_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_paths = [tmp_path / f"run-{index}.set" for index in range(3)]
    for index, path in enumerate(eeg_paths):
        path.write_bytes(f"payload-{index}".encode())

    monkeypatch.setattr(
        data_interpretation_content_identity,
        "CONTENT_IDENTITY_HASH_WORKERS",
        1,
    )
    sequential_identity = build_review_content_identity(
        label_carrier_plan=[],
        selected_eeg_files=[str(path) for path in reversed(eeg_paths)],
    )

    original = data_interpretation_content_identity._stable_stream_sha256
    lock = threading.Lock()
    release = threading.Event()
    active = 0
    overlap_observed = False

    def _observed_stream(path: Path) -> tuple[int, str]:
        nonlocal active, overlap_observed
        with lock:
            active += 1
            if active >= 2:
                overlap_observed = True
                release.set()
        release.wait(timeout=1.0)
        try:
            return original(path)
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(
        data_interpretation_content_identity,
        "_stable_stream_sha256",
        _observed_stream,
    )
    monkeypatch.setattr(
        data_interpretation_content_identity,
        "CONTENT_IDENTITY_HASH_WORKERS",
        4,
    )

    identity = build_review_content_identity(
        label_carrier_plan=[],
        selected_eeg_files=[str(path) for path in reversed(eeg_paths)],
    )

    assert overlap_observed is True
    assert identity == sequential_identity
    assert [row["path"] for row in identity["files"]] == [
        str(path.resolve()) for path in eeg_paths
    ]


def test_review_identity_detects_same_size_selected_eeg_rewrite(
    tmp_path: Path,
) -> None:
    eeg_path = tmp_path / "subject.fif"
    eeg_path.write_bytes(b"reviewed-eeg-a")
    expected = build_review_content_identity(
        label_carrier_plan=[],
        selected_eeg_files=[str(eeg_path)],
    )

    eeg_path.write_bytes(b"reviewed-eeg-b")

    with pytest.raises(PreconditionError) as raised:
        assert_review_content_unchanged(
            expected=expected,
            label_carrier_plan=[],
            selected_eeg_files=[str(eeg_path)],
        )

    assert raised.value.diagnostics["reason"] == (
        "reviewed_content_or_contract_changed"
    )
    assert_filesystem_path_lists_equal(
        raised.value.diagnostics["changed_paths"],
        [eeg_path],
    )


def test_review_identity_detects_same_size_bids_event_sidecar_rewrite(
    tmp_path: Path,
) -> None:
    events = tmp_path / "sub-01_task-mi_events.tsv"
    sidecar = tmp_path / "task-mi_events.json"
    events.write_text(
        "onset\tduration\ttrial_type\n1\t0\tleft\n",
        encoding="utf-8",
    )
    sidecar.write_text('{"trial_type":"left"}\n', encoding="utf-8")
    expected = build_review_content_identity(
        label_carrier_plan=[_plan(events)],
        bids_events_json_files=[str(sidecar)],
    )
    reviewed_size = sidecar.stat().st_size
    sidecar.write_text('{"trial_type":"foot"}\n', encoding="utf-8")
    assert sidecar.stat().st_size == reviewed_size

    with pytest.raises(PreconditionError) as raised:
        assert_review_content_unchanged(
            expected=expected,
            label_carrier_plan=[_plan(events)],
        )

    assert_filesystem_path_lists_equal(
        raised.value.diagnostics["changed_paths"],
        [sidecar],
    )
    assert raised.value.diagnostics["next_action"] == "preview_and_review_again"


def test_review_identity_reuses_parser_admitted_bids_sidecar_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sidecar = tmp_path / "task-mi_events.json"
    payload = b'{"trial_type":{"Levels":{"left":"Left hand"}}}'
    sidecar.write_bytes(payload)
    reader = BidsEventsJsonReader.from_paths([str(sidecar)])
    reader.read_object(sidecar)

    def _unexpected_stream_read(_path: Path) -> tuple[int, str]:
        raise AssertionError("admitted BIDS sidecar must not be fingerprinted twice")

    monkeypatch.setattr(
        data_interpretation_content_identity,
        "_stable_stream_sha256",
        _unexpected_stream_read,
    )

    identity = build_review_content_identity(
        label_carrier_plan=[],
        bids_events_json_files=[str(sidecar)],
        admitted_file_identities=reader.content_identities([str(sidecar)]),
    )

    assert identity["files"] == [
        {
            "path": str(sidecar.resolve()),
            "role": "bids_events_json",
            "file_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    ]


def test_review_identity_rejects_size_change_before_hashing_expanded_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = tmp_path / "events.tsv"
    events.write_text("label\nleft\n", encoding="utf-8")
    expected = build_review_content_identity(label_carrier_plan=[_plan(events)])
    events.write_bytes(b"x" * 1_000_000)

    def _unexpected_stream_read(_path: Path) -> tuple[int, str]:
        raise AssertionError("size mismatch must fail before hashing the new payload")

    monkeypatch.setattr(
        data_interpretation_content_identity,
        "_stable_stream_sha256",
        _unexpected_stream_read,
    )

    with pytest.raises(PreconditionError) as raised:
        assert_review_content_unchanged(
            expected=expected,
            label_carrier_plan=[_plan(events)],
        )

    assert_filesystem_path_lists_equal(
        raised.value.diagnostics["changed_paths"],
        [events],
    )
    assert raised.value.diagnostics["reason"] == "reviewed_content_size_changed"
