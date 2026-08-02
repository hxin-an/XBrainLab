"""Security regressions for training output path construction."""

from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, cast

import pytest

from tests.unit.backend.dataset.test_epochs import (  # noqa: F401
    epochs,
    preprocessed_data_list,
)
from tests.unit.backend.training.test_training_plan import (  # noqa: F401
    dataset,
    model_holder,
    training_option,
)
from XBrainLab.backend.dataset import (
    DatasetGenerator,
    DataSplittingConfig,
    TrainingType,
)
from XBrainLab.backend.training.record import TrainRecord
from XBrainLab.backend.training.record.key import RecordKey
from XBrainLab.backend.utils import filesystem_identity, set_seed
from XBrainLab.backend.utils.filesystem_identity import (
    FilesystemIdentityError,
    create_contained_output_directory,
    filesystem_safe_identity,
)


class _DisplayDataset:
    def __init__(self, display_name: str):
        self.display_name = display_name

    def get_name(self) -> str:
        return self.display_name


class _Option:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def get_output_dir(self) -> str:
        return str(self.output_dir)


class Model:
    pass


class _EpochData:
    def __init__(self, subject_name: str | list[str]):
        self.subject_names = (
            [subject_name] if isinstance(subject_name, str) else list(subject_name)
        )

    def get_subject_index_list(self) -> list[int]:
        return list(range(len(self.subject_names)))

    def get_subject_name(self, subject_idx: int) -> str:
        return self.subject_names[subject_idx]

    def reset_trial_selection_evidence(self) -> None:
        pass


def _record(
    output_dir: Path,
    display_name: str,
    *,
    plan_id: str | None = "20260730-120000-000000-a1b2c3d4e5f6",
) -> TrainRecord:
    record = TrainRecord.__new__(TrainRecord)
    mutable_record = cast(Any, record)
    mutable_record.repeat = 0
    mutable_record.dataset = _DisplayDataset(display_name)
    mutable_record.option = _Option(output_dir)
    mutable_record.model = Model()
    mutable_record.plan_id = plan_id
    mutable_record.target_path = None
    mutable_record._artifact_io_path = None
    mutable_record._output_directory = None
    return record


def _expected_identity(display_name: str) -> str:
    normalized = unicodedata.normalize("NFKC", display_name.strip())
    ascii_name = (
        unicodedata.normalize("NFKD", normalized)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.casefold()).strip("-")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    return f"{slug[:48]}-{digest}"


def test_training_path_preserves_display_name_but_uses_stable_safe_identity(
    tmp_path: Path,
) -> None:
    display_name = "Subject-Alice Smith_0"
    first = _record(tmp_path / "first", display_name)
    second = _record(tmp_path / "second", display_name)

    first.init_dir()
    second.init_dir()

    assert first.dataset.get_name() == display_name
    assert second.dataset.get_name() == display_name
    first_path = Path(first.target_path or "")
    second_path = Path(second.target_path or "")
    expected_identity = _expected_identity(display_name)
    assert first_path.relative_to((tmp_path / "first").resolve()).parts[0] == (
        expected_identity
    )
    assert second_path.relative_to((tmp_path / "second").resolve()).parts[0] == (
        expected_identity
    )
    assert display_name not in first_path.parts


def test_training_path_hash_distinguishes_equal_slugs(tmp_path: Path) -> None:
    first = _record(tmp_path / "first", "Subject-A B_0")
    second = _record(tmp_path / "second", "Subject-A-B_0")

    first.init_dir()
    second.init_dir()

    first_component = (
        Path(first.target_path or "")
        .relative_to((tmp_path / "first").resolve())
        .parts[0]
    )
    second_component = (
        Path(second.target_path or "")
        .relative_to((tmp_path / "second").resolve())
        .parts[0]
    )
    assert first_component.startswith("subject-a-b-0-")
    assert second_component.startswith("subject-a-b-0-")
    assert first_component != second_component


def test_training_identity_normalizes_canonical_unicode_but_hashes_distinct_values() -> (
    None
):
    assert filesystem_safe_identity(
        "Caf\u00e9",
        field="dataset display metadata",
    ) == filesystem_safe_identity(
        "Cafe\u0301",
        field="dataset display metadata",
    )
    first = filesystem_safe_identity(
        "\u53d7\u8a66\u8005\u7532",
        field="dataset display metadata",
    )
    second = filesystem_safe_identity(
        "\u53d7\u8a66\u8005\u4e59",
        field="dataset display metadata",
    )
    assert first.startswith("item-")
    assert second.startswith("item-")
    assert first != second


def test_individual_dataset_name_preserves_unicode_display_metadata() -> None:
    subject_name = "Cafe\u0301-\u53d7\u8a66\u8005"
    generator = DatasetGenerator.__new__(DatasetGenerator)
    mutable_generator = cast(Any, generator)
    mutable_generator.epoch_data = _EpochData(subject_name)
    captured: list[str] = []
    mutable_generator.handle = lambda name, _hook=None: captured.append(name)

    generator.handle_ind()

    assert captured == [f"Subject-{subject_name}"]


def test_individual_subject_display_metadata_uses_safe_training_identity(
    tmp_path: Path,
    epochs,  # noqa: F811
) -> None:
    config = DataSplittingConfig(TrainingType.IND, False, [], [])
    generated_dataset = DatasetGenerator(epochs, config).generate()[0]
    record = _record(tmp_path / "authorized", "unused")
    record.dataset = generated_dataset

    record.init_dir()

    assert generated_dataset.get_name() == "Subject-1_0"
    target = Path(record.target_path or "")
    assert target.relative_to((tmp_path / "authorized").resolve()).parts[0] == (
        _expected_identity(generated_dataset.get_name())
    )


@pytest.mark.parametrize(
    "subject_name",
    [
        "../escape",
        r"..\escape",
        ".",
        "..",
        "NUL",
        "com1.csv",
        "CONIN$",
        "conout$.txt",
        "subject\x1fname",
    ],
)
def test_individual_dataset_generation_rejects_unsafe_subject_metadata(
    subject_name: str,
) -> None:
    generator = DatasetGenerator.__new__(DatasetGenerator)
    mutable_generator = cast(Any, generator)
    mutable_generator.epoch_data = _EpochData(subject_name)
    mutable_generator.handle = lambda *_args, **_kwargs: pytest.fail(
        "unsafe subject metadata reached dataset generation"
    )

    with pytest.raises(ValueError, match="subject metadata"):
        generator.handle_ind()


@pytest.mark.parametrize(
    "display_name",
    [
        "../escape",
        r"..\escape",
        ".",
        "..",
        "CON",
        "con.txt",
        "CONIN$",
        "conout$.txt",
        "subject\x00name",
        "subject\nname",
    ],
)
def test_training_path_rejects_unsafe_display_metadata_without_writing(
    tmp_path: Path,
    display_name: str,
) -> None:
    authorized_root = tmp_path / "authorized"
    record = _record(authorized_root, display_name)

    with pytest.raises(ValueError, match="training output"):
        record.init_dir()

    assert not authorized_root.exists()
    assert list(tmp_path.iterdir()) == []


def test_training_plan_target_is_created_exclusively(tmp_path: Path) -> None:
    authorized_root = tmp_path / "authorized"
    first = _record(authorized_root, "Subject-01_0")
    duplicate = _record(authorized_root, "Subject-01_0")

    first.init_dir()

    with pytest.raises(FileExistsError, match="implicit resume"):
        duplicate.init_dir()


def test_fallback_output_identity_rejects_same_path_replacement(
    tmp_path: Path,
) -> None:
    output = filesystem_identity._create_fallback_output_directory(
        tmp_path / "authorized",
        ("dataset", "Model_plan", "Repeat-0"),
        exclusive=True,
        legacy_components=(),
    )
    target = output.path
    target.rename(target.with_name("displaced-repeat"))
    target.mkdir()

    with pytest.raises(FilesystemIdentityError, match="identity changed"):
        output.retain_identity()


def test_pre_sec02_output_namespace_is_rejected_explicitly(tmp_path: Path) -> None:
    authorized_root = tmp_path / "authorized"
    display_name = "Subject-01_0"
    legacy_target = authorized_root / display_name / "Model" / "Repeat-0"
    legacy_target.mkdir(parents=True)
    record = _record(authorized_root, display_name, plan_id=None)

    with pytest.raises(RuntimeError, match="pre-SEC-02"):
        record.init_dir()

    safe_target = authorized_root / filesystem_safe_identity(
        display_name,
        field="dataset display metadata",
    )
    assert not safe_target.exists()


def test_individual_generation_rolls_back_all_subjects_on_metadata_failure() -> None:
    generator = DatasetGenerator.__new__(DatasetGenerator)
    mutable_generator = cast(Any, generator)
    mutable_generator.epoch_data = _EpochData(["safe", "../escape"])
    mutable_generator.config = type("Config", (), {"train_type": TrainingType.IND})()
    mutable_generator.datasets = []
    mutable_generator.interrupted = False
    mutable_generator.preview_failed = False
    mutable_generator.done = False
    mutable_generator.handle = (
        lambda name, _hook=None: mutable_generator.datasets.append(name)
    )

    with pytest.raises(ValueError, match="subject metadata"):
        generator.generate()

    assert generator.datasets == []
    assert generator.preview_failed is True
    with pytest.raises(ValueError, match="not clean"):
        generator.generate()


def test_individual_generation_rolls_back_when_later_subject_handling_fails() -> None:
    generator = DatasetGenerator.__new__(DatasetGenerator)
    mutable_generator = cast(Any, generator)
    mutable_generator.epoch_data = _EpochData(["first", "second"])
    mutable_generator.config = type("Config", (), {"train_type": TrainingType.IND})()
    mutable_generator.datasets = []
    mutable_generator.interrupted = False
    mutable_generator.preview_failed = False
    mutable_generator.done = False

    def handle(name: str, _hook=None) -> None:
        mutable_generator.datasets.append(name)
        if name == "Subject-second":
            raise RuntimeError("later subject failed")

    mutable_generator.handle = handle

    with pytest.raises(RuntimeError, match="later subject failed"):
        generator.generate()

    assert generator.datasets == []
    assert generator.preview_failed is True
    with pytest.raises(ValueError, match="not clean"):
        generator.generate()


@pytest.mark.skipif(os.name != "posix", reason="POSIX dir-fd security contract")
def test_directory_creation_rejects_symlink_swap_between_mkdir_and_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorized_root = tmp_path / "authorized"
    authorized_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    original_mkdir_at = filesystem_identity._mkdir_at

    def raced_mkdir(
        dir_fd: int,
        path: str,
    ) -> None:
        original_mkdir_at(dir_fd, path)
        if path == "dataset":
            os.rename(
                "dataset",
                "held-dataset",
                src_dir_fd=dir_fd,
                dst_dir_fd=dir_fd,
            )
            os.symlink(
                outside,
                "dataset",
                target_is_directory=True,
                dir_fd=dir_fd,
            )

    monkeypatch.setattr(filesystem_identity, "_mkdir_at", raced_mkdir)

    with pytest.raises(ValueError, match="symlinks"):
        create_contained_output_directory(
            authorized_root,
            "dataset",
            "Model_plan",
            "Repeat-0",
            exclusive=True,
        )

    assert list(outside.iterdir()) == []
    assert (authorized_root / "held-dataset").is_dir()


@pytest.mark.skipif(os.name != "posix", reason="POSIX dir-fd security contract")
def test_authorized_output_root_symlink_is_rejected(tmp_path: Path) -> None:
    real_root = tmp_path / "real-root"
    real_root.mkdir()
    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(real_root, target_is_directory=True)

    with pytest.raises(ValueError, match="symlinks"):
        create_contained_output_directory(
            linked_root,
            "dataset",
            "Model_plan",
            "Repeat-0",
            exclusive=True,
        )

    assert list(real_root.iterdir()) == []


@pytest.mark.skipif(os.name != "posix", reason="POSIX dir-fd security contract")
def test_artifact_writes_remain_bound_to_open_directory_after_symlink_swap(
    tmp_path: Path,
    dataset,  # noqa: F811
    model_holder,  # noqa: F811
    training_option,  # noqa: F811
) -> None:
    authorized_root = tmp_path / "authorized"
    training_option.output_dir = str(authorized_root)
    model = model_holder.get_model({})
    record = TrainRecord(
        0,
        dataset,
        model,
        training_option,
        set_seed(7),
        plan_id="20260730-120000-000000-a1b2c3d4e5f6",
    )
    original_target = Path(record.target_path or "")
    held_target = original_target.with_name("held-repeat")
    outside = tmp_path / "outside"
    outside.mkdir()
    original_target.rename(held_target)
    original_target.symlink_to(outside, target_is_directory=True)
    record.update_train({RecordKey.LOSS: 0.5, RecordKey.ACC: 75.0})
    record.update_validation({RecordKey.LOSS: 0.6, RecordKey.ACC: 70.0})
    record.step()

    record.export_checkpoint()

    assert (held_target / "record").is_file()
    assert (held_target / "record.npz").is_file()
    assert not (outside / "record").exists()
    assert not (outside / "record.npz").exists()
