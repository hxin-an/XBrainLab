"""Background worker for LLM inference.

Provides a Qt-based worker that runs LLM generation in a separate
thread, with streaming output, timeout handling, and hot-swap model
switching.
"""

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication

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
            logger.error("Generation error: %s", e, exc_info=True)
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
        self.engine: LLMEngine | None = None
        self.generation_thread: GenerationThread | None = None
        self.timeout_timer: QTimer | None = None

    @staticmethod
    def _load_runtime_config(fallback: LLMConfig | None = None):
        """Load the current persisted config and apply transient CLI overrides."""
        config = LLMConfig.load_from_file() or fallback or LLMConfig()

        app = QApplication.instance()
        if app:
            override = app.property("model_override")
            if override:
                override_value = str(override)
                if override_value in LLMConfig.allowed_local_model_ids():
                    config.apply_runtime_selection(
                        "local",
                        model_id=override_value,
                        ui_active_mode="local",
                    )
                else:
                    config.apply_runtime_selection("local", ui_active_mode="local")

        return config

    @staticmethod
    def _resolve_local_runtime(config: LLMConfig):
        """Apply the local fallback model policy to a runtime config."""
        selection = LLMConfig.assistant_runtime_selection_from(config)

        try:
            fallback_result = config.available_local_model_id(selection.model_id)
        except AttributeError:
            return selection, None, True
        if not isinstance(fallback_result, tuple) or len(fallback_result) != 2:
            # Tests and some legacy callers pass config-like mocks. If they do
            # not implement the product fallback contract, keep old behavior
            # instead of failing config sync before generation starts.
            return selection, None, True

        model_id, message = fallback_result
        if model_id is None:
            return selection, message, False

        if model_id != selection.model_id:
            config.apply_runtime_selection(
                "local",
                model_id=model_id,
                ui_active_mode="local",
            )
            selection = LLMConfig.assistant_runtime_selection_from(config)

        return selection, message, True

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

        config = self._load_runtime_config()
        selection, readiness_message, runtime_ready = self._resolve_local_runtime(
            config
        )
        if selection.backend_mode == "local" and not runtime_ready:
            message = readiness_message or config.local_backend_status_message(
                selection.model_id
            )
            logger.warning("Local backend not ready during initialization: %s", message)
            self.error.emit(f"Model Load Error: {message}")
            return
        if selection.backend_mode == "local":
            message = readiness_message or config.local_backend_status_message(
                selection.model_id
            )
            if message != "Local runtime ready.":
                logger.warning(
                    "Local backend will continue with adjusted runtime: %s",
                    message,
                )
                self.log.emit(message)

        try:
            logger.info("Initializing LLM Engine...")
            self.log.emit("Loading AI Model...")

            self.engine = LLMEngine(config)
            self.engine.load_model()

            self.log.emit(f"AI Model Loaded: {selection.model_id}")
            logger.info("Local Agent initialized successfully")
        except Exception as e:
            logger.error("Failed to initialize Agent", exc_info=True)
            self.error.emit(f"Model Load Error: {e!s}")

    def _cleanup_generation_thread(self):
        """Disconnect and request interruption of any running generation thread.

        Prevents double callbacks and interleaved chunks when a new
        generation is started before a previous one finishes.
        """
        if self.generation_thread is not None:
            try:
                self.generation_thread.chunk_received.disconnect(self.chunk_received)
                self.generation_thread.finished_generation.disconnect(
                    self._on_generation_finished,
                )
                self.generation_thread.error_occurred.disconnect(
                    self._on_generation_error,
                )
            except (TypeError, RuntimeError):
                pass  # Already disconnected
            if self.generation_thread.isRunning():
                self.generation_thread.requestInterruption()
            self.generation_thread = None

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
                self.error.emit("Failed to initialize LLM engine.")
                self.finished.emit([])
                return

        last_msg = messages[-1]
        if last_msg["role"] == "user":
            log_text = (
                last_msg["content"][:50] + "..."
                if len(last_msg["content"]) > 50
                else last_msg["content"]
            )
            self.log.emit("Processing...")
            logger.info("Agent generating for input: %s", log_text)
        else:
            self.log.emit("Processing...")

        # SYNC CONFIG: Reload from file to avoid "Split Brain" with UI Settings
        # This ensures change in Temperature/API Key are picked up immediately.
        previous_config = self.engine.config
        try:
            fresh_config = self._load_runtime_config(previous_config)
            if fresh_config:
                previous_selection = LLMConfig.assistant_runtime_selection_from(
                    previous_config
                )
                fresh_selection = LLMConfig.assistant_runtime_selection_from(
                    fresh_config
                )

                readiness_message = None
                runtime_ready = True
                if fresh_selection.backend_mode == "local":
                    (
                        fresh_selection,
                        readiness_message,
                        runtime_ready,
                    ) = self._resolve_local_runtime(fresh_config)

                if fresh_selection.backend_mode == "local" and not runtime_ready:
                    message = (
                        readiness_message
                        or fresh_config.local_backend_status_message(
                            fresh_selection.model_id
                        )
                    )
                    logger.warning(
                        "Local backend not ready during config sync: %s",
                        message,
                    )
                    self.error.emit(f"Config Sync Failed: {message}")
                    self.finished.emit([])
                    return
                if (
                    fresh_selection.backend_mode == "local"
                    and readiness_message
                    and readiness_message != "Local runtime ready."
                ):
                    self.log.emit(readiness_message)

                self.engine.config = fresh_config

                # Reload when the backend mode changes or the selected model ID
                # inside the same backend has drifted from the active backend.
                if (
                    fresh_selection.backend_mode != previous_selection.backend_mode
                    or fresh_selection.model_id != previous_selection.model_id
                ):
                    self.engine.switch_backend(fresh_selection.backend_mode)
        except Exception as e:
            self.engine.config = previous_config
            logger.error("Failed to sync config: %s", e)
            self.error.emit(f"Config Sync Failed: {e}")
            self.finished.emit([])
            return

        # Start Generation Thread — clean up any previous thread first
        self._cleanup_generation_thread()

        self.generation_thread = GenerationThread(self.engine, messages)
        self.generation_thread.chunk_received.connect(self.chunk_received)
        self.generation_thread.finished_generation.connect(self._on_generation_finished)
        self.generation_thread.error_occurred.connect(self._on_generation_error)

        # Timeout timer (thread-safe UI timer) — reuse existing or create once
        self._is_timed_out = False

        if self.timeout_timer is None:
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
                    self._on_generation_finished,
                )
                self.generation_thread.error_occurred.disconnect(
                    self._on_generation_error,
                )
                # self.generation_thread.terminate() # Dangerous, avoid unless necessary
            except Exception:
                logger.debug(
                    "Signal disconnect failed (already disconnected)",
                    exc_info=True,
                )

            self.error.emit("Error: Generation timed out (Local LLM is too slow).")
            self.finished.emit([])  # Unblock the UI

    def _on_generation_finished(self):
        """Handles successful completion of the generation thread."""
        if self._is_timed_out:
            return
        if self.timeout_timer is not None:
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
        if self.timeout_timer is not None:
            self.timeout_timer.stop()
        self.error.emit(err_msg)

    @staticmethod
    def _unsupported_local_model_message(allowed_models: list[str]) -> str:
        """Build a fail-closed message for non-catalog model switches."""
        supported = ", ".join(allowed_models)
        return (
            "Only approved local assistant models can be selected. "
            f"Supported models: {supported}."
        )

    def reinitialize_agent(self, model_id: str):
        """Re-initializes the engine with a new model configuration.

        Supports hot-swap between the approved local product models.

        Args:
            model_id: Identifier or display name of the target local model.

        """
        logger.info("Worker switching model to: %s", model_id)
        self.log.emit(f"Switching to {model_id}...")

        engine = self.engine
        if engine is None:
            logger.warning("Engine not initialized in switch_model")
            return

        old_inference_mode = engine.config.inference_mode
        old_active_mode = engine.config.active_mode

        try:
            allowed_models = LLMConfig.allowed_local_model_ids()
            model_id_clean = str(model_id or "").strip()
            if model_id_clean.lower() == "local":
                new_model_id = engine.config.model_name
                if new_model_id not in allowed_models:
                    new_model_id = LLMConfig.default_local_model_id()
            elif model_id_clean in allowed_models:
                new_model_id = model_id_clean
            else:
                message = self._unsupported_local_model_message(allowed_models)
                logger.warning("Rejected assistant model switch: %s", message)
                self.error.emit(f"Switch Failed: {message}")
                return

            engine.config.apply_runtime_selection(
                "local",
                model_id=new_model_id,
                ui_active_mode="local",
            )
            engine.switch_backend("local")

            # Persist change so Settings Dialog sees it
            engine.config.save_to_file()

            self.log.emit(f"Switched to local model: {new_model_id}")
            logger.info("Model switch successful to local model %s", new_model_id)

        except Exception as e:
            engine.config.inference_mode = old_inference_mode
            engine.config.active_mode = old_active_mode
            logger.error("Failed to switch model: %s", e, exc_info=True)
            self.error.emit(f"Switch Failed: {e}")
