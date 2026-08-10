import copy
from pathlib import Path
from types import SimpleNamespace

import mne
from PIL import Image

import scripts.dev.local_assistant_capture_runtime as capture_runtime
from scripts.dev.capture_chatpanel_local_training_readiness_walkthrough import (
    TURN_SPECS,
    prepare_dataset_ready_state,
    render_markdown,
    validate_training_readiness_payload,
    validate_turn,
    write_synthetic_raw_fif,
)
from scripts.dev.local_assistant_capture_runtime import (
    _snapshot_manifest_identity,
    collect_runtime_input_evidence,
    collect_screenshot_evidence,
    seal_evidence_identity,
    validate_strict_capture_evidence,
)
from XBrainLab.backend.application import CreateEpochCommand
from XBrainLab.llm.core.model_catalog import (
    PRIMARY_LOCAL_MODEL_ID,
    PRIMARY_LOCAL_MODEL_REVISION,
)


def _base_payload():
    return {
        "status": "passed",
        "failure_reason": "",
        "source_path": "/tmp/source.fif",
        "dataset_preparation": {
            "ok": True,
            "commands": [
                {"command": "scan_source", "ok": True},
                {"command": "configure_dataset_split", "ok": True},
            ],
        },
        "runtime": {
            "classification": "gpu-ready",
            "model_id": PRIMARY_LOCAL_MODEL_ID,
            "cache_usage": "15.34 GB",
        },
        "hf_offline": {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        },
        "screenshots": {"ready": "ready.png"},
        "turns": [
            {
                "index": 1,
                "prompt": "Use EEGNet.",
                "kind": "tool",
                "expected_tool": "set_model",
                "assistant_text": "Model set.",
                "new_tools": [
                    {"name": "set_model", "success": True, "duration_ms": 1.0}
                ],
                "screenshot": "turn-1.png",
            },
            {
                "index": 2,
                "prompt": "Configure training.",
                "kind": "tool",
                "expected_tool": "configure_training",
                "assistant_text": "Training configured.",
                "new_tools": [
                    {
                        "name": "configure_training",
                        "success": True,
                        "duration_ms": 1.0,
                    }
                ],
                "screenshot": "turn-2.png",
            },
            {
                "index": 3,
                "prompt": "Start training.",
                "kind": "confirmation",
                "expected_tool": "start_training",
                "assistant_text": "Cancelled: Start training.",
                "new_tools": [],
                "screenshot": "turn-3.png",
            },
            {
                "index": 4,
                "prompt": "Visualize readiness.",
                "kind": "tool",
                "expected_tool": "visualize",
                "assistant_text": "Visualization summary ready.",
                "new_tools": [
                    {"name": "visualize", "success": True, "duration_ms": 1.0}
                ],
                "screenshot": "turn-4.png",
            },
            {
                "index": 5,
                "prompt": "Saliency readiness.",
                "kind": "tool",
                "expected_tool": "saliency",
                "assistant_text": "Saliency summary ready.",
                "new_tools": [
                    {"name": "saliency", "success": True, "duration_ms": 1.0}
                ],
                "screenshot": "turn-5.png",
            },
            {
                "index": 6,
                "prompt": "Evaluate.",
                "kind": "blocked",
                "expected_tool": "evaluate",
                "assistant_text": "Create a training plan before evaluating results.",
                "new_tools": [
                    {
                        "name": "evaluate",
                        "success": False,
                        "duration_ms": 0.0,
                        "error": "Create a training plan before evaluating results.",
                    }
                ],
                "screenshot": "turn-6.png",
            },
        ],
        "visible_messages": [],
        "executed_tools": [
            {"name": "set_model", "success": True, "duration_ms": 1.0},
            {"name": "configure_training", "success": True, "duration_ms": 1.0},
            {"name": "visualize", "success": True, "duration_ms": 1.0},
            {"name": "saliency", "success": True, "duration_ms": 1.0},
            {
                "name": "evaluate",
                "success": False,
                "duration_ms": 0.0,
                "error": "Create a training plan before evaluating results.",
            },
        ],
        "confirmation_events": [
            {
                "surface": "inline_card",
                "request_id": "confirmation-1",
                "action": "Start training",
                "approved": False,
            }
        ],
        "final_state": {
            "dataset": {"available": True},
            "training": {
                "has_model": True,
                "has_training_option": True,
                "has_trainer": False,
                "is_running": False,
            },
            "evaluation": {"available": False, "total_plans": 0},
        },
        "ui_state": {
            "send_button_text": "Send",
            "send_button_enabled": True,
            "input_enabled": True,
            "chat_processing": False,
            "controller_processing": False,
            "dataset_table_rows": 1,
            "dataset_empty_state_visible": False,
        },
        "shutdown": {"status": "completed", "detail": ""},
        "elapsed_seconds": 42.0,
    }


def _strict_evidence_payload() -> dict:
    source_identity = seal_evidence_identity(
        "source",
        {
            "branch": "stabilize/product-quality-closure",
            "commit_sha": "a" * 40,
            "head_tree_sha": "b" * 40,
            "dirty": False,
            "dirty_fingerprint": "c" * 64,
            "source_content_sha256": "d" * 64,
        },
    )
    model_identity = seal_evidence_identity(
        "model",
        {
            "requested_model_id": PRIMARY_LOCAL_MODEL_ID,
            "loaded_model_id": PRIMARY_LOCAL_MODEL_ID,
            "loaded_revision": PRIMARY_LOCAL_MODEL_REVISION,
            "snapshot_manifest_sha256": "e" * 64,
            "snapshot_file_count": 8,
            "snapshot_total_bytes": 5_000_000_000,
            "cache_complete": True,
            "loader_policy": "pinned-local-files-only",
        },
    )
    screenshots = {
        "ready": {
            "relative_path": "ready.png",
            "sha256": "f" * 64,
            "byte_size": 123,
            "dimensions": [1280, 900],
        }
    }
    runtime_inputs = {
        "training_eeg_fixture": {
            "kind": "deterministic-eeg-fixture",
            "display_name": "training_readiness_raw.fif",
            "sha256": "2" * 64,
            "byte_size": 2048,
            "retained": False,
        }
    }
    runtime_input_evidence = {
        "artifacts": runtime_inputs,
        "aggregate_sha256": seal_evidence_identity(
            "runtime-inputs",
            runtime_inputs,
        )["identity_sha256"],
    }
    return {
        "status": "passed",
        "runtime": {
            "classification": "gpu-ready",
            "requested_model_id": PRIMARY_LOCAL_MODEL_ID,
            "loaded_model_id": PRIMARY_LOCAL_MODEL_ID,
            "model_identity": model_identity,
        },
        "source_identity": source_identity,
        "capture_source": {
            "identity_at_start": source_identity["identity_sha256"],
            "identity_at_completion": source_identity["identity_sha256"],
            "stable": True,
        },
        "host_assistance": {
            "classification": "host-assisted",
            "used": True,
            "actions": ["prepared deterministic dataset state"],
        },
        "screenshot_artifacts": {
            "artifacts": screenshots,
            "aggregate_sha256": seal_evidence_identity(
                "screenshots",
                screenshots,
            )["identity_sha256"],
        },
        "runtime_input_artifacts": runtime_input_evidence,
        "capture_runtime_inputs": {
            "identity_at_start": runtime_input_evidence["aggregate_sha256"],
            "identity_at_completion": runtime_input_evidence["aggregate_sha256"],
            "stable": True,
        },
        "hf_offline": {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        },
        "shutdown": {"status": "completed", "detail": ""},
    }


def _strict_workflow_payload() -> dict:
    payload = _base_payload()
    payload.pop("source_path")
    evidence = _strict_evidence_payload()
    payload["runtime"].update(evidence["runtime"])
    for key in (
        "source_identity",
        "capture_source",
        "host_assistance",
        "screenshot_artifacts",
        "runtime_input_artifacts",
        "capture_runtime_inputs",
    ):
        payload[key] = evidence[key]
    return payload


def test_strict_capture_evidence_accepts_exact_granite_identity() -> None:
    ok, reason = validate_strict_capture_evidence(_strict_evidence_payload())

    assert ok is True
    assert reason == ""


def test_strict_capture_evidence_rejects_mutated_loaded_revision_and_digest() -> None:
    payload = _strict_evidence_payload()
    identity = payload["runtime"]["model_identity"]
    identity["loaded_revision"] = "0" * 40
    identity["snapshot_manifest_sha256"] = "1" * 64

    ok, reason = validate_strict_capture_evidence(payload)

    assert ok is False
    assert "model identity" in reason.lower()


def test_strict_capture_evidence_rejects_resealed_stale_model_snapshot() -> None:
    payload = _strict_evidence_payload()
    current = copy.deepcopy(payload["runtime"]["model_identity"])
    mutated = copy.deepcopy(current)
    mutated["snapshot_manifest_sha256"] = "1" * 64
    payload["runtime"]["model_identity"] = seal_evidence_identity(
        "model",
        {key: value for key, value in mutated.items() if key != "identity_sha256"},
    )

    ok, reason = validate_strict_capture_evidence(
        payload,
        current_model_identity=current,
    )

    assert ok is False
    assert "stale" in reason.lower()


def test_snapshot_manifest_hashes_symlink_target_bytes_and_stales_old_evidence(
    tmp_path: Path,
) -> None:
    cache_root = tmp_path / "cache"
    snapshot = cache_root / "models--ibm-granite--granite" / "snapshots" / "revision"
    blob = cache_root / "models--ibm-granite--granite" / "blobs" / "fixed-name"
    snapshot.mkdir(parents=True)
    blob.parent.mkdir(parents=True)
    blob.write_bytes(b"first-bytes")
    (snapshot / "model.safetensors").symlink_to(blob)

    first_digest, first_count, first_bytes = _snapshot_manifest_identity(
        snapshot,
        cache_root=cache_root,
    )
    payload = _strict_evidence_payload()
    old_model = dict(payload["runtime"]["model_identity"])
    old_model["snapshot_manifest_sha256"] = first_digest
    payload["runtime"]["model_identity"] = seal_evidence_identity(
        "model",
        {key: value for key, value in old_model.items() if key != "identity_sha256"},
    )

    blob.write_bytes(b"other-bytes")
    second_digest, second_count, second_bytes = _snapshot_manifest_identity(
        snapshot,
        cache_root=cache_root,
    )
    current_model = dict(payload["runtime"]["model_identity"])
    current_model["snapshot_manifest_sha256"] = second_digest
    current_model = seal_evidence_identity(
        "model",
        {
            key: value
            for key, value in current_model.items()
            if key != "identity_sha256"
        },
    )

    assert first_count == second_count == 1
    assert first_bytes == second_bytes == len(b"first-bytes")
    assert first_digest != second_digest
    ok, reason = validate_strict_capture_evidence(
        payload,
        current_model_identity=current_model,
    )
    assert ok is False
    assert "stale" in reason.lower()


def test_snapshot_manifest_rejects_escape_and_non_regular_symlink_targets(
    tmp_path: Path,
) -> None:
    cache_root = tmp_path / "cache"
    snapshot = cache_root / "snapshot"
    snapshot.mkdir(parents=True)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    (snapshot / "escape.bin").symlink_to(outside)

    assert _snapshot_manifest_identity(snapshot, cache_root=cache_root) == ("", 0, 0)

    (snapshot / "escape.bin").unlink()
    directory_target = cache_root / "directory-target"
    directory_target.mkdir()
    (snapshot / "not-a-file").symlink_to(directory_target, target_is_directory=True)

    assert _snapshot_manifest_identity(snapshot, cache_root=cache_root) == ("", 0, 0)


def test_snapshot_manifest_hashes_hardlinked_content_once(
    monkeypatch,
    tmp_path: Path,
) -> None:
    cache_root = tmp_path / "cache"
    snapshot = cache_root / "snapshot"
    snapshot.mkdir(parents=True)
    first = snapshot / "first.bin"
    second = snapshot / "second.bin"
    first.write_bytes(b"shared-content")
    second.hardlink_to(first)
    calls = 0
    real_file_sha256 = capture_runtime._file_sha256

    def count_file_sha256(path: Path) -> str:
        nonlocal calls
        calls += 1
        return real_file_sha256(path)

    monkeypatch.setattr(capture_runtime, "_file_sha256", count_file_sha256)

    digest, file_count, total_bytes = _snapshot_manifest_identity(
        snapshot,
        cache_root=cache_root,
    )

    assert digest
    assert file_count == 2
    assert total_bytes == len(b"shared-content") * 2
    assert calls == 1


def test_strict_capture_evidence_rejects_missing_identity() -> None:
    payload = _strict_evidence_payload()
    payload.pop("source_identity")

    ok, reason = validate_strict_capture_evidence(payload)

    assert ok is False
    assert "source identity" in reason.lower()


def test_strict_capture_evidence_rejects_private_runtime_source_path() -> None:
    payload = _strict_evidence_payload()
    payload["source_path"] = "/private/runtime/training_raw.fif"

    ok, reason = validate_strict_capture_evidence(payload)

    assert ok is False
    assert "private runtime source path" in reason.lower()


def test_strict_capture_evidence_requires_terminal_shutdown() -> None:
    payload = _strict_evidence_payload()
    payload["shutdown"] = {"status": "closing", "detail": ""}

    ok, reason = validate_strict_capture_evidence(payload)

    assert ok is False
    assert "terminal shutdown" in reason.lower()


def test_strict_capture_evidence_rejects_stale_source_identity() -> None:
    payload = _strict_evidence_payload()
    current = copy.deepcopy(payload["source_identity"])
    current["source_content_sha256"] = "9" * 64
    current = seal_evidence_identity(
        "source",
        {key: value for key, value in current.items() if key != "identity_sha256"},
    )

    ok, reason = validate_strict_capture_evidence(
        payload,
        current_source_identity=current,
    )

    assert ok is False
    assert "stale" in reason.lower()


def test_strict_capture_evidence_rejects_mutated_screenshot_file(tmp_path) -> None:
    screenshot = tmp_path / "ready.png"
    Image.new("RGB", (64, 48), "white").save(screenshot)
    payload = _strict_evidence_payload()
    payload["screenshot_artifacts"] = collect_screenshot_evidence(
        {"ready": screenshot},
        artifact_root=tmp_path,
    )

    ok, reason = validate_strict_capture_evidence(payload, artifact_root=tmp_path)
    assert ok is True, reason

    Image.new("RGB", (64, 48), "black").save(screenshot)
    ok, reason = validate_strict_capture_evidence(payload, artifact_root=tmp_path)

    assert ok is False
    assert "mutated" in reason.lower()


def test_runtime_input_evidence_is_path_free_and_changes_with_fixture_bytes(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "private" / "training_raw.fif"
    fixture.parent.mkdir()
    fixture.write_bytes(b"first fixture bytes")

    first = collect_runtime_input_evidence(
        {"training_eeg_fixture": fixture},
        kinds={"training_eeg_fixture": "deterministic-eeg-fixture"},
        retained=False,
    )
    fixture.write_bytes(b"second fixture bytes")
    second = collect_runtime_input_evidence(
        {"training_eeg_fixture": fixture},
        kinds={"training_eeg_fixture": "deterministic-eeg-fixture"},
        retained=False,
    )

    record = first["artifacts"]["training_eeg_fixture"]
    assert record["display_name"] == "training_raw.fif"
    assert "path" not in record
    assert str(tmp_path) not in str(first)
    assert first["aggregate_sha256"] != second["aggregate_sha256"]


def test_turn_specs_capture_training_boundary_and_analysis_tools():
    assert [turn["kind"] for turn in TURN_SPECS] == [
        "tool",
        "tool",
        "confirmation",
        "tool",
        "tool",
        "blocked",
    ]
    assert [turn["expected_tool"] for turn in TURN_SPECS] == [
        "set_model",
        "configure_training",
        "start_training",
        "visualize",
        "saliency",
        "evaluate",
    ]
    assert TURN_SPECS[-1]["prompt"] == "Evaluate the current training results."


def test_blocked_evaluation_turn_requires_backend_specific_guidance():
    state = _base_payload()

    ok, reason = validate_turn(
        len(TURN_SPECS) - 1,
        (
            "As an AI text-based model, I don't have the capability to directly "
            "evaluate EEG or BCI training results."
        ),
        [],
        state,
    )

    assert ok is False
    assert "backend readiness" in reason


def test_blocked_evaluation_turn_accepts_backend_readiness_reason():
    state = _base_payload()

    ok, reason = validate_turn(
        len(TURN_SPECS) - 1,
        "Complete at least one training run before evaluating results.",
        [],
        state,
    )

    assert ok is True
    assert reason == ""


def test_prepare_dataset_ready_state_uses_eegnet_compatible_epoch_window(
    monkeypatch,
):
    commands = []

    class FakeState:
        def to_dict(self):
            return {"pipeline_stage": "dataset"}

    class FakeService:
        def execute(self, command):
            commands.append(command)
            return SimpleNamespace(
                ok=True,
                failed=False,
                message="ok",
                error_type=None,
                diagnostics={},
            )

        def get_state(self):
            return FakeState()

    monkeypatch.setattr(
        "scripts.dev.capture_chatpanel_local_training_readiness_walkthrough."
        "get_application_service",
        lambda _study: FakeService(),
    )

    result = prepare_dataset_ready_state(object(), Path("/tmp/source.fif"))

    epoch = next(
        command for command in commands if isinstance(command, CreateEpochCommand)
    )
    assert result["ok"] is True
    assert epoch.t_max - epoch.t_min >= 1.5


def test_training_readiness_fixture_contains_the_full_epoch_window():
    source_path = write_synthetic_raw_fif()
    raw = mne.io.read_raw_fif(source_path, preload=False, verbose=False)

    assert raw.times[-1] >= max(raw.annotations.onset) + 1.5


def test_validate_training_readiness_payload_accepts_boundary():
    ok, reason = validate_training_readiness_payload(_strict_workflow_payload())

    assert ok is True
    assert reason == ""


def test_validate_training_readiness_payload_requires_bound_fixture_identity():
    payload = _strict_workflow_payload()
    payload.pop("runtime_input_artifacts")
    payload.pop("capture_runtime_inputs")

    ok, reason = validate_training_readiness_payload(payload)

    assert ok is False
    assert "runtime input" in reason.lower()


def test_validate_training_readiness_payload_requires_training_confirmation():
    payload = _base_payload()
    payload["confirmation_events"] = []

    ok, reason = validate_training_readiness_payload(payload)

    assert ok is False
    assert "confirmation" in reason


def test_validate_training_readiness_payload_rejects_stale_dataset_empty_state():
    payload = _base_payload()
    payload["ui_state"]["dataset_table_rows"] = 0
    payload["ui_state"]["dataset_empty_state_visible"] = True

    ok, reason = validate_training_readiness_payload(payload, strict=False)

    assert ok is False
    assert "Dataset-ready" in reason


def test_render_markdown_records_analysis_boundary():
    markdown = render_markdown(_base_payload())

    assert "# ChatPanel Local Training Readiness Walkthrough" in markdown
    assert "training confirmation cards observed: `1`" in markdown
    assert "shutdown: `completed`" in markdown
    assert "expected tool: `saliency`" in markdown
    assert "evaluate blocked: `True`" in markdown
    assert "dataset table rows: `1`" in markdown
    assert "/tmp/source.fif" not in markdown
