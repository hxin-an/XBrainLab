"""Shared assertions for real training artifact persistence workflows."""

from __future__ import annotations

from pathlib import Path

from XBrainLab.backend.training.record import EvalRecord
from XBrainLab.backend.training.record.artifact_store import load_model_state_dict


def assert_real_training_artifacts(output_root: Path) -> None:
    """Prove that one real-source run persisted reloadable safe artifacts."""
    record_manifests = list(output_root.rglob("record"))
    assert len(record_manifests) == 1
    artifact_dir = record_manifests[0].parent
    persisted_names = {path.name for path in artifact_dir.iterdir() if path.is_file()}
    assert {"record", "record.npz", "eval", "eval.npz"} <= persisted_names
    checkpoint_paths = [
        path
        for path in artifact_dir.iterdir()
        if path.is_file() and path.name.startswith("Epoch-1-model")
    ]
    assert len(checkpoint_paths) == 1
    reloaded_state_dict = load_model_state_dict(checkpoint_paths[0])
    assert reloaded_state_dict

    reloaded_evaluation = EvalRecord.load(str(artifact_dir))
    assert reloaded_evaluation is not None
    assert len(reloaded_evaluation.label) > 0
    assert len(reloaded_evaluation.output) == len(reloaded_evaluation.label)
