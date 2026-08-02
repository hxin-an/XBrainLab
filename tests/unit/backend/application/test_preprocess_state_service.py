"""Focused contracts for the Study-owned Preprocess product port."""

from __future__ import annotations

from typing import Any

from XBrainLab.backend.application import (
    ApplicationService,
    PreprocessCommand,
    PreprocessOperation,
)
from XBrainLab.backend.controller.preprocess_controller import PreprocessController
from XBrainLab.backend.services.preprocess_state_service import PreprocessStateService
from XBrainLab.backend.study import Study


class _Row:
    def __init__(self, history: list[str] | None = None) -> None:
        self.history = list(history or [])

    def copy(self) -> _Row:
        return _Row(self.history)


def _processor(label: str, *, fail: bool = False) -> type[Any]:
    class _Processor:
        def __init__(self, rows: list[_Row]) -> None:
            self.rows = rows

        def data_preprocess(self, *_args: Any, **_kwargs: Any) -> list[_Row]:
            for row in self.rows:
                row.history.append(label)
            if fail:
                raise RuntimeError(f"{label} failed")
            return self.rows

    return _Processor


class _Study:
    def __init__(self) -> None:
        self.preprocessed_data_list = [_Row(["loaded"])]
        self.commits: list[list[_Row]] = []

    def set_preprocessed_data_list(
        self,
        rows: list[_Row],
        force_update: bool = False,
    ) -> None:
        assert force_update is True
        self.preprocessed_data_list = rows
        self.commits.append(rows)

    def reset_preprocess(self, force_update: bool = False) -> None:
        assert force_update is True

    def lock_dataset(self) -> None:
        pass

    def set_channels(
        self,
        _channels: list[str],
        _positions: list[tuple[float, float, float]],
    ) -> None:
        pass


def test_preprocess_state_service_preserves_atomic_standard_pipeline() -> None:
    study = _Study()
    original = study.preprocessed_data_list
    notifications: list[str] = []
    processors = {
        "Filtering": _processor("filter"),
        "Resample": _processor("resample", fail=True),
    }
    service = PreprocessStateService(
        study,
        processor_provider=processors.__getitem__,
    )
    service.subscribe("preprocess_changed", lambda: notifications.append("changed"))

    try:
        service.apply_standard_pipeline(
            l_freq=4,
            h_freq=40,
            rate=128,
        )
    except RuntimeError as exc:
        assert str(exc) == "resample failed"
    else:
        raise AssertionError("Expected the failing processor to abort the recipe")

    assert study.preprocessed_data_list is original
    assert original[0].history == ["loaded"]
    assert study.commits == []
    assert notifications == []


def test_preprocess_state_service_commits_and_publishes_once() -> None:
    study = _Study()
    notifications: list[str] = []
    processors = {
        "Filtering": _processor("filter"),
        "Resample": _processor("resample"),
        "Rereference": _processor("rereference"),
        "Normalize": _processor("normalize"),
    }
    service = PreprocessStateService(
        study,
        processor_provider=processors.__getitem__,
    )
    service.subscribe("preprocess_changed", lambda: notifications.append("changed"))

    assert service.apply_standard_pipeline(
        l_freq=4,
        h_freq=40,
        notch_freq=60,
        rate=128,
        ref_channels="average",
        normalization="z score",
    )

    assert len(study.commits) == 1
    assert study.preprocessed_data_list[0].history == [
        "loaded",
        "filter",
        "filter",
        "resample",
        "rereference",
        "normalize",
    ]
    assert notifications == ["changed"]


def test_application_preprocess_composition_never_resolves_controller(
    monkeypatch,
) -> None:
    study = Study()
    original_get_controller = study.get_controller
    resolved_names: list[str] = []

    def reject_preprocess_controller(name: str) -> Any:
        resolved_names.append(name)
        if name == "preprocess":
            raise AssertionError("Application composition resolved a UI controller")
        return original_get_controller(name)

    monkeypatch.setattr(study, "get_controller", reject_preprocess_controller)

    service = ApplicationService(study)
    result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.BANDPASS,
            low_freq=4,
            high_freq=40,
        )
    )

    assert result.failed is True
    assert service.preprocess is study.preprocess_state_service
    assert "preprocess" not in resolved_names


def test_preprocess_controller_relays_shared_service_publication_once() -> None:
    study = Study()
    controller = PreprocessController(study)
    notifications: list[str] = []
    controller.subscribe("preprocess_changed", lambda: notifications.append("changed"))

    study.preprocess_state_service.reset_preprocess()

    assert notifications == ["changed"]
