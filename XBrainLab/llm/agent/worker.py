"""Background worker for LLM inference.

Provides a Qt-based worker that runs LLM generation in a separate
thread, with streaming output, timeout handling, and hot-swap model
switching.
"""

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal

from XBrainLab.backend.utils.logger import logger
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import LLMEngine


class GenerationThread(QThread):
    """QThread for running LLM generation without blocking the UI.

    Attributes:
        chunk_received: Signal emitted for each text chunk generated.
        finished_generation: Signal emitted when generation completes.
        error_occurred: Signal emitted with an error message on failure.
        engine: The LLM engine performing inference.
        messages: The message list to generate from.
    """

    chunk_received = pyqtSignal(str)
    finished_generation = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, engine, messages):
        """Initializes the GenerationThread.

        Args:
            engine: The ``LLMEngine`` instance to use for generation.
            messages: List of message dicts to pass to the engine.
        """
        super().__init__()
        self.engine = engine
        self.messages = messages

    def run(self):
        """Executes streaming generation, emitting chunks until done."""
        try:
            for chunk in self.engine.generate_stream(self.messages):
                if self.isInterruptionRequested():
                    logger.info("Generation interrupted by user request.")
                    break
                self.chunk_received.emit(chunk)
            self.finished_generation.emit()
        except Exception as e:
            logger.error(f"Generation error: {e}", exc_info=True)
            self.error_occurred.emit(str(e))


class AgentWorker(QObject):
    """Worker managing LLM initialization, generation, and model switching.

    Runs inside a dedicated ``QThread`` to keep the UI responsive.  Emits
    Qt signals for streaming chunks, completion, errors, and status logs.

    Attributes:
        finished: Signal emitted (with empty list) when generation ends.
        chunk_received: Signal forwarding text chunks from the generation thread.
        error: Signal emitted with an error message string.
        log: Signal emitted with status/log messages.
        engine: The underlying ``LLMEngine`` instance (``None`` until initialized).
        generation_thread: The currently running ``GenerationThread``, if any.
    """

    finished = pyqtSignal(list)
    chunk_received = pyqtSignal(str)
    error = pyqtSignal(str)
    log = pyqtSignal(str)

    def __init__(self):
        """Initializes the AgentWorker with no engine loaded."""
        super().__init__()
        self.engine = None
        self.generation_thread = None

    def initialize_agent(self):
        """Initializes the LLM engine and loads the model.

        Reads configuration from ``LLMConfig`` defaults.  If the engine
        is already initialized, this method is a no-op.

        Raises:
            Exception: Propagated via the ``error`` signal if model
                loading fails.
        """
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
        """Runs LLM generation using a full message history.

        Reloads configuration from the settings file to capture any
        runtime changes (e.g. temperature, API key), then spawns a
        ``GenerationThread`` with a configurable timeout.

        Args:
            messages: List of message dicts with ``role`` and ``content``
                keys representing the conversation so far.
        """
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

        # SYNC CONFIG: Reload from file to avoid "Split Brain" with UI Settings
        # This ensures change in Temperature/API Key are picked up immediately.
        try:
            fresh_config = LLMConfig.load_from_file()
            if fresh_config:
                old_mode = self.engine.config.inference_mode
                self.engine.config = fresh_config

                # Only switch backend if inference mode actually changed
                if fresh_config.inference_mode != old_mode:
                    self.engine.switch_backend(fresh_config.inference_mode)
        except Exception as e:
            logger.error(f"Failed to sync config: {e}")

        # Start Generation Thread
        self.generation_thread = GenerationThread(self.engine, messages)
        self.generation_thread.chunk_received.connect(self.chunk_received)
        self.generation_thread.finished_generation.connect(self._on_generation_finished)
        self.generation_thread.error_occurred.connect(self._on_generation_error)

        # Timeout timer (thread-safe UI timer)
        self._is_timed_out = False

        self.timeout_timer = QTimer(self)
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self._on_timeout)

        # Start with config timeout or default 60s
        timeout_ms = getattr(self.engine.config, "timeout", 60) * 1000
        self.timeout_timer.start(timeout_ms)

        self.generation_thread.start()

    def _on_timeout(self):
        """Handles generation timeout.

        Requests interruption of the generation thread and emits an
        error signal.  The timed-out flag prevents stale callbacks from
        further processing.
        """
        if self.generation_thread and self.generation_thread.isRunning():
            self._is_timed_out = True
            logger.error("Agent generation timed out.")

            # We can't safely kill the thread in Python, but we can ignore its
            # future output and signal the UI to proceed.
            try:
                self.generation_thread.requestInterruption()  # Request stop
                self.generation_thread.chunk_received.disconnect(self.chunk_received)
                self.generation_thread.finished_generation.disconnect(
                    self._on_generation_finished
                )
                self.generation_thread.error_occurred.disconnect(
                    self._on_generation_error
                )
                # self.generation_thread.terminate() # Dangerous, avoid unless necessary
            except Exception:
                pass  # Signals may already be disconnected after timeout

            self.error.emit("Error: Generation timed out (Local LLM is too slow).")
            self.finished.emit([])  # Unblock the UI

    def _on_generation_finished(self):
        """Handles successful completion of the generation thread."""
        if self._is_timed_out:
            return
        self.timeout_timer.stop()
        self.finished.emit([])
        self.log.emit("Generation completed.")

    def _on_generation_error(self, err_msg):
        """Handles an error emitted by the generation thread.

        Args:
            err_msg: The error message string from the generation thread.
        """
        if self._is_timed_out:
            return
        self.timeout_timer.stop()
        self.error.emit(err_msg)

    def reinitialize_agent(self, model_id: str):
        """Re-initializes the engine with a new model configuration.

        Supports hot-swap between local, API, and Gemini backends based
        on the provided ``model_id``.

        Args:
            model_id: Identifier or display name of the target model.
                May contain hints like ``'gemini'`` or ``'local'`` for
                backend routing.
        """
        logger.info(f"Worker switching model to: {model_id}")
        self.log.emit(f"Switching to {model_id}...")

        try:
            # 1. Determine Inference Mode
            if not self.engine:
                logger.warning("Engine not initialized in switch_model")
                return

            model_id_lower = model_id.lower()

            if "gemini" in model_id_lower:
                new_mode = "gemini"
                # FIX: Only update model name if not generic mode switch "Gemini"
                if model_id_lower != "gemini":
                    self.engine.config.gemini_model_name = model_id

            elif "local" in model_id_lower:
                new_mode = "local"
                # FIX: Only update model name if not generic mode switch "Local"
                # Usually local models don't contain "local" in repo ID.
                if model_id_lower != "local":
                    # Note: LocalBackend uses config.model_name
                    self.engine.config.model_name = model_id
            else:
                new_mode = "api"
                self.engine.config.api_model_name = model_id

            # 2. Update config and switch backend
            self.engine.config.inference_mode = new_mode
            self.engine.switch_backend(new_mode)

            # Persist change so Settings Dialog sees it
            self.engine.config.save_to_file()

            self.log.emit(f"Switched to {new_mode.capitalize()}")
            logger.info(f"Model switch successful to {new_mode}")

        except Exception as e:
            logger.error(f"Failed to switch model: {e}", exc_info=True)
            self.error.emit(f"Switch Failed: {e}")
