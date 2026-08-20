from unittest.mock import patch

from XBrainLab.llm.agent.runtime_state import AssistantRuntimePhase
from XBrainLab.llm.core.config import LLMConfig


def test_reselecting_only_supported_model_is_idempotent(test_app, qtbot):
    """
    Verify that reselecting the sole approved model does not reload the runtime.

    Mocks LLMEngine to avoid real PyTorch initialization/crash on Windows.
    """
    primary_model = LLMConfig.default_local_model_id()
    selected_model = LLMConfig.default_local_model_id()
    assert selected_model == primary_model
    config = LLMConfig()
    config.local_model_enabled = True
    config.model_name = primary_model
    config.inference_mode = "local"
    config.active_mode = "local"
    config.local_backend_ready = lambda _model=None: True  # type: ignore[method-assign]
    config.local_backend_status_message = (  # type: ignore[method-assign]
        lambda _model=None: "Local runtime ready."
    )

    with (
        patch("XBrainLab.llm.agent.worker.LLMEngine") as MockEngine,
        patch.object(LLMConfig, "load_from_file", return_value=config),
        patch.object(LLMConfig, "save_to_file"),
    ):
        mock_engine_instance = MockEngine.return_value
        agent_mgr = None
        try:
            test_app.init_agent()
            agent_mgr = test_app.agent_manager
            agent_mgr.start_system()

            assert agent_mgr.agent_controller is not None
            qtbot.waitUntil(
                lambda: agent_mgr.assistant_runtime.current.phase
                is AssistantRuntimePhase.READY,
                timeout=2_000,
            )
            assert agent_mgr.assistant_runtime.current.model_id == primary_model

            with qtbot.assertNotEmitted(agent_mgr.agent_controller.sig_reinit):
                agent_mgr.set_model(selected_model)

            assert MockEngine.called
            mock_engine_instance.switch_backend.assert_not_called()
            assert (
                agent_mgr.assistant_runtime.current.phase is AssistantRuntimePhase.READY
            )
            assert agent_mgr.assistant_runtime.current.model_id == selected_model
        finally:
            if agent_mgr is not None:
                agent_mgr.close()
                qtbot.waitUntil(
                    lambda: agent_mgr.assistant_runtime.state.value == "closed",
                    timeout=5_000,
                )
                assert agent_mgr.close() is True
