"""Tests for AgentMetricsTracker and TurnMetrics."""

from __future__ import annotations

import time

from XBrainLab.llm.agent.metrics import AgentMetricsTracker, TurnMetrics


class TestTurnMetrics:
    def test_defaults(self):
        m = TurnMetrics()
        assert m.input_chars == 0
        assert m.output_chars == 0
        assert m.llm_calls == 0
        assert m.tool_count == 0
        assert m.duration_ms == 0.0

    def test_token_estimation(self):
        m = TurnMetrics(input_chars=400, output_chars=200)
        assert m.estimated_input_tokens == 100
        assert m.estimated_output_tokens == 50

    def test_record_tool(self):
        m = TurnMetrics()
        m.record_tool("load_data", True, 150.0)
        m.record_tool("preprocess", False, 50.0, "file not found")
        assert m.tool_count == 2
        assert m.tool_success_count == 1
        assert m.tool_executions[1].error == "file not found"

    def test_finalize(self):
        m = TurnMetrics()
        # Override start_time to ensure measurable duration
        m.start_time = time.monotonic() - 0.1  # 100ms ago
        m.finalize()
        assert m.end_time > 0
        assert m.duration_ms >= 50  # at least 50ms

    def test_duration_before_finalize(self):
        m = TurnMetrics()
        assert m.duration_ms == 0.0


class TestAgentMetricsTracker:
    def test_init(self):
        t = AgentMetricsTracker()
        assert len(t.conversation_id) == 12
        assert t.current_turn is None
        assert t.total_turns == 0

    def test_start_turn(self):
        t = AgentMetricsTracker()
        turn = t.start_turn()
        assert turn.conversation_id == t.conversation_id
        assert t.current_turn is turn

    def test_finish_turn(self):
        t = AgentMetricsTracker()
        turn = t.start_turn()
        turn.input_chars = 100
        turn.output_chars = 200
        finished = t.finish_turn()
        assert finished is turn
        assert finished.end_time > 0
        assert t.current_turn is None
        assert t.total_turns == 1

    def test_finish_turn_none(self):
        t = AgentMetricsTracker()
        assert t.finish_turn() is None

    def test_start_turn_auto_finalizes_previous(self):
        t = AgentMetricsTracker()
        turn1 = t.start_turn()
        turn1.input_chars = 50
        turn2 = t.start_turn()
        assert t.total_turns == 1  # turn1 was auto-finalized
        assert t.current_turn is turn2

    def test_total_estimated_tokens(self):
        t = AgentMetricsTracker()
        turn1 = t.start_turn()
        turn1.input_chars = 400
        turn1.output_chars = 200
        t.finish_turn()

        turn2 = t.start_turn()
        turn2.input_chars = 800
        turn2.output_chars = 400
        t.finish_turn()

        # (400/4 + 200/4) + (800/4 + 400/4) = 150 + 300 = 450
        assert t.total_estimated_tokens == 450

    def test_reset(self):
        t = AgentMetricsTracker()
        old_id = t.conversation_id
        t.start_turn()
        t.finish_turn()
        t.reset()
        assert t.conversation_id != old_id
        assert t.current_turn is None
        assert t.total_turns == 0
