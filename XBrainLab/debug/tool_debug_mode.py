"""Debug tool call script loader and step-by-step executor.

This module provides classes to load a JSON-based debug script containing
pre-defined tool calls and replay them one at a time, enabling
interactive step-through debugging via the chat UI.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast

from XBrainLab.backend.utils.logger import logger
from XBrainLab.llm.tools.result_contract import safe_unexpected_failure

WALKTHROUGH_SCHEMA = "xbrainlab.tool_walkthrough.v1"
_WALKTHROUGH_TOP_LEVEL_FIELDS = frozenset({"schema", "title", "calls"})
_WALKTHROUGH_CALL_FIELDS = frozenset(
    {"id", "prompt", "tool", "params", "expected", "completion"}
)
_WALKTHROUGH_COMPLETIONS = frozenset(
    {"terminal", "confirmation", "ui_handoff", "training_terminal"}
)
_WALKTHROUGH_SOURCE_PLACEHOLDER = "${XBL_WALKTHROUGH_SOURCE}"
_WALKTHROUGH_SOURCE_DIR_PLACEHOLDER = "${XBL_WALKTHROUGH_SOURCE_DIR}"
_WALKTHROUGH_RECIPE_PLACEHOLDER = "${XBL_WALKTHROUGH_RECIPE}"


def _replace_walkthrough_tokens(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, str):
        for token, replacement in replacements.items():
            value = value.replace(token, replacement)
        return value
    if isinstance(value, list):
        return [_replace_walkthrough_tokens(item, replacements) for item in value]
    if isinstance(value, dict):
        return {
            key: _replace_walkthrough_tokens(item, replacements)
            for key, item in value.items()
        }
    return value


def _write_walkthrough_raw_fif(path: Path) -> None:
    """Create one small session-only EEG source suitable for CPU EEGNet."""
    import mne  # noqa: PLC0415 - only walkthrough profiles need the EEG fixture
    import numpy as np  # noqa: PLC0415 - keep ordinary debug loading lightweight

    sfreq = 128
    info = mne.create_info(
        ch_names=["C3", "C4", "Cz", "Pz"],
        sfreq=sfreq,
        ch_types="eeg",
    )
    data = np.random.default_rng(41).normal(scale=1e-6, size=(4, sfreq * 18))
    raw = mne.io.RawArray(data, info, verbose="ERROR")
    events = np.array(
        [[128 + index * 64, 0, 1 + index % 2] for index in range(24)],
        dtype=int,
    )
    raw.set_annotations(
        mne.annotations_from_events(
            events,
            sfreq=sfreq,
            event_desc={1: "left", 2: "right"},
        )
    )
    raw.save(path, overwrite=True, verbose="ERROR")


@dataclass(frozen=True)
class DebugToolCall:
    """Immutable representation of a single debug tool invocation.

    Attributes:
        tool: The name of the tool to execute (must match a key in
            ``ToolExecutor.TOOL_MAP``).
        params: Keyword arguments forwarded to the tool's ``execute`` method.

    """

    tool: str
    params: dict[str, Any]
    confirmed: bool = False
    authorization_text: str = ""
    step_id: str = ""
    prompt: str = ""
    expected: str = ""
    completion: str = "terminal"


class ToolDebugMode:
    """Manages the execution of a pre-defined tool call script for debugging.

    Loads a JSON debug script and yields one ``DebugToolCall`` at a time,
    allowing step-by-step execution triggered by pressing Enter in the
    chat UI.

    Attributes:
        script_path: Absolute or relative path to the JSON debug script.
        calls: Ordered list of raw call dictionaries loaded from the script.
        index: Zero-based position of the next call to return.

    """

    def __init__(self, script_path: str):
        """Initialise the debug mode and load the script.

        Args:
            script_path: Path to a JSON file containing a ``calls`` array.
                Each element must have a ``"tool"`` key and an optional
                ``"params"`` dictionary.

        """
        self.script_path = script_path
        self.calls: list[dict[str, Any]] = []
        self.index = 0
        self.schema = ""
        self.title = "Tool diagnostics"
        self.load_error = ""
        self._current_call: DebugToolCall | None = None
        self._session_directory: TemporaryDirectory[str] | None = None
        self._load_script()

    def _load_script(self) -> None:
        """Load and parse the JSON debug script into ``self.calls``.

        If the file does not exist or cannot be parsed, an error is logged
        and ``self.calls`` remains empty.
        """
        if not os.path.exists(self.script_path):
            logger.error("Debug script was not found.")
            return

        try:
            self._apply_script_data(self._read_script_data())
            logger.info("Loaded debug script with %d calls.", len(self.calls))
        except Exception as error:
            self.calls = []
            self.load_error = "The tool walkthrough file is invalid."
            safe_unexpected_failure(
                logger,
                error,
                boundary="tool_debug_script_loader",
                operation="load_script",
            )

    def _read_script_data(self) -> object:
        with open(self.script_path, encoding="utf-8") as script_file:
            return json.load(script_file)

    def _apply_script_data(self, data: object) -> None:
        if not isinstance(data, dict):
            raise ValueError("Debug script root must be an object.")
        schema = data.get("schema")
        if schema == WALKTHROUGH_SCHEMA:
            self._load_walkthrough(data)
            return
        calls = data.get("calls", [])
        if not isinstance(calls, list):
            raise ValueError("Debug script calls must be an array.")
        self.calls = calls

    def _load_walkthrough(self, data: dict[str, Any]) -> None:
        data = self._materialize_session_tokens(data)
        self.schema = WALKTHROUGH_SCHEMA
        unknown_top_level = set(data) - _WALKTHROUGH_TOP_LEVEL_FIELDS
        if unknown_top_level:
            raise ValueError("Tool walkthrough contains unknown top-level fields.")
        title = data.get("title")
        calls = data.get("calls")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("Tool walkthrough title must be a non-empty string.")
        if not isinstance(calls, list) or not calls:
            raise ValueError("Tool walkthrough calls must be a non-empty array.")
        step_ids: set[str] = set()
        validated: list[dict[str, Any]] = []
        for call in calls:
            if not isinstance(call, dict) or set(call) != _WALKTHROUGH_CALL_FIELDS:
                raise ValueError("Tool walkthrough call fields do not match v1.")
            step_id = call.get("id")
            prompt = call.get("prompt")
            tool = call.get("tool")
            params = call.get("params")
            expected = call.get("expected")
            completion = call.get("completion")
            if not all(
                isinstance(value, str) and value.strip()
                for value in (step_id, prompt, tool, expected, completion)
            ) or not isinstance(params, dict):
                raise ValueError("Tool walkthrough call values do not match v1.")
            step_id = cast(str, step_id)
            completion = cast(str, completion)
            if step_id in step_ids:
                raise ValueError("Tool walkthrough step IDs must be unique.")
            if completion not in _WALKTHROUGH_COMPLETIONS:
                raise ValueError("Tool walkthrough completion is not supported.")
            step_ids.add(step_id)
            validated.append(dict(call))
        self.title = title.strip()
        self.calls = validated

    def _materialize_session_tokens(self, data: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(data, ensure_ascii=False)
        if not any(
            token in encoded
            for token in (
                _WALKTHROUGH_SOURCE_PLACEHOLDER,
                _WALKTHROUGH_SOURCE_DIR_PLACEHOLDER,
                _WALKTHROUGH_RECIPE_PLACEHOLDER,
            )
        ):
            return data
        session = TemporaryDirectory(prefix="xbrainlab-tool-walkthrough-")
        self._session_directory = session
        source_path = Path(session.name) / "walkthrough_raw.fif"
        recipe_path = Path(session.name) / "walkthrough_recipe.json"
        _write_walkthrough_raw_fif(source_path)
        replacements = {
            _WALKTHROUGH_SOURCE_PLACEHOLDER: str(source_path),
            _WALKTHROUGH_SOURCE_DIR_PLACEHOLDER: str(source_path.parent),
            _WALKTHROUGH_RECIPE_PLACEHOLDER: str(recipe_path),
        }
        return _replace_walkthrough_tokens(data, replacements)

    @property
    def is_walkthrough(self) -> bool:
        return self.schema == WALKTHROUGH_SCHEMA

    @property
    def current_call(self) -> DebugToolCall | None:
        return self._current_call

    def begin_next(self) -> DebugToolCall | None:
        """Reserve the current step without consuming it before terminal."""
        if self._current_call is not None:
            return self._current_call
        if self.index >= len(self.calls):
            return None
        call = self._parse_call(self.calls[self.index])
        if call is not None:
            self._current_call = call
        return call

    def peek_next(self) -> DebugToolCall | None:
        """Return the current/upcoming step without reserving or consuming it."""
        if self._current_call is not None:
            return self._current_call
        if self.index >= len(self.calls):
            return None
        return self._parse_call(self.calls[self.index])

    def complete_current(self, outcome: str) -> None:
        """Advance exactly one reserved step after a correlated terminal."""
        if self._current_call is None:
            return
        if not isinstance(outcome, str) or not outcome.strip():
            raise ValueError("Tool walkthrough terminal outcome must be a string.")
        self._current_call = None
        self.index += 1

    def release_current(self) -> None:
        """Allow retry when host admission failed before a turn was created."""
        self._current_call = None

    def next_call(self) -> DebugToolCall | None:
        """Return the next tool call in the sequence.

        Advances the internal index by one each time it is called.

        Returns:
            A ``DebugToolCall`` containing the tool name and parameters,
            or ``None`` if all calls have been consumed.

        """
        if self.index >= len(self.calls):
            return None

        call_data = self.calls[self.index]
        call = self._parse_call(call_data)
        if call is not None:
            self.index += 1
        return call

    def _parse_call(self, call_data: object) -> DebugToolCall | None:
        if not isinstance(call_data, dict) or not isinstance(
            call_data.get("tool"),
            str,
        ):
            logger.error(
                "Invalid debug call entry at index %d.",
                self.index,
            )
            return None
        params = call_data.get("params", {})
        confirmed = call_data.get("confirmed", False)
        authorization_text = call_data.get("authorization_text", "")
        if (
            not isinstance(params, dict)
            or type(confirmed) is not bool
            or not isinstance(authorization_text, str)
        ):
            logger.error(
                "Invalid debug call contract at index %d.",
                self.index,
            )
            return None
        if self.is_walkthrough:
            return DebugToolCall(
                tool=call_data["tool"],
                params=dict(params),
                authorization_text=call_data["prompt"],
                step_id=call_data["id"],
                prompt=call_data["prompt"],
                expected=call_data["expected"],
                completion=call_data["completion"],
            )
        return DebugToolCall(
            tool=call_data["tool"],
            params=dict(params),
            confirmed=confirmed,
            authorization_text=authorization_text,
        )

    @property
    def is_complete(self) -> bool:
        """Whether all calls in the debug script have been consumed.

        Returns:
            ``True`` if the internal index has reached or exceeded the
            total number of calls; ``False`` otherwise.

        """
        return self.index >= len(self.calls) and self._current_call is None
