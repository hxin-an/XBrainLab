from PyQt6.QtCore import QThread, pyqtSignal, QObject
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from remote.core.agent import Agent
from XBrainLab.utils.logger import logger

class AgentWorker(QObject):
    """
    Worker class to run Agent inference in a separate thread.
    """
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    log = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.agent = None

    def initialize_agent(self):
        """Initialize the agent (heavy loading). Should be called in the thread."""
        try:
            logger.info("Initializing Local Agent...")
            self.log.emit("Loading AI Model (this may take a while)...")
            self.agent = Agent(use_rag=True, use_voting=True)
            self.log.emit("AI Model Loaded.")
            logger.info("Local Agent initialized successfully")
        except Exception as e:
            logger.error("Failed to initialize Agent", exc_info=True)
            self.error.emit(str(e))

    def generate(self, history, input_text):
        """Run generation."""
        if not self.agent:
            self.initialize_agent()
        
        try:
            logger.info(f"Agent generating for input: {input_text}")
            commands = self.agent.generate_commands(history, input_text)
            self.finished.emit(commands)
        except Exception as e:
            logger.error("Error during generation", exc_info=True)
            self.error.emit(str(e))
