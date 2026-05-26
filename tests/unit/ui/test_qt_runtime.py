from XBrainLab.ui.qt_runtime import configure_qt_platform_for_runtime, is_wslg_session


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
