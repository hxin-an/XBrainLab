"""Preprocessing and epoch command handlers for the application command spine."""

from __future__ import annotations

from typing import Any

from .commands import (
    Command,
    CreateEpochCommand,
    PreprocessCommand,
    PreprocessOperation,
)
from .errors import ConfirmationRequiredError, PreconditionError

HandlerResult = str | tuple[str, dict[str, Any]]


class PreprocessCommandService:
    """Handle preprocessing operations and epoch creation commands."""

    def __init__(
        self,
        *,
        preprocess: Any,
        dataset: Any,
        get_state: Any | None = None,
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
            self.preprocess.apply_normalization(method)
            return f"Normalized data using {method}."
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

    def handle_create_epoch(self, command: Command) -> HandlerResult:
        if not isinstance(command, CreateEpochCommand):
            raise TypeError("Invalid command for create_epoch")
        event_ids = self._event_ids_for_epoch_command(command)
        self.preprocess.apply_epoching(
            command.baseline,
            event_ids,
            command.t_min,
            command.t_max,
        )
        return f"Created epochs from {command.t_min}s to {command.t_max}s."

    def _event_ids_for_epoch_command(
        self,
        command: CreateEpochCommand,
    ) -> list[str] | dict[str, int] | None:
        handoff = self._epoch_handoff()
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
        if isinstance(event_ids, list | dict):
            explicit_targets = [str(item) for item in event_ids]
        if explicit_targets and defaults:
            missing = [item for item in explicit_targets if item not in set(defaults)]
            if missing and bool(handoff.get("supervised_ready")):
                raise PreconditionError(
                    "Epoch target is not in the reviewed import labels: "
                    + ", ".join(str(item) for item in missing)
                    + ".",
                )
        return event_ids

    def _epoch_handoff(self) -> dict[str, Any]:
        if not callable(self._get_state):
            return {}
        try:
            state = self._get_state()
        except Exception:
            return {}
        interpretation = getattr(state, "interpretation", None)
        handoff = getattr(interpretation, "epoch_handoff", None)
        return dict(handoff) if isinstance(handoff, dict) else {}

    def _handle_standard_preprocess(self, command: PreprocessCommand) -> HandlerResult:
        low_freq = command.low_freq if command.low_freq is not None else 4
        high_freq = command.high_freq if command.high_freq is not None else 40
        with self.preprocess.batch_notifications():
            self.preprocess.apply_filter(low_freq, high_freq, None)
            if command.notch_freq:
                self.preprocess.apply_filter(None, None, [command.notch_freq])
            if command.rate:
                self.preprocess.apply_resample(command.rate)
            if command.method:
                self.preprocess.apply_normalization(command.method)
        return "Standard preprocessing applied."

    @staticmethod
    def _require(value: Any, name: str) -> Any:
        if value is None:
            raise PreconditionError(f"{name} is required.")
        return value
