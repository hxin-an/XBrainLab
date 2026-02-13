from XBrainLab.backend.facade import BackendFacade


def test_headless_app_fixture(test_app):
    """
    Verify that the test_app fixture creates a valid MainWindow
    and that it is visible (exposed to the window system, even if headless).
    """
    assert test_app is not None
    assert test_app.isVisible()
    assert test_app.study is not None


def test_panel_switching_via_controller(test_app, qtbot):
    """
    Verify that we can switch panels using MainWindow's method.
    Agent would trigger this via 'SwitchPanelTool'.
    """
    # MainWindow uses QStackedWidget
    # Indices: 0:Dataset, 1:Preprocess, 2:Training, 3:Evaluation, 4:Visualization

    # 1. Initial State
    assert test_app.stack.currentIndex() == 0

    # 2. Switch to Preprocess (Index 1)
    test_app.switch_page(1)
    qtbot.wait(100)
    assert test_app.stack.currentIndex() == 1

    # 3. Switch to Training (Index 2)
    test_app.switch_page(2)
    qtbot.wait(100)
    assert test_app.stack.currentIndex() == 2


def test_real_tool_access(test_app):
    """
    Verify that we can access the backend through the UI's study reference,
    mimicking what Real Tools do.
    """
    # Real Tools use BackendFacade(study)
    study = test_app.study
    facade = BackendFacade(study)

    # Verify Facade works
    summary = facade.get_data_summary()
    assert isinstance(summary, dict)
    assert "count" in summary
