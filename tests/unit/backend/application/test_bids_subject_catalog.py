from pathlib import Path
from threading import Event, Thread

import pytest

from XBrainLab.backend.application import (
    ApplicationService,
    ErrorType,
)
from XBrainLab.backend.application.bids_subject_catalog import (
    inspect_bids_subject_catalog,
)
from XBrainLab.backend.application.commands import (
    ReviewInterpretationCommand,
    ScanSourceCommand,
)
from XBrainLab.backend.application.data_interpretation_scan import (
    discover_source_preflight_scope,
)
from XBrainLab.backend.application.data_interpretation_service import (
    DataInterpretationCommandService,
)
from XBrainLab.backend.application.owned_work import OwnedWorkPhase
from XBrainLab.backend.study import Study

_THREAD_WATCHDOG_SECONDS = 5.0


def _write_bids_dataset(root: Path) -> None:
    (root / "dataset_description.json").write_text(
        '{"Name": "subject-selection", "BIDSVersion": "1.9.0"}',
        encoding="utf-8",
    )
    (root / "participants.tsv").write_text(
        "participant_id\nsub-01\nsub-02\nsub-03\n",
        encoding="utf-8",
    )
    for subject, session, task, runs in (
        ("01", "01", "p300", ("1", "2")),
        ("02", "02", "mi", ("1",)),
        ("03", "01", "rest", ("1",)),
    ):
        eeg_dir = root / f"sub-{subject}" / f"ses-{session}" / "eeg"
        eeg_dir.mkdir(parents=True)
        for run in runs:
            stem = f"sub-{subject}_ses-{session}_task-{task}_run-{run}"
            (eeg_dir / f"{stem}_eeg.fif").write_bytes(b"header only")
            (eeg_dir / f"{stem}_events.tsv").write_text(
                "onset\tduration\ttrial_type\n0\t1\ttarget\n",
                encoding="utf-8",
            )


def test_catalog_lists_subject_scope_without_materializing_tsv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_bids_dataset(tmp_path)
    original_read_text = Path.read_text

    def _guarded_read_text(path: Path, *args, **kwargs):
        if path.suffix.casefold() == ".tsv":
            pytest.fail(f"catalog materialized BIDS table: {path}")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _guarded_read_text)

    catalog = inspect_bids_subject_catalog(tmp_path)

    assert catalog["subject_count"] == 3
    assert catalog["eeg_file_count"] == 4
    assert [item["subject"] for item in catalog["subjects"]] == ["01", "02", "03"]
    assert catalog["subjects"][0] == {
        "subject": "01",
        "label": "sub-01",
        "eeg_file_count": 2,
        "sessions": ["01"],
        "tasks": ["p300"],
        "runs": ["1", "2"],
    }


def test_selected_subject_scope_excludes_unselected_subject_payloads(
    tmp_path: Path,
) -> None:
    _write_bids_dataset(tmp_path)

    scope = discover_source_preflight_scope(
        source_path=str(tmp_path),
        source_hint="bids",
        selected_bids_subjects=["02"],
    )

    assert len(scope.eeg_files) == 1
    assert all("sub-02" in path for path in scope.eeg_files)
    assert all("sub-02" in path for path in scope.label_carriers)
    assert not any("sub-01" in path or "sub-03" in path for path in scope.paths)
    assert (
        str((tmp_path / "dataset_description.json").resolve()) in scope.metadata_files
    )
    assert str((tmp_path / "participants.tsv").resolve()) in scope.metadata_files


def test_selected_subject_scope_rejects_unknown_subject(tmp_path: Path) -> None:
    _write_bids_dataset(tmp_path)

    with pytest.raises(ValueError, match="sub-99"):
        discover_source_preflight_scope(
            source_path=str(tmp_path),
            source_hint="bids",
            selected_bids_subjects=["99"],
        )


def test_scan_command_can_publish_lightweight_bids_catalog(tmp_path: Path) -> None:
    _write_bids_dataset(tmp_path)
    service = DataInterpretationCommandService(
        object(),
        data_filename=lambda data: str(data),
        data_filepath=lambda data: str(data),
    )

    result = service.handle_scan_source(
        ScanSourceCommand(
            source_path=str(tmp_path),
            source_hint="bids",
            catalog_only=True,
        )
    )

    assert isinstance(result, tuple)
    message, diagnostics = result
    assert message == "Found 3 BIDS subject(s)."
    assert diagnostics["payload_type"] == "bids_subject_catalog"
    assert diagnostics["bids_subject_catalog"]["eeg_file_count"] == 4


def test_review_command_materializes_only_selected_bids_subject(tmp_path: Path) -> None:
    _write_bids_dataset(tmp_path)
    service = DataInterpretationCommandService(
        object(),
        data_filename=lambda data: str(data),
        data_filepath=lambda data: str(data),
    )

    result = service.handle_review_interpretation(
        ReviewInterpretationCommand(
            source_path=str(tmp_path),
            source_hint="bids",
            choices={"selected_bids_subjects": ["02"]},
        )
    )

    assert isinstance(result, tuple)
    scan = result[1]["scan_result"]
    assert len(scan["eeg_files"]) == 1
    assert all("sub-02" in path for path in scan["eeg_files"])
    assert all("sub-02" in path for path in scan["label_carriers"])


def test_cached_bids_review_publishes_cancellable_metadata_materialization_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_bids_dataset(tmp_path)
    service = ApplicationService(Study())
    catalog = service.execute(
        ScanSourceCommand(
            source_path=str(tmp_path),
            source_hint="bids",
            catalog_only=True,
        )
    )
    assert catalog.ok
    before = service.get_view_publication()

    from XBrainLab.backend.application import data_interpretation_scan

    original_bids_summary = data_interpretation_scan._bids_summary
    materialization_started = Event()
    release_materialization = Event()

    def _blocking_bids_summary(*args, **kwargs):
        if kwargs.get("materialize") is not True:
            return original_bids_summary(*args, **kwargs)
        materialization_started.set()
        assert release_materialization.wait(timeout=_THREAD_WATCHDOG_SECONDS)
        return original_bids_summary(*args, **kwargs)

    monkeypatch.setattr(
        data_interpretation_scan,
        "_bids_summary",
        _blocking_bids_summary,
    )
    command = ReviewInterpretationCommand(
        source_path=str(tmp_path),
        source_hint="bids",
        choices={"selected_bids_subjects": ["02"]},
    )
    operation = service.begin_owned_operation(command)
    results = []
    worker = Thread(
        target=lambda: results.append(
            service.execute(command, operation_id=operation.operation_id)
        ),
        name="cached-bids-review-cancel",
    )

    worker.start()
    assert materialization_started.wait(timeout=_THREAD_WATCHDOG_SECONDS)
    snapshot = service.get_owned_operation(operation.operation_id)
    assert service.cancel_owned_operation(operation.operation_id) is True
    release_materialization.set()
    worker.join(timeout=_THREAD_WATCHDOG_SECONDS)

    assert not worker.is_alive()
    assert snapshot.phase is OwnedWorkPhase.RUNNING
    assert snapshot.stage == "Materializing BIDS review metadata"
    assert snapshot.completed == 0
    assert snapshot.total == 2
    assert len(results) == 1
    cancelled = results[0]
    assert cancelled.failed
    assert cancelled.error_type is ErrorType.CANCELLED
    assert cancelled.diagnostics["state_preserved"] is True
    assert cancelled.changed_state.interpretation_changed is False
    assert service.get_view_publication() == before
    assert service.get_owned_operation(operation.operation_id).phase is (
        OwnedWorkPhase.CANCELLED
    )
