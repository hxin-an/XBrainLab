"""Tests for AgentMetricsTracker and TurnMetrics."""

from __future__ import annotations

import gc
import time
import weakref

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
        m.record_tool("import_eeg_data", True, 150.0)
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
        assert t.last_completed_turn is None

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
        assert t.last_completed_turn is finished

    def test_finish_turn_none(self):
        t = AgentMetricsTracker()
        assert t.finish_turn() is None

    def test_start_turn_auto_finalizes_previous(self):
        t = AgentMetricsTracker()
        turn1 = t.start_turn()
        turn1.input_chars = 50
        turn2 = t.start_turn()
        assert t.last_completed_turn is turn1
        assert t.current_turn is turn2

    def test_tracker_releases_superseded_completed_turns(self):
        t = AgentMetricsTracker()
        turn1 = t.start_turn()
        reference = weakref.ref(turn1)
        t.finish_turn()
        assert t.last_completed_turn is turn1
        del turn1
        turn2 = t.start_turn()
        t.finish_turn()
        gc.collect()
        assert reference() is None
        assert t.last_completed_turn is turn2
        reset_reference = weakref.ref(turn2)
        del turn2
        t.reset()
        gc.collect()
        assert reset_reference() is None

    def test_reset(self):
        t = AgentMetricsTracker()
        old_id = t.conversation_id
        t.start_turn()
        t.finish_turn()
        t.reset()
        assert t.conversation_id != old_id
        assert t.current_turn is None
        assert t.last_completed_turn is None
