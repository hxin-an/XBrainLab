"""Unit tests for :mod:`XBrainLab.llm.agent.confidence`."""

from __future__ import annotations

from XBrainLab.llm.agent.confidence import estimate_confidence

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
_KNOWN = frozenset({"load_data", "run_training", "set_model"})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEstimateConfidence:
    """Verifies the heuristic confidence estimator."""

    def test_empty_commands_returns_zero(self):
        assert estimate_confidence("anything", [], known_tools=_KNOWN) == 0.0

    def test_perfect_response_near_one(self):
        text = '```json\n{"tool": "load_data", "params": {"path": "/a"}}\n```'
        cmds = [("load_data", {"path": "/a"})]
        score = estimate_confidence(text, cmds, known_tools=_KNOWN)
        assert score >= 0.85

    def test_no_fence_lowers_score(self):
        text = '{"tool": "load_data", "params": {"path": "/a"}}'
        cmds = [("load_data", {"path": "/a"})]
        score = estimate_confidence(text, cmds, known_tools=_KNOWN)
        assert score < 1.0

    def test_unknown_tool_lowers_score(self):
        text = '```json\n{"tool": "delete_everything"}\n```'
        cmds = [("delete_everything", {"x": 1})]
        score = estimate_confidence(text, cmds, known_tools=_KNOWN)
        # Known-tool bonus absent → lower
        assert score < 0.9

    def test_hedging_language_lowers_score(self):
        text = 'I think ```json\n{"tool": "load_data", "params": {"p": 1}}\n```'
        cmds = [("load_data", {"p": 1})]
        high = estimate_confidence(
            '```json\n{"tool": "load_data", "params": {"p": 1}}\n```',
            cmds,
            known_tools=_KNOWN,
        )
        low = estimate_confidence(text, cmds, known_tools=_KNOWN)
        assert low < high

    def test_multiple_commands_reduces_score(self):
        text = '```json\n[{"tool": "load_data"}, {"tool": "set_model"}]\n```'
        single = [("load_data", {"p": 1})]
        multi = [("load_data", {"p": 1}), ("set_model", {"m": "x"})]
        s1 = estimate_confidence(text, single, known_tools=_KNOWN)
        s2 = estimate_confidence(text, multi, known_tools=_KNOWN)
        assert s1 > s2

    def test_empty_params_lowers_score(self):
        text = '```json\n{"tool": "load_data"}\n```'
        cmds_full = [("load_data", {"path": "/a"})]
        cmds_empty = [("load_data", {})]
        f = estimate_confidence(text, cmds_full, known_tools=_KNOWN)
        e = estimate_confidence(text, cmds_empty, known_tools=_KNOWN)
        assert f > e

    def test_score_bounded_zero_one(self):
        """Score should always be in [0, 1]."""
        text = '```json\n{"tool": "load_data", "params": {"x": 1}}\n```'
        cmds = [("load_data", {"x": 1})]
        score = estimate_confidence(text, cmds, known_tools=_KNOWN)
        assert 0.0 <= score <= 1.0

    def test_default_known_tools_used(self):
        """When *known_tools* is ``None`` the module default is used."""
        text = '```json\n{"tool": "load_data", "params": {"p": 1}}\n```'
        cmds = [("load_data", {"p": 1})]
        # load_data IS in the default set → should get the bonus
        score = estimate_confidence(text, cmds)
        assert score >= 0.7
