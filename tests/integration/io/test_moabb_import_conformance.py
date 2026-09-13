"""Real-command regression coverage for the tracked MOABB import conformance runner."""

from __future__ import annotations

import hashlib
import json
from argparse import Namespace
from pathlib import Path

import numpy as np
import pytest

from scripts.dev.moabb_user_journeys.import_catalog import load_catalog
from scripts.dev.moabb_user_journeys.import_conformance import (
    _waveform_error,
    run_import_case,
)
from scripts.dev.run_moabb_import_conformance import _run_one


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _write_case_fixture(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    data_root = tmp_path / "data"
    root = data_root / "tiny-bids"
    eeg_dir = root / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    (root / "dataset_description.json").write_text(
        json.dumps({"Name": "conformance", "BIDSVersion": "1.10.0"}),
        encoding="utf-8",
    )
    eeg = eeg_dir / "sub-01_task-mi_eeg.vhdr"
    eeg.with_suffix(".eeg").write_bytes(
        np.arange(2_000, dtype="<f4").reshape(1_000, 2).tobytes()
    )
    eeg.write_text(
        "Brain Vision Data Exchange Header File Version 1.0\n"
        "[Common Infos]\nCodepage=UTF-8\n"
        f"DataFile={eeg.with_suffix('.eeg').name}\n"
        f"MarkerFile={eeg.with_suffix('.vmrk').name}\n"
        "DataFormat=BINARY\nDataOrientation=MULTIPLEXED\n"
        "NumberOfChannels=2\nSamplingInterval=10000\n"
        "[Binary Infos]\nBinaryFormat=IEEE_FLOAT_32\n"
        "[Channel Infos]\nCh1=C3,,1,µV\nCh2=C4,,1,µV\n",
        encoding="utf-8",
    )
    eeg.with_suffix(".vmrk").write_text(
        "Brain Vision Data Exchange Marker File, Version 1.0\n"
        "[Common Infos]\nCodepage=UTF-8\n"
        f"DataFile={eeg.with_suffix('.eeg').name}\n[Marker Infos]\n"
        "Mk1=Comment,baseline,1,1,0\nMk2=Comment,reviewed,101,1,0\n",
        encoding="utf-8",
    )
    events = eeg_dir / "sub-01_task-mi_events.tsv"
    events.write_text(
        "onset\tduration\ttrial_type\tvalue\n1.0\t0\tleft\t1\n3.0\t0\tright\t2\n",
        encoding="utf-8",
    )
    events.with_suffix(".json").write_text(
        json.dumps({"trial_type": {"Levels": {"left": "left", "right": "right"}}}),
        encoding="utf-8",
    )
    channels = eeg_dir / "sub-01_task-mi_channels.tsv"
    channels.write_text(
        "name\ttype\tunits\tstatus\nC3\tEEG\tuV\tgood\nC4\tEEG\tuV\tgood\n",
        encoding="utf-8",
    )

    def relative(path: Path) -> str:
        return path.relative_to(data_root).as_posix()

    inputs = [
        root / "dataset_description.json",
        eeg,
        eeg.with_suffix(".eeg"),
        eeg.with_suffix(".vmrk"),
        events,
        events.with_suffix(".json"),
        channels,
    ]
    case: dict[str, object] = {
        "id": "tiny_bids",
        "bids_root": relative(root),
        "selected_recording": relative(eeg),
        "choices": {
            "label_carrier_choices": {
                relative(events): {
                    "label_field": "trial_type",
                    "anchor": "onset",
                    "duration_field": "duration",
                    "time_model": "seconds",
                    "placement_method": "interval",
                    "value_decisions": {
                        "left": {
                            "role": "stimulus",
                            "keep_event": True,
                            "use_as_class": True,
                            "class_name": "left",
                        },
                        "right": {
                            "role": "stimulus",
                            "keep_event": True,
                            "use_as_class": True,
                            "class_name": "right",
                        },
                    },
                }
            }
        },
        "expected": {
            "channel_names": ["C3", "C4"],
            "channel_types": ["eeg", "eeg"],
            "sfreq": 100.0,
            "n_times": 1_000,
            "events": [[100, "left"], [300, "right"]],
        },
        "input_files": [
            {"path": relative(path), "sha256": _sha256(path)} for path in inputs
        ],
    }
    return data_root, case


def test_import_case_replays_real_bids_commands_and_preserves_input(
    tmp_path: Path,
) -> None:
    data_root, case = _write_case_fixture(tmp_path)

    result = run_import_case(case, data_root=data_root, output_root=tmp_path / "out")

    assert result["status"] == "passed", result
    assert result["commands"]["initial"] == ["scan", "preview", "validate", "apply"]
    assert result["commands"]["replay"] == ["reload", "validate", "apply"]
    assert result["observed"]["events"] == [[100, "left"], [300, "right"]]
    assert result["initial"]["waveform_max_abs_error"] == 0.0
    assert result["replay"]["waveform_max_abs_error"] == 0.0
    assert result["input_files_before"] == result["input_files_after"]
    assert Path(result["recipe"]["path"]).is_file()


def test_import_case_preserves_context_without_inventing_classes(
    tmp_path: Path,
) -> None:
    data_root, case = _write_case_fixture(tmp_path)
    case["choices"] = {"skip_labels": True}
    case["expected"]["events"] = []

    result = run_import_case(case, data_root, tmp_path / "out")

    assert result["status"] == "passed", result
    assert result["observed"]["events"] == []
    assert result["reference"]["annotation_count"] == 2
    assert result["initial"]["waveform_max_abs_error"] == 0.0
    assert result["replay"]["waveform_max_abs_error"] == 0.0


@pytest.mark.parametrize("wrong_alias", [False, True])
def test_import_case_verifies_reviewed_internal_aliases_and_retains_context(
    tmp_path: Path, wrong_alias: bool
) -> None:
    data_root, case = _write_case_fixture(tmp_path)
    marker = data_root / "tiny-bids/sub-01/eeg/sub-01_task-mi_eeg.vmrk"
    marker.write_text(
        marker.read_text(encoding="utf-8").replace(
            "Mk2=Comment,reviewed,101,1,0\n",
            "Mk2=Stimulus,S  1,101,1,0\nMk3=Stimulus,S  2,301,1,0\n",
        ),
        encoding="utf-8",
    )
    for item in case["input_files"]:
        if item["path"] == marker.relative_to(data_root).as_posix():
            item["sha256"] = _sha256(marker)
    case["choices"] = {
        "label_carrier": "embedded_events",
        "internal_event_selection": {
            "label_event_codes": ["Stimulus/S  1", "Stimulus/S  2"],
            "not_label_event_codes": ["Comment/baseline"],
            "class_map": {
                "Stimulus/S  1": "wrong" if wrong_alias else "left",
                "Stimulus/S  2": "right",
            },
        },
        "event_roles": {
            "Stimulus/S  1": "class label",
            "Stimulus/S  2": "class label",
            "Comment/baseline": "not a label",
        },
    }

    result = run_import_case(case, data_root, tmp_path / "out")

    if wrong_alias:
        assert result["status"] == "failed", result
        assert "class events differ" in result["failure"]["message"]
    else:
        assert result["status"] == "passed", result
        assert result["observed"]["events"] == [[100, "left"], [300, "right"]]
        assert result["reference"]["annotation_count"] == 3
        assert result["initial"]["waveform_max_abs_error"] == 0.0
        assert result["replay"]["waveform_max_abs_error"] == 0.0


def test_import_case_cannot_hide_applied_classes_with_empty_expectation(
    tmp_path: Path,
) -> None:
    data_root, case = _write_case_fixture(tmp_path)
    case["expected"]["events"] = []

    result = run_import_case(case, data_root, tmp_path / "out")

    assert result["status"] == "failed"
    assert "unexpectedly admits supervised classes" in result["failure"]["message"]


def test_campaign_subprocess_replay_and_tampered_resume_fail_closed(
    tmp_path: Path,
) -> None:
    data_root, case = _write_case_fixture(tmp_path)
    case["id"] = "AlexMI"
    manifest = data_root / "case.json"
    manifest.write_text(json.dumps(case), encoding="utf-8")
    catalog = load_catalog()
    row = catalog["entries"][0]
    assert row["id"] == case["id"]
    row["case_manifest"] = {"path": "case.json", "sha256": _sha256(manifest)}
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    args = Namespace(
        data_root=data_root,
        catalog=catalog_path,
        output=tmp_path / "campaign",
        timeout=60,
    )

    args.timeout = 0.001
    timed_out = _run_one(row, args, None)
    assert timed_out["status"] == "failed", timed_out
    assert timed_out["failure"]["stage"] == "process"
    assert timed_out["attempt"] == 1
    timeout_receipt = Path(timed_out["receipt"]).read_bytes()
    args.timeout = 60
    initial = _run_one(row, args, timed_out)

    assert initial["status"] == "passed", initial
    assert initial["attempt"] == 2
    assert Path(timed_out["receipt"]).read_bytes() == timeout_receipt
    assert _run_one(row, args, initial) == initial

    source = data_root / "tiny-bids/sub-01/eeg/sub-01_task-mi_eeg.eeg"
    original_source = source.read_bytes()
    source.write_bytes(b"changed")
    reused = _run_one(row, args, initial)
    assert reused["status"] == "failed"
    assert "input identity changed" in reused["failure"]["message"]
    fresh = _run_one(row, args, None)
    assert fresh["status"] == "failed"
    source.write_bytes(original_source)

    receipt = Path(initial["receipt"])
    recipe = Path(json.loads(receipt.read_text(encoding="utf-8"))["recipe"]["path"])
    original_recipe = recipe.read_bytes()
    recipe.write_text("{}", encoding="utf-8")
    reused = _run_one(row, args, initial)
    assert reused["status"] == "failed"
    assert "recipe identity changed" in reused["failure"]["message"]
    recipe.write_bytes(original_recipe)
    assert _run_one(row, args, initial) == initial
    Path(initial["receipt"]).write_text("{}", encoding="utf-8")
    reused = _run_one(row, args, initial)
    assert reused["status"] == "failed"
    assert "result identity changed" in reused["failure"]["message"]


def test_import_case_rejects_selected_recording_escape(tmp_path: Path) -> None:
    data_root, case = _write_case_fixture(tmp_path)
    case["selected_recording"] = "../outside.vhdr"

    result = run_import_case(case, data_root=data_root, output_root=tmp_path / "out")

    assert result["status"] == "failed"
    assert result["failure"]["stage"] == "admission"


def test_import_case_binds_explicit_root_channel_metadata(tmp_path: Path) -> None:
    data_root, case = _write_case_fixture(tmp_path)
    old = "tiny-bids/sub-01/eeg/sub-01_task-mi_channels.tsv"
    new = "tiny-bids/channels.tsv"
    (data_root / old).rename(data_root / new)
    case["expected"]["channels_tsv"] = new
    for item in case["input_files"]:
        if item["path"] == old:
            item["path"] = new

    result = run_import_case(case, data_root, tmp_path / "out")

    assert result["status"] == "passed", result


def test_import_case_rejects_unbound_matching_bids_sidecar(tmp_path: Path) -> None:
    data_root, case = _write_case_fixture(tmp_path)
    sidecar = data_root / "tiny-bids" / "sub-01" / "eeg" / "sub-01_task-mi_eeg.json"
    sidecar.write_text(json.dumps({"RecordingType": "continuous"}), encoding="utf-8")

    result = run_import_case(case, data_root=data_root, output_root=tmp_path / "out")

    assert result["status"] == "failed"
    assert result["failure"]["stage"] == "admission"
    assert "unbound selected BIDS dependency" in result["failure"]["message"]


def test_import_case_uses_independent_event_expectation(tmp_path: Path) -> None:
    data_root, case = _write_case_fixture(tmp_path)
    case["expected"] = {**case["expected"], "events": [[99, "left"], [300, "right"]]}

    result = run_import_case(case, data_root=data_root, output_root=tmp_path / "out")

    assert result["status"] == "failed"
    assert result["failure"]["stage"] == "verification"
    assert "class events differ" in result["failure"]["message"]


def test_import_case_rejects_changed_hashed_source(tmp_path: Path) -> None:
    data_root, case = _write_case_fixture(tmp_path)
    source = data_root / "tiny-bids" / "sub-01" / "eeg" / "sub-01_task-mi_eeg.eeg"
    source.write_bytes(b"changed")

    result = run_import_case(case, data_root=data_root, output_root=tmp_path / "out")

    assert result["status"] == "failed"
    assert result["failure"]["stage"] == "admission"
    assert "input hash mismatch" in result["failure"]["message"]


def test_import_case_rejects_choice_for_a_different_recording(tmp_path: Path) -> None:
    data_root, case = _write_case_fixture(tmp_path)
    case["choices"] = {
        **case["choices"],
        "selected_eeg_files": ["tiny-bids/sub-01/eeg/not-the-selected-run.vhdr"],
    }

    result = run_import_case(case, data_root=data_root, output_root=tmp_path / "out")

    assert result["status"] == "failed"
    assert result["failure"]["stage"] == "admission"
    assert "selected_eeg_files" in result["failure"]["message"]


class _Wave:
    def __init__(self, values: np.ndarray) -> None:
        self.ch_names = ["C3"]
        self.n_times = values.shape[1]
        self.values = values

    def get_data(self, *, start: int, stop: int) -> np.ndarray:
        return self.values[:, start:stop]


def test_waveform_guard_rejects_nonfinite_pattern_mismatch() -> None:
    source = _Wave(np.array([[np.nan, 1.0]]))
    changed = _Wave(np.array([[1.0, 1.0]]))

    with pytest.raises(RuntimeError, match="finite-value pattern"):
        _waveform_error(source, changed)
