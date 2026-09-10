"""Capture entrypoints must not inherit writable host preferences."""

import importlib
import os
import sys
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from PyQt6.QtCore import QByteArray, QSettings

from scripts.dev import capture_config
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.ui.qt_settings import application_settings


class _BeforeGui(RuntimeError):
    pass


@pytest.fixture
def capture_tmp(monkeypatch, tmp_path):
    created = []

    def owned_directory(**kwargs):
        directory = TemporaryDirectory(dir=tmp_path, **kwargs)
        created.append(Path(directory.name))
        return directory

    monkeypatch.setattr(capture_config, "TemporaryDirectory", owned_directory)
    return created


@pytest.mark.parametrize(
    ("module_name", "uses_assistant"),
    [
        ("capture_ui_baseline", False),
        ("capture_chatpanel_local_walkthrough", True),
        ("capture_chatpanel_local_tool_chain_walkthrough", True),
        ("capture_chatpanel_local_workflow_walkthrough", True),
        ("capture_visualization_render_walkthrough", False),
        ("capture_human_like_product_walkthrough", False),
        ("capture_chatpanel_ui_ux_walkthrough", False),
        ("capture_data_interpretation_replay", False),
        ("capture_ui_reviewer_fixes", False),
        ("capture_ui_polish_surfaces", False),
    ],
)
def test_main_isolates_preferences_before_gui_and_restores_host_on_failure(
    monkeypatch, tmp_path, capture_tmp, module_name, uses_assistant
):
    module = importlib.import_module(f"scripts.dev.{module_name}")
    host = tmp_path / "host config"
    monkeypatch.setenv("XBRAINLAB_CONFIG_DIR", str(host))
    monkeypatch.setenv(
        "XBRAINLAB_MODEL_CACHE_DIR", str(tmp_path / "existing model cache")
    )
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    config = LLMConfig(
        model_name="ibm-granite/granite-3.3-2b-instruct",
        device="cpu",
        cache_dir=str(tmp_path / "existing model cache"),
    )
    assert config.save_to_file(str(host / "settings.json"))
    host_bytes = (host / "settings.json").read_bytes()
    classified = []

    if uses_assistant:

        def classify(loaded):
            assert os.environ["XBRAINLAB_CONFIG_DIR"] == str(host)
            assert loaded.model_name == config.model_name
            assert loaded.cache_dir == config.cache_dir
            classified.append(loaded)
            return {"classification": "cpu-fallback"}

        monkeypatch.setattr(module, "classify_runtime", classify)
    if module_name == "capture_chatpanel_local_tool_chain_walkthrough":
        monkeypatch.setattr(
            module, "write_synthetic_raw_fif", lambda: tmp_path / "source.fif"
        )
    if module_name in (
        "capture_ui_baseline",
        "capture_human_like_product_walkthrough",
        "capture_ui_reviewer_fixes",
        "capture_ui_polish_surfaces",
    ):
        monkeypatch.setattr(module, "collect_source_identity", lambda *a, **k: {})
    if module_name == "capture_ui_reviewer_fixes":
        monkeypatch.setattr(module, "_fixture_evidence", lambda _path: {})
    if module_name == "capture_data_interpretation_replay":
        monkeypatch.setattr(
            module.ARTIFACT_PATHS, "directory", module.ARTIFACT_PATHS.directory
        )

    roots = []

    def before_gui(_argv):
        isolated = Path(os.environ["XBRAINLAB_CONFIG_DIR"])
        assert isolated != host
        assert isolated.is_dir()
        roots.append(isolated)
        settings = application_settings()
        assert settings.format() == QSettings.Format.IniFormat
        assert Path(settings.fileName()).is_relative_to(isolated)
        settings.setValue("capture-probe", QByteArray(b"isolated"))
        settings.sync()
        assert application_settings().value("capture-probe") == QByteArray(b"isolated")
        if uses_assistant:
            assert len(classified) == 1
            loaded = LLMConfig.load_from_file()
            assert loaded is not None
            assert loaded.model_name == config.model_name
            assert loaded.cache_dir == config.cache_dir
        else:
            assert not (isolated / "settings.json").exists()
        raise _BeforeGui

    class BeforeGuiApplication:
        @staticmethod
        def instance():
            return None

        def __init__(self, argv):
            before_gui(argv)

    monkeypatch.setattr(module, "QApplication", BeforeGuiApplication)
    argv = [module_name, "--output-dir", str(tmp_path / "outputs")]
    if module_name == "capture_visualization_render_walkthrough":
        argv.extend(["--training-output-dir", str(tmp_path / "training")])
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(_BeforeGui):
        module.main()

    assert os.environ["XBRAINLAB_CONFIG_DIR"] == str(host)
    assert (host / "settings.json").read_bytes() == host_bytes
    assert not (host / "qt-settings").exists()
    assert roots and all(not root.exists() for root in roots)


@pytest.mark.parametrize("previous", [None, ""])
@pytest.mark.parametrize("fail", [False, True])
def test_capture_config_lifetime_restores_missing_or_empty_override(
    monkeypatch, capture_tmp, previous, fail
):
    if previous is None:
        monkeypatch.delenv("XBRAINLAB_CONFIG_DIR", raising=False)
    else:
        monkeypatch.setenv("XBRAINLAB_CONFIG_DIR", previous)
    expected = pytest.raises(_BeforeGui) if fail else nullcontext()

    with expected, capture_config.isolated_capture_config() as root:
        assert root.is_dir()
        assert os.environ["XBRAINLAB_CONFIG_DIR"] == str(root)
        settings = application_settings("SmartParser")
        assert Path(settings.fileName()).is_relative_to(root)
        settings.setValue("mode", 3)
        settings.sync()
        assert application_settings("SmartParser").value("mode", type=int) == 3
        if fail:
            raise _BeforeGui

    assert os.environ.get("XBRAINLAB_CONFIG_DIR") == previous
    assert capture_tmp and all(not path.exists() for path in capture_tmp)


def test_capture_config_copy_failure_never_yields_and_restores_host(
    monkeypatch, tmp_path, capture_tmp
):
    host = str(tmp_path / "host")
    monkeypatch.setenv("XBRAINLAB_CONFIG_DIR", host)
    config = LLMConfig(device="cpu")
    monkeypatch.setattr(config, "save_to_file", lambda _path: False)

    with (
        pytest.raises(RuntimeError, match="Could not copy Assistant settings"),
        capture_config.isolated_capture_config(config),
    ):
        pytest.fail("Failed settings copy must not admit GUI construction")

    assert os.environ["XBRAINLAB_CONFIG_DIR"] == host
    assert capture_tmp and all(not path.exists() for path in capture_tmp)


@pytest.mark.parametrize("fail_during_preparation", [False, True])
def test_deactivation_capture_restores_explicit_settings_binding_on_failure(
    monkeypatch, tmp_path, capture_tmp, fail_during_preparation
):
    from scripts.dev import capture_chatpanel_local_workflow_walkthrough as workflow

    original = LLMConfig.__dict__["_default_settings_path"]
    monkeypatch.setattr(LLMConfig, "_default_settings_path", original)
    monkeypatch.setattr(workflow.tempfile, "gettempdir", lambda: str(tmp_path))
    host = str(tmp_path / "host")
    monkeypatch.setenv("XBRAINLAB_CONFIG_DIR", host)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    explicit = tmp_path / "chosen-assistant.json"
    monkeypatch.setattr(
        workflow, "classify_runtime", lambda _config: {"classification": "cpu-fallback"}
    )

    def before_gui(_argv):
        assert LLMConfig._default_settings_path() == str(explicit.resolve())
        root = Path(os.environ["XBRAINLAB_CONFIG_DIR"])
        assert root != Path(host)
        assert not (root / "settings.json").exists()
        loaded = LLMConfig.load_from_file()
        assert loaded is not None and loaded.local_runtime_notice_acknowledged
        raise _BeforeGui

    if fail_during_preparation:

        def broken_preparation(path):
            monkeypatch.setattr(
                LLMConfig, "_default_settings_path", staticmethod(lambda: str(path))
            )
            raise _BeforeGui

        monkeypatch.setattr(workflow, "_prepare_isolated_settings", broken_preparation)
    monkeypatch.setattr(workflow, "QApplication", before_gui)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "workflow",
            "--output-dir",
            str(tmp_path / "outputs"),
            "--exercise-deactivation",
            "--isolated-settings-path",
            str(explicit),
        ],
    )
    with pytest.raises(_BeforeGui):
        workflow.main()

    assert LLMConfig.__dict__["_default_settings_path"] is original
    assert os.environ["XBRAINLAB_CONFIG_DIR"] == host
    assert all(not path.exists() for path in capture_tmp)
