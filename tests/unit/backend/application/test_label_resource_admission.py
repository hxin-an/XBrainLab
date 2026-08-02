"""Resource-admission contracts for external and legacy label commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest

from XBrainLab.backend.application.commands import (
    AttachLabelsCommand,
    ImportLabelsCommand,
    LabelImportPlan,
)
from XBrainLab.backend.application.data_compatibility_service import (
    DataCompatibilityCommandService,
    HandlerResult,
)
from XBrainLab.backend.application.errors import PreconditionError
from XBrainLab.backend.application.resource_guard import (
    ResourceConfirmationRequiredError,
    ResourcePreflightResult,
    check_import_resource_preflight,
)
from XBrainLab.backend.application.resource_label_estimation import (
    LABEL_CARRIER_FILE_SIZE_MULTIPLIERS,
    SUPPORTED_EXTERNAL_LABEL_EXTENSIONS,
)
from XBrainLab.backend.load_data import label_loader


class _Raw:
    def __init__(self, path: str) -> None:
        self._path = path

    def get_filepath(self) -> str:
        return self._path

    def get_filename(self) -> str:
        return Path(self._path).name


class _Dataset:
    def __init__(self, raws: list[_Raw]) -> None:
        self.raws = raws
        self.batch_calls: list[tuple[Any, ...]] = []

    def get_loaded_data_list(self) -> list[_Raw]:
        return self.raws

    def apply_labels_batch(self, *args: Any) -> int:
        self.batch_calls.append(args)
        return len(args[0])


class _Interpretation:
    def __init__(self) -> None:
        self.recorded: list[dict[str, Any]] = []

    def record_label_import_for_recipe(self, **kwargs: Any) -> dict[str, Any]:
        self.recorded.append(kwargs)
        plan = kwargs["plan"]
        return {
            "label_carriers": sorted(str(path) for path in plan.label_paths),
            "mode": kwargs["mode"],
        }


class _PipelineTransaction:
    def capture(self) -> None:
        return None

    def prepare_raw_replacement(self) -> None:
        return None

    def restore(self, _snapshot: None) -> None:
        return None


def _service(
    raw_path: Path,
) -> tuple[DataCompatibilityCommandService, _Dataset, _Interpretation]:
    dataset = _Dataset([_Raw(str(raw_path))])
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


def _warning_preflight(paths: list[str]) -> ResourcePreflightResult:
    safe = check_import_resource_preflight(paths)
    return ResourcePreflightResult(
        issues=(),
        diagnostics={"files": safe.diagnostics["files"]},
        warnings=("Label materialization may use substantial RAM.",),
    )


def _blocking_preflight(paths: list[str]) -> ResourcePreflightResult:
    safe = check_import_resource_preflight(paths)
    return ResourcePreflightResult(
        issues=("Label materialization exceeds the RAM limit.",),
        diagnostics={"files": safe.diagnostics["files"]},
    )


def _challenge(error: ResourceConfirmationRequiredError) -> str:
    preflight = error.diagnostics["resource_preflight"]
    challenge = preflight["confirmation_challenge"]
    assert challenge["challenge_id"]
    return str(challenge["challenge_id"])


def test_attach_blocking_preflight_runs_before_label_loader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_path = tmp_path / "sub-01_raw.fif"
    label_path = tmp_path / "labels.csv"
    label_path.write_text("label\n1\n2\n", encoding="utf-8")
    service, dataset, _interpretation = _service(raw_path)
    loader_calls: list[str] = []

    monkeypatch.setattr(
        "XBrainLab.backend.application.label_resource_admission.check_import_resource_preflight",
        _blocking_preflight,
    )
    monkeypatch.setattr(
        "XBrainLab.backend.load_data.label_loader.load_label_file",
        lambda path, **_kwargs: loader_calls.append(str(path)),
    )

    with pytest.raises(PreconditionError) as raised:
        service.handle_attach_labels(
            AttachLabelsCommand(
                mapping={raw_path.name: str(label_path)},
                label_paths=[str(label_path)],
            )
        )

    assert raised.value.diagnostics["resource_preflight"]["risk_level"] == "blocking"
    assert loader_calls == []
    assert dataset.batch_calls == []


def test_attach_warning_receipt_is_exact_and_one_shot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_path = tmp_path / "sub-01_raw.fif"
    label_path = tmp_path / "labels.csv"
    label_path.write_text("label\n1\n2\n", encoding="utf-8")
    service, dataset, _interpretation = _service(raw_path)
    loader_calls: list[str] = []

    monkeypatch.setattr(
        "XBrainLab.backend.application.label_resource_admission.check_import_resource_preflight",
        _warning_preflight,
    )

    def _load(path: str, **_kwargs: Any) -> list[int]:
        loader_calls.append(path)
        return [1, 2]

    monkeypatch.setattr(
        "XBrainLab.backend.load_data.label_loader.load_label_file",
        _load,
    )
    initial = AttachLabelsCommand(
        mapping={raw_path.name: str(label_path)},
        label_paths=[str(label_path)],
    )
    with pytest.raises(ResourceConfirmationRequiredError) as raised:
        service.handle_attach_labels(initial)
    token = _challenge(raised.value)
    assert loader_calls == []

    payload = _payload(
        service.handle_attach_labels(
            AttachLabelsCommand(
                mapping=initial.mapping,
                label_paths=initial.label_paths,
                resource_preflight_confirmed=True,
                resource_preflight_token=token,
            )
        )
    )
    assert payload["resource_preflight"]["confirmation_receipt_reused"] is True
    assert loader_calls == [str(label_path)]
    assert len(dataset.batch_calls) == 1

    with pytest.raises(ResourceConfirmationRequiredError) as replayed:
        service.handle_attach_labels(
            AttachLabelsCommand(
                mapping=initial.mapping,
                label_paths=initial.label_paths,
                resource_preflight_confirmed=True,
                resource_preflight_token=token,
            )
        )
    assert _challenge(replayed.value) != token
    assert loader_calls == [str(label_path)]


def test_attach_warning_receipt_rejects_content_and_configuration_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_path = tmp_path / "sub-01_raw.fif"
    label_path = tmp_path / "labels.csv"
    label_path.write_text("label\n1\n2\n", encoding="utf-8")
    service, _dataset, _interpretation = _service(raw_path)
    loader_calls: list[str] = []

    monkeypatch.setattr(
        "XBrainLab.backend.application.label_resource_admission.check_import_resource_preflight",
        _warning_preflight,
    )
    monkeypatch.setattr(
        "XBrainLab.backend.load_data.label_loader.load_label_file",
        lambda path, **_kwargs: loader_calls.append(str(path)),
    )

    with pytest.raises(ResourceConfirmationRequiredError) as raised:
        service.handle_attach_labels(
            AttachLabelsCommand(
                mapping={raw_path.name: str(label_path)},
                label_paths=[str(label_path)],
                label_format="csv",
            )
        )
    token = _challenge(raised.value)
    label_path.write_text("label\n2\n1\n", encoding="utf-8")

    with pytest.raises(ResourceConfirmationRequiredError):
        service.handle_attach_labels(
            AttachLabelsCommand(
                mapping={raw_path.name: str(label_path)},
                label_paths=[str(label_path)],
                label_format="csv",
                resource_preflight_confirmed=True,
                resource_preflight_token=token,
            )
        )
    assert loader_calls == []

    with pytest.raises(ResourceConfirmationRequiredError) as refreshed:
        service.handle_attach_labels(
            AttachLabelsCommand(
                mapping={raw_path.name: str(label_path)},
                label_paths=[str(label_path)],
                label_format="csv",
            )
        )
    refreshed_token = _challenge(refreshed.value)
    with pytest.raises(ResourceConfirmationRequiredError):
        service.handle_attach_labels(
            AttachLabelsCommand(
                mapping={raw_path.name: str(label_path)},
                label_paths=[str(label_path)],
                label_format="tsv",
                resource_preflight_confirmed=True,
                resource_preflight_token=refreshed_token,
            )
        )
    assert loader_calls == []


def test_attach_warning_receipt_rejects_changed_target_event_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_path = tmp_path / "sub-01_raw.fif"
    label_path = tmp_path / "labels.csv"
    label_path.write_text("label\n1\n2\n", encoding="utf-8")
    service, dataset, _interpretation = _service(raw_path)
    loader_calls: list[str] = []

    monkeypatch.setattr(
        "XBrainLab.backend.application.label_resource_admission.check_import_resource_preflight",
        _warning_preflight,
    )
    monkeypatch.setattr(
        "XBrainLab.backend.load_data.label_loader.load_label_file",
        lambda path, **_kwargs: loader_calls.append(str(path)),
    )

    with pytest.raises(ResourceConfirmationRequiredError) as raised:
        service.handle_attach_labels(
            AttachLabelsCommand(
                mapping={raw_path.name: str(label_path)},
                label_paths=[str(label_path)],
                selected_event_names=["cue"],
            )
        )
    token = _challenge(raised.value)

    with pytest.raises(ResourceConfirmationRequiredError) as changed:
        service.handle_attach_labels(
            AttachLabelsCommand(
                mapping={raw_path.name: str(label_path)},
                label_paths=[str(label_path)],
                selected_event_names=["response"],
                resource_preflight_confirmed=True,
                resource_preflight_token=token,
            )
        )

    assert _challenge(changed.value) != token
    assert loader_calls == []
    assert dataset.batch_calls == []


def test_attach_warning_receipt_rejects_same_content_at_a_different_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_path = tmp_path / "sub-01_raw.fif"
    first_path = tmp_path / "labels-a.csv"
    second_path = tmp_path / "labels-b.csv"
    first_path.write_text("label\n1\n2\n", encoding="utf-8")
    second_path.write_bytes(first_path.read_bytes())
    service, dataset, _interpretation = _service(raw_path)
    loader_calls: list[str] = []

    monkeypatch.setattr(
        "XBrainLab.backend.application.label_resource_admission.check_import_resource_preflight",
        _warning_preflight,
    )
    monkeypatch.setattr(
        label_loader,
        "load_label_file",
        lambda path, **_kwargs: loader_calls.append(str(path)),
    )

    with pytest.raises(ResourceConfirmationRequiredError) as raised:
        service.handle_attach_labels(
            AttachLabelsCommand(
                mapping={raw_path.name: str(first_path)},
                label_paths=[str(first_path)],
            )
        )
    token = _challenge(raised.value)

    with pytest.raises(ResourceConfirmationRequiredError) as changed:
        service.handle_attach_labels(
            AttachLabelsCommand(
                mapping={raw_path.name: str(second_path)},
                label_paths=[str(second_path)],
                resource_preflight_confirmed=True,
                resource_preflight_token=token,
            )
        )

    assert _challenge(changed.value) != token
    assert loader_calls == []
    assert dataset.batch_calls == []


def test_public_label_import_plan_cannot_accept_prematerialized_payloads() -> None:
    with pytest.raises(TypeError, match="label_map"):
        LabelImportPlan(label_map={"labels.csv": [1, 2]})  # type: ignore[call-arg]


def test_import_warning_receipt_precedes_parser_and_is_one_shot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_path = tmp_path / "sub-01_raw.fif"
    label_path = tmp_path / "labels.tsv"
    label_path.write_text("label\n1\n2\n", encoding="utf-8")
    service, dataset, _interpretation = _service(raw_path)
    loader_calls: list[str] = []

    monkeypatch.setattr(
        "XBrainLab.backend.application.label_resource_admission.check_import_resource_preflight",
        _warning_preflight,
    )
    real_loader = label_loader.load_label_file

    def observed_loader(path: str, **kwargs: Any) -> Any:
        loader_calls.append(path)
        return real_loader(path, **kwargs)

    monkeypatch.setattr(label_loader, "load_label_file", observed_loader)
    plan = LabelImportPlan(
        target_indices=[0],
        label_paths=[str(label_path)],
        file_mapping={str(raw_path): str(label_path)},
        mapping={1: "left", 2: "right"},
        mode="sequence",
    )

    with pytest.raises(ResourceConfirmationRequiredError) as raised:
        service.handle_import_labels(ImportLabelsCommand(plan=plan))
    token = _challenge(raised.value)
    assert loader_calls == []
    assert dataset.batch_calls == []

    payload = _payload(
        service.handle_import_labels(
            ImportLabelsCommand(
                plan=plan,
                resource_preflight_confirmed=True,
                resource_preflight_token=token,
            )
        )
    )
    assert payload["success_count"] == 1
    assert payload["resource_preflight"]["confirmation_receipt_reused"] is True
    assert loader_calls == [str(label_path)]

    with pytest.raises(ResourceConfirmationRequiredError):
        service.handle_import_labels(
            ImportLabelsCommand(
                plan=plan,
                resource_preflight_confirmed=True,
                resource_preflight_token=token,
            )
        )
    assert loader_calls == [str(label_path)]


def test_path_import_parses_after_admission_and_preserves_recipe_trace(
    tmp_path: Path,
) -> None:
    raw_path = tmp_path / "sub-01_raw.fif"
    label_path = tmp_path / "labels.tsv"
    label_path.write_text("label\n1\n2\n", encoding="utf-8")
    service, dataset, interpretation = _service(raw_path)

    payload = _payload(
        service.handle_import_labels(
            ImportLabelsCommand(
                plan=LabelImportPlan(
                    target_indices=[0],
                    label_paths=[str(label_path)],
                    file_mapping={str(raw_path): str(label_path)},
                    mapping={1: "left", 2: "right"},
                    mode="sequence",
                )
            )
        )
    )

    assert payload["success_count"] == 1
    assert payload["resource_preflight"]["risk_level"] == "safe"
    assert payload["label_import"] == {
        "label_carriers": [str(label_path)],
        "mode": "sequence",
    }
    assert len(dataset.batch_calls) == 1
    assert dataset.batch_calls[0][1][str(label_path)].tolist() == [1, 2]
    assert interpretation.recorded[0]["file_mapping"] == {
        str(raw_path): str(label_path)
    }


@pytest.mark.parametrize("name", ["labels.bin", "labels.npz"])
def test_unknown_label_format_fails_closed_before_loader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> None:
    raw_path = tmp_path / "sub-01_raw.fif"
    label_path = tmp_path / name
    label_path.write_bytes(b"not a supported label payload")
    service, dataset, _interpretation = _service(raw_path)
    loader_calls: list[str] = []
    monkeypatch.setattr(
        "XBrainLab.backend.load_data.label_loader.load_label_file",
        lambda path, **_kwargs: loader_calls.append(str(path)),
    )

    with pytest.raises(PreconditionError, match="format"):
        service.handle_attach_labels(
            AttachLabelsCommand(
                mapping={raw_path.name: str(label_path)},
                label_paths=[str(label_path)],
            )
        )

    assert loader_calls == []
    assert dataset.batch_calls == []


def test_uninspectable_npy_fails_closed_before_numpy_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_path = tmp_path / "sub-01_raw.fif"
    label_path = tmp_path / "labels.npy"
    label_path.write_bytes(b"not-numpy")
    service, dataset, _interpretation = _service(raw_path)
    numpy_load_calls: list[object] = []
    monkeypatch.setattr(
        "XBrainLab.backend.load_data.label_loader.np.load",
        lambda source, **_kwargs: numpy_load_calls.append(source),
    )

    with pytest.raises(PreconditionError, match="inspect"):
        service.handle_attach_labels(
            AttachLabelsCommand(
                mapping={raw_path.name: str(label_path)},
                label_paths=[str(label_path)],
            )
        )

    assert numpy_load_calls == []
    assert dataset.batch_calls == []


def test_npy_materialization_uses_bounded_admitted_stream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_path = tmp_path / "sub-01_raw.fif"
    label_path = tmp_path / "labels.npy"
    np.save(label_path, np.asarray([1, 2, 1], dtype=np.int16))
    service, dataset, _interpretation = _service(raw_path)
    real_numpy_load = np.load
    parser_sources: list[Any] = []

    def _load(source: Any, **kwargs: Any) -> Any:
        parser_sources.append(source)
        assert not isinstance(source, (str, Path))
        assert source.tell() == 0
        return real_numpy_load(source, **kwargs)

    monkeypatch.setattr(
        "XBrainLab.backend.load_data.label_loader.np.load",
        _load,
    )

    payload = _payload(
        service.handle_attach_labels(
            AttachLabelsCommand(
                mapping={raw_path.name: str(label_path)},
                label_paths=[str(label_path)],
            )
        )
    )

    assert payload["success_count"] == 1
    assert len(parser_sources) == 1
    assert dataset.batch_calls[0][1][str(label_path)].tolist() == [1, 2, 1]


def test_label_resource_formats_and_estimator_thresholds_have_one_owner() -> None:
    assert (
        frozenset(LABEL_CARRIER_FILE_SIZE_MULTIPLIERS)
        == SUPPORTED_EXTERNAL_LABEL_EXTENSIONS
    )
    assert {".mat", ".csv", ".tsv", ".txt", ".npy"} <= (
        SUPPORTED_EXTERNAL_LABEL_EXTENSIONS
    )
