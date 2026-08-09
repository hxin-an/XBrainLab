from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from scripts.dev.moabb_user_journeys.registry import (
    REPO_ROOT,
    expected_download_bytes,
    load_registry,
    materialize_dataset,
    validate_registry,
)
from XBrainLab.backend.model_requirements import minimum_samples_for_model


def test_registry_pins_diverse_compact_official_sources() -> None:
    registry = load_registry()

    assert registry["moabb_release"] == {
        "version": "1.5.0",
        "tag": "v1.5",
        "commit": "140809d8c48bdf2be953951ff75f688122edee34",  # pragma: allowlist secret
        "repository": "https://github.com/NeuroTechX/moabb",
        "license": "BSD-3-Clause",
    }
    assert registry["resource_policy"]["data_root"] == "build/moabb-data"
    assert registry["resource_policy"]["serial_downloads"] is True
    assert registry["resource_policy"]["max_download_bytes"] == 1024**3
    assert expected_download_bytes(registry["datasets"]) == 979_833_042
    assert expected_download_bytes(registry["datasets"]) < 1024**3
    assert {dataset["source_format"] for dataset in registry["datasets"]} == {
        "GDF",
        "EDF+",
        "BrainVision",
    }
    assert any(dataset["paradigm"] == "p300_erp" for dataset in registry["datasets"])
    assert all(
        dataset["identity"]["moabb_adapter_url"].find(
            registry["moabb_release"]["commit"]
        )
        >= 0
        for dataset in registry["datasets"]
    )


def test_registry_separates_smoke_from_showcase_quality_budget() -> None:
    registry = load_registry()

    for dataset in registry["datasets"]:
        smoke = dataset["workflow"]["training_profiles"]["smoke"]
        showcase = dataset["workflow"]["training_profiles"]["showcase"]
        assert smoke["epochs"] == 1
        assert "smoke only" in smoke["stopping_budget"]
        assert showcase["epochs"] == 30
        assert showcase["evaluation_option"].startswith("val_")
        assert "held-out test split is not used" in showcase["stopping_budget"]
        acceptance = dataset["workflow"]["quality_acceptance"]
        assert acceptance["held_out_split"] == "test"
        assert all(
            rule["threshold"]["kind"] in {"observed_baseline", "fixed"}
            for rule in acceptance["rules"]
        )
        assert dataset["claim_boundary"]

    p300 = next(
        dataset for dataset in registry["datasets"] if dataset["paradigm"] == "p300_erp"
    )
    assert (
        p300["workflow"]["training_profiles"]["showcase"]["evaluation_option"]
        == "val_auc"
    )
    assert "accuracy" not in {
        rule["metric"] for rule in p300["workflow"]["quality_acceptance"]["rules"]
    }


def test_physionet_selection_repeats_both_run_dependent_event_semantics() -> None:
    registry = load_registry()
    dataset = next(
        item
        for item in registry["datasets"]
        if item["id"] == "physionetmi-edf-run-semantics"
    )

    assert dataset["selection"]["runs"] == [4, 6, 8, 10, 12, 14]
    assert len(dataset["files"]) == 6
    assert len(dataset["import"]["selected_eeg_files"]) == 6
    mappings = dataset["import"]["choices"]["run_event_mappings"]
    assert mappings == {
        "S001R04.edf": {"T1": "left fist", "T2": "right fist"},
        "S001R06.edf": {"T1": "both fists", "T2": "both feet"},
        "S001R08.edf": {"T1": "left fist", "T2": "right fist"},
        "S001R10.edf": {"T1": "both fists", "T2": "both feet"},
        "S001R12.edf": {"T1": "left fist", "T2": "right fist"},
        "S001R14.edf": {"T1": "both fists", "T2": "both feet"},
    }


def test_lee_erp_epoch_preserves_pinned_interval_and_meets_eegnet_contract() -> None:
    registry = load_registry()
    lee = next(
        dataset
        for dataset in registry["datasets"]
        if dataset["id"] == "lee2021mobile-erp-brainvision"
    )
    epoch = lee["workflow"]["epoch"]

    # Lee segments ERP at -0.2 to 0.8 s; the pinned adapter exposes 0 to 1 s at 100 Hz.
    sfreq = 100.0
    requirement = minimum_samples_for_model("EEGNet", sfreq=sfreq)
    assert requirement is not None
    sample_count = round((epoch["t_max"] - epoch["t_min"]) * sfreq) + 1

    assert epoch["t_min"] <= -0.2
    assert epoch["t_max"] == 1.0
    assert epoch["baseline"] is None
    assert sample_count >= requirement.min_samples


def test_ofner_selection_is_a_resource_bounded_full_class_evaluation_unit() -> None:
    registry = load_registry()
    ofner = next(
        dataset
        for dataset in registry["datasets"]
        if dataset["id"] == "ofner2017-mi-gdf"
    )

    selection = ofner["selection"]

    assert selection["subjects"] == [1]
    assert selection["sessions"] == ["imagination"]
    assert selection["runs"] == list(range(1, 10))
    assert selection["expected_trial_count"] == 378
    assert selection["expected_trials_per_class"] == 54
    assert "1 GiB" in selection["reason"]
    assert "run 10" in selection["reason"]
    assert len(ofner["files"]) == 9
    assert len(ofner["import"]["selected_eeg_files"]) == 9
    assert ofner["import"]["source_hint"] == "folder"
    metadata = ofner["import"]["choices"]["metadata_overrides"]
    assert set(metadata) == {f"run-{run:02d}.gdf" for run in range(1, 10)}
    assert {item["subject"] for item in metadata.values()} == {"001"}
    assert {item["session"] for item in metadata.values()} == {"imagination"}
    assert {item["task"] for item in metadata.values()} == {"motor_imagery"}
    assert {item["run"] for item in metadata.values()} == {
        f"{run:02d}" for run in range(1, 10)
    }
    assert ofner["identity"]["license"] == "CC-BY-4.0"
    assert all(item["checksum"]["algorithm"] == "md5" for item in ofner["files"])
    assert all(item["source_metadata_url"] for item in ofner["files"])


def test_ofner_workflow_preserves_bad_spans_without_imputation() -> None:
    registry = load_registry()
    ofner = next(
        dataset
        for dataset in registry["datasets"]
        if dataset["id"] == "ofner2017-mi-gdf"
    )
    preprocessing = ofner["workflow"]["preprocessing"]

    assert [step["operation"] for step in preprocessing] == [
        "select_channels",
        "bandpass",
        "rereference",
        "normalize",
    ]
    assert len(preprocessing[0]["channels"]) == 61
    assert all(
        not channel.casefold().startswith(("eog", "armeodummy"))
        for channel in preprocessing[0]["channels"]
    )
    assert preprocessing[1] == {
        "operation": "bandpass",
        "low_freq": 0.3,
        "high_freq": 3.0,
    }
    assert preprocessing[2] == {"operation": "rereference", "method": "average"}
    assert preprocessing[3] == {"operation": "normalize", "method": "z score"}
    assert any("artefact" in boundary for boundary in ofner["claim_boundary"])
    assert any("non-finite" in boundary for boundary in ofner["claim_boundary"])
    source_quality = ofner["selection"]["source_quality"]
    assert source_quality["sampling_rate_hz"] == 512
    assert source_quality["policy"] == "exclude_bad_spans_during_epoching"
    assert source_quality["imputation"] == "none"
    spans = {item["run"]: item for item in source_quality["nonfinite_tail_spans"]}
    assert 2 not in spans
    assert spans[1] == {
        "run": 1,
        "start_sample": 165761,
        "stop_sample_exclusive": 165888,
        "start_seconds": 323.751953125,
        "stop_seconds": 324.0,
        "affected_eeg_channels": 61,
    }


def test_ofner_quality_floor_is_fixed_before_held_out_test_read() -> None:
    registry = load_registry()
    ofner = next(
        dataset
        for dataset in registry["datasets"]
        if dataset["id"] == "ofner2017-mi-gdf"
    )
    quality = ofner["workflow"]["quality_acceptance"]
    balanced_rule = next(
        rule for rule in quality["rules"] if rule["metric"] == "balanced_accuracy"
    )

    assert balanced_rule["operator"] == ">="
    assert balanced_rule["threshold"] == {
        "kind": "fixed",
        "name": "predeclared_meaningful_floor",
        "value": 0.25,
    }
    assert "once" in quality["test_access_policy"]


def test_registry_rejects_one_epoch_showcase() -> None:
    registry = deepcopy(load_registry())
    registry["datasets"][0]["workflow"]["training_profiles"]["showcase"]["epochs"] = 1

    with pytest.raises(ValueError, match="showcase profile"):
        validate_registry(registry, repo_root=REPO_ROOT)


def test_materialized_dataset_stays_under_d_drive_build_cache() -> None:
    registry = load_registry()
    data_root = REPO_ROOT / registry["resource_policy"]["data_root"]

    materialized = materialize_dataset(registry["datasets"][0], data_root=data_root)

    assert Path(materialized["import"]["source_path"]).is_relative_to(data_root)
    assert all(
        Path(item["cache_path"]).is_relative_to(data_root)
        for item in materialized["files"]
    )
