"""Focused tests for application state snapshot and query services."""

from __future__ import annotations

from typing import Any, ClassVar, cast

from XBrainLab.backend.application.capabilities import CapabilityPolicy
from XBrainLab.backend.application.commands import QueryStateCommand
from XBrainLab.backend.application.dataset_generation_service import (
    DatasetGenerationCommandService,
)
from XBrainLab.backend.application.state import (
    ApplicationStateSnapshot,
    InterpretationStateSnapshot,
)
from XBrainLab.backend.application.state_service import (
    HandlerResult,
    QueryStateCommandService,
    StateSnapshotService,
)
from XBrainLab.backend.application.training_service import TrainingCommandService


class _Raw:
    def __init__(self, filename: str = "subject01.fif") -> None:
        self.filename = filename

    def get_filename(self) -> str:
        return self.filename

    def get_subject_name(self) -> str:
        return "S01"

    def get_session_name(self) -> str:
        return "session-01"

    def get_mne(self) -> Any:
        return type("MNE", (), {"ch_names": ["C3", "C4"]})()

    def get_preprocess_history(self) -> list[str]:
        return ["filter", "normalize"]


class _Epoch:
    event_id: ClassVar[dict[str, int]] = {"left": 1}
    data: ClassVar[list[list[list[float]]]] = [[[0.0, 0.1], [0.2, 0.3]]]
    channel_position: ClassVar[dict[str, tuple[float, float, float]]] = {
        "C3": (0.0, 0.0, 0.0),
    }

    def __len__(self) -> int:
        return 1

    def get_channel_names(self) -> list[str]:
        return ["C3", "C4"]


class _Study:
    def __init__(self) -> None:
        raw = _Raw()
        self.loaded_data_list = [raw]
        self.preprocessed_data_list = [raw]
        self.epoch_data = _Epoch()
        self.datasets: list[Any] = [type("Dataset", (), {"name": "D1"})()]
        self.trainer = None
        self.model_holder = None
        self.training_option = None
        self.dataset_generator = object()
        self.saliency_params = object()
        self.pipeline_stage = "loaded"


class _DatasetController:
    def __init__(self, study: _Study) -> None:
        self.study = study

    def get_runtime_diagnostics(self) -> dict[str, Any]:
        return {
            "source": "runtime",
            "runtime_signals": ["signal one"],
            "gdf_duplicate_channel_files": ["sub01.gdf"],
            "gdf_duplicate_channel_details": [
                {
                    "file": "sub01.gdf",
                    "generated_bases": ["EEG"],
                    "generated_channels": ["EEG-0", "EEG-1"],
                    "message": "detail message",
                },
            ],
        }

    def get_event_info(self) -> dict[str, Any]:
        return {"total": 2, "unique_labels": ["left"]}

    def is_locked(self) -> bool:
        return True

    def get_loaded_data_list(self) -> list[Any]:
        return self.study.loaded_data_list

    def get_smart_filter_suggestions(
        self, _target: Any, target_count: int
    ) -> list[int]:
        return list(range(target_count))


class _BrokenLoadedDataController(_DatasetController):
    def get_loaded_data_list(self) -> list[Any]:
        raise RuntimeError("loaded data list unavailable")


class _PreprocessController:
    def get_runtime_diagnostics(self) -> dict[str, Any]:
        return {
            "preprocess": "ok",
            "runtime_signals": ["preprocess signal"],
            "gdf_duplicate_channel_files": ["preprocessed-sub01.gdf"],
        }

    def is_epoched(self) -> bool:
        return True

    def get_channel_names(self) -> list[str]:
        return ["C3", "C4"]


class _TrainingController:
    def is_training(self) -> bool:
        return False

    def get_missing_requirements(self) -> list[str]:
        return ["model"]

    def get_formatted_history(self) -> list[dict[str, Any]]:
        plan = object()
        record = type("Record", (), {"epoch": 2})()
        return [
            {
                "plan": plan,
                "record": record,
                "group_name": "Group 1",
                "run_name": "1",
                "model_name": "EEGNet",
                "is_active": True,
                "is_current_run": True,
            }
        ]


class _EvaluationController:
    def get_plans(self) -> list[Any]:
        return []


def _snapshot_service() -> StateSnapshotService:
    study = _Study()
    dataset = _DatasetController(study)
    return StateSnapshotService(
        study=study,
        dataset=dataset,
        preprocess=_PreprocessController(),
        training=_TrainingController(),
        evaluation=_EvaluationController(),
        visualization=object(),
        dataset_generation=DatasetGenerationCommandService(
            study=study,
            training=object(),
        ),
        training_commands=TrainingCommandService(
            training=object(),
            get_state=lambda: cast(ApplicationStateSnapshot, None),
        ),
        interpretation=type(
            "Interpretation",
            (),
            {
                "snapshot": lambda self: InterpretationStateSnapshot(
                    has_scan_result=True
                )
            },
        )(),
    )


def _expect_payload(result: HandlerResult) -> tuple[str, dict[str, Any]]:
    assert isinstance(result, tuple)
    return cast(tuple[str, dict[str, Any]], result)


def test_state_snapshot_service_builds_workflow_snapshot() -> None:
    state = _snapshot_service().build()

    assert state.pipeline_stage == "dataset_ready"
    assert state.raw.loaded is True
    assert state.raw.files == ["subject01.fif"]
    assert state.raw.metadata[0]["subject"] == "S01"
    assert state.preprocessed.operations == ["filter", "normalize"]
    assert state.raw.diagnostics["runtime_signals"] == ["signal one"]
    assert state.preprocessed.diagnostics["runtime_signals"] == ["preprocess signal"]
    assert state.epoch.available is True
    assert state.epoch.event_ids == {"left": 1}
    assert state.dataset.count == 1
    assert state.visualization.saliency_configured is True
    assert state.interpretation.has_scan_result is True
    assert state.active_dataset.has_epoch_data is True


def test_data_summary_query_falls_back_to_state_when_loaded_list_query_fails() -> None:
    state_builder = _snapshot_service()
    state = state_builder.build()
    state_builder.dataset = _BrokenLoadedDataController(state_builder.study)

    summary = state_builder.data_summary_from_state(state)

    assert summary["count"] == state.raw.count
    assert summary["files"] == state.raw.files
    assert summary["formats"] == state.raw.formats
    assert summary["metadata"] == state.raw.metadata
    assert summary["unique_labels"] == ["left"]


def test_query_state_service_returns_summary_and_capabilities() -> None:
    state_builder = _snapshot_service()
    query = QueryStateCommandService(
        study=state_builder.study,
        dataset=state_builder.dataset,
        state_builder=state_builder,
        get_state=state_builder.build,
        get_capabilities=lambda: CapabilityPolicy({}),
    )

    message, payload = _expect_payload(
        query.handle_query_state(QueryStateCommand(query="state")),
    )
    assert message == "Application state snapshot ready."
    assert payload["state"]["raw"]["files"] == ["subject01.fif"]
    assert "capabilities" in payload

    summary_message, summary = _expect_payload(
        query.handle_query_state(QueryStateCommand(query="data_summary")),
    )
    assert summary_message == "Dataset summary ready."
    assert summary["count"] == 1
    assert summary["unique_labels"] == ["left"]
    assert summary["runtime_signals"] == ["signal one"]
    assert summary["gdf_duplicate_channel_files"] == ["sub01.gdf"]
    assert summary["gdf_duplicate_channel_details"][0]["message"] == "detail message"

    suggestions_message, suggestions = _expect_payload(
        query.handle_query_state(
            QueryStateCommand(
                query="smart_filter_suggestions",
                params={"target_index": 0, "target_count": 2},
            ),
        ),
    )
    assert suggestions_message == "Smart filter suggestions ready."
    assert suggestions == {"suggestions": [0, 1]}

    history_message, history = _expect_payload(
        query.handle_query_state(QueryStateCommand(query="training_history")),
    )
    assert history_message == "Training history query ready."
    assert history["row_count"] == 1
    assert history["rows"][0] == {
        "group_name": "Group 1",
        "run_name": "1",
        "model_name": "EEGNet",
        "is_active": True,
        "is_current_run": True,
    }

    _history_objects_message, history_objects = _expect_payload(
        query.handle_query_state(
            QueryStateCommand(query="training_history", include_objects=True),
        ),
    )
    assert "plan" in history_objects["rows"][0]
    assert "record" in history_objects["rows"][0]

    split_message, split_context = _expect_payload(
        query.handle_query_state(QueryStateCommand(query="dataset_generation_context")),
    )
    assert split_message == "Dataset generation context ready."
    assert split_context == {
        "payload_type": "dataset_generation_context",
        "epoch_available": True,
        "generator_exists": True,
    }

    _split_objects_message, split_context_objects = _expect_payload(
        query.handle_query_state(
            QueryStateCommand(
                query="dataset_generation_context",
                include_objects=True,
            ),
        ),
    )
    assert split_context_objects["epoch_data"] is state_builder.study.epoch_data
    assert (
        split_context_objects["dataset_generator"]
        is state_builder.study.dataset_generator
    )
