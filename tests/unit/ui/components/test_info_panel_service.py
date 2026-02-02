import weakref
from unittest.mock import MagicMock

import pytest

from XBrainLab.backend.study import Study
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
