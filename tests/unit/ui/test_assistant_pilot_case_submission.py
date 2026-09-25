"""Real composer regression for the case host's fill-before-readiness sequence.

These tests observe the normal UI submission signal, not model admission or
inference; real controller/runtime execution is separate engineering evidence.
"""

from time import perf_counter_ns

import pytest
from PyQt6.QtCore import QTimer

from scripts.dev.assistant_pilot_case import poll_case_safely, submit_case_input
from XBrainLab.ui.chat.panel import ChatPanel


def test_empty_composer_is_disabled_then_real_submission_after_fill(qtbot):
    panel = ChatPanel()
    qtbot.addWidget(panel)
    panel.resize(480, 720)
    panel.show()
    panel.set_runtime_state("ready")
    assert panel.input_field.isEnabled()
    assert not panel.send_btn.isEnabled()
    submissions = []
    panel.send_message.connect(
        lambda text: submissions.append((text, perf_counter_ns()))
    )
    panel.send_btn.click()
    assert not submissions

    def wait_until(predicate, _seconds):
        qtbot.waitUntil(predicate, timeout=250)
        assert panel.input_field.toPlainText() == "Inspect the current workflow."
        assert panel.send_btn.isEnabled()

    seconds, nanoseconds = submit_case_input(
        panel, "Inspect the current workflow.", wait_until
    )
    assert len(submissions) == 1
    assert submissions[0][0] == "Inspect the current workflow."
    assert nanoseconds <= submissions[0][1]
    assert abs(seconds - nanoseconds / 1e9) < 0.01


@pytest.mark.parametrize(
    "runtime_state,text", [("ready", "   "), ("loading", "Inspect data.")]
)
def test_case_host_does_not_click_until_real_composer_admits_submission(
    qtbot, runtime_state, text
):
    panel = ChatPanel()
    qtbot.addWidget(panel)
    panel.set_runtime_state(runtime_state)
    submissions = []
    panel.send_message.connect(submissions.append)

    def wait_until(predicate, _seconds):
        qtbot.waitUntil(predicate, timeout=50)

    with pytest.raises(qtbot.TimeoutError):
        submit_case_input(panel, text, wait_until)
    assert not panel.send_btn.isEnabled()
    assert not submissions
    assert panel.input_field.toPlainText() == text


@pytest.mark.parametrize("stop_raises", [False, True])
def test_actual_qtimer_poll_error_is_preserved_and_stops_timer(qtbot, stop_raises):
    result = {"issues": []}
    poll = QTimer()
    poll.setInterval(1)
    calls, stopped, terminals = [], [], []

    def broken_observation():
        calls.append(True)
        raise ValueError("invalid observation clock")

    def stop_generation():
        stopped.append(True)
        if stop_raises:
            raise RuntimeError("stop transport unavailable")

    def observe():
        terminals.append(
            poll_case_safely(
                broken_observation,
                result,
                stop_poll=poll.stop,
                stop_generation=stop_generation,
            )
        )

    poll.timeout.connect(observe)
    poll.start()
    qtbot.waitUntil(lambda: bool(terminals), timeout=1000)
    assert terminals == [False]
    assert calls == [True]
    assert stopped == [True]
    assert not poll.isActive()
    assert result["issues"] == ["poll_callback_failed"]
    assert result["poll_error"] == {
        "error_type": "ValueError",
        "detail": "invalid observation clock",
    }
    if stop_raises:
        assert result["poll_stop_errors"] == [
            {
                "operation": "stop_generation",
                "error_type": "RuntimeError",
                "detail": "stop transport unavailable",
            }
        ]
    else:
        assert not result.get("poll_stop_errors")
