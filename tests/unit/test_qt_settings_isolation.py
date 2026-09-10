"""Pytest must exercise real Qt preferences without touching the user's store."""

from pathlib import Path

import pytest
from PyQt6.QtCore import QByteArray, QSettings

from XBrainLab.ui.window_geometry_lifecycle import application_settings


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
    window = application_settings()
    montage = QSettings("XBrainLab", "MontagePicker")
    parser = QSettings("XBrainLab", "SmartParser")
    for settings in (window, montage, parser):
        assert settings.format() == QSettings.Format.IniFormat
        assert Path(settings.fileName()).is_relative_to(tmp_path)
        assert not settings.contains("isolation_probe")

    assert len({settings.fileName() for settings in (window, montage, parser)}) == 3
    window.setValue("isolation_probe", "window-only")
    window.sync()

    assert application_settings().value("isolation_probe") == "window-only"
    assert not montage.contains("isolation_probe")
    assert not parser.contains("isolation_probe")


def test_explicit_ini_constructor_keeps_its_requested_path(tmp_path):
    path = tmp_path / "explicit.ini"
    settings = QSettings(str(path), QSettings.Format.IniFormat)
    assert Path(settings.fileName()) == path
    settings.setValue("explicit", "kept")
    settings.sync()
    assert QSettings(str(path), QSettings.Format.IniFormat).value("explicit") == "kept"


def test_geometry_preferences_honor_the_explicit_product_config_root(
    monkeypatch, tmp_path
):
    config_root = tmp_path / "chosen product config"
    monkeypatch.setenv("XBRAINLAB_CONFIG_DIR", str(config_root))

    settings = application_settings()

    # Fail before writing if a smoke/capture config root does not reach Qt.
    assert Path(settings.fileName()).is_relative_to(config_root)
    assert settings.format() == QSettings.Format.IniFormat
    settings.setValue("main_window/geometry", QByteArray(b"geometry"))
    settings.sync()
    assert application_settings().value("main_window/geometry") == QByteArray(
        b"geometry"
    )


def test_product_config_override_preserves_application_partitioning(
    monkeypatch, tmp_path
):
    config_root = tmp_path / "chosen product config"
    monkeypatch.setenv("XBRAINLAB_CONFIG_DIR", str(config_root))
    names = ("XBrainLab", "MontagePicker", "SmartParser")
    stores = [application_settings(name) for name in names]
    for name, settings in zip(names, stores, strict=True):
        assert settings.format() == QSettings.Format.IniFormat
        assert Path(settings.fileName()).is_relative_to(config_root)
        assert not settings.contains("partition")
        settings.setValue("partition", name)
        settings.sync()
        assert settings.status() == QSettings.Status.NoError

    assert len({settings.fileName() for settings in stores}) == 3
    assert [application_settings(name).value("partition") for name in names] == list(
        names
    )


def test_inherited_product_config_does_not_escape_per_test_qt_storage(
    monkeypatch, tmp_path, tmp_path_factory
):
    inherited_root = tmp_path_factory.mktemp("inherited-config")
    monkeypatch.setenv("XBRAINLAB_CONFIG_DIR", str(inherited_root))
    settings = application_settings()
    assert Path(settings.fileName()).is_relative_to(tmp_path)
    settings.setValue("isolation_probe", "per-test")
    settings.sync()
    assert application_settings().value("isolation_probe") == "per-test"
    assert not (inherited_root / "qt-settings").exists()


@pytest.mark.parametrize("override", [None, "", "   "])
def test_normal_launch_keeps_the_native_organization_and_application(
    monkeypatch, override
):
    from XBrainLab.ui import qt_settings

    if override is None:
        monkeypatch.delenv("XBRAINLAB_CONFIG_DIR", raising=False)
    else:
        monkeypatch.setenv("XBRAINLAB_CONFIG_DIR", override)
    calls = []
    native_store = object()

    def native_constructor(*args):
        calls.append(args)
        return native_store

    # Isolate the real user store only; verify its exact existing constructor route.
    monkeypatch.setattr(qt_settings, "QSettings", native_constructor)
    assert application_settings("MontagePicker") is native_store
    assert calls == [("XBrainLab", "MontagePicker")]
