from unittest.mock import patch


def test_model_switching(test_app, qtbot):
    """
    Verify that the AgentManager -> LLMController -> AgentWorker pipeline
    correctly handles model switching at runtime.
    Mocks LLMEngine to avoid real PyTorch initialization/crash on Windows.
    """
    # Patch LLMEngine at the source where AgentWorker imports it
    # AgentWorker is in XBrainLab.llm.agent.worker
    with patch("XBrainLab.llm.agent.worker.LLMEngine") as MockEngine:
        # Mock instance
        mock_engine_instance = MockEngine.return_value

        # 1. Initialize Agent System
        test_app.init_agent()
        agent_mgr = test_app.agent_manager

        # Needs explicit start
        agent_mgr.start_system()

        # Wait for lazy init
        qtbot.wait(200)
        assert agent_mgr.agent_controller is not None

        # 2. Trigger Switch to Gemini
        # "Gemini 2.0 Flash" -> gemini-2.0-flash-exp
        with qtbot.waitSignal(agent_mgr.agent_controller.sig_reinit, timeout=1000):
            agent_mgr.set_model("Gemini 2.0 Flash")

        # Wait for worker to process
        qtbot.wait(500)

        # 3. Verify Switch Attempt
        # AgentWorker should have re-instantiated or called a method on Engine
        # The worker's `reinitialize_agent` calls `self.engine.switch_backend(mode)`
        # or creates new engine if not existing.

        # Verify Mock interaction
        assert MockEngine.called
