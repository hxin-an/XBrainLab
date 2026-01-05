from PyQt6.QtCore import QThread, pyqtSignal, QObject
from XBrainLab.backend.utils.logger import logger

class AgentWorker(QObject):
    """
    Worker class for AI Agent inference.
    
    NOTE: AI Agent functionality is currently disabled to maintain 
    frontend-backend separation. The agent backend (remote/) is under 
    development and should not be imported by the UI layer.
    
    This class provides a stub implementation that returns empty results.
    To enable AI features, implement a proper API-based backend service.
    """
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    log = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.agent = None
        self._agent_disabled = True

    def initialize_agent(self):
        """Initialize the agent (currently disabled)."""
        if self._agent_disabled:
            logger.warning("AI Agent is disabled - remote module not integrated")
            self.log.emit("AI Agent is currently disabled.")
            self.error.emit("AI Agent functionality is not available in this build.")
            return
        
        # Original implementation would go here when backend is ready:
        # try:
        #     logger.info("Initializing Local Agent...")
        #     self.log.emit("Loading AI Model (this may take a while)...")
        #     # TODO: Use API-based backend instead of direct import
        #     # Example: requests.post('http://localhost:5000/api/init')
        #     self.log.emit("AI Model Loaded.")
        #     logger.info("Local Agent initialized successfully")
        # except Exception as e:
        #     logger.error("Failed to initialize Agent", exc_info=True)
        #     self.error.emit(str(e))

    def generate(self, history, input_text):
        """Run generation (currently disabled)."""
        if self._agent_disabled:
            logger.warning(f"AI Agent disabled, ignoring request: {input_text}")
            self.error.emit("AI Agent is currently disabled.")
            self.finished.emit([])  # Return empty command list
            return
        
        # Original implementation would go here when backend is ready:
        # if not self.agent:
        #     self.initialize_agent()
        # 
        # try:
        #     logger.info(f"Agent generating for input: {input_text}")
        #     # TODO: Use API call instead of direct method call
        #     # Example: response = requests.post('http://localhost:5000/api/generate',
        #     #                                   json={'history': history, 'input': input_text})
        #     # commands = response.json()
        #     self.finished.emit(commands)
        # except Exception as e:
        #     logger.error("Error during generation", exc_info=True)
        #     self.error.emit(str(e))
