
from PyQt6.QtCore import QObject, pyqtSignal, QThread
from XBrainLab.backend.utils.logger import logger
from .parser import CommandParser
from XBrainLab.llm.tools import get_tool_by_name, AVAILABLE_TOOLS
from .prompts import get_system_prompt
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

    def handle_user_input(self, text: str):
        """Entry point for user input from UI."""
        if not text.strip():
            return

        self.is_processing = True
        self.status_update.emit("Thinking...")
        
        # 1. Update History
        self.history.append({"role": "user", "content": text})
        
        # 2. Start Generation Loop
        self._generate_response()

    def _generate_response(self):
        """Triggers the LLM generation based on current history."""
        # Construct full messages list
        system_prompt = get_system_prompt(AVAILABLE_TOOLS)
        messages = [{"role": "system", "content": system_prompt}]
        # Sliding Window: Keep only the last 10 messages to avoid context overflow
        recent_history = self.history[-10:]
        messages.extend(recent_history)
        
        self.current_response = "" # Reset accumulator
        
        # Call worker via signal
        self.sig_generate.emit(messages)

    def _on_chunk_received(self, chunk: str):
        """Accumulate chunk and forward to UI if it's a text response."""
        self.current_response += chunk
        # We can optionally stream to UI here if we are sure it's not a tool call.
        # But since we don't know yet, we might want to buffer or stream optimistically.
        # For better UX, let's stream to UI. If it turns out to be JSON, we might hide it later?
        # Or we just stream everything and let the user see the "Thinking" process (JSON).
        # The user requested "Intermediate messages shouldn't be in output box, only in log".
        # So we should NOT stream to UI until we know it's final text?
        # But that makes it feel slow.
        # Compromise: We don't stream to UI. We wait for finish.
        # OR: We check if it looks like JSON.
        # Let's wait for finish for now to ensure clean UI as requested.
        pass 

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
            self.history.append({"role": "assistant", "content": response_text})
            
            # Defer execution slightly to allow UI to update status
            self._execute_tool(command_name, params)
        
        else:
            # It's a final text response
            self.history.append({"role": "assistant", "content": response_text})
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
                self.history.append({"role": "user", "content": f"Tool Output: {result}"})
                
                # Loop: Generate again
                self._generate_response()
                return
                
            except Exception as e:
                error_msg = f"Tool execution failed: {e}"
                self.status_update.emit(error_msg)
                self.history.append({"role": "user", "content": f"Tool Error: {error_msg}"})
                self._generate_response()
                return
        else:
            self.status_update.emit(f"Unknown tool: {command_name}")
            self.history.append({"role": "user", "content": f"Error: Unknown tool '{command_name}'"})
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
