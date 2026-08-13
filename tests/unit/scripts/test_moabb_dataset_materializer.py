from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

import pytest

from scripts.dev import moabb_campaign_preflight
from scripts.dev.moabb_campaign_preflight import (
    EXPECTED_CLASS_NAMES,
    PreflightInputs,
    evaluate_preflight,
)
from scripts.dev.moabb_dataset_materializer import (
    MaterializationContractError,
    MaterializationInputs,
    _bids_event_semantics,
    _bounded_http_resource_probe,
    _campaign_product_identity_digest,
    _conversion_identity_digest,
    _environment_identity_digest,
    _expected_product_class_mapping,
    _git_status_policy,
    _parse_nvidia_smi_row,
    _temporary_mne_environment,
    _validate_environment,
    bids_tree_integrity_error,
    run_materialization,
)
from scripts.dev.moabb_gui_campaign_v2 import contract as gui_contract

FORMATS = {
    "FakeEDF": "EDF",
    "FakeBrainVision": "BrainVision",
    "FakeEEGLAB": "EEGLAB",
}

CRITICAL_PACKAGES = {
    "moabb": "1.5.0",
    "mne": "1.11.0",
    "mne-bids": "0.19.0",
    "pybv": "0.8.1",
    "edfio": "0.4.16",
    "edflib-python": "1.0.8",
    "eeglabio": "0.1.3",
    "numpy": "2.5.2",
    "torch": "2.11.0",
    "pyxdf": "1.17.5",
    "pymatreader": "1.2.3",
    "pyriemann": "0.12",
    "scipy": "1.17.0",
    "scikit-learn": "1.8.0",
    "bids-validator-deno": "2.4.1",
}


def test_product_class_mapping_is_separate_from_nonalphabetic_source_codes() -> None:
    assert _expected_product_class_mapping(["zeta", "alpha"]) == [
        {"class_index": 0, "event_code": "0", "class_name": "alpha"},
        {"class_index": 1, "event_code": "1", "class_name": "zeta"},
    ]


def test_bids_event_semantics_rejects_duplicate_values_across_labels(
    tmp_path: Path,
) -> None:
    events = tmp_path / "sub-1_task-test_events.tsv"
    events.write_text(
        "onset\tduration\ttrial_type\tvalue\n0\t1\tleft_hand\t1\n1\t1\tright_hand\t1\n",
        encoding="utf-8",
    )

    with pytest.raises(
        MaterializationContractError,
        match="mapping is missing, duplicated, or inconsistent within",
    ):
        _bids_event_semantics(tmp_path)


def test_bids_event_semantics_preserves_physionet_run_local_label_union(
    tmp_path: Path,
) -> None:
    (tmp_path / "sub-1_task-feet-hands_events.tsv").write_text(
        "onset\tduration\ttrial_type\tvalue\n"
        "0\t1\tfeet\t1\n"
        "1\t1\trest\t2\n"
        "2\t1\thands\t3\n",
        encoding="utf-8",
    )
    (tmp_path / "sub-1_task-left-right_events.tsv").write_text(
        "onset\tduration\ttrial_type\tvalue\n"
        "0\t1\tleft_hand\t1\n"
        "1\t1\tright_hand\t2\n"
        "2\t1\trest\t3\n",
        encoding="utf-8",
    )

    labels, values, crosscheck = _bids_event_semantics(tmp_path)

    assert labels == ["feet", "rest", "hands", "left_hand", "right_hand"]
    assert values == {}
    assert crosscheck == "run-local"


def _environment(identity_sha256: str = "e" * 64) -> dict[str, Any]:
    environment = {
        "python": {
            "version": "3.12.0",
            "implementation": "CPython",
            "executable": "/synthetic/python",
        },
        "platform": {
            "system": "Linux",
            "release": "synthetic",
            "machine": "x86_64",
            "platform": "synthetic-linux",
        },
        "git": {
            "commit": "a" * 40,
            "tree": "b" * 40,
            "dirty": False,
            "protected_local_changes": [],
            "status_sha256": "c" * 64,
        },
        "poetry_lock_sha256": "d" * 64,
        "packages": dict(CRITICAL_PACKAGES),
        "locked_packages": {
            name: [version] for name, version in CRITICAL_PACKAGES.items()
        },
        "torch_cuda": {
            "torch_version": CRITICAL_PACKAGES["torch"],
            "cuda_runtime": "12.8",
            "cuda_available": True,
            "device_count": 1,
            "selected_device_index": 0,
            "selected_device_name": "Synthetic GPU",
            "selected_device_total_memory_bytes": 16 * 1024**3,
            "compute_capability": [8, 9],
        },
        "nvidia_smi": {
            "selected_device_index": 0,
            "uuid": "GPU-synthetic",
            "name": "Synthetic GPU",
            "driver_version": "999.0",
            "memory_total_mib": 16384,
        },
        "cuda": "12.8",
        "gpu": "Synthetic GPU",
        "converter_code": {
            "distribution": "moabb",
            "relative_path": "moabb/datasets/base.py",
            "sha256": "f" * 64,
        },
    }
    environment["conversion_identity_sha256"] = _conversion_identity_digest(environment)
    product_digest = _campaign_product_identity_digest(environment)
    environment["campaign_product_identity_sha256"] = product_digest
    environment["identity_sha256"] = product_digest
    if identity_sha256 != "e" * 64:
        environment["identity_sha256"] = identity_sha256
    return environment


def _passed_validator(root: Path) -> dict[str, Any]:
    return {
        "status": "passed",
        "validator": "bids-validator-deno",
        "version": "2.4.1",
        "argv": [
            "bids-validator-deno",
            str(root),
            "--format",
            "json",
            "--max-rows",
            "-1",
        ],
        "exit_code": 0,
        "error_count": 0,
        "warning_count": 0,
        "report": {"issues": {"errors": [], "warnings": []}},
    }


class _FakeDataset:
    _DEFAULT_EVENT_ID: ClassVar[dict[str, int]] = {"target": 1, "non-target": 2}
    event_id: dict[str, int]

    def __init__(
        self,
        class_name: str,
        *,
        calls: list[dict[str, Any]],
        fail: bool = False,
        event_names: list[str] | None = None,
        bids_event_id: dict[str, int] | None = None,
        bids_event_id_by_run: list[dict[str, int]] | None = None,
    ) -> None:
        self.class_name = class_name
        self.calls = calls
        self.fail = fail
        self.event_id = dict(self._DEFAULT_EVENT_ID)
        if event_names is not None:
            self.event_id = {
                label: index for index, label in enumerate(event_names, start=1)
            }
        self.bids_event_id = bids_event_id
        self.bids_event_id_by_run = bids_event_id_by_run

    def convert_to_bids(
        self,
        *,
        path: Path,
        subjects: list[int],
        overwrite: bool,
        format: str,  # noqa: A002 - mirrors the pinned MOABB public signature
        verbose: str | None,
        generate_figures: bool,
    ) -> Path:
        self.calls.append(
            {
                "class_name": self.class_name,
                "path": str(path),
                "subjects": subjects,
                "overwrite": overwrite,
                "format": format,
                "verbose": verbose,
                "generate_figures": generate_figures,
            }
        )
        source_root = Path(os.environ["MNE_DATA"])
        source_file = source_root / "download" / f"{self.class_name}.source"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_bytes(f"source:{self.class_name}".encode())

        bids_root = Path(path) / f"MNE-BIDS-{self.class_name.lower()}"
        eeg_root = bids_root / "sub-1" / "eeg"
        eeg_root.mkdir(parents=True, exist_ok=True)
        (bids_root / "dataset_description.json").write_text(
            '{"Name":"synthetic","BIDSVersion":"1.9.0"}',
            encoding="utf-8",
        )
        if self.bids_event_id_by_run is not None:
            for run, event_id in enumerate(self.bids_event_id_by_run, start=1):
                event_rows = "".join(
                    f"{index}\t1\t{label}\t{event_id[label]}\n"
                    for index, label in enumerate(self.event_id, start=0)
                )
                (eeg_root / f"sub-1_task-test_run-{run}_events.tsv").write_text(
                    "onset\tduration\ttrial_type\tvalue\n" + event_rows,
                    encoding="utf-8",
                )
        elif self.bids_event_id is None:
            event_header = "onset\tduration\ttrial_type\n"
            event_rows = "".join(
                f"{index}\t1\t{label}\n"
                for index, label in enumerate(self.event_id, start=0)
            )
        else:
            event_header = "onset\tduration\ttrial_type\tvalue\n"
            event_rows = "".join(
                f"{index}\t1\t{label}\t{self.bids_event_id[label]}\n"
                for index, label in enumerate(self.event_id, start=0)
            )
        if self.bids_event_id_by_run is None:
            (eeg_root / "sub-1_task-test_events.tsv").write_text(
                f"{event_header}{event_rows}", encoding="utf-8"
            )
        stem = eeg_root / "sub-1_task-test_eeg"
        if format == "EDF":
            stem.with_suffix(".edf").write_bytes(b"synthetic-edf")
        elif format == "BrainVision":
            stem.with_suffix(".vhdr").write_text(
                "DataFile=sub-1_task-test_eeg.eeg\n"
                "MarkerFile=sub-1_task-test_eeg.vmrk\n",
                encoding="utf-8",
            )
            stem.with_suffix(".vmrk").write_text(
                "DataFile=sub-1_task-test_eeg.eeg\n", encoding="utf-8"
            )
            stem.with_suffix(".eeg").write_bytes(b"synthetic-brainvision")
        elif format == "EEGLAB":
            stem.with_suffix(".set").write_text(
                "external=sub-1_task-test_eeg.fdt\n", encoding="utf-8"
            )
            stem.with_suffix(".fdt").write_bytes(b"synthetic-eeglab")
        else:  # pragma: no cover - manifest validation owns this boundary
            raise AssertionError(format)
        if self.fail:
            (bids_root / "partial.txt").write_text("partial", encoding="utf-8")
            raise RuntimeError("synthetic conversion failed")
        return bids_root


def _write_contracts(
    tmp_path: Path,
    *,
    class_names: tuple[str, ...] = tuple(FORMATS),
    resource_preflight: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    datasets: list[dict[str, Any]] = []
    gui_datasets: list[dict[str, Any]] = []
    for class_name in class_names:
        row: dict[str, Any] = {
            "moabb_class": class_name,
            "subjects": [1],
            "output_format": FORMATS[class_name],
            "source_download_bytes": 128,
            "source_checksum_status": "ABSENT",
            "supervised_classes": ["target"],
            "license_status": "verified",
            "resource_status": "verified",
        }
        if resource_preflight is not None:
            row["resource_status"] = "RESOURCE_PREFLIGHT_REQUIRED"
            row["resource_preflight"] = resource_preflight
        datasets.append(row)
        gui_datasets.append(
            {
                "moabb_class": class_name,
                "subjects": [1],
                "execution_state": "awaiting_dataset_materialization",
                "bids": {
                    "formal_bids": True,
                    "format": FORMATS[class_name],
                    "conversion_parent": "/mnt/d/unmaterialized",
                    "root": None,
                    "root_resolution": {
                        "source": "convert_to_bids_return_value",
                        "must_be_descendant_of_conversion_parent": True,
                        "required_basename_prefix": "MNE-BIDS-",
                        "required_marker": "dataset_description.json",
                    },
                    "checksum_manifest": "/mnt/d/unmaterialized.sha256",
                    "dataset_revision_sha256": None,
                },
                "oracle": {"state": "awaiting_dataset_materialization"},
            }
        )
    materialization_manifest = tmp_path / "materialization.json"
    materialization_manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.1.0",
                "profile_id": "synthetic-moabb-freeze",
                "moabb_release": {
                    "version": "1.5.0",
                    "commit": "1" * 40,
                },
                "resource_policy": {
                    "minimum_headroom_multiplier": 4,
                    "minimum_artifact_headroom_bytes": 512,
                },
                "datasets": datasets,
            }
        ),
        encoding="utf-8",
    )
    gui_plan = tmp_path / "gui-plan.json"
    gui_plan.write_text(
        json.dumps(
            {
                "schema_version": "2.0.0",
                "profile_id": "synthetic-gui-plan",
                "datasets": gui_datasets,
            }
        ),
        encoding="utf-8",
    )
    return materialization_manifest, gui_plan


def _git_blob_sha1(payload: bytes) -> str:
    digest = hashlib.sha1(usedforsecurity=False)
    digest.update(f"blob {len(payload)}\0".encode())
    digest.update(payload)
    return digest.hexdigest()


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_mirror_contracts(
    tmp_path: Path,
) -> tuple[Path, Path, bytes, dict[str, bytes]]:
    events = (
        b"onset\tduration\ttrial_type\tvalue\n"
        b"0\t1\tright_hand\t2\n1\t1\tright_elbow\t1\n"
    )
    payloads = {
        "dataset_description.json": (
            b'{"Name":"synthetic mirror","BIDSVersion":"1.9.0",'
            b'"DatasetType":"derivative"}'
        ),
        "participants.tsv": b"participant_id\nsub-1\nsub-2\nsub-3\n",
        "code/provenance.json": b'{"GeneratedBy":"MOABB 1.5.0"}',
        "sub-1/eeg/sub-1_task-imagery_events.tsv": events,
        "sub-1/eeg/sub-1_task-imagery_eeg.bdf": b"synthetic-bdf-subject-1" * 512,
        "sub-2/eeg/sub-2_task-imagery_events.tsv": events,
        "sub-2/eeg/sub-2_task-imagery_eeg.bdf": b"synthetic-bdf-subject-2" * 512,
        "sub-3/eeg/sub-3_task-imagery_events.tsv": events,
        "sub-3/eeg/sub-3_task-imagery_eeg.bdf": b"unselected-subject-3" * 512,
    }
    sha256_paths = {path for path in payloads if path.endswith(".bdf")}
    entries = []
    for relative_path, payload in payloads.items():
        algorithm = "sha256" if relative_path in sha256_paths else "git"
        checksum = (
            hashlib.sha256(payload).hexdigest()
            if algorithm == "sha256"
            else _git_blob_sha1(payload)
        )
        entries.append(
            {
                "path": relative_path,
                "size": len(payload),
                "checksum_algorithm": algorithm,
                "checksum": checksum,
                "bytes_url": f"https://mirror.invalid/v1/{relative_path}",
            }
        )
    entries.sort(key=lambda item: item["path"])
    selected = [
        entry
        for entry in entries
        if entry["path"] in {"dataset_description.json", "participants.tsv"}
        or entry["path"].startswith("code/")
        or entry["path"].split("/", 1)[0] in {"sub-1", "sub-2"}
    ]

    def _pin(values: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "entry_count": len(values),
            "total_bytes": sum(int(item["size"]) for item in values),
            "projection_sha256": _canonical_sha256(values),
        }

    mirror_policy = {
        "manifest_url": "https://mirror.invalid/v1/manifest.json",
        "manifest_hosts": ["mirror.invalid"],
        "manifest_maximum_bytes": 64 * 1024,
        "download_hosts": ["mirror.invalid"],
        "redirect_hosts": ["objects.invalid"],
        "entries_pointer": "$",
        "projection_fields": [
            "path",
            "size",
            "checksum_algorithm",
            "checksum",
            "bytes_url",
        ],
        "native_format": "BDF",
        "root_basename": "MNE-BIDS-synthetic-mirror",
        "subject_path_template": "sub-{subject}",
        "include_paths": ["dataset_description.json", "participants.tsv"],
        "include_prefixes": ["code/"],
        "full_projection": _pin(entries),
        "selected_projection": _pin(selected),
        "expected_trial_type_values": {"right_hand": 2, "right_elbow": 1},
        "provenance": {
            "dataset_id": "synthetic-mirror",
            "version": "1.0.0",
            "source_doi": "10.example/source",
            "bids_doi": "10.example/bids",
            "repository_tag": "v1.0.0",
            "repository_tag_object": "1" * 40,
            "repository_commit": "2" * 40,
            "generated_by": "MOABB 1.5.0",
        },
    }
    dataset = {
        "moabb_class": "FakeMirror",
        "source_mode": "formal_bids_mirror",
        "subjects": [1, 2],
        "output_format": "BDF",
        "source_download_bytes": mirror_policy["selected_projection"]["total_bytes"],
        "source_checksum_status": "ABSENT",
        "supervised_classes": ["right_hand", "right_elbow"],
        "license_status": "verified",
        "resource_status": "FORMAL_BIDS_MIRROR_REQUIRED",
        "formal_bids_mirror": mirror_policy,
    }
    manifest = {
        "schema_version": "1.1.0",
        "profile_id": "synthetic-mirror-freeze",
        "moabb_release": {"version": "1.5.0", "commit": "1" * 40},
        "resource_policy": {
            "minimum_headroom_multiplier": 4,
            "minimum_artifact_headroom_bytes": 512,
        },
        "datasets": [dataset],
    }
    gui_plan = {
        "schema_version": "2.0.0",
        "profile_id": "synthetic-mirror-gui",
        "datasets": [
            {
                "moabb_class": "FakeMirror",
                "source_mode": "formal_bids_mirror",
                "subjects": [1, 2],
                "execution_state": "awaiting_dataset_materialization",
                "bids": {
                    "formal_bids": True,
                    "format": "BDF",
                    "conversion_parent": "/mnt/d/unmaterialized",
                    "root": None,
                    "root_resolution": {
                        "source": "formal_bids_mirror_receipt",
                        "must_be_descendant_of_conversion_parent": True,
                        "required_basename_prefix": "MNE-BIDS-",
                        "required_marker": "dataset_description.json",
                    },
                    "checksum_manifest": "/mnt/d/unmaterialized.sha256",
                    "dataset_revision_sha256": None,
                },
                "oracle": {"state": "awaiting_dataset_materialization"},
            }
        ],
    }
    manifest_path = tmp_path / "mirror-materialization.json"
    gui_plan_path = tmp_path / "mirror-gui-plan.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    gui_plan_path.write_text(json.dumps(gui_plan), encoding="utf-8")
    return manifest_path, gui_plan_path, json.dumps(entries).encode(), payloads


def _inputs(
    tmp_path: Path,
    *,
    manifest_path: Path,
    gui_plan_path: Path,
    dataset_factory: Callable[[str], Any],
    dataset: str | None = None,
    source_seed_root: Path | None = None,
    dry_run: bool = False,
    allow_download: bool = True,
    free_bytes: int = 10**9,
    environment_identity: dict[str, Any] | None = None,
    resource_probe: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    mirror_manifest_fetcher: Callable[[str, frozenset[str], int], bytes] | None = None,
    mirror_file_downloader: Callable[[str, Path, frozenset[str], int], dict[str, Any]]
    | None = None,
    bids_validator: Callable[[Path], dict[str, Any]] = _passed_validator,
) -> MaterializationInputs:
    return MaterializationInputs(
        manifest_path=manifest_path,
        gui_plan_path=gui_plan_path,
        mne_data_root=tmp_path / "source-cache",
        output_root=tmp_path / "bids-output",
        checksum_root=tmp_path / "checksums",
        source_seed_root=source_seed_root,
        dataset=dataset,
        dry_run=dry_run,
        allow_download=allow_download,
        resume=True,
        free_bytes=free_bytes,
        dataset_factory=dataset_factory,
        environment_identity=lambda: environment_identity or _environment(),
        resource_probe=resource_probe
        or (
            lambda policy: {
                "status": "passed",
                "resources": [
                    {
                        "url": resource["url"],
                        "http_status": 206,
                        "total_bytes": 64,
                    }
                    for resource in policy.get("resources", [])
                ],
                "total_bytes": 64 * len(policy.get("resources", [])),
            }
        ),
        mirror_manifest_fetcher=mirror_manifest_fetcher
        or (
            lambda _url, _hosts, _maximum_bytes: (_ for _ in ()).throw(
                AssertionError("unexpected formal BIDS mirror manifest fetch")
            )
        ),
        mirror_file_downloader=mirror_file_downloader
        or (
            lambda _url, _target, _hosts, _expected_bytes: (_ for _ in ()).throw(
                AssertionError("unexpected formal BIDS mirror download")
            )
        ),
        bids_validator=bids_validator,
        d_mount_validator=lambda _path: True,
    )


@pytest.mark.parametrize(("class_name", "output_format"), FORMATS.items())
def test_materializer_uses_generic_convert_to_bids_and_freezes_all_format_files(
    tmp_path: Path,
    class_name: str,
    output_format: str,
) -> None:
    manifest_path, gui_plan_path = _write_contracts(tmp_path, class_names=(class_name,))
    calls: list[dict[str, Any]] = []

    result = run_materialization(
        _inputs(
            tmp_path,
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
            dataset_factory=lambda selected: _FakeDataset(selected, calls=calls),
        )
    )

    assert result["status"] == "ready"

    assert calls == [
        {
            "class_name": class_name,
            "path": calls[0]["path"],
            "subjects": [1],
            "overwrite": False,
            "format": output_format,
            "verbose": "ERROR",
            "generate_figures": False,
        }
    ]
    assert ".staging" in calls[0]["path"]
    frozen = json.loads(Path(result["freeze_manifest"]).read_text(encoding="utf-8"))
    row = frozen["datasets"][0]
    assert row["status"] == "ready"
    assert row["source_checksum_status"] == "verified"
    assert row["bids_checksum_status"] == "verified"
    assert all(
        item["checksum"]["algorithm"] == "sha256" for item in row["source_artifacts"]
    )
    bids_names = {item["relative_path"] for item in row["bids_artifacts"]}
    required_suffixes = {
        "EDF": {".edf"},
        "BrainVision": {".vhdr", ".vmrk", ".eeg"},
        "EEGLAB": {".set", ".fdt"},
    }[output_format]
    assert required_suffixes <= {Path(name).suffix for name in bids_names}
    assert Path(row["checksum_manifest"]).is_file()
    assert Path(row["source_checksum_manifest"]).is_file()
    ready_plan = json.loads(Path(result["gui_plan"]).read_text(encoding="utf-8"))
    ready_row = ready_plan["datasets"][0]
    assert ready_row["execution_state"] == "ready"
    assert ready_row["bids"]["root"] == row["bids_root"]
    assert (
        ready_row["bids"]["dataset_revision_sha256"] == row["dataset_revision_sha256"]
    )
    assert ready_row["oracle"] == {
        "state": "pinned",
        "expected_events": ["target", "non-target"],
        "expected_classes": ["target"],
        "source_event_id": {"target": 1, "non-target": 2},
        "expected_product_class_mapping": [
            {"class_index": 0, "event_code": "0", "class_name": "target"}
        ],
        "bids_event_values": {},
        "bids_value_crosscheck": "not-present",
    }
    assert row["bids_validation"]["status"] == "passed"
    assert row["bids_validation"]["error_count"] == 0
    assert len(row["bids_validation"]["report_sha256"]) == 64


def test_materializer_normalizes_scalar_hardware_filter_metadata_before_validation(
    tmp_path: Path,
) -> None:
    manifest_path, gui_plan_path = _write_contracts(tmp_path, class_names=("FakeEDF",))
    seen: list[object] = []

    class DatasetWithLegacyHardwareFilter(_FakeDataset):
        def convert_to_bids(self, **kwargs: Any) -> Path:
            root = super().convert_to_bids(**kwargs)
            sidecar = root / "sub-1" / "eeg" / "sub-1_task-test_eeg.json"
            sidecar.write_text(
                json.dumps(
                    {
                        "TaskName": "test",
                        "HardwareFilters": {
                            "HardwareFilter": "0.01-200 Hz bandpass, 50 Hz notch"
                        },
                    }
                ),
                encoding="utf-8",
            )
            return root

    def validator(root: Path) -> dict[str, Any]:
        sidecar = next(root.rglob("*_eeg.json"))
        value = json.loads(sidecar.read_text(encoding="utf-8"))["HardwareFilters"]
        seen.append(value)
        assert value == {
            "HardwareFilter": {"Description": "0.01-200 Hz bandpass, 50 Hz notch"}
        }
        return _passed_validator(root)

    result = run_materialization(
        _inputs(
            tmp_path,
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
            dataset_factory=lambda name: DatasetWithLegacyHardwareFilter(
                name, calls=[]
            ),
            bids_validator=validator,
        )
    )

    assert result["status"] == "ready"
    assert seen


def test_materializer_downgrades_incomplete_head_montage_for_generic_converter(
    tmp_path: Path,
) -> None:
    import mne
    import numpy as np

    manifest_path, gui_plan_path = _write_contracts(tmp_path, class_names=("FakeEDF",))
    calls: list[dict[str, Any]] = []

    class IncompleteHeadMontageDataset(_FakeDataset):
        def __init__(self, class_name: str, *, calls: list[dict[str, Any]]) -> None:
            super().__init__(class_name, calls=calls)
            raw = mne.io.RawArray(
                np.zeros((2, 100)),
                mne.create_info(["C3", "C4"], 100, ["eeg", "eeg"]),
                verbose="ERROR",
            )
            raw.set_montage(
                mne.channels.make_dig_montage(
                    ch_pos={"C3": (-0.05, 0.0, 0.08), "C4": (0.05, 0.0, 0.08)},
                    coord_frame="head",
                )
            )
            with raw.info._unlock():
                raw.info["dig"] = [
                    point
                    for point in raw.info["dig"]
                    if point["kind"] != mne.io.constants.FIFF.FIFFV_POINT_CARDINAL
                ]
            self.raw = raw

        def get_data(self, *, subjects: list[int]) -> dict[str, Any]:
            assert subjects == [1]
            return {"1": {"0": {"0": self.raw}}}

        def convert_to_bids(self, **kwargs: Any) -> Path:
            raw = self.get_data(subjects=kwargs["subjects"])["1"]["0"]["0"]
            positions = raw.get_montage().get_positions()
            if positions["coord_frame"] == "head" and any(
                positions[name] is None for name in ("nasion", "lpa", "rpa")
            ):
                raise ValueError(
                    "'head' coordinate frame must contain nasion and left/right "
                    "pre-auricular landmarks"
                )
            assert positions["coord_frame"] == "unknown"
            assert set(positions["ch_pos"]) == {"C3", "C4"}
            return super().convert_to_bids(**kwargs)

    result = run_materialization(
        _inputs(
            tmp_path,
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
            dataset_factory=lambda selected: IncompleteHeadMontageDataset(
                selected, calls=calls
            ),
        )
    )

    assert result["status"] == "ready", result["datasets"][0]["error"]


def test_materializer_independently_copies_and_seals_source_seed(
    tmp_path: Path,
) -> None:
    manifest_path, gui_plan_path = _write_contracts(tmp_path, class_names=("FakeEDF",))
    seed_root = tmp_path / "independent-seed"
    seeded_file = seed_root / "download" / "prefetched.zip"
    seeded_file.parent.mkdir(parents=True)
    seeded_file.write_bytes(b"prefetched-upstream-bytes")
    stale_config = seed_root / ".mne-config/.mne/mne-python.json"
    stale_config.parent.mkdir(parents=True)
    stale_config.write_text('{"MNE_DATA":"/stale/staging"}', encoding="utf-8")
    calls: list[dict[str, Any]] = []

    class SeedAwareDataset(_FakeDataset):
        def convert_to_bids(self, **kwargs: Any) -> Path:
            staged_seed = Path(os.environ["MNE_DATA"]) / "download/prefetched.zip"
            assert staged_seed.read_bytes() == b"prefetched-upstream-bytes"
            return super().convert_to_bids(**kwargs)

    result = run_materialization(
        _inputs(
            tmp_path,
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
            dataset="FakeEDF",
            source_seed_root=seed_root,
            dataset_factory=lambda selected: SeedAwareDataset(selected, calls=calls),
        )
    )

    assert result["status"] == "ready"
    receipt = json.loads(
        (tmp_path / "checksums/FakeEDF.freeze.json").read_text(encoding="utf-8")
    )
    assert receipt["source_seed_receipt"] == {
        "schema_version": "1.0.0",
        "kind": "independent-copy",
        "source_root": str(seed_root),
        "revision_sha256": receipt["source_seed_receipt"]["revision_sha256"],
        "artifact_count": 1,
        "total_bytes": len(b"prefetched-upstream-bytes"),
    }
    assert (
        tmp_path / "source-cache/FakeEDF/download/prefetched.zip"
    ).read_bytes() == b"prefetched-upstream-bytes"
    published_config = (
        tmp_path / "source-cache/FakeEDF/.mne-config/.mne/mne-python.json"
    )
    assert not published_config.exists() or "/stale/staging" not in (
        published_config.read_text(encoding="utf-8")
    )


def test_materializer_excludes_runtime_mne_config_from_source_freeze(
    tmp_path: Path,
) -> None:
    manifest_path, gui_plan_path = _write_contracts(tmp_path, class_names=("FakeEDF",))
    lock_path = tmp_path / "source-cache/FakeEDF/.mne-config/.mne/mne-python.json.lock"

    class RuntimeConfigDataset(_FakeDataset):
        def convert_to_bids(self, **kwargs: Any) -> Path:
            runtime_lock = (
                Path(os.environ["_MNE_FAKE_HOME_DIR"]) / ".mne/mne-python.json.lock"
            )
            runtime_lock.parent.mkdir(parents=True, exist_ok=True)
            runtime_lock.write_bytes(b"")
            return super().convert_to_bids(**kwargs)

    def validator(root: Path) -> dict[str, Any]:
        staged_lock = next(
            (tmp_path / "source-cache/FakeEDF/.mne-config").rglob("*.lock")
        )
        staged_lock.write_bytes(b"runtime-only-validator-state")
        return _passed_validator(root)

    result = run_materialization(
        _inputs(
            tmp_path,
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
            dataset_factory=lambda selected: RuntimeConfigDataset(selected, calls=[]),
            bids_validator=validator,
        )
    )

    assert result["status"] == "ready"
    assert lock_path.read_bytes() == b"runtime-only-validator-state"
    frozen = json.loads(Path(result["freeze_manifest"]).read_text(encoding="utf-8"))
    row = frozen["datasets"][0]
    assert all(
        ".mne-config" not in Path(item["relative_path"]).parts
        for item in row["source_artifacts"]
    )
    assert ".mne-config" not in Path(row["source_checksum_manifest"]).read_text(
        encoding="utf-8"
    )

    lock_path.write_bytes(b"background-runtime-update")
    replay = run_materialization(
        _inputs(
            tmp_path,
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
            dataset_factory=lambda selected: RuntimeConfigDataset(selected, calls=[]),
            allow_download=False,
            bids_validator=validator,
        )
    )
    assert replay["status"] == "ready"
    assert replay["datasets"][0]["action"] == "reused"

    changed_environment = _environment()
    changed_environment["git"]["commit"] = "9" * 40
    changed_environment["campaign_product_identity_sha256"] = (
        _campaign_product_identity_digest(changed_environment)
    )
    changed_environment["identity_sha256"] = changed_environment[
        "campaign_product_identity_sha256"
    ]
    resealed = run_materialization(
        _inputs(
            tmp_path,
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
            dataset_factory=lambda selected: RuntimeConfigDataset(selected, calls=[]),
            environment_identity=changed_environment,
            allow_download=False,
            bids_validator=validator,
        )
    )
    assert resealed["status"] == "ready"
    assert resealed["datasets"][0]["action"] == "resealed"


def test_materializer_migrates_legacy_runtime_source_inventory_without_download(
    tmp_path: Path,
) -> None:
    manifest_path, gui_plan_path = _write_contracts(tmp_path, class_names=("FakeEDF",))
    calls: list[dict[str, Any]] = []
    common = {
        "manifest_path": manifest_path,
        "gui_plan_path": gui_plan_path,
        "dataset_factory": lambda selected: _FakeDataset(selected, calls=calls),
    }
    cold = run_materialization(_inputs(tmp_path, **common))
    assert cold["status"] == "ready"

    receipt_path = tmp_path / "checksums/FakeEDF.freeze.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    lock_path = tmp_path / "source-cache/FakeEDF/.mne-config/.mne/mne-python.json.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_bytes(b"")
    legacy_artifact = {
        "relative_path": ".mne-config/.mne/mne-python.json.lock",
        "size_bytes": 0,
        "checksum": {
            "algorithm": "sha256",
            "value": hashlib.sha256(b"").hexdigest(),
        },
    }
    legacy_artifacts = sorted(
        [*receipt["source_artifacts"], legacy_artifact],
        key=lambda item: item["relative_path"],
    )
    receipt["source_artifacts"] = legacy_artifacts
    receipt["source_revision_sha256"] = _canonical_sha256(legacy_artifacts)
    receipt["retained_source_bytes"] = sum(
        item["size_bytes"] for item in legacy_artifacts
    )
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    Path(receipt["source_checksum_manifest"]).write_text(
        "".join(
            f"{item['checksum']['value']}  {item['relative_path']}\n"
            for item in legacy_artifacts
        ),
        encoding="utf-8",
    )

    migrated = run_materialization(_inputs(tmp_path, allow_download=False, **common))

    assert migrated["status"] == "ready"
    assert migrated["network_used"] is False
    assert migrated["datasets"][0]["action"] == "resealed"
    assert len(calls) == 1
    migrated_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert all(
        ".mne-config" not in Path(item["relative_path"]).parts
        for item in migrated_receipt["source_artifacts"]
    )
    assert ".mne-config" not in Path(
        migrated_receipt["source_checksum_manifest"]
    ).read_text(encoding="utf-8")


def test_materializer_keeps_source_and_bids_event_codes_as_distinct_oracles(
    tmp_path: Path,
) -> None:
    manifest_path, gui_plan_path = _write_contracts(tmp_path, class_names=("FakeEDF",))
    calls: list[dict[str, Any]] = []

    result = run_materialization(
        _inputs(
            tmp_path,
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
            dataset_factory=lambda selected: _FakeDataset(
                selected,
                calls=calls,
                bids_event_id={"non-target": 1, "target": 2},
            ),
        )
    )

    assert result["status"] == "ready"
    frozen = json.loads(Path(result["freeze_manifest"]).read_text(encoding="utf-8"))
    assert frozen["datasets"][0]["event_id"] == {"target": 1, "non-target": 2}
    assert frozen["datasets"][0]["bids_event_values"] == {
        "target": 2,
        "non-target": 1,
    }
    ready = json.loads(Path(result["gui_plan"]).read_text(encoding="utf-8"))
    oracle = ready["datasets"][0]["oracle"]
    assert oracle["source_event_id"] == {"target": 1, "non-target": 2}
    assert oracle["bids_event_values"] == {"target": 2, "non-target": 1}
    assert oracle["expected_product_class_mapping"] == [
        {"class_index": 0, "event_code": "0", "class_name": "target"}
    ]


def test_materializer_accepts_run_local_bids_values_without_losing_labels(
    tmp_path: Path,
) -> None:
    manifest_path, gui_plan_path = _write_contracts(tmp_path, class_names=("FakeEDF",))
    calls: list[dict[str, Any]] = []

    result = run_materialization(
        _inputs(
            tmp_path,
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
            dataset_factory=lambda selected: _FakeDataset(
                selected,
                calls=calls,
                bids_event_id_by_run=[
                    {"target": 1, "non-target": 2},
                    {"target": 2, "non-target": 1},
                ],
            ),
        )
    )

    assert result["status"] == "ready"
    frozen = json.loads(Path(result["freeze_manifest"]).read_text(encoding="utf-8"))
    row = frozen["datasets"][0]
    assert row["event_names"] == ["target", "non-target"]
    assert row["event_id"] == {"target": 1, "non-target": 2}
    assert row["bids_event_values"] == {}
    assert row["bids_value_crosscheck"] == "run-local"
    ready = json.loads(Path(result["gui_plan"]).read_text(encoding="utf-8"))
    oracle = ready["datasets"][0]["oracle"]
    assert oracle["expected_events"] == ["target", "non-target"]
    assert oracle["source_event_id"] == {"target": 1, "non-target": 2}
    assert oracle["bids_event_values"] == {}
    assert oracle["bids_value_crosscheck"] == "run-local"
    assert oracle["expected_product_class_mapping"] == [
        {"class_index": 0, "event_code": "0", "class_name": "target"}
    ]


def test_formal_bids_mirror_preserves_bdf_and_separates_upstream_from_source(
    tmp_path: Path,
) -> None:
    manifest_path, gui_plan_path, raw_manifest, payloads = _write_mirror_contracts(
        tmp_path
    )
    manifest_calls: list[tuple[str, frozenset[str], int]] = []
    download_calls: list[str] = []
    payload_by_url = {
        f"https://mirror.invalid/v1/{relative_path}": payload
        for relative_path, payload in payloads.items()
    }

    def _fetch(url: str, hosts: frozenset[str], maximum: int) -> bytes:
        manifest_calls.append((url, hosts, maximum))
        return raw_manifest

    def _download(
        url: str,
        target: Path,
        hosts: frozenset[str],
        expected_bytes: int,
    ) -> dict[str, Any]:
        download_calls.append(url)
        payload = payload_by_url[url]
        assert len(payload) == expected_bytes
        assert hosts == frozenset({"mirror.invalid", "objects.invalid"})
        target.write_bytes(payload)
        return {
            "final_url": f"https://objects.invalid/{target.name}",
            "size_bytes": len(payload),
        }

    result = run_materialization(
        _inputs(
            tmp_path,
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
            dataset_factory=lambda _selected: (_ for _ in ()).throw(
                AssertionError("formal BIDS mirror must not instantiate MOABB")
            ),
            mirror_manifest_fetcher=_fetch,
            mirror_file_downloader=_download,
        )
    )

    assert result["status"] == "ready"
    assert manifest_calls == [
        (
            "https://mirror.invalid/v1/manifest.json",
            frozenset({"mirror.invalid"}),
            64 * 1024,
        )
    ]
    assert len(download_calls) == 7
    assert all("sub-3/" not in url for url in download_calls)
    frozen = json.loads(Path(result["freeze_manifest"]).read_text("utf-8"))
    row = frozen["datasets"][0]
    assert row["source_mode"] == "formal_bids_mirror"
    assert row["output_format"] == "BDF"
    assert row["upstream_download_status"] == "verified"
    assert row["upstream_download_bytes"] == row["source_download_bytes"]
    assert row["retained_source_bytes"] < row["upstream_download_bytes"]
    assert row["retained_source_bytes"] == sum(
        item["size_bytes"] for item in row["source_artifacts"]
    )
    assert row["upstream_download_bytes"] == sum(
        item["size_bytes"] for item in row["bids_artifacts"]
    )
    assert [
        {
            "relative_path": item["relative_path"],
            "size_bytes": item["size_bytes"],
            "checksum": item["checksum"],
        }
        for item in row["upstream_download_artifacts"]
    ] == row["bids_artifacts"]
    assert {Path(item["relative_path"]).suffix for item in row["bids_artifacts"]} >= {
        ".bdf",
        ".tsv",
    }
    assert row["event_id"] == {"right_hand": 2, "right_elbow": 1}
    assert row["bids_event_values"] == {"right_hand": 2, "right_elbow": 1}
    assert row["bids_value_crosscheck"] == "formal-bids-mirror-authoritative"
    assert {
        item["upstream_checksum"]["algorithm"]
        for item in row["upstream_download_artifacts"]
    } == {"git", "sha256"}
    ready_plan = json.loads(Path(result["gui_plan"]).read_text("utf-8"))
    ready_row = ready_plan["datasets"][0]
    assert ready_row["source_mode"] == "formal_bids_mirror"
    assert ready_row["bids"]["format"] == "BDF"
    assert ready_row["bids"]["root_resolution"]["source"] == (
        "formal_bids_mirror_receipt"
    )
    assert ready_row["bids"]["root"] == row["bids_root"]


def test_formal_bids_mirror_replay_and_no_download_never_touch_network(
    tmp_path: Path,
) -> None:
    manifest_path, gui_plan_path, raw_manifest, payloads = _write_mirror_contracts(
        tmp_path
    )
    payload_by_url = {
        f"https://mirror.invalid/v1/{relative_path}": payload
        for relative_path, payload in payloads.items()
    }

    def _download(
        url: str,
        target: Path,
        _hosts: frozenset[str],
        _expected_bytes: int,
    ) -> dict[str, Any]:
        target.write_bytes(payload_by_url[url])
        return {"final_url": url, "size_bytes": len(payload_by_url[url])}

    cold = run_materialization(
        _inputs(
            tmp_path,
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
            dataset_factory=lambda _selected: None,
            mirror_manifest_fetcher=lambda _url, _hosts, _maximum: raw_manifest,
            mirror_file_downloader=_download,
        )
    )
    frozen = json.loads(Path(cold["freeze_manifest"]).read_text("utf-8"))
    roots = (
        Path(frozen["datasets"][0]["source_root"]),
        Path(frozen["datasets"][0]["bids_root"]),
    )
    before = {
        str(path): (path.read_bytes(), path.stat().st_mtime_ns)
        for root in roots
        for path in root.rglob("*")
        if path.is_file()
    }

    replay = run_materialization(
        _inputs(
            tmp_path,
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
            dataset_factory=lambda _selected: (_ for _ in ()).throw(
                AssertionError("replay must not instantiate MOABB")
            ),
            allow_download=False,
        )
    )
    after = {
        str(path): (path.read_bytes(), path.stat().st_mtime_ns)
        for root in roots
        for path in root.rglob("*")
        if path.is_file()
    }

    assert replay["status"] == "ready"
    assert replay["datasets"][0]["action"] == "reused"
    assert after == before


def test_formal_bids_mirror_dry_run_and_missing_no_download_are_network_free(
    tmp_path: Path,
) -> None:
    manifest_path, gui_plan_path, _raw_manifest, _payloads = _write_mirror_contracts(
        tmp_path
    )
    calls: list[str] = []

    def _fetch(_url: str, _hosts: frozenset[str], _maximum: int) -> bytes:
        calls.append("manifest")
        raise AssertionError("network is forbidden")

    def _download(
        _url: str,
        _target: Path,
        _hosts: frozenset[str],
        _maximum: int,
    ) -> dict[str, Any]:
        calls.append("download")
        raise AssertionError("network is forbidden")

    common = {
        "manifest_path": manifest_path,
        "gui_plan_path": gui_plan_path,
        "dataset_factory": lambda _selected: None,
        "mirror_manifest_fetcher": _fetch,
        "mirror_file_downloader": _download,
        "allow_download": False,
    }
    dry_run = run_materialization(_inputs(tmp_path, dry_run=True, **common))
    no_download = run_materialization(_inputs(tmp_path, **common))

    assert dry_run["status"] == "dry-run-ready"
    assert dry_run["datasets"][0]["output_format"] == "BDF"
    assert dry_run["datasets"][0]["source_mode"] == "formal_bids_mirror"
    assert dry_run["datasets"][0]["resource_preflight_required"] is True
    assert no_download["status"] == "blocked"
    assert "allow-download" in no_download["datasets"][0]["error"]
    assert calls == []


def test_formal_bids_mirror_rejects_signed_urls_even_when_projection_is_repinned(
    tmp_path: Path,
) -> None:
    manifest_path, gui_plan_path, raw_manifest, _payloads = _write_mirror_contracts(
        tmp_path
    )
    entries = json.loads(raw_manifest)
    entries[0]["bytes_url"] += "?temporary-signature=1"
    entries.sort(key=lambda item: item["path"])
    manifest = json.loads(manifest_path.read_text("utf-8"))
    policy = manifest["datasets"][0]["formal_bids_mirror"]
    policy["full_projection"] = {
        "entry_count": len(entries),
        "total_bytes": sum(item["size"] for item in entries),
        "projection_sha256": _canonical_sha256(entries),
    }
    selected = [
        entry
        for entry in entries
        if entry["path"] in {"dataset_description.json", "participants.tsv"}
        or entry["path"].startswith("code/")
        or entry["path"].split("/", 1)[0] in {"sub-1", "sub-2"}
    ]
    policy["selected_projection"] = {
        "entry_count": len(selected),
        "total_bytes": sum(item["size"] for item in selected),
        "projection_sha256": _canonical_sha256(selected),
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    downloads: list[str] = []

    result = run_materialization(
        _inputs(
            tmp_path,
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
            dataset_factory=lambda _selected: None,
            mirror_manifest_fetcher=lambda _url, _hosts, _maximum: json.dumps(
                entries
            ).encode(),
            mirror_file_downloader=lambda url, _target, _hosts, _maximum: (
                downloads.append(url) or {}
            ),
        )
    )

    assert result["status"] == "blocked"
    assert "stable, HTTPS, and allowlisted" in result["datasets"][0]["error"]
    assert downloads == []
    assert not (tmp_path / "source-cache" / "FakeMirror").exists()
    assert not (tmp_path / "bids-output" / "FakeMirror").exists()


def test_formal_bids_mirror_checksum_failure_quarantines_partial_tree(
    tmp_path: Path,
) -> None:
    manifest_path, gui_plan_path, raw_manifest, payloads = _write_mirror_contracts(
        tmp_path
    )
    payload_by_url = {
        f"https://mirror.invalid/v1/{relative_path}": payload
        for relative_path, payload in payloads.items()
    }

    def _download(
        url: str,
        target: Path,
        _hosts: frozenset[str],
        _expected_bytes: int,
    ) -> dict[str, Any]:
        payload = payload_by_url[url]
        if url.endswith("dataset_description.json"):
            payload = bytes([payload[0] ^ 1]) + payload[1:]
        target.write_bytes(payload)
        return {"final_url": url, "size_bytes": len(payload)}

    result = run_materialization(
        _inputs(
            tmp_path,
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
            dataset_factory=lambda _selected: None,
            mirror_manifest_fetcher=lambda _url, _hosts, _maximum: raw_manifest,
            mirror_file_downloader=_download,
        )
    )

    assert result["status"] == "blocked"
    assert result["datasets"][0]["action"] == "quarantined"
    assert "checksum changed" in result["datasets"][0]["error"]
    assert not (tmp_path / "source-cache" / "FakeMirror").exists()
    assert not (tmp_path / "bids-output" / "FakeMirror").exists()
    assert list((tmp_path / "bids-output" / ".quarantine").rglob("provenance.json"))
    ready = json.loads(Path(result["gui_plan"]).read_text("utf-8"))
    assert ready["datasets"][0]["execution_state"] == (
        "awaiting_dataset_materialization"
    )


def test_replay_verifies_receipt_without_conversion_or_touching_data_bytes(
    tmp_path: Path,
) -> None:
    manifest_path, gui_plan_path = _write_contracts(tmp_path, class_names=("FakeEDF",))
    calls: list[dict[str, Any]] = []
    cold_inputs = _inputs(
        tmp_path,
        manifest_path=manifest_path,
        gui_plan_path=gui_plan_path,
        dataset_factory=lambda selected: _FakeDataset(selected, calls=calls),
    )
    cold = run_materialization(cold_inputs)
    frozen = json.loads(Path(cold["freeze_manifest"]).read_text(encoding="utf-8"))
    source_root = Path(frozen["datasets"][0]["source_root"])
    bids_root = Path(frozen["datasets"][0]["bids_root"])
    observed_before = {
        str(path): (path.read_bytes(), path.stat().st_mtime_ns)
        for root in (source_root, bids_root)
        for path in root.rglob("*")
        if path.is_file()
    }

    replay = run_materialization(
        _inputs(
            tmp_path,
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
            dataset_factory=lambda _selected: (_ for _ in ()).throw(
                AssertionError("replay must not instantiate MOABB")
            ),
            allow_download=False,
        )
    )
    observed_after = {
        str(path): (path.read_bytes(), path.stat().st_mtime_ns)
        for root in (source_root, bids_root)
        for path in root.rglob("*")
        if path.is_file()
    }

    assert replay["status"] == "ready"
    assert replay["datasets"][0]["action"] == "reused"
    assert calls and len(calls) == 1
    assert observed_after == observed_before


def test_no_download_replay_reserves_only_artifact_headroom(tmp_path: Path) -> None:
    manifest_path, gui_plan_path = _write_contracts(tmp_path, class_names=("FakeEDF",))
    cold = run_materialization(
        _inputs(
            tmp_path,
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
            dataset_factory=lambda selected: _FakeDataset(selected, calls=[]),
        )
    )
    assert cold["status"] == "ready"

    replay = run_materialization(
        _inputs(
            tmp_path,
            allow_download=False,
            free_bytes=512,
            dataset_factory=lambda _selected: (_ for _ in ()).throw(
                AssertionError("replay must not instantiate MOABB")
            ),
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
        )
    )
    insufficient = run_materialization(
        _inputs(
            tmp_path,
            allow_download=False,
            free_bytes=511,
            dataset_factory=lambda _selected: (_ for _ in ()).throw(
                AssertionError("blocked replay must not instantiate MOABB")
            ),
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
        )
    )

    assert replay["status"] == "ready"
    assert replay["headroom_phase"] == "frozen-replay"
    assert replay["required_headroom_bytes"] == 512
    assert insufficient["status"] == "blocked"
    assert insufficient["required_headroom_bytes"] == 512
    assert any("free space" in item for item in insufficient["blockers"])


def test_stale_checksum_invalidates_ready_then_rebuilds_through_quarantine(
    tmp_path: Path,
) -> None:
    manifest_path, gui_plan_path = _write_contracts(tmp_path, class_names=("FakeEDF",))
    calls: list[dict[str, Any]] = []
    inputs = _inputs(
        tmp_path,
        manifest_path=manifest_path,
        gui_plan_path=gui_plan_path,
        dataset_factory=lambda selected: _FakeDataset(selected, calls=calls),
    )
    cold = run_materialization(inputs)
    frozen = json.loads(Path(cold["freeze_manifest"]).read_text(encoding="utf-8"))
    bids_root = Path(frozen["datasets"][0]["bids_root"])
    raw_file = next(bids_root.rglob("*.edf"))
    raw_file.write_bytes(b"stale replacement")

    rebuilt = run_materialization(inputs)

    assert rebuilt["status"] == "ready"
    assert rebuilt["datasets"][0]["action"] == "rebuilt"
    assert len(calls) == 2
    assert (
        next(Path(rebuilt["datasets"][0]["bids_root"]).rglob("*.edf")).read_bytes()
        == b"synthetic-edf"
    )
    quarantined = list((tmp_path / "bids-output" / ".quarantine").rglob("*.edf"))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == b"stale replacement"


def test_gui_preflight_rehash_rejects_exact_tree_drift_and_symlinks(
    tmp_path: Path,
) -> None:
    manifest_path, gui_plan_path = _write_contracts(
        tmp_path,
        class_names=("FakeEDF",),
    )
    materialized = run_materialization(
        _inputs(
            tmp_path,
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
            dataset_factory=lambda selected: _FakeDataset(selected, calls=[]),
        )
    )
    frozen = json.loads(Path(materialized["freeze_manifest"]).read_text("utf-8"))
    row = frozen["datasets"][0]
    root = Path(row["bids_root"])
    checksum_manifest = Path(row["checksum_manifest"])

    assert (
        bids_tree_integrity_error(
            root=root,
            checksum_manifest=checksum_manifest,
            expected_revision_sha256=row["dataset_revision_sha256"],
        )
        is None
    )

    extra = root / "untracked.txt"
    extra.write_text("extra", encoding="utf-8")
    assert "aggregate checksum changed" in str(
        bids_tree_integrity_error(
            root=root,
            checksum_manifest=checksum_manifest,
            expected_revision_sha256=row["dataset_revision_sha256"],
        )
    )
    extra.unlink()

    symlink = root / "linked.edf"
    symlink.symlink_to(next(root.rglob("*.edf")))
    assert "symbolic-link" in str(
        bids_tree_integrity_error(
            root=root,
            checksum_manifest=checksum_manifest,
            expected_revision_sha256=row["dataset_revision_sha256"],
        )
    )


def test_selected_refresh_cannot_publish_unselected_stale_dataset_ready(
    tmp_path: Path,
) -> None:
    manifest_path, gui_plan_path = _write_contracts(
        tmp_path, class_names=("FakeEDF", "FakeBrainVision")
    )
    calls: list[dict[str, Any]] = []
    common = {
        "manifest_path": manifest_path,
        "gui_plan_path": gui_plan_path,
        "dataset_factory": lambda selected: _FakeDataset(selected, calls=calls),
    }
    cold = run_materialization(_inputs(tmp_path, **common))
    assert cold["campaign_ready"] is True
    frozen = json.loads(Path(cold["freeze_manifest"]).read_text(encoding="utf-8"))
    stale_root = Path(
        next(
            row["bids_root"]
            for row in frozen["datasets"]
            if row["moabb_class"] == "FakeEDF"
        )
    )
    next(stale_root.rglob("*.edf")).write_bytes(b"stale-unselected")

    selected = run_materialization(
        _inputs(tmp_path, dataset="FakeBrainVision", **common)
    )
    republished = json.loads(
        Path(selected["freeze_manifest"]).read_text(encoding="utf-8")
    )
    rows = {row["moabb_class"]: row for row in republished["datasets"]}

    assert selected["status"] == "ready"
    assert selected["campaign_ready"] is False
    assert republished["status"] == "partial"
    assert rows["FakeEDF"]["status"] == "pending"
    assert rows["FakeEDF"]["bids_checksum_status"] == "ABSENT"
    assert rows["FakeBrainVision"]["status"] == "ready"


def test_progressive_publish_rehashes_after_validation_and_again_at_final_seal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.dev import moabb_dataset_materializer as materializer

    manifest_path, gui_plan_path = _write_contracts(tmp_path)
    original_hash_tree = materializer._hash_tree
    hash_roots: list[str] = []

    def _counted_hash_tree(
        root: Path, *, ignored_root_names: frozenset[str] = frozenset()
    ):
        hash_roots.append(str(root))
        return original_hash_tree(root, ignored_root_names=ignored_root_names)

    monkeypatch.setattr(materializer, "_hash_tree", _counted_hash_tree)
    calls: list[dict[str, Any]] = []
    common = {
        "manifest_path": manifest_path,
        "gui_plan_path": gui_plan_path,
        "dataset_factory": lambda selected: _FakeDataset(selected, calls=calls),
    }

    first = run_materialization(_inputs(tmp_path, dataset="FakeEDF", **common))
    second = run_materialization(_inputs(tmp_path, dataset="FakeBrainVision", **common))
    final = run_materialization(_inputs(tmp_path, dataset="FakeEEGLAB", **common))

    assert first["campaign_ready"] is False
    assert second["campaign_ready"] is False
    assert final["campaign_ready"] is True
    # Every new source/BIDS tree is bound before and verified after the external
    # validator.  The final ready seal then re-hashes all three datasets in one
    # last pass; partial campaign publications do not rehash prior datasets.
    assert len(hash_roots) == 18


def test_partial_failure_is_quarantined_and_never_published_ready(
    tmp_path: Path,
) -> None:
    manifest_path, gui_plan_path = _write_contracts(
        tmp_path, class_names=("FakeBrainVision",)
    )
    calls: list[dict[str, Any]] = []

    result = run_materialization(
        _inputs(
            tmp_path,
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
            dataset_factory=lambda selected: _FakeDataset(
                selected, calls=calls, fail=True
            ),
        )
    )

    assert result["status"] == "blocked"
    assert result["datasets"][0]["status"] == "failed"
    assert not (tmp_path / "bids-output" / "FakeBrainVision").exists()
    assert not (tmp_path / "source-cache" / "FakeBrainVision").exists()
    assert list((tmp_path / "bids-output" / ".quarantine").rglob("partial.txt"))
    ready_plan = json.loads(Path(result["gui_plan"]).read_text(encoding="utf-8"))
    assert (
        ready_plan["datasets"][0]["execution_state"]
        == "awaiting_dataset_materialization"
    )
    assert ready_plan["datasets"][0]["bids"]["root"] is None


def test_dry_run_and_no_download_fail_before_side_effects(tmp_path: Path) -> None:
    manifest_path, gui_plan_path = _write_contracts(tmp_path, class_names=("FakeEDF",))
    factory = lambda _selected: (_ for _ in ()).throw(  # noqa: E731
        AssertionError("no-download modes must not instantiate MOABB")
    )

    dry_run = run_materialization(
        _inputs(
            tmp_path,
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
            dataset_factory=factory,
            dry_run=True,
            allow_download=False,
        )
    )
    no_download = run_materialization(
        _inputs(
            tmp_path,
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
            dataset_factory=factory,
            allow_download=False,
        )
    )

    assert dry_run["status"] == "dry-run-ready"
    assert dry_run["network_used"] is False
    assert not (tmp_path / "source-cache").exists()
    assert no_download["status"] == "blocked"
    assert "allow-download" in no_download["datasets"][0]["error"]


def test_one_dataset_selector_disk_and_resource_preflight_are_fail_closed(
    tmp_path: Path,
) -> None:
    policy = {
        "kind": "http_range",
        "resources": [
            {
                "url": "https://example.invalid/source.bin",
                "maximum_bytes": 128,
            }
        ],
        "maximum_total_bytes": 128,
        "allowed_hosts": ["example.invalid"],
        "accepted_statuses": [200, 206],
        "denied_content_types": ["text/html"],
        "denied_body_markers": ["access denied"],
    }
    manifest_path, gui_plan_path = _write_contracts(
        tmp_path,
        class_names=("FakeEDF", "FakeBrainVision"),
        resource_preflight=policy,
    )
    calls: list[dict[str, Any]] = []
    common = {
        "manifest_path": manifest_path,
        "gui_plan_path": gui_plan_path,
        "dataset_factory": lambda selected: _FakeDataset(selected, calls=calls),
        "dataset": "FakeBrainVision",
    }

    disk_blocked = run_materialization(_inputs(tmp_path, free_bytes=1, **common))
    waf_blocked = run_materialization(
        _inputs(
            tmp_path,
            resource_probe=lambda _resource: {
                "status": "blocked",
                "reason": "HTML WAF challenge",
            },
            **common,
        )
    )
    selected = run_materialization(_inputs(tmp_path, **common))

    assert disk_blocked["status"] == "blocked"
    assert "free space" in disk_blocked["blockers"][0]
    assert waf_blocked["status"] == "blocked"
    assert waf_blocked["datasets"][0]["dataset"] == "FakeBrainVision"
    assert "resource preflight" in waf_blocked["datasets"][0]["error"]
    assert selected["status"] == "ready"
    assert selected["campaign_ready"] is False
    assert selected["datasets"] == [
        {
            "dataset": "FakeBrainVision",
            "status": "ready",
            "action": "materialized",
            "bids_root": selected["datasets"][0]["bids_root"],
            "dataset_revision_sha256": selected["datasets"][0][
                "dataset_revision_sha256"
            ],
        }
    ]
    assert [call["class_name"] for call in calls] == ["FakeBrainVision"]


def test_environment_change_blocks_replay_and_source_has_no_dataset_branches(
    tmp_path: Path,
) -> None:
    manifest_path, gui_plan_path = _write_contracts(
        tmp_path, class_names=("FakeEEGLAB",)
    )
    calls: list[dict[str, Any]] = []
    run_materialization(
        _inputs(
            tmp_path,
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
            dataset_factory=lambda selected: _FakeDataset(selected, calls=calls),
        )
    )

    changed = run_materialization(
        _inputs(
            tmp_path,
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
            dataset_factory=lambda _selected: (_ for _ in ()).throw(
                AssertionError("changed replay must fail before conversion")
            ),
            allow_download=False,
            environment_identity={
                **_environment("f" * 64),
            },
        )
    )

    assert changed["status"] == "blocked"
    assert changed["datasets"] == []
    assert "environment identity" in changed["blockers"][0]
    product_source = (
        Path(__file__).resolve().parents[3]
        / "scripts/dev/moabb_dataset_materializer.py"
    ).read_text(encoding="utf-8")
    assert 'getattr(dataset, "convert_to_bids", None)' in product_source
    assert "converter(" in product_source
    for dataset_name in (
        "BNCI2014_001",
        "PhysionetMI",
        "Lee2021Mobile_ERP",
        "BNCI2014_009",
        "Nakanishi2015",
        "Ofner2017",
        "Ma2020",
        "ErpCore2021_P3",
        "Wang2016",
        "Chen2017SingleFlicker",
        "Thielen2021",
        "Hinss2021",
        "MAMEM1",
        "GuttmannFlury2025_SSVEP",
        "Zhou2020",
    ):
        assert dataset_name not in product_source


def test_commit_only_change_rehashes_revalidates_and_reseals_without_conversion(
    tmp_path: Path,
) -> None:
    manifest_path, gui_plan_path = _write_contracts(tmp_path, class_names=("FakeEDF",))
    calls: list[dict[str, Any]] = []
    validation_calls: list[str] = []
    cold_environment = _environment()
    common = {
        "manifest_path": manifest_path,
        "gui_plan_path": gui_plan_path,
        "dataset_factory": lambda selected: _FakeDataset(selected, calls=calls),
        "bids_validator": lambda root: (
            validation_calls.append(str(root)) or _passed_validator(root)
        ),
    }
    cold = run_materialization(
        _inputs(tmp_path, environment_identity=cold_environment, **common)
    )
    frozen = json.loads(Path(cold["freeze_manifest"]).read_text(encoding="utf-8"))
    source_root = Path(frozen["datasets"][0]["source_root"])
    bids_root = Path(frozen["datasets"][0]["bids_root"])
    before = {
        str(path): (path.read_bytes(), path.stat().st_mtime_ns)
        for root in (source_root, bids_root)
        for path in root.rglob("*")
        if path.is_file()
    }
    changed_environment = json.loads(json.dumps(cold_environment))
    changed_environment["git"]["commit"] = "9" * 40
    changed_environment["git"]["tree"] = "8" * 40
    product_digest = _campaign_product_identity_digest(changed_environment)
    changed_environment["campaign_product_identity_sha256"] = product_digest
    changed_environment["identity_sha256"] = product_digest

    resealed = run_materialization(
        _inputs(
            tmp_path,
            environment_identity=changed_environment,
            allow_download=False,
            **common,
        )
    )
    after = {
        str(path): (path.read_bytes(), path.stat().st_mtime_ns)
        for root in (source_root, bids_root)
        for path in root.rglob("*")
        if path.is_file()
    }
    receipt = json.loads(
        (tmp_path / "checksums" / "FakeEDF.freeze.json").read_text("utf-8")
    )

    assert resealed["status"] == "ready"
    assert resealed["datasets"][0]["action"] == "resealed"
    assert len(calls) == 1
    assert len(validation_calls) == 2
    assert after == before
    assert (
        receipt["campaign_product_identity_sha256"]
        == changed_environment["campaign_product_identity_sha256"]
    )
    assert (
        receipt["conversion_identity_sha256"]
        == cold_environment["conversion_identity_sha256"]
    )


def test_validator_induced_tree_drift_blocks_reseal_and_preserves_ready_seals(
    tmp_path: Path,
) -> None:
    manifest_path, gui_plan_path = _write_contracts(tmp_path, class_names=("FakeEDF",))
    calls: list[dict[str, Any]] = []
    common = {
        "manifest_path": manifest_path,
        "gui_plan_path": gui_plan_path,
        "dataset_factory": lambda selected: _FakeDataset(selected, calls=calls),
    }
    cold_environment = _environment()
    cold = run_materialization(
        _inputs(tmp_path, environment_identity=cold_environment, **common)
    )
    receipt_path = tmp_path / "checksums" / "FakeEDF.freeze.json"
    report_path = tmp_path / "checksums" / "bids-validation" / "FakeEDF.json"
    freeze_path = Path(cold["freeze_manifest"])
    ready_plan_path = Path(cold["gui_plan"])
    sealed_before = {
        path: path.read_bytes()
        for path in (receipt_path, report_path, freeze_path, ready_plan_path)
    }
    frozen = json.loads(freeze_path.read_text("utf-8"))
    raw_file = next(Path(frozen["datasets"][0]["bids_root"]).rglob("*.edf"))
    changed_environment = json.loads(json.dumps(cold_environment))
    changed_environment["git"]["commit"] = "6" * 40
    product_digest = _campaign_product_identity_digest(changed_environment)
    changed_environment["campaign_product_identity_sha256"] = product_digest
    changed_environment["identity_sha256"] = product_digest

    def drifting_validator(root: Path) -> dict[str, Any]:
        assert root == raw_file.parents[2]
        raw_file.write_bytes(b"validator-induced-drift")
        return _passed_validator(root)

    failed = run_materialization(
        _inputs(
            tmp_path,
            environment_identity=changed_environment,
            allow_download=False,
            bids_validator=drifting_validator,
            **common,
        )
    )

    assert failed["status"] == "blocked"
    assert failed["campaign_ready"] is False
    assert failed["datasets"][0]["action"] == "reseal-blocked"
    assert "checksum inventory changed" in failed["datasets"][0]["error"]
    assert {path: path.read_bytes() for path in sealed_before} == sealed_before


def test_validator_induced_tree_drift_never_creates_a_cold_ready_row(
    tmp_path: Path,
) -> None:
    manifest_path, gui_plan_path = _write_contracts(tmp_path, class_names=("FakeEDF",))

    def drifting_validator(root: Path) -> dict[str, Any]:
        next(root.rglob("*.edf")).write_bytes(b"validator-induced-drift")
        return _passed_validator(root)

    failed = run_materialization(
        _inputs(
            tmp_path,
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
            dataset_factory=lambda selected: _FakeDataset(selected, calls=[]),
            bids_validator=drifting_validator,
        )
    )

    assert failed["status"] == "blocked"
    assert failed["campaign_ready"] is False
    assert failed["datasets"][0]["status"] == "failed"
    assert (
        "changed during authoritative BIDS validation" in failed["datasets"][0]["error"]
    )
    ready_plan = json.loads(Path(failed["gui_plan"]).read_text("utf-8"))
    assert ready_plan["datasets"][0]["execution_state"] == (
        "awaiting_dataset_materialization"
    )
    assert ready_plan["datasets"][0]["bids"]["root"] is None


def test_tree_drift_between_receipt_and_campaign_seal_blocks_ready_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.dev import moabb_dataset_materializer as materializer

    manifest_path, gui_plan_path = _write_contracts(tmp_path, class_names=("FakeEDF",))
    original_write = materializer._atomic_write_json
    drift_injected = False

    def _write_then_drift(path: Path, payload: dict[str, Any]) -> None:
        nonlocal drift_injected
        original_write(path, payload)
        if path.name == "FakeEDF.freeze.json" and payload.get("status") == "ready":
            raw_file = next((tmp_path / "bids-output" / "FakeEDF").rglob("*.edf"))
            raw_file.write_bytes(b"concurrent-drift-after-receipt")
            drift_injected = True

    monkeypatch.setattr(materializer, "_atomic_write_json", _write_then_drift)

    failed = run_materialization(
        _inputs(
            tmp_path,
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
            dataset_factory=lambda selected: _FakeDataset(selected, calls=[]),
        )
    )

    assert drift_injected is True
    assert failed["status"] == "blocked"
    assert failed["campaign_ready"] is False
    assert failed["freeze_manifest"] is None
    assert failed["gui_plan"] is None
    assert any(
        "changed during final campaign seal" in item for item in failed["blockers"]
    )
    assert not (tmp_path / "checksums" / "moabb-15-freeze-manifest-v1.json").exists()
    assert not (tmp_path / "checksums" / "moabb-gui-campaign-v2.ready.json").exists()


@pytest.mark.parametrize("validator_failure", ["blocked", "exception"])
def test_failed_reseal_preserves_previous_ready_receipt_and_validator_report(
    tmp_path: Path,
    validator_failure: str,
) -> None:
    manifest_path, gui_plan_path = _write_contracts(tmp_path, class_names=("FakeEDF",))
    calls: list[dict[str, Any]] = []
    common = {
        "manifest_path": manifest_path,
        "gui_plan_path": gui_plan_path,
        "dataset_factory": lambda selected: _FakeDataset(selected, calls=calls),
    }
    cold_environment = _environment()
    cold = run_materialization(
        _inputs(tmp_path, environment_identity=cold_environment, **common)
    )
    receipt_path = tmp_path / "checksums" / "FakeEDF.freeze.json"
    report_path = tmp_path / "checksums" / "bids-validation" / "FakeEDF.json"
    receipt_before = receipt_path.read_bytes()
    report_before = report_path.read_bytes()
    frozen = json.loads(Path(cold["freeze_manifest"]).read_text("utf-8"))
    bids_root = Path(frozen["datasets"][0]["bids_root"])
    tree_before = {
        str(path): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in bids_root.rglob("*")
        if path.is_file()
    }
    changed_environment = json.loads(json.dumps(cold_environment))
    changed_environment["git"]["commit"] = "7" * 40
    product_digest = _campaign_product_identity_digest(changed_environment)
    changed_environment["campaign_product_identity_sha256"] = product_digest
    changed_environment["identity_sha256"] = product_digest

    def failing_validator(root: Path) -> dict[str, Any]:
        if validator_failure == "exception":
            raise RuntimeError("synthetic validator crash")
        return {
            **_passed_validator(root),
            "status": "blocked",
            "exit_code": 1,
            "error_count": 1,
        }

    failed = run_materialization(
        _inputs(
            tmp_path,
            environment_identity=changed_environment,
            allow_download=False,
            bids_validator=failing_validator,
            **common,
        )
    )

    assert failed["status"] == "blocked"
    assert failed["datasets"][0]["action"] == "reseal-blocked"
    assert len(calls) == 1
    assert receipt_path.read_bytes() == receipt_before
    assert report_path.read_bytes() == report_before
    assert {
        str(path): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in bids_root.rglob("*")
        if path.is_file()
    } == tree_before


def test_conversion_dependency_change_blocks_reuse_and_rebuilds_when_authorized(
    tmp_path: Path,
) -> None:
    manifest_path, gui_plan_path = _write_contracts(
        tmp_path, class_names=("FakeEEGLAB",)
    )
    calls: list[dict[str, Any]] = []
    common = {
        "manifest_path": manifest_path,
        "gui_plan_path": gui_plan_path,
        "dataset_factory": lambda selected: _FakeDataset(selected, calls=calls),
    }
    run_materialization(_inputs(tmp_path, **common))
    changed_environment = _environment()
    changed_environment["packages"]["pymatreader"] = "1.2.4"
    changed_environment["locked_packages"]["pymatreader"] = ["1.2.4"]
    changed_environment["conversion_identity_sha256"] = _conversion_identity_digest(
        changed_environment
    )
    product_digest = _campaign_product_identity_digest(changed_environment)
    changed_environment["campaign_product_identity_sha256"] = product_digest
    changed_environment["identity_sha256"] = product_digest

    blocked = run_materialization(
        _inputs(
            tmp_path,
            environment_identity=changed_environment,
            allow_download=False,
            **common,
        )
    )
    rebuilt = run_materialization(
        _inputs(tmp_path, environment_identity=changed_environment, **common)
    )

    assert blocked["status"] == "blocked"
    assert "conversion identity" in blocked["datasets"][0]["error"]
    assert rebuilt["status"] == "ready"
    assert rebuilt["datasets"][0]["action"] == "rebuilt"
    assert len(calls) == 2


def test_exact_fifteen_freeze_is_consumable_by_existing_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    manifest_path = (
        repo_root / "artifacts/user-journeys/moabb-15-campaign-preflight-v1.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    (
        synthetic_manifest_path,
        _synthetic_gui_path,
        raw_mirror_manifest,
        mirror_payloads,
    ) = _write_mirror_contracts(tmp_path)
    synthetic_mirror = json.loads(synthetic_manifest_path.read_text(encoding="utf-8"))[
        "datasets"
    ][0]
    for index, row in enumerate(manifest["datasets"]):
        if row["moabb_class"] == "Ma2020":
            manifest["datasets"][index] = {
                **synthetic_mirror,
                "moabb_class": "Ma2020",
            }
            break
    manifest_path = tmp_path / "exact-15-synthetic-mirror.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    event_names = {
        str(row["moabb_class"]): list(row["supervised_classes"])
        for row in manifest["datasets"]
    }
    calls: list[dict[str, Any]] = []
    payload_by_url = {
        f"https://mirror.invalid/v1/{relative_path}": payload
        for relative_path, payload in mirror_payloads.items()
    }

    def _download_mirror(
        url: str,
        target: Path,
        _hosts: frozenset[str],
        _expected_bytes: int,
    ) -> dict[str, Any]:
        payload = payload_by_url[url]
        target.write_bytes(payload)
        return {"final_url": url, "size_bytes": len(payload)}

    materialized = run_materialization(
        _inputs(
            tmp_path,
            manifest_path=manifest_path,
            gui_plan_path=(
                repo_root / "artifacts/user-journeys/moabb-gui-campaign-v2.json"
            ),
            dataset_factory=lambda selected: _FakeDataset(
                selected,
                calls=calls,
                event_names=event_names[selected],
            ),
            mirror_manifest_fetcher=lambda _url, _hosts, _maximum: (
                raw_mirror_manifest
            ),
            mirror_file_downloader=_download_mirror,
            free_bytes=10**15,
        )
    )

    assert materialized["status"] == "ready"
    assert materialized["campaign_ready"] is True
    assert tuple(row["dataset"] for row in materialized["datasets"]) == (
        EXPECTED_CLASS_NAMES
    )
    frozen = json.loads(
        Path(materialized["freeze_manifest"]).read_text(encoding="utf-8")
    )
    assert frozen["status"] == "ready"
    assert all(row["status"] == "ready" for row in frozen["datasets"])

    versions = {
        "moabb": "1.5.0",
        "pyxdf": "1.17.0",
        "mne-bids": "0.19.0",
        "pybv": "0.7.6",
        "edfio": "0.4.8",
        "edflib-python": "1.0.8",
        "eeglabio": "0.1.0",
    }
    monkeypatch.setattr(
        moabb_campaign_preflight,
        "_is_d_drive_mount",
        lambda _value: True,
    )
    preflight = evaluate_preflight(
        PreflightInputs(
            manifest_path=Path(materialized["freeze_manifest"]),
            mne_data_root=Path(frozen["materialization"]["mne_data_root"]),
            output_root=Path(frozen["materialization"]["output_root"]),
            free_bytes=10**15,
            distribution_version=versions.__getitem__,
            moabb_class_names=lambda: EXPECTED_CLASS_NAMES,
            moabb_has_generic_bids_conversion=lambda: True,
            configured_mne_data=None,
            poetry_dependency_blockers=list,
        )
    )
    assert preflight["campaign_allowed"] is True
    assert preflight["dataset_count"] == 15
    ready_plan = json.loads(Path(materialized["gui_plan"]).read_text(encoding="utf-8"))
    monkeypatch.setattr(gui_contract, "_is_d_mounted_absolute", lambda _value: True)
    assert gui_contract.validate_campaign_plan(ready_plan) == []
    assert (
        gui_contract.execution_preflight_errors(
            ready_plan,
            environment={
                "identity_sha256": ready_plan["materialization"][
                    "environment_identity_sha256"
                ],
                "git": {"dirty": False},
                "cuda": "12.8",
                "gpu": "Synthetic GPU",
            },
        )
        == []
    )


def test_exact_environment_allows_only_unstaged_protected_local_settings() -> None:
    assert _git_status_policy(" M settings.json") == (["settings.json"], [])
    assert _git_status_policy("M  settings.json") == ([], ["M  settings.json"])
    assert _git_status_policy(" M settings.json\n?? unexpected.bin") == (
        ["settings.json"],
        ["?? unexpected.bin"],
    )


def test_environment_digest_excludes_protected_local_settings_only() -> None:
    clean = {
        "git": {
            "commit": "a" * 40,
            "dirty": False,
            "protected_local_changes": [],
            "status_sha256": "e3b0c442",
        },
        "packages": {"moabb": "1.5.0"},
    }
    protected = json.loads(json.dumps(clean))
    protected["git"]["protected_local_changes"] = ["settings.json"]
    assert _environment_identity_digest(clean) == _environment_identity_digest(
        protected
    )

    unprotected = json.loads(json.dumps(clean))
    unprotected["git"]["dirty"] = True
    unprotected["git"]["status_sha256"] = "changed"
    assert _environment_identity_digest(clean) != _environment_identity_digest(
        unprotected
    )


def test_mne_environment_isolates_and_restores_all_dataset_specific_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MNE_DATA", "/preexisting/general")
    monkeypatch.setenv("MNE_DATASETS_SHARED_PATH", "/preexisting/shared")
    first = tmp_path / "first-source-stage"
    second = tmp_path / "second-source-stage"
    first.mkdir()
    second.mkdir()

    with _temporary_mne_environment(first):
        assert os.environ["MNE_DATA"] == str(first)
        assert os.environ["_MNE_FAKE_HOME_DIR"] == str(first / ".mne-config")
        assert "MNE_DATASETS_SHARED_PATH" not in os.environ
        os.environ["MNE_DATASETS_SHARED_PATH"] = str(first / "shared-sign")
        os.environ["MNE_DATASETS_CREATED_PATH"] = str(first / "created")

    assert os.environ["MNE_DATA"] == "/preexisting/general"
    assert os.environ["MNE_DATASETS_SHARED_PATH"] == "/preexisting/shared"
    assert "MNE_DATASETS_CREATED_PATH" not in os.environ

    with _temporary_mne_environment(second):
        assert "MNE_DATASETS_SHARED_PATH" not in os.environ
        assert "MNE_DATASETS_CREATED_PATH" not in os.environ
        os.environ["MNE_DATASETS_SHARED_PATH"] = str(second / "shared-sign")

    assert os.environ["MNE_DATASETS_SHARED_PATH"] == "/preexisting/shared"
    assert not (first / "shared-sign").is_relative_to(second)


def test_exact_environment_rejects_installed_package_drift_from_lock() -> None:
    environment = _environment()
    _validate_environment(
        {"moabb_release": {"version": "1.5.0"}},
        environment,
    )

    drifted = json.loads(json.dumps(environment))
    drifted["packages"]["scipy"] = "1.16.0"
    with pytest.raises(MaterializationContractError, match=r"scipy.*Poetry lock"):
        _validate_environment(
            {"moabb_release": {"version": "1.5.0"}},
            drifted,
        )


def test_validator_version_is_campaign_identity_but_not_conversion_identity() -> None:
    environment = _environment()
    original_conversion = environment["conversion_identity_sha256"]
    original_campaign = environment["campaign_product_identity_sha256"]

    drifted = json.loads(json.dumps(environment))
    drifted["packages"]["bids-validator-deno"] = "2.4.0"
    drifted["locked_packages"]["bids-validator-deno"] = ["2.4.0"]

    assert _conversion_identity_digest(drifted) == original_conversion
    assert _campaign_product_identity_digest(drifted) != original_campaign
    with pytest.raises(
        MaterializationContractError,
        match=r"locked bids-validator-deno 2\.4\.1",
    ):
        _validate_environment(
            {"moabb_release": {"version": "1.5.0"}},
            drifted,
        )


def test_nvidia_smi_identity_parser_is_exact_and_fail_closed() -> None:
    assert _parse_nvidia_smi_row("GPU-123, NVIDIA RTX Synthetic, 591.01, 16384") == {
        "selected_device_index": 0,
        "uuid": "GPU-123",
        "name": "NVIDIA RTX Synthetic",
        "driver_version": "591.01",
        "memory_total_mib": 16384,
    }
    with pytest.raises(MaterializationContractError, match="nvidia-smi"):
        _parse_nvidia_smi_row("malformed")


def test_exact_environment_accepts_only_one_mib_of_gpu_memory_quantization() -> None:
    rounded = _environment()
    rounded["torch_cuda"]["selected_device_total_memory_bytes"] = 16384 * 1024**2 - 1
    product_digest = _campaign_product_identity_digest(rounded)
    rounded["campaign_product_identity_sha256"] = product_digest
    rounded["identity_sha256"] = product_digest

    _validate_environment(
        {"moabb_release": {"version": "1.5.0"}},
        rounded,
    )

    mismatched = json.loads(json.dumps(rounded))
    mismatched["torch_cuda"]["selected_device_total_memory_bytes"] = 16382 * 1024**2 - 1
    product_digest = _campaign_product_identity_digest(mismatched)
    mismatched["campaign_product_identity_sha256"] = product_digest
    mismatched["identity_sha256"] = product_digest

    with pytest.raises(MaterializationContractError, match="disagrees"):
        _validate_environment(
            {"moabb_release": {"version": "1.5.0"}},
            mismatched,
        )


class _ProbeResponse:
    def __init__(
        self,
        *,
        url: str,
        status: int,
        headers: dict[str, str],
        body: bytes = b"binary",
    ) -> None:
        self._url = url
        self.status = status
        self.headers = headers
        self._body = body

    def __enter__(self) -> _ProbeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def geturl(self) -> str:
        return self._url

    def read(self, size: int) -> bytes:
        return self._body[:size]


def _probe_policy(*, maximum_total_bytes: int = 300) -> dict[str, Any]:
    return {
        "kind": "http_range",
        "resources": [
            {"url": "https://example.invalid/one", "maximum_bytes": 200},
            {"url": "https://example.invalid/two", "maximum_bytes": 200},
        ],
        "maximum_total_bytes": maximum_total_bytes,
        "allowed_hosts": ["example.invalid"],
        "accepted_statuses": [200, 206],
        "denied_content_types": ["text/html"],
        "denied_body_markers": ["access denied"],
    }


def test_resource_probe_admits_every_exact_resource_and_trustworthy_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _urlopen(request: Any, *, timeout: int):
        assert timeout == 15
        if request.full_url.endswith("/one"):
            return _ProbeResponse(
                url=request.full_url,
                status=206,
                headers={
                    "Content-Type": "application/octet-stream",
                    "Content-Range": "bytes 0-99/100",
                    "Content-Length": "100",
                },
            )
        return _ProbeResponse(
            url=request.full_url,
            status=200,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Length": "120",
            },
        )

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)

    result = _bounded_http_resource_probe(_probe_policy())

    assert result["status"] == "passed"
    assert result["total_bytes"] == 220
    assert [row["url"] for row in result["resources"]] == [
        "https://example.invalid/one",
        "https://example.invalid/two",
    ]
    assert [row["total_bytes"] for row in result["resources"]] == [100, 120]


@pytest.mark.parametrize(
    ("headers", "maximum_total_bytes", "expected"),
    [
        ({"Content-Type": "application/octet-stream"}, 300, "Content-Range"),
        (
            {
                "Content-Type": "application/octet-stream",
                "Content-Range": "bytes 0-99/invalid",
            },
            300,
            "Content-Range",
        ),
        (
            {
                "Content-Type": "application/octet-stream",
                "Content-Range": "bytes 0-99/200",
            },
            150,
            "maximum total",
        ),
    ],
)
def test_resource_probe_rejects_missing_malformed_or_oversize_totals(
    monkeypatch: pytest.MonkeyPatch,
    headers: dict[str, str],
    maximum_total_bytes: int,
    expected: str,
) -> None:
    def _urlopen(request: Any, *, timeout: int):
        return _ProbeResponse(url=request.full_url, status=206, headers=headers)

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)
    policy = _probe_policy(maximum_total_bytes=maximum_total_bytes)
    policy["resources"] = [policy["resources"][0]]

    result = _bounded_http_resource_probe(policy)

    assert result["status"] == "blocked"
    assert expected.casefold() in result["reason"].casefold()


def test_unavailable_authoritative_validator_never_publishes_ready(
    tmp_path: Path,
) -> None:
    manifest_path, gui_plan_path = _write_contracts(tmp_path, class_names=("FakeEDF",))

    result = run_materialization(
        _inputs(
            tmp_path,
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
            dataset_factory=lambda selected: _FakeDataset(selected, calls=[]),
            bids_validator=lambda root: {
                "status": "blocked",
                "validator": "bids-validator-deno",
                "required_version": "2.4.1",
                "version": None,
                "argv": [
                    "bids-validator-deno",
                    str(root),
                    "--format",
                    "json",
                    "--max-rows",
                    "-1",
                ],
                "exit_code": None,
                "error_count": None,
                "reason": "validator executable is unavailable",
            },
        )
    )

    assert result["status"] == "blocked"
    assert result["campaign_ready"] is False
    assert "validator" in result["datasets"][0]["error"]
