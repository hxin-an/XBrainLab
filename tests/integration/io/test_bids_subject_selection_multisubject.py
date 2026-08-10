"""Optional real-data evidence for multi-subject BIDS selection."""

from __future__ import annotations

from pathlib import Path

import pytest

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    CreateEpochCommand,
    DatasetSplitPreviewRequest,
    DatasetSplitSpecification,
    PreprocessCommand,
    PreprocessOperation,
    ReviewInterpretationCommand,
    SaveDatasetSplitCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
)

OPENNEURO_P300_ROOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "data"
    / "public"
    / "openneuro-ds003061-p300"
)
ALL_SUBJECTS = ("001", "002", "003")
RUNS = (1, 2, 3)
P300_CLASS_VALUES = (
    "standard",
    "oddball",
    "noise",
)
P300_VALUE_CLASS_MAP = {
    "standard": "standard",
    "standard_with_reponse": "standard",
    "oddball": "oddball",
    "oddball_with_reponse": "oddball",
    "noise": "noise",
    "noise_with_reponse": "noise",
}

pytestmark = pytest.mark.optional_public_fixture


@pytest.fixture(scope="module", autouse=True)
def _require_multisubject_extension() -> None:
    missing_subjects = [
        subject
        for subject in ("002", "003")
        if not (OPENNEURO_P300_ROOT / f"sub-{subject}").is_dir()
    ]
    if missing_subjects:
        pytest.skip(
            "Optional OpenNeuro ds003061 multi-subject fixture is not installed; "
            "fetch profile p300-multisubject first."
        )


def _run_paths(subjects: tuple[str, ...], suffix: str) -> list[str]:
    return [
        str(
            (
                OPENNEURO_P300_ROOT
                / f"sub-{subject}"
                / "eeg"
                / f"sub-{subject}_task-P300_run-{run}_{suffix}"
            ).resolve()
        )
        for subject in subjects
        for run in RUNS
    ]


def _selected_scope(subjects: tuple[str, ...]) -> dict[str, object]:
    return {
        "eeg_file_count": len(subjects) * len(RUNS),
        "subjects": list(subjects),
        "sessions": [],
        "tasks": ["P300"],
        "runs": [str(run) for run in RUNS],
        "datatypes": ["eeg"],
        "eeg_files": _run_paths(subjects, "eeg.set"),
        "events_files": _run_paths(subjects, "events.tsv"),
        "channels_files": _run_paths(subjects, "channels.tsv"),
    }


def _subjects_in_paths(paths: list[str]) -> set[str]:
    return {
        part.removeprefix("sub-")
        for path in paths
        for part in Path(path).parent.parts
        if part.startswith("sub-")
    }


def _p300_choices(subjects: tuple[str, ...]) -> dict[str, object]:
    value_decisions = {
        value: {
            "role": "stimulus",
            "keep_event": True,
            "use_as_class": True,
            "class_name": class_name,
        }
        for value, class_name in P300_VALUE_CLASS_MAP.items()
    }
    value_decisions.update(
        {
            "response": {
                "role": "response",
                "keep_event": False,
                "use_as_class": False,
            },
            "ignore": {
                "role": "system",
                "keep_event": False,
                "use_as_class": False,
            },
        }
    )
    return {
        "selected_bids_subjects": list(subjects),
        "label_carrier_choices": {
            path: {
                "label_field": "value",
                "anchor": "onset",
                "time_model": "seconds",
                "placement_method": "time_field",
                "value_decisions": value_decisions,
            }
            for path in _run_paths(subjects, "events.tsv")
        },
    }


def _trial_split_specification() -> DatasetSplitSpecification:
    return DatasetSplitSpecification.from_payload(
        {
            "train_type": "Individual",
            "is_cross_validation": False,
            "val_splitters": [
                {
                    "split_type": "By Trial",
                    "split_unit": "Ratio",
                    "value": "0.2",
                }
            ],
            "test_splitters": [
                {
                    "split_type": "By Trial",
                    "split_unit": "Ratio",
                    "value": "0.2",
                }
            ],
        }
    )


def test_catalog_reports_three_complete_subjects_and_nine_recordings() -> None:
    result = ApplicationService().execute(
        ScanSourceCommand(
            source_path=str(OPENNEURO_P300_ROOT),
            source_hint="bids",
            catalog_only=True,
        )
    )

    assert result.ok, result.message
    catalog = result.diagnostics["bids_subject_catalog"]
    assert catalog == {
        "root": str(OPENNEURO_P300_ROOT.resolve()),
        "subject_count": 3,
        "eeg_file_count": 9,
        "subjects": [
            {
                "subject": subject,
                "label": f"sub-{subject}",
                "eeg_file_count": 3,
                "sessions": [],
                "tasks": ["P300"],
                "runs": ["1", "2", "3"],
            }
            for subject in ALL_SUBJECTS
        ],
        "warnings": [],
    }


@pytest.mark.parametrize(
    "subjects",
    [("001",), ("002",), ("003",), ("002", "003")],
    ids=["subject-001", "subject-002", "subject-003", "subjects-002-003"],
)
def test_scan_uses_only_the_exact_selected_subject_scope(
    subjects: tuple[str, ...],
) -> None:
    result = ApplicationService().execute(
        ScanSourceCommand(
            source_path=str(OPENNEURO_P300_ROOT),
            source_hint="bids",
            selected_bids_subjects=list(subjects),
        )
    )

    assert result.ok, result.message
    scan = result.diagnostics["scan_result"]
    expected_scope = _selected_scope(subjects)
    expected_eeg_files = expected_scope["eeg_files"]
    expected_events_files = expected_scope["events_files"]
    assert isinstance(expected_eeg_files, list)
    assert isinstance(expected_events_files, list)

    assert scan["eeg_files"] == expected_eeg_files
    assert scan["label_carriers"] == expected_events_files
    assert scan["bids"]["selected_scope"] == expected_scope


def test_review_pairs_events_only_with_selected_subjects_002_and_003() -> None:
    subjects = ("002", "003")
    result = ApplicationService().execute(
        ReviewInterpretationCommand(
            source_path=str(OPENNEURO_P300_ROOT),
            source_hint="bids",
            choices={"selected_bids_subjects": list(subjects)},
        )
    )

    assert result.ok, result.message
    scan = result.diagnostics["scan_result"]
    candidate = result.diagnostics["candidate"]
    preview = result.diagnostics["preview"]
    expected_scope = _selected_scope(subjects)
    expected_eeg_files = expected_scope["eeg_files"]
    expected_events_files = expected_scope["events_files"]
    assert isinstance(expected_eeg_files, list)
    assert isinstance(expected_events_files, list)

    assert scan["eeg_files"] == expected_eeg_files
    assert scan["label_carriers"] == expected_events_files
    assert scan["bids"]["selected_scope"] == expected_scope
    assert candidate["selected_eeg_files"] == expected_eeg_files
    assert candidate["label_carriers"] == expected_events_files
    assert preview["bids"]["selected_scope"] == expected_scope

    event_review = preview["bids"]["event_validation"]
    expected_pairing = dict(zip(expected_eeg_files, expected_events_files, strict=True))
    assert event_review["file_mapping"] == expected_pairing
    assert event_review["pairing_issues"] == []
    assert [
        (run["eeg_file"], run["events_file"]) for run in event_review["runs"]
    ] == list(expected_pairing.items())

    reviewed_paths = [
        *event_review["file_mapping"].keys(),
        *event_review["file_mapping"].values(),
    ]
    assert _subjects_in_paths(reviewed_paths) == set(subjects)


def test_selected_subjects_reach_epochs_and_deferred_split_without_scope_leakage() -> (
    None
):
    subjects = ("002", "003")
    expected_eeg_files = _run_paths(subjects, "eeg.set")
    expected_events_files = _run_paths(subjects, "events.tsv")
    expected_dataset_subjects = {
        f"Subject-{subject}_0": subject for subject in subjects
    }
    service = ApplicationService()

    try:
        review = service.execute(
            ReviewInterpretationCommand(
                source_path=str(OPENNEURO_P300_ROOT),
                source_hint="bids",
                choices=_p300_choices(subjects),
            )
        )
        validation = service.execute(ValidateInterpretationCommand())
        applied = service.execute(ApplyInterpretationCommand(confirmed=True))

        assert review.ok, review.message
        assert validation.ok, validation.message
        assert validation.diagnostics["validation_decision"]["blocked_reasons"] == []
        assert applied.ok, applied.message
        assert applied.state.raw.count == len(expected_eeg_files)
        assert applied.state.raw.files == [
            Path(path).name for path in expected_eeg_files
        ]
        assert {row["subject"] for row in applied.state.raw.metadata} == set(subjects)
        assert applied.state.interpretation.bids["selected_scope"]["eeg_files"] == (
            expected_eeg_files
        )

        handoff = applied.state.interpretation.epoch_handoff
        handoff_paths = [
            *[row["path"] for row in handoff["label_carrier_plan"]],
            *[row["selected_target_file"] for row in handoff["label_carrier_plan"]],
        ]
        assert set(handoff_paths) == {*expected_eeg_files, *expected_events_files}
        assert _subjects_in_paths(handoff_paths) == set(subjects)

        normalized = service.execute(
            PreprocessCommand(
                operation=PreprocessOperation.NORMALIZE,
                method="z-score",
            )
        )
        epoch = service.execute(
            CreateEpochCommand(
                t_min=-0.2,
                t_max=0.5,
                event_ids=list(P300_CLASS_VALUES),
            )
        )

        assert normalized.ok, normalized.message
        assert epoch.ok, epoch.message
        assert epoch.state.epoch.available is True
        assert epoch.state.epoch.epoch_count is not None
        assert epoch.state.epoch.epoch_count > 0

        epoch_data = service.study.epoch_data
        assert epoch_data is not None
        assert set(epoch_data.get_subject_map().values()) == set(subjects)
        assert len(epoch_data.get_epoch_window_provenance()) == (
            epoch.state.epoch.epoch_count
        )

        epoched_sources = service.study.preprocessed_data_list
        assert len(epoched_sources) == len(expected_eeg_files)
        assert [item.get_filepath() for item in epoched_sources] == expected_eeg_files
        expected_source_ids: set[str] = set()
        for item in epoched_sources:
            identity = item.get_source_content_identity()
            assert identity is not None
            assert identity["algorithm"] == "sha256"
            expected_source_ids.add(f"content-sha256:{identity['sha256']}")
        assert len(expected_source_ids) == len(expected_eeg_files)

        epoch_provenance = epoch_data.get_epoch_window_provenance()
        assert all(item.source_coordinates_verified for item in epoch_provenance)
        assert {
            item.source_recording_id for item in epoch_provenance
        } == expected_source_ids

        split_specification = _trial_split_specification()
        split_generation = service.get_view_publication().generation
        split_preview = service.get_dataset_split_preview(
            DatasetSplitPreviewRequest(
                request_id="selected-multisubject-split",
                publication_generation=split_generation,
                specification=split_specification,
            )
        )
        assert {row.name for row in split_preview.rows} == set(
            expected_dataset_subjects
        )

        saved = service.execute(
            SaveDatasetSplitCommand(
                split_config=split_specification.to_payload(),
                preview_receipt=split_preview.receipt,
            ),
            expected_publication_generation=split_generation,
        )

        assert saved.ok, saved.message
        assert saved.state.dataset.split_spec_saved is True
        assert saved.state.dataset.split_materialized is False
        assert saved.state.dataset.available is False
        assert saved.state.dataset.count == 0
        assert service.study.datasets == []

        candidate = service.dataset_generation.prepare_saved_split_candidate()

        assert candidate.summary["audit"]["ok"] is True
        assert {dataset.get_name() for dataset in candidate.datasets} == set(
            expected_dataset_subjects
        )
        for dataset in candidate.datasets:
            materialized_epoch_data = dataset.get_epoch_data()
            assert set(materialized_epoch_data.get_subject_map().values()) == set(
                subjects
            )
            assert {
                item.source_recording_id
                for item in materialized_epoch_data.get_epoch_window_provenance()
            } == expected_source_ids
            materialized_mask = (
                dataset.train_mask | dataset.val_mask | dataset.test_mask
            )
            materialized_subjects = {
                materialized_epoch_data.get_subject_name(int(subject_index))
                for subject_index in materialized_epoch_data.get_subject_list_by_mask(
                    materialized_mask
                ).tolist()
            }
            assert materialized_subjects == {
                expected_dataset_subjects[dataset.get_name()]
            }

        assert service.study.datasets == []
        assert service.get_state().dataset.split_materialized is False
    finally:
        service.dataset_generation.discard_prepared_split()
        assert service.wait_for_background_tasks(timeout=30.0)
        service.close()
