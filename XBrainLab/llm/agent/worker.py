from PyQt6.QtCore import QObject, QThread, pyqtSignal

from XBrainLab.backend.utils.logger import logger
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import LLMEngine


class GenerationThread(QThread):
    """Thread for running LLM generation without blocking UI."""

    chunk_received = pyqtSignal(str)
    finished_generation = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, engine, messages):
        super().__init__()
        self.engine = engine
        self.messages = messages

    def run(self):
        try:
            for chunk in self.engine.generate_stream(self.messages):
                self.chunk_received.emit(chunk)
            self.finished_generation.emit()
        except Exception as e:
            logger.error(f"Generation error: {e}", exc_info=True)
            self.error_occurred.emit(str(e))


class AgentWorker(QObject):
    """
    Worker class for AI Agent inference using Local LLM.
    """

    finished = pyqtSignal(list)
    chunk_received = pyqtSignal(str)
    error = pyqtSignal(str)
    log = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.engine = None
        self.generation_thread = None

    def initialize_agent(self):
        """Initialize the local LLM engine."""
        if self.engine:
            return  # Already initialized

        try:
            logger.info("Initializing LLM Engine...")
            self.log.emit("Loading AI Model...")

            config = LLMConfig()
            self.engine = LLMEngine(config)
            self.engine.load_model()

            self.log.emit(f"AI Model Loaded: {config.model_name}")
            logger.info("Local Agent initialized successfully")
        except Exception as e:
            logger.error("Failed to initialize Agent", exc_info=True)
            self.error.emit(f"Model Load Error: {e!s}")

    def generate_from_messages(self, messages):
        """Run generation with full message history."""
        if not self.engine:
            self.initialize_agent()
            if not self.engine:
                return

        last_msg = messages[-1]
        if last_msg["role"] == "user":
            log_text = (
                last_msg["content"][:50] + "..."
                if len(last_msg["content"]) > 50
                else last_msg["content"]
            )
            self.log.emit("Processing...")
            logger.info(f"Agent generating for input: {log_text}")
        else:
            self.log.emit("Processing...")

        self.generation_thread = GenerationThread(self.engine, messages)
        self.generation_thread.chunk_received.connect(self.chunk_received)
        self.generation_thread.finished_generation.connect(self._on_generation_finished)
        self.generation_thread.error_occurred.connect(self._on_generation_error)

        # Timeout timer (thread-safe UI timer)
        self._is_timed_out = False
        from PyQt6.QtCore import QTimer
        self.timeout_timer = QTimer(self)
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self._on_timeout)

        # Start with config timeout or default 60s
        timeout_ms = getattr(self.engine.config, "timeout", 60) * 1000
        self.timeout_timer.start(timeout_ms)

        self.generation_thread.start()

    def _on_timeout(self):
        """Handle generation timeout."""
        if self.generation_thread and self.generation_thread.isRunning():
            self._is_timed_out = True
            logger.error("Agent generation timed out.")

            # We can't safely kill the thread in Python, but we can ignore its
            # future output and signal the UI to proceed.
            try:
                self.generation_thread.chunk_received.disconnect(self.chunk_received)
                self.generation_thread.finished_generation.disconnect(self._on_generation_finished)
                # self.generation_thread.terminate() # Dangerous, avoid unless necessary
            except Exception:
                pass

            self.error.emit("Error: Generation timed out (Local LLM is too slow).")
            self.finished.emit([]) # Unblock the UI

    def _on_generation_finished(self):
        if self._is_timed_out:
            return
        self.timeout_timer.stop()
        self.finished.emit([])
        self.log.emit("Generation completed.")

    def _on_generation_error(self, err_msg):
        if self._is_timed_out:
            return
        self.timeout_timer.stop()
        self.error.emit(err_msg)
