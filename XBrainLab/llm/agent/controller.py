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
    response_ready = pyqtSignal(str, str) # sender, text
    status_update = pyqtSignal(str)       # status message
    error_occurred = pyqtSignal(str)      # error message

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

        self.history = [] # List of {"role": str, "content": str}

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
        MAX_HISTORY = 20
        if len(self.history) > MAX_HISTORY:
            # Keep index 0 (system prompt implied? No, prompt_manager handles system)
            # If we just slice, we might lose context.
            # Ideally we keep a summary. For now, simple sliding window.
            self.history = self.history[-MAX_HISTORY:]

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

        self.current_response = "" # Reset accumulator

        # Call worker via signal
        self.sig_generate.emit(messages)

    def _on_chunk_received(self, chunk: str):
        """Accumulate chunk and forward to UI if it's a text response."""
        self.current_response += chunk
        # ... logic ...

    def _on_generation_finished(self):
        """Called when LLM finishes generating one turn."""
        response_text = self.current_response.strip()

        # 1. Parse for Commands
        command_result = CommandParser.parse(response_text)

        if command_result:
            # It's a tool call
            command_name, params = command_result
            self.status_update.emit(f"Executing tool: {command_name}...")

            # Add the tool call to history (as assistant output)
            self._append_history("assistant", response_text)

            # Defer execution slightly to allow UI to update status
            self._execute_tool(command_name, params)

        else:
            # It's a final text response
            self._append_history("assistant", response_text)
            self.response_ready.emit("Agent", response_text)
            self.status_update.emit("Ready")
            self.is_processing = False

    def _execute_tool(self, command_name, params):
        """Executes the tool and handles the result."""
        tool = get_tool_by_name(command_name)
        if tool:
            try:
                result = tool.execute(self.study, **params)
                self.status_update.emit(f"Tool Result: {result}")

                # Feed result back to LLM
                self._append_history("user", f"Tool Output: {result}")

                # Loop: Generate again
                self._generate_response()
                return

            except Exception as e:
                error_msg = f"Tool execution failed: {e}"
                self.status_update.emit(error_msg)
                self._append_history("user", f"Tool Error: {error_msg}")
                self._generate_response()
                return
        else:
            self.status_update.emit(f"Unknown tool: {command_name}")
            self._append_history("user", f"Error: Unknown tool '{command_name}'")
            self._generate_response()
            return

    def _on_worker_error(self, error_msg):
        self.error_occurred.emit(error_msg)
        self.status_update.emit("Error")
        self.is_processing = False

    def close(self):
        """Cleanup thread."""
        if hasattr(self, 'worker_thread') and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait()
