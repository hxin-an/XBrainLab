from PyQt6.QtCore import QObject, QThread, pyqtSignal

from XBrainLab.llm.tools import AVAILABLE_TOOLS, get_tool_by_name

from .parser import CommandParser
from .prompt_manager import PromptManager
from .worker import AgentWorker


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
    sig_initialize = pyqtSignal()
    sig_generate = pyqtSignal(list)

    def __init__(self, study):
        super().__init__()
        self.study = study

        # Initialize PromptManager
        self.prompt_manager = PromptManager(AVAILABLE_TOOLS)

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

        # 2. Start Generation Loop
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

        if command_result:
            # It's a tool call - don't show anything in chat (or hide what was just
            # streamed)
            # Actually, since we streamed it, the user sees JSON.
            # We emit remove_content signal if we want to collapse it.
            # But let's stick to simple logic first.
            command_name, params = command_result
            self.status_update.emit(f"Executing: {command_name}...")

            # Add the tool call to history (as assistant output)
            self._append_history("assistant", response_text)

            # Execute tool (will loop back to _generate_response)
            self._execute_tool(command_name, params)

        else:
            # It's the FINAL text response
            self._append_history("assistant", response_text)

            # We already streamed it, so just update status
            # self.generation_started.emit() # Removed
            # self.chunk_received.emit(response_text) # Removed

            self.status_update.emit("Ready")
            self.is_processing = False

    def _execute_tool(self, command_name, params):
        """Executes the tool and handles the result."""
        tool = get_tool_by_name(command_name)
        if tool:
            try:
                result = tool.execute(self.study, **params)
            except Exception as e:
                error_msg = f"Tool execution failed: {e}"
                self.status_update.emit(error_msg)
                self._append_history("user", f"Tool Error: {error_msg}")
                self._generate_response()
                return
            else:
                self._handle_tool_result(result)
                return

        else:
            self.status_update.emit(f"Unknown tool: {command_name}")
            self._append_history("user", f"Error: Unknown tool '{command_name}'")
            self._generate_response()
            return

    def _handle_tool_result(self, result: str):
        """Processes tool result and decides next step."""
        # Check for Human-in-the-loop Request
        if result.startswith("Request:"):
            # Format: "Request: CommandName params"
            cmd_part = result.replace("Request:", "").strip()

            if cmd_part.lower().startswith("switch ui to"):
                # Handle Switch Panel
                # cmd_part example: "Switch UI to 'training' (View: metrics)"
                # Simple parsing logic
                target = cmd_part.replace("Switch UI to", "").strip()
                # Remove quotes if present
                if target.startswith(("'", '"')):
                    # primitive parsing
                    target = (
                        target.split("'")[1] if "'" in target else target.split('"')[1]
                    )

                self.request_user_interaction.emit("switch_panel", {"panel": target})
                self._append_history("assistant", f"Switching UI to {target}")
                return

            # Default to Montage Confirmation for other requests (for now)
            # Emit signal to UI to take over
            self.status_update.emit("Waiting for user interaction...")
            self.request_user_interaction.emit("confirm_montage", {"context": cmd_part})

            # Pause the Agent Loop (do not call _generate_response)
            # Record that we are waiting?
            self._append_history("assistant", f"Requested user interaction: {cmd_part}")
            return

        self.status_update.emit(f"Tool Result: {result}")
        if not result.startswith("Request:"):
            # Only show tool output in chat if it's an error (Less verbosity)
            if (
                "error" in result.lower()
                or "exception" in result.lower()
                or "failed" in result.lower()
            ):
                self.response_ready.emit("System", f"Tool Error: {result}")
            else:
                # Normal success: Silent in chat, but visible in Status Bar (above)
                pass

        # Feed result back to LLM
        self._append_history("user", f"Tool Output: {result}")

        # Loop: Generate again
        self._generate_response()

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
