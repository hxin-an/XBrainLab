"""Preprocessing and epoch command handlers for the application command spine."""

from __future__ import annotations

import hmac
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from typing import Any

from XBrainLab.backend.exceptions import StaleTrainingPipelineMutationError
from XBrainLab.backend.preprocessor.normalize import (
    NORMALIZATION_RUNTIME_KEY,
    NORMALIZATION_SCOPE,
)
from XBrainLab.backend.preprocessor.time_epoch import summarize_epoch_boundaries
from XBrainLab.backend.services.dataset_state_service import (
    DatasetChannelSelectionPort,
    PreparedChannelSelection,
)
from XBrainLab.backend.services.preprocess_state_service import (
    PreparedPreprocessData,
    PreprocessProductPort,
)

from .commands import (
    ApplyMontageCommand,
    Command,
    CreateEpochCommand,
    PreprocessCommand,
    PreprocessOperation,
)
from .epoch_context import (
    EPOCH_HINT_KEY,
    build_epoch_confirmation_requirement,
    build_epoching_context,
    require_epoch_context_available,
    validated_epoch_handoff,
)
from .errors import (
    ApplicationError,
    ConfirmationRequiredError,
    PreconditionError,
    map_exception,
)
from .pipeline_transaction import PipelineStateIdentity, PipelineStateTransaction
from .preprocess_preparation import (
    ApplicationPreprocessBoundary,
    PreparedPreprocessCommand,
    PreprocessMutationPlan,
)
from .resource_guard import RISK_UNKNOWN, ResourceChecker
from .state import ApplicationStateSnapshot, InterpretationStateSnapshot

HandlerResult = str | tuple[str, dict[str, Any]]

EPOCH_BOUNDARY_AUTO_EXCLUDE_MAX_RATIO = 0.01


class PreprocessCommandService:
    """Handle preprocessing, montage, and epoch creation commands."""

    def __init__(
        self,
        *,
        preprocess: PreprocessProductPort,
        dataset: DatasetChannelSelectionPort,
        get_state: Callable[[], ApplicationStateSnapshot],
        pipeline_transaction: PipelineStateTransaction | None = None,
    ) -> None:
        self.preprocess = preprocess
        self.dataset = dataset
        self._get_state = get_state
        self._pipeline_transaction = pipeline_transaction

    def begin_prepared_command(
        self,
        command: PreprocessCommand | CreateEpochCommand,
        *,
        application_boundary: ApplicationPreprocessBoundary,
    ) -> PreprocessMutationPlan:
        """Capture identities for a transform that will run outside the lock."""
        if self._pipeline_transaction is None:
            raise RuntimeError(
                "Prepared preprocessing requires a pipeline transaction."
            )
        if not isinstance(application_boundary, ApplicationPreprocessBoundary):
            raise TypeError(
                "application_boundary must be ApplicationPreprocessBoundary"
            )
        if isinstance(command, PreprocessCommand):
            operation = PreprocessOperation(command.operation)
            if operation is PreprocessOperation.SET_MONTAGE:
                raise TypeError(
                    f"{operation.value} does not use prepared preprocessing."
                )
        elif not isinstance(command, CreateEpochCommand):
            raise TypeError("Invalid command for prepared preprocessing")
        training_boundary = self._pipeline_transaction.begin_downstream_replacement()
        training_startup_snapshot = (
            self._pipeline_transaction.capture_training_startup_snapshot()
        )
        pipeline_snapshot = self._pipeline_transaction.capture()
        return PreprocessMutationPlan.capture(
            command,
            application=application_boundary,
            training=training_boundary,
            training_startup_snapshot=training_startup_snapshot,
            pipeline_snapshot=pipeline_snapshot,
        )

    def prepare_command(
        self,
        plan: PreprocessMutationPlan,
    ) -> PreparedPreprocessCommand:
        """Transform captured EEG holders without touching the active Study."""
        if not isinstance(plan, PreprocessMutationPlan):
            raise TypeError("plan must be PreprocessMutationPlan")
        detached = self.preprocess.detached_preparation_service(
            plan.pipeline_snapshot.preprocessed_data
        )
        if isinstance(plan.command, PreprocessCommand):
            operation = PreprocessOperation(plan.command.operation)
            if operation in {
                PreprocessOperation.CHANNEL_SELECTION,
                PreprocessOperation.SELECT_CHANNELS,
            }:
                channels = self._require(plan.command.channels, "channels")
                prepared_data = self.dataset.prepare_channel_selection(
                    channels,
                    source_data=plan.pipeline_snapshot.loaded_data,
                )
                handler_result = f"Selected {len(channels)} channel(s)."
            else:
                prepared_data, handler_result = self._prepare_preprocess(
                    detached,
                    plan.command,
                    source_data=plan.pipeline_snapshot.preprocessed_data,
                )
        else:
            prepared_data, handler_result = self._prepare_epoch(
                detached,
                plan.command,
                state=plan.application.state,
                source_data=plan.pipeline_snapshot.preprocessed_data,
            )
        message, diagnostics = self._normalize_handler_result(handler_result)
        return PreparedPreprocessCommand.create(
            plan=plan,
            prepared_data=prepared_data,
            message=message,
            diagnostics=diagnostics,
        )

    def commit_prepared_command(
        self,
        prepared: PreparedPreprocessCommand,
    ) -> HandlerResult:
        """Revalidate captured pipeline identity and publish one short commit."""
        if not isinstance(prepared, PreparedPreprocessCommand):
            raise TypeError("prepared must be PreparedPreprocessCommand")
        if self._pipeline_transaction is None:
            raise RuntimeError(
                "Prepared preprocessing commit requires a pipeline transaction."
            )
        plan = prepared.plan
        current_pipeline = self._pipeline_transaction.capture()
        if (
            PipelineStateIdentity.from_snapshot(current_pipeline)
            != plan.pipeline_identity
        ):
            raise PreconditionError(
                "EEG pipeline state changed while preprocessing was prepared. "
                "Review the current data and retry.",
                diagnostics={
                    "code": "stale_prepared_preprocess",
                    "stale_prepared_preprocess": True,
                    "state_preserved": True,
                },
            )

        expected_source_identity = (
            plan.pipeline_identity.loaded_data
            if isinstance(prepared.prepared_data, PreparedChannelSelection)
            else plan.pipeline_identity.preprocessed_data
        )
        if prepared.prepared_data.source_identity != expected_source_identity:
            raise PreconditionError(
                "Prepared EEG source identity no longer matches the active pipeline.",
                diagnostics={
                    "code": "stale_prepared_preprocess",
                    "stale_prepared_preprocess": True,
                    "state_preserved": True,
                },
            )

        def publish() -> None:
            if isinstance(prepared.prepared_data, PreparedChannelSelection):
                self.dataset.commit_prepared_channel_selection(prepared.prepared_data)
            else:
                self.preprocess.commit_prepared(prepared.prepared_data)

        try:
            trainer_retired = self._pipeline_transaction.commit_pipeline_replacement(
                plan.training,
                publish=publish,
            )
        except BaseException as exc:
            if isinstance(exc, Exception) and self._is_stale_pipeline_boundary_error(
                exc
            ):
                raise
            if not isinstance(exc, Exception):
                with suppress(BaseException):
                    self._pipeline_transaction.restore_training_startup_snapshot(
                        plan.training_startup_snapshot,
                    )
                with suppress(BaseException):
                    self._pipeline_transaction.restore(plan.pipeline_snapshot)
                raise
            rollback_errors: list[str] = []
            try:
                self._pipeline_transaction.restore_training_startup_snapshot(
                    plan.training_startup_snapshot,
                )
            except Exception as rollback_exc:
                rollback_errors.append(map_exception(rollback_exc).message)
            try:
                self._pipeline_transaction.restore(plan.pipeline_snapshot)
            except Exception as rollback_exc:
                rollback_errors.append(map_exception(rollback_exc).message)
            if rollback_errors:
                mapped = map_exception(exc)
                raise ApplicationError(
                    message=mapped.message,
                    error_type=mapped.error_type,
                    recoverable=mapped.recoverable,
                    diagnostics={
                        **mapped.diagnostics,
                        "state_preserved": False,
                        "rollback_failed": True,
                        "rollback_errors": rollback_errors,
                    },
                ) from exc
            raise
        message, diagnostics = self._normalize_handler_result(prepared.handler_result())
        return message, {**diagnostics, "trainer_cleared": trainer_retired}

    @staticmethod
    def _is_stale_pipeline_boundary_error(exc: Exception) -> bool:
        if isinstance(exc, StaleTrainingPipelineMutationError):
            return True
        return bool(
            isinstance(exc, PreconditionError)
            and exc.diagnostics.get("code") == "training_pipeline_boundary_changed"
        )

    def handle_preprocess(self, command: Command) -> HandlerResult:
        if not isinstance(command, PreprocessCommand):
            raise TypeError("Invalid command for preprocess")
        operation = PreprocessOperation(command.operation)
        if operation == PreprocessOperation.BANDPASS:
            low_freq = self._require(command.low_freq, "low_freq")
            high_freq = self._require(command.high_freq, "high_freq")
            notch_freqs = [command.notch_freq] if command.notch_freq else None
            self.preprocess.apply_filter(low_freq, high_freq, notch_freqs)
            return f"Applied bandpass filter ({low_freq}-{high_freq} Hz)."
        if operation == PreprocessOperation.NOTCH:
            freq = self._require(command.notch_freq, "notch_freq")
            self.preprocess.apply_filter(None, None, [freq])
            return f"Applied notch filter ({freq} Hz)."
        if operation == PreprocessOperation.RESAMPLE:
            rate = self._require(command.rate, "rate")
            self.preprocess.apply_resample(rate)
            return f"Resampled data to {rate} Hz."
        if operation == PreprocessOperation.NORMALIZE:
            method = self._require(command.method, "method")
            raw_count, epoch_count = self._normalization_target_counts()
            self.preprocess.apply_normalization(method)
            return self._normalization_result(
                str(method),
                raw_count=raw_count,
                epoch_count=epoch_count,
            )
        if operation == PreprocessOperation.REREFERENCE:
            ref_channels: str | list[str]
            if command.channels:
                ref_channels = command.channels
                method = ", ".join(command.channels)
            else:
                method = self._require(command.method, "method")
                ref_channels = "average" if method == "average" else [method]
            self.preprocess.apply_rereference(ref_channels)
            return f"Applied reference: {method}."
        if operation in (
            PreprocessOperation.CHANNEL_SELECTION,
            PreprocessOperation.SELECT_CHANNELS,
        ):
            channels = self._require(command.channels, "channels")
            self.dataset.apply_channel_selection(channels)
            return f"Selected {len(channels)} channel(s)."
        if operation == PreprocessOperation.SET_MONTAGE:
            montage_name = self._require(command.montage_name, "montage_name")
            raise ConfirmationRequiredError(
                "set_montage requires UI confirmation and remains on the "
                f"app confirmation path for '{montage_name}'.",
            )
        if operation == PreprocessOperation.STANDARD:
            return self._handle_standard_preprocess(command)
        raise ValueError(f"Unsupported preprocess operation: {operation}")

    def _prepare_preprocess(
        self,
        target: PreprocessProductPort,
        command: PreprocessCommand,
        *,
        source_data: Sequence[Any],
    ) -> tuple[PreparedPreprocessData, HandlerResult]:
        """Prepare one non-raw preprocessing command without publication."""
        operation = PreprocessOperation(command.operation)
        if operation == PreprocessOperation.BANDPASS:
            low_freq = self._require(command.low_freq, "low_freq")
            high_freq = self._require(command.high_freq, "high_freq")
            notch_freqs = [command.notch_freq] if command.notch_freq else None
            return (
                target.prepare_filter(low_freq, high_freq, notch_freqs),
                f"Applied bandpass filter ({low_freq}-{high_freq} Hz).",
            )
        if operation == PreprocessOperation.NOTCH:
            freq = self._require(command.notch_freq, "notch_freq")
            return (
                target.prepare_filter(None, None, [freq]),
                f"Applied notch filter ({freq} Hz).",
            )
        if operation == PreprocessOperation.RESAMPLE:
            rate = self._require(command.rate, "rate")
            return target.prepare_resample(rate), f"Resampled data to {rate} Hz."
        if operation == PreprocessOperation.NORMALIZE:
            method = self._require(command.method, "method")
            raw_count, epoch_count = self._normalization_target_counts_for(source_data)
            return (
                target.prepare_normalization(method),
                self._normalization_result(
                    str(method),
                    raw_count=raw_count,
                    epoch_count=epoch_count,
                ),
            )
        if operation == PreprocessOperation.REREFERENCE:
            ref_channels: str | list[str]
            if command.channels:
                ref_channels = command.channels
                method = ", ".join(command.channels)
            else:
                method = self._require(command.method, "method")
                ref_channels = "average" if method == "average" else [method]
            return (
                target.prepare_rereference(ref_channels),
                f"Applied reference: {method}.",
            )
        if operation == PreprocessOperation.STANDARD:
            low_freq = command.low_freq if command.low_freq is not None else 4
            high_freq = command.high_freq if command.high_freq is not None else 40
            reference: str | list[str] | None = None
            if command.channels:
                is_average = (
                    len(command.channels) == 1
                    and command.channels[0].lower() == "average"
                )
                reference = "average" if is_average else list(command.channels)
            prepared = target.prepare_standard_pipeline(
                l_freq=low_freq,
                h_freq=high_freq,
                notch_freq=command.notch_freq,
                rate=command.rate,
                ref_channels=reference,
                normalization=command.method,
            )
            if command.method:
                raw_count, epoch_count = self._normalization_target_counts_for(
                    source_data
                )
                message, diagnostics = self._normalization_result(
                    command.method,
                    raw_count=raw_count,
                    epoch_count=epoch_count,
                )
                return prepared, (
                    f"Standard preprocessing applied. {message}",
                    diagnostics,
                )
            return prepared, "Standard preprocessing applied."
        raise ValueError(
            f"Unsupported prepared preprocess operation: {operation.value}"
        )

    def _prepare_epoch(
        self,
        target: PreprocessProductPort,
        command: CreateEpochCommand,
        *,
        state: ApplicationStateSnapshot,
        source_data: Sequence[Any],
    ) -> tuple[PreparedPreprocessData, HandlerResult]:
        """Validate and materialize epochs against the admitted state snapshot."""
        handoff = self._epoch_handoff_from_state(state)
        preprocessed_data = list(source_data)
        epoch_context = build_epoching_context(
            preprocessed_data,
            epoch_handoff=handoff,
        )
        require_epoch_context_available(epoch_context)
        event_ids = self._event_ids_for_epoch_command(command, handoff=handoff)
        self._enforce_epoch_confirmation(
            command,
            epoch_context=epoch_context,
            effective_event_ids=event_ids,
        )
        resource_check = ResourceChecker.check_epoch_materialization_safe(
            preprocessed_data,
            selected_event_names=event_ids,
            tmin=command.t_min,
            tmax=command.t_max,
        )
        if resource_check.blocking or resource_check.risk_level == RISK_UNKNOWN:
            raise PreconditionError(
                resource_check.message,
                diagnostics={
                    "resource_preflight": resource_check.to_diagnostics(),
                },
            )
        boundary_summary = summarize_epoch_boundaries(
            preprocessed_data,
            event_ids,
            tmin=command.t_min,
            tmax=command.t_max,
        )
        event_label_aliases_by_source = self._event_label_aliases_by_source(
            handoff,
            preprocessed_data,
        )
        boundary_diagnostics = boundary_summary.to_diagnostics()
        if boundary_summary.excluded_event_count:
            if boundary_summary.remaining_event_count <= 0:
                raise PreconditionError(
                    "The selected epoch window exceeds recording bounds for every "
                    "selected event. Shorten the EEG epoch window before continuing.",
                    diagnostics={"epoch_boundary_check": boundary_diagnostics},
                )
            if boundary_summary.excluded_ratio > EPOCH_BOUNDARY_AUTO_EXCLUDE_MAX_RATIO:
                raise PreconditionError(
                    "The selected epoch window would exclude "
                    f"{boundary_summary.excluded_event_count} of "
                    f"{boundary_summary.selected_event_count} selected events "
                    "because they are too close to a recording boundary. Shorten "
                    "the epoch window or review the selected events.",
                    diagnostics={"epoch_boundary_check": boundary_diagnostics},
                )
        prepared = target.prepare_epoching(
            command.baseline,
            event_ids,
            command.t_min,
            command.t_max,
            bool(boundary_summary.excluded_event_count),
            event_label_aliases_by_source=event_label_aliases_by_source,
        )
        message = f"Created EEG epochs from {command.t_min}s to {command.t_max}s."
        diagnostics: dict[str, Any] = {
            "epoch_boundary_check": boundary_diagnostics,
        }
        if boundary_summary.excluded_event_count:
            message += (
                f" Excluded {boundary_summary.excluded_event_count} boundary "
                "event(s) that could not contain the complete window."
            )
        applied = self._applied_deferred_normalization_count_for(prepared.data)
        if not applied and not boundary_summary.excluded_event_count:
            return prepared, message
        if not applied:
            return prepared, (message, diagnostics)
        diagnostics.update(
            {
                "normalization_scope": NORMALIZATION_SCOPE,
                "deferred_normalization_applied_count": applied,
                "recording_statistics_used": False,
            }
        )
        return prepared, (message, diagnostics)

    @staticmethod
    def _normalize_handler_result(
        value: HandlerResult,
    ) -> tuple[str, dict[str, Any]]:
        if isinstance(value, tuple):
            return str(value[0]), dict(value[1])
        return str(value), {}

    def handle_apply_montage(self, command: Command) -> HandlerResult:
        if not isinstance(command, ApplyMontageCommand):
            raise TypeError("Invalid command for apply_montage")
        if not command.channels:
            raise PreconditionError("channels list cannot be empty.")
        if not command.positions:
            raise PreconditionError("positions list cannot be empty.")
        if len(command.channels) != len(command.positions):
            raise PreconditionError("channels and positions must have equal length.")

        self.preprocess.apply_montage(command.channels, command.positions)
        message = (
            f"Applied montage '{command.montage_name}' "
            f"to {len(command.channels)} channel(s)."
            if command.montage_name
            else f"Applied montage to {len(command.channels)} channel(s)."
        )
        return (
            message,
            {
                "channel_count": len(command.channels),
                "montage_name": command.montage_name,
            },
        )

    def handle_create_epoch(self, command: Command) -> HandlerResult:
        if not isinstance(command, CreateEpochCommand):
            raise TypeError("Invalid command for create_epoch")
        handoff = self._epoch_handoff()
        preprocessed_data = self.preprocess.get_preprocessed_data_list()
        epoch_context = build_epoching_context(
            preprocessed_data,
            epoch_handoff=handoff,
        )
        require_epoch_context_available(epoch_context)
        event_ids = self._event_ids_for_epoch_command(command, handoff=handoff)
        self._enforce_epoch_confirmation(
            command,
            epoch_context=epoch_context,
            effective_event_ids=event_ids,
        )
        resource_check = ResourceChecker.check_epoch_materialization_safe(
            preprocessed_data,
            selected_event_names=event_ids,
            tmin=command.t_min,
            tmax=command.t_max,
        )
        if resource_check.blocking or resource_check.risk_level == RISK_UNKNOWN:
            raise PreconditionError(
                resource_check.message,
                diagnostics={
                    "resource_preflight": resource_check.to_diagnostics(),
                },
            )
        boundary_summary = summarize_epoch_boundaries(
            preprocessed_data,
            event_ids,
            tmin=command.t_min,
            tmax=command.t_max,
        )
        event_label_aliases_by_source = self._event_label_aliases_by_source(
            handoff,
            preprocessed_data,
        )
        epoch_options: dict[str, Any] = {}
        if event_label_aliases_by_source is not None:
            epoch_options["event_label_aliases_by_source"] = (
                event_label_aliases_by_source
            )
        boundary_diagnostics = boundary_summary.to_diagnostics()
        if boundary_summary.excluded_event_count:
            if boundary_summary.remaining_event_count <= 0:
                raise PreconditionError(
                    "The selected epoch window exceeds recording bounds for every "
                    "selected event. Shorten the EEG epoch window before continuing.",
                    diagnostics={"epoch_boundary_check": boundary_diagnostics},
                )
            if boundary_summary.excluded_ratio > EPOCH_BOUNDARY_AUTO_EXCLUDE_MAX_RATIO:
                raise PreconditionError(
                    "The selected epoch window would exclude "
                    f"{boundary_summary.excluded_event_count} of "
                    f"{boundary_summary.selected_event_count} selected events "
                    "because they are too close to a recording boundary. Shorten "
                    "the epoch window or review the selected events.",
                    diagnostics={"epoch_boundary_check": boundary_diagnostics},
                )
        if boundary_summary.excluded_event_count:
            self.preprocess.apply_epoching(
                command.baseline,
                event_ids,
                command.t_min,
                command.t_max,
                True,
                **epoch_options,
            )
        else:
            self.preprocess.apply_epoching(
                command.baseline,
                event_ids,
                command.t_min,
                command.t_max,
                **epoch_options,
            )
        message = f"Created EEG epochs from {command.t_min}s to {command.t_max}s."
        diagnostics: dict[str, Any] = {
            "epoch_boundary_check": boundary_diagnostics,
        }
        if boundary_summary.excluded_event_count:
            message += (
                f" Excluded {boundary_summary.excluded_event_count} boundary "
                "event(s) that could not contain the complete window."
            )
        applied = self._applied_deferred_normalization_count()
        if not applied and not boundary_summary.excluded_event_count:
            return message
        if not applied:
            return message, diagnostics
        diagnostics.update(
            {
                "normalization_scope": NORMALIZATION_SCOPE,
                "deferred_normalization_applied_count": applied,
                "recording_statistics_used": False,
            }
        )
        return (
            message,
            diagnostics,
        )

    def _event_ids_for_epoch_command(
        self,
        command: CreateEpochCommand,
        *,
        handoff: dict[str, Any],
    ) -> list[str] | dict[str, int] | None:
        if not handoff:
            return command.event_ids
        defaults = [
            str(item)
            for item in handoff.get("default_epoch_events", [])
            if str(item).strip()
        ]
        blockers = [
            str(item)
            for item in handoff.get("supervised_blockers", [])
            if str(item).strip()
        ]
        event_ids = command.event_ids
        if event_ids is None and blockers:
            raise PreconditionError("; ".join(blockers))
        if event_ids is None and defaults:
            return defaults
        explicit_targets: list[str] = []
        aliases = self._event_label_aliases(handoff)
        if isinstance(event_ids, (list, dict)):
            explicit_targets = [str(item) for item in event_ids]
        if explicit_targets and defaults:
            allowed = set(defaults) | set(aliases)
            missing = [item for item in explicit_targets if item not in allowed]
            if missing and bool(handoff.get("supervised_ready")):
                raise PreconditionError(
                    "EEG epoch target is not in the reviewed import labels: "
                    + ", ".join(str(item) for item in missing)
                    + ".",
                )
            if isinstance(event_ids, list):
                return [aliases.get(str(item), str(item)) for item in event_ids]
            if isinstance(event_ids, dict):
                return {
                    aliases.get(str(key), str(key)): int(value)
                    for key, value in event_ids.items()
                }
        return event_ids

    def _enforce_epoch_confirmation(
        self,
        command: CreateEpochCommand,
        *,
        epoch_context: Mapping[str, Any],
        effective_event_ids: list[str] | dict[str, int] | None,
    ) -> None:
        requirement = build_epoch_confirmation_requirement(
            epoch_context,
            t_min=command.t_min,
            t_max=command.t_max,
            event_ids=(
                command.event_ids
                if command.event_ids is not None
                else effective_event_ids
            ),
        )
        if requirement is None:
            return
        if hmac.compare_digest(
            str(command.confirmation_receipt or ""),
            str(requirement["receipt"]),
        ):
            return
        error = ConfirmationRequiredError(requirement["message"])
        error.diagnostics["confirmation_requirement"] = requirement
        raise error

    def _epoch_handoff(self) -> dict[str, Any]:
        try:
            state = self._get_state()
        except PreconditionError:
            raise
        except Exception as exc:
            raise self._epoch_handoff_precondition("state_read_failed") from exc

        return self._epoch_handoff_from_state(state)

    @classmethod
    def _epoch_handoff_from_state(
        cls,
        state: ApplicationStateSnapshot,
    ) -> dict[str, Any]:
        """Validate one already-admitted immutable application state."""

        if not isinstance(state, ApplicationStateSnapshot):
            raise cls._epoch_handoff_precondition("invalid_state")
        read_errors = state.read_errors
        if not isinstance(read_errors, list) or any(
            not isinstance(error, str) for error in read_errors
        ):
            raise cls._epoch_handoff_precondition("invalid_state")
        if state.state_reliable is not True or read_errors:
            raise cls._epoch_handoff_precondition("state_unreliable")
        if not isinstance(state.interpretation, InterpretationStateSnapshot):
            raise cls._epoch_handoff_precondition("invalid_state")
        try:
            return validated_epoch_handoff(state.interpretation.epoch_handoff)
        except (TypeError, ValueError) as exc:
            raise cls._epoch_handoff_precondition("invalid_handoff") from exc

    @staticmethod
    def _epoch_handoff_precondition(reason: str) -> PreconditionError:
        return PreconditionError(
            "Creating EEG epochs is unavailable because workflow state could not "
            "be verified.",
            diagnostics={"epoch_handoff_error": reason},
        )

    @staticmethod
    def _event_label_aliases(handoff: dict[str, Any]) -> dict[str, str]:
        raw_aliases = handoff.get("event_label_aliases")
        if not isinstance(raw_aliases, dict):
            return {}
        aliases: dict[str, str] = {}
        for event_name, label_name in raw_aliases.items():
            event_text = str(event_name).strip()
            label_text = str(label_name).strip()
            if event_text and label_text and event_text != label_text:
                aliases[label_text] = event_text
        return aliases

    @classmethod
    def _event_label_aliases_by_source(
        cls,
        handoff: dict[str, Any],
        preprocessed_data: list[Any],
    ) -> list[dict[str, str]] | None:
        """Resolve reviewed class names without flattening per-run semantics."""
        global_aliases = cls._normalized_event_label_aliases(
            handoff.get("event_label_aliases"),
        )
        aliases_by_source: list[dict[str, str]] = []
        source_semantics_resolved: list[bool] = []
        for data in preprocessed_data:
            source_aliases: dict[str, str] | None = None
            getter = getattr(data, "get_runtime_detail", None)
            if callable(getter):
                try:
                    hint = getter(EPOCH_HINT_KEY)
                except Exception as exc:
                    if handoff.get("run_dependent_mapping") is True:
                        raise PreconditionError(
                            "Creating EEG epochs is unavailable because reviewed "
                            "per-recording class labels could not be read."
                        ) from exc
                else:
                    if isinstance(hint, Mapping) and "event_label_aliases" in hint:
                        source_aliases = cls._normalized_event_label_aliases(
                            hint.get("event_label_aliases"),
                        )
            aliases_by_source.append(
                dict(source_aliases if source_aliases is not None else global_aliases)
            )
            source_semantics_resolved.append(
                bool(aliases_by_source[-1])
                or cls._source_events_are_already_semantic(data, handoff)
            )

        if handoff.get("run_dependent_mapping") is True and any(
            not resolved for resolved in source_semantics_resolved
        ):
            raise PreconditionError(
                "Creating EEG epochs is unavailable because reviewed per-recording "
                "class labels are incomplete. Review each run's event meanings again."
            )
        if not any(aliases_by_source):
            return None
        return aliases_by_source

    @staticmethod
    def _source_events_are_already_semantic(
        data: Any,
        handoff: Mapping[str, Any],
    ) -> bool:
        reviewed_labels = {
            str(label).strip()
            for label in handoff.get("usable_class_labels", [])
            if str(label).strip()
        }
        if not reviewed_labels:
            return False
        try:
            _events, event_id = data.get_event_list()
        except Exception:
            return False
        if not isinstance(event_id, Mapping):
            return False
        source_event_names = {
            str(name).strip() for name in event_id if str(name).strip()
        }
        unresolved_targets = {
            str(name).strip()
            for name in handoff.get("default_epoch_events", [])
            if str(name).strip() and str(name).strip() not in reviewed_labels
        }
        return bool(source_event_names & reviewed_labels) and not bool(
            source_event_names & unresolved_targets
        )

    @staticmethod
    def _normalized_event_label_aliases(value: object) -> dict[str, str]:
        if not isinstance(value, Mapping):
            return {}
        aliases: dict[str, str] = {}
        for raw_event, display_label in value.items():
            event_name = str(raw_event).strip()
            label_name = str(display_label).strip()
            if event_name and label_name and event_name != label_name:
                aliases[event_name] = label_name
        return aliases

    def _handle_standard_preprocess(self, command: PreprocessCommand) -> HandlerResult:
        low_freq = command.low_freq if command.low_freq is not None else 4
        high_freq = command.high_freq if command.high_freq is not None else 40
        reference: str | list[str] | None = None
        if command.channels:
            is_average = (
                len(command.channels) == 1 and command.channels[0].lower() == "average"
            )
            reference = "average" if is_average else list(command.channels)
        raw_count, epoch_count = self._normalization_target_counts()
        self.preprocess.apply_standard_pipeline(
            l_freq=low_freq,
            h_freq=high_freq,
            notch_freq=command.notch_freq,
            rate=command.rate,
            ref_channels=reference,
            normalization=command.method,
        )
        if command.method:
            message, diagnostics = self._normalization_result(
                command.method,
                raw_count=raw_count,
                epoch_count=epoch_count,
            )
            return (
                f"Standard preprocessing applied. {message}",
                diagnostics,
            )
        return "Standard preprocessing applied."

    def _normalization_target_counts(self) -> tuple[int, int]:
        data_list = self.preprocess.get_preprocessed_data_list()
        return self._normalization_target_counts_for(data_list)

    @staticmethod
    def _normalization_target_counts_for(
        data_list: Sequence[Any],
    ) -> tuple[int, int]:
        raw_count = sum(bool(data.is_raw()) for data in data_list)
        return raw_count, len(data_list) - raw_count

    @staticmethod
    def _normalization_result(
        method: str,
        *,
        raw_count: int,
        epoch_count: int,
    ) -> tuple[str, dict[str, Any]]:
        if raw_count and epoch_count:
            message = (
                f"Normalization using {method} was applied to {epoch_count} "
                f"epoched item(s) and queued for {raw_count} raw item(s)."
            )
        elif raw_count:
            message = (
                f"Normalization using {method} is queued for per-EEG-epoch "
                "application during EEG epoch creation."
            )
        else:
            message = (
                f"Normalized data using {method} independently within each EEG epoch."
            )
        return (
            message,
            {
                "normalization_method": method,
                "normalization_scope": NORMALIZATION_SCOPE,
                "raw_requests_deferred": raw_count,
                "epoched_items_normalized": epoch_count,
                "recording_statistics_used": False,
            },
        )

    def _applied_deferred_normalization_count(self) -> int:
        return self._applied_deferred_normalization_count_for(
            self.preprocess.get_preprocessed_data_list()
        )

    @staticmethod
    def _applied_deferred_normalization_count_for(
        data_list: Sequence[Any],
    ) -> int:
        applied = 0
        for data in data_list:
            get_detail = getattr(data, "get_runtime_detail", None)
            if not callable(get_detail):
                continue
            detail = get_detail(NORMALIZATION_RUNTIME_KEY)
            if (
                isinstance(detail, dict)
                and detail.get("status") == "applied"
                and detail.get("requested_on") == "raw"
                and detail.get("scope") == NORMALIZATION_SCOPE
            ):
                applied += 1
        return applied

    @staticmethod
    def _require(value: Any, name: str) -> Any:
        if value is None:
            raise PreconditionError(f"{name} is required.")
        return value
