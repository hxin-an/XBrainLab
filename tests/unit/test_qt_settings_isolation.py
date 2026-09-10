"""Pytest must exercise real Qt preferences without touching the user's store."""

from pathlib import Path

import pytest
from PyQt6.QtCore import QByteArray, QSettings

from XBrainLab.ui.window_geometry_lifecycle import _default_settings


@pytest.mark.parametrize("application", ("XBrainLab", "MontagePicker", "SmartParser"))
def test_product_preferences_use_real_per_test_storage(tmp_path, application):
    settings = QSettings("XBrainLab", application)
    # Fail before writing if the constructor still targets the native user store.
    assert settings.format() == QSettings.Format.IniFormat
    assert Path(settings.fileName()).is_relative_to(tmp_path)
    assert not settings.contains("isolation_probe")

    value = QByteArray(b"\x00geometry-roundtrip\xff")
    settings.setValue("isolation_probe", value)
    settings.sync()

    assert settings.status() == QSettings.Status.NoError
    assert Path(settings.fileName()).is_file()
    reopened = QSettings("XBrainLab", application)
    assert reopened.value("isolation_probe") == value


def test_preimported_owner_alias_and_app_names_remain_isolated(tmp_path):
    window = _default_settings()
    montage = QSettings("XBrainLab", "MontagePicker")
    parser = QSettings("XBrainLab", "SmartParser")
    for settings in (window, montage, parser):
        assert settings.format() == QSettings.Format.IniFormat
        assert Path(settings.fileName()).is_relative_to(tmp_path)
        assert not settings.contains("isolation_probe")

    assert len({settings.fileName() for settings in (window, montage, parser)}) == 3
    window.setValue("isolation_probe", "window-only")
    window.sync()

    assert _default_settings().value("isolation_probe") == "window-only"
    assert not montage.contains("isolation_probe")
    assert not parser.contains("isolation_probe")


def test_explicit_ini_constructor_keeps_its_requested_path(tmp_path):
    path = tmp_path / "explicit.ini"
    settings = QSettings(str(path), QSettings.Format.IniFormat)
    assert Path(settings.fileName()) == path
    settings.setValue("explicit", "kept")
    settings.sync()
    assert QSettings(str(path), QSettings.Format.IniFormat).value("explicit") == "kept"
