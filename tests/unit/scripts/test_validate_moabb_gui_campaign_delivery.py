from __future__ import annotations

import ast
import copy
import inspect
import json
from pathlib import Path

import pytest

from scripts.dev import moabb_campaign_preflight
from scripts.dev import validate_moabb_gui_campaign_delivery as delivery_validator
from scripts.dev.moabb_campaign_preflight import (
    EXPECTED_CLASS_NAMES,
    PreflightInputs,
)
from scripts.dev.moabb_dataset_materializer import run_materialization
from scripts.dev.validate_moabb_gui_campaign_delivery import (
    validate_delivery_evidence,
)
from tests.unit.scripts import test_moabb_dataset_materializer as materializer_support

ROOT = Path(__file__).resolve().parents[3]
TRACKED_PLAN = ROOT / "artifacts" / "user-journeys" / "moabb-gui-campaign-v2.json"
FROZEN_ENVIRONMENT = {
    "identity_sha256": "e" * 64,
    "git": {"commit": "1" * 40},
    "poetry_lock_sha256": "2" * 64,
    "cuda": "13.0",
    "gpu": "Frozen GPU",
}


def _pending_plan() -> dict:
    payload = json.loads(TRACKED_PLAN.read_text(encoding="utf-8"))
    payload.pop("materialization", None)
    for row in payload["datasets"]:
        row["execution_state"] = "awaiting_dataset_materialization"
        row["bids"]["root"] = None
        row["bids"]["dataset_revision_sha256"] = None
        row["oracle"] = {
            "state": "awaiting_dataset_materialization",
            "expected_events": [],
            "expected_classes": [],
        }
    return payload


def _stub_materialization_plans(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    ready_plan: dict,
) -> Path:
    seed_path = tmp_path / "seed-plan.json"
    freeze_path = tmp_path / "freeze.json"
    ready_path = tmp_path / "ready-plan.json"
    seed_plan = {"resource_policy": {"checksum_root": "/mnt/d/frozen-checksums"}}

    def load_plan(path: Path):
        return seed_plan if path == seed_path else ready_plan

    monkeypatch.setattr(delivery_validator, "load_campaign_plan", load_plan)
    monkeypatch.setattr(
        delivery_validator,
        "campaign_plan_sha256",
        lambda path: "a" * 64 if path == seed_path else "b" * 64,
    )
    monkeypatch.setattr(
        delivery_validator,
        "_resolve_materialization_paths",
        lambda _plan: (freeze_path, ready_path, []),
    )
    monkeypatch.setattr(
        delivery_validator,
        "_load_json_object",
        lambda _path, *, label: (
            {
                "status": "ready",
                "materialization": {"environment": FROZEN_ENVIRONMENT},
            },
            [],
        ),
    )
    monkeypatch.setattr(
        delivery_validator,
        "_freeze_ready_binding_errors",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        delivery_validator,
        "_materialization_preflight_errors",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        delivery_validator, "execution_preflight_errors", lambda _plan: []
    )
    monkeypatch.setattr(
        delivery_validator, "missing_product_source_hooks", lambda _root: []
    )
    monkeypatch.setattr(delivery_validator, "_is_d_mounted", lambda _path: True)
    return seed_path


def test_delivery_validator_has_no_execution_or_download_boundary() -> None:
    source_path = Path(inspect.getsourcefile(delivery_validator) or "")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_modules = {
        module
        for node in ast.walk(tree)
        for module in (
            (
                node.module
                if isinstance(node, ast.ImportFrom) and node.module is not None
                else None
            ),
            *(
                (alias.name for alias in node.names)
                if isinstance(node, ast.Import)
                else ()
            ),
        )
        if module is not None
    }
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    materializer_imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "scripts.dev.moabb_dataset_materializer"
        for alias in node.names
    }

    forbidden_modules = {
        "scripts.dev.moabb_gui_campaign_v2.runner",
        "scripts.dev.moabb_gui_campaign_v2.worker",
    }
    assert imported_modules.isdisjoint(forbidden_modules)
    assert called_names.isdisjoint(
        {"run_campaign", "run_materialization", "run_worker", "Popen"}
    )
    assert materializer_imports == {"FREEZE_MANIFEST_NAME", "READY_GUI_PLAN_NAME"}


def test_delivery_validator_resolves_generated_freeze_and_ready_plan() -> None:
    seed_plan = json.loads(TRACKED_PLAN.read_text(encoding="utf-8"))
    checksum_root = Path(seed_plan["resource_policy"]["checksum_root"])

    freeze, ready, errors = delivery_validator._resolve_materialization_paths(seed_plan)

    assert errors == []
    assert freeze == checksum_root / delivery_validator.FREEZE_MANIFEST_NAME
    assert ready == checksum_root / delivery_validator.READY_GUI_PLAN_NAME


def test_unresolved_seed_reports_awaiting_and_null() -> None:
    errors = delivery_validator._unresolved_seed_materialization_errors(_pending_plan())

    assert (
        len([error for error in errors if "awaiting_dataset_materialization" in error])
        == 15
    )
    assert len([error for error in errors if "bids.root remains null" in error]) == 15


def test_real_exact_fifteen_materializer_outputs_satisfy_delivery_binding_and_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = json.loads(
        (
            ROOT / "artifacts" / "user-journeys" / "moabb-15-campaign-preflight-v1.json"
        ).read_text(encoding="utf-8")
    )
    (
        synthetic_manifest_path,
        _synthetic_gui_path,
        raw_mirror_manifest,
        mirror_payloads,
    ) = materializer_support._write_mirror_contracts(tmp_path)
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
    seed = json.loads(TRACKED_PLAN.read_text(encoding="utf-8"))
    output_root = tmp_path / "bids-output"
    checksum_root = tmp_path / "checksums"
    seed["resource_policy"]["data_root"] = str(output_root.resolve())
    seed["resource_policy"]["checksum_root"] = str(checksum_root.resolve())
    for row in seed["datasets"]:
        dataset = str(row["moabb_class"])
        row["bids"]["conversion_parent"] = str((output_root / dataset).resolve())
        row["bids"]["checksum_manifest"] = str(
            (checksum_root / f"{dataset}.sha256").resolve()
        )
    seed_path = tmp_path / "exact-15-gui-plan.json"
    seed_path.write_text(json.dumps(seed), encoding="utf-8")
    event_names = {
        str(row["moabb_class"]): list(row["supervised_classes"])
        for row in manifest["datasets"]
    }
    payload_by_url = {
        f"https://mirror.invalid/v1/{relative_path}": payload
        for relative_path, payload in mirror_payloads.items()
    }

    def download_mirror(
        url: str,
        target: Path,
        _hosts: frozenset[str],
        _expected_bytes: int,
    ) -> dict[str, object]:
        payload = payload_by_url[url]
        target.write_bytes(payload)
        return {"final_url": url, "size_bytes": len(payload)}

    calls: list[dict] = []
    materialized = run_materialization(
        materializer_support._inputs(
            tmp_path,
            manifest_path=manifest_path,
            gui_plan_path=seed_path,
            dataset_factory=lambda selected: materializer_support._FakeDataset(
                selected,
                calls=calls,
                event_names=event_names[selected],
            ),
            mirror_manifest_fetcher=lambda _url, _hosts, _maximum: (
                raw_mirror_manifest
            ),
            mirror_file_downloader=download_mirror,
            free_bytes=10**15,
        )
    )
    freeze_path = Path(materialized["freeze_manifest"])
    ready_path = Path(materialized["gui_plan"])
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    ready = json.loads(ready_path.read_text(encoding="utf-8"))
    monkeypatch.setattr(delivery_validator, "DEFAULT_MANIFEST_PATH", manifest_path)

    assert materialized["status"] == "ready"
    assert (
        delivery_validator._freeze_ready_binding_errors(
            seed_plan=seed,
            seed_plan_digest=delivery_validator._sha256_file(seed_path),
            freeze_manifest=freeze,
            freeze_manifest_path=freeze_path,
            ready_plan=ready,
        )
        == []
    )

    forged_freeze = copy.deepcopy(freeze)
    forged_freeze["datasets"][0]["subjects"] = [5, 4, 3, 2, 1]
    errors = delivery_validator._freeze_ready_binding_errors(
        seed_plan=seed,
        seed_plan_digest=delivery_validator._sha256_file(seed_path),
        freeze_manifest=forged_freeze,
        freeze_manifest_path=freeze_path,
        ready_plan=ready,
    )
    assert any("tracked dataset manifest" in error for error in errors)

    forged_roots = copy.deepcopy(freeze)
    forged_roots["materialization"]["output_root"] = "/mnt/d/forged-output"
    errors = delivery_validator._freeze_ready_binding_errors(
        seed_plan=seed,
        seed_plan_digest=delivery_validator._sha256_file(seed_path),
        freeze_manifest=forged_roots,
        freeze_manifest_path=freeze_path,
        ready_plan=ready,
    )
    assert any("tracked seed output root" in error for error in errors)

    forged_environment = copy.deepcopy(freeze)
    forged_environment["materialization"]["environment"]["git"]["commit"] = "f" * 40
    errors = delivery_validator._freeze_ready_binding_errors(
        seed_plan=seed,
        seed_plan_digest=delivery_validator._sha256_file(seed_path),
        freeze_manifest=forged_environment,
        freeze_manifest_path=freeze_path,
        ready_plan=ready,
    )
    assert any("product environment seal is invalid" in error for error in errors)

    forged_ready = copy.deepcopy(ready)
    forged_ready["datasets"][0]["oracle"]["source_event_id"] = {"forged": 999}
    errors = delivery_validator._freeze_ready_binding_errors(
        seed_plan=seed,
        seed_plan_digest=delivery_validator._sha256_file(seed_path),
        freeze_manifest=freeze,
        freeze_manifest_path=freeze_path,
        ready_plan=forged_ready,
    )
    assert any("full frozen oracle" in error for error in errors)

    versions = {
        "moabb": "1.5.0",
        "pyxdf": "1.17.0",
        "mne-bids": "0.19.0",
        "pybv": "0.7.6",
        "edfio": "0.4.8",
        "edflib-python": "1.0.8",
        "eeglabio": "0.1.0",
    }
    preflight_inputs = PreflightInputs(
        manifest_path=freeze_path,
        mne_data_root=Path(freeze["materialization"]["mne_data_root"]),
        output_root=Path(freeze["materialization"]["output_root"]),
        free_bytes=10**15,
        distribution_version=versions.__getitem__,
        moabb_class_names=lambda: EXPECTED_CLASS_NAMES,
        moabb_has_generic_bids_conversion=lambda: True,
        configured_mne_data=None,
        poetry_dependency_blockers=list,
    )
    monkeypatch.setattr(
        delivery_validator.PreflightInputs,
        "from_environment",
        lambda **_kwargs: preflight_inputs,
    )
    monkeypatch.setattr(
        moabb_campaign_preflight,
        "_is_d_drive_mount",
        lambda _value: True,
    )

    assert (
        delivery_validator._materialization_preflight_errors(
            freeze_manifest_path=freeze_path,
            freeze_manifest=freeze,
        )
        == []
    )


def test_materialization_preflight_blockers_remain_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    freeze_path = tmp_path / "freeze.json"
    freeze_manifest = {
        "materialization": {
            "mne_data_root": "/mnt/d/source",
            "output_root": "/mnt/d/bids",
        }
    }
    monkeypatch.setattr(
        delivery_validator.PreflightInputs,
        "from_environment",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(
        delivery_validator,
        "evaluate_preflight",
        lambda _inputs: {
            "status": "blocked",
            "campaign_allowed": False,
            "blockers": ["checksum mismatch"],
        },
    )

    errors = delivery_validator._materialization_preflight_errors(
        freeze_manifest_path=freeze_path,
        freeze_manifest=freeze_manifest,
    )

    assert errors == ["frozen dataset preflight: checksum mismatch"]


def test_delivery_validation_rejects_pending_null_plan_and_zero_receipts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_root = tmp_path / "moabb-15-campaign"
    evidence_root.mkdir()
    seed_path = _stub_materialization_plans(
        monkeypatch,
        tmp_path,
        ready_plan=_pending_plan(),
    )

    result = validate_delivery_evidence(
        plan_path=seed_path,
        evidence_root=evidence_root,
    )

    assert result["status"] == "blocked"
    assert result["delivery_allowed"] is False
    assert result["expected_dataset_count"] == 15
    assert result["expected_receipt_count"] == 30
    assert result["loaded_receipt_count"] == 0
    errors = result["errors"]
    assert any("execution_state must be ready" in error for error in errors)
    assert any("bids.root must be non-null" in error for error in errors)
    assert any("expected 30 journey receipts, loaded 0" in error for error in errors)


def test_delivery_validation_rejects_missing_campaign_evidence_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_path = _stub_materialization_plans(
        monkeypatch,
        tmp_path,
        ready_plan=_pending_plan(),
    )

    result = validate_delivery_evidence(
        plan_path=seed_path,
        evidence_root=tmp_path / "missing",
    )

    assert result["status"] == "blocked"
    assert result["loaded_receipt_count"] == 0
    assert any("evidence root is missing" in error for error in result["errors"])


def test_delivery_validation_admits_only_complete_existing_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_root = tmp_path / "moabb-15-campaign"
    expected_identities = [
        (dataset, mode)
        for dataset in delivery_validator.DATASET_MATRIX
        for mode in delivery_validator.JOURNEY_MODES
    ]
    for dataset, mode in expected_identities:
        path = evidence_root / dataset / mode / "journey-receipt.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"dataset": dataset, "journey_mode": mode}),
            encoding="utf-8",
        )
    ready_plan = {
        "datasets": [
            {
                "execution_state": "ready",
                "bids": {"root": f"/mnt/d/frozen/{dataset}"},
            }
            for dataset in delivery_validator.DATASET_MATRIX
        ]
    }
    seed_path = _stub_materialization_plans(
        monkeypatch,
        tmp_path,
        ready_plan=ready_plan,
    )

    def validate_receipts(
        _plan,
        receipts,
        *,
        artifact_root,
        expected_plan_sha256,
        authoritative_environment,
    ):
        assert artifact_root == evidence_root
        assert expected_plan_sha256 == "b" * 64
        assert authoritative_environment == FROZEN_ENVIRONMENT
        assert [
            (receipt["dataset"], receipt["journey_mode"]) for receipt in receipts
        ] == expected_identities
        return []

    monkeypatch.setattr(
        delivery_validator,
        "validate_campaign_receipts",
        validate_receipts,
    )
    monkeypatch.setattr(
        delivery_validator,
        "validate_visual_review_attestation",
        lambda *_args, **_kwargs: [],
    )

    result = validate_delivery_evidence(
        plan_path=seed_path,
        evidence_root=evidence_root,
    )

    assert result["status"] == "ready"
    assert result["delivery_allowed"] is True
    assert result["loaded_receipt_count"] == 30
    assert result["errors"] == []


def test_delivery_validation_requires_completed_visual_review_attestation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_root = tmp_path / "moabb-15-campaign"
    seed_path = _stub_materialization_plans(
        monkeypatch,
        tmp_path,
        ready_plan={"datasets": []},
    )
    monkeypatch.setattr(
        delivery_validator, "_load_exact_receipt_inventory", lambda _root: ([], [])
    )
    monkeypatch.setattr(
        delivery_validator,
        "_load_json_object",
        lambda _path, *, label: (
            (None, ["visual review attestation cannot be loaded"])
            if label == "visual review attestation"
            else (
                {
                    "status": "ready",
                    "materialization": {"environment": FROZEN_ENVIRONMENT},
                },
                [],
            )
        ),
    )

    result = validate_delivery_evidence(
        plan_path=seed_path,
        evidence_root=evidence_root,
    )

    assert result["delivery_allowed"] is False
    assert result["visual_review_status"] == "missing"
    assert any(
        "visual review attestation cannot be loaded" in error
        for error in result["errors"]
    )
