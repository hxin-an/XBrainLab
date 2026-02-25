"""Unit tests for UI utils — CheckboxObj."""

from XBrainLab.ui.core.utils import CheckboxObj


class TestCheckboxObj:
    def test_init_value(self):
        cb = CheckboxObj(True)
        assert cb.ctrl is True

    def test_call_updates_state(self):
        cb = CheckboxObj(False)
        cb(True)
        assert cb.ctrl is True

    def test_callback_invoked(self):
        received = []
        cb = CheckboxObj(0, callback=received.append)
        cb(42)
        assert cb.ctrl == 42
        assert received == [42]

    def test_no_callback(self):
        cb = CheckboxObj(0, callback=None)
        cb(1)  # should not raise
        assert cb.ctrl == 1

    def test_multiple_calls(self):
        calls = []
        cb = CheckboxObj("a", callback=calls.append)
        cb("b")
        cb("c")
        assert cb.ctrl == "c"
        assert calls == ["b", "c"]
