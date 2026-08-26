from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.dev import report_teacher_dataset_preflight as preflight


def test_openneuro_choices_preserve_three_run_pairing_and_reviewed_classes(
    tmp_path: Path,
) -> None:
    eeg_dir = tmp_path / "sub-001" / "eeg"
    eeg_dir.mkdir(parents=True)
    eeg_files = []
    events_files = []
    for run in (1, 2, 3):
        stem = f"sub-001_task-P300_run-{run}"
        eeg_path = eeg_dir / f"{stem}_eeg.set"
        events_path = eeg_dir / f"{stem}_events.tsv"
        eeg_path.touch()
        events_path.touch()
        eeg_files.append(eeg_path.resolve())
        events_files.append(events_path.resolve())

    choices = preflight.build_openneuro_p300_choices(tmp_path)

    assert choices["selected_bids_subjects"] == ["001"]
    assert choices["selected_eeg_files"] == [str(path) for path in eeg_files]
    assert set(choices["label_carrier_choices"]) == {str(path) for path in events_files}
    for choice in choices["label_carrier_choices"].values():
        assert choice["label_field"] == "value"
        assert choice["anchor"] == "onset"
        assert choice["placement_method"] == "time_field"
        assert choice["time_model"] == "seconds"
        assert (
            choice["value_decisions"]["oddball_with_reponse"]["class_name"] == "oddball"
        )
        assert choice["value_decisions"]["response"]["keep_event"] is False
        assert choice["value_decisions"]["ignore"]["role"] == "system"


def test_summary_requires_all_three_independent_dataset_cases() -> None:
    results = [
        {"case_id": "openneuro_p300_bids", "status": "passed"},
        {"case_id": "chbmit_raw_edf", "status": "passed"},
        {"case_id": "sleep_edfx_psg", "status": "failed"},
    ]

    summary = preflight.summarize_results(results)

    assert summary["required_case_count"] == 3
    assert summary["passed_required_case_count"] == 2
    assert summary["failed_case_ids"] == ["sleep_edfx_psg"]
    assert summary["all_required_passed"] is False


def test_markdown_states_supervised_and_annotation_boundaries() -> None:
    snapshot = {
        "summary": {
            "required_case_count": 3,
            "passed_required_case_count": 3,
            "all_required_passed": True,
            "strict_ok": True,
        },
        "results": [
            {
                "case_id": "openneuro_p300_bids",
                "dataset": "OpenNeuro ds003061",
                "format": "BIDS EEG / EEGLAB SET + events.tsv",
                "status": "passed",
                "evidence_tier": "supervised_import",
                "message": "Three runs imported.",
            },
            {
                "case_id": "chbmit_raw_edf",
                "dataset": "CHB-MIT chb01",
                "format": "EDF",
                "status": "passed",
                "evidence_tier": "raw_import_only",
                "message": "Raw recording imported.",
            },
        ],
        "claim_boundary": {
            "supports": "Representative teacher preflight.",
            "does_not_support": (
                "CHB-MIT seizure sidecars and Sleep-EDF hypnograms are not "
                "automatically applied as supervised labels."
            ),
        },
    }

    rendered = preflight.render_markdown(snapshot)

    assert "# Teacher Dataset Preflight" in rendered
    assert "OpenNeuro ds003061" in rendered
    assert "supervised_import" in rendered
    assert "raw_import_only" in rendered
    assert "not automatically applied as supervised labels" in rendered


@pytest.mark.parametrize(("strict_ok", "expected_exit"), [(True, 0), (False, 1)])
def test_cli_strict_exit_tracks_all_required_cases(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    strict_ok: bool,
    expected_exit: int,
) -> None:
    snapshot = {
        "summary": {
            "all_required_passed": strict_ok,
            "strict_ok": strict_ok,
        },
        "results": [],
        "claim_boundary": {"supports": "", "does_not_support": ""},
    }
    monkeypatch.setattr(
        preflight,
        "build_teacher_preflight_snapshot",
        lambda: snapshot,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "report_teacher_dataset_preflight.py",
            "--format",
            "json",
            "--strict",
        ],
    )

    assert preflight.main() == expected_exit
    assert json.loads(capsys.readouterr().out) == snapshot


def test_cli_strict_fails_closed_when_strict_result_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    snapshot = {
        "summary": {"all_required_passed": True},
        "results": [],
        "claim_boundary": {"supports": "", "does_not_support": ""},
    }
    monkeypatch.setattr(
        preflight,
        "build_teacher_preflight_snapshot",
        lambda: snapshot,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "report_teacher_dataset_preflight.py",
            "--format",
            "json",
            "--strict",
        ],
    )

    assert preflight.main() == 1
    assert json.loads(capsys.readouterr().out) == snapshot


def test_snapshot_does_not_execute_dataset_cases_when_manifest_is_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        preflight,
        "_manifest_evidence",
        lambda _root: {
            "all_files_verified": False,
            "invalid_files": ["broken.edf"],
            "missing_required_groups": [],
        },
    )

    def _must_not_run(_root: Path) -> dict[str, object]:
        raise AssertionError("dataset case ran against an invalid manifest")

    monkeypatch.setattr(preflight, "run_openneuro_p300_case", _must_not_run)
    monkeypatch.setattr(preflight, "run_chbmit_case", _must_not_run)
    monkeypatch.setattr(preflight, "run_sleep_edfx_case", _must_not_run)

    snapshot = preflight.build_teacher_preflight_snapshot(tmp_path)

    assert snapshot["summary"]["strict_ok"] is False
    assert snapshot["summary"]["passed_required_case_count"] == 0
    assert all(result["failed_stage"] == "manifest" for result in snapshot["results"])


def test_manifest_requires_every_teacher_dataset_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(preflight, "fixture_groups_for_profile", lambda _profile: [])

    evidence = preflight._manifest_evidence(tmp_path)

    assert evidence["all_files_verified"] is False
    assert set(evidence["missing_required_groups"]) == set(
        preflight.TEACHER_FIXTURE_GROUP_NAMES
    )


def test_release_service_closes_every_raw_and_application_lifecycle() -> None:
    close_calls: list[str] = []

    class _Raw:
        def __init__(self, name: str, *, raises: bool = False) -> None:
            self.name = name
            self.raises = raises

        def close(self) -> None:
            close_calls.append(self.name)
            if self.raises:
                raise RuntimeError("close failed")

    class _Loaded:
        def __init__(self, raw: _Raw) -> None:
            self.raw = raw

        def get_mne(self) -> _Raw:
            return self.raw

    service = SimpleNamespace(
        study=SimpleNamespace(
            loaded_data_list=[
                _Loaded(_Raw("first", raises=True)),
                _Loaded(_Raw("second")),
            ]
        ),
        close=lambda: close_calls.append("service"),
    )

    preflight._release_service(service)

    assert close_calls == ["first", "second", "service"]


def test_public_fixture_dir_uses_canonical_data_root_when_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XBRAINLAB_DATA_DIR", str(tmp_path))

    assert preflight._public_fixture_dir(preflight.ROOT) == (
        tmp_path / "datasets" / "public-fixtures"
    )


def test_import_performance_snapshot_runs_one_warmup_and_three_fresh_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset_root = tmp_path / "openneuro-ds003061-p300"
    dataset_root.mkdir()
    calls: list[Path] = []

    def _passing_run(path: Path, **_kwargs: object) -> dict[str, object]:
        calls.append(path)
        return {
            "status": "passed",
            "blocking_wait_seconds": float(len(calls)),
            "background_idle_seconds": 0.25,
            "stable_idle_seconds": float(len(calls)) + 0.25,
            "phases": {
                stage: {"wall_seconds": 0.25}
                for stage in ("catalog", "review", "apply", "background_idle")
            },
            "correctness": {"raw_file_count": 3},
        }

    monkeypatch.setattr(preflight, "_public_fixture_dir", lambda _root: tmp_path)
    monkeypatch.setattr(
        preflight,
        "_run_openneuro_import_performance_pass",
        _passing_run,
    )

    snapshot = preflight.build_openneuro_import_performance_snapshot(
        tmp_path,
        max_blocking_median_seconds=3.0,
    )

    assert len(calls) == 4
    assert snapshot["warmup"]["status"] == "passed"
    assert snapshot["summary"] == {
        "ok": True,
        "passed_pass_count": 3,
        "required_pass_count": 3,
        "median_blocking_wait_seconds": 3.0,
        "median_background_idle_seconds": 0.25,
        "median_stable_idle_seconds": 3.25,
        "max_blocking_median_seconds": 3.0,
        "budget_ok": True,
    }


def test_import_performance_snapshot_fails_closed_for_missed_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset_root = tmp_path / "openneuro-ds003061-p300"
    dataset_root.mkdir()
    monkeypatch.setattr(preflight, "_public_fixture_dir", lambda _root: tmp_path)
    monkeypatch.setattr(
        preflight,
        "_run_openneuro_import_performance_pass",
        lambda _path, **_kwargs: {
            "status": "passed",
            "blocking_wait_seconds": 10.1,
            "background_idle_seconds": 1.0,
            "stable_idle_seconds": 11.1,
            "phases": {},
            "correctness": {},
        },
    )

    snapshot = preflight.build_openneuro_import_performance_snapshot(
        tmp_path,
        max_blocking_median_seconds=10.0,
    )

    assert snapshot["summary"]["ok"] is False
    assert snapshot["summary"]["budget_ok"] is False


def test_cli_import_performance_uses_profile_result_for_exit(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    snapshot = {
        "summary": {"ok": False},
        "workload": {"dataset": "OpenNeuro ds003061 P300"},
        "warmup": {"status": "passed"},
        "measured_passes": [],
    }
    monkeypatch.setattr(
        preflight,
        "build_openneuro_import_performance_snapshot",
        lambda **_kwargs: snapshot,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "report_teacher_dataset_preflight.py",
            "--import-performance",
            "--max-blocking-median-seconds",
            "10",
            "--format",
            "json",
        ],
    )

    assert preflight.main() == 1
    assert json.loads(capsys.readouterr().out) == snapshot


def test_import_performance_reads_recipe_trace_from_apply_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Service:
        def __init__(self) -> None:
            self.study = SimpleNamespace(
                loaded_data_list=[object(), object(), object()]
            )

        def execute(self, command: object) -> SimpleNamespace:
            if isinstance(command, preflight.ScanSourceCommand):
                return SimpleNamespace(
                    ok=True,
                    message="cataloged",
                    diagnostics={
                        "bids_subject_catalog": {"subjects": [{"subject": "001"}]}
                    },
                )
            if isinstance(command, preflight.ReviewInterpretationCommand):
                return SimpleNamespace(
                    ok=True,
                    message="reviewed",
                    diagnostics={"validation_decision": {"decision": "safe"}},
                )
            return SimpleNamespace(
                ok=True,
                message="applied",
                diagnostics={
                    "label_apply": {"status": "applied"},
                    "applied_interpretation": {"recipe_trace": ["label_import:bids:3"]},
                },
                state=SimpleNamespace(
                    raw=SimpleNamespace(count=3),
                    interpretation=SimpleNamespace(),
                ),
            )

        def wait_for_background_tasks(self, timeout: float) -> bool:
            assert timeout == 30.0
            return True

        def close(self) -> None:
            pass

    service = _Service()
    monkeypatch.setattr(preflight, "ApplicationService", lambda _study: service)
    monkeypatch.setattr(preflight, "build_openneuro_p300_choices", lambda _root: {})
    monkeypatch.setattr(
        preflight,
        "_review_openneuro_event_timing",
        lambda _data, **_kwargs: {
            "sample_label_rows_match": True,
            "source_sample_label_digest": "source",
            "stored_sample_label_digest": "stored",
        },
    )

    result = preflight._run_openneuro_import_performance_pass(
        tmp_path,
        background_timeout_seconds=30.0,
    )

    assert result["status"] == "passed"
    assert result["correctness"]["recipe_trace_has_label_import"] is True
