"""State snapshot service and compatibility exports for the command spine."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import replace
from typing import Any, cast

from XBrainLab.backend.services.dataset_state_service import DatasetStateReadPort
from XBrainLab.backend.services.preprocess_state_service import PreprocessStateReadPort
from XBrainLab.backend.services.training_state_service import (
    resolve_training_missing_requirements,
)
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyStatus,
    TrainingReadBoundary,
    TrainingTerminalOutcome,
)
from XBrainLab.backend.utils.logger import logger

from .epoch_context import (
    EPOCH_CONTEXT_AVAILABILITY_KEY,
    EpochContextAvailabilityCode,
    build_epoching_context,
    validated_epoch_context_availability,
)
from .errors import PreconditionError
from .pipeline_stage import pipeline_stage_from_snapshots
from .query_state_service import HandlerResult, QueryStateCommandService
from .saliency_coverage import (
    SaliencyCoverageProjector,
    saliency_coverage_for_eval_record,
    saliency_label_items_from_epoch,
    saliency_method_coverage,
)
from .serialization import serialize_json_value
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
    SaliencyRunCoverageSnapshot,
    TrainingStateSnapshot,
    VisualizationStateSnapshot,
)
from .training_history import project_training_history_rows
from .training_recommendation import (
    TrainingRecommendation,
    TrainingRecommendationContext,
    TrainingRecommendationService,
)
from .training_runtime import TrainingStateReadPort

__all__ = [
    "HandlerResult",
    "QueryStateCommandService",
    "StateSnapshotService",
    "saliency_coverage_for_eval_record",
    "saliency_label_items_from_epoch",
    "saliency_method_coverage",
]

_BACKGROUND_SNAPSHOT_ATTEMPTS = 3


class StateSnapshotService:
    """Build serializable backend state snapshots from the active study."""

    def __init__(
        self,
        *,
        study: Any,
        dataset: DatasetStateReadPort,
        preprocess: PreprocessStateReadPort,
        training: Any,
        training_runtime: TrainingStateReadPort,
        evaluation: Any,
        visualization: Any,
        dataset_generation: Any,
        training_commands: Any,
        interpretation: Any,
        saliency_coverage_projector: SaliencyCoverageProjector,
        training_state: Any | None = None,
        evaluation_state: Any | None = None,
        training_recommendation: TrainingRecommendationService | None = None,
    ) -> None:
        self.study = study
        self.dataset = dataset
        self.preprocess = preprocess
        self.training = training
        self.training_runtime = training_runtime
        self.training_state = training_state or training
        self.evaluation = evaluation
        self.evaluation_state = evaluation_state or evaluation
        self.visualization = visualization
        self.dataset_generation = dataset_generation
        self.training_commands = training_commands
        self.interpretation = interpretation
        self.saliency_coverage_projector = saliency_coverage_projector
        self.training_recommendation = training_recommendation

    def build(
        self,
        *,
        last_error: ErrorSnapshot | None = None,
    ) -> ApplicationStateSnapshot:
        """Return a snapshot that did not straddle a training transition."""
        latest: ApplicationStateSnapshot | None = None
        for _attempt in range(_BACKGROUND_SNAPSHOT_ATTEMPTS):
            before = self._training_snapshot_token()
            latest = self._build_once(
                last_error=last_error,
                training_read_generation=before.token.generation,
            )
            after = self._training_snapshot_token()
            if before == after and after.token.stable:
                identity_error = self._training_identity_error(latest, after)
                if identity_error is not None:
                    return self._fail_closed_training_snapshot(
                        latest,
                        identity_error,
                    )
                return latest

        if latest is None:
            raise RuntimeError("Application state snapshot was not attempted")
        return self._fail_closed_training_snapshot(
            latest,
            "training state changed during snapshot",
        )

    @staticmethod
    def _training_identity_error(
        snapshot: ApplicationStateSnapshot,
        boundary: TrainingReadBoundary,
    ) -> str | None:
        """Reject a run outcome that came from another trainer generation."""
        run = snapshot.training.terminal_outcome.run
        if run is None:
            return None
        if boundary.trainer_identity is None:
            return (
                "training terminal outcome identity does not match the read "
                "boundary: no trainer is active"
            )
        if run.trainer_id != boundary.trainer_identity:
            return "training terminal outcome identity does not match the read boundary"
        return None

    @staticmethod
    def _fail_closed_training_snapshot(
        snapshot: ApplicationStateSnapshot,
        error: str,
    ) -> ApplicationStateSnapshot:
        """Make an inconsistent training read unusable for command admission."""
        return replace(
            snapshot,
            pipeline_stage="unavailable",
            training=replace(snapshot.training, is_running=True),
            active_training=replace(snapshot.active_training, is_running=True),
            state_reliable=False,
            training_liveness_reliable=False,
            read_errors=[*snapshot.read_errors, error],
        )

    def _build_once(
        self,
        *,
        last_error: ErrorSnapshot | None = None,
        training_read_generation: int = 0,
    ) -> ApplicationStateSnapshot:
        """Return a fresh serializable snapshot of backend state."""
        read_errors: list[str] = []
        raw_data = list(getattr(self.study, "loaded_data_list", []) or [])
        preprocessed = list(getattr(self.study, "preprocessed_data_list", []) or [])
        epoch_data = getattr(self.study, "epoch_data", None)
        datasets = list(getattr(self.study, "datasets", []) or [])
        training_configuration = self.training_runtime.configuration_snapshot()
        has_trainer = self.training_runtime.has_trainer()
        model_holder = training_configuration.model_holder
        training_option = training_configuration.training_option
        interpretation = self._interpretation_snapshot()

        raw_diagnostics = (
            self._read_optional_dict(
                self.dataset.get_runtime_diagnostics,
                label="dataset.runtime_diagnostics",
            )
            if raw_data
            else {}
        )
        preprocess_diagnostics = dict(
            self._read_optional_dict(
                self.preprocess.get_runtime_diagnostics,
                label="preprocess.runtime_diagnostics",
            )
            if preprocessed
            else {}
        )
        preprocess_diagnostics.update(
            self._epoch_context_readiness_diagnostics(
                preprocessed,
                epoch_data=epoch_data,
                epoch_handoff=interpretation.epoch_handoff,
            )
        )
        event_info = (
            self._read_optional_dict(
                self.dataset.get_event_info,
                label="dataset.event_summary",
            )
            if raw_data
            else {}
        )
        evaluation, saliency_coverage = self._evaluation_snapshot(
            read_errors,
            label_items=self.saliency_coverage_projector.label_items_from_epoch(
                epoch_data,
            ),
        )
        post_training_saliency = self._post_training_saliency_status(read_errors)
        saliency_output_available = any(
            method.available and method.complete
            for run in saliency_coverage
            for method in run.methods
        )

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
            locked=self._read_authoritative_bool(
                getattr(self.study, "is_locked", lambda: False),
                label="dataset.is_locked",
                errors=read_errors,
                default=True,
            ),
            diagnostics=raw_diagnostics,
        )
        has_preprocess_context = bool(preprocessed) or epoch_data is not None
        preprocessed_state = PreprocessedStateSnapshot(
            available=bool(preprocessed),
            count=len(preprocessed),
            files=[self.data_filename(item) for item in preprocessed],
            is_epoched=(
                self._read_authoritative_bool(
                    getattr(self.preprocess, "is_epoched", None),
                    label="preprocess.is_epoched",
                    errors=read_errors,
                    default=False,
                )
                if has_preprocess_context
                else False
            ),
            channel_names=(
                self._read_authoritative_list(
                    getattr(self.preprocess, "get_channel_names", None),
                    label="preprocess.channel_names",
                    errors=read_errors,
                )
                if has_preprocess_context
                else []
            ),
            operations=self._preprocess_history(preprocessed, read_errors),
            diagnostics=preprocess_diagnostics,
        )
        epoch = EpochStateSnapshot(
            available=epoch_data is not None,
            exists=epoch_data is not None,
            epoch_count=self._epoch_count(epoch_data),
            n_channels=self._epoch_n_channels(epoch_data),
            n_times=self._epoch_n_times(epoch_data, read_errors),
            sfreq=self._epoch_sfreq(epoch_data, read_errors),
            event_names=self._epoch_event_names(epoch_data),
            event_ids=self._epoch_event_ids(epoch_data),
            channel_names=self._epoch_channel_names(epoch_data),
        )
        split_state = self.dataset_generation.dataset_split_state(datasets)
        dataset = DatasetStateSnapshot(
            available=bool(datasets),
            count=len(datasets),
            names=[self._dataset_name(item, idx) for idx, item in enumerate(datasets)],
            locked=raw.locked,
            generator_exists=getattr(self.study, "dataset_generator", None) is not None,
            split_spec_saved=bool(split_state["split_spec_saved"]),
            split_specification=dict(split_state["split_specification"]),
            split_specification_fingerprint=split_state[
                "split_specification_fingerprint"
            ],
            split_epoch_revision=split_state["split_epoch_revision"],
            split_preview_summary=dict(split_state["split_preview_summary"]),
            split_lifecycle=split_state["split_lifecycle"],
            split_materialized=bool(split_state["split_materialized"]),
            active_split_summary=dict(split_state["active_split_summary"]),
            last_split_attempt=dict(split_state["last_split_attempt"]),
        )
        model_name = self.training_commands.model_name(model_holder)
        model_params = self.training_commands.model_params_snapshot(model_holder)
        training_option_values = self.training_commands.training_option_snapshot(
            training_option,
        )
        recommendation = self._training_recommendation(
            epoch=epoch,
            dataset=dataset,
            model_name=model_name,
            model_params=model_params,
            training_option=training_option,
            training_option_values=training_option_values,
        )
        materialized_missing_requirements = self._read_authoritative_list(
            getattr(self.training_state, "get_missing_requirements", None),
            label="training.missing_requirements",
            errors=read_errors,
        )
        training = TrainingStateSnapshot(
            has_model=model_holder is not None,
            model_name=model_name,
            model_params=model_params,
            has_training_option=training_option is not None,
            training_option=training_option_values,
            recommendation=recommendation,
            has_trainer=has_trainer,
            is_running=self._read_authoritative_bool(
                getattr(self.training_state, "is_training", None),
                label="training.is_running",
                errors=read_errors,
                default=True,
            ),
            plan_count=evaluation.total_plans,
            run_count=evaluation.total_runs,
            finished_run_count=evaluation.finished_runs,
            read_generation=training_read_generation,
            progress_message=self._read_optional_string(
                getattr(self.training, "get_progress_text", None),
                label="training.progress",
            ),
            terminal_outcome=self._training_terminal_outcome(),
            missing_requirements=resolve_training_missing_requirements(
                materialized_missing_requirements,
                data_splitting_ready=dataset.split_spec_saved,
            ),
        )

        saliency_params = training_configuration.saliency_params
        visualization = VisualizationStateSnapshot(
            saliency_configured=bool(saliency_params),
            saliency_available=evaluation.finished_runs > 0
            and saliency_output_available,
            montage_available=self._montage_available(epoch_data),
            channel_positions_available=self._channel_positions_available(epoch_data),
            channel_count=len(epoch.channel_names),
            saliency_params=self._json_mapping(saliency_params),
            montage_channels=list(epoch.channel_names),
            montage_positions=self._montage_positions(epoch_data),
            saliency_coverage=saliency_coverage,
            post_training_saliency=post_training_saliency,
        )
        active_dataset = ActiveDatasetSnapshot(
            has_raw_data=raw.count > 0,
            has_preprocessed_data=preprocessed_state.count > 0,
            has_epoch_data=epoch.exists,
            has_datasets=dataset.count > 0,
            has_saved_split=dataset.split_spec_saved,
            is_locked=raw.locked,
        )
        active_training = ActiveTrainingSnapshot(
            has_model=training.has_model,
            has_training_option=training.has_training_option,
            has_trainer=training.has_trainer,
            is_running=training.is_running,
            finished_run_count=training.finished_run_count,
        )
        training_liveness_reliable = not any(
            error.startswith("training.is_running:") for error in read_errors
        )
        pipeline_stage = pipeline_stage_from_snapshots(
            active_dataset,
            active_training,
        ).value
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
            state_reliable=not read_errors,
            training_liveness_reliable=training_liveness_reliable,
            read_errors=sorted(read_errors),
        )

    @staticmethod
    def _epoch_context_readiness_diagnostics(
        preprocessed: list[Any],
        *,
        epoch_data: Any | None,
        epoch_handoff: dict[str, Any],
    ) -> dict[str, Any]:
        """Publish a canonical, metadata-only blocker needed by capability policy."""
        if not preprocessed or epoch_data is not None:
            return {}
        try:
            context = build_epoching_context(
                preprocessed,
                epoch_handoff=epoch_handoff,
            )
            availability = validated_epoch_context_availability(context)
        except (TypeError, ValueError):
            logger.debug(
                "Failed to project EEG epoch context readiness.", exc_info=True
            )
            return {}
        if (
            availability.code
            is not EpochContextAvailabilityCode.SAMPLING_FREQUENCY_MISMATCH
        ):
            return {}
        return {EPOCH_CONTEXT_AVAILABILITY_KEY: availability.to_payload()}

    def _training_recommendation(
        self,
        *,
        epoch: EpochStateSnapshot,
        dataset: DatasetStateSnapshot,
        model_name: str | None,
        model_params: dict[str, Any],
        training_option: Any | None,
        training_option_values: dict[str, Any],
    ) -> TrainingRecommendation | None:
        """Project a matching cached starting point without recomputing it."""
        service = self.training_recommendation
        if service is None or not (
            epoch.exists
            or dataset.available
            or model_name is not None
            or training_option is not None
        ):
            return None
        context = self._training_recommendation_context(
            epoch=epoch,
            dataset=dataset,
            model_name=model_name,
            model_params=model_params,
            training_option_values=training_option_values,
        )
        return service.for_state_snapshot(
            context,
            current_option=training_option,
        )

    def refresh_training_recommendation(
        self,
        state: ApplicationStateSnapshot,
        *,
        prospective_model_name: str | None = None,
        prospective_model_params: dict[str, Any] | None = None,
        prospective_device: str | None = None,
    ) -> TrainingRecommendation:
        """Build a recommendation from detached publication metadata only."""
        service = self.training_recommendation
        if service is None:
            raise PreconditionError("Training recommendations are unavailable.")
        configuration = self.training_runtime.configuration_snapshot()
        model_holder = configuration.model_holder
        training_option = configuration.training_option
        model_name = (
            prospective_model_name
            if prospective_model_name is not None
            else self.training_commands.model_name(model_holder)
        )
        model_params = (
            dict(prospective_model_params or {})
            if prospective_model_name is not None
            else self.training_commands.model_params_snapshot(model_holder)
        )
        option_values = self.training_commands.training_option_snapshot(training_option)
        if prospective_device is not None:
            option_values = {**option_values, "device": prospective_device}
        context = self._training_recommendation_context(
            epoch=state.epoch,
            dataset=state.dataset,
            model_name=model_name,
            model_params=model_params,
            training_option_values=option_values,
        )
        return service.recommend(
            context,
            current_option=training_option,
        )

    @staticmethod
    def _training_recommendation_context(
        *,
        epoch: EpochStateSnapshot,
        dataset: DatasetStateSnapshot,
        model_name: str | None,
        model_params: dict[str, Any],
        training_option_values: dict[str, Any],
    ) -> TrainingRecommendationContext:
        split_summary = dataset.active_split_summary
        split_preview_summary = dataset.split_preview_summary
        train_count = StateSnapshotService._positive_summary_count(
            split_summary,
            "train_count",
        )
        if train_count is None:
            train_count = StateSnapshotService._positive_summary_count(
                split_preview_summary,
                "train_count",
            )
        validation_count = StateSnapshotService._positive_summary_count(
            split_summary,
            "val_count",
            allow_zero=True,
        )
        if validation_count is None:
            validation_count = StateSnapshotService._positive_summary_count(
                split_preview_summary,
                "validation_count",
                allow_zero=True,
            )
        preview_dataset_count = StateSnapshotService._positive_summary_count(
            split_preview_summary,
            "dataset_count",
        )
        return TrainingRecommendationContext(
            model_name=model_name,
            model_params=dict(model_params),
            epoch_count=epoch.epoch_count,
            n_channels=epoch.n_channels,
            n_times=epoch.n_times,
            dataset_count=dataset.count or preview_dataset_count or 0,
            training_sample_count=train_count or epoch.epoch_count,
            validation_sample_count=validation_count,
            device=str(training_option_values.get("device") or "auto"),
        )

    @staticmethod
    def _positive_summary_count(
        summary: dict[str, Any],
        key: str,
        *,
        allow_zero: bool = False,
    ) -> int | None:
        value = summary.get(key)
        if value is None or isinstance(value, bool):
            return None
        try:
            parsed = int(cast(Any, value))
        except (TypeError, ValueError):
            return None
        if parsed > 0 or (allow_zero and parsed == 0):
            return parsed
        return None

    def _training_terminal_outcome(self) -> TrainingTerminalOutcome:
        """Read typed trainer truth; never infer it from progress display text."""
        return self.training_runtime.terminal_outcome()

    def _post_training_saliency_status(
        self,
        read_errors: list[str],
    ) -> PostTrainingSaliencyStatus:
        """Read the immutable background saliency lifecycle from its owner."""
        try:
            status = self.training_runtime.saliency_status()
        except Exception as exc:
            read_errors.append(f"visualization.post_training_saliency: {exc}")
            return PostTrainingSaliencyStatus.idle()
        if not isinstance(status, PostTrainingSaliencyStatus):
            read_errors.append(
                "visualization.post_training_saliency: invalid status contract"
            )
            return PostTrainingSaliencyStatus.idle()
        return status

    def capture_training_read_boundary(self) -> TrainingReadBoundary:
        """Return the identity/generation guarding an object-bearing read."""
        return self._training_snapshot_token()

    def _training_snapshot_token(self) -> TrainingReadBoundary:
        """Return trainer identity/generation around one snapshot attempt."""
        return self.training_runtime.capture_read_boundary()

    def data_summary_from_state(
        self,
        state: ApplicationStateSnapshot,
    ) -> dict[str, Any]:
        data_list = self._read_optional_list(
            self.dataset.get_loaded_data_list,
            label="dataset.loaded_data_summary",
        )
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
            "runtime_signals": [],
            "gdf_duplicate_channel_files": [],
            "gdf_duplicate_channel_details": [],
        }
        summary.update(
            self._read_optional_dict(
                self.dataset.get_event_info,
                label="dataset.event_summary",
            )
        )
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

    def training_history(self) -> list[dict[str, Any]]:
        """Return detached training-history rows for UI or headless queries."""
        getter = getattr(self.training_state, "get_formatted_history", None)
        rows = list(cast(Callable[[], Any], getter)() or []) if callable(getter) else []
        return project_training_history_rows(rows)

    def _interpretation_snapshot(self) -> InterpretationStateSnapshot:
        return self.interpretation.snapshot()

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
    def _preprocess_history(
        preprocessed: list[Any],
        read_errors: list[str],
    ) -> list[str]:
        """Read capability-driving preprocess history without hiding failures."""
        history: list[str] = []
        for index, item in enumerate(preprocessed):
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
                read_errors.append(f"preprocess.history[{index}]: {exc}")
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
                logger.debug("Dataset name lookup failed", exc_info=True)
        return f"Dataset {idx + 1}"

    def _evaluation_snapshot(
        self,
        read_errors: list[str],
        *,
        label_items: Iterable[tuple[object, object]] | None = None,
    ) -> tuple[EvaluationStateSnapshot, list[SaliencyRunCoverageSnapshot]]:
        """Read evaluation truth once and record every plan/run read failure."""
        try:
            plans = list(self.evaluation_state.get_plans() or [])
        except Exception as exc:
            read_errors.append(f"evaluation.plans: {exc}")
            plans = []
        total_runs = 0
        finished_runs = 0
        metrics_available = False
        saliency_coverage: list[SaliencyRunCoverageSnapshot] = []
        for plan_index, plan in enumerate(plans):
            runs = self._read_plan_runs(plan, plan_index, read_errors)
            total_runs += len(runs)
            for run_index, run in enumerate(runs):
                run_context = f"evaluation.plan[{plan_index}].run[{run_index}]"
                try:
                    is_finished = self._run_finished(run)
                except Exception as exc:
                    read_errors.append(f"{run_context}.is_finished: {exc}")
                    is_finished = False
                try:
                    eval_record = getattr(run, "eval_record", None)
                except Exception as exc:
                    read_errors.append(f"{run_context}.eval_record: {exc}")
                    eval_record = None
                try:
                    saliency_record_getter = getattr(
                        type(run),
                        "get_saliency_eval_record",
                        None,
                    )
                    saliency_record = (
                        saliency_record_getter(run)
                        if callable(saliency_record_getter)
                        else eval_record
                    )
                except Exception as exc:
                    read_errors.append(f"{run_context}.saliency_record: {exc}")
                    saliency_record = eval_record
                if is_finished:
                    finished_runs += 1
                if eval_record is not None:
                    metrics_available = True
                if is_finished and saliency_record is not None:
                    try:
                        saliency_coverage.append(
                            replace(
                                self.saliency_coverage_projector.project_run(
                                    saliency_record,
                                    plan_index=plan_index,
                                    run_index=run_index,
                                    label_items=label_items,
                                ),
                                plan_name=self._safe_plan_name(plan, plan_index),
                                model_name=self._plan_model_name(plan),
                                run_name=f"Run {run_index + 1}",
                            )
                        )
                    except Exception as exc:
                        read_errors.append(f"{run_context}.saliency: {exc}")
        return (
            EvaluationStateSnapshot(
                available=finished_runs > 0,
                total_plans=len(plans),
                total_runs=total_runs,
                finished_runs=finished_runs,
                metrics_available=metrics_available,
            ),
            saliency_coverage,
        )

    @staticmethod
    def _read_plan_runs(
        plan: Any,
        plan_index: int,
        read_errors: list[str],
    ) -> list[Any]:
        try:
            return list(plan.get_plans() or [])
        except Exception as exc:
            read_errors.append(f"evaluation.plan[{plan_index}].runs: {exc}")
            return []

    @staticmethod
    def _safe_plan_name(plan: Any, idx: int) -> str:
        try:
            return str(plan.get_name())
        except Exception:
            return f"Plan {idx + 1}"

    @staticmethod
    def _plan_model_name(plan: Any) -> str:
        model_holder = getattr(plan, "model_holder", None)
        target_model = getattr(model_holder, "target_model", None)
        return str(getattr(target_model, "__name__", "Unknown model"))

    @staticmethod
    def _run_finished(run: Any) -> bool:
        return bool(run.is_finished())

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
                logger.debug("Epoch data shape lookup failed", exc_info=True)
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
            logger.debug("Epoch event-list lookup failed", exc_info=True)
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
    def _epoch_n_times(
        epoch_data: Any,
        read_errors: list[str],
    ) -> int | None:
        """Read model-compatibility sample count without hiding malformed state."""
        if epoch_data is None:
            return None
        try:
            data = getattr(epoch_data, "data", None)
            raw_shape = getattr(data, "shape", None)
        except Exception as exc:
            read_errors.append(f"epoch.n_times: {exc}")
            return None
        if raw_shape is None:
            return None
        if not isinstance(raw_shape, (list, tuple)):
            # Compatibility wrappers may expose a placeholder ``shape`` object
            # while intentionally omitting concrete epoch dimensions.
            return None
        try:
            shape = tuple(int(dim) for dim in raw_shape)
        except Exception:
            read_errors.append(f"epoch.n_times: invalid shape {raw_shape!r}")
            return None
        if shape and len(shape) >= 3:
            return shape[2]
        read_errors.append(f"epoch.n_times: expected 3D shape, got {shape!r}")
        return None

    @staticmethod
    def _epoch_sfreq(
        epoch_data: Any,
        read_errors: list[str],
    ) -> float | None:
        """Read model-compatibility sampling rate when the field is present."""
        if epoch_data is None:
            return None
        try:
            value = getattr(epoch_data, "sfreq", None)
        except Exception as exc:
            read_errors.append(f"epoch.sfreq: {exc}")
            return None
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            read_errors.append(f"epoch.sfreq: invalid value {value!r}")
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
                    logger.debug("Epoch channel-name lookup failed", exc_info=True)
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
    def _montage_positions(epoch_data: Any) -> list[list[float]]:
        if epoch_data is None:
            return []
        positions = getattr(epoch_data, "channel_position", None)
        values: Iterable[Any]
        if isinstance(positions, dict):
            values = positions.values()
        elif isinstance(positions, (list, tuple)):
            values = positions
        else:
            return []
        result: list[list[float]] = []
        for position in values:
            normalized = StateSnapshotService._float_position(position)
            if normalized is not None:
                result.append(normalized)
        return result

    @staticmethod
    def _float_position(position: Any) -> list[float] | None:
        try:
            return [float(value) for value in position]
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _json_mapping(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        return cast(dict[str, Any], serialize_json_value(value))

    @staticmethod
    def _read_optional_dict(
        call: Callable[[], Any],
        *,
        label: str,
    ) -> dict[str, Any]:
        """Read display-only diagnostics without invalidating workflow truth."""
        try:
            value = call()
        except Exception as exc:
            logger.debug("Optional state read %s failed: %s", label, exc)
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _read_optional_list(
        call: Callable[[], Any],
        *,
        label: str,
    ) -> list[Any]:
        """Read a best-effort query summary that does not drive capabilities."""
        try:
            value = call()
        except Exception as exc:
            logger.debug("Optional state read %s failed: %s", label, exc)
            return []
        return list(value) if value is not None else []

    @staticmethod
    def _read_authoritative_list(
        call: Callable[[], Any] | None,
        *,
        label: str,
        errors: list[str],
    ) -> list[Any]:
        """Read workflow truth and label failures so policy can fail closed."""
        if not callable(call):
            errors.append(f"{label}: reader unavailable")
            return []
        try:
            value = call()
        except Exception as exc:
            errors.append(f"{label}: {exc}")
            return []
        return list(value) if value is not None else []

    @staticmethod
    def _read_authoritative_bool(
        call: Callable[[], Any] | None,
        *,
        label: str,
        errors: list[str],
        default: bool,
    ) -> bool:
        """Read workflow truth and use a conservative value after failure."""
        if not callable(call):
            errors.append(f"{label}: reader unavailable")
            return default
        try:
            return bool(call())
        except Exception as exc:
            errors.append(f"{label}: {exc}")
            return default

    @staticmethod
    def _read_optional_string(
        call: Callable[[], Any] | None,
        *,
        label: str,
    ) -> str | None:
        """Read presentation text without treating its absence as state failure."""
        if not callable(call):
            return None
        try:
            value = call()
        except Exception as exc:
            logger.debug("Optional state read %s failed: %s", label, exc)
            return None
        if value is None:
            return None
        text = str(value)
        return text if text else None
