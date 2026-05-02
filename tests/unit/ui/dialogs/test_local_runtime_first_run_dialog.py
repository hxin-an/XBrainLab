from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.ui.dialogs.local_runtime_first_run_dialog import (
    LocalRuntimeFirstRunDialog,
)


def test_local_runtime_first_run_dialog_shows_preflight(qtbot, tmp_path):
    config = LLMConfig(cache_dir=str(tmp_path / "models"))
    dialog = LocalRuntimeFirstRunDialog(config=config)
    qtbot.addWidget(dialog)

    assert dialog.windowTitle() == "Local Assistant Runtime"
    assert dialog.download_btn.text() == "Download"
    assert dialog.later_btn.text() == "Later"
    assert dialog.disable_btn.text() == "Disable"
    assert "Use existing cache" in dialog.use_cache_btn.text()
    assert dialog.use_cache_btn.isEnabled() is False


def test_local_runtime_first_run_dialog_records_choice(qtbot, tmp_path):
    config = LLMConfig(cache_dir=str(tmp_path / "models"))
    dialog = LocalRuntimeFirstRunDialog(config=config)
    qtbot.addWidget(dialog)

    dialog._choose(LocalRuntimeFirstRunDialog.DISABLE)

    assert dialog.choice == LocalRuntimeFirstRunDialog.DISABLE
