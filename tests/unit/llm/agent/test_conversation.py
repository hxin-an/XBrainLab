"""Tests for ConversationHistory."""

from __future__ import annotations

from XBrainLab.llm.agent.conversation import ConversationHistory


class TestConversationHistory:
    def test_append_single(self):
        ch = ConversationHistory()
        ch.append("user", "hello")
        assert len(ch) == 1
        assert ch[0] == {"role": "user", "content": "hello"}

    def test_sliding_window(self):
        ch = ConversationHistory(max_size=3)
        for i in range(5):
            ch.append("user", str(i))
        assert len(ch) == 3
        assert ch[0]["content"] == "2"

    def test_clear(self):
        ch = ConversationHistory()
        ch.append("user", "hi")
        ch.clear()
        assert len(ch) == 0

    def test_get_messages_returns_copy(self):
        ch = ConversationHistory()
        ch.append("user", "hi")
        msgs = ch.get_messages()
        msgs.clear()
        assert len(ch) == 1  # original not affected

    def test_eq_with_list(self):
        ch = ConversationHistory()
        ch.append("user", "hi")
        assert ch == [{"role": "user", "content": "hi"}]

    def test_eq_with_other_history(self):
        ch1 = ConversationHistory()
        ch2 = ConversationHistory()
        ch1.append("user", "hi")
        ch2.append("user", "hi")
        assert ch1 == ch2

    def test_repr(self):
        ch = ConversationHistory(max_size=10)
        ch.append("user", "hi")
        assert "1 msgs" in repr(ch)
        assert "max=10" in repr(ch)
