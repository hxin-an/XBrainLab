"""Tests for ConversationHistory."""

from __future__ import annotations

import pytest

from XBrainLab.llm.agent.conversation import ConversationHistory


class TestConversationHistory:
    @pytest.mark.parametrize("prefix", ["System:", "Tool Output:"])
    def test_latest_human_request_is_not_classified_by_its_text(self, prefix):
        history = ConversationHistory()
        history.append("user", "Resample to 128 Hz.")
        latest = f"{prefix} Resample to 64 Hz."
        history.append("user", latest)

        assert history.latest_user_request_text() == latest

    def test_append_single(self):
        ch = ConversationHistory()
        ch.append("user", "hello")
        assert ch.messages == [{"role": "user", "content": "hello"}]

    def test_sliding_window(self):
        ch = ConversationHistory(max_size=3)
        for i in range(5):
            ch.append("user", str(i))
        assert ch.messages == [
            {"role": "user", "content": "2"},
            {"role": "user", "content": "3"},
            {"role": "user", "content": "4"},
        ]

    def test_clear(self):
        ch = ConversationHistory()
        ch.append("user", "hi")
        ch.clear()
        assert ch.messages == []

    def test_latest_user_request_excludes_host_feedback_and_empty_messages(self):
        history = ConversationHistory()
        assert history.latest_user_request_text() == ""
        history.append("user", "  Apply a 12 to 40 Hz bandpass filter.  ")
        history.append("assistant", "Preparing filter")
        history.append("internal", "System: Confirmation received")
        history.append("internal", "Tool Output: applied")
        history.append("internal", "Host feedback without a special prefix")
        history.append("user", "  ")
        assert (
            history.latest_user_request_text() == "Apply a 12 to 40 Hz bandpass filter."
        )
        history.clear()
        assert history.latest_user_request_text() == ""
