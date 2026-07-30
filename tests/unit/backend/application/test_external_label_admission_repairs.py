"""Regression coverage for the external-label admission repair slice."""

from __future__ import annotations

import io
import os
from dataclasses import fields
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest

from XBrainLab.backend.application import commands as command_contracts
from XBrainLab.backend.application.automation import command_specs
from XBrainLab.backend.application.commands import (
    AttachLabelsCommand,
    ImportLabelsCommand,
    LabelImportPlan,
    PreviewLabelImportCommand,
)
from XBrainLab.backend.application.data_compatibility_service import (
    DataCompatibilityCommandService,
    HandlerResult,
)
from XBrainLab.backend.application.errors import PreconditionError
from XBrainLab.backend.application.label_resource_admission import (
    LabelResourceAdmissionService,
    LabelResourceSpec,
)
from XBrainLab.backend.exceptions import FileCorruptedError
from XBrainLab.backend.load_data import label_loader


class _Raw:
    def __init__(self, path: str) -> None:
        self.path = path
        self.label_revision = 0

    def get_filepath(self) -> str:
        return self.path

    def get_filename(self) -> str:
        return Path(self.path).name


class _Dataset:
    def __init__(self, raws: list[_Raw]) -> None:
        self.raws = raws
        self.batch_calls: list[tuple[Any, ...]] = []

    def get_loaded_data_list(self) -> list[_Raw]:
        return self.raws

    def apply_labels_batch(self, *args: Any) -> int:
        self.batch_calls.append(args)
        for raw in args[0]:
            raw.label_revision += 1
        return len(args[0])

    @property
    def label_revisions(self) -> list[int]:
        return [raw.label_revision for raw in self.raws]


class _Interpretation:
    def __init__(self) -> None:
        self.recorded: list[dict[str, Any]] = []

    def record_label_import_for_recipe(self, **kwargs: Any) -> dict[str, Any]:
        self.recorded.append(kwargs)
        return {"mode": kwargs["mode"]}


class _PipelineTransaction:
    def capture(self) -> None:
        return None

    def prepare_raw_replacement(self) -> None:
        return None

    def restore(self, _snapshot: None) -> None:
        return None


def _service(
    raw_paths: list[Path],
) -> tuple[DataCompatibilityCommandService, _Dataset, _Interpretation]:
    dataset = _Dataset([_Raw(str(path)) for path in raw_paths])
    interpretation = _Interpretation()
    return (
        DataCompatibilityCommandService(
            dataset=dataset,
            interpretation=interpretation,
            pipeline_transaction=_PipelineTransaction(),
        ),
        dataset,
        interpretation,
    )


def _payload(result: HandlerResult) -> dict[str, Any]:
    assert isinstance(result, tuple)
    return cast(tuple[str, dict[str, Any]], result)[1]


def test_attach_mixed_valid_txt_and_corrupt_mat_is_request_atomic(
    tmp_path: Path,
) -> None:
    first_raw = tmp_path / "sub-01_raw.fif"
    second_raw = tmp_path / "sub-02_raw.fif"
    valid_labels = tmp_path / "sub-01_labels.txt"
    corrupt_labels = tmp_path / "sub-02_labels.mat"
    valid_labels.write_text("1 2\n", encoding="utf-8")
    corrupt_labels.write_bytes(b"not a MATLAB payload")
    service, dataset, interpretation = _service([first_raw, second_raw])

    with pytest.raises(FileCorruptedError, match=r"Invalid \.mat file.*labels\.mat"):
        service.handle_attach_labels(
            AttachLabelsCommand(
                mapping={
                    first_raw.name: str(valid_labels),
                    second_raw.name: str(corrupt_labels),
                },
                label_paths=[str(valid_labels), str(corrupt_labels)],
            )
        )

    assert dataset.label_revisions == [0, 0]
    assert dataset.batch_calls == []
    assert interpretation.recorded == []


def test_import_rejects_entire_request_when_any_target_index_is_invalid(
    tmp_path: Path,
) -> None:
    raw_path = tmp_path / "sub-01_raw.fif"
    label_path = tmp_path / "labels.txt"
    label_path.write_text("1 2\n", encoding="utf-8")
    service, dataset, interpretation = _service([raw_path])

    with pytest.raises(PreconditionError, match="target index") as raised:
        service.handle_import_labels(
            ImportLabelsCommand(
                plan=LabelImportPlan(
                    target_indices=[0, 99],
                    label_paths=[str(label_path)],
                    file_mapping={str(raw_path): str(label_path)},
                    mapping={1: "left", 2: "right"},
                    mode="sequence",
                )
            )
        )

    assert raised.value.diagnostics["code"] == "label_target_index_invalid"
    assert raised.value.diagnostics["target_index"] == 99
    assert dataset.label_revisions == [0]
    assert dataset.batch_calls == []
    assert interpretation.recorded == []


def test_import_rejects_incomplete_requested_file_mapping_atomically(
    tmp_path: Path,
) -> None:
    first_raw = tmp_path / "sub-01_raw.fif"
    second_raw = tmp_path / "sub-02_raw.fif"
    label_path = tmp_path / "labels.txt"
    label_path.write_text("1 2\n", encoding="utf-8")
    service, dataset, interpretation = _service([first_raw, second_raw])

    with pytest.raises(PreconditionError, match="every selected target") as raised:
        service.handle_import_labels(
            ImportLabelsCommand(
                plan=LabelImportPlan(
                    target_indices=[0, 1],
                    label_paths=[str(label_path)],
                    file_mapping={str(first_raw): str(label_path)},
                    mapping={1: "left", 2: "right"},
                    mode="sequence",
                )
            )
        )

    assert raised.value.diagnostics["code"] == "label_target_mapping_incomplete"
    assert raised.value.diagnostics["missing_targets"] == [str(second_raw)]
    assert dataset.label_revisions == [0, 0]
    assert dataset.batch_calls == []
    assert interpretation.recorded == []


def test_attach_rejects_a_missing_requested_target_before_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_path = tmp_path / "sub-01_raw.fif"
    label_path = tmp_path / "labels.txt"
    label_path.write_text("1 2\n", encoding="utf-8")
    service, dataset, interpretation = _service([raw_path])
    parser_calls: list[str] = []
    monkeypatch.setattr(
        label_loader,
        "load_label_file",
        lambda path, **_kwargs: parser_calls.append(str(path)),
    )

    with pytest.raises(PreconditionError, match="requested target") as raised:
        service.handle_attach_labels(
            AttachLabelsCommand(
                mapping={
                    raw_path.name: str(label_path),
                    "missing_raw.fif": str(label_path),
                },
                label_paths=[str(label_path)],
            )
        )

    assert raised.value.diagnostics == {
        "code": "label_target_missing",
        "missing_targets": ["missing_raw.fif"],
    }
    assert parser_calls == []
    assert dataset.label_revisions == [0]
    assert dataset.batch_calls == []
    assert interpretation.recorded == []


def test_bounded_reader_denies_descriptor_bypass_after_adversarial_append(
    tmp_path: Path,
) -> None:
    label_path = tmp_path / "labels.txt"
    original = b"1 2\n"
    label_path.write_bytes(original)
    session = LabelResourceAdmissionService(command_name="test_labels").admit(
        [LabelResourceSpec(path=str(label_path))],
        confirmed=False,
        token=None,
    )

    with (
        pytest.raises(
            PreconditionError, match="changed after resource admission"
        ) as changed,
        session.reader.open_binary(
            str(label_path), purpose="descriptor bypass regression"
        ) as source,
    ):
        with label_path.open("ab") as external:
            external.write(b"9 9\n")
        with pytest.raises(io.UnsupportedOperation, match="Raw file descriptors"):
            os.read(source.fileno(), 64)
        source.seek(0)
        assert source.read() == original

    assert (
        changed.value.diagnostics["code"]
        == "interpretation_resource_changed_after_admission"
    )


def test_public_label_import_plan_and_production_schema_have_no_label_map() -> None:
    assert "label_map" not in {field.name for field in fields(LabelImportPlan)}
    with pytest.raises(TypeError, match="label_map"):
        LabelImportPlan(label_map={"labels.txt": [1]})  # type: ignore[call-arg]
    spec = next(
        item
        for item in command_specs(include_legacy_compatibility=True)
        if item.name == "import_labels"
    )
    plan_schema = spec.input_schema["properties"]["plan"]
    assert "label_map" not in plan_schema["properties"]


def test_preview_and_import_reuse_one_exact_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preview_type = getattr(command_contracts, "PreviewLabelImportCommand", None)
    assert preview_type is not None, (
        "A typed backend label-preview command is required."
    )
    raw_path = tmp_path / "sub-01_raw.fif"
    label_path = tmp_path / "labels.txt"
    label_path.write_text("1 2 1\n", encoding="utf-8")
    service, dataset, interpretation = _service([raw_path])
    hash_calls: list[str] = []
    parser_calls: list[str] = []

    from XBrainLab.backend.application import label_resource_admission

    real_hash = label_resource_admission._content_identity
    real_loader = label_loader.load_label_file

    def observed_hash(path: str, **kwargs: Any) -> dict[str, Any]:
        hash_calls.append(path)
        return real_hash(path, **kwargs)

    def observed_loader(path: str, **kwargs: Any) -> Any:
        parser_calls.append(path)
        return real_loader(path, **kwargs)

    monkeypatch.setattr(label_resource_admission, "_content_identity", observed_hash)
    monkeypatch.setattr(label_loader, "load_label_file", observed_loader)

    preview = _payload(
        service.handle_import_labels(preview_type(label_paths=[str(label_path)]))
    )["label_preview"]
    result = _payload(
        service.handle_import_labels(
            ImportLabelsCommand(
                plan=LabelImportPlan(
                    preview_id=preview["preview_id"],
                    target_indices=[0],
                    label_paths=[str(label_path)],
                    file_mapping={str(raw_path): str(label_path)},
                    mapping={1: "left", 2: "right"},
                    mode="sequence",
                )
            )
        )
    )

    assert result["success_count"] == 1
    assert hash_calls == [str(label_path)]
    assert parser_calls == [str(label_path)]
    assert dataset.label_revisions == [1]
    assert len(dataset.batch_calls) == 1
    assert len(interpretation.recorded) == 1


def test_same_size_mutation_invalidates_preview_without_applying_stale_payload(
    tmp_path: Path,
) -> None:
    preview_type = getattr(command_contracts, "PreviewLabelImportCommand", None)
    assert preview_type is not None, (
        "A typed backend label-preview command is required."
    )
    raw_path = tmp_path / "sub-01_raw.fif"
    label_path = tmp_path / "labels.txt"
    label_path.write_text("1 2\n", encoding="utf-8")
    service, dataset, interpretation = _service([raw_path])

    preview = _payload(
        service.handle_import_labels(preview_type(label_paths=[str(label_path)]))
    )["label_preview"]
    original_stat = label_path.stat()
    label_path.write_text("2 1\n", encoding="utf-8")
    os.utime(
        label_path,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
    )

    with pytest.raises(
        PreconditionError, match="changed after resource admission"
    ) as raised:
        service.handle_import_labels(
            ImportLabelsCommand(
                plan=LabelImportPlan(
                    preview_id=preview["preview_id"],
                    target_indices=[0],
                    label_paths=[str(label_path)],
                    file_mapping={str(raw_path): str(label_path)},
                    mapping={1: "left", 2: "right"},
                    mode="sequence",
                )
            )
        )

    assert (
        raised.value.diagnostics["code"]
        == "interpretation_resource_changed_after_admission"
    )
    assert dataset.label_revisions == [0]
    assert dataset.batch_calls == []
    assert interpretation.recorded == []


def test_preview_rejects_twenty_thousand_distinct_labels_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from XBrainLab.backend.application import label_import_preview

    raw_path = tmp_path / "sub-01_raw.fif"
    label_path = tmp_path / "high-cardinality.npy"
    np.save(label_path, np.arange(20_000, dtype=np.int32))
    service, dataset, interpretation = _service([raw_path])
    scalar_calls = 0
    real_python_scalar = label_import_preview._python_scalar

    def observe_scalar(value: Any) -> Any:
        nonlocal scalar_calls
        scalar_calls += 1
        return real_python_scalar(value)

    monkeypatch.setattr(label_import_preview, "_python_scalar", observe_scalar)

    with pytest.raises(PreconditionError) as raised:
        service.handle_import_labels(
            PreviewLabelImportCommand(label_paths=[str(label_path)])
        )

    assert raised.value.diagnostics == {
        "code": "label_preview_cardinality_exceeded",
        "observed_count": 257,
        "observed_count_is_lower_bound": True,
        "limit": label_import_preview.MAX_LABEL_MAPPING_CARDINALITY,
        "suggestions": [
            "select the label field that contains class or event codes",
            "convert the source to a bounded class or event column",
        ],
    }
    assert scalar_calls == 257
    assert "at least 257 distinct values" in str(raised.value)
    assert "class or event codes" in str(raised.value)
    assert "Select the correct label field" in str(raised.value)
    assert dataset.batch_calls == []
    assert interpretation.recorded == []


def test_preview_rejects_an_overlong_public_label_value(
    tmp_path: Path,
) -> None:
    from XBrainLab.backend.application import label_import_preview

    raw_path = tmp_path / "sub-01_raw.fif"
    label_path = tmp_path / "long-label.csv"
    overlong = "x" * (label_import_preview.MAX_LABEL_PREVIEW_TEXT_LENGTH + 1)
    label_path.write_text(f"label\n{overlong}\n", encoding="utf-8")
    service, dataset, interpretation = _service([raw_path])

    with pytest.raises(PreconditionError) as raised:
        service.handle_import_labels(
            PreviewLabelImportCommand(
                label_paths=[str(label_path)],
                label_configs={
                    str(label_path): {
                        "label_field": "label",
                        "sequence_only": True,
                    }
                },
            )
        )

    assert raised.value.diagnostics == {
        "code": "label_preview_text_too_long",
        "field": "unique_label",
        "observed_length": len(overlong),
        "limit": label_import_preview.MAX_LABEL_PREVIEW_TEXT_LENGTH,
        "path": str(label_path.resolve()),
        "suggestions": [
            "select the label field that contains compact class or event codes",
            "convert verbose values to bounded class or event codes",
        ],
    }
    assert "too long for the external label mapping editor" in str(raised.value)
    assert dataset.batch_calls == []
    assert interpretation.recorded == []


def test_preview_accepts_bounded_mixed_numeric_and_string_labels(
    tmp_path: Path,
) -> None:
    numeric_path = tmp_path / "numeric.txt"
    string_path = tmp_path / "string.csv"
    numeric_path.write_text("2 1 2\n", encoding="utf-8")
    string_path.write_text('label\n"1"\nrest\n', encoding="utf-8")
    service, dataset, interpretation = _service([tmp_path / "sub-01_raw.fif"])

    summary = _payload(
        service.handle_import_labels(
            PreviewLabelImportCommand(
                label_paths=[str(numeric_path), str(string_path)],
                label_configs={
                    str(string_path): {
                        "label_field": "label",
                        "sequence_only": True,
                    }
                },
            )
        )
    )["label_preview"]

    assert summary["unique_labels"] == [1, 2, "1", "rest"]
    assert summary["total_label_count"] == 5
    assert summary["mode"] == "sequence"
    assert summary["mapping_cardinality_limit"] >= len(summary["unique_labels"])
    assert dataset.batch_calls == []
    assert interpretation.recorded == []


def test_preview_identity_is_opaque_and_replacement_cannot_consume_new_cache(
    tmp_path: Path,
) -> None:
    raw_path = tmp_path / "sub-01_raw.fif"
    label_path = tmp_path / "labels.txt"
    label_path.write_text("1 2 1\n", encoding="utf-8")
    service, dataset, interpretation = _service([raw_path])

    first_payload = _payload(
        service.handle_import_labels(
            PreviewLabelImportCommand(label_paths=[str(label_path)])
        )
    )
    second_payload = _payload(
        service.handle_import_labels(
            PreviewLabelImportCommand(label_paths=[str(label_path)])
        )
    )
    first = first_payload["label_preview"]
    second = second_payload["label_preview"]

    assert first["preview_id"].startswith("label-preview-")
    assert second["preview_id"].startswith("label-preview-")
    assert first["preview_id"] != second["preview_id"]
    assert "content_identities" not in second_payload["resource_preflight"]
    scope = second_payload["resource_preflight"]["scope_fingerprint"]
    assert second["preview_id"] != f"label-preview-{scope[:24]}"

    stale_plan = LabelImportPlan(
        preview_id=first["preview_id"],
        target_indices=[0],
        label_paths=[str(label_path)],
        file_mapping={str(raw_path): str(label_path)},
        mapping={1: "left", 2: "right"},
        mode="sequence",
    )
    with pytest.raises(PreconditionError) as raised:
        service.handle_import_labels(ImportLabelsCommand(plan=stale_plan))

    assert raised.value.diagnostics["code"] == "label_preview_unavailable"
    assert dataset.batch_calls == []
    assert interpretation.recorded == []

    current_plan = LabelImportPlan(
        preview_id=second["preview_id"],
        target_indices=[0],
        label_paths=[str(label_path)],
        file_mapping={str(raw_path): str(label_path)},
        mapping={1: "left", 2: "right"},
        mode="sequence",
    )
    result = _payload(
        service.handle_import_labels(ImportLabelsCommand(plan=current_plan))
    )
    assert result["success_count"] == 1
    assert dataset.label_revisions == [1]

    with pytest.raises(PreconditionError) as consumed:
        service.handle_import_labels(ImportLabelsCommand(plan=current_plan))
    assert consumed.value.diagnostics["code"] == "label_preview_unavailable"


def test_preview_identity_rejects_reloaded_raw_at_the_same_path(
    tmp_path: Path,
) -> None:
    raw_path = tmp_path / "sub-01_raw.fif"
    label_path = tmp_path / "labels.txt"
    label_path.write_text("1 2 1\n", encoding="utf-8")
    service, dataset, interpretation = _service([raw_path])
    original_raw = dataset.raws[0]
    preview = _payload(
        service.handle_import_labels(
            PreviewLabelImportCommand(label_paths=[str(label_path)])
        )
    )["label_preview"]
    dataset.raws = [_Raw(str(raw_path))]
    replacement_raw = dataset.raws[0]
    plan = LabelImportPlan(
        preview_id=preview["preview_id"],
        target_indices=[0],
        label_paths=[str(label_path)],
        file_mapping={str(raw_path): str(label_path)},
        mapping={1: "left", 2: "right"},
        mode="sequence",
    )

    with pytest.raises(PreconditionError) as stale:
        service.handle_import_labels(ImportLabelsCommand(plan=plan))

    assert replacement_raw is not original_raw
    assert stale.value.diagnostics == {"code": "label_preview_unavailable"}
    assert original_raw.label_revision == 0
    assert replacement_raw.label_revision == 0
    assert dataset.batch_calls == []
    assert interpretation.recorded == []

    with pytest.raises(PreconditionError) as consumed:
        service.handle_import_labels(ImportLabelsCommand(plan=plan))
    assert consumed.value.diagnostics == {"code": "label_preview_unavailable"}


def test_preview_rejects_more_than_the_public_file_summary_limit(
    tmp_path: Path,
) -> None:
    from XBrainLab.backend.application import label_import_preview

    paths = [str(tmp_path / f"labels-{index}.txt") for index in range(65)]
    service, dataset, interpretation = _service([tmp_path / "sub-01_raw.fif"])

    with pytest.raises(PreconditionError) as raised:
        service.handle_import_labels(PreviewLabelImportCommand(label_paths=paths))

    assert raised.value.diagnostics == {
        "code": "label_preview_file_count_exceeded",
        "observed_count": 65,
        "limit": label_import_preview.MAX_LABEL_PREVIEW_FILES,
        "suggestions": [
            "select label files for a matching EEG subset or smaller batch"
        ],
    }
    assert "matching EEG subset" in str(raised.value)
    assert dataset.batch_calls == []
    assert interpretation.recorded == []


def test_preview_accepts_exactly_the_public_file_summary_limit(
    tmp_path: Path,
) -> None:
    from XBrainLab.backend.application import label_import_preview

    paths: list[str] = []
    for index in range(label_import_preview.MAX_LABEL_PREVIEW_FILES):
        path = tmp_path / f"labels-{index}.txt"
        path.write_text("1\n", encoding="utf-8")
        paths.append(str(path))
    service, dataset, interpretation = _service([tmp_path / "sub-01_raw.fif"])

    summary = _payload(
        service.handle_import_labels(PreviewLabelImportCommand(label_paths=paths))
    )["label_preview"]

    assert len(summary["files"]) == label_import_preview.MAX_LABEL_PREVIEW_FILES
    assert summary["total_label_count"] == label_import_preview.MAX_LABEL_PREVIEW_FILES
    assert summary["unique_labels"] == [1]
    assert dataset.batch_calls == []
    assert interpretation.recorded == []


@pytest.mark.parametrize("entry_point", ["attach", "direct_import"])
def test_public_non_preview_commands_reject_high_cardinality_materialization(
    tmp_path: Path,
    entry_point: str,
) -> None:
    raw_path = tmp_path / "sub-01_raw.fif"
    label_path = tmp_path / "high-cardinality.npy"
    np.save(label_path, np.arange(20_000, dtype=np.int32))
    service, dataset, interpretation = _service([raw_path])

    with pytest.raises(PreconditionError) as raised:
        if entry_point == "attach":
            service.handle_attach_labels(
                AttachLabelsCommand(
                    mapping={raw_path.name: str(label_path)},
                    label_paths=[str(label_path)],
                )
            )
        else:
            service.handle_import_labels(
                ImportLabelsCommand(
                    plan=LabelImportPlan(
                        target_indices=[0],
                        label_paths=[str(label_path)],
                        file_mapping={str(raw_path): str(label_path)},
                        mapping={},
                        mode="sequence",
                    )
                )
            )

    assert raised.value.diagnostics["code"] == "label_mapping_cardinality_exceeded"
    assert raised.value.diagnostics["observed_count"] == 257
    assert raised.value.diagnostics["observed_count_is_lower_bound"] is True
    assert dataset.batch_calls == []
    assert interpretation.recorded == []


@pytest.mark.parametrize("entry_point", ["preview", "attach", "direct_import"])
def test_high_cardinality_first_file_stops_before_second_parser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entry_point: str,
) -> None:
    first_raw = tmp_path / "sub-01_raw.fif"
    second_raw = tmp_path / "sub-02_raw.fif"
    first_labels = tmp_path / "first-high-cardinality.npy"
    second_labels = tmp_path / "second-labels.npy"
    np.save(first_labels, np.arange(20_000, dtype=np.int32))
    np.save(second_labels, np.array([1, 2], dtype=np.int32))
    service, dataset, interpretation = _service([first_raw, second_raw])
    parser_calls: list[str] = []
    real_loader = label_loader.load_label_file

    def observed_loader(path: str, **kwargs: Any) -> Any:
        parser_calls.append(str(path))
        return real_loader(path, **kwargs)

    monkeypatch.setattr(label_loader, "load_label_file", observed_loader)

    with pytest.raises(PreconditionError) as raised:
        if entry_point == "preview":
            service.handle_import_labels(
                PreviewLabelImportCommand(
                    label_paths=[str(first_labels), str(second_labels)],
                )
            )
        elif entry_point == "attach":
            service.handle_attach_labels(
                AttachLabelsCommand(
                    mapping={
                        first_raw.name: str(first_labels),
                        second_raw.name: str(second_labels),
                    },
                    label_paths=[str(first_labels), str(second_labels)],
                )
            )
        else:
            service.handle_import_labels(
                ImportLabelsCommand(
                    plan=LabelImportPlan(
                        target_indices=[0, 1],
                        label_paths=[str(first_labels), str(second_labels)],
                        file_mapping={
                            str(first_raw): str(first_labels),
                            str(second_raw): str(second_labels),
                        },
                        mapping={},
                        mode="sequence",
                    )
                )
            )

    expected_code = (
        "label_preview_cardinality_exceeded"
        if entry_point == "preview"
        else "label_mapping_cardinality_exceeded"
    )
    assert raised.value.diagnostics["code"] == expected_code
    assert raised.value.diagnostics["observed_count"] == 257
    assert parser_calls == [str(first_labels.resolve())]
    assert dataset.label_revisions == [0, 0]
    assert dataset.batch_calls == []
    assert interpretation.recorded == []


def test_direct_import_rejects_an_oversized_public_mapping(
    tmp_path: Path,
) -> None:
    raw_path = tmp_path / "sub-01_raw.fif"
    label_path = tmp_path / "labels.txt"
    label_path.write_text("1 2\n", encoding="utf-8")
    service, dataset, interpretation = _service([raw_path])

    with pytest.raises(PreconditionError) as raised:
        service.handle_import_labels(
            ImportLabelsCommand(
                plan=LabelImportPlan(
                    target_indices=[0],
                    label_paths=[str(label_path)],
                    file_mapping={str(raw_path): str(label_path)},
                    mapping={index: f"class-{index}" for index in range(20_000)},
                    mode="sequence",
                )
            )
        )

    assert raised.value.diagnostics["code"] == "label_mapping_cardinality_exceeded"
    assert raised.value.diagnostics["observed_count"] == 257
    assert raised.value.diagnostics["observed_count_is_lower_bound"] is True
    assert dataset.batch_calls == []
    assert interpretation.recorded == []


def test_preview_mode_mismatch_spends_the_one_time_identity(
    tmp_path: Path,
) -> None:
    raw_path = tmp_path / "sub-01_raw.fif"
    label_path = tmp_path / "labels.txt"
    label_path.write_text("1 2\n", encoding="utf-8")
    service, dataset, interpretation = _service([raw_path])
    preview = _payload(
        service.handle_import_labels(
            PreviewLabelImportCommand(label_paths=[str(label_path)])
        )
    )["label_preview"]

    def plan(mode: str) -> LabelImportPlan:
        return LabelImportPlan(
            preview_id=preview["preview_id"],
            target_indices=[0],
            label_paths=[str(label_path)],
            file_mapping={str(raw_path): str(label_path)},
            mapping={1: "left", 2: "right"},
            mode=mode,
        )

    with pytest.raises(PreconditionError) as mismatch:
        service.handle_import_labels(ImportLabelsCommand(plan=plan("timestamp")))
    assert mismatch.value.diagnostics == {
        "code": "label_preview_scope_mismatch",
        "reviewed_mode": "sequence",
        "requested_mode": "timestamp",
    }

    with pytest.raises(PreconditionError) as consumed:
        service.handle_import_labels(ImportLabelsCommand(plan=plan("sequence")))
    assert consumed.value.diagnostics["code"] == "label_preview_unavailable"
    assert dataset.batch_calls == []
    assert interpretation.recorded == []


@pytest.mark.parametrize("invalid_mode", ["unsupported", "", "SEQUENCE"])
def test_matching_preview_invalid_mode_is_rejected_and_spends_identity(
    tmp_path: Path,
    invalid_mode: str,
) -> None:
    raw_path = tmp_path / "sub-01_raw.fif"
    label_path = tmp_path / "labels.txt"
    label_path.write_text("1 2\n", encoding="utf-8")
    service, dataset, interpretation = _service([raw_path])
    preview = _payload(
        service.handle_import_labels(
            PreviewLabelImportCommand(label_paths=[str(label_path)])
        )
    )["label_preview"]

    def plan(mode: str) -> LabelImportPlan:
        return LabelImportPlan(
            preview_id=preview["preview_id"],
            target_indices=[0],
            label_paths=[str(label_path)],
            file_mapping={str(raw_path): str(label_path)},
            mapping={1: "left", 2: "right"},
            mode=mode,
        )

    with pytest.raises(PreconditionError) as mismatch:
        service.handle_import_labels(ImportLabelsCommand(plan=plan(invalid_mode)))

    assert mismatch.value.diagnostics == {
        "code": "label_preview_scope_mismatch",
        "reviewed_mode": "sequence",
        "requested_mode": invalid_mode,
    }
    with pytest.raises(PreconditionError) as consumed:
        service.handle_import_labels(ImportLabelsCommand(plan=plan("sequence")))
    assert consumed.value.diagnostics["code"] == "label_preview_unavailable"
    assert dataset.label_revisions == [0]
    assert dataset.batch_calls == []
    assert interpretation.recorded == []


@pytest.mark.parametrize("invalid_mode", ["unsupported", "", "SEQUENCE"])
def test_direct_import_without_preview_rejects_invalid_mode_normally(
    tmp_path: Path,
    invalid_mode: str,
) -> None:
    raw_path = tmp_path / "sub-01_raw.fif"
    label_path = tmp_path / "labels.txt"
    label_path.write_text("1 2\n", encoding="utf-8")
    service, dataset, interpretation = _service([raw_path])

    with pytest.raises(ValueError, match="Unknown label import mode"):
        service.handle_import_labels(
            ImportLabelsCommand(
                plan=LabelImportPlan(
                    target_indices=[0],
                    label_paths=[str(label_path)],
                    file_mapping={str(raw_path): str(label_path)},
                    mapping={1: "left", 2: "right"},
                    mode=invalid_mode,
                )
            )
        )

    assert dataset.label_revisions == [0]
    assert dataset.batch_calls == []
    assert interpretation.recorded == []


def test_preview_rejects_an_overlong_path_without_echoing_it(
    tmp_path: Path,
) -> None:
    from XBrainLab.backend.application import label_import_preview

    overlong = "x" * (label_import_preview.MAX_LABEL_PREVIEW_PATH_LENGTH + 1)
    service, dataset, interpretation = _service([tmp_path / "sub-01_raw.fif"])

    with pytest.raises(PreconditionError) as raised:
        service.handle_import_labels(
            PreviewLabelImportCommand(
                label_paths=[overlong],
                label_configs={overlong: {"label_field": "label"}},
            )
        )

    assert raised.value.diagnostics["code"] == "label_preview_text_too_long"
    assert raised.value.diagnostics["field"] == "path"
    assert raised.value.diagnostics["observed_length"] > (
        label_import_preview.MAX_LABEL_PREVIEW_PATH_LENGTH
    )
    assert raised.value.diagnostics["limit"] == (
        label_import_preview.MAX_LABEL_PREVIEW_PATH_LENGTH
    )
    assert raised.value.diagnostics["suggestions"] == [
        "use shorter label paths and parser field names"
    ]
    assert "path" not in raised.value.diagnostics
    assert overlong not in str(raised.value)
    assert dataset.batch_calls == []
    assert interpretation.recorded == []


def test_matching_preview_identity_is_spent_by_scope_mismatch(
    tmp_path: Path,
) -> None:
    raw_path = tmp_path / "sub-01_raw.fif"
    label_path = tmp_path / "labels.txt"
    label_path.write_text("1 2 1\n", encoding="utf-8")
    service, dataset, interpretation = _service([raw_path])
    preview = _payload(
        service.handle_import_labels(
            PreviewLabelImportCommand(label_paths=[str(label_path)])
        )
    )["label_preview"]
    changed = LabelImportPlan(
        preview_id=preview["preview_id"],
        target_indices=[0],
        label_paths=[str(label_path)],
        label_configs={str(label_path): {"sequence_only": True}},
        file_mapping={str(raw_path): str(label_path)},
        mapping={1: "left", 2: "right"},
        mode="sequence",
    )

    with pytest.raises(PreconditionError) as mismatch:
        service.handle_import_labels(ImportLabelsCommand(plan=changed))

    assert mismatch.value.diagnostics["code"] == "label_preview_scope_mismatch"

    correct = LabelImportPlan(
        preview_id=preview["preview_id"],
        target_indices=[0],
        label_paths=[str(label_path)],
        file_mapping={str(raw_path): str(label_path)},
        mapping={1: "left", 2: "right"},
        mode="sequence",
    )
    with pytest.raises(PreconditionError) as consumed:
        service.handle_import_labels(ImportLabelsCommand(plan=correct))

    assert consumed.value.diagnostics["code"] == "label_preview_unavailable"
    assert dataset.batch_calls == []
    assert interpretation.recorded == []
