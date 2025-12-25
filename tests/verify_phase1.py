import unittest
from unittest.mock import MagicMock, patch
import os
import sys
import shutil

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from XBrainLab.utils.logger import setup_logger
from remote.core.agent import Agent

class TestPhase1(unittest.TestCase):
    
    def setUp(self):
        # Clean up logs before test
        if os.path.exists("logs_test"):
            shutil.rmtree("logs_test")

    def test_logger_creation(self):
        print("\n[Test] Verifying Logger...")
        log_file = "logs_test/test.log"
        logger = setup_logger("TestLogger", log_file=log_file)
        logger.info("This is a test log message")
        
        self.assertTrue(os.path.exists(log_file), "Log file should be created")
        with open(log_file, 'r') as f:
            content = f.read()
            self.assertIn("This is a test log message", content, "Log content should match")
        print("[Pass] Logger works correctly.")

    @patch('remote.core.agent.RAGEngine')
    @patch('remote.core.agent.LLMEngine')
    def test_agent_structure(self, MockLLM, MockRAG):
        print("\n[Test] Verifying Agent Logic (Mocked)...")
        
        # Setup Mocks
        mock_llm_instance = MockLLM.return_value
        mock_rag_instance = MockRAG.return_value
        
        # Mock RAG encode to return a tensor (for prompt selection)
        import torch
        # Mocking embeddings for 6 prompts
        mock_rag_instance.encode.return_value = torch.rand(6, 768) 
        
        # Mock LLM generation
        # Simulate a valid JSON response
        mock_llm_instance.generate.return_value = ['{"command": "Start", "parameters": {}}']
        
        # Initialize Agent
        agent = Agent(use_rag=True, use_voting=False)
        
        # Test generate_commands
        commands = agent.generate_commands(history="", input_text="Hello")
        
        self.assertTrue(len(commands) > 0, "Agent should return commands")
        self.assertEqual(commands[0]['command'], 'start', "Should parse command correctly (lowercase)")
        print("[Pass] Agent logic flow works correctly.")

if __name__ == '__main__':
    unittest.main()
