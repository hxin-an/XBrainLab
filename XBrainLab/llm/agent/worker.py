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
    finished = pyqtSignal(list) # Kept for compatibility, though we stream now
    chunk_received = pyqtSignal(str) # New signal for streaming text
    error = pyqtSignal(str)
    log = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.engine = None
        self.generation_thread = None

    def initialize_agent(self):
        """Initialize the local LLM engine."""
        if self.engine:
            return

        try:
            logger.info("Initializing Local LLM Engine...")
            self.log.emit("Loading AI Model (this may take a while)...")

            # Initialize Engine
            # TODO: Allow user to configure model path via UI settings
            config = LLMConfig()
            self.engine = LLMEngine(config)

            # Load model in a separate thread to not freeze UI completely
            # For simplicity in this step, we might block briefly or need another thread
            # But LLMEngine.load_model is called lazily in generate_stream usually,
            # or we can force it here. Let's force it but warn user.
            self.engine.load_model()

            self.log.emit("AI Model Loaded.")
            logger.info("Local Agent initialized successfully")
        except Exception as e:
            logger.error("Failed to initialize Agent", exc_info=True)
            self.error.emit(f"Model Load Error: {e!s}")

    def generate_from_messages(self, messages):
        """Run generation with full message history."""
        if not self.engine:
            self.initialize_agent()
            if not self.engine: # If initialization failed
                return

        # Log the last user message for context
        last_msg = messages[-1]
        if last_msg['role'] == 'user':
            log_text = last_msg['content'][:50] + "..." if len(last_msg['content']) > 50 else last_msg['content']
            self.log.emit(f"Processing: {log_text}")
            logger.info(f"Agent generating for input: {log_text}")
        else:
            self.log.emit("Processing...")

        self.generation_thread = GenerationThread(self.engine, messages)
        self.generation_thread.chunk_received.connect(self.chunk_received)
        self.generation_thread.finished_generation.connect(lambda: (self.finished.emit([]), self.log.emit("Generation completed.")))
        self.generation_thread.error_occurred.connect(self.error)
        self.generation_thread.start()
