"""Research composition keeps the real MainWindow/AgentManager host lifecycle."""

from XBrainLab.backend.study import Study
from XBrainLab.ui.components.agent_manager import AgentManager
from XBrainLab.ui.components.assistant_runtime_lifecycle import (
    AssistantRuntimeLifecycle,
)
from XBrainLab.ui.main_window import MainWindow


def test_explicit_manager_factory_keeps_real_host_and_cleanup(qtbot):
    created = []
    study = Study()

    def factory(window, actual_study, *, application_service):
        def must_not_start_before_explicit_research_launch(_study):
            raise AssertionError("Opening the host must not load a model")

        runtime = AssistantRuntimeLifecycle(
            actual_study,
            controller_factory=must_not_start_before_explicit_research_launch,
            parent=window,
        )
        manager = AgentManager(
            window,
            actual_study,
            application_service=application_service,
            runtime_lifecycle=runtime,
        )
        created.append((window, actual_study, manager, runtime))
        return manager

    window = MainWindow(study, agent_manager_factory=factory)
    qtbot.addWidget(window)
    try:
        window.init_agent()
        window.init_agent()
        assert len(created) == 1
        actual_window, actual_study, manager, runtime = created[0]
        assert actual_window is window and actual_study is study
        assert window.agent_manager is manager
        assert manager.assistant_runtime is runtime
        assert manager.chat_panel is not None
        assert manager.agent_controller is None
        assert manager.close() is True
    finally:
        window.close()
