"""Focused tests for legacy data/label compatibility command handlers."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import XBrainLab.backend.application.data_load_resource_receipt as receipt_module
from XBrainLab.backend.application import (
    data_compatibility_service as compatibility_module,
)
from XBrainLab.backend.application import (
    data_interpretation_path_identity as path_identity_module,
)
from XBrainLab.backend.application import resource_guard
from XBrainLab.backend.application.commands import (
    AttachLabelsCommand,
    ImportLabelsCommand,
    LabelImportPlan,
    LoadDataCommand,
)
from XBrainLab.backend.application.data_compatibility_service import (
    DataCompatibilityCommandService,
    HandlerResult,
)
from XBrainLab.backend.application.errors import ApplicationError, PreconditionError
from XBrainLab.backend.application.pipeline_transaction import PipelineStateTransaction
from XBrainLab.backend.application.results import ErrorType
from XBrainLab.backend.exceptions import FileCorruptedError
from XBrainLab.backend.training_manager import TrainingManager


class _Raw:
    def __init__(self, filepath: str, filename: str | None = None) -> None:
        self.filepath = filepath
        self.filename = filename or filepath.rsplit("/", 1)[-1]

    def get_filepath(self) -> str:
        return self.filepath

    def get_filename(self) -> str:
        return self.filename


class _DatasetController:
    def __init__(self) -> None:
        self.import_result: tuple[int, list[str]] = (0, [])
        self.import_exception: Exception | None = None
        self.import_calls: list[list[str]] = []
        self.loaded_data: list[Any] = []
        self.batch_calls: list[tuple[Any, ...]] = []
        self.sequence_calls: list[tuple[Any, ...]] = []
        self.batch_result: int | None = None
        self.mutate_imports = False
        self.import_hook: Callable[[], None] | None = None

    def import_files(self, paths: list[str]) -> tuple[int, list[str]]:
        self.import_calls.append(list(paths))
        self.import_paths = paths
        if self.import_exception is not None:
            raise self.import_exception
        if self.mutate_imports:
            self.loaded_data.extend(
                _Raw(path) for path in paths[: self.import_result[0]]
            )
        if self.import_hook is not None:
            self.import_hook()
        return self.import_result

    def get_loaded_data_list(self) -> list[Any]:
        return self.loaded_data

    def apply_labels_batch(self, *args: Any) -> int:
        self.batch_calls.append(args)
        if self.batch_result is not None:
            return self.batch_result
        target_files = args[0] if args else []
        return len(target_files)

    def apply_labels_sequence(self, *args: Any, **kwargs: Any) -> int:
        self.sequence_calls.append((*args, kwargs))
        return 1


class _InterpretationCommands:
    def __init__(self) -> None:
        self.recorded: list[dict[str, Any]] = []

    def record_label_import_for_recipe(self, **kwargs: Any) -> dict[str, Any]:
        self.recorded.append(kwargs)
        return {
            "mode": kwargs["mode"],
            "target_files": [raw.get_filepath() for raw in kwargs["target_files"]],
            "selected_event_names": kwargs["selected_event_names"],
        }


class _TransactionDataManager:
    def __init__(self) -> None:
        self.loaded_data_list: list[Any] = []
        self.backup_loaded_data_list: list[Any] | None = None
        self.preprocessed_data_list: list[Any] = []
        self.epoch_data: Any | None = None
        self.datasets: list[Any] = []
        self.dataset_generator: Any | None = None
        self.dataset_locked = False


class _BoundDatasetController(_DatasetController):
    def __init__(self, data_manager: _TransactionDataManager) -> None:
        self._data_manager = data_manager
        super().__init__()

    @property
    def loaded_data(self) -> list[Any]:
        return self._data_manager.loaded_data_list

    @loaded_data.setter
    def loaded_data(self, value: list[Any]) -> None:
        self._data_manager.loaded_data_list = list(value)


class _PipelineTransaction:
    def __init__(self, dataset: _DatasetController) -> None:
        self.dataset = dataset
        self.captures = 0
        self.prepares = 0
        self.restores = 0
        self.raw_boundaries = 0
        self.commits = 0
        self.boundary = object()

    def capture(self) -> list[Any]:
        self.captures += 1
        return list(self.dataset.loaded_data)

    def prepare_raw_replacement(self) -> None:
        self.prepares += 1
        self.dataset.loaded_data = []

    def restore(self, snapshot: list[Any]) -> None:
        self.restores += 1
        self.dataset.loaded_data = list(snapshot)

    def begin_raw_replacement(self) -> object:
        self.raw_boundaries += 1
        return self.boundary

    def commit_pipeline_invalidation(self, expected: object) -> bool:
        assert expected is self.boundary
        self.commits += 1
        return False


def _expect_payload(result: HandlerResult) -> tuple[str, dict[str, Any]]:
    assert isinstance(result, tuple)
    return cast(tuple[str, dict[str, Any]], result)


def _resource_challenge(
    error: resource_guard.ResourceConfirmationRequiredError,
) -> dict[str, Any]:
    preflight = error.diagnostics["resource_preflight"]
    challenge = preflight.get("confirmation_challenge")
    assert isinstance(challenge, dict)
    assert challenge["command_name"] == "load_data"
    assert challenge["challenge_id"]
    return challenge


def _service() -> tuple[
    DataCompatibilityCommandService,
    _DatasetController,
    _InterpretationCommands,
]:
    dataset = _DatasetController()
    interpretation = _InterpretationCommands()
    pipeline_transaction = _PipelineTransaction(dataset)
    return (
        DataCompatibilityCommandService(
            dataset=dataset,
            interpretation=interpretation,
            pipeline_transaction=pipeline_transaction,
        ),
        dataset,
        interpretation,
    )


def test_label_path_normalization_preserves_spelling_for_windows_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    label_path = (tmp_path / "ExternalLabels" / "A01T.mat").resolve()
    case_variant = str(label_path).swapcase()
    native_path = compatibility_module.os.path
    windows_path = SimpleNamespace(
        normcase=lambda value: str(value).casefold(),
        basename=native_path.basename,
    )
    windows_os = SimpleNamespace(path=windows_path)
    monkeypatch.setattr(compatibility_module, "os", windows_os)
    monkeypatch.setattr(path_identity_module, "os", windows_os, raising=False)

    normalized = DataCompatibilityCommandService._normalized_label_paths(
        [str(label_path), case_variant]
    )

    assert normalized == [str(label_path)]


def test_load_data_replacement_uses_transaction_and_discards_old_data() -> None:
    service, dataset, _interpretation = _service()
    old = _Raw("/data/old.gdf")
    dataset.loaded_data = [old]
    dataset.import_result = (1, [])
    dataset.mutate_imports = True

    message, payload = _expect_payload(
        service.handle_load_data(
            LoadDataCommand(paths=["/data/new.gdf"], allow_append=False),
        )
    )

    transaction = cast(_PipelineTransaction, service._pipeline_transaction)
    assert message == "Loaded 1 file(s)."
    assert payload["allow_append"] is False
    assert [item.get_filepath() for item in dataset.loaded_data] == ["/data/new.gdf"]
    assert transaction.captures == 1
    assert transaction.raw_boundaries == 1
    assert transaction.prepares == 1
    assert transaction.commits == 1
    assert transaction.restores == 0


def test_load_data_partial_batch_rolls_back_and_fails() -> None:
    service, dataset, _interpretation = _service()
    old = _Raw("/data/old.gdf")
    dataset.loaded_data = [old]
    dataset.import_result = (1, ["/data/bad.gdf: File corrupted."])
    dataset.mutate_imports = True

    with pytest.raises(ApplicationError) as raised:
        service.handle_load_data(
            LoadDataCommand(
                paths=["/data/new.gdf", "/data/bad.gdf"],
                allow_append=True,
            )
        )

    transaction = cast(_PipelineTransaction, service._pipeline_transaction)
    assert [item.get_filepath() for item in dataset.loaded_data] == ["/data/old.gdf"]
    assert transaction.captures == 1
    assert transaction.raw_boundaries == 1
    assert transaction.prepares == 0
    assert transaction.commits == 0
    assert transaction.restores == 1
    assert raised.value.diagnostics["success_count"] == 0
    assert raised.value.diagnostics["attempted_success_count"] == 1
    assert raised.value.diagnostics["expected_count"] == 2


def test_load_data_stale_commit_restores_data_without_overwriting_new_trainer(
    tmp_path: Path,
) -> None:
    path = tmp_path / "new.gdf"
    path.write_bytes(b"test")
    data_manager = _TransactionDataManager()
    old = _Raw("/data/old.gdf")
    training_manager = TrainingManager()
    study = SimpleNamespace(
        data_manager=data_manager,
        training_manager=training_manager,
    )
    dataset = _BoundDatasetController(data_manager)
    data_manager.loaded_data_list = [old]
    dataset.import_result = (1, [])
    dataset.mutate_imports = True
    replacement_trainer = object()
    dataset.import_hook = lambda: setattr(
        training_manager,
        "trainer",
        replacement_trainer,
    )
    service = DataCompatibilityCommandService(
        dataset=dataset,
        interpretation=_InterpretationCommands(),
        pipeline_transaction=PipelineStateTransaction(study),
    )

    with pytest.raises(PreconditionError, match="changed"):
        service.handle_load_data(
            LoadDataCommand(paths=[str(path)], allow_append=False),
        )

    assert data_manager.loaded_data_list == [old]
    assert training_manager.trainer is replacement_trainer


def test_data_compatibility_service_maps_load_failures_to_typed_error() -> None:
    service, dataset, _interpretation = _service()
    dataset.import_result = (0, ["Unsupported format: sample.xyz"])

    try:
        service.handle_load_data(LoadDataCommand(paths=["sample.xyz"]))
    except ApplicationError as error:
        assert error.error_type == ErrorType.UNSUPPORTED_FORMAT
        assert error.diagnostics["success_count"] == 0
        assert error.diagnostics["attempted_success_count"] == 0
        assert error.diagnostics["expected_count"] == 1
        assert error.diagnostics["errors"] == ["Unsupported format: sample.xyz"]
        assert error.diagnostics["rolled_back"] is True
    else:
        raise AssertionError("Expected unsupported-format ApplicationError")


def test_data_compatibility_service_blocks_load_when_files_exceed_available_ram(
    tmp_path,
    monkeypatch: Any,
) -> None:
    service, dataset, _interpretation = _service()
    path = tmp_path / "huge.gdf"
    path.write_bytes(b"0" * 100)
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 100)

    with pytest.raises(PreconditionError, match="available RAM"):
        service.handle_load_data(
            LoadDataCommand(
                paths=[str(path)],
                resource_preflight_confirmed=True,
            ),
        )

    assert not hasattr(dataset, "import_paths")


def test_data_compatibility_service_requires_resource_confirmation_before_warning_load(
    tmp_path,
    monkeypatch: Any,
) -> None:
    service, dataset, _interpretation = _service()
    path = tmp_path / "warning.unknown"
    path.write_bytes(b"0" * 100)
    dataset.import_result = (1, [])
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 2_000_000)

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as raised:
        service.handle_load_data(LoadDataCommand(paths=[str(path)]))

    assert raised.value.diagnostics["resource_preflight"]["risk_level"] == "warning"
    challenge = _resource_challenge(raised.value)
    assert not hasattr(dataset, "import_paths")

    message, payload = _expect_payload(
        service.handle_load_data(
            LoadDataCommand(
                paths=[str(path)],
                resource_preflight_confirmed=True,
                resource_preflight_token=challenge["challenge_id"],
            ),
        ),
    )

    assert message == "Loaded 1 file(s)."
    assert dataset.import_paths == [str(path)]
    assert payload["resource_preflight"]["risk_level"] == "warning"
    assert payload["resource_preflight"]["confirmation_receipt_reused"] is True


def test_data_compatibility_service_requires_confirmation_when_ram_is_unknown(
    tmp_path,
    monkeypatch: Any,
) -> None:
    service, dataset, _interpretation = _service()
    path = tmp_path / "unknown.unknown"
    path.write_bytes(b"0" * 100)
    dataset.import_result = (1, [])
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": None,
                "total_bytes": None,
                "used_bytes": None,
            }
        ),
    )

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as raised:
        service.handle_load_data(LoadDataCommand(paths=[str(path)]))

    assert raised.value.diagnostics["resource_preflight"]["risk_level"] == "unknown"
    challenge = _resource_challenge(raised.value)
    assert not hasattr(dataset, "import_paths")

    _message, payload = _expect_payload(
        service.handle_load_data(
            LoadDataCommand(
                paths=[str(path)],
                resource_preflight_confirmed=True,
                resource_preflight_token=challenge["challenge_id"],
            ),
        ),
    )

    assert dataset.import_paths == [str(path)]
    assert payload["resource_preflight"]["risk_level"] == "unknown"


def test_load_warning_rejects_naked_boolean_and_consumes_exact_receipt_once(
    tmp_path,
    monkeypatch: Any,
) -> None:
    service, dataset, _interpretation = _service()
    path = tmp_path / "warning.unknown"
    path.write_bytes(b"0" * 100)
    dataset.import_result = (1, [])
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 2_000_000)

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as initial:
        service.handle_load_data(LoadDataCommand(paths=[str(path)]))
    initial_challenge = _resource_challenge(initial.value)

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as naked:
        service.handle_load_data(
            LoadDataCommand(
                paths=[str(path)],
                resource_preflight_confirmed=True,
            )
        )
    naked_challenge = _resource_challenge(naked.value)
    assert naked_challenge["challenge_id"] != initial_challenge["challenge_id"]
    assert dataset.import_calls == []

    service.handle_load_data(
        LoadDataCommand(
            paths=[str(path)],
            resource_preflight_confirmed=True,
            resource_preflight_token=naked_challenge["challenge_id"],
        )
    )
    assert dataset.import_calls == [[str(path)]]

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as replayed:
        service.handle_load_data(
            LoadDataCommand(
                paths=[str(path)],
                resource_preflight_confirmed=True,
                resource_preflight_token=naked_challenge["challenge_id"],
            )
        )
    assert (
        _resource_challenge(replayed.value)["challenge_id"]
        != naked_challenge["challenge_id"]
    )
    assert dataset.import_calls == [[str(path)]]


def test_load_warning_receipt_is_bound_to_allow_append_and_ordered_paths(
    tmp_path,
    monkeypatch: Any,
) -> None:
    service, dataset, _interpretation = _service()
    first = tmp_path / "first.unknown"
    second = tmp_path / "second.unknown"
    first.write_bytes(b"0" * 100)
    second.write_bytes(b"1" * 100)
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 4_000_000)

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as initial:
        service.handle_load_data(LoadDataCommand(paths=[str(first), str(second)]))
    token = _resource_challenge(initial.value)["challenge_id"]

    with pytest.raises(
        resource_guard.ResourceConfirmationRequiredError
    ) as changed_mode:
        service.handle_load_data(
            LoadDataCommand(
                paths=[str(first), str(second)],
                allow_append=False,
                resource_preflight_confirmed=True,
                resource_preflight_token=token,
            )
        )
    changed_mode_token = _resource_challenge(changed_mode.value)["challenge_id"]
    assert changed_mode_token != token

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as reordered:
        service.handle_load_data(
            LoadDataCommand(
                paths=[str(second), str(first)],
                allow_append=False,
                resource_preflight_confirmed=True,
                resource_preflight_token=changed_mode_token,
            )
        )
    assert _resource_challenge(reordered.value)["challenge_id"] != changed_mode_token
    assert dataset.import_calls == []


def test_load_warning_receipt_is_invalidated_when_file_changes(
    tmp_path,
    monkeypatch: Any,
) -> None:
    service, dataset, _interpretation = _service()
    path = tmp_path / "warning.unknown"
    path.write_bytes(b"0" * 100)
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 2_000_000)

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as initial:
        service.handle_load_data(LoadDataCommand(paths=[str(path)]))
    token = _resource_challenge(initial.value)["challenge_id"]

    old_stat = path.stat()
    path.write_bytes(b"1" * 100)
    os.utime(
        path,
        ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns + 1_000_000),
    )

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as changed:
        service.handle_load_data(
            LoadDataCommand(
                paths=[str(path)],
                resource_preflight_confirmed=True,
                resource_preflight_token=token,
            )
        )
    assert _resource_challenge(changed.value)["challenge_id"] != token
    assert dataset.import_calls == []


def test_load_warning_preflight_fingerprint_ignores_live_ram_fluctuation(
    tmp_path,
    monkeypatch: Any,
) -> None:
    service, dataset, _interpretation = _service()
    path = tmp_path / "warning.unknown"
    path.write_bytes(b"0" * 100)
    available = 2_000_000
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: available)
    dataset.import_result = (1, [])

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as initial:
        service.handle_load_data(LoadDataCommand(paths=[str(path)]))
    challenge = _resource_challenge(initial.value)

    available = 1_900_000
    _message, payload = _expect_payload(
        service.handle_load_data(
            LoadDataCommand(
                paths=[str(path)],
                resource_preflight_confirmed=True,
                resource_preflight_token=challenge["challenge_id"],
            )
        )
    )

    assert payload["resource_preflight"]["risk_level"] == "warning"
    assert payload["resource_preflight"]["confirmation_receipt_reused"] is True
    assert dataset.import_calls == [[str(path)]]


def test_load_warning_receipt_expires_before_import_side_effect(
    tmp_path,
    monkeypatch: Any,
) -> None:
    now = 100.0
    monkeypatch.setattr(receipt_module.time, "monotonic", lambda: now)
    service, dataset, _interpretation = _service()
    path = tmp_path / "warning.unknown"
    path.write_bytes(b"0" * 100)
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 2_000_000)

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as initial:
        service.handle_load_data(LoadDataCommand(paths=[str(path)]))
    token = _resource_challenge(initial.value)["challenge_id"]
    now += receipt_module.DATA_LOAD_PREFLIGHT_RECEIPT_TTL_SECONDS

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as expired:
        service.handle_load_data(
            LoadDataCommand(
                paths=[str(path)],
                resource_preflight_confirmed=True,
                resource_preflight_token=token,
            )
        )
    assert _resource_challenge(expired.value)["challenge_id"] != token
    assert dataset.import_calls == []


def test_load_safe_path_discards_presented_warning_receipt(
    tmp_path,
    monkeypatch: Any,
) -> None:
    service, dataset, _interpretation = _service()
    path = tmp_path / "warning.unknown"
    path.write_bytes(b"0" * 100)
    available = 2_000_000
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: available)
    dataset.import_result = (1, [])

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as initial:
        service.handle_load_data(LoadDataCommand(paths=[str(path)]))
    token = _resource_challenge(initial.value)["challenge_id"]

    available = 1_000_000_000
    _message, safe_payload = _expect_payload(
        service.handle_load_data(
            LoadDataCommand(
                paths=[str(path)],
                resource_preflight_confirmed=True,
                resource_preflight_token=token,
            )
        )
    )
    assert safe_payload["resource_preflight"]["risk_level"] == "safe"
    assert dataset.import_calls == [[str(path)]]

    available = 2_000_000
    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as stale:
        service.handle_load_data(
            LoadDataCommand(
                paths=[str(path)],
                resource_preflight_confirmed=True,
                resource_preflight_token=token,
            )
        )
    assert _resource_challenge(stale.value)["challenge_id"] != token
    assert dataset.import_calls == [[str(path)]]


def test_load_blocking_preflight_cannot_reuse_warning_receipt(
    tmp_path,
    monkeypatch: Any,
) -> None:
    service, dataset, _interpretation = _service()
    path = tmp_path / "warning.unknown"
    path.write_bytes(b"0" * 100)
    available = 2_000_000
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: available)

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as initial:
        service.handle_load_data(LoadDataCommand(paths=[str(path)]))
    token = _resource_challenge(initial.value)["challenge_id"]

    available = 100
    with pytest.raises(PreconditionError, match="available RAM"):
        service.handle_load_data(
            LoadDataCommand(
                paths=[str(path)],
                resource_preflight_confirmed=True,
                resource_preflight_token=token,
            )
        )
    assert dataset.import_calls == []


def test_load_warning_receipt_is_consumed_before_import_failure(
    tmp_path,
    monkeypatch: Any,
) -> None:
    service, dataset, _interpretation = _service()
    path = tmp_path / "warning.unknown"
    path.write_bytes(b"0" * 100)
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 2_000_000)

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as initial:
        service.handle_load_data(LoadDataCommand(paths=[str(path)]))
    token = _resource_challenge(initial.value)["challenge_id"]
    dataset.import_exception = RuntimeError("loader failed")

    with pytest.raises(RuntimeError, match="loader failed"):
        service.handle_load_data(
            LoadDataCommand(
                paths=[str(path)],
                resource_preflight_confirmed=True,
                resource_preflight_token=token,
            )
        )
    dataset.import_exception = None

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as replayed:
        service.handle_load_data(
            LoadDataCommand(
                paths=[str(path)],
                resource_preflight_confirmed=True,
                resource_preflight_token=token,
            )
        )
    assert _resource_challenge(replayed.value)["challenge_id"] != token
    assert dataset.import_calls == [[str(path)]]


def test_data_compatibility_service_attaches_labels_with_default_event_names(
    tmp_path: Path,
) -> None:
    service, dataset, _interpretation = _service()
    raw = _Raw("/data/sub-01_raw.fif", "sub-01_raw.fif")
    dataset.loaded_data = [raw]
    label_path = tmp_path / "labels.txt"
    label_path.write_text("1 2 1\n", encoding="utf-8")

    message, payload = _expect_payload(
        service.handle_attach_labels(
            AttachLabelsCommand(
                mapping={"sub-01_raw.fif": str(label_path)},
                label_paths=[str(label_path)],
            ),
        ),
    )

    assert message == "Attached labels to 1 file(s)."
    assert payload["success_count"] == 1
    assert payload["errors"] == []
    assert payload["resource_preflight"]["risk_level"] == "safe"
    assert len(dataset.batch_calls) == 1
    targets, label_map, file_mapping, event_names, selected_events = (
        dataset.batch_calls[0]
    )
    canonical_label_path = str(label_path.resolve())
    assert targets == [raw]
    assert label_map[canonical_label_path] == pytest.approx([1, 2, 1])
    assert file_mapping == {"/data/sub-01_raw.fif": canonical_label_path}
    assert event_names == {1: "1", 2: "2"}
    assert selected_events is None


def test_data_compatibility_service_attach_labels_rejects_missing_target() -> None:
    service, dataset, _interpretation = _service()
    raw = _Raw("/data/sub-01_raw.fif", "sub-01_raw.fif")
    dataset.loaded_data = [raw]

    with pytest.raises(PreconditionError, match="requested target") as raised:
        service.handle_attach_labels(
            AttachLabelsCommand(
                mapping={"other-file.fif": "labels.txt"},
                label_paths=["labels.txt"],
            ),
        )

    assert raised.value.diagnostics == {
        "code": "label_target_missing",
        "missing_targets": ["other-file.fif"],
    }
    assert dataset.batch_calls == []


def test_data_compatibility_service_attach_labels_rejects_corrupt_resource(
    tmp_path: Path,
) -> None:
    service, dataset, _interpretation = _service()
    raw = _Raw("/data/sub-01_raw.fif", "sub-01_raw.fif")
    dataset.loaded_data = [raw]

    label_path = tmp_path / "labels.mat"
    label_path.write_bytes(b"not a MATLAB payload")

    with pytest.raises(FileCorruptedError) as caught:
        service.handle_attach_labels(
            AttachLabelsCommand(
                mapping={"sub-01_raw.fif": str(label_path)},
                label_paths=[str(label_path)],
            ),
        )

    public_message = str(caught.value)
    assert "Invalid .mat file" in public_message
    assert "[REDACTED_PATH]" in public_message
    assert "labels.mat" not in public_message
    assert str(label_path) not in public_message

    assert dataset.batch_calls == []


def test_data_compatibility_service_attach_labels_accepts_full_data_path_without_facade(
    tmp_path: Path,
) -> None:
    service, dataset, _interpretation = _service()
    raw = _Raw("/data/sub-01_raw.fif", "sub-01_raw.fif")
    dataset.loaded_data = [raw]
    label_path = tmp_path / "labels.csv"
    label_path.write_text("label\nleft\nright\n", encoding="utf-8")

    message, payload = _expect_payload(
        service.handle_attach_labels(
            AttachLabelsCommand(
                mapping={"/data/sub-01_raw.fif": str(label_path)},
                label_paths=[str(label_path)],
            ),
        ),
    )

    assert message == "Attached labels to 1 file(s)."
    assert payload["success_count"] == 1
    assert payload["errors"] == []
    assert len(dataset.batch_calls) == 1
    targets, label_map, file_mapping, event_names, selected_events = (
        dataset.batch_calls[0]
    )
    assert targets == [raw]
    canonical_label_path = str(label_path.resolve())
    assert label_map[canonical_label_path].tolist() == ["left", "right"]
    assert file_mapping == {"/data/sub-01_raw.fif": canonical_label_path}
    assert event_names == {"left": "left", "right": "right"}
    assert selected_events is None


def test_data_compatibility_service_attach_labels_batches_multiple_files_without_facade(
    tmp_path: Path,
) -> None:
    service, dataset, _interpretation = _service()
    raw_1 = _Raw("/data/sub-01_raw.fif", "sub-01_raw.fif")
    raw_2 = _Raw("/data/sub-02_raw.fif", "sub-02_raw.fif")
    dataset.loaded_data = [raw_1, raw_2]

    label_1 = tmp_path / "labels-01.txt"
    label_2 = tmp_path / "labels-02.txt"
    label_1.write_text("1 2\n", encoding="utf-8")
    label_2.write_text("2 1\n", encoding="utf-8")

    message, payload = _expect_payload(
        service.handle_attach_labels(
            AttachLabelsCommand(
                mapping={
                    "sub-01_raw.fif": str(label_1),
                    "sub-02_raw.fif": str(label_2),
                },
                label_paths=[str(label_1), str(label_2)],
                selected_event_names=["cue"],
            ),
        ),
    )

    assert message == "Attached labels to 2 file(s)."
    assert payload["success_count"] == 2
    assert payload["errors"] == []
    assert len(dataset.batch_calls) == 1
    targets, label_map, file_mapping, event_names, selected_events = (
        dataset.batch_calls[0]
    )
    assert targets == [raw_1, raw_2]
    canonical_label_1 = str(label_1.resolve())
    canonical_label_2 = str(label_2.resolve())
    assert label_map[canonical_label_1].tolist() == [1, 2]
    assert label_map[canonical_label_2].tolist() == [2, 1]
    assert file_mapping == {
        "/data/sub-01_raw.fif": canonical_label_1,
        "/data/sub-02_raw.fif": canonical_label_2,
    }
    assert event_names == {1: "1", 2: "2"}
    assert selected_events == ["cue"]


def test_data_compatibility_service_normalizes_target_events_at_backend_boundary(
    tmp_path: Path,
) -> None:
    service, dataset, _interpretation = _service()
    raw = _Raw("/data/sub-01_raw.fif", "sub-01_raw.fif")
    dataset.loaded_data = [raw]
    label_path = tmp_path / "labels.txt"
    label_path.write_text("1 2\n", encoding="utf-8")

    _expect_payload(
        service.handle_attach_labels(
            AttachLabelsCommand(
                mapping={"sub-01_raw.fif": str(label_path)},
                label_paths=[str(label_path)],
                selected_event_names=[" response ", "cue", "cue", "", "  "],
            ),
        ),
    )

    assert dataset.batch_calls[0][-1] == ["cue", "response"]


def test_data_compatibility_service_imports_labels_and_updates_recipe(
    tmp_path: Path,
) -> None:
    service, dataset, interpretation = _service()
    raw = _Raw("/data/sub-01_raw.fif")
    dataset.loaded_data = [raw]
    label_path = tmp_path / "labels.tsv"
    label_path.write_text("label\n1\n2\n", encoding="utf-8")

    message, payload = _expect_payload(
        service.handle_import_labels(
            ImportLabelsCommand(
                plan=LabelImportPlan(
                    target_indices=[0],
                    label_paths=[str(label_path)],
                    file_mapping={"/data/sub-01_raw.fif": str(label_path)},
                    mapping={1: "left", 2: "right"},
                    selected_event_names=["cue"],
                ),
            ),
        ),
    )

    assert message == "Imported labels for 1 file(s)."
    assert payload["success_count"] == 1
    assert payload["mode"] == "batch"
    assert payload["recipe_updated"] is True
    assert payload["label_import"] == {
        "mode": "batch",
        "target_files": ["/data/sub-01_raw.fif"],
        "selected_event_names": ["cue"],
    }
    assert interpretation.recorded[0]["file_mapping"] == {
        "/data/sub-01_raw.fif": str(label_path.resolve()),
    }
