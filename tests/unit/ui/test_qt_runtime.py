from unittest.mock import patch

from PyQt6.QtCore import QEvent

from XBrainLab.ui.qt_runtime import (
    configure_qt_platform_for_runtime,
    drain_qt_runtime_after_event_loop,
    is_wslg_session,
    run_qt_event_loop,
)


def test_configure_qt_platform_defaults_wslg_to_xcb():
    env = {
        "WSL_DISTRO_NAME": "Ubuntu-24.04",
        "WSL_INTEROP": "/run/WSL/123_interop",
        "DISPLAY": ":0",
        "WAYLAND_DISPLAY": "wayland-0",
    }

    applied = configure_qt_platform_for_runtime(env)

    assert applied == "xcb"
    assert env["QT_QPA_PLATFORM"] == "xcb"


def test_configure_qt_platform_respects_explicit_platform():
    env = {
        "QT_QPA_PLATFORM": "offscreen",
        "WSL_DISTRO_NAME": "Ubuntu-24.04",
        "DISPLAY": ":0",
        "WAYLAND_DISPLAY": "wayland-0",
    }

    applied = configure_qt_platform_for_runtime(env)

    assert applied is None
    assert env["QT_QPA_PLATFORM"] == "offscreen"


def test_configure_qt_platform_uses_xbrainlab_override():
    env = {
        "XBRAINLAB_QT_PLATFORM": "minimal",
        "WSL_DISTRO_NAME": "Ubuntu-24.04",
        "DISPLAY": ":0",
        "WAYLAND_DISPLAY": "wayland-0",
    }

    applied = configure_qt_platform_for_runtime(env)

    assert applied == "minimal"
    assert env["QT_QPA_PLATFORM"] == "minimal"


def test_configure_qt_platform_leaves_non_wslg_runtime_unset():
    env = {"DISPLAY": ":0"}

    applied = configure_qt_platform_for_runtime(env)

    assert applied is None
    assert "QT_QPA_PLATFORM" not in env


def test_is_wslg_session_requires_wsl_and_display_pair():
    assert is_wslg_session(
        {
            "WSL_DISTRO_NAME": "Ubuntu",
            "DISPLAY": ":0",
            "WAYLAND_DISPLAY": "wayland-0",
        }
    )
    assert not is_wslg_session({"DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0"})
    assert not is_wslg_session({"WSL_DISTRO_NAME": "Ubuntu", "DISPLAY": ":0"})


def test_drain_qt_runtime_processes_deferred_deletes_before_python_gc():
    calls: list[tuple[str, object | None]] = []

    class _App:
        def sendPostedEvents(self, _receiver, event_type) -> None:
            calls.append(("posted", event_type))

        def processEvents(self) -> None:
            calls.append(("events", None))

    with patch("XBrainLab.ui.qt_runtime.gc.collect") as collect:
        drain_qt_runtime_after_event_loop(_App(), cycles=2)

    assert calls == [
        ("posted", QEvent.Type.DeferredDelete),
        ("events", None),
        ("posted", QEvent.Type.DeferredDelete),
        ("events", None),
    ]
    assert collect.call_count == 2


def test_run_qt_event_loop_drains_before_returning_exit_code():
    calls: list[str] = []

    class _App:
        def exec(self) -> int:
            calls.append("exec")
            return 7

    app = _App()
    with patch("XBrainLab.ui.qt_runtime.drain_qt_runtime_after_event_loop") as drain:
        assert run_qt_event_loop(app) == 7

    assert calls == ["exec"]
    drain.assert_called_once_with(app)
