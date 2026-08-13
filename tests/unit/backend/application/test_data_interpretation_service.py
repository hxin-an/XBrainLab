"""Focused tests for the Data Interpretation command coordinator."""

from __future__ import annotations

import inspect
import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from tests.unit.backend.path_assertions import (
    assert_filesystem_path_lists_equal,
    assert_filesystem_paths_equal,
)
from XBrainLab.backend.application import (
    data_interpretation_internal_events,
    resource_guard,
)
from XBrainLab.backend.application import (
    data_interpretation_service as service_module,
)
from XBrainLab.backend.application.commands import (
    ApplyInterpretationCommand,
    LabelImportPlan,
    PreviewInterpretationCommand,
    ReloadInterpretationRecipeCommand,
    ReviewInterpretationCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.backend.application.data_interpretation_candidate import (
    build_interpretation_candidate,
)
from XBrainLab.backend.application.data_interpretation_discovery_preparation import (
    ApplicationDiscoveryBoundary,
)
from XBrainLab.backend.application.data_interpretation_resource_receipt import (
    INTERPRETATION_PREFLIGHT_RECEIPT_LIMIT,
    INTERPRETATION_PREFLIGHT_RECEIPT_TTL_SECONDS,
)
from XBrainLab.backend.application.data_interpretation_service import (
    DataInterpretationCommandService,
    HandlerResult,
)
from XBrainLab.backend.application.errors import (
    ApplicationError,
    ConfirmationRequiredError,
    PreconditionError,
)
from XBrainLab.backend.application.resource_guard import ResourcePreflightResult
from XBrainLab.backend.application.state import ApplicationStateSnapshot


def test_discovery_prepare_paths_cannot_publish_session_state() -> None:
    prepare_names = (
        "_prepare_scan_source",
        "_prepare_review_interpretation",
        "_prepare_preview_interpretation",
        "_prepare_validate_interpretation",
    )

    for name in prepare_names:
        source = inspect.getsource(getattr(DataInterpretationCommandService, name))
        assert "owned_work_commit_boundary" not in source
        assert ".record_scan(" not in source
        assert ".record_preview(" not in source
        assert ".record_validation(" not in source

    commit_source = inspect.getsource(
        DataInterpretationCommandService.commit_prepared_interpretation_discovery
    )
    assert "owned_work_commit_boundary" in commit_source
    assert "publish_staged_session_state" in commit_source


def test_apply_begin_only_captures_short_state_and_prepare_owns_resources() -> None:
    begin_source = inspect.getsource(
        DataInterpretationCommandService.begin_apply_interpretation
    )
    prepare_source = inspect.getsource(
        DataInterpretationCommandService.prepare_apply_interpretation
    )
    guard_source = inspect.getsource(
        DataInterpretationCommandService._ensure_apply_session_is_current
    )

    assert "_resolve_apply_resource_preflight" not in begin_source
    assert "_admitted_reviewed_label_resources" not in begin_source
    assert "checkpoint_apply_state" not in begin_source
    assert "deepcopy(self.state)" not in begin_source
    assert "session_identity" in begin_source
    assert "_resolve_apply_resource_preflight" in prepare_source
    assert "_admitted_reviewed_label_resources" in prepare_source
    assert "_ensure_apply_session_is_current" in prepare_source
    assert "session_identity_is_current" in guard_source


def test_discovery_commit_publishes_prepared_state_without_commit_time_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = tmp_path / "sub-01_task-mi_raw.fif"
    eeg_path.write_bytes(b"stable EEG header")
    service, _dataset = _service()
    plan = service.begin_interpretation_discovery(
        ScanSourceCommand(source_path=str(eeg_path)),
        application_boundary=ApplicationDiscoveryBoundary(
            publication_generation=0,
            publication_revision=0,
            state=ApplicationStateSnapshot.empty(),
        ),
    )
    prepared = service.prepare_interpretation_discovery(plan)

    monkeypatch.setattr(
        service.state,
        "checkpoint_session_state",
        lambda: pytest.fail("commit copied the live session checkpoint"),
    )
    monkeypatch.setattr(
        service.state,
        "restore_session_state",
        lambda _checkpoint: pytest.fail("commit recopied prepared session state"),
    )

    _message, payload = _expect_payload(
        service.commit_prepared_interpretation_discovery(prepared)
    )

    assert payload["payload_type"] == "scan_result"
    assert service.state.snapshot().has_scan_result is True


def test_discovery_commit_isolates_live_nested_state_from_prepared_receipt(
    tmp_path: Path,
) -> None:
    eeg_path = tmp_path / "sub-01_task-mi_raw.fif"
    eeg_path.write_bytes(b"stable EEG header")
    service, _dataset = _service()
    plan = service.begin_interpretation_discovery(
        ScanSourceCommand(source_path=str(eeg_path)),
        application_boundary=ApplicationDiscoveryBoundary(
            publication_generation=0,
            publication_revision=0,
            state=ApplicationStateSnapshot.empty(),
        ),
    )
    prepared = service.prepare_interpretation_discovery(plan)

    service.commit_prepared_interpretation_discovery(prepared)
    [prepared_scan] = prepared.state_after.scans.values()
    prepared_scan.eeg_files.append(str(tmp_path / "mutated-after-commit.fif"))

    live_scan = service.state.resolve_scan(None)
    assert live_scan.eeg_files == [str(eeg_path.resolve())]


def test_discovery_prepared_state_is_one_shot_without_second_live_mutation(
    tmp_path: Path,
) -> None:
    eeg_path = tmp_path / "sub-01_task-mi_raw.fif"
    eeg_path.write_bytes(b"stable EEG header")
    service, _dataset = _service()
    plan = service.begin_interpretation_discovery(
        ScanSourceCommand(source_path=str(eeg_path)),
        application_boundary=ApplicationDiscoveryBoundary(
            publication_generation=0,
            publication_revision=0,
            state=ApplicationStateSnapshot.empty(),
        ),
    )
    prepared = service.prepare_interpretation_discovery(plan)
    service.commit_prepared_interpretation_discovery(prepared)
    committed = service.state.checkpoint_session_state()

    with pytest.raises(PreconditionError, match="state changed"):
        service.commit_prepared_interpretation_discovery(prepared)

    assert service.state.checkpoint_session_state() == committed


def test_discovery_commit_validates_cache_payload_before_live_publication(
    tmp_path: Path,
) -> None:
    eeg_path = tmp_path / "sub-01_task-mi_raw.fif"
    eeg_path.write_bytes(b"stable EEG header")
    service, _dataset = _service()
    plan = service.begin_interpretation_discovery(
        ScanSourceCommand(source_path=str(eeg_path)),
        application_boundary=ApplicationDiscoveryBoundary(
            publication_generation=0,
            publication_revision=0,
            state=ApplicationStateSnapshot.empty(),
        ),
    )
    prepared = service.prepare_interpretation_discovery(plan)
    malformed = replace(
        prepared,
        safe_preview_admissions=(([], object()),),
    )
    before = service.state.checkpoint_session_state()

    with pytest.raises(TypeError, match="unhashable"):
        service.commit_prepared_interpretation_discovery(malformed)

    assert service.state.checkpoint_session_state() == before


class _LoadedData:
    def __init__(self, filepath: str) -> None:
        self.filepath = filepath
        self.subject = ""
        self.session = ""
        self.runtime_details: dict[str, dict[str, Any]] = {}

    def get_filepath(self) -> str:
        return self.filepath

    def get_filename(self) -> str:
        return Path(self.filepath).name

    def set_subject_name(self, subject: str) -> None:
        self.subject = subject

    def set_session_name(self, session: str) -> None:
        self.session = session

    def set_runtime_detail(self, name: str, detail: dict[str, Any]) -> None:
        self.runtime_details[name] = detail


class _DatasetController:
    def __init__(self) -> None:
        self.loaded: list[_LoadedData] = []
        self.imported_paths: list[str] = []
        self.notifications: list[str] = []
        self.clean_count = 0

    def import_files(self, filepaths: Sequence[str]) -> tuple[int, list[str]]:
        self.imported_paths = list(filepaths)
        self.loaded = [_LoadedData(path) for path in filepaths]
        return len(filepaths), []

    def get_loaded_data_list(self) -> list[_LoadedData]:
        return list(self.loaded)

    def clean_dataset(self) -> None:
        self.clean_count += 1
        self.loaded = []
        self.imported_paths = []

    def notify(self, event_name: str) -> None:
        self.notifications.append(event_name)

    def apply_labels_batch(
        self,
        target_files: Sequence[Any],
        label_map: Mapping[str, Any],
        file_mapping: Mapping[str, str],
        mapping: Mapping[Any, str],
        selected_event_names: Sequence[str] | set[str] | None,
    ) -> int:
        del target_files, label_map, file_mapping, mapping, selected_event_names
        return 1

    def apply_labels_sequence(
        self,
        _target_files: list[Any],
        _labels: Any,
        _mapping: Any,
        _selected_event_names: set[str] | None,
        *,
        force_import: bool = False,
    ) -> int:
        return 1


def _data_filename(data: Any) -> str:
    get_filename = getattr(data, "get_filename", None)
    if callable(get_filename):
        return str(get_filename())
    return Path(_data_filepath(data)).name


def _data_filepath(data: Any) -> str:
    get_filepath = getattr(data, "get_filepath", None)
    if callable(get_filepath):
        return str(get_filepath())
    return str(getattr(data, "filepath", ""))


def _service() -> tuple[DataInterpretationCommandService, _DatasetController]:
    dataset = _DatasetController()
    return (
        DataInterpretationCommandService(
            dataset,
            data_filename=_data_filename,
            data_filepath=_data_filepath,
        ),
        dataset,
    )


def _expect_payload(result: HandlerResult) -> tuple[str, dict[str, Any]]:
    assert isinstance(result, tuple)
    return cast(tuple[str, dict[str, Any]], result)


def _class_value_decisions(
    class_names: dict[str, str],
) -> dict[str, dict[str, object]]:
    return {
        raw_value: {
            "role": "stimulus",
            "keep_event": True,
            "use_as_class": True,
            "class_name": class_name,
        }
        for raw_value, class_name in class_names.items()
    }


def _resource_preflight(
    risk_level: str,
    paths: list[str] | None = None,
) -> ResourcePreflightResult:
    message = f"resource risk: {risk_level}"
    diagnostics: dict[str, Any] = {"risk_level": risk_level, "message": message}
    if paths is not None:
        diagnostics["files"] = [
            {
                "path": str(Path(path).resolve()),
                "file_bytes": Path(path).stat().st_size,
            }
            for path in paths
        ]
    return ResourcePreflightResult(
        issues=(message,) if risk_level == "blocking" else (),
        diagnostics=diagnostics,
        warnings=(message,) if risk_level == "warning" else (),
        unknowns=(message,) if risk_level == "unknown" else (),
    )


def _resource_challenge(exc: resource_guard.ResourceConfirmationRequiredError) -> dict:
    diagnostics = exc.diagnostics["resource_preflight"]
    challenge = diagnostics.get("confirmation_challenge")
    assert isinstance(challenge, dict)
    assert challenge["challenge_id"]
    return challenge


def test_apply_resource_preflight_publishes_scope_estimate_and_finalize_stages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = tmp_path / "subject.bdf"
    eeg_path.write_bytes(b"header")
    service, _dataset = _service()
    candidate = SimpleNamespace(
        candidate_id="candidate-1",
        selected_eeg_files=[str(eeg_path)],
        label_carriers=[],
        content_identity={},
    )
    stages: list[str] = []
    monkeypatch.setattr(
        service_module,
        "owned_work_checkpoint",
        lambda stage, **_kwargs: stages.append(stage),
    )
    monkeypatch.setattr(
        service_module,
        "check_import_resource_preflight",
        lambda paths: _resource_preflight("safe", paths),
    )

    preflight, receipt, reused = service._resolve_apply_resource_preflight(
        command=ApplyInterpretationCommand(candidate_id="candidate-1"),
        candidate=candidate,
    )

    assert preflight.risk_level is resource_guard.ResourceRiskLevel.SAFE
    assert receipt is None
    assert reused is False
    assert stages == [
        "Binding reviewed import resource scope",
        "Estimating reviewed import resources",
        "Finalizing reviewed import resource preflight",
    ]


def _mutate_same_size(path: Path) -> None:
    with path.open("r+b") as handle:
        payload = handle.read(1)
        assert payload
        handle.seek(0)
        handle.write(bytes([payload[0] ^ 0x01]))


def _brainvision_integrity_fixture(
    tmp_path: Path,
    *,
    dependency_suffix: str,
) -> tuple[Path, Path]:
    fixture_root = (
        Path(__file__).resolve().parents[4]
        / "tests"
        / "fixtures"
        / "data"
        / "multiformat"
    )
    stem = "A01T-mini-real"
    for suffix in (".vhdr", ".eeg", ".vmrk"):
        source = fixture_root / f"{stem}{suffix}"
        (tmp_path / source.name).write_bytes(source.read_bytes())
    return tmp_path / f"{stem}.vhdr", tmp_path / f"{stem}{dependency_suffix}"


def _non_bids_interpretation_source(
    tmp_path: Path,
    source_format: str,
) -> tuple[Path, str]:
    if source_format == "gdf":
        source = tmp_path / "A01T.gdf"
        source.write_bytes(b"GDF header only")
        return source, "file"
    if source_format == "edf":
        source = tmp_path / "S001R04.edf"
        source.write_bytes(b"EDF header only")
        return tmp_path, "folder"
    if source_format == "brainvision":
        source, _dependency = _brainvision_integrity_fixture(
            tmp_path,
            dependency_suffix=".eeg",
        )
        return source, "file"
    raise AssertionError(f"Unsupported non-BIDS source format: {source_format}")


def _integrity_fixture(tmp_path: Path, resource_kind: str) -> tuple[Path, Path]:
    if resource_kind == "selected_eeg":
        selected = tmp_path / "subject.fif"
        selected.write_bytes(b"selected EEG content")
        return selected, selected
    if resource_kind == "brainvision_data":
        return _brainvision_integrity_fixture(
            tmp_path,
            dependency_suffix=".eeg",
        )
    if resource_kind == "brainvision_markers":
        return _brainvision_integrity_fixture(
            tmp_path,
            dependency_suffix=".vmrk",
        )
    if resource_kind == "eeglab_fdt":
        from scipy.io import savemat

        selected = tmp_path / "subject.set"
        dependency = tmp_path / "subject-data.fdt"
        dependency.write_bytes(b"\0" * (2 * 20 * 4))
        savemat(
            selected,
            {
                "EEG": {
                    "data": dependency.name,
                    "nbchan": 2.0,
                    "pnts": 20.0,
                    "trials": 1.0,
                }
            },
            do_compression=True,
        )
        return selected, dependency
    raise AssertionError(f"Unsupported integrity fixture: {resource_kind}")


def _review_integrity_candidate(
    service: DataInterpretationCommandService,
    *,
    selected_eeg: Path,
    entrypoint: str,
) -> str:
    choices = {"label_carrier": "embedded_events"}
    if entrypoint == "review":
        _message, payload = _expect_payload(
            service.handle_review_interpretation(
                ReviewInterpretationCommand(
                    source_path=str(selected_eeg),
                    choices=choices,
                )
            )
        )
        return str(payload["candidate"]["candidate_id"])
    service.handle_scan_source(ScanSourceCommand(source_path=str(selected_eeg)))
    _message, payload = _expect_payload(
        service.handle_preview_interpretation(
            PreviewInterpretationCommand(choices=choices)
        )
    )
    candidate_id = str(payload["candidate"]["candidate_id"])
    service.handle_validate_interpretation(
        ValidateInterpretationCommand(candidate_id=candidate_id)
    )
    return candidate_id


def test_resource_admission_deduplicates_cross_host_path_aliases() -> None:
    first_spelling = r"C:\EEG Data\Subject.fif"

    assert service_module._deduplicate_resource_paths(
        [
            first_spelling,
            r"c:\eeg data\subject.fif",
            r"C:\EEG Data\labels.tsv",
        ]
    ) == [first_spelling, r"C:\EEG Data\labels.tsv"]


def test_scan_preview_validate_and_clear_are_owned_by_interpretation_service(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "reviewed_source"
    source_dir.mkdir()
    eeg_path = source_dir / "sub-01_task-mi_raw.fif"
    events_path = source_dir / "events.tsv"
    eeg_path.write_bytes(b"not loaded during scan")
    events_path.write_text("onset\ttrial_type\n0.0\tleft\n", encoding="utf-8")
    service, _dataset = _service()

    _scan_message, scan_payload = _expect_payload(
        service.handle_scan_source(ScanSourceCommand(source_path=str(source_dir))),
    )
    _preview_message, preview_payload = _expect_payload(
        service.handle_preview_interpretation(
            PreviewInterpretationCommand(
                choices={
                    "label_carrier_choices": {
                        str(events_path): {
                            "label_field": "trial_type",
                            "anchor": "onset",
                            "time_model": "seconds",
                            "granularity": "trial",
                            "value_decisions": _class_value_decisions(
                                {"left": "left hand"}
                            ),
                        },
                    },
                },
            ),
        ),
    )
    _validation_message, validation_payload = _expect_payload(
        service.handle_validate_interpretation(ValidateInterpretationCommand()),
    )
    snapshot = service.snapshot()

    assert scan_payload["payload_type"] == "scan_result"
    assert scan_payload["scan_result"]["eeg_files"] == [str(eeg_path)]
    assert scan_payload["scan_result"]["label_carriers"] == [str(events_path)]
    assert preview_payload["payload_type"] == "interpretation_preview"
    assert preview_payload["preview"]["label_carrier_count"] == 1
    assert validation_payload["payload_type"] == "validation_decision"
    assert validation_payload["validation_decision"]["decision"] == "safe"
    assert validation_payload["validation_decision"]["required_confirmations"] == []
    assert snapshot.has_scan_result is True
    assert snapshot.has_candidate is True
    assert snapshot.has_preview is True
    assert snapshot.has_validation_decision is True
    assert snapshot.pending_confirmation is False
    assert snapshot.class_map == {"left": "left hand"}

    service.clear()

    cleared = service.snapshot()
    assert cleared.has_scan_result is False
    assert cleared.has_candidate is False
    assert cleared.has_preview is False
    assert cleared.has_validation_decision is False


@pytest.mark.parametrize("source_format", ["gdf", "edf", "brainvision"])
def test_non_bids_scan_preview_validate_has_no_bids_root_warning(
    tmp_path: Path,
    source_format: str,
) -> None:
    source_path, source_hint = _non_bids_interpretation_source(
        tmp_path,
        source_format,
    )
    service, _dataset = _service()

    _scan_message, scan_payload = _expect_payload(
        service.handle_scan_source(
            ScanSourceCommand(
                source_path=str(source_path),
                source_hint=source_hint,
            ),
        ),
    )
    _preview_message, preview_payload = _expect_payload(
        service.handle_preview_interpretation(
            PreviewInterpretationCommand(choices={"skip_labels": True}),
        ),
    )
    _validation_message, validation_payload = _expect_payload(
        service.handle_validate_interpretation(ValidateInterpretationCommand()),
    )

    missing_bids_root = (
        "dataset_description.json is missing from the selected BIDS root."
    )
    assert missing_bids_root not in scan_payload["scan_result"]["warnings"]
    assert preview_payload["candidate"]["bids"]["root_validation_issue"] == ""
    assert missing_bids_root not in preview_payload["candidate"]["warnings"]
    assert missing_bids_root not in preview_payload["preview"]["warnings"]
    assert (
        missing_bids_root not in validation_payload["validation_decision"]["warnings"]
    )


def test_scan_preview_includes_labels_from_external_folder(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "eeg"
    label_dir = tmp_path / "labels"
    source_dir.mkdir()
    label_dir.mkdir()
    eeg_path = source_dir / "sub-01_task-mi_raw.fif"
    label_path = label_dir / "sub-01_task-mi_events.tsv"
    eeg_path.write_bytes(b"not loaded during scan")
    label_path.write_text("onset\ttrial_type\n0.0\tleft\n", encoding="utf-8")
    service, _dataset = _service()

    _scan_message, scan_payload = _expect_payload(
        service.handle_scan_source(
            ScanSourceCommand(
                source_path=str(source_dir),
                label_sources=[str(label_dir)],
            ),
        ),
    )
    _preview_message, preview_payload = _expect_payload(
        service.handle_preview_interpretation(
            PreviewInterpretationCommand(
                choices={
                    "label_carrier_choices": {
                        str(label_path): {
                            "label_field": "trial_type",
                            "anchor": "onset",
                            "time_model": "seconds",
                            "granularity": "trial",
                        },
                    },
                },
            ),
        ),
    )
    snapshot = service.snapshot()

    assert scan_payload["scan_result"]["label_sources"] == [str(label_dir.resolve())]
    assert scan_payload["scan_result"]["label_carriers"] == [str(label_path.resolve())]
    assert preview_payload["candidate"]["label_sources"] == [str(label_dir.resolve())]
    assert preview_payload["preview"]["label_carrier_count"] == 1
    assert preview_payload["preview"]["label_carrier_preview"][0]["source_kind"] == (
        "user_added"
    )
    assert snapshot.label_sources == [str(label_dir.resolve())]
    assert snapshot.action_items


def test_review_explicit_file_selection_does_not_scan_unselected_subfolders(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "source"
    label_dir = source_dir / "label"
    unrelated_dir = source_dir / "multiformat"
    label_dir.mkdir(parents=True)
    unrelated_dir.mkdir()
    selected_eeg_files = [
        source_dir / "A01T.fif",
        source_dir / "A02T.fif",
        source_dir / "A03T.fif",
    ]
    for eeg_path in selected_eeg_files:
        eeg_path.write_bytes(b"header only")
        (label_dir / f"{eeg_path.stem}.csv").write_text(
            "label\n1\n",
            encoding="utf-8",
        )
    unrelated_eeg = unrelated_dir / "A01T-mini-real.edf"
    unrelated_eeg.write_bytes(b"not part of the explicit file selection")
    (label_dir / "unrelated.csv").write_text("label\n2\n", encoding="utf-8")
    service, _dataset = _service()

    _message, payload = _expect_payload(
        service.handle_review_interpretation(
            ReviewInterpretationCommand(
                source_path=str(source_dir),
                source_hint="file",
                choices={
                    "selected_eeg_files": [
                        str(path.resolve()) for path in selected_eeg_files
                    ],
                },
            ),
        ),
    )

    expected_eeg_files = [str(path.resolve()) for path in selected_eeg_files]
    expected_label_files = [
        str((label_dir / f"{path.stem}.csv").resolve()) for path in selected_eeg_files
    ]
    assert payload["scan_result"]["source_kind"] == "file"
    assert payload["scan_result"]["eeg_files"] == expected_eeg_files
    assert payload["scan_result"]["label_carriers"] == expected_label_files
    assert payload["candidate"]["selected_eeg_files"] == expected_eeg_files
    assert payload["resource_preflight"]["eeg_path_count"] == 3
    assert str(unrelated_eeg.resolve()) not in payload["scan_result"]["eeg_files"]


def test_folder_preview_materializes_only_the_selected_admitted_eeg_scope(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "source"
    nested_dir = source_dir / "other-format"
    nested_dir.mkdir(parents=True)
    selected_eeg = source_dir / "selected.fif"
    unrelated_eeg = nested_dir / "unrelated.edf"
    selected_eeg.write_bytes(b"selected header")
    unrelated_eeg.write_bytes(b"unselected header")
    service, _dataset = _service()

    service.handle_scan_source(
        ScanSourceCommand(
            source_path=str(source_dir),
            source_hint="folder",
        ),
    )
    _message, payload = _expect_payload(
        service.handle_preview_interpretation(
            PreviewInterpretationCommand(
                choices={
                    "selected_eeg_files": [str(selected_eeg.resolve())],
                    "label_carrier": "embedded_events",
                },
            ),
        ),
    )

    assert payload["candidate"]["selected_eeg_files"] == [
        str(selected_eeg.resolve()),
    ]
    capability_paths = {
        item["path"] for item in payload["candidate"]["format_capabilities"]
    }
    assert str(unrelated_eeg.resolve()) not in capability_paths


def test_review_blocks_external_label_before_candidate_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_dir = tmp_path / "eeg"
    label_dir = tmp_path / "labels"
    eeg_dir.mkdir()
    label_dir.mkdir()
    eeg_path = eeg_dir / "subject.fif"
    label_path = label_dir / "subject.mat"
    eeg_path.write_bytes(b"header only")
    label_path.write_bytes(b"large external label carrier")
    service, _dataset = _service()
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 64)

    def _must_not_materialize(**_kwargs: Any) -> Any:
        pytest.fail("candidate materialization ran before the blocking RAM preflight")

    monkeypatch.setattr(
        "XBrainLab.backend.application.data_interpretation_service.build_interpretation_candidate",
        _must_not_materialize,
    )

    with pytest.raises(PreconditionError) as raised:
        service.handle_review_interpretation(
            ReviewInterpretationCommand(
                source_path=str(eeg_path),
                label_sources=[str(label_dir)],
            ),
        )

    diagnostics = raised.value.diagnostics["resource_preflight"]
    assert diagnostics["risk_level"] == "blocking"
    assert diagnostics["eeg_path_count"] == 1
    assert diagnostics["label_carrier_count"] == 1
    assert diagnostics["label_carrier_file_bytes"] == label_path.stat().st_size


def test_review_blocking_mat_preflight_runs_before_loadmat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = tmp_path / "subject.fif"
    label_path = tmp_path / "subject.mat"
    eeg_path.write_bytes(b"header only")
    with label_path.open("wb") as handle:
        handle.truncate(1_000_000)
    service, _dataset = _service()
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 10_000_000)
    loadmat_calls = 0

    eeg_only = resource_guard.check_import_resource_preflight([str(eeg_path)])
    assert eeg_only.risk_level is resource_guard.ResourceRiskLevel.SAFE

    def _must_not_loadmat(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal loadmat_calls
        loadmat_calls += 1
        pytest.fail("loadmat ran before the blocking RAM preflight")

    monkeypatch.setattr(
        "XBrainLab.backend.application.data_interpretation_label_carriers.loadmat",
        _must_not_loadmat,
    )

    with pytest.raises(PreconditionError) as raised:
        service.handle_review_interpretation(
            ReviewInterpretationCommand(
                source_path=str(eeg_path),
                label_sources=[str(label_path)],
            ),
        )

    diagnostics = raised.value.diagnostics["resource_preflight"]
    assert diagnostics["risk_level"] == "blocking"
    assert diagnostics["label_carrier_count"] == 1
    assert diagnostics["label_carrier_working_set_bytes"] > label_path.stat().st_size
    assert loadmat_calls == 0


def test_review_blocking_bids_preflight_runs_before_events_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bids_root = tmp_path / "bids"
    eeg_dir = bids_root / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    (bids_root / "dataset_description.json").write_text(
        json.dumps({"Name": "Resource preflight", "BIDSVersion": "1.9.0"}),
        encoding="utf-8",
    )
    eeg_path = eeg_dir / "sub-01_task-mi_eeg.fif"
    events_path = eeg_dir / "sub-01_task-mi_events.tsv"
    eeg_path.write_bytes(b"header only")
    events_path.write_text("onset\tduration\ttrial_type\n", encoding="utf-8")
    with events_path.open("ab") as handle:
        handle.truncate(1_000_000)
    service, _dataset = _service()
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 10_000_000)
    events_read_calls = 0

    def _must_not_read_events(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal events_read_calls
        events_read_calls += 1
        pytest.fail("events.tsv materialized before the blocking RAM preflight")

    monkeypatch.setattr(
        "XBrainLab.backend.application.data_interpretation_bids._read_events_rows",
        _must_not_read_events,
    )

    with pytest.raises(PreconditionError) as raised:
        service.handle_review_interpretation(
            ReviewInterpretationCommand(
                source_path=str(bids_root),
                source_hint="bids",
            ),
        )

    diagnostics = raised.value.diagnostics["resource_preflight"]
    assert diagnostics["risk_level"] == "blocking"
    assert diagnostics["label_carrier_count"] == 1
    assert diagnostics["label_carrier_file_bytes"] == events_path.stat().st_size
    assert events_read_calls == 0


def test_review_blocks_bids_participants_before_scan_tsv_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bids_root = tmp_path / "bids"
    eeg_dir = bids_root / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    (bids_root / "dataset_description.json").write_text(
        json.dumps({"Name": "Resource preflight", "BIDSVersion": "1.9.0"}),
        encoding="utf-8",
    )
    (eeg_dir / "sub-01_task-mi_eeg.fif").write_bytes(b"header only")
    (eeg_dir / "sub-01_task-mi_events.tsv").write_text(
        "onset\ttrial_type\n0\tleft\n",
        encoding="utf-8",
    )
    participants = bids_root / "participants.tsv"
    participants.write_text("participant_id\n", encoding="utf-8")
    with participants.open("ab") as handle:
        handle.truncate(2_000_000)
    service, _dataset = _service()
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 100_000_000)

    def _must_not_read_tsv(_path: Path) -> list[dict[str, str]]:
        pytest.fail("participants.tsv was parsed before RAM admission")

    monkeypatch.setattr(
        "XBrainLab.backend.application.data_interpretation_metadata._read_tsv_rows",
        _must_not_read_tsv,
    )

    with pytest.raises(PreconditionError) as raised:
        service.handle_review_interpretation(
            ReviewInterpretationCommand(
                source_path=str(bids_root),
                source_hint="bids",
            ),
        )

    diagnostics = raised.value.diagnostics["resource_preflight"]
    assert diagnostics["risk_level"] == "blocking"
    assert diagnostics["scan_metadata_count"] == 2
    assert str(participants.resolve()) in {
        item["path"] for item in diagnostics["files"]
    }


def test_reload_blocks_bids_channels_before_scan_tsv_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bids_root = tmp_path / "bids"
    eeg_dir = bids_root / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    (bids_root / "dataset_description.json").write_text(
        json.dumps({"Name": "Resource preflight", "BIDSVersion": "1.9.0"}),
        encoding="utf-8",
    )
    eeg_path = eeg_dir / "sub-01_task-mi_eeg.fif"
    events_path = eeg_dir / "sub-01_task-mi_events.tsv"
    channels = eeg_dir / "sub-01_task-mi_channels.tsv"
    eeg_path.write_bytes(b"header only")
    events_path.write_text("onset\ttrial_type\n0\tleft\n", encoding="utf-8")
    channels.write_text("name\tstatus\n", encoding="utf-8")
    with channels.open("ab") as handle:
        handle.truncate(2_000_000)
    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_text(
        json.dumps(
            {
                "recipe_id": "recipe-1",
                "interpretation_id": "interpretation-1",
                "source_path": str(bids_root),
                "source_kind": "bids",
                "selected_eeg_files": [str(eeg_path)],
                "label_carriers": [str(events_path)],
            },
        ),
        encoding="utf-8",
    )
    service, _dataset = _service()
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 100_000_000)

    def _must_not_read_tsv(_path: Path) -> list[dict[str, str]]:
        pytest.fail("channels.tsv was parsed before RAM admission")

    monkeypatch.setattr(
        "XBrainLab.backend.application.data_interpretation_metadata._read_tsv_rows",
        _must_not_read_tsv,
    )

    with pytest.raises(PreconditionError) as raised:
        service.handle_reload_interpretation_recipe(
            ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path)),
        )

    diagnostics = raised.value.diagnostics["resource_preflight"]
    assert diagnostics["risk_level"] == "blocking"
    assert diagnostics["scan_metadata_count"] == 2
    assert str(channels.resolve()) in {item["path"] for item in diagnostics["files"]}


def test_preview_blocks_external_label_before_candidate_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = tmp_path / "subject.fif"
    label_path = tmp_path / "subject.mat"
    eeg_path.write_bytes(b"header only")
    with label_path.open("wb") as handle:
        handle.truncate(1_000_000)
    service, _dataset = _service()
    service.handle_scan_source(
        ScanSourceCommand(
            source_path=str(eeg_path),
            label_sources=[str(label_path)],
        ),
    )
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 10_000_000)

    def _must_not_materialize(**_kwargs: Any) -> Any:
        pytest.fail("candidate materialization ran before the blocking RAM preflight")

    monkeypatch.setattr(
        "XBrainLab.backend.application.data_interpretation_service.build_interpretation_candidate",
        _must_not_materialize,
    )

    with pytest.raises(PreconditionError) as raised:
        service.handle_preview_interpretation(PreviewInterpretationCommand())

    diagnostics = raised.value.diagnostics["resource_preflight"]
    assert diagnostics["risk_level"] == "blocking"
    assert diagnostics["label_carrier_count"] == 1


def test_preview_blocks_unbounded_compressed_set_before_internal_event_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    service, _dataset = _service()
    service.handle_scan_source(
        ScanSourceCommand(source_path=str(set_path), source_hint="file")
    )
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 10**12)

    def _must_not_materialize(**_kwargs: Any) -> Any:
        pytest.fail("internal-event preview ran before bounded SET preflight")

    monkeypatch.setattr(
        service_module,
        "build_interpretation_candidate",
        _must_not_materialize,
    )

    with pytest.raises(PreconditionError) as raised:
        service.handle_preview_interpretation(
            PreviewInterpretationCommand(choices={"label_carrier": "embedded_events"})
        )

    diagnostics = raised.value.diagnostics["resource_preflight"]
    assert diagnostics["risk_level"] == "blocking"
    assert diagnostics["files"][0]["size_bound_known"] is False


def test_preview_skip_labels_excludes_carrier_from_resource_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = tmp_path / "subject.fif"
    label_path = tmp_path / "subject.mat"
    eeg_path.write_bytes(b"header only")
    with label_path.open("wb") as handle:
        handle.truncate(1_000_000)
    service, _dataset = _service()
    service.handle_scan_source(
        ScanSourceCommand(
            source_path=str(eeg_path),
            label_sources=[str(label_path)],
        ),
    )
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 10_000_000)

    _message, payload = _expect_payload(
        service.handle_preview_interpretation(
            PreviewInterpretationCommand(choices={"skip_labels": True}),
        ),
    )

    assert payload["resource_preflight"]["risk_level"] == "safe"
    assert payload["resource_preflight"]["label_carrier_count"] == 0
    assert payload["candidate"]["label_carriers"] == []


def test_review_warning_requires_confirmation_before_materializing_deduped_labels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    eeg_path = source_dir / "subject.fif"
    label_path = source_dir / "subject_events.tsv"
    eeg_path.write_bytes(b"header only")
    label_path.write_text("onset\ttrial_type\n0\tleft\n", encoding="utf-8")
    service, _dataset = _service()
    checked_scopes: list[tuple[str, ...]] = []
    materialized = 0

    def _check(paths: list[str]) -> ResourcePreflightResult:
        checked_scopes.append(tuple(paths))
        return _resource_preflight("warning", paths)

    original_builder = build_interpretation_candidate

    def _build(**kwargs: Any) -> Any:
        nonlocal materialized
        materialized += 1
        return original_builder(**kwargs)

    monkeypatch.setattr(
        "XBrainLab.backend.application.data_interpretation_service.check_import_resource_preflight",
        _check,
    )
    monkeypatch.setattr(
        "XBrainLab.backend.application.data_interpretation_service.build_interpretation_candidate",
        _build,
    )

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as raised:
        service.handle_review_interpretation(
            ReviewInterpretationCommand(
                source_path=str(eeg_path),
                label_sources=[str(label_path), str(source_dir)],
            ),
        )

    assert materialized == 0
    assert len(checked_scopes) == 1
    assert_filesystem_path_lists_equal(
        checked_scopes[0],
        [eeg_path, label_path],
    )
    challenge = _resource_challenge(raised.value)
    assert challenge["command_name"] == "review_interpretation"

    _message, payload = _expect_payload(
        service.handle_review_interpretation(
            ReviewInterpretationCommand(
                source_path=str(eeg_path),
                label_sources=[str(label_path), str(source_dir)],
                resource_preflight_confirmed=True,
                resource_preflight_token=challenge["challenge_id"],
            ),
        ),
    )

    assert materialized == 1
    assert len(checked_scopes) == 2
    assert payload["resource_preflight"]["risk_level"] == "warning"
    assert payload["resource_preflight"]["confirmation_receipt_reused"] is True


def test_review_warning_naked_boolean_and_replay_fail_closed_with_fresh_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = tmp_path / "subject.fif"
    eeg_path.write_bytes(b"header only")
    service, _dataset = _service()
    materialized = 0
    original_builder = build_interpretation_candidate

    def _check(paths: list[str]) -> ResourcePreflightResult:
        return _resource_preflight("warning", paths)

    def _build(**kwargs: Any) -> Any:
        nonlocal materialized
        materialized += 1
        return original_builder(**kwargs)

    monkeypatch.setattr(service_module, "check_import_resource_preflight", _check)
    monkeypatch.setattr(service_module, "build_interpretation_candidate", _build)

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as first:
        service.handle_review_interpretation(
            ReviewInterpretationCommand(source_path=str(eeg_path))
        )
    first_challenge = _resource_challenge(first.value)

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as naked:
        service.handle_review_interpretation(
            ReviewInterpretationCommand(
                source_path=str(eeg_path),
                resource_preflight_confirmed=True,
            )
        )
    naked_challenge = _resource_challenge(naked.value)
    assert naked_challenge["challenge_id"] != first_challenge["challenge_id"]
    assert materialized == 0

    _message, payload = _expect_payload(
        service.handle_review_interpretation(
            ReviewInterpretationCommand(
                source_path=str(eeg_path),
                resource_preflight_confirmed=True,
                resource_preflight_token=naked_challenge["challenge_id"],
            )
        )
    )
    assert payload["resource_preflight"]["confirmation_receipt_reused"] is True
    assert materialized == 1

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as replayed:
        service.handle_review_interpretation(
            ReviewInterpretationCommand(
                source_path=str(eeg_path),
                resource_preflight_confirmed=True,
                resource_preflight_token=naked_challenge["challenge_id"],
            )
        )
    replay_challenge = _resource_challenge(replayed.value)
    assert replay_challenge["challenge_id"] != naked_challenge["challenge_id"]
    assert materialized == 1


def test_review_warning_receipt_is_discarded_when_presented_on_safe_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = tmp_path / "subject.fif"
    eeg_path.write_bytes(b"header only")
    service, _dataset = _service()
    risk_levels = iter(("warning", "safe", "warning"))

    monkeypatch.setattr(
        service_module,
        "check_import_resource_preflight",
        lambda paths: _resource_preflight(next(risk_levels), paths),
    )

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as first:
        service.handle_review_interpretation(
            ReviewInterpretationCommand(source_path=str(eeg_path))
        )
    first_challenge = _resource_challenge(first.value)

    _expect_payload(
        service.handle_review_interpretation(
            ReviewInterpretationCommand(
                source_path=str(eeg_path),
                resource_preflight_confirmed=True,
                resource_preflight_token=first_challenge["challenge_id"],
            )
        )
    )

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as stale:
        service.handle_review_interpretation(
            ReviewInterpretationCommand(
                source_path=str(eeg_path),
                resource_preflight_confirmed=True,
                resource_preflight_token=first_challenge["challenge_id"],
            )
        )

    assert (
        _resource_challenge(stale.value)["challenge_id"]
        != first_challenge["challenge_id"]
    )


def test_review_warning_receipt_is_bound_to_deterministic_choices(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = tmp_path / "subject.fif"
    eeg_path.write_bytes(b"header only")
    service, _dataset = _service()
    monkeypatch.setattr(
        service_module,
        "check_import_resource_preflight",
        lambda paths: _resource_preflight("warning", paths),
    )

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as first:
        service.handle_review_interpretation(
            ReviewInterpretationCommand(
                source_path=str(eeg_path),
                choices={"skip_labels": False},
            )
        )
    first_challenge = _resource_challenge(first.value)

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as changed:
        service.handle_review_interpretation(
            ReviewInterpretationCommand(
                source_path=str(eeg_path),
                choices={"skip_labels": True},
                resource_preflight_confirmed=True,
                resource_preflight_token=first_challenge["challenge_id"],
            )
        )
    changed_challenge = _resource_challenge(changed.value)

    assert changed_challenge["challenge_id"] != first_challenge["challenge_id"]
    assert (
        changed_challenge["configuration_fingerprint"]
        != first_challenge["configuration_fingerprint"]
    )
    assert service.snapshot().has_preview is False


def test_review_warning_receipt_choice_fingerprint_is_order_independent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = tmp_path / "subject.fif"
    eeg_path.write_bytes(b"header only")
    service, _dataset = _service()
    monkeypatch.setattr(
        service_module,
        "check_import_resource_preflight",
        lambda paths: _resource_preflight("warning", paths),
    )
    first_choices = {
        "skip_labels": False,
        "metadata_overrides": {
            eeg_path.name: {"session": "02", "subject": "01"},
        },
    }
    reordered_choices = {
        "metadata_overrides": {
            eeg_path.name: {"subject": "01", "session": "02"},
        },
        "skip_labels": False,
    }

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as first:
        service.handle_review_interpretation(
            ReviewInterpretationCommand(
                source_path=str(eeg_path),
                choices=first_choices,
            )
        )
    first_challenge = _resource_challenge(first.value)

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as reordered:
        service.handle_review_interpretation(
            ReviewInterpretationCommand(
                source_path=str(eeg_path),
                choices=reordered_choices,
            )
        )
    reordered_challenge = _resource_challenge(reordered.value)

    assert reordered_challenge["challenge_id"] == first_challenge["challenge_id"]
    assert (
        reordered_challenge["configuration_fingerprint"]
        == first_challenge["configuration_fingerprint"]
    )


def test_review_warning_receipt_rejects_changed_source_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_eeg = tmp_path / "first.fif"
    second_eeg = tmp_path / "second.fif"
    first_eeg.write_bytes(b"first header")
    second_eeg.write_bytes(b"second header")
    service, _dataset = _service()
    monkeypatch.setattr(
        service_module,
        "check_import_resource_preflight",
        lambda paths: _resource_preflight("warning", paths),
    )

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as first:
        service.handle_review_interpretation(
            ReviewInterpretationCommand(source_path=str(first_eeg))
        )
    first_challenge = _resource_challenge(first.value)

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as changed:
        service.handle_review_interpretation(
            ReviewInterpretationCommand(
                source_path=str(second_eeg),
                resource_preflight_confirmed=True,
                resource_preflight_token=first_challenge["challenge_id"],
            )
        )
    changed_challenge = _resource_challenge(changed.value)

    assert changed_challenge["challenge_id"] != first_challenge["challenge_id"]
    assert (
        changed_challenge["scope_fingerprint"] != first_challenge["scope_fingerprint"]
    )
    assert service.snapshot().has_preview is False


def test_review_warning_receipt_cannot_authorize_preview_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = tmp_path / "subject.fif"
    eeg_path.write_bytes(b"header only")
    service, _dataset = _service()
    service.handle_scan_source(ScanSourceCommand(source_path=str(eeg_path)))
    monkeypatch.setattr(
        service_module,
        "check_import_resource_preflight",
        lambda paths: _resource_preflight("warning", paths),
    )

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as review:
        service.handle_review_interpretation(
            ReviewInterpretationCommand(source_path=str(eeg_path))
        )
    review_challenge = _resource_challenge(review.value)

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as preview:
        service.handle_preview_interpretation(
            PreviewInterpretationCommand(
                resource_preflight_confirmed=True,
                resource_preflight_token=review_challenge["challenge_id"],
            )
        )
    preview_challenge = _resource_challenge(preview.value)

    assert review_challenge["command_name"] == "review_interpretation"
    assert preview_challenge["command_name"] == "preview_interpretation"
    assert preview_challenge["challenge_id"] != review_challenge["challenge_id"]
    assert service.snapshot().has_preview is False


def test_preview_warning_receipt_is_bound_to_exact_scan_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_eeg = tmp_path / "first.fif"
    second_eeg = tmp_path / "second.fif"
    first_eeg.write_bytes(b"first header")
    second_eeg.write_bytes(b"second header")
    service, _dataset = _service()
    _message, first_scan_payload = _expect_payload(
        service.handle_scan_source(ScanSourceCommand(source_path=str(first_eeg)))
    )
    first_scan_id = first_scan_payload["scan_result"]["scan_id"]
    monkeypatch.setattr(
        service_module,
        "check_import_resource_preflight",
        lambda paths: _resource_preflight("warning", paths),
    )

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as first:
        service.handle_preview_interpretation(
            PreviewInterpretationCommand(scan_id=first_scan_id)
        )
    first_challenge = _resource_challenge(first.value)

    _message, second_scan_payload = _expect_payload(
        service.handle_scan_source(ScanSourceCommand(source_path=str(second_eeg)))
    )
    second_scan_id = second_scan_payload["scan_result"]["scan_id"]
    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as changed:
        service.handle_preview_interpretation(
            PreviewInterpretationCommand(
                scan_id=second_scan_id,
                resource_preflight_confirmed=True,
                resource_preflight_token=first_challenge["challenge_id"],
            )
        )
    changed_challenge = _resource_challenge(changed.value)

    assert first_challenge["candidate_id"] == first_scan_id
    assert changed_challenge["candidate_id"] == second_scan_id
    assert changed_challenge["challenge_id"] != first_challenge["challenge_id"]
    assert service.snapshot().has_preview is False


def test_review_warning_receipts_evict_oldest_after_authority_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _dataset = _service()
    monkeypatch.setattr(
        service_module,
        "check_import_resource_preflight",
        lambda paths: _resource_preflight("warning", paths),
    )
    challenges: list[tuple[Path, dict[str, Any]]] = []
    for index in range(INTERPRETATION_PREFLIGHT_RECEIPT_LIMIT + 1):
        eeg_path = tmp_path / f"subject-{index}.fif"
        eeg_path.write_bytes(f"header-{index}".encode())
        with pytest.raises(
            resource_guard.ResourceConfirmationRequiredError
        ) as challenged:
            service.handle_review_interpretation(
                ReviewInterpretationCommand(source_path=str(eeg_path))
            )
        challenges.append((eeg_path, _resource_challenge(challenged.value)))

    oldest_path, oldest_challenge = challenges[0]
    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as evicted:
        service.handle_review_interpretation(
            ReviewInterpretationCommand(
                source_path=str(oldest_path),
                resource_preflight_confirmed=True,
                resource_preflight_token=oldest_challenge["challenge_id"],
            )
        )

    assert (
        _resource_challenge(evicted.value)["challenge_id"]
        != oldest_challenge["challenge_id"]
    )
    assert service.snapshot().has_preview is False


def test_preview_warning_receipt_expires_before_candidate_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = tmp_path / "subject.fif"
    eeg_path.write_bytes(b"header only")
    monotonic_now = 100.0
    monkeypatch.setattr(service_module.time, "monotonic", lambda: monotonic_now)
    service, _dataset = _service()
    service.handle_scan_source(ScanSourceCommand(source_path=str(eeg_path)))
    monkeypatch.setattr(
        service_module,
        "check_import_resource_preflight",
        lambda paths: _resource_preflight("warning", paths),
    )

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as first:
        service.handle_preview_interpretation(PreviewInterpretationCommand())
    first_challenge = _resource_challenge(first.value)

    monotonic_now += INTERPRETATION_PREFLIGHT_RECEIPT_TTL_SECONDS + 1.0
    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as expired:
        service.handle_preview_interpretation(
            PreviewInterpretationCommand(
                resource_preflight_confirmed=True,
                resource_preflight_token=first_challenge["challenge_id"],
            )
        )
    expired_challenge = _resource_challenge(expired.value)

    assert expired_challenge["challenge_id"] != first_challenge["challenge_id"]
    assert service.snapshot().has_preview is False


def test_review_warning_receipt_is_consumed_before_candidate_build_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = tmp_path / "subject.fif"
    eeg_path.write_bytes(b"header only")
    service, _dataset = _service()
    monkeypatch.setattr(
        service_module,
        "check_import_resource_preflight",
        lambda paths: _resource_preflight("warning", paths),
    )

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as first:
        service.handle_review_interpretation(
            ReviewInterpretationCommand(source_path=str(eeg_path))
        )
    challenge = _resource_challenge(first.value)

    build_calls = 0

    def _fail_build(**_kwargs: Any) -> Any:
        nonlocal build_calls
        build_calls += 1
        raise RuntimeError("candidate build failed")

    monkeypatch.setattr(service_module, "build_interpretation_candidate", _fail_build)
    with pytest.raises(RuntimeError, match="candidate build failed"):
        service.handle_review_interpretation(
            ReviewInterpretationCommand(
                source_path=str(eeg_path),
                resource_preflight_confirmed=True,
                resource_preflight_token=challenge["challenge_id"],
            )
        )

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as replayed:
        service.handle_review_interpretation(
            ReviewInterpretationCommand(
                source_path=str(eeg_path),
                resource_preflight_confirmed=True,
                resource_preflight_token=challenge["challenge_id"],
            )
        )
    assert (
        _resource_challenge(replayed.value)["challenge_id"] != challenge["challenge_id"]
    )
    assert build_calls == 1


def test_review_preflight_combines_auto_and_user_added_label_carriers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_dir = tmp_path / "eeg"
    label_dir = tmp_path / "labels"
    eeg_dir.mkdir()
    label_dir.mkdir()
    eeg_path = eeg_dir / "subject.fif"
    auto_label = eeg_dir / "subject_events.tsv"
    user_label = label_dir / "subject.csv"
    eeg_path.write_bytes(b"header only")
    auto_label.write_text("onset\ttrial_type\n0\tleft\n", encoding="utf-8")
    user_label.write_text("label\nleft\n", encoding="utf-8")
    service, _dataset = _service()
    checked_scopes: list[tuple[str, ...]] = []

    def _check(paths: list[str]) -> ResourcePreflightResult:
        checked_scopes.append(tuple(paths))
        return _resource_preflight("safe", paths)

    monkeypatch.setattr(
        "XBrainLab.backend.application.data_interpretation_service.check_import_resource_preflight",
        _check,
    )

    service.handle_review_interpretation(
        ReviewInterpretationCommand(
            source_path=str(eeg_path),
            label_sources=[str(label_dir), str(user_label)],
        ),
    )

    assert len(checked_scopes) == 1
    assert len(checked_scopes[0]) == 3
    assert set(checked_scopes[0]) == {
        str(eeg_path.resolve()),
        str(auto_label.resolve()),
        str(user_label.resolve()),
    }


def test_current_review_returns_exact_serialized_review_without_rescanning(
    tmp_path: Path,
) -> None:
    eeg_path = tmp_path / "subject.fif"
    eeg_path.write_bytes(b"header only")
    service, _dataset = _service()
    _message, payload = _expect_payload(
        service.handle_review_interpretation(
            ReviewInterpretationCommand(
                source_path=str(eeg_path),
                choices={"metadata_overrides": {str(eeg_path): {"subject": "01"}}},
            )
        )
    )

    review = service.current_review()

    assert review["source_path"] == str(eeg_path.resolve())
    assert review["source_hint"] == "auto"
    assert review["label_sources"] == []
    assert review["choices"] == payload["candidate"]["choices"]
    assert review["scan_result"] == payload["scan_result"]
    assert review["candidate"] == payload["candidate"]
    assert review["preview"] == payload["preview"]
    assert review["validation_decision"] == payload["validation_decision"]


def test_reload_skip_label_recipe_does_not_rescan_external_label_sources(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "eeg"
    label_dir = tmp_path / "labels"
    source_dir.mkdir()
    label_dir.mkdir()
    eeg_path = source_dir / "sub-01_task-mi_raw.fif"
    label_path = label_dir / "sub-01_task-mi_events.tsv"
    recipe_path = tmp_path / "skip-labels-recipe.json"
    eeg_path.write_bytes(b"not loaded during scan")
    label_path.write_text("onset\ttrial_type\n0.0\tleft\n", encoding="utf-8")
    recipe_path.write_text(
        json.dumps(
            {
                "recipe_id": "recipe-1",
                "interpretation_id": "interp-1",
                "source_path": str(source_dir),
                "source_kind": "folder",
                "selected_eeg_files": [str(eeg_path)],
                "skip_labels": True,
                "label_sources": [str(label_dir)],
                "label_carriers": [str(label_path)],
                "label_carrier_plan": [{"path": str(label_path)}],
                "label_carrier": "external_files",
                "event_roles": {"trial_type": "class cue"},
                "class_map": {"left": "left hand"},
            },
        ),
        encoding="utf-8",
    )
    service, _dataset = _service()

    _message, payload = _expect_payload(
        service.handle_reload_interpretation_recipe(
            ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path)),
        ),
    )

    assert payload["scan_result"]["label_sources"] == []
    assert payload["scan_result"]["label_carriers"] == []
    assert payload["candidate"]["label_sources"] == []
    assert payload["candidate"]["label_carriers"] == []
    assert payload["candidate"]["class_map"] == {}
    assert payload["candidate"]["choices"]["skip_labels"] is True
    assert "label_carrier" not in payload["candidate"]["choices"]


def test_reload_recipe_blocks_large_label_before_candidate_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_dir = tmp_path / "eeg"
    label_dir = tmp_path / "labels"
    source_dir.mkdir()
    label_dir.mkdir()
    eeg_path = source_dir / "subject.fif"
    label_path = label_dir / "subject.mat"
    recipe_path = tmp_path / "recipe.json"
    eeg_path.write_bytes(b"header only")
    with label_path.open("wb") as handle:
        handle.truncate(1_000_000)
    recipe_path.write_text(
        json.dumps(
            {
                "recipe_id": "recipe-1",
                "interpretation_id": "interp-1",
                "source_path": str(source_dir),
                "source_kind": "folder",
                "selected_eeg_files": [str(eeg_path)],
                "label_sources": [str(label_dir)],
                "label_carriers": [str(label_path)],
                "label_carrier_plan": [{"path": str(label_path)}],
                "label_carrier": "external_files",
            }
        ),
        encoding="utf-8",
    )
    service, _dataset = _service()
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 10_000_000)

    def _must_not_materialize(**_kwargs: Any) -> Any:
        pytest.fail("recipe candidate materialized before the blocking RAM preflight")

    monkeypatch.setattr(
        "XBrainLab.backend.application.data_interpretation_service.build_interpretation_candidate",
        _must_not_materialize,
    )

    with pytest.raises(PreconditionError) as raised:
        service.handle_reload_interpretation_recipe(
            ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path)),
        )

    diagnostics = raised.value.diagnostics["resource_preflight"]
    assert diagnostics["risk_level"] == "blocking"
    assert diagnostics["label_carrier_count"] == 1


def test_reload_rejects_oversized_recipe_before_json_loader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recipe_path = tmp_path / "oversized-recipe.json"
    recipe_path.write_text("{}", encoding="utf-8")
    with recipe_path.open("ab") as handle:
        handle.truncate(service_module.IMPORT_RECIPE_MAX_BYTES + 1)
    service, _dataset = _service()

    def _must_not_load_recipe(_path: str) -> Any:
        pytest.fail("oversized recipe reached the full JSON loader")

    monkeypatch.setattr(service_module, "load_import_recipe", _must_not_load_recipe)

    with pytest.raises(PreconditionError) as raised:
        service.handle_reload_interpretation_recipe(
            ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path)),
        )

    diagnostics = raised.value.diagnostics["recipe_input"]
    assert diagnostics["risk_level"] == "blocking"
    assert diagnostics["file_bytes"] == service_module.IMPORT_RECIPE_MAX_BYTES + 1
    assert diagnostics["max_bytes"] == service_module.IMPORT_RECIPE_MAX_BYTES
    assert "smaller recipe" in raised.value.message.lower()
    assert service.snapshot().has_scan_result is False


def test_reload_admits_recipe_before_json_loader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_text("{}", encoding="utf-8")
    checked_scopes: list[tuple[str, ...]] = []
    service, _dataset = _service()

    def _check(paths: list[str]) -> ResourcePreflightResult:
        checked_scopes.append(tuple(paths))
        return _resource_preflight("blocking")

    def _must_not_load_recipe(_path: str) -> Any:
        pytest.fail("recipe JSON loaded before its resource admission")

    monkeypatch.setattr(service_module, "check_import_resource_preflight", _check)
    monkeypatch.setattr(service_module, "load_import_recipe", _must_not_load_recipe)

    with pytest.raises(PreconditionError):
        service.handle_reload_interpretation_recipe(
            ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path)),
        )

    assert checked_scopes == [(str(recipe_path.resolve()),)]
    assert service.snapshot().has_scan_result is False


def test_reload_includes_bounded_recipe_file_in_resource_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = tmp_path / "subject.fif"
    eeg_path.write_bytes(b"header only")
    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_text(
        json.dumps(
            {
                "recipe_id": "recipe-1",
                "interpretation_id": "interpretation-1",
                "source_path": str(eeg_path),
                "source_kind": "file",
                "selected_eeg_files": [str(eeg_path)],
                "skip_labels": True,
            },
        ),
        encoding="utf-8",
    )
    checked_scopes: list[tuple[str, ...]] = []
    service, _dataset = _service()

    def _check(paths: list[str]) -> ResourcePreflightResult:
        checked_scopes.append(tuple(paths))
        return _resource_preflight("safe", paths)

    monkeypatch.setattr(service_module, "check_import_resource_preflight", _check)

    service.handle_reload_interpretation_recipe(
        ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )

    assert checked_scopes[0] == (str(recipe_path.resolve()),)
    assert str(recipe_path.resolve()) in checked_scopes[1]


def test_reload_warning_receipt_is_bound_to_recipe_content_not_only_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_eeg = tmp_path / "first.fif"
    second_eeg = tmp_path / "second.fif"
    first_eeg.write_bytes(b"first header")
    second_eeg.write_bytes(b"second header")
    recipe_path = tmp_path / "recipe.json"

    def _write_recipe(source: Path) -> None:
        recipe_path.write_text(
            json.dumps(
                {
                    "recipe_id": "recipe-1",
                    "interpretation_id": "interpretation-1",
                    "source_path": str(source),
                    "source_kind": "file",
                    "selected_eeg_files": [str(source)],
                    "skip_labels": True,
                },
            ),
            encoding="utf-8",
        )

    _write_recipe(first_eeg)
    service, _dataset = _service()
    monkeypatch.setattr(
        service_module,
        "check_import_resource_preflight",
        lambda paths: _resource_preflight("warning", paths),
    )

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as first:
        service.handle_reload_interpretation_recipe(
            ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path))
        )
    first_challenge = _resource_challenge(first.value)

    _write_recipe(second_eeg)
    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as changed:
        service.handle_reload_interpretation_recipe(
            ReloadInterpretationRecipeCommand(
                recipe_path=str(recipe_path),
                resource_preflight_confirmed=True,
                resource_preflight_token=first_challenge["challenge_id"],
            )
        )
    changed_challenge = _resource_challenge(changed.value)

    assert changed_challenge["challenge_id"] != first_challenge["challenge_id"]
    assert (
        changed_challenge["configuration_fingerprint"]
        != first_challenge["configuration_fingerprint"]
    )
    assert service.snapshot().has_scan_result is False


def test_preview_warning_receipt_cannot_bypass_new_blocking_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = tmp_path / "subject.fif"
    eeg_path.write_bytes(b"header only")
    service, _dataset = _service()
    service.handle_scan_source(ScanSourceCommand(source_path=str(eeg_path)))
    preflights = iter(
        (
            _resource_preflight("warning", [str(eeg_path)]),
            _resource_preflight("blocking", [str(eeg_path)]),
        )
    )
    monkeypatch.setattr(
        service_module,
        "check_import_resource_preflight",
        lambda _paths: next(preflights),
    )

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as first:
        service.handle_preview_interpretation(PreviewInterpretationCommand())
    challenge = _resource_challenge(first.value)

    with pytest.raises(PreconditionError, match="resource risk: blocking"):
        service.handle_preview_interpretation(
            PreviewInterpretationCommand(
                resource_preflight_confirmed=True,
                resource_preflight_token=challenge["challenge_id"],
            )
        )

    assert service.snapshot().has_preview is False


def test_reload_recipe_reader_blocks_growth_after_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = tmp_path / "subject.fif"
    eeg_path.write_bytes(b"header only")
    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_text(
        json.dumps(
            {
                "recipe_id": "recipe-1",
                "interpretation_id": "interpretation-1",
                "source_path": str(eeg_path),
                "source_kind": "file",
                "selected_eeg_files": [str(eeg_path)],
                "skip_labels": True,
            },
        ),
        encoding="utf-8",
    )
    service, _dataset = _service()
    admission_calls = 0
    original_read_text = Path.read_text

    def _check(paths: list[str]) -> ResourcePreflightResult:
        nonlocal admission_calls
        admission_calls += 1
        if admission_calls == 1:
            with recipe_path.open("ab") as handle:
                handle.truncate(service_module.IMPORT_RECIPE_MAX_BYTES + 100)
        return _resource_preflight("safe", paths)

    def _guarded_read_text(path: Path, *args, **kwargs):
        if path == recipe_path:
            pytest.fail("authoritative recipe reader used unbounded read_text")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(service_module, "check_import_resource_preflight", _check)
    monkeypatch.setattr(Path, "read_text", _guarded_read_text)

    with pytest.raises(PreconditionError) as raised:
        service.handle_reload_interpretation_recipe(
            ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path)),
        )

    diagnostics = raised.value.diagnostics["recipe_input"]
    assert diagnostics["risk_level"] == "blocking"
    assert diagnostics["file_bytes_at_least"] == (
        service_module.IMPORT_RECIPE_MAX_BYTES + 1
    )
    assert diagnostics["max_bytes"] == service_module.IMPORT_RECIPE_MAX_BYTES
    assert admission_calls == 1
    assert service.snapshot().has_scan_result is False


def test_reload_recipe_reader_blocks_same_size_rewrite_during_parse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = tmp_path / "subject.fif"
    eeg_path.write_bytes(b"header only")
    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_text(
        json.dumps(
            {
                "recipe_id": "recipe-a",
                "interpretation_id": "interpretation-1",
                "source_path": str(eeg_path),
                "source_kind": "file",
                "selected_eeg_files": [str(eeg_path)],
                "skip_labels": True,
            },
        ),
        encoding="utf-8",
    )
    service, _dataset = _service()
    original_loader = service_module.load_import_recipe

    def _rewrite_then_load(path: str):
        original = recipe_path.read_text(encoding="utf-8")
        rewritten = original.replace("recipe-a", "recipe-b")
        assert len(rewritten.encode("utf-8")) == len(original.encode("utf-8"))
        replacement = recipe_path.with_suffix(".replacement.json")
        replacement.write_text(rewritten, encoding="utf-8")
        replacement.replace(recipe_path)
        return original_loader(path)

    monkeypatch.setattr(service_module, "load_import_recipe", _rewrite_then_load)

    with pytest.raises(PreconditionError) as raised:
        service.handle_reload_interpretation_recipe(
            ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path)),
        )

    diagnostics = raised.value.diagnostics
    assert diagnostics["code"] == "interpretation_resource_changed_after_admission"
    assert diagnostics["purpose"] == "import recipe reload"
    assert diagnostics["parse_started"] is True
    assert service.snapshot().has_scan_result is False


def test_apply_interpretation_imports_only_preview_selected_eeg_files(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    selected_eeg = source_dir / "selected.fif"
    sibling_eeg = source_dir / "sibling.fif"
    selected_eeg.write_bytes(b"not loaded during scan")
    sibling_eeg.write_bytes(b"must not be imported by selected preview")
    service, dataset = _service()

    _scan_message, scan_payload = _expect_payload(
        service.handle_scan_source(ScanSourceCommand(source_path=str(source_dir))),
    )
    _preview_message, preview_payload = _expect_payload(
        service.handle_preview_interpretation(
            PreviewInterpretationCommand(
                choices={"selected_eeg_files": [str(selected_eeg.resolve())]},
            ),
        ),
    )
    _validation_message, validation_payload = _expect_payload(
        service.handle_validate_interpretation(ValidateInterpretationCommand()),
    )
    _apply_message, apply_payload = _expect_payload(
        service.handle_apply_interpretation(ApplyInterpretationCommand(confirmed=True)),
    )

    assert sorted(scan_payload["scan_result"]["eeg_files"]) == [
        str(selected_eeg.resolve()),
        str(sibling_eeg.resolve()),
    ]
    assert preview_payload["candidate"]["selected_eeg_files"] == [
        str(selected_eeg.resolve()),
    ]
    assert preview_payload["preview"]["selected_eeg_files"] == [
        str(selected_eeg.resolve()),
    ]
    assert validation_payload["validation_decision"]["decision"] == (
        "needs_confirmation"
    )
    assert dataset.imported_paths == [str(selected_eeg.resolve())]
    assert apply_payload["success_count"] == 1
    assert apply_payload["applied_interpretation"]["loaded_files"] == [
        str(selected_eeg.resolve()),
    ]


def test_apply_interpretation_requires_resource_confirmation_before_mutation(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    selected_eeg = source_dir / "selected.fif"
    selected_eeg.write_bytes(b"not loaded during scan")
    service, dataset = _service()
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 2_000_000)

    service.handle_scan_source(ScanSourceCommand(source_path=str(selected_eeg)))
    with pytest.raises(
        resource_guard.ResourceConfirmationRequiredError
    ) as preview_gate:
        service.handle_preview_interpretation(
            PreviewInterpretationCommand(
                choices={"selected_eeg_files": [str(selected_eeg)]},
            ),
        )
    preview_token = _resource_challenge(preview_gate.value)["challenge_id"]
    service.handle_preview_interpretation(
        PreviewInterpretationCommand(
            choices={"selected_eeg_files": [str(selected_eeg)]},
            resource_preflight_confirmed=True,
            resource_preflight_token=preview_token,
        ),
    )
    service.handle_validate_interpretation(ValidateInterpretationCommand())

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as raised:
        service.handle_apply_interpretation(
            ApplyInterpretationCommand(confirmed=True),
        )

    assert raised.value.diagnostics["resource_preflight"]["risk_level"] == "warning"
    assert dataset.imported_paths == []
    assert dataset.clean_count == 0
    token = raised.value.diagnostics["resource_preflight"]["confirmation_token"]

    _message, payload = _expect_payload(
        service.handle_apply_interpretation(
            ApplyInterpretationCommand(
                confirmed=True,
                resource_preflight_confirmed=True,
                resource_preflight_token=token,
            ),
        ),
    )

    assert dataset.imported_paths == [str(selected_eeg.resolve())]
    assert payload["resource_preflight"]["risk_level"] == "warning"


def test_apply_warning_confirmation_rechecks_current_preflight_before_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_eeg = tmp_path / "selected.fif"
    selected_eeg.write_bytes(b"reviewed EEG scope")
    service, dataset = _service()
    service.handle_scan_source(ScanSourceCommand(source_path=str(selected_eeg)))
    service.handle_preview_interpretation(PreviewInterpretationCommand())
    service.handle_validate_interpretation(ValidateInterpretationCommand())
    calls: list[tuple[str, ...]] = []

    def _check(paths: list[str]) -> ResourcePreflightResult:
        calls.append(tuple(paths))
        return _resource_preflight("warning")

    monkeypatch.setattr(
        "XBrainLab.backend.application.data_interpretation_service.check_import_resource_preflight",
        _check,
    )

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as raised:
        service.handle_apply_interpretation(
            ApplyInterpretationCommand(confirmed=True),
        )

    diagnostics = raised.value.diagnostics["resource_preflight"]
    token = diagnostics["confirmation_token"]
    assert token
    assert diagnostics["candidate_id"]
    assert dataset.imported_paths == []

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as missing:
        service.handle_apply_interpretation(
            ApplyInterpretationCommand(
                confirmed=True,
                resource_preflight_confirmed=True,
            ),
        )

    assert (
        missing.value.diagnostics["resource_preflight"]["confirmation_token"] == token
    )
    assert dataset.imported_paths == []

    _message, payload = _expect_payload(
        service.handle_apply_interpretation(
            ApplyInterpretationCommand(
                confirmed=True,
                resource_preflight_confirmed=True,
                resource_preflight_token=token,
            ),
        ),
    )

    assert len(calls) == 3
    assert dataset.imported_paths == [str(selected_eeg.resolve())]
    assert payload["resource_preflight"]["confirmation_receipt_reused"] is True


def test_apply_warning_receipt_cannot_bypass_new_blocking_ram_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_eeg = tmp_path / "selected.fif"
    selected_eeg.write_bytes(b"reviewed EEG scope")
    service, dataset = _service()
    service.handle_scan_source(ScanSourceCommand(source_path=str(selected_eeg)))
    service.handle_preview_interpretation(PreviewInterpretationCommand())
    service.handle_validate_interpretation(ValidateInterpretationCommand())
    preflights = iter((_resource_preflight("warning"), _resource_preflight("blocking")))
    monkeypatch.setattr(
        "XBrainLab.backend.application.data_interpretation_service.check_import_resource_preflight",
        lambda _paths: next(preflights),
    )

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as raised:
        service.handle_apply_interpretation(ApplyInterpretationCommand(confirmed=True))
    token = raised.value.diagnostics["resource_preflight"]["confirmation_token"]

    with pytest.raises(PreconditionError, match="resource risk: blocking"):
        service.handle_apply_interpretation(
            ApplyInterpretationCommand(
                confirmed=True,
                resource_preflight_confirmed=True,
                resource_preflight_token=token,
            )
        )

    assert dataset.imported_paths == []
    assert dataset.clean_count == 0


def test_apply_resource_receipt_is_invalidated_when_file_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_eeg = tmp_path / "selected.fif"
    selected_eeg.write_bytes(b"before")
    service, dataset = _service()
    service.handle_scan_source(ScanSourceCommand(source_path=str(selected_eeg)))
    service.handle_preview_interpretation(PreviewInterpretationCommand())
    service.handle_validate_interpretation(ValidateInterpretationCommand())
    calls = 0

    def _check(paths: list[str]) -> ResourcePreflightResult:
        nonlocal calls
        calls += 1
        return _resource_preflight("warning", paths)

    monkeypatch.setattr(
        "XBrainLab.backend.application.data_interpretation_service.check_import_resource_preflight",
        _check,
    )
    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as raised:
        service.handle_apply_interpretation(ApplyInterpretationCommand(confirmed=True))
    stale_token = raised.value.diagnostics["resource_preflight"]["confirmation_token"]

    selected_eeg.write_bytes(b"after: changed file size invalidates the receipt")

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as refreshed:
        service.handle_apply_interpretation(
            ApplyInterpretationCommand(
                confirmed=True,
                resource_preflight_confirmed=True,
                resource_preflight_token=stale_token,
            ),
        )

    assert calls == 2
    assert dataset.imported_paths == []
    assert (
        refreshed.value.diagnostics["resource_preflight"]["confirmation_token"]
        != stale_token
    )


def test_apply_resource_receipt_is_invalidated_after_ttl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_eeg = tmp_path / "selected.fif"
    selected_eeg.write_bytes(b"reviewed EEG scope")
    service, dataset = _service()
    service.handle_scan_source(ScanSourceCommand(source_path=str(selected_eeg)))
    service.handle_preview_interpretation(PreviewInterpretationCommand())
    service.handle_validate_interpretation(ValidateInterpretationCommand())
    calls = 0
    monotonic_now = 100.0

    def _check(_paths: list[str]) -> ResourcePreflightResult:
        nonlocal calls
        calls += 1
        return _resource_preflight("warning")

    monkeypatch.setattr(
        "XBrainLab.backend.application.data_interpretation_service.check_import_resource_preflight",
        _check,
    )
    monkeypatch.setattr(service_module.time, "monotonic", lambda: monotonic_now)

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as raised:
        service.handle_apply_interpretation(ApplyInterpretationCommand(confirmed=True))
    stale_token = raised.value.diagnostics["resource_preflight"]["confirmation_token"]

    monotonic_now += service_module.IMPORT_PREFLIGHT_RECEIPT_TTL_SECONDS + 1.0

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as refreshed:
        service.handle_apply_interpretation(
            ApplyInterpretationCommand(
                confirmed=True,
                resource_preflight_confirmed=True,
                resource_preflight_token=stale_token,
            ),
        )

    assert calls == 2
    assert dataset.imported_paths == []
    assert (
        refreshed.value.diagnostics["resource_preflight"]["confirmation_token"]
        != stale_token
    )


def test_apply_resource_receipt_is_invalidated_when_selected_scope_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_eeg = tmp_path / "first.fif"
    second_eeg = tmp_path / "second.fif"
    first_eeg.write_bytes(b"first")
    second_eeg.write_bytes(b"second")
    service, dataset = _service()
    service.handle_scan_source(ScanSourceCommand(source_path=str(tmp_path)))
    service.handle_preview_interpretation(
        PreviewInterpretationCommand(
            choices={"selected_eeg_files": [str(first_eeg)]},
        ),
    )
    service.handle_validate_interpretation(ValidateInterpretationCommand())
    calls = 0

    def _check(paths: list[str]) -> ResourcePreflightResult:
        nonlocal calls
        calls += 1
        return _resource_preflight("warning", paths)

    monkeypatch.setattr(
        "XBrainLab.backend.application.data_interpretation_service.check_import_resource_preflight",
        _check,
    )
    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as raised:
        service.handle_apply_interpretation(ApplyInterpretationCommand(confirmed=True))
    first_token = raised.value.diagnostics["resource_preflight"]["confirmation_token"]

    with pytest.raises(
        resource_guard.ResourceConfirmationRequiredError
    ) as preview_gate:
        service.handle_preview_interpretation(
            PreviewInterpretationCommand(
                choices={"selected_eeg_files": [str(second_eeg)]},
            ),
        )
    preview_token = _resource_challenge(preview_gate.value)["challenge_id"]
    _message, preview = _expect_payload(
        service.handle_preview_interpretation(
            PreviewInterpretationCommand(
                choices={"selected_eeg_files": [str(second_eeg)]},
                resource_preflight_confirmed=True,
                resource_preflight_token=preview_token,
            ),
        )
    )
    second_candidate_id = preview["candidate"]["candidate_id"]
    service.handle_validate_interpretation(
        ValidateInterpretationCommand(candidate_id=second_candidate_id),
    )

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as refreshed:
        service.handle_apply_interpretation(
            ApplyInterpretationCommand(
                candidate_id=second_candidate_id,
                confirmed=True,
                resource_preflight_confirmed=True,
                resource_preflight_token=first_token,
            ),
        )

    assert calls == 4
    assert dataset.imported_paths == []
    refreshed_diagnostics = refreshed.value.diagnostics["resource_preflight"]
    assert refreshed_diagnostics["candidate_id"] == second_candidate_id
    assert refreshed_diagnostics["confirmation_token"] != first_token


def test_apply_blocking_resource_preflight_never_mutates_dataset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_eeg = tmp_path / "selected.fif"
    selected_eeg.write_bytes(b"reviewed EEG scope")
    service, dataset = _service()
    service.handle_scan_source(ScanSourceCommand(source_path=str(selected_eeg)))
    service.handle_preview_interpretation(PreviewInterpretationCommand())
    service.handle_validate_interpretation(ValidateInterpretationCommand())
    calls = 0

    def _check(_paths: list[str]) -> ResourcePreflightResult:
        nonlocal calls
        calls += 1
        return _resource_preflight("blocking")

    monkeypatch.setattr(
        "XBrainLab.backend.application.data_interpretation_service.check_import_resource_preflight",
        _check,
    )

    with pytest.raises(PreconditionError, match="resource risk: blocking"):
        service.handle_apply_interpretation(
            ApplyInterpretationCommand(
                confirmed=True,
                resource_preflight_confirmed=True,
            ),
        )

    assert calls == 1
    assert dataset.imported_paths == []
    assert dataset.clean_count == 0


def test_apply_resource_preflight_includes_external_label_carriers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = tmp_path / "subject.fif"
    label_path = tmp_path / "subject_events.tsv"
    eeg_path.write_bytes(b"reviewed EEG scope")
    label_path.write_text("onset\ttrial_type\n0\tleft\n", encoding="utf-8")
    service, dataset = _service()
    service.handle_scan_source(ScanSourceCommand(source_path=str(eeg_path)))
    service.handle_preview_interpretation(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_path): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "time_model": "seconds",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions({"left": "left"}),
                    }
                }
            }
        )
    )
    service.handle_validate_interpretation(ValidateInterpretationCommand())
    checked_scopes: list[tuple[str, ...]] = []

    def _check(paths: list[str]) -> ResourcePreflightResult:
        checked_scopes.append(tuple(paths))
        return _resource_preflight("blocking")

    monkeypatch.setattr(
        "XBrainLab.backend.application.data_interpretation_service.check_import_resource_preflight",
        _check,
    )

    with pytest.raises(PreconditionError):
        service.handle_apply_interpretation(
            ApplyInterpretationCommand(confirmed=True),
        )

    assert len(checked_scopes) == 1
    assert_filesystem_path_lists_equal(
        checked_scopes[0],
        [eeg_path, label_path],
    )
    assert dataset.imported_paths == []


@pytest.mark.parametrize(
    "resource_kind",
    [
        "selected_eeg",
        "brainvision_data",
        "brainvision_markers",
        "eeglab_fdt",
    ],
)
@pytest.mark.parametrize("entrypoint", ["preview", "review"])
def test_apply_blocks_exact_candidate_when_reviewed_eeg_or_parser_dependency_changes_before_load(
    tmp_path: Path,
    resource_kind: str,
    entrypoint: str,
) -> None:
    selected_eeg, mutation_target = _integrity_fixture(tmp_path, resource_kind)
    service, dataset = _service()
    candidate_id = _review_integrity_candidate(
        service,
        selected_eeg=selected_eeg,
        entrypoint=entrypoint,
    )
    import_calls = 0
    original_import = dataset.import_files

    def _observed_import(paths: list[str]) -> tuple[int, list[str]]:
        nonlocal import_calls
        import_calls += 1
        return original_import(paths)

    dataset.import_files = _observed_import  # type: ignore[method-assign]
    _mutate_same_size(mutation_target)

    with pytest.raises(PreconditionError, match="changed after preview") as raised:
        service.handle_apply_interpretation(
            ApplyInterpretationCommand(
                candidate_id=candidate_id,
                confirmed=True,
            )
        )

    assert raised.value.diagnostics["candidate_id"] == candidate_id
    assert_filesystem_path_lists_equal(
        raised.value.diagnostics["changed_paths"],
        [mutation_target],
    )
    assert import_calls == 0
    assert dataset.imported_paths == []
    assert dataset.clean_count == 0


@pytest.mark.parametrize(
    "resource_kind",
    [
        "selected_eeg",
        "brainvision_data",
        "brainvision_markers",
        "eeglab_fdt",
    ],
)
@pytest.mark.parametrize("entrypoint", ["preview", "review"])
def test_apply_rolls_back_exact_candidate_when_reviewed_eeg_or_parser_dependency_changes_after_load(
    tmp_path: Path,
    resource_kind: str,
    entrypoint: str,
) -> None:
    selected_eeg, mutation_target = _integrity_fixture(tmp_path, resource_kind)
    service, dataset = _service()
    candidate_id = _review_integrity_candidate(
        service,
        selected_eeg=selected_eeg,
        entrypoint=entrypoint,
    )
    import_calls = 0
    original_import = dataset.import_files

    def _import_then_mutate(paths: list[str]) -> tuple[int, list[str]]:
        nonlocal import_calls
        import_calls += 1
        result = original_import(paths)
        _mutate_same_size(mutation_target)
        return result

    dataset.import_files = _import_then_mutate  # type: ignore[method-assign]

    with pytest.raises(PreconditionError, match="changed after preview") as raised:
        service.handle_apply_interpretation(
            ApplyInterpretationCommand(
                candidate_id=candidate_id,
                confirmed=True,
            )
        )

    assert raised.value.diagnostics["candidate_id"] == candidate_id
    assert_filesystem_path_lists_equal(
        raised.value.diagnostics["changed_paths"],
        [mutation_target],
    )
    assert import_calls == 1
    assert dataset.imported_paths == []
    assert dataset.loaded == []
    assert service.snapshot().has_applied_interpretation is False


def test_apply_fails_closed_when_reviewed_external_label_content_changes(
    tmp_path: Path,
) -> None:
    eeg_path = tmp_path / "subject.fif"
    label_path = tmp_path / "subject_labels.csv"
    eeg_path.write_bytes(b"reviewed EEG scope")
    label_path.write_text(
        "event_code,label\n1,left\n",
        encoding="utf-8",
    )
    reviewed_size = label_path.stat().st_size
    service, dataset = _service()

    service.handle_scan_source(
        ScanSourceCommand(
            source_path=str(eeg_path),
            label_sources=[str(label_path)],
        )
    )
    _preview_message, preview_payload = _expect_payload(
        service.handle_preview_interpretation(
            PreviewInterpretationCommand(
                choices={
                    "label_carrier_choices": {
                        str(label_path): {
                            "label_field": "label",
                            "anchor": "event_code",
                            "placement_method": "event_code",
                            "role": "class labels",
                        }
                    }
                }
            )
        )
    )
    service.handle_validate_interpretation(ValidateInterpretationCommand())

    identity = preview_payload["preview"]["content_identity"]
    assert identity["version"] == 3
    assert identity["algorithm"] == "sha256"
    assert identity["scope_sha256"]
    [binding] = identity["bindings"]
    assert_filesystem_paths_equal(binding["path"], label_path)
    assert binding["format"] == "CSV"
    assert binding["selected_label_field"] == "label"
    assert binding["selected_anchor"] == "event_code"
    assert binding["placement_method"] == "event_code"
    assert binding["run_class_map"] == {"left": "left"}
    assert binding["value_decisions"]["left"]["decision"] == "resolved"
    files_by_role = {row["role"]: row for row in identity["files"]}
    assert_filesystem_paths_equal(files_by_role["selected_eeg"]["path"], eeg_path)
    assert files_by_role["selected_eeg"]["file_bytes"] == eeg_path.stat().st_size
    assert files_by_role["selected_eeg"]["sha256"]
    assert_filesystem_paths_equal(
        files_by_role["label_carrier"]["path"],
        label_path,
    )
    assert files_by_role["label_carrier"]["file_bytes"] == reviewed_size
    assert files_by_role["label_carrier"]["sha256"]

    label_path.write_text(
        "event_code,label\n1,foot\n",
        encoding="utf-8",
    )
    assert label_path.stat().st_size == reviewed_size

    with pytest.raises(PreconditionError, match="changed after preview") as raised:
        service.handle_apply_interpretation(
            ApplyInterpretationCommand(confirmed=True),
        )

    assert raised.value.diagnostics["code"] == (
        "interpretation_content_changed_after_review"
    )
    assert_filesystem_path_lists_equal(
        raised.value.diagnostics["changed_paths"],
        [label_path],
    )
    assert raised.value.diagnostics["next_action"] == "preview_and_review_again"
    assert dataset.imported_paths == []
    assert dataset.clean_count == 0


def test_validate_blocks_when_label_content_changes_after_preview(
    tmp_path: Path,
) -> None:
    eeg_path = tmp_path / "subject.fif"
    label_path = tmp_path / "subject_labels.csv"
    eeg_path.write_bytes(b"reviewed EEG scope")
    label_path.write_text("event_code,label\n1,left\n", encoding="utf-8")
    service, _dataset = _service()

    service.handle_scan_source(
        ScanSourceCommand(
            source_path=str(eeg_path),
            label_sources=[str(label_path)],
        )
    )
    service.handle_preview_interpretation(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_path): {
                        "label_field": "label",
                        "anchor": "event_code",
                        "placement_method": "event_code",
                        "role": "class labels",
                    }
                }
            }
        )
    )
    label_path.write_text("event_code,label\n1,foot\n", encoding="utf-8")

    _message, payload = _expect_payload(
        service.handle_validate_interpretation(ValidateInterpretationCommand())
    )

    decision = payload["validation_decision"]
    assert decision["decision"] == "blocked"
    assert any("changed after preview" in item for item in decision["blocked_reasons"])
    assert any(
        item["severity"] == "blocked"
        and item["target_step"] == "Load Labels"
        and "Preview and review" in item["next_action"]
        for item in decision["action_items"]
    )


def test_apply_rolls_back_when_label_content_changes_during_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = tmp_path / "subject.fif"
    label_path = tmp_path / "subject_labels.csv"
    eeg_path.write_bytes(b"reviewed EEG scope")
    label_path.write_text("event_code,label\n1,left\n", encoding="utf-8")
    service, dataset = _service()

    service.handle_scan_source(
        ScanSourceCommand(
            source_path=str(eeg_path),
            label_sources=[str(label_path)],
        )
    )
    service.handle_preview_interpretation(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_path): {
                        "label_field": "label",
                        "anchor": "event_code",
                        "placement_method": "event_code",
                        "role": "class labels",
                    }
                }
            }
        )
    )
    service.handle_validate_interpretation(ValidateInterpretationCommand())

    def _mutate_after_label_read(
        _candidate: Any,
        _label_resources: Any,
    ) -> dict[str, Any]:
        label_path.write_text("event_code,label\n1,foot\n", encoding="utf-8")
        return {"status": "applied", "success_count": 1}

    monkeypatch.setattr(
        service.apply_service,
        "apply_label_carriers",
        _mutate_after_label_read,
    )

    with pytest.raises(PreconditionError, match="changed after preview"):
        service.handle_apply_interpretation(
            ApplyInterpretationCommand(confirmed=True),
        )

    assert dataset.imported_paths == []
    assert dataset.loaded == []
    assert service.snapshot().has_applied_interpretation is False


def test_apply_interpretation_replaces_active_raw_data(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    selected_eeg = source_dir / "selected.fif"
    selected_eeg.write_bytes(b"not loaded during scan")
    service, dataset = _service()
    dataset.loaded = [_LoadedData(str(tmp_path / "old_raw.fif"))]
    dataset.imported_paths = [str(tmp_path / "old_raw.fif")]

    service.handle_scan_source(ScanSourceCommand(source_path=str(source_dir)))
    service.handle_preview_interpretation(
        PreviewInterpretationCommand(
            choices={"selected_eeg_files": [str(selected_eeg.resolve())]},
        ),
    )
    service.handle_validate_interpretation(ValidateInterpretationCommand())
    _apply_message, apply_payload = _expect_payload(
        service.handle_apply_interpretation(ApplyInterpretationCommand(confirmed=True)),
    )

    assert dataset.clean_count == 1
    assert dataset.imported_paths == [str(selected_eeg.resolve())]
    assert [item.filepath for item in dataset.loaded] == [str(selected_eeg.resolve())]
    assert apply_payload["success_count"] == 1


def test_apply_interpretation_requires_confirmation_when_replacing_raw_data(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    selected_eeg = source_dir / "selected.fif"
    selected_eeg.write_bytes(b"not loaded during scan")
    service, dataset = _service()
    dataset.loaded = [_LoadedData(str(tmp_path / "old_raw.fif"))]

    service.handle_scan_source(ScanSourceCommand(source_path=str(source_dir)))
    service.handle_preview_interpretation(
        PreviewInterpretationCommand(
            choices={"selected_eeg_files": [str(selected_eeg.resolve())]},
        ),
    )
    service.handle_validate_interpretation(ValidateInterpretationCommand())

    with pytest.raises(ConfirmationRequiredError, match="replacing"):
        service.handle_apply_interpretation(ApplyInterpretationCommand())

    assert [item.filepath for item in dataset.loaded] == [str(tmp_path / "old_raw.fif")]
    assert dataset.imported_paths == []


def test_apply_interpretation_rolls_back_partial_import_failure(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    good_eeg = source_dir / "good.fif"
    bad_eeg = source_dir / "bad.fif"
    good_eeg.write_bytes(b"not loaded during scan")
    bad_eeg.write_bytes(b"not loaded during scan")
    service, dataset = _service()
    old_path = str(tmp_path / "old_raw.fif")
    dataset.loaded = [_LoadedData(old_path)]
    dataset.imported_paths = [old_path]

    def partial_import(paths: list[str]) -> tuple[int, list[str]]:
        dataset.imported_paths = [paths[0]]
        dataset.loaded = [_LoadedData(paths[0])]
        return 1, [f"{paths[1]}: bad file"]

    dataset.import_files = partial_import  # type: ignore[method-assign]

    service.handle_scan_source(ScanSourceCommand(source_path=str(source_dir)))
    service.handle_preview_interpretation(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [
                    str(good_eeg.resolve()),
                    str(bad_eeg.resolve()),
                ],
            },
        ),
    )
    service.handle_validate_interpretation(ValidateInterpretationCommand())

    with pytest.raises(ApplicationError, match="loaded 1/2"):
        service.handle_apply_interpretation(
            ApplyInterpretationCommand(confirmed=True),
        )

    assert [item.filepath for item in dataset.loaded] == [old_path]
    assert dataset.imported_paths == [old_path]
    assert service.state.snapshot().has_applied_interpretation is False


def test_confirmation_cannot_apply_unresolved_sequence_label_target(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    eeg_path = source_dir / "selected.fif"
    label_path = source_dir / "labels.csv"
    eeg_path.write_bytes(b"not loaded during scan")
    label_path.write_text("label\n1\n2\n", encoding="utf-8")
    service, dataset = _service()
    old_path = str(tmp_path / "old_raw.fif")
    dataset.loaded = [_LoadedData(old_path)]
    dataset.imported_paths = [old_path]

    service.handle_scan_source(ScanSourceCommand(source_path=str(source_dir)))
    _preview_message, preview_payload = _expect_payload(
        service.handle_preview_interpretation(
            PreviewInterpretationCommand(
                choices={
                    "label_carrier_choices": {
                        str(label_path): {
                            "label_field": "label",
                            "role": "class labels",
                        }
                    }
                }
            )
        )
    )
    _validation_message, validation_payload = _expect_payload(
        service.handle_validate_interpretation(ValidateInterpretationCommand())
    )

    [carrier] = preview_payload["candidate"]["label_carrier_plan"]
    assert carrier["placement_review"]["status"] == "blocked"
    assert validation_payload["validation_decision"]["decision"] == "blocked"
    with pytest.raises(PreconditionError, match="explicit target EEG event"):
        service.handle_apply_interpretation(
            ApplyInterpretationCommand(confirmed=True),
        )

    assert [item.filepath for item in dataset.loaded] == [old_path]
    assert dataset.imported_paths == [old_path]
    assert dataset.clean_count == 0
    assert service.state.snapshot().has_applied_interpretation is False


def test_confirmation_cannot_apply_sequence_placement_that_needs_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scipy.io import savemat

    eeg_path = tmp_path / "A01T.gdf"
    label_path = tmp_path / "A01T.mat"
    eeg_path.write_bytes(b"reviewed EEG scope")
    savemat(label_path, {"classlabel": [1, 2]})
    monkeypatch.setattr(
        data_interpretation_internal_events,
        "_read_internal_events_for_file",
        lambda _path: {"events": {"768": {"count": 3, "description": "trial start"}}},
    )
    service, dataset = _service()

    service.handle_scan_source(ScanSourceCommand(source_path=str(tmp_path)))
    _preview_message, preview_payload = _expect_payload(
        service.handle_preview_interpretation(
            PreviewInterpretationCommand(
                choices={
                    "label_carrier_choices": {
                        str(label_path): {
                            "label_field": "classlabel",
                            "target_event_codes": ["768"],
                            "placement_method": "eeg_event",
                            "time_model": "trial_order",
                            "granularity": "trial",
                            "value_decisions": _class_value_decisions(
                                {"1": "left", "2": "right"}
                            ),
                        }
                    }
                }
            )
        )
    )
    _validation_message, validation_payload = _expect_payload(
        service.handle_validate_interpretation(ValidateInterpretationCommand())
    )

    [carrier] = preview_payload["candidate"]["label_carrier_plan"]
    assert carrier["placement_review"]["status"] == "needs_review"
    assert validation_payload["validation_decision"]["decision"] == "blocked"
    with pytest.raises(PreconditionError, match="selected EEG event has no label"):
        service.handle_apply_interpretation(
            ApplyInterpretationCommand(confirmed=True),
        )

    assert dataset.imported_paths == []
    assert dataset.clean_count == 0
    assert service.state.snapshot().has_applied_interpretation is False


def test_apply_interpretation_requires_target_candidate_confirmation(
    tmp_path: Path,
) -> None:
    confirm_dir = tmp_path / "needs_confirmation"
    safe_dir = tmp_path / "safe"
    confirm_dir.mkdir()
    safe_dir.mkdir()
    confirm_eeg = confirm_dir / "recording_raw.fif"
    confirm_events = confirm_dir / "recording_events.tsv"
    safe_eeg = safe_dir / "sub-02_task-mi_raw.fif"
    confirm_eeg.write_bytes(b"not loaded during scan")
    confirm_events.write_text("onset\ttrial_type\n0.0\tleft\n", encoding="utf-8")
    safe_eeg.write_bytes(b"not loaded during scan")
    service, _dataset = _service()

    service.handle_scan_source(ScanSourceCommand(source_path=str(confirm_dir)))
    _preview_message, preview_payload = _expect_payload(
        service.handle_preview_interpretation(
            PreviewInterpretationCommand(
                choices={
                    "label_carrier_choices": {
                        str(confirm_events): {
                            "label_field": "trial_type",
                            "anchor": "onset",
                            "time_model": "seconds",
                            "granularity": "trial",
                            "value_decisions": _class_value_decisions({"left": "left"}),
                        }
                    }
                }
            )
        ),
    )
    needs_confirmation_candidate_id = preview_payload["candidate"]["candidate_id"]
    _validation_message, validation_payload = _expect_payload(
        service.handle_validate_interpretation(ValidateInterpretationCommand()),
    )
    assert validation_payload["validation_decision"]["decision"] == (
        "needs_confirmation"
    )
    assert any(
        "subject metadata" in item
        for item in validation_payload["validation_decision"]["required_confirmations"]
    )
    service.handle_scan_source(ScanSourceCommand(source_path=str(safe_dir)))
    service.handle_preview_interpretation(
        PreviewInterpretationCommand(
            choices={
                "metadata_overrides": {
                    safe_eeg.name: {
                        "subject": "02",
                        "session": "01",
                        "task": "mi",
                        "run": "1",
                    },
                },
            },
        ),
    )
    _validation_message, safe_validation_payload = _expect_payload(
        service.handle_validate_interpretation(ValidateInterpretationCommand()),
    )
    assert safe_validation_payload["validation_decision"]["decision"] == "safe"

    with pytest.raises(ConfirmationRequiredError):
        service.handle_apply_interpretation(
            ApplyInterpretationCommand(
                candidate_id=needs_confirmation_candidate_id,
                confirmed=False,
            ),
        )


def test_apply_interpretation_from_single_file_source_uses_preview_selected_file_only(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    selected_eeg = source_dir / "selected.fif"
    sibling_eeg = source_dir / "sibling.fif"
    selected_eeg.write_bytes(b"not loaded during scan")
    sibling_eeg.write_bytes(b"should not be imported")
    service, dataset = _service()

    _scan_message, scan_payload = _expect_payload(
        service.handle_scan_source(ScanSourceCommand(source_path=str(selected_eeg))),
    )
    _preview_message, preview_payload = _expect_payload(
        service.handle_preview_interpretation(
            PreviewInterpretationCommand(
                choices={"selected_eeg_files": [str(selected_eeg)]},
            ),
        ),
    )
    _validation_message, validation_payload = _expect_payload(
        service.handle_validate_interpretation(ValidateInterpretationCommand()),
    )
    _apply_message, apply_payload = _expect_payload(
        service.handle_apply_interpretation(ApplyInterpretationCommand(confirmed=True)),
    )

    assert scan_payload["payload_type"] == "scan_result"
    assert scan_payload["scan_result"]["source_path"] == str(selected_eeg.resolve())
    assert scan_payload["scan_result"]["source_kind"] == "file"
    assert scan_payload["scan_result"]["eeg_files"] == [str(selected_eeg.resolve())]
    assert (
        sibling_eeg.resolve().as_posix() not in scan_payload["scan_result"]["eeg_files"]
    )
    assert preview_payload["candidate"]["selected_eeg_files"] == [
        str(selected_eeg.resolve())
    ]
    assert preview_payload["preview"]["selected_eeg_files"] == [
        str(selected_eeg.resolve())
    ]
    assert validation_payload["validation_decision"]["decision"] == (
        "needs_confirmation"
    )
    assert dataset.imported_paths == [str(selected_eeg.resolve())]
    assert apply_payload["success_count"] == 1
    assert apply_payload["applied_interpretation"]["loaded_files"] == [
        str(selected_eeg.resolve())
    ]
    [source_identity] = apply_payload["source_identity_apply"]
    assert source_identity["file"] == selected_eeg.name
    assert source_identity["algorithm"] == "sha256"
    assert (
        source_identity["sha256"]
        == (preview_payload["preview"]["content_identity"]["files"][0]["sha256"])
    )
    assert dataset.loaded[0].runtime_details["source_content_identity"] == {
        "algorithm": "sha256",
        "sha256": source_identity["sha256"],
        "file_bytes": selected_eeg.stat().st_size,
    }


def test_apply_metadata_and_label_import_recipe_state_stay_together(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "metadata_source"
    source_dir.mkdir()
    eeg_path = source_dir / "subject01_run1.fif"
    label_path = tmp_path / "subject01_run1_events.tsv"
    recipe_path = tmp_path / "recipe.json"
    eeg_path.write_bytes(b"not loaded during scan")
    label_path.write_text("onset\ttrial_type\n0.0\tleft\n", encoding="utf-8")
    service, dataset = _service()

    service.handle_scan_source(ScanSourceCommand(source_path=str(source_dir)))
    service.handle_preview_interpretation(
        PreviewInterpretationCommand(
            choices={
                "metadata_overrides": {
                    eeg_path.name: {
                        "subject": "S01",
                        "session": "session-01",
                        "task": "motor-imagery",
                        "run": "1",
                    },
                },
            },
        ),
    )
    service.handle_validate_interpretation(ValidateInterpretationCommand())
    _apply_message, apply_payload = _expect_payload(
        service.handle_apply_interpretation(ApplyInterpretationCommand(confirmed=True)),
    )
    service.handle_save_interpretation_recipe(
        SaveInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )
    loaded = dataset.loaded[0]
    plan = LabelImportPlan(
        target_indices=[0],
        label_paths=[str(label_path)],
        mapping={"left": "left hand"},
        file_mapping={str(eeg_path): str(label_path)},
        mode="timestamp",
    )
    record = service.record_label_import_for_recipe(
        plan=plan,
        mode="timestamp",
        target_files=[loaded],
        file_mapping={str(eeg_path): str(label_path)},
        selected_event_names=None,
        success_count=1,
    )
    snapshot = service.snapshot()

    assert apply_payload["metadata_apply"] == [
        {
            "file": eeg_path.name,
            "subject": "S01",
            "session": "session-01",
            "task": "motor-imagery",
            "run": "1",
        }
    ]
    assert loaded.subject == "S01"
    assert loaded.session == "session-01"
    assert loaded.runtime_details["data_interpretation_metadata"]["task"] == (
        "motor-imagery"
    )
    assert dataset.notifications == []
    assert record is not None
    assert record["mode"] == "timestamp"
    assert snapshot.has_applied_interpretation is True
    assert snapshot.has_recipe is True
    assert snapshot.label_import_count == 1
    assert snapshot.label_imports[0]["class_map"] == {"left": "left hand"}


def test_repeated_safe_preview_reuses_admission_after_identity_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = tmp_path / "sub-01_task-mi_raw.fif"
    eeg_path.write_bytes(b"stable EEG header")
    service, _dataset = _service()
    service.handle_scan_source(ScanSourceCommand(source_path=str(eeg_path)))
    choices = {"selected_eeg_files": [str(eeg_path.resolve())]}
    service.handle_preview_interpretation(PreviewInterpretationCommand(choices=choices))
    original_check = service_module.check_import_resource_preflight
    checks = 0

    def _counted_check(paths: list[str]) -> ResourcePreflightResult:
        nonlocal checks
        checks += 1
        return original_check(paths)

    monkeypatch.setattr(
        service_module,
        "check_import_resource_preflight",
        _counted_check,
    )
    _message, payload = _expect_payload(
        service.handle_preview_interpretation(
            PreviewInterpretationCommand(choices=choices)
        )
    )

    assert checks == 0
    assert payload["resource_preflight"]["admission_cache_reused"] is True


def test_first_safe_preview_reuses_matching_scan_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bids_root = tmp_path / "bids"
    eeg_dir = bids_root / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    (bids_root / "dataset_description.json").write_text(
        json.dumps({"Name": "Preview cache", "BIDSVersion": "1.9.0"}),
        encoding="utf-8",
    )
    eeg_path = eeg_dir / "sub-01_task-mi_eeg.fif"
    events_path = eeg_dir / "sub-01_task-mi_events.tsv"
    eeg_path.write_bytes(b"stable EEG header")
    events_path.write_text(
        "onset\tduration\ttrial_type\n0\t1\tleft\n",
        encoding="utf-8",
    )
    service, _dataset = _service()
    service.handle_scan_source(
        ScanSourceCommand(source_path=str(bids_root), source_hint="bids")
    )
    original_check = service_module.check_import_resource_preflight
    checks = 0

    def _counted_check(paths: list[str]) -> ResourcePreflightResult:
        nonlocal checks
        checks += 1
        return original_check(paths)

    monkeypatch.setattr(
        service_module,
        "check_import_resource_preflight",
        _counted_check,
    )
    monkeypatch.setattr(
        service_module,
        "discover_source_preflight_scope",
        lambda **_kwargs: pytest.fail("matching BIDS scan scope was rediscovered"),
    )

    _message, payload = _expect_payload(
        service.handle_preview_interpretation(
            PreviewInterpretationCommand(
                choices={"selected_eeg_files": [str(eeg_path.resolve())]}
            )
        )
    )

    assert checks == 0
    assert payload["resource_preflight"]["admission_cache_reused"] is True


def test_scan_does_not_cache_warning_resource_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = tmp_path / "sub-01_task-mi_raw.fif"
    eeg_path.write_bytes(b"stable EEG header")
    service, _dataset = _service()
    checks = 0

    def _warning_check(paths: list[str]) -> ResourcePreflightResult:
        nonlocal checks
        checks += 1
        return _resource_preflight("warning", paths)

    monkeypatch.setattr(
        service_module,
        "check_import_resource_preflight",
        _warning_check,
    )
    service.handle_scan_source(ScanSourceCommand(source_path=str(eeg_path)))

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError):
        service.handle_preview_interpretation(
            PreviewInterpretationCommand(
                choices={"selected_eeg_files": [str(eeg_path.resolve())]}
            )
        )

    assert checks == 2


def test_repeated_preview_discards_admission_when_source_content_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = tmp_path / "sub-01_task-mi_raw.fif"
    eeg_path.write_bytes(b"first EEG header")
    service, _dataset = _service()
    service.handle_scan_source(ScanSourceCommand(source_path=str(eeg_path)))
    choices = {"selected_eeg_files": [str(eeg_path.resolve())]}
    service.handle_preview_interpretation(PreviewInterpretationCommand(choices=choices))
    original_check = service_module.check_import_resource_preflight
    checks = 0

    def _counted_check(paths: list[str]) -> ResourcePreflightResult:
        nonlocal checks
        checks += 1
        return original_check(paths)

    monkeypatch.setattr(
        service_module,
        "check_import_resource_preflight",
        _counted_check,
    )
    eeg_path.write_bytes(b"other EEG header")

    _message, payload = _expect_payload(
        service.handle_preview_interpretation(
            PreviewInterpretationCommand(choices=choices)
        )
    )

    assert checks == 1
    assert payload["resource_preflight"]["admission_cache_reused"] is False


def test_reusable_content_identity_matches_windows_paths_case_insensitively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _dataset = _service()
    candidate = SimpleNamespace(
        scan_id="scan-1",
        content_identity={
            "files": [
                {
                    "path": r"C:\Data\Subject\Run.set",
                    "file_bytes": 123,
                    "sha256": "a" * 64,
                }
            ]
        },
    )
    monkeypatch.setattr(service.state, "resolve_candidate", lambda _value: candidate)
    monkeypatch.setattr(
        service_module,
        "_stat_change_time_is_reliable",
        lambda: True,
    )
    admission = SimpleNamespace(
        resource_reader=SimpleNamespace(
            admitted_files={r"c:\data\subject\run.set": object()}
        ),
        bids_events_json_reader=SimpleNamespace(admitted_files={}),
    )

    reusable = service._latest_admitted_content_identities(
        admission,
        expected_scan_id="scan-1",
    )

    assert reusable == {
        r"C:\Data\Subject\Run.set": {
            "file_bytes": 123,
            "sha256": "a" * 64,
        }
    }


def test_windows_does_not_reuse_content_identity_without_reliable_change_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _dataset = _service()
    candidate = SimpleNamespace(
        scan_id="scan-1",
        content_identity={
            "files": [
                {
                    "path": r"C:\Data\Subject\Run.set",
                    "file_bytes": 123,
                    "sha256": "a" * 64,
                }
            ]
        },
    )
    monkeypatch.setattr(service.state, "resolve_candidate", lambda _value: candidate)
    monkeypatch.setattr(
        service_module,
        "_stat_change_time_is_reliable",
        lambda: False,
    )
    admission = SimpleNamespace(
        resource_reader=SimpleNamespace(
            admitted_files={r"c:\data\subject\run.set": object()}
        ),
        bids_events_json_reader=SimpleNamespace(admitted_files={}),
    )

    reusable = service._latest_admitted_content_identities(
        admission,
        expected_scan_id="scan-1",
    )

    assert reusable == {}
