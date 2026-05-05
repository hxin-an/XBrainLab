import weakref
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from XBrainLab.backend.study import Study
from XBrainLab.backend.utils.observer import Observable
from XBrainLab.ui.components.info_panel_service import InfoPanelService


@pytest.fixture
def study_mock():
    study = MagicMock(spec=Study)
    # Mock controllers
    study.get_controller.return_value = MagicMock()
    return study


@pytest.fixture
def service(study_mock):
    return InfoPanelService(study_mock)


def test_service_initialization(service, study_mock):
    """Test that bridges are set up on init."""
    assert service.study == study_mock
    # Check if bridges connected
    # Since bridges are internal, we assume success if no error, or check functionality


def test_register_and_notify(service, study_mock):
    """Test registering a panel and notifying it."""
    panel_mock = MagicMock()

    # 1. Register
    service.register(panel_mock)
    assert panel_mock in service._listeners

    # Register should trigger an initial update
    assert panel_mock.update_info.called

    # 2. Notify
    # Setup mock data return
    dataset_ctrl = study_mock.get_controller("dataset")
    dataset_ctrl.get_loaded_data_list.return_value = ["loaded_data"]

    preprocess_ctrl = study_mock.get_controller("preprocess")
    preprocess_ctrl.get_preprocessed_data_list.return_value = ["prep_data"]

    # Trigger notification
    service.notify_all()

    # Check if panel called with correct args
    panel_mock.update_info.assert_called_with(
        loaded_data_list=["loaded_data"], preprocessed_data_list=["prep_data"]
    )


def test_successful_legacy_import_updates_info_once(qtbot):
    """data_changed owns successful legacy import refresh for info panels."""

    class DatasetController(Observable):
        def get_loaded_data_list(self):
            return ["raw"]

    class PreprocessController(Observable):
        def get_preprocessed_data_list(self):
            return []

    class StudyLike:
        def __init__(self):
            self.dataset = DatasetController()
            self.preprocess = PreprocessController()

        def get_controller(self, name):
            return {"dataset": self.dataset, "preprocess": self.preprocess}[name]

    study = StudyLike()
    service = InfoPanelService(cast(Any, study))
    panel = MagicMock()
    service.register(panel)
    panel.update_info.reset_mock()

    study.dataset.notify("data_changed")
    qtbot.wait(50)
    study.dataset.notify("import_finished", 1, [])
    qtbot.wait(50)

    panel.update_info.assert_called_once_with(
        loaded_data_list=["raw"],
        preprocessed_data_list=[],
    )


def test_weak_ref_cleanup(service):
    """Test that service doesn't hold strong refs to panels."""

    class MockPanel:
        def update_info(self, **kwargs):
            pass

    panel = MockPanel()
    service.register(panel)

    assert panel in service._listeners

    del panel
    # Force gc if needed, but WeakSet should handle it
    # note: locally 'panel' is gone, but we can't easily assert weakref collection in simple sync test without gc.collect()
    # But we can check that it IS a WeakSet
    assert isinstance(service._listeners, weakref.WeakSet)
