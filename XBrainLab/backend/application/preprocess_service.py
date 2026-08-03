"""Preprocessing and epoch command handlers for the application command spine."""

from __future__ import annotations

import hmac
from collections.abc import Callable
from typing import Any

from XBrainLab.backend.preprocessor.normalize import (
    NORMALIZATION_RUNTIME_KEY,
    NORMALIZATION_SCOPE,
)
from XBrainLab.backend.preprocessor.time_epoch import summarize_epoch_boundaries
from XBrainLab.backend.services.dataset_state_service import DatasetChannelSelectionPort
from XBrainLab.backend.services.preprocess_state_service import PreprocessProductPort

from .commands import (
    ApplyMontageCommand,
    Command,
    CreateEpochCommand,
    PreprocessCommand,
    PreprocessOperation,
)
from .epoch_context import (
    build_epoch_confirmation_requirement,
    build_epoching_context,
    validated_epoch_handoff,
)
from .errors import ConfirmationRequiredError, PreconditionError
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
    ) -> None:
        self.preprocess = preprocess
        self.dataset = dataset
        self._get_state = get_state

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
        event_ids = self._event_ids_for_epoch_command(command, handoff=handoff)
        preprocessed_data = self.preprocess.get_preprocessed_data_list()
        self._enforce_epoch_confirmation(
            command,
            preprocessed_data=preprocessed_data,
            handoff=handoff,
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
        boundary_diagnostics = boundary_summary.to_diagnostics()
        if boundary_summary.excluded_event_count:
            if boundary_summary.remaining_event_count <= 0:
                raise PreconditionError(
                    "The selected epoch window exceeds recording bounds for every "
                    "selected event. Shorten the epoch window before creating epochs.",
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
            )
        else:
            self.preprocess.apply_epoching(
                command.baseline,
                event_ids,
                command.t_min,
                command.t_max,
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
        preprocessed_data: list[Any],
        handoff: dict[str, Any],
        effective_event_ids: list[str] | dict[str, int] | None,
    ) -> None:
        context = build_epoching_context(
            preprocessed_data,
            epoch_handoff=handoff,
        )
        requirement = build_epoch_confirmation_requirement(
            context,
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

        if not isinstance(state, ApplicationStateSnapshot):
            raise self._epoch_handoff_precondition("invalid_state")
        read_errors = state.read_errors
        if not isinstance(read_errors, list) or any(
            not isinstance(error, str) for error in read_errors
        ):
            raise self._epoch_handoff_precondition("invalid_state")
        if state.state_reliable is not True or read_errors:
            raise self._epoch_handoff_precondition("state_unreliable")
        if not isinstance(state.interpretation, InterpretationStateSnapshot):
            raise self._epoch_handoff_precondition("invalid_state")
        try:
            return validated_epoch_handoff(state.interpretation.epoch_handoff)
        except (TypeError, ValueError) as exc:
            raise self._epoch_handoff_precondition("invalid_handoff") from exc

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
        applied = 0
        for data in self.preprocess.get_preprocessed_data_list():
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
