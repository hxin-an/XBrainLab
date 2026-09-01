from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import re
from contextlib import suppress
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
from XBrainLab.backend.training.option import class_map_fingerprint
from XBrainLab.backend.training.record import EvalRecord, RecordKey, TrainRecord
from XBrainLab.backend.training.record import artifact_store as artifact_store_module
from XBrainLab.backend.training.record.artifact_store import (
    ArtifactStoreError,
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


def test_artifact_writer_rejects_numpy_allow_pickle_control_key(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "record"

    with pytest.raises(ArtifactStoreError, match="Invalid artifact array name"):
        write_json_npz_artifact(
            manifest,
            artifact_type="test.artifact",
            payload={},
            arrays={
                "allow_pickle": np.array([1.0]),
                "values": np.array([2.0]),
            },
        )

    assert not manifest.exists()
    assert not manifest.with_name("record.npz").exists()


@pytest.mark.platform_contract
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


@pytest.mark.platform_contract
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


@pytest.mark.platform_contract
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


@pytest.mark.platform_contract
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


@pytest.mark.platform_contract
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


@pytest.mark.platform_contract
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


@pytest.mark.platform_contract
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


@pytest.mark.platform_contract
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
    model_identity = {
        "model_id": "braindecode.eegnet",
        "provider": "braindecode",
        "source_revision": "braindecode==1.6.1",
    }
    with patch.object(TrainRecord, "init_dir"):
        record = TrainRecord(
            0,
            dataset,
            model,
            training_option,
            seed,
            model_identity=model_identity,
        )
    record.target_path = str(tmp_path)
    record._artifact_io_path = str(tmp_path)
    record.update_train({RecordKey.LOSS: 0.5, RecordKey.ACC: 75.0})
    record.update_validation({RecordKey.LOSS: 0.6, RecordKey.ACC: 70.0})
    record.step()

    record.export_checkpoint()

    manifest = _read_manifest(tmp_path / "record")
    assert manifest["artifact_store_schema_version"] == 1
    assert manifest["artifact_type"] == "xbrainlab.training_record"
    assert manifest["payload"]["model_identity"] == model_identity
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
        loaded = TrainRecord(
            0,
            dataset,
            model_holder.get_model({}),
            training_option,
            0,
            model_identity=model_identity,
        )
    loaded.target_path = str(tmp_path)
    loaded._artifact_io_path = str(tmp_path)
    loaded.load()
    assert loaded.seed == 42
    assert loaded.epoch == 1
    assert loaded.train[RecordKey.LOSS] == [0.5]
    assert loaded.val[RecordKey.ACC] == [70.0]
    assert loaded.model_identity == model_identity


def _class_weighting_payload(
    epoch_dataset,
    *,
    mode: str,
) -> tuple[dict[str, object], dict[str, object]]:
    class_map = epoch_dataset.get_epoch_data().get_label_map()
    class_order = sorted(class_map)
    class_names = [class_map[index] for index in class_order]
    counts = [5] * len(class_order)
    fingerprint = class_map_fingerprint(class_map)
    if mode == "off":
        requested = {
            "mode": "off",
            "custom_class_weights": {},
            "class_map_fingerprint": fingerprint,
        }
        weights = [1.0] * len(class_order)
    elif mode == "balanced":
        requested = {
            "mode": "balanced",
            "custom_class_weights": {},
            "class_map_fingerprint": fingerprint,
        }
        weights = [1.0] * len(class_order)
    else:
        custom = {name: index + 1.0 for index, name in enumerate(class_names)}
        requested = {
            "mode": "custom",
            "custom_class_weights": custom,
            "class_map_fingerprint": fingerprint,
        }
        weights = [custom[name] for name in class_names]
    return requested, {
        "class_names": class_names,
        "class_order": class_order,
        "class_counts": counts,
        "weights": weights,
    }


@pytest.mark.parametrize("mode", ["off", "balanced", "custom"])
def test_training_record_v3_weighting_round_trip_is_lossless(
    tmp_path: Path,
    dataset,  # noqa: F811
    training_option,  # noqa: F811
    model_holder,  # noqa: F811
    mode: str,
) -> None:
    requested, resolved = _class_weighting_payload(dataset, mode=mode)
    with patch.object(TrainRecord, "init_dir"):
        record = TrainRecord(
            0,
            dataset,
            model_holder.get_model({}),
            training_option,
            1,
            class_weighting_requested=requested,
            class_weighting_resolution=resolved,
        )
    record.target_path = str(tmp_path)
    record._artifact_io_path = str(tmp_path)
    record.export_checkpoint()

    manifest = _read_manifest(tmp_path / "record")
    payload = manifest["payload"]
    assert payload["record_schema_version"] == 3
    assert payload["class_weighting"] == {
        "requested": requested,
        "resolved": resolved,
    }
    assert payload["early_stopping"] == {
        "enabled": False,
        "patience": 3,
        "min_delta": 0.0,
        "stopped_early": False,
        "best_value": None,
        "best_epoch": None,
        "consecutive_non_improvements": 0,
        "stop_epoch": None,
    }

    with patch.object(TrainRecord, "init_dir"):
        loaded = TrainRecord(
            0,
            dataset,
            model_holder.get_model({}),
            training_option,
            0,
        )
    loaded.target_path = str(tmp_path)
    loaded._artifact_io_path = str(tmp_path)
    loaded.load()

    assert loaded.class_weighting == {
        "requested": requested,
        "resolved": resolved,
    }
    if mode == "off":
        assert loaded.criterion.weight is None
    else:
        assert loaded.criterion.weight.tolist() == pytest.approx(resolved["weights"])


def test_training_record_v2_migrates_early_stopping_to_disabled(
    tmp_path: Path,
    dataset,  # noqa: F811
    training_option,  # noqa: F811
    model_holder,  # noqa: F811
) -> None:
    with patch.object(TrainRecord, "init_dir"):
        record = TrainRecord(0, dataset, model_holder.get_model({}), training_option, 1)
    record.target_path = str(tmp_path)
    record._artifact_io_path = str(tmp_path)
    record.export_checkpoint()
    manifest_path = tmp_path / "record"
    manifest = _read_manifest(manifest_path)
    manifest["payload"]["record_schema_version"] = 2
    del manifest["payload"]["early_stopping"]
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with patch.object(TrainRecord, "init_dir"):
        restored = TrainRecord(
            0, dataset, model_holder.get_model({}), training_option, 1
        )
    restored.target_path = str(tmp_path)
    restored._artifact_io_path = str(tmp_path)
    restored.load()

    assert restored.early_stopping["enabled"] is False
    assert restored.early_stopping["stopped_early"] is False


@pytest.mark.parametrize(
    "mutate",
    [
        lambda weighting: weighting["requested"].pop("mode"),
        lambda weighting: weighting["resolved"].pop("weights"),
        lambda weighting: weighting["resolved"]["weights"].__setitem__(0, float("nan")),
        lambda weighting: weighting["resolved"]["weights"].__setitem__(0, -1.0),
        lambda weighting: weighting["resolved"]["class_counts"].__setitem__(0, -1),
        lambda weighting: weighting["resolved"]["weights"].append(1.0),
        lambda weighting: weighting["resolved"]["class_names"].__setitem__(
            0, "renamed"
        ),
        lambda weighting: weighting["requested"]["custom_class_weights"].__setitem__(
            " C1 ",
            weighting["requested"]["custom_class_weights"].pop("C1"),
        ),
    ],
)
def test_training_record_v2_rejects_weighting_mutations_without_partial_load(
    tmp_path: Path,
    dataset,  # noqa: F811
    training_option,  # noqa: F811
    model_holder,  # noqa: F811
    mutate,
) -> None:
    requested, resolved = _class_weighting_payload(dataset, mode="custom")
    with patch.object(TrainRecord, "init_dir"):
        record = TrainRecord(
            0,
            dataset,
            model_holder.get_model({}),
            training_option,
            1,
            class_weighting_requested=requested,
            class_weighting_resolution=resolved,
        )
    record.target_path = str(tmp_path)
    record._artifact_io_path = str(tmp_path)
    record.export_checkpoint()
    manifest_path = tmp_path / "record"
    manifest = _read_manifest(manifest_path)
    mutate(manifest["payload"]["class_weighting"])
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with patch.object(TrainRecord, "init_dir"):
        restored = TrainRecord(
            0,
            dataset,
            model_holder.get_model({}),
            training_option,
            0,
        )
    restored.target_path = str(tmp_path)
    restored._artifact_io_path = str(tmp_path)
    before = copy.deepcopy(restored.class_weighting)
    # Non-standard JSON NaN is rejected by the safe store before the v2 schema
    # parser; all other mutations reach its fail-closed validator.
    with suppress(RuntimeError):
        restored.load()

    assert restored.class_weighting == before


def test_training_record_v1_migrates_to_explicit_off_weighting(
    tmp_path: Path,
    dataset,  # noqa: F811
    training_option,  # noqa: F811
    model_holder,  # noqa: F811
) -> None:
    requested, resolved = _class_weighting_payload(dataset, mode="custom")
    with patch.object(TrainRecord, "init_dir"):
        record = TrainRecord(
            0,
            dataset,
            model_holder.get_model({}),
            training_option,
            1,
            class_weighting_requested=requested,
            class_weighting_resolution=resolved,
        )
    record.target_path = str(tmp_path)
    record._artifact_io_path = str(tmp_path)
    record.export_checkpoint()
    manifest_path = tmp_path / "record"
    manifest = _read_manifest(manifest_path)
    manifest["payload"]["record_schema_version"] = 1
    del manifest["payload"]["class_weighting"]
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with patch.object(TrainRecord, "init_dir"):
        restored = TrainRecord(
            0,
            dataset,
            model_holder.get_model({}),
            training_option,
            0,
        )
    restored.target_path = str(tmp_path)
    restored._artifact_io_path = str(tmp_path)
    restored.load()

    assert restored.class_weighting == {
        "requested": {
            "mode": "off",
            "custom_class_weights": {},
            "class_map_fingerprint": None,
        },
        "resolved": {
            "class_names": [],
            "class_order": [],
            "class_counts": [],
            "weights": [],
        },
    }


def test_training_record_rejects_v2_weighting_downgraded_only_by_schema_number(
    tmp_path: Path,
    dataset,  # noqa: F811
    training_option,  # noqa: F811
    model_holder,  # noqa: F811
) -> None:
    requested, resolved = _class_weighting_payload(dataset, mode="custom")
    with patch.object(TrainRecord, "init_dir"):
        record = TrainRecord(
            0,
            dataset,
            model_holder.get_model({}),
            training_option,
            1,
            class_weighting_requested=requested,
            class_weighting_resolution=resolved,
        )
    record.target_path = str(tmp_path)
    record._artifact_io_path = str(tmp_path)
    record.export_checkpoint()

    manifest_path = tmp_path / "record"
    manifest = _read_manifest(manifest_path)
    manifest["payload"]["record_schema_version"] = 1
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with patch.object(TrainRecord, "init_dir"):
        restored = TrainRecord(
            0,
            dataset,
            model_holder.get_model({}),
            training_option,
            0,
        )
    restored.target_path = str(tmp_path)
    restored._artifact_io_path = str(tmp_path)
    before = copy.deepcopy(restored.class_weighting)

    with pytest.raises(ArtifactStoreError, match=r"v1.*class-weighting"):
        restored.load()

    assert restored.class_weighting == before


def test_training_record_rejects_different_provider_identity(
    tmp_path: Path,
    dataset,  # noqa: F811
    training_option,  # noqa: F811
    model_holder,  # noqa: F811
) -> None:
    upstream_identity = {
        "model_id": "braindecode.eegnet",
        "provider": "braindecode",
        "source_revision": "braindecode==1.6.1",
    }
    with patch.object(TrainRecord, "init_dir"):
        record = TrainRecord(
            0,
            dataset,
            model_holder.get_model({}),
            training_option,
            0,
            model_identity=upstream_identity,
        )
    record.target_path = str(tmp_path)
    record._artifact_io_path = str(tmp_path)
    record.export_checkpoint()

    with patch.object(TrainRecord, "init_dir"):
        recovery = TrainRecord(
            0,
            dataset,
            model_holder.get_model({}),
            training_option,
            0,
            model_identity={
                "model_id": "legacy.braindecode.eegnet",
                "provider": "legacy-braindecode",
                "source_revision": "braindecode==1.6.1+xbrainlab-reviewed",
            },
        )
    recovery.target_path = str(tmp_path)
    recovery._artifact_io_path = str(tmp_path)

    with pytest.raises(RuntimeError, match="model identity does not match"):
        recovery.load()


def test_training_record_does_not_assign_provider_to_identityless_artifact(
    tmp_path: Path,
    dataset,  # noqa: F811
    training_option,  # noqa: F811
    model_holder,  # noqa: F811
) -> None:
    with patch.object(TrainRecord, "init_dir"):
        unknown = TrainRecord(
            0,
            dataset,
            model_holder.get_model({}),
            training_option,
            0,
        )
    unknown.target_path = str(tmp_path)
    unknown._artifact_io_path = str(tmp_path)
    unknown.export_checkpoint()

    with patch.object(TrainRecord, "init_dir"):
        recovery = TrainRecord(
            0,
            dataset,
            model_holder.get_model({}),
            training_option,
            0,
            model_identity={
                "model_id": "legacy.braindecode.eegnet",
                "provider": "legacy-braindecode",
                "source_revision": "braindecode==1.6.1+xbrainlab-reviewed",
            },
        )
    recovery.target_path = str(tmp_path)
    recovery._artifact_io_path = str(tmp_path)

    with pytest.raises(RuntimeError, match="no model provider identity"):
        recovery.load()


def test_training_record_rejects_malformed_provider_identity(
    tmp_path: Path,
    dataset,  # noqa: F811
    training_option,  # noqa: F811
    model_holder,  # noqa: F811
) -> None:
    model_identity = {
        "model_id": "braindecode.eegnet",
        "provider": "braindecode",
        "source_revision": "braindecode==1.6.1",
    }
    with patch.object(TrainRecord, "init_dir"):
        record = TrainRecord(
            0,
            dataset,
            model_holder.get_model({}),
            training_option,
            0,
            model_identity=model_identity,
        )
    record.target_path = str(tmp_path)
    record._artifact_io_path = str(tmp_path)
    record.export_checkpoint()
    manifest_path = tmp_path / "record"
    manifest = _read_manifest(manifest_path)
    manifest["payload"]["model_identity"] = {"provider": "braindecode"}
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with patch.object(TrainRecord, "init_dir"):
        restored = TrainRecord(
            0,
            dataset,
            model_holder.get_model({}),
            training_option,
            0,
            model_identity=model_identity,
        )
    restored.target_path = str(tmp_path)
    restored._artifact_io_path = str(tmp_path)

    with pytest.raises(RuntimeError, match="model identity is malformed"):
        restored.load()


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
