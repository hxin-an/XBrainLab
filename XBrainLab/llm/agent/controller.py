import logging
import threading
from collections import deque
from typing import Any

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from XBrainLab.llm.rag import RAGRetriever
from XBrainLab.llm.tools import AVAILABLE_TOOLS, get_tool_by_name

from .parser import CommandParser
from .prompt_manager import PromptManager
from .worker import AgentWorker

logger = logging.getLogger(__name__)


class LLMController(QObject):
    """
    Central controller for the LLM Agent.
    Manages conversation history, ReAct loop, and tool execution.
    Separates logic from UI (MainWindow) and Generation (AgentWorker).
    """

    # Signals to UI
    response_ready = pyqtSignal(str, str)  # sender, text
    chunk_received = pyqtSignal(str)  # New signal for streaming
    generation_started = pyqtSignal()  # New signal for UI prep
    status_update = pyqtSignal(str)  # status message
    error_occurred = pyqtSignal(str)  # error message
    request_user_interaction = pyqtSignal(str, dict)  # command, params
    remove_content = pyqtSignal(str)  # New signal to hide JSON

    # Internal signals to Worker
    sig_initialize = pyqtSignal()  # Simple signal, no args
    sig_generate = pyqtSignal(list)

    def __init__(self, study):
        super().__init__()
        self.study = study

        # Initialize PromptManager
        self.prompt_manager = PromptManager(AVAILABLE_TOOLS)

        # Initialize RAG Retriever
        self.rag_retriever = RAGRetriever()

        # Setup Worker in separate thread to avoid blocking UI during load/inference
        self.worker_thread = QThread()
        self.worker = AgentWorker()
        self.worker.moveToThread(self.worker_thread)

        self.history = []  # List of {"role": str, "content": str}

        # Connect worker signals
        self.worker.chunk_received.connect(self._on_chunk_received)
        self.worker.finished.connect(self._on_generation_finished)
        self.worker.error.connect(self._on_worker_error)
        self.worker.log.connect(self.status_update)

        # Connect control signals
        self.sig_initialize.connect(self.worker.initialize_agent)
        self.sig_generate.connect(self.worker.generate_from_messages)

        # Start thread
        self.worker_thread.start()

        self.current_response = ""
        self.is_processing = False

        # Robustness State
        # Robustness State
        self._recent_tool_calls: deque = deque(maxlen=10)
        self._retry_count = 0
        self._max_retries = 2

        # Tool Failure Loop Protection
        self._tool_failure_count = 0
        self._max_tool_failures = 3

    def initialize(self):
        """Initialize the underlying worker/engine."""
        self.sig_initialize.emit()

        # Start RAG initialization in a separate thread to not block UI
        # This will run in parallel with the LLM loading (which is in worker thread)
        threading.Thread(target=self.rag_retriever.initialize, daemon=True).start()

    def _append_history(self, role: str, content: str):
        """Append to history and prune if necessary."""
        self.history.append({"role": role, "content": content})

        # Sliding Window: Keep last N turns
        # N=20 means 10 user-sys pairs roughly
        max_history = 20
        if len(self.history) > max_history:
            # Keep index 0 (system prompt implied? No, prompt_manager handles system)
            # If we just slice, we might lose context.
            # Ideally we keep a summary. For now, simple sliding window.
            self.history = self.history[-max_history:]

    def handle_user_input(self, text: str):
        """Entry point for user input from UI."""
        if not text.strip():
            return

        self.is_processing = True
        self.status_update.emit("Thinking...")

        # 1. Update History
        self._append_history("user", text)

        # Reset retry counters for new turn
        self._retry_count = 0
        self._tool_failure_count = 0

        # 2. Retrieve RAG Context (Examples)
        features = self.rag_retriever.get_similar_examples(text)
        self.prompt_manager.clear_context()
        if features:
            self.prompt_manager.add_context(features)
            # Log for debugging (optional), visible in tool output usually
            # self.status_update.emit("Context retrieved for query.")

        # 3. Start Generation Loop
        self._generate_response()

    def _generate_response(self):
        """Triggers the LLM generation based on current history."""
        # Use PromptManager to construct messages
        messages = self.prompt_manager.get_messages(self.history)
        self.current_response = ""  # Reset accumulator
        self._emitted_len = 0  # Track what we sent to UI
        self._is_buffering = False

        # Update status and Start Bubble
        self.status_update.emit("Generating response...")
        self.generation_started.emit()

        # Call worker via signal
        self.sig_generate.emit(messages)

    def _on_chunk_received(self, chunk: str):
        """Accumulate chunk and stream to UI with speculative buffering."""
        self.current_response += chunk

        # Heuristic: Determine if we should buffer (hide) this output
        # 1. Start of message: Wait a bit to check for '{' or 'Request:'
        if len(self.current_response) < 10:
            # Buffer the first few chars to identify tool calls vs text
            return

        # 2. Check for Tool Signatures
        stripped = self.current_response.strip()
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
        """Called when LLM finishes generating one turn."""
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
        self, response_text: str, command_result: Any
    ) -> bool:
        """
        Checks if output looks like broken JSON and triggers retry.
        Returns True if retry was triggered (caller should return).
        """
        if command_result:
            return False

        # Simple heuristic: contains braces or code blocks but parser failed
        if "```" in response_text or ("{" in response_text and "}" in response_text):
            if self._retry_count < self._max_retries:
                logger.warning("Broken JSON detected. Retrying...")
                # Hide the broken JSON from UI
                self.remove_content.emit(response_text)

                self._retry_count += 1
                self._append_history("assistant", response_text)

                err_msg = (
                    "System: Your last output contained broken JSON. "
                    "Please check your syntax and output VALID JSON only."
                )
                self._append_history("user", err_msg)
                self.status_update.emit("Invalid JSON, retrying...")
                self._generate_response()
                return True
            else:
                logger.error("Max retries reached for JSON error.")

        return False

    def _process_tool_calls(self, command_result: Any, response_text: str):
        """Iterates through parsed commands and executes them."""
        commands = (
            command_result if isinstance(command_result, list) else [command_result]
        )

        # Hide the raw JSON from the UI now that we've parsed it
        self.remove_content.emit(response_text)

        self._append_history("assistant", response_text)

        # Track if any tool failed during this batch
        has_failure = False

        for cmd, params in commands:
            # --- Loop Detection ---
            call_signature = (cmd, str(params))
            self._recent_tool_calls.append(call_signature)

            if self._detect_loop(call_signature):
                self._handle_loop_detected(cmd)
                return

            self.status_update.emit(f"Executing: {cmd}...")

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
                    f"Tool failure detected "
                    f"(Attempt {self._tool_failure_count}/{self._max_tool_failures}), "
                    "retrying..."
                )
                self._generate_response()
        else:
            self._tool_failure_count = 0  # Reset on success
            self._finalize_turn_after_tool()

    def _finalize_turn_after_tool(self):
        """Finalizes turn immediately after tool execution (Safe Mode)."""
        # We don't generate more text. We just stop.
        # But we ensure the UI knows we are done.
        self.status_update.emit("Ready")
        self.is_processing = False

        # Optional: If the tool output is hidden, the user sees nothing?
        # The user said "Tool call doesn't show...".
        # If we successfully hid the tool call JSON, the chat is blank?
        # We might want to show a standard "Action Completed" if silence.

    def _handle_loop_detected(self, cmd: str):
        """Handles logic when a loop is detected."""
        msg = (
            f"System: Loop detected. You have called '{cmd}' "
            "with these params multiple times. Stop."
        )
        self._append_history("user", msg)
        self.status_update.emit("Loop detected, interrupting...")
        self._generate_response()

    def _finalize_turn(self, response_text: str):
        """Finalizes the turn when no commands are present."""
        self._append_history("assistant", response_text)
        self.status_update.emit("Ready")
        self.is_processing = False

    def _execute_tool_no_loop(self, command_name, params):
        """
        Executes tool and returns (success, result_str).
        Does NOT trigger generation.
        """
        tool = get_tool_by_name(command_name)
        if tool:
            try:
                result = tool.execute(self.study, **params)
            except Exception as e:
                error_msg = f"Tool execution failed: {e}"
                self.status_update.emit(error_msg)
                return False, error_msg
            else:
                return True, result
        else:
            self.status_update.emit(f"Unknown tool: {command_name}")
            return False, f"Error: Unknown tool '{command_name}'"

    def _detect_loop(self, current_call_signature) -> bool:
        """
        Check if the same tool call has been made > 3 times recently.
        current_call_signature: (cmd_name, params_str)
        """
        count = 0
        for call in self._recent_tool_calls:
            if call == current_call_signature:
                count += 1
        return count >= 3

    def _handle_tool_result_logic(self, result: str, success: bool = True):
        """Processes tool result for UI side effects (Switch Panel, etc)."""
        if result.startswith("Request:"):
            # Format: "Request: CommandName params"
            cmd_part = result.replace("Request:", "").strip()

            if cmd_part.lower().startswith("switch ui to"):
                target = cmd_part.replace("Switch UI to", "").strip()
                if target.startswith(("'", '"')):
                    target = (
                        target.split("'")[1] if "'" in target else target.split('"')[1]
                    )
                self.request_user_interaction.emit("switch_panel", {"panel": target})
                # We don't append history here, caller does.
                return True

            self.status_update.emit("Waiting for user interaction...")
            self.request_user_interaction.emit("confirm_montage", {"context": cmd_part})
            return True

        if not result.startswith("Request:"):
            # Only report as System Error if the tool actually failed
            if not success:
                self.response_ready.emit("System", f"Tool Error: {result}")
            else:
                pass
        return False

    # Deprecated/Removed old _execute_tool and _handle_tool_result to avoid confusion
    # But for safety, keep _handle_tool_result if referenced elsewhere?
    # It was internal. I'll replace it completely.

    def _on_worker_error(self, error_msg):
        self.error_occurred.emit(error_msg)
        self.status_update.emit("Error")
        self.is_processing = False

    def close(self):
        """Cleanup thread."""
        if hasattr(self, "worker_thread") and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait()

    def stop_generation(self):
        """Stops the current generation process."""
        if self.is_processing:
            self.status_update.emit("Stopping...")
            self.is_processing = False
            # Ideally, we should signal the worker to stop.
            # checks worker.requestInterruption() inside long loops?
            self.worker_thread.requestInterruption()

    def set_model(self, model_display_name: str):
        """Updates the model configuration."""
        # Map Display Name to Model ID
        # "Gemini 2.0 Flash", "Gemini 1.5 Pro", "Local (Qwen)"
        model_map = {
            "Gemini 2.0 Flash": "gemini-2.0-flash-exp",  # or similar
            "Gemini 1.5 Pro": "gemini-1.5-pro",
            "Local (Qwen)": "local-qwen",  # hypothetical
        }

        _mode_id = model_map.get(model_display_name, "gemini-1.5-pro")
        self.status_update.emit(f"Model switched to {model_display_name}")
        # TODO: Implement actual engine switch in Worker
        # self.sig_reinit.emit(_mode_id)
