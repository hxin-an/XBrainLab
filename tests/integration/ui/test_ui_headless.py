from XBrainLab.backend.application import QueryStateCommand, get_application_service
from XBrainLab.ui.main_window import MainWindow

EXPECTED_NAV_TEXTS = [
    "Dataset",
    "Preprocess",
    "Training",
    "Evaluation",
    "Visualization",
]


def _checked_states(test_app):
    return [button.isChecked() for button in test_app.nav_btns]


def test_headless_app_fixture(test_app):
    """The fixture exposes the product MainWindow contract in headless mode."""
    assert isinstance(test_app, MainWindow)
    assert test_app.isVisible()
    assert test_app.stack.count() == 5
    assert [button.text() for button in test_app.nav_btns] == EXPECTED_NAV_TEXTS
    assert test_app.stack.currentIndex() == 0
    assert _checked_states(test_app) == [True, False, False, False, False]


def test_panel_switching_via_controller(test_app, qtbot):
    """
    Verify that we can switch panels using MainWindow's method.
    Agent would trigger this via 'SwitchPanelTool'.
    """
    # MainWindow uses QStackedWidget
    # Indices: 0:Dataset, 1:Preprocess, 2:Training, 3:Evaluation, 4:Visualization

    assert test_app.stack.currentIndex() == 0
    assert _checked_states(test_app) == [True, False, False, False, False]

    test_app.switch_page(1)
    qtbot.wait(100)
    assert test_app.stack.currentIndex() == 1
    assert _checked_states(test_app) == [False, True, False, False, False]

    test_app.switch_page(2)
    qtbot.wait(100)
    assert test_app.stack.currentIndex() == 2
    assert _checked_states(test_app) == [False, False, True, False, False]


def test_real_tool_access(test_app):
    """Headless UI tools read exact empty-state summary through ApplicationService."""
    study = test_app.study
    service = get_application_service(study)

    result = service.execute(QueryStateCommand(query="data_summary"))
    summary = dict(result.diagnostics)
    assert result.ok, result.message
    assert result.message == "Dataset summary ready."
    assert summary == {
        "count": 0,
        "files": [],
        "formats": [],
        "channels": [],
        "metadata": [],
        "total": 0,
        "unique_count": 0,
        "unique_labels": [],
        "runtime_signals": [],
        "gdf_duplicate_channel_files": [],
        "gdf_duplicate_channel_details": [],
    }
