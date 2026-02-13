import pytest

from XBrainLab.backend.controller.chat_controller import ChatController


class TestChatController:
    @pytest.fixture
    def controller(self):
        return ChatController()

    def test_initial_state(self, controller):
        assert controller.messages == []
        assert controller.is_processing is False

    def test_add_user_message(self, controller):
        # 監聽信號
        signal_received = []
        controller.message_added.connect(
            lambda text, is_user: signal_received.append((text, is_user))
        )

        controller.add_user_message("Hello")

        assert len(controller.messages) == 1
        assert controller.messages[0] == {"role": "user", "content": "Hello"}
        assert signal_received == [("Hello", True)]

    def test_add_agent_message(self, controller):
        signal_received = []
        controller.message_added.connect(
            lambda text, is_user: signal_received.append((text, is_user))
        )

        controller.add_agent_message("Hi there")

        assert len(controller.messages) == 1
        assert controller.messages[0] == {"role": "assistant", "content": "Hi there"}
        assert signal_received == [("Hi there", False)]

    def test_clear_conversation(self, controller):
        controller.add_user_message("Test")
        assert len(controller.messages) == 1

        cleared_signal = []
        controller.conversation_cleared.connect(lambda: cleared_signal.append(True))

        controller.clear_conversation()

        assert len(controller.messages) == 0
        assert cleared_signal == [True]

    def test_set_processing(self, controller):
        processing_signal = []
        controller.processing_state_changed.connect(
            lambda state: processing_signal.append(state)
        )

        controller.set_processing(True)
        assert controller.is_processing is True
        assert processing_signal[-1] is True

        controller.set_processing(False)
        assert controller.is_processing is False
        assert processing_signal[-1] is False
