import hashlib
from pathlib import Path

import pytest

from tests.unit.backend.path_assertions import (
    assert_filesystem_path_lists_equal,
    filesystem_path_key,
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
            "path": filesystem_path_key(vhdr_path),
            "dependencies": [
                filesystem_path_key(eeg_path),
                filesystem_path_key(vmrk_path),
            ],
        }
    ]
    assert {row["path"]: row["role"] for row in identity["files"]} == {
        filesystem_path_key(vhdr_path): "selected_eeg",
        filesystem_path_key(eeg_path): "eeg_parser_dependency",
        filesystem_path_key(vmrk_path): "eeg_parser_dependency",
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
            "path": filesystem_path_key(eeg_path),
            "role": "selected_eeg",
            "file_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
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
            "path": filesystem_path_key(sidecar),
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
