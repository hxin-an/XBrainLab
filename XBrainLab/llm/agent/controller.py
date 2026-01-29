import logging
from collections import deque

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
        self._recent_tool_calls = deque(maxlen=10)
        self._retry_count = 0
        self._max_retries = 2

    def initialize(self):
        """Initialize the underlying worker/engine."""
        self.sig_initialize.emit()

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

        # Update status and Start Bubble
        self.status_update.emit("Generating response...")
        self.generation_started.emit()

        # Call worker via signal
        self.sig_generate.emit(messages)

    def _on_chunk_received(self, chunk: str):
        """Accumulate chunk and stream to UI."""
        self.current_response += chunk
        self.chunk_received.emit(chunk)

    def _on_generation_finished(self):
        """Called when LLM finishes generating one turn."""
        response_text = self.current_response.strip()

        # 1. Parse for Commands
        command_result = CommandParser.parse(response_text)

        # --- JSON Fault Tolerance (Auto-Retry) ---
        if not command_result and (
            "```" in response_text or ("{" in response_text and "}" in response_text)
        ):
                if self._retry_count < self._max_retries:
                    logger.warning("Broken JSON detected. Retrying...")
                    self._retry_count += 1

                    self._append_history("assistant", response_text)
                    err_msg = (
                        "System: Your last output contained broken JSON. "
                        "Please check your syntax and output VALID JSON only."
                    )
                    self._append_history("user", err_msg)
                    self.status_update.emit("Invalid JSON, retrying...")
                    self._generate_response()
                    return
                else:
                    logger.error("Max retries reached for JSON error.")
                    # Fallthrough to "Ready" but maybe show error?

        if command_result:
            self._retry_count = 0 # Reset on success
            # Handle List of Commands (Multi-Step Support)
            # Ensure it is a list
            commands = (
                command_result if isinstance(command_result, list) else [command_result]
            )

            self._append_history("assistant", response_text)

            for cmd, params in commands:
                # --- Loop Detection ---
                call_signature = (cmd, str(params))
                self._recent_tool_calls.append(call_signature)
                if self._detect_loop(call_signature):
                    msg = (
                        f"System: Loop detected. You have called '{cmd}' "
                        "with these params multiple times. Stop."
                    )
                    self._append_history("user", msg)
                    self.status_update.emit("Loop detected, interrupting...")
                    self._generate_response() # Let LLM handle it or stop?
                    # If we loop, we might want to stop or ask LLM to fix.
                    return

                self.status_update.emit(f"Executing: {cmd}...")

                # Execute Tool
                _success, result = self._execute_tool_no_loop(cmd, params)

                # If special UI Interaction triggered in tool result?
                # _execute_tool_no_loop handles execution.
                # We need to handle the result (e.g. Switch UI).
                self._handle_tool_result_logic(result)

                # Feed result back to History
                self._append_history("user", f"Tool Output: {result}")

            # After all tools executed, trigger next generation loop
            self._generate_response()

        else:
            # It's the FINAL text response
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

    def _handle_tool_result_logic(self, result: str):
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
                return

            self.status_update.emit("Waiting for user interaction...")
            self.request_user_interaction.emit("confirm_montage", {"context": cmd_part})
            return

        if not result.startswith("Request:"):
            if (
                "error" in result.lower()
                or "exception" in result.lower()
                or "failed" in result.lower()
            ):
                self.response_ready.emit("System", f"Tool Error: {result}")
            else:
                pass

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
