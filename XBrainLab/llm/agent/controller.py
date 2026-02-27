"""Central LLM agent controller.

Orchestrates conversation management, the ReAct reasoning loop, tool
execution, and communication between the UI layer and the backend
worker thread.
"""

import json
import logging
import re
import threading
import time as _time
from collections import deque
from typing import Any

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from XBrainLab.llm.pipeline_state import (
    STAGE_CONFIG,
    PipelineStage,
    compute_pipeline_stage,
)
from XBrainLab.llm.rag import RAGRetriever
from XBrainLab.llm.tools import AVAILABLE_TOOLS
from XBrainLab.llm.tools.tool_registry import ToolRegistry

from .assembler import ContextAssembler
from .confidence import estimate_confidence
from .conversation import ConversationHistory
from .metrics import AgentMetricsTracker
from .parser import CommandParser
from .verifier import VerificationLayer
from .worker import AgentWorker

logger = logging.getLogger(__name__)


class LLMController(QObject):
    """Central controller for the LLM agent.

    Manages conversation history with a sliding window, drives the ReAct
    reasoning loop (parse → verify → execute → feedback), and bridges
    UI signals with the background ``AgentWorker``.

    Attributes:
        study: The application Study object providing experiment state.
        registry: Tool registry holding all registered tools.
        assembler: Context assembler for building system prompts.
        verifier: Verification layer for validating tool calls.
        rag_retriever: RAG retriever for augmenting prompts with examples.
        worker_thread: Background QThread running the AgentWorker.
        worker: AgentWorker performing LLM inference.
        history: List of message dicts representing conversation history.
        current_response: Accumulated text of the current LLM response.
        is_processing: Flag indicating whether a generation is in progress.

    """

    # Signals to UI
    response_ready = pyqtSignal(str, str)  # sender, text
    chunk_received = pyqtSignal(str)  # New signal for streaming
    generation_started = pyqtSignal()  # New signal for UI prep
    processing_finished = pyqtSignal()  # ROBUST: New signal for UI to stop spinner
    status_update = pyqtSignal(str)  # status message
    error_occurred = pyqtSignal(str)  # error message
    request_user_interaction = pyqtSignal(str, dict)  # command, params
    remove_content = pyqtSignal(str)  # New signal to hide JSON

    # Internal signals to Worker
    sig_initialize = pyqtSignal()  # Simple signal, no args
    sig_generate = pyqtSignal(list)
    sig_reinit = pyqtSignal(str)  # M3.4: Re-init signal

    MAX_HISTORY = 20

    def __init__(self, study):
        """Initializes the LLMController.

        Sets up the tool registry, context assembler, verification layer,
        RAG retriever, and background worker thread.

        Args:
            study: The application Study object providing experiment context.

        """
        super().__init__()
        self.study = study

        # Initialize Tool Registry & Assembler
        self.registry = ToolRegistry()
        for tool in AVAILABLE_TOOLS:
            self.registry.register(tool)

        self.assembler = ContextAssembler(self.registry, self.study)
        self.verifier = VerificationLayer()  # Default confidence threshold

        # Initialize RAG Retriever
        self.rag_retriever = RAGRetriever()

        # Setup Worker in separate thread to avoid blocking UI during load/inference
        self.worker_thread = QThread()
        self.worker = AgentWorker()
        self.worker.moveToThread(self.worker_thread)

        self._conversation = ConversationHistory(max_size=self.MAX_HISTORY)

        # Connect worker signals
        self.worker.chunk_received.connect(self._on_chunk_received)
        self.worker.finished.connect(self._on_generation_finished)
        self.worker.error.connect(self._on_worker_error)
        self.worker.log.connect(self.status_update)

        # Connect control signals
        self.sig_initialize.connect(self.worker.initialize_agent)
        self.sig_generate.connect(self.worker.generate_from_messages)
        self.sig_reinit.connect(self.worker.reinitialize_agent)  # M3.4

        # Start thread
        self.worker_thread.start()

        self.current_response = ""
        self.is_processing = False
        self._emitted_len = 0
        self._is_buffering = False

        # Metrics tracker
        self.metrics = AgentMetricsTracker()

        # Robustness State
        self._recent_tool_calls: deque = deque(maxlen=10)
        self._retry_count = 0
        self._max_retries = 2

        # Tool Failure Loop Protection
        self._tool_failure_count = 0
        self._max_tool_failures = 3
        self._loop_break_count = 0
        self._max_loop_breaks = 3

        # HITL: Pending confirmation state
        self._pending_confirmation: (
            tuple[str, dict, list[tuple[str, dict]], str, float] | None
        ) = None

    def initialize(self):
        """Initializes the underlying worker engine and RAG retriever.

        Emits the initialization signal to the worker thread and starts
        RAG initialization in a separate daemon thread.
        """
        self.sig_initialize.emit()

        # Start RAG initialization in a separate thread to not block UI
        # This will run in parallel with the LLM loading (which is in worker thread)
        threading.Thread(target=self.rag_retriever.initialize, daemon=True).start()

    @property
    def history(self):
        """list: Backward-compatible accessor for conversation messages."""
        return self._conversation.messages

    @history.setter
    def history(self, value):
        self._conversation.messages = value

    def _append_history(self, role: str, content: str):
        """Appends a message to history and prunes to the sliding window.

        Args:
            role: Message role (``'user'``, ``'assistant'``, or ``'system'``).
            content: The message text.

        """
        self._conversation.append(role, content)

    def handle_user_input(self, text: str):
        """Entry point for user input from the UI.

        Appends the user message to history, retrieves RAG context, and
        triggers LLM generation.  Ignores empty input or input received
        while the agent is already processing.

        Args:
            text: The user's input text.

        """
        if not text.strip():
            return

        # RACE CONDITION FIX: Prevent re-entry if already generating or loading
        if self.is_processing:
            logger.warning("User input ignored - Agent is busy.")
            return

        self.is_processing = True
        self.status_update.emit("Thinking...")

        # Start metrics for this turn
        turn = self.metrics.start_turn()
        turn.input_chars += len(text)

        try:
            # 1. Update History
            self._append_history("user", text)

            # Reset retry counters for new turn
            self._retry_count = 0
            self._tool_failure_count = 0
            self._loop_break_count = 0

            # 2. Retrieve RAG Context (Examples)
            features = self.rag_retriever.get_similar_examples(text)
            self.assembler.clear_context()
            if features:
                self.assembler.add_context(features)

            # 3. Start Generation Loop
            self._generate_response()
        except Exception as e:
            logger.error("Error in handle_user_input: %s", e)
            self.metrics.finish_turn()
            self.error_occurred.emit(str(e))
            self.is_processing = False
            self.processing_finished.emit()

    def _generate_response(self):
        """Triggers LLM generation based on the current history.

        Builds the full message list via the assembler, resets the
        response accumulator, and emits signals to the worker thread.
        """
        # Use Assembler to construct messages (Dynamic Prompting)
        messages = self.assembler.get_messages(self.history)
        self.current_response = ""  # Reset accumulator
        self._emitted_len = 0  # Track what we sent to UI
        self._is_buffering = False

        # Track LLM call metrics
        if self.metrics.current_turn:
            self.metrics.current_turn.llm_calls += 1
            self.metrics.current_turn.input_chars += sum(
                len(m.get("content", "")) for m in messages
            )

        # Update status and Start Bubble
        self.status_update.emit("Generating response...")
        self.generation_started.emit()

        # Call worker via signal
        self.sig_generate.emit(messages)

    def _on_chunk_received(self, chunk: str):
        """Accumulates a streaming chunk and forwards it to the UI.

        Implements speculative buffering: the first few characters are
        held back to detect tool-call JSON signatures before deciding
        whether to stream or suppress the output.

        Args:
            chunk: A text fragment received from the LLM generation stream.

        """
        self.current_response += chunk

        # Track output chars
        if self.metrics.current_turn:
            self.metrics.current_turn.output_chars += len(chunk)

        # Heuristic: Determine if we should buffer (hide) this output
        # 1. Start of message: Wait a bit to check for '{' or 'Request:'
        if len(self.current_response) < 10:
            # Buffer the first few chars to identify tool calls vs text
            return

        # 2. Check for Tool Signatures
        stripped = self.current_response.strip()
        is_tool_start = stripped.startswith(("{", "Request:"))
        has_tool_block = (
            "```json" in self.current_response or "```python" in self.current_response
        )

        if is_tool_start or has_tool_block:
            self._is_buffering = True

        # 3. Stream or Buffer
        if not self._is_buffering:
            # Emit only the NEW part
            to_emit = self.current_response[self._emitted_len :]
            if to_emit:
                self.chunk_received.emit(to_emit)
                self._emitted_len += len(to_emit)
        else:
            # We are buffering (hiding) potential tool output
            pass

    def _on_generation_finished(self):
        """Handles completion of one LLM generation turn.

        Parses the accumulated response for tool commands, retries on
        broken JSON, or finalizes the turn if no commands are found.
        """
        response_text = self.current_response.strip()

        # Flush buffer if we detained text thinking it was a tool, but it's not
        # (yet validated) Actually, wait until we confirm it's NOT a tool.

        command_result = CommandParser.parse(response_text)

        # 1. broken JSON check
        if self._handle_json_broken_retry(response_text, command_result):
            return

        # 2. Process Result
        if command_result:
            self._retry_count = 0  # Reset on success
            self._process_tool_calls(command_result, response_text)
        else:
            # Not a tool call. Ensure we emitted everything to the UI.
            to_emit = self.current_response[self._emitted_len :]
            if to_emit:
                self.chunk_received.emit(to_emit)
                self._emitted_len += len(to_emit)

            self._finalize_turn(response_text)

    def _handle_json_broken_retry(
        self,
        response_text: str,
        command_result: Any,
    ) -> bool:
        """Checks for broken JSON output and triggers a retry if needed.

        If the response looks like a JSON tool call but failed parsing,
        appends an error hint to history and re-triggers generation up to
        ``_max_retries`` times.

        Args:
            response_text: The full accumulated LLM response.
            command_result: The result from ``CommandParser.parse``, or
                ``None`` if parsing failed.

        Returns:
            ``True`` if a retry was triggered (caller should return early),
            ``False`` otherwise.

        """
        if command_result:
            return False

        # Fragile check refactoring:
        # Check if it looks like JSON/Code but failed parsing
        has_code_block = "```json" in response_text or "```python" in response_text
        has_braces = response_text.strip().startswith("{") and "}" in response_text

        if (has_code_block or has_braces) and self._retry_count < self._max_retries:
            logger.warning("Broken JSON/Code detected. Retrying...")
            # Hide the broken JSON from UI
            self.remove_content.emit(response_text)

            self._retry_count += 1
            self._append_history("assistant", response_text)

            err_msg = (
                "System: Your last output contained broken JSON or Code. "
                "Please ensure you output VALID JSON inside ```json``` blocks only."
            )
            self._append_history("user", err_msg)
            self.status_update.emit("Invalid JSON, retrying...")
            self._generate_response()
            return True
        if self._retry_count >= self._max_retries:
            logger.error("Max retries reached for JSON error.")

        return False

    def _process_tool_calls(self, command_result: Any, response_text: str):
        """Iterates through parsed commands and executes them.

        Verifies each command via the verification layer, executes valid
        calls, feeds tool output back into history, and decides whether
        to retry on failure or finalize the turn on success.

        Args:
            command_result: Parsed command(s) from ``CommandParser.parse``.
            response_text: The raw LLM response text (used for UI hiding).

        """
        commands = (
            command_result if isinstance(command_result, list) else [command_result]
        )

        # Hide the raw JSON from the UI now that we've parsed it
        self.remove_content.emit(response_text)

        self._append_history("assistant", response_text)

        # Track if any tool failed during this batch
        has_failure = False

        # Heuristic confidence for the whole batch
        confidence = estimate_confidence(response_text, commands)
        logger.debug("Heuristic confidence: %.2f", confidence)

        for cmd, params in commands:
            # --- Loop Detection ---

            # Use sort_keys=True for stable string representation of params
            try:
                params_str = json.dumps(params, sort_keys=True)
            except (TypeError, ValueError):
                # Fallback for non-serializable objects (rare for parsed tool output)
                logger.debug("Non-serializable tool params, using str()", exc_info=True)
                params_str = str(params)
            call_signature = (cmd, params_str)
            self._recent_tool_calls.append(call_signature)

            if self._detect_loop(call_signature):
                self._handle_loop_detected(cmd)
                return

            # --- Verification Layer ---
            validation = self.verifier.verify_tool_call(
                (cmd, params),
                confidence=confidence,
            )

            if not validation.is_valid:
                logger.warning(
                    "Tool rejected by Verifier: %s",
                    validation.error_message,
                )
                self.status_update.emit(f"Blocked: {validation.error_message}")
                self._append_history(
                    "user",
                    f"System: Tool call REJECTED: {validation.error_message}",
                )
                has_failure = True  # Treat as failure to trigger retry loop
                # Do not execute remaining commands — let LLM fix.
                break

            self.status_update.emit(f"Executing: {cmd}...")

            # --- HITL: Dangerous Action Confirmation ---
            tool = self.registry.get_tool(cmd)
            if tool and tool.requires_confirmation:
                # Store remaining commands for resumption after confirmation
                remaining = [
                    (c, p) for c, p in commands[commands.index((cmd, params)) + 1 :]
                ]
                self._pending_confirmation = (
                    cmd,
                    params,
                    remaining,
                    response_text,
                    confidence,
                )
                self.status_update.emit(f"Waiting for confirmation: {cmd}")
                self.request_user_interaction.emit(
                    "confirm_action",
                    {
                        "tool_name": cmd,
                        "params": params,
                        "description": tool.description,
                    },
                )
                return  # Pause — wait for user response

            # Execute Tool
            _success, result = self._execute_tool_no_loop(cmd, params)

            if not _success:
                has_failure = True

            # Handle Side Effects
            self._handle_tool_result_logic(result, _success)

            # Feed result back to History
            self._append_history("user", f"Tool Output: {result}")

        # Intelligent Continuation Strategy:
        # 1. If FAILURE occurred: Auto-trigger loop to allow Agent to self-correct.
        # 2. If SUCCESS: Stop and wait for user (prevent runaway).

        if has_failure:
            self._tool_failure_count += 1
            if self._tool_failure_count >= self._max_tool_failures:
                msg = "System: Max tool execution retries exceeded. Stopping."
                self._append_history("user", msg)
                self.status_update.emit("Max retries exceeded, stopping.")
                self._finalize_turn_after_tool()
            else:
                logger.info(
                    "Tool failure detected (Attempt %d/%d), retrying...",
                    self._tool_failure_count,
                    self._max_tool_failures,
                )
                self._generate_response()
        else:
            self._tool_failure_count = 0  # Reset on success
            self._finalize_turn_after_tool()

    def _finalize_turn_after_tool(self):
        """Finalizes the turn after tool execution.

        Stops generation and signals the UI that the agent is ready for
        new input (Safe Mode — does not auto-generate follow-up text).
        """
        self.metrics.finish_turn()
        self.status_update.emit("Ready")
        self.is_processing = False
        self.processing_finished.emit()

    def on_user_confirmed(self, approved: bool):
        """Resume tool execution after a HITL confirmation dialog.

        Called by the UI when the user accepts or rejects a dangerous
        action that was gated by ``requires_confirmation``.

        Args:
            approved: ``True`` if the user confirmed the action,
                ``False`` if they cancelled.

        """
        if not self._pending_confirmation:
            logger.warning("on_user_confirmed called with no pending action")
            return

        cmd, params, _remaining, _resp_text, _confidence = self._pending_confirmation
        self._pending_confirmation = None

        if approved:
            logger.info("User confirmed dangerous action: %s", cmd)
            self.status_update.emit(f"Executing confirmed: {cmd}...")

            _success, result = self._execute_tool_no_loop(cmd, params)
            self._handle_tool_result_logic(result, _success)
            self._append_history("user", f"Tool Output: {result}")

            if not _success:
                self._tool_failure_count += 1
                if self._tool_failure_count >= self._max_tool_failures:
                    msg = "System: Max tool execution retries exceeded. Stopping."
                    self._append_history("user", msg)
                    self.status_update.emit("Max retries exceeded, stopping.")
                    self._finalize_turn_after_tool()
                else:
                    self._generate_response()
            else:
                self._tool_failure_count = 0
                self._finalize_turn_after_tool()
        else:
            logger.info("User rejected dangerous action: %s", cmd)
            self._append_history(
                "user",
                f"System: User rejected '{cmd}'. Action was NOT executed.",
            )
            self.status_update.emit("Action cancelled by user.")
            self._finalize_turn_after_tool()

    def _handle_loop_detected(self, cmd: str):
        """Handles detection of a repeated tool-call loop.

        Injects a system message into history informing the LLM of the
        loop and re-triggers generation to break the cycle.

        Args:
            cmd: The tool name that was called repeatedly.

        """
        self._loop_break_count += 1
        if self._loop_break_count >= self._max_loop_breaks:
            msg = (
                f"System: Persistent loop detected for '{cmd}'. "
                "Aborting to prevent infinite recursion."
            )
            self._append_history("user", msg)
            self.metrics.finish_turn()
            self.status_update.emit("Loop detected, aborting.")
            self.is_processing = False
            self.processing_finished.emit()
            return

        msg = (
            f"System: Loop detected. You have called '{cmd}' "
            "with these params multiple times. Stop."
        )
        self._append_history("user", msg)
        self.status_update.emit("Loop detected, interrupting...")
        self._generate_response()

    def _finalize_turn(self, response_text: str):
        """Finalizes the turn when no tool commands are present.

        Appends the assistant response to history and emits the
        ``processing_finished`` signal.

        Args:
            response_text: The assistant's final response text.

        """
        self._append_history("assistant", response_text)
        self.metrics.finish_turn()
        self.status_update.emit("Ready")
        self.is_processing = False
        self.processing_finished.emit()

    def _execute_tool_no_loop(self, command_name, params):
        """Executes a single tool call without triggering generation.

        Performs a pipeline-stage gate check before execution to reject
        tool calls that are not allowed in the current stage.

        Args:
            command_name: Name of the tool to execute.
            params: Dictionary of parameters to pass to the tool.

        Returns:
            A ``(success, result_str)`` tuple where *success* is a bool
            and *result_str* is the tool's output or an error message.

        """
        tool = self.registry.get_tool(command_name)
        if tool:
            # --- Execution-time pipeline gate ---
            stage = compute_pipeline_stage(self.study)
            config = STAGE_CONFIG.get(stage)
            if config is None:
                config = STAGE_CONFIG.get(PipelineStage.EMPTY, {"tools": []})
            if command_name not in config["tools"]:
                gate_msg = (
                    f"Tool '{command_name}' is not available in the current "
                    f"pipeline stage '{stage.value}'. "
                    f"Allowed tools: {config['tools']}"
                )
                logger.warning(gate_msg)
                if self.metrics.current_turn:
                    self.metrics.current_turn.record_tool(
                        command_name,
                        False,
                        0,
                        gate_msg,
                    )
                self.status_update.emit(f"Blocked: {gate_msg}")
                return False, f"Error: {gate_msg}"

            t0 = _time.monotonic()
            try:
                result = tool.execute(self.study, **params)
            except Exception as e:
                elapsed = (_time.monotonic() - t0) * 1000
                error_msg = f"Tool execution failed: {e}"
                if self.metrics.current_turn:
                    self.metrics.current_turn.record_tool(
                        command_name,
                        False,
                        elapsed,
                        str(e),
                    )
                self.status_update.emit(error_msg)
                return False, error_msg
            else:
                elapsed = (_time.monotonic() - t0) * 1000
                if self.metrics.current_turn:
                    self.metrics.current_turn.record_tool(
                        command_name,
                        True,
                        elapsed,
                    )
                return True, result
        else:
            if self.metrics.current_turn:
                self.metrics.current_turn.record_tool(
                    command_name,
                    False,
                    0,
                    "unknown tool",
                )
            self.status_update.emit(f"Unknown tool: {command_name}")
            return False, f"Error: Unknown tool '{command_name}'"

    def _detect_loop(self, current_call_signature) -> bool:
        """Checks whether the same tool call has been made excessively.

        Args:
            current_call_signature: A ``(cmd_name, params_str)`` tuple
                uniquely identifying the tool call.

        Returns:
            ``True`` if the signature appears 3 or more times in the
            recent call history.

        """
        count = 0
        for call in self._recent_tool_calls:
            if call == current_call_signature:
                count += 1
        return count >= 3

    def _handle_tool_result_logic(self, result: str, success: bool = True) -> bool:
        """Processes tool output for UI side effects.

        Detects special ``Request:`` prefixed results (e.g. panel switches,
        montage confirmations) and emits the appropriate interaction
        signals to the UI.

        Args:
            result: The tool's output string.
            success: Whether the tool execution was successful.

        Returns:
            ``True`` if the result triggered a UI interaction signal,
            ``False`` otherwise.

        """
        if result.startswith("Request:"):
            # Format: "Request: CMD params... (View: view_mode)"
            # Example: "Request: Switch UI to 'visualization' (View: 3d_plot)"

            cmd_part = result.replace("Request:", "").strip()

            if cmd_part.lower().startswith("switch ui to"):
                # Use regex to robustly capture panel name and optional view mode
                # Matches: Switch UI to 'panel' OR Switch UI to 'panel' (View: view)
                pattern = r"Switch UI to ['\"](\w+)['\"](?:\s+\(View:\s+(\w+)\))?"
                match = re.match(pattern, cmd_part, re.IGNORECASE)

                if match:
                    panel = match.group(1)
                    view_mode = match.group(2)  # None if not present

                    self.request_user_interaction.emit(
                        "switch_panel",
                        {"panel": panel, "view_mode": view_mode},
                    )
                    return True

            # Handle confirm_montage requests
            if "confirm_montage" in cmd_part.lower():
                # Extract montage name: "confirm_montage 'standard_1020'"
                pattern = r"confirm_montage\s+['\"](\w+)['\"]"
                montage_match = re.search(pattern, cmd_part, re.IGNORECASE)
                montage_name = montage_match.group(1) if montage_match else None

                self.status_update.emit("Waiting for user to confirm montage...")
                self.request_user_interaction.emit(
                    "confirm_montage",
                    {"montage_name": montage_name, "context": cmd_part},
                )
                return True

        if not result.startswith("Request:") and not success:
            # Only report as System Error if the tool actually failed
            self.response_ready.emit("System", f"Tool Error: {result}")
        return False

    def _on_worker_error(self, error_msg):
        """Handle a fatal worker error by notifying the UI.

        Finishes the current metrics turn and resets processing state.

        Args:
            error_msg: Human-readable error description from the worker.

        """
        self.metrics.finish_turn()
        self.error_occurred.emit(error_msg)
        self.status_update.emit("Error")
        self.is_processing = False
        self.processing_finished.emit()

    def close(self):
        """Shuts down the worker thread and cleans up resources."""
        if hasattr(self, "rag_retriever") and self.rag_retriever:
            try:
                self.rag_retriever.close()
            except Exception:
                logger.debug("RAG retriever cleanup failed", exc_info=True)
        if hasattr(self, "worker_thread") and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait()

    def stop_generation(self):
        """Stops the current generation process and resets processing state."""
        if self.is_processing:
            self.status_update.emit("Stopping...")
            self.metrics.finish_turn()
            self.is_processing = False
            # Signal the generation thread (not worker thread) to stop
            if (
                self.worker.generation_thread
                and self.worker.generation_thread.isRunning()
            ):
                self.worker.generation_thread.requestInterruption()
            self.processing_finished.emit()

    def set_model(self, model_display_name: str):
        """Switches the active LLM model.

        Args:
            model_display_name: Display name or identifier of the model
                to switch to (e.g. ``'Gemini'``, ``'Local'``).

        """
        # Map Display Name to Model ID
        # "Gemini", "Local"
        # We pass these directly to worker.reinitialize_agent which now handles logic
        _mode_id = model_display_name

        self.status_update.emit(f"Switching mode to: {model_display_name}")
        self.sig_reinit.emit(_mode_id)

    def reset_conversation(self):
        """Resets conversation history and all internal state counters."""
        self._conversation.clear()
        self.current_response = ""
        self._retry_count = 0
        self._tool_failure_count = 0
        self._loop_break_count = 0
        self._recent_tool_calls.clear()
        self._pending_confirmation = None

        # Reset metrics for new conversation
        self.metrics.reset()

        # Clear Assembler context as well
        self.assembler.clear_context()

        self.status_update.emit("Conversation reset.")

    def execute_debug_tool(self, tool_name: str, params: dict):
        """Executes a tool directly, bypassing LLM generation.

        Used by Debug Mode to invoke tools manually.  The call and its
        result are recorded in conversation history.

        Args:
            tool_name: Name of the tool to execute.
            params: Dictionary of parameters for the tool.

        """
        logger.info("Debug Execution: %s with %s", tool_name, params)

        self.is_processing = True
        self.status_update.emit(f"Debug: Executing {tool_name}...")

        # Show Tool Call in chat (so user can see what was requested)
        params_str = json.dumps(params, indent=2, ensure_ascii=False)
        call_msg = f"Tool Call: {tool_name}\nParams: {params_str}"
        self._append_history("user", f"[DEBUG] {call_msg}")
        self.response_ready.emit("Debug", call_msg)

        success, result = self._execute_tool_no_loop(tool_name, params)

        # Handle Side Effects (UI Switching etc)
        self._handle_tool_result_logic(result, success)

        # Show Output
        msg = f"Tool Output: {result}"
        self._append_history("assistant", msg)
        self.response_ready.emit("System", msg)

        self.status_update.emit("Ready")
        self.is_processing = False
        self.processing_finished.emit()
