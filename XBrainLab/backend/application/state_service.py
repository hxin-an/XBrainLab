"""State snapshot and read-only query services for the command spine."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from typing import Any, cast

from XBrainLab.backend.utils.logger import logger

from .commands import Command, QueryStateCommand
from .errors import PreconditionError
from .state import (
    ActiveDatasetSnapshot,
    ActiveTrainingSnapshot,
    ApplicationStateSnapshot,
    DatasetStateSnapshot,
    EpochStateSnapshot,
    ErrorSnapshot,
    EvaluationStateSnapshot,
    InterpretationStateSnapshot,
    PreprocessedStateSnapshot,
    RawStateSnapshot,
    TrainingStateSnapshot,
    VisualizationStateSnapshot,
)

HandlerResult = str | tuple[str, dict[str, Any]]


class StateSnapshotService:
    """Build serializable backend state snapshots from the active study."""

    def __init__(
        self,
        *,
        study: Any,
        dataset: Any,
        preprocess: Any,
        training: Any,
        evaluation: Any,
        visualization: Any,
        dataset_generation: Any,
        training_commands: Any,
        interpretation: Any,
    ) -> None:
        self.study = study
        self.dataset = dataset
        self.preprocess = preprocess
        self.training = training
        self.evaluation = evaluation
        self.visualization = visualization
        self.dataset_generation = dataset_generation
        self.training_commands = training_commands
        self.interpretation = interpretation

    def build(
        self,
        *,
        last_error: ErrorSnapshot | None = None,
    ) -> ApplicationStateSnapshot:
        """Return a fresh serializable snapshot of backend state."""
        raw_data = list(getattr(self.study, "loaded_data_list", []) or [])
        preprocessed = list(getattr(self.study, "preprocessed_data_list", []) or [])
        epoch_data = getattr(self.study, "epoch_data", None)
        datasets = list(getattr(self.study, "datasets", []) or [])
        trainer = getattr(self.study, "trainer", None)
        model_holder = getattr(self.study, "model_holder", None)
        training_option = getattr(self.study, "training_option", None)

        raw_diagnostics = self._safe_call_dict(self.dataset.get_runtime_diagnostics)
        preprocess_diagnostics = self._safe_call_dict(
            self.preprocess.get_runtime_diagnostics,
        )
        event_info = self._safe_call_dict(self.dataset.get_event_info)
        evaluation = self._evaluation_snapshot()

        raw = RawStateSnapshot(
            loaded=bool(raw_data),
            count=len(raw_data),
            files=[self.data_filename(item) for item in raw_data],
            formats=self._raw_formats(raw_data),
            channels=self._raw_channels(raw_data),
            metadata=self._raw_metadata(raw_data),
            event_total=int(event_info.get("total", 0) or 0),
            unique_events=[
                str(item) for item in event_info.get("unique_labels", []) or []
            ],
            locked=self._safe_bool(self.dataset.is_locked),
            diagnostics=raw_diagnostics,
        )
        preprocessed_state = PreprocessedStateSnapshot(
            available=bool(preprocessed),
            count=len(preprocessed),
            files=[self.data_filename(item) for item in preprocessed],
            is_epoched=self._safe_bool(self.preprocess.is_epoched),
            channel_names=self._safe_list(self.preprocess.get_channel_names),
            operations=self._preprocess_history(preprocessed),
            diagnostics=preprocess_diagnostics,
        )
        epoch = EpochStateSnapshot(
            available=epoch_data is not None,
            exists=epoch_data is not None,
            epoch_count=self._epoch_count(epoch_data),
            n_channels=self._epoch_n_channels(epoch_data),
            n_times=self._epoch_n_times(epoch_data),
            event_names=self._epoch_event_names(epoch_data),
            event_ids=self._epoch_event_ids(epoch_data),
            channel_names=self._epoch_channel_names(epoch_data),
        )
        dataset = DatasetStateSnapshot(
            available=bool(datasets),
            count=len(datasets),
            names=[self._dataset_name(item, idx) for idx, item in enumerate(datasets)],
            locked=raw.locked,
            generator_exists=getattr(self.study, "dataset_generator", None) is not None,
            split_summary=self.dataset_generation.dataset_split_summary(datasets),
        )
        training = TrainingStateSnapshot(
            has_model=model_holder is not None,
            model_name=self.training_commands.model_name(model_holder),
            has_training_option=training_option is not None,
            training_option=self.training_commands.training_option_snapshot(
                training_option,
            ),
            has_trainer=trainer is not None,
            is_running=self._safe_bool(self.training.is_training),
            plan_count=evaluation.total_plans,
            run_count=evaluation.total_runs,
            finished_run_count=evaluation.finished_runs,
            progress_message=self._safe_string_call(
                getattr(self.training, "get_progress_text", None),
            ),
            missing_requirements=self._safe_list(
                self.training.get_missing_requirements,
            ),
        )
        visualization = VisualizationStateSnapshot(
            saliency_configured=(
                getattr(self.study, "saliency_params", None) is not None
            ),
            saliency_available=evaluation.finished_runs > 0
            and getattr(self.study, "saliency_params", None) is not None,
            montage_available=self._montage_available(epoch_data),
            channel_positions_available=self._channel_positions_available(epoch_data),
            channel_count=len(epoch.channel_names),
        )
        interpretation = self._interpretation_snapshot()
        active_dataset = ActiveDatasetSnapshot(
            has_raw_data=raw.count > 0,
            has_preprocessed_data=preprocessed_state.count > 0,
            has_epoch_data=epoch.exists,
            has_datasets=dataset.count > 0,
            is_locked=raw.locked,
        )
        active_training = ActiveTrainingSnapshot(
            has_model=training.has_model,
            has_training_option=training.has_training_option,
            has_trainer=training.has_trainer,
            is_running=training.is_running,
        )
        pipeline_stage = self._pipeline_stage_from_snapshots(
            active_dataset,
            active_training,
        )
        return ApplicationStateSnapshot(
            pipeline_stage=pipeline_stage,
            raw=raw,
            preprocessed=preprocessed_state,
            epoch=epoch,
            dataset=dataset,
            training=training,
            evaluation=evaluation,
            visualization=visualization,
            interpretation=interpretation,
            active_dataset=active_dataset,
            active_training=active_training,
            last_error=last_error,
        )

    def data_summary_from_state(
        self,
        state: ApplicationStateSnapshot,
    ) -> dict[str, Any]:
        data_list = self._safe_call_list(self.dataset.get_loaded_data_list)
        summary: dict[str, Any] = {
            "count": len(data_list) if data_list else state.raw.count,
            "files": [self.data_filename(item) for item in data_list]
            if data_list
            else state.raw.files,
            "formats": (
                self._raw_formats(data_list) if data_list else state.raw.formats
            ),
            "channels": (
                self._raw_channels(data_list) if data_list else state.raw.channels
            ),
            "metadata": self._raw_metadata(data_list)
            if data_list
            else state.raw.metadata,
            "total": state.raw.event_total,
            "unique_count": len(state.raw.unique_events),
            "unique_labels": state.raw.unique_events,
        }
        summary.update(self._safe_call_dict(self.dataset.get_event_info))
        summary.update(state.raw.diagnostics)
        return summary

    def smart_filter_suggestions(self, params: dict[str, Any]) -> list[int]:
        target_index = params.get("target_index")
        target_count = params.get("target_count")
        if target_index is None or target_count is None:
            raise PreconditionError("target_index and target_count are required.")
        data_list = list(self.dataset.get_loaded_data_list() or [])
        index = int(target_index)
        if index < 0 or index >= len(data_list):
            raise PreconditionError("target_index does not reference a loaded file.")
        return [
            int(item)
            for item in self.dataset.get_smart_filter_suggestions(
                data_list[index],
                int(target_count),
            )
        ]

    def training_history(
        self,
        *,
        include_objects: bool = False,
    ) -> list[dict[str, Any]]:
        """Return formatted training-history rows for UI or headless queries."""
        getter = getattr(self.training, "get_formatted_history", None)
        rows = self._safe_call_list(getter) if callable(getter) else []
        result: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            summary = {
                "group_name": str(row.get("group_name", "")),
                "run_name": str(row.get("run_name", "")),
                "model_name": str(row.get("model_name", "")),
                "is_active": bool(row.get("is_active", False)),
                "is_current_run": bool(row.get("is_current_run", False)),
            }
            if include_objects:
                summary["plan"] = row.get("plan")
                summary["record"] = row.get("record")
            result.append(summary)
        return result

    def _interpretation_snapshot(self) -> InterpretationStateSnapshot:
        return self.interpretation.snapshot()

    @staticmethod
    def _pipeline_stage_from_snapshots(
        active_dataset: ActiveDatasetSnapshot,
        active_training: ActiveTrainingSnapshot,
    ) -> str:
        if active_training.is_running:
            return "training"
        if active_training.has_trainer:
            return "trained"
        if active_dataset.has_datasets:
            return "dataset_ready"
        if active_dataset.has_epoch_data:
            return "preprocessed"
        if active_dataset.has_raw_data:
            return "data_loaded"
        return "empty"

    @staticmethod
    def _raw_formats(raw_data: list[Any]) -> list[str]:
        formats = []
        for item in raw_data:
            filename = StateSnapshotService.data_filename(item)
            _, ext = os.path.splitext(filename)
            if ext:
                formats.append(ext.lower())
        return sorted(set(formats))

    @staticmethod
    def _raw_channels(raw_data: list[Any]) -> list[str]:
        if not raw_data:
            return []
        try:
            return [str(ch) for ch in raw_data[0].get_mne().ch_names]
        except Exception:
            return []

    @staticmethod
    def _raw_metadata(raw_data: list[Any]) -> list[dict[str, str]]:
        metadata = []
        for idx, item in enumerate(raw_data):
            metadata.append(
                {
                    "index": str(idx),
                    "file": StateSnapshotService.data_filename(item),
                    "subject": StateSnapshotService._safe_string_attr(
                        item,
                        "get_subject_name",
                    ),
                    "session": StateSnapshotService._safe_string_attr(
                        item,
                        "get_session_name",
                    ),
                },
            )
        return metadata

    @staticmethod
    def _safe_string_attr(item: Any, method_name: str) -> str:
        method = getattr(item, method_name, None)
        if not callable(method):
            return ""
        try:
            return str(method())
        except Exception:
            return ""

    @staticmethod
    def data_filepath(item: Any) -> str:
        method = getattr(item, "get_filepath", None)
        if callable(method):
            try:
                return str(method())
            except Exception:
                logger.debug("Failed to read raw file path", exc_info=True)
        return StateSnapshotService.data_filename(item)

    @staticmethod
    def data_filename(data: Any) -> str:
        try:
            return str(data.get_filename())
        except Exception:
            return str(data)

    @staticmethod
    def _preprocess_history(preprocessed: list[Any]) -> list[str]:
        history: list[str] = []
        for item in preprocessed:
            getter = getattr(item, "get_preprocess_history", None)
            if not callable(getter):
                continue
            try:
                steps = getter()
                if steps is None:
                    continue
                for step in cast(Iterable[Any], steps):
                    text = str(step)
                    if text and text not in history:
                        history.append(text)
            except Exception as exc:
                logger.debug(
                    "Failed to read preprocess history from %s: %s",
                    StateSnapshotService.data_filename(item),
                    exc,
                )
                continue
        return history

    @staticmethod
    def _dataset_name(dataset: Any, idx: int) -> str:
        for attr in ("name", "dataset_name"):
            value = getattr(dataset, attr, None)
            if value:
                return str(value)
        getter = getattr(dataset, "get_name", None)
        if callable(getter):
            try:
                return str(getter())
            except Exception:
                pass
        return f"Dataset {idx + 1}"

    def _evaluation_snapshot(self) -> EvaluationStateSnapshot:
        plans = self._safe_call_list(self.evaluation.get_plans)
        total_runs = 0
        finished_runs = 0
        metrics_available = False
        for plan in plans:
            runs = self._safe_plan_runs(plan)
            total_runs += len(runs)
            for run in runs:
                if self._run_finished(run):
                    finished_runs += 1
                if getattr(run, "eval_record", None) is not None:
                    metrics_available = True
        return EvaluationStateSnapshot(
            available=finished_runs > 0,
            total_plans=len(plans),
            total_runs=total_runs,
            finished_runs=finished_runs,
            metrics_available=metrics_available,
        )

    @staticmethod
    def _safe_plan_runs(plan: Any) -> list[Any]:
        try:
            return list(plan.get_plans())
        except Exception:
            return []

    @staticmethod
    def _safe_plan_name(plan: Any, idx: int) -> str:
        try:
            return str(plan.get_name())
        except Exception:
            return f"Plan {idx + 1}"

    @staticmethod
    def _run_finished(run: Any) -> bool:
        try:
            return bool(run.is_finished())
        except Exception:
            return False

    @staticmethod
    def _shape(value: Any) -> tuple[int, ...] | None:
        shape = getattr(value, "shape", None)
        if shape is None:
            return None
        try:
            return tuple(int(dim) for dim in shape)
        except Exception:
            return None

    @staticmethod
    def _epoch_count(epoch_data: Any) -> int | None:
        if epoch_data is None:
            return None
        for attr in ("epoch_count", "n_epochs"):
            value = getattr(epoch_data, attr, None)
            if isinstance(value, int):
                return value
        shape = StateSnapshotService._shape(getattr(epoch_data, "data", None))
        if shape:
            return shape[0]
        getter = getattr(epoch_data, "get_data", None)
        if callable(getter):
            try:
                value = getter()
                shape = StateSnapshotService._shape(value)
                if shape:
                    return shape[0]
            except Exception:
                pass
        try:
            return len(epoch_data)
        except Exception:
            return None

    @staticmethod
    def _epoch_event_names(epoch_data: Any) -> list[str]:
        if epoch_data is None:
            return []
        event_ids = StateSnapshotService._epoch_event_ids(epoch_data)
        if event_ids:
            return sorted(event_ids)
        try:
            _, event_ids = epoch_data.get_event_list()
            if isinstance(event_ids, dict):
                return sorted(str(name) for name in event_ids)
        except Exception:
            pass
        return []

    @staticmethod
    def _epoch_event_ids(epoch_data: Any) -> dict[str, int] | None:
        if epoch_data is None:
            return None
        event_id = getattr(epoch_data, "event_id", None)
        if isinstance(event_id, dict):
            return {str(k): int(v) for k, v in event_id.items()}
        return None

    @staticmethod
    def _epoch_n_channels(epoch_data: Any) -> int | None:
        if epoch_data is None:
            return None
        shape = StateSnapshotService._shape(getattr(epoch_data, "data", None))
        if shape and len(shape) >= 2:
            return shape[1]
        return None

    @staticmethod
    def _epoch_n_times(epoch_data: Any) -> int | None:
        if epoch_data is None:
            return None
        shape = StateSnapshotService._shape(getattr(epoch_data, "data", None))
        if shape and len(shape) >= 3:
            return shape[2]
        return None

    @staticmethod
    def _epoch_channel_names(epoch_data: Any) -> list[str]:
        if epoch_data is None:
            return []
        for method_name in ("get_channel_names",):
            method = getattr(epoch_data, method_name, None)
            if callable(method):
                try:
                    values = cast(Iterable[Any], method())
                    return [str(ch) for ch in values]
                except Exception:
                    pass
        try:
            return [str(ch) for ch in epoch_data.get_mne().ch_names]
        except Exception:
            return []

    @staticmethod
    def _montage_available(epoch_data: Any) -> bool:
        if epoch_data is None:
            return False
        return bool(getattr(epoch_data, "channel_position", None))

    @staticmethod
    def _channel_positions_available(epoch_data: Any) -> bool:
        return StateSnapshotService._montage_available(epoch_data)

    @staticmethod
    def _safe_call_dict(call: Callable[[], Any]) -> dict[str, Any]:
        try:
            value = call()
        except Exception:
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _safe_call_list(call: Callable[[], Any]) -> list[Any]:
        try:
            value = call()
        except Exception:
            return []
        return list(value) if value is not None else []

    @staticmethod
    def _safe_list(call: Callable[[], Any]) -> list[Any]:
        try:
            value = call()
        except Exception:
            return []
        return list(value) if value is not None else []

    @staticmethod
    def _safe_bool(call: Callable[[], Any]) -> bool:
        try:
            return bool(call())
        except Exception:
            return False

    @staticmethod
    def _safe_string_call(call: Callable[[], Any] | None) -> str | None:
        if not callable(call):
            return None
        try:
            value = call()
        except Exception:
            return None
        if value is None:
            return None
        text = str(value)
        return text if text else None


class QueryStateCommandService:
    """Handle read-only query_state commands through the command spine."""

    def __init__(
        self,
        *,
        study: Any,
        dataset: Any,
        state_builder: StateSnapshotService,
        get_state: Callable[[], ApplicationStateSnapshot],
        get_capabilities: Callable[[], Any],
    ) -> None:
        self.study = study
        self.dataset = dataset
        self.state_builder = state_builder
        self.get_state = get_state
        self.get_capabilities = get_capabilities

    def handle_query_state(self, command: Command) -> HandlerResult:
        if not isinstance(command, QueryStateCommand):
            raise TypeError("Invalid command for query_state")

        query = str(command.query or "state").lower()
        state = self.get_state()
        if query == "state":
            return (
                "Application state snapshot ready.",
                {
                    "state": state.to_dict(),
                    "capabilities": self.get_capabilities().to_dict(),
                },
            )
        if query == "data_lists":
            loaded = list(getattr(self.study, "loaded_data_list", []) or [])
            preprocessed = list(
                getattr(self.study, "preprocessed_data_list", []) or [],
            )
            diagnostics: dict[str, Any] = {
                "raw_count": len(loaded),
                "preprocessed_count": len(preprocessed),
                "raw_files": state.raw.files,
                "preprocessed_files": state.preprocessed.files,
            }
            if command.include_objects:
                diagnostics["loaded_data_list"] = loaded
                diagnostics["preprocessed_data_list"] = preprocessed
            return "Data list query ready.", diagnostics
        if query == "dataset_generation_context":
            epoch_data = getattr(self.study, "epoch_data", None)
            dataset_generator = getattr(self.study, "dataset_generator", None)
            diagnostics = {
                "payload_type": "dataset_generation_context",
                "epoch_available": epoch_data is not None,
                "generator_exists": dataset_generator is not None,
            }
            if command.include_objects:
                diagnostics["epoch_data"] = epoch_data
                diagnostics["dataset_generator"] = dataset_generator
            return "Dataset generation context ready.", diagnostics
        if query == "data_summary":
            return "Dataset summary ready.", self.state_builder.data_summary_from_state(
                state,
            )
        if query == "preprocess_diagnostics":
            return (
                "Preprocess diagnostics ready.",
                dict(state.preprocessed.diagnostics),
            )
        if query == "smart_filter_suggestions":
            suggestions = self.state_builder.smart_filter_suggestions(command.params)
            return (
                "Smart filter suggestions ready.",
                {"suggestions": suggestions},
            )
        if query == "training_history":
            rows = self.state_builder.training_history(
                include_objects=command.include_objects,
            )
            return (
                "Training history query ready.",
                {
                    "payload_type": "training_history",
                    "row_count": len(rows),
                    "rows": rows,
                },
            )
        raise ValueError(f"Unknown query_state request: {command.query}")
