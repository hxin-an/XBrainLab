from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import torch

from tests.unit.backend.training.test_training_plan import (
    dataset,  # noqa: F401
    epochs,  # noqa: F401
    model_holder,  # noqa: F401
    preprocessed_data_list,  # noqa: F401
    training_option,  # noqa: F401
    y,  # noqa: F401
)
from XBrainLab.backend.training.record import EvalRecord, RecordKey, TrainRecord
from XBrainLab.backend.training.record import artifact_store as artifact_store_module
from XBrainLab.backend.training.record.artifact_store import (
    load_model_state_dict,
    read_json_npz_artifact,
    write_json_npz_artifact,
)
from XBrainLab.backend.utils import set_seed
from XBrainLab.backend.utils.filesystem_identity import FilesystemIdentityError


class _ReplacingDirectoryIdentity:
    def __init__(self) -> None:
        self.validation_count = 0

    def assert_matches(self, _directory=None) -> None:
        self.validation_count += 1
        if self.validation_count >= 2:
            raise FilesystemIdentityError(
                "Directory or ancestor identity changed before filesystem use."
            )


def _read_manifest(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_artifact_write_revalidates_before_opening_replaced_directory(
    tmp_path: Path,
) -> None:
    identity = _ReplacingDirectoryIdentity()

    with pytest.raises(FilesystemIdentityError, match="identity changed"):
        write_json_npz_artifact(
            tmp_path / "record",
            artifact_type="test.artifact",
            payload={},
            arrays={"values": np.array([1.0])},
            directory_identity=identity,  # type: ignore[arg-type]
        )

    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(os.name != "posix", reason="POSIX no-follow artifact contract")
def test_artifact_manifest_symlink_is_rejected(tmp_path: Path) -> None:
    store = tmp_path / "store"
    store.mkdir()
    manifest = store / "record"
    write_json_npz_artifact(
        manifest,
        artifact_type="test.artifact",
        payload={"value": 1},
        arrays={"values": np.array([1.0])},
    )
    outside_manifest = tmp_path / "outside-manifest.json"
    manifest.replace(outside_manifest)
    manifest.symlink_to(outside_manifest)

    with pytest.raises(FilesystemIdentityError, match="regular artifact file"):
        read_json_npz_artifact(
            manifest,
            expected_artifact_type="test.artifact",
        )


@pytest.mark.skipif(os.name != "posix", reason="POSIX no-follow artifact contract")
def test_artifact_numeric_payload_symlink_is_rejected(tmp_path: Path) -> None:
    store = tmp_path / "store"
    store.mkdir()
    manifest = store / "record"
    arrays_path = store / "record.npz"
    write_json_npz_artifact(
        manifest,
        artifact_type="test.artifact",
        payload={"value": 1},
        arrays={"values": np.array([1.0])},
        arrays_filename=arrays_path.name,
    )
    outside_arrays = tmp_path / "outside-arrays.npz"
    arrays_path.replace(outside_arrays)
    arrays_path.symlink_to(outside_arrays)

    with pytest.raises(FilesystemIdentityError, match="regular artifact file"):
        read_json_npz_artifact(
            manifest,
            expected_artifact_type="test.artifact",
        )


@pytest.mark.skipif(os.name != "posix", reason="POSIX no-follow artifact contract")
def test_artifact_manifest_hardlink_is_rejected(tmp_path: Path) -> None:
    manifest = tmp_path / "record"
    write_json_npz_artifact(
        manifest,
        artifact_type="test.artifact",
        payload={"value": 1},
        arrays={"values": np.array([1.0])},
    )
    os.link(manifest, tmp_path / "manifest-alias")

    with pytest.raises(FilesystemIdentityError, match="multiple hard links"):
        read_json_npz_artifact(
            manifest,
            expected_artifact_type="test.artifact",
        )


@pytest.mark.skipif(os.name != "posix", reason="POSIX no-follow artifact contract")
def test_artifact_numeric_payload_hardlink_is_rejected(tmp_path: Path) -> None:
    manifest = tmp_path / "record"
    arrays_path = tmp_path / "record.npz"
    write_json_npz_artifact(
        manifest,
        artifact_type="test.artifact",
        payload={"value": 1},
        arrays={"values": np.array([1.0])},
        arrays_filename=arrays_path.name,
    )
    os.link(arrays_path, tmp_path / "arrays-alias.npz")

    with pytest.raises(FilesystemIdentityError, match="multiple hard links"):
        read_json_npz_artifact(
            manifest,
            expected_artifact_type="test.artifact",
        )


@pytest.mark.skipif(os.name != "posix", reason="POSIX no-follow artifact contract")
def test_artifact_write_does_not_follow_existing_temporary_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outside = tmp_path / "outside"
    outside.write_bytes(b"must remain unchanged")
    malicious_temp = tmp_path / "arrays-temp"
    malicious_temp.symlink_to(outside)
    temporary_paths = iter([malicious_temp, tmp_path / "manifest-temp"])
    monkeypatch.setattr(
        artifact_store_module,
        "_temporary_path",
        lambda _target: next(temporary_paths),
    )

    with pytest.raises(FilesystemIdentityError, match="temporary entry"):
        write_json_npz_artifact(
            tmp_path / "record",
            artifact_type="test.artifact",
            payload={},
            arrays={"values": np.array([1.0])},
        )

    assert outside.read_bytes() == b"must remain unchanged"


@pytest.mark.skipif(os.name != "posix", reason="POSIX no-follow artifact contract")
def test_model_checkpoint_symlink_is_rejected(tmp_path: Path) -> None:
    store = tmp_path / "store"
    store.mkdir()
    outside_checkpoint = tmp_path / "outside-checkpoint"
    outside_checkpoint.write_bytes(b"must not be opened through a symlink")
    checkpoint = store / "model"
    checkpoint.symlink_to(outside_checkpoint)

    with pytest.raises(FilesystemIdentityError, match="regular artifact file"):
        load_model_state_dict(checkpoint)


@pytest.mark.skipif(os.name != "posix", reason="POSIX no-follow artifact contract")
def test_model_checkpoint_hardlink_is_rejected(tmp_path: Path) -> None:
    store = tmp_path / "store"
    store.mkdir()
    outside_checkpoint = tmp_path / "outside-checkpoint"
    outside_checkpoint.write_bytes(b"must not be opened through a hard link")
    checkpoint = store / "model"
    os.link(outside_checkpoint, checkpoint)

    with pytest.raises(FilesystemIdentityError, match="multiple hard links"):
        load_model_state_dict(checkpoint)


@pytest.mark.skipif(os.name != "posix", reason="POSIX no-follow artifact contract")
def test_model_checkpoint_non_regular_file_is_rejected(tmp_path: Path) -> None:
    checkpoint = tmp_path / "model"
    os.mkfifo(checkpoint)

    with pytest.raises(FilesystemIdentityError, match="regular artifact file"):
        load_model_state_dict(checkpoint)


def test_eval_record_uses_versioned_json_and_non_pickle_npz(tmp_path: Path) -> None:
    label = np.array([0, 1], dtype=np.int64)
    output = np.array([[0.9, 0.1], [0.2, 0.8]], dtype=np.float32)
    record = EvalRecord(label, output, {}, {}, {}, {}, {})

    record.export(str(tmp_path))

    manifest = _read_manifest(tmp_path / "eval")
    assert manifest["artifact_store_schema_version"] == 1
    assert manifest["artifact_type"] == "xbrainlab.evaluation_record"
    arrays = manifest["arrays"]
    assert isinstance(arrays, dict)
    assert arrays["file"] == "eval.npz"
    with np.load(tmp_path / "eval.npz", allow_pickle=False) as archive:
        assert set(archive.files) == {"label", "output"}
        assert all(not archive[name].dtype.hasobject for name in archive.files)

    loaded = EvalRecord.load(str(tmp_path))
    assert loaded is not None
    np.testing.assert_array_equal(loaded.label, label)
    np.testing.assert_array_equal(loaded.output, output)


def test_eval_record_rejects_object_array_npz_without_pickle(
    tmp_path: Path,
) -> None:
    record = EvalRecord(
        np.array([0], dtype=np.int64),
        np.array([[1.0]], dtype=np.float32),
        {},
        {},
        {},
        {},
        {},
    )
    record.export(str(tmp_path))
    arrays_path = tmp_path / "eval.npz"
    np.savez(
        arrays_path,
        label=np.array([object()], dtype=object),
        output=np.array([[1.0]], dtype=np.float32),
    )
    manifest = _read_manifest(tmp_path / "eval")
    arrays = manifest["arrays"]
    assert isinstance(arrays, dict)
    arrays["sha256"] = hashlib.sha256(arrays_path.read_bytes()).hexdigest()
    (tmp_path / "eval").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    assert EvalRecord.load(str(tmp_path)) is None


def test_legacy_eval_artifact_is_rejected_without_deserialization(
    tmp_path: Path,
) -> None:
    torch.save(
        {
            "label": np.array([0]),
            "output": np.array([[1.0]]),
            "gradient": {},
        },
        tmp_path / "eval",
    )

    with (
        patch("torch.load", side_effect=AssertionError("must not deserialize")),
        pytest.raises(
            RuntimeError,
            match=r"(?i)unsupported legacy evaluation record.*start a new evaluation",
        ),
    ):
        EvalRecord.load(str(tmp_path))


def test_training_record_round_trip_uses_safe_store_and_state_dicts(
    tmp_path: Path,
    dataset,  # noqa: F811
    training_option,  # noqa: F811
    model_holder,  # noqa: F811
) -> None:
    seed = set_seed(42)
    model = model_holder.get_model({})
    with patch.object(TrainRecord, "init_dir"):
        record = TrainRecord(0, dataset, model, training_option, seed)
    record.target_path = str(tmp_path)
    record._artifact_io_path = str(tmp_path)
    record.update_train({RecordKey.LOSS: 0.5, RecordKey.ACC: 75.0})
    record.update_validation({RecordKey.LOSS: 0.6, RecordKey.ACC: 70.0})
    record.step()

    record.export_checkpoint()

    manifest = _read_manifest(tmp_path / "record")
    assert manifest["artifact_store_schema_version"] == 1
    assert manifest["artifact_type"] == "xbrainlab.training_record"
    with np.load(tmp_path / "record.npz", allow_pickle=False) as archive:
        assert archive.files
        assert all(not archive[name].dtype.hasobject for name in archive.files)
    for checkpoint in (
        tmp_path / "Epoch-1-model",
        tmp_path / "best_val_loss_model",
        tmp_path / "best_val_accuracy_model",
    ):
        state = torch.load(checkpoint, map_location="cpu", weights_only=True)
        assert isinstance(state, dict)
        assert state
        assert all(isinstance(value, torch.Tensor) for value in state.values())

    with patch.object(TrainRecord, "init_dir"):
        loaded = TrainRecord(0, dataset, model_holder.get_model({}), training_option, 0)
    loaded.target_path = str(tmp_path)
    loaded._artifact_io_path = str(tmp_path)
    loaded.load()
    assert loaded.seed == 42
    assert loaded.epoch == 1
    assert loaded.train[RecordKey.LOSS] == [0.5]
    assert loaded.val[RecordKey.ACC] == [70.0]


def test_legacy_training_record_is_rejected_without_deserialization(
    tmp_path: Path,
    dataset,  # noqa: F811
    training_option,  # noqa: F811
    model_holder,  # noqa: F811
) -> None:
    torch.save(
        {
            "train": {},
            "val": {},
            "best_record": {},
            "seed": 1,
        },
        tmp_path / "record",
    )
    with patch.object(TrainRecord, "init_dir"):
        record = TrainRecord(
            0,
            dataset,
            model_holder.get_model({}),
            training_option,
            0,
        )
    record.target_path = str(tmp_path)
    record._artifact_io_path = str(tmp_path)

    with (
        patch("torch.load", side_effect=AssertionError("must not deserialize")),
        pytest.raises(
            RuntimeError,
            match=r"(?i)unsupported legacy training record.*start a new training run",
        ),
    ):
        record.load()


def test_product_source_requires_weights_only_true() -> None:
    repo_root = Path(__file__).resolve().parents[5]
    forbidden = re.compile(r"weights_only\s*=\s*False")
    violations: list[str] = []
    unsafe_loads: list[str] = []
    for path in sorted((repo_root / "XBrainLab").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        relative_path = str(path.relative_to(repo_root))
        if forbidden.search(source):
            violations.append(relative_path)
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "torch"
                and node.func.attr == "load"
            ):
                continue
            weights_only = next(
                (
                    keyword.value
                    for keyword in node.keywords
                    if keyword.arg == "weights_only"
                ),
                None,
            )
            if not (
                isinstance(weights_only, ast.Constant) and weights_only.value is True
            ):
                unsafe_loads.append(f"{relative_path}:{node.lineno}")

    assert violations == []
    assert unsafe_loads == []
