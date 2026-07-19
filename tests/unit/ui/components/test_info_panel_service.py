import weakref
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.backend.study import Study
from XBrainLab.backend.utils.observer import Observable
from XBrainLab.ui.components.info_panel_service import InfoPanelService


class FakeDatasetController(Observable):
    def __init__(self) -> None:
        super().__init__()
        self.loaded_data_list: list[object] = []

    def get_loaded_data_list(self) -> list[object]:
        return list(self.loaded_data_list)


class FakePreprocessController(Observable):
    def __init__(self) -> None:
        super().__init__()
        self.preprocessed_data_list: list[object] = []

    def get_preprocessed_data_list(self) -> list[object]:
        return list(self.preprocessed_data_list)


class FakeInfoPanelStudy:
    def __init__(self) -> None:
        self.controllers = {
            "dataset": FakeDatasetController(),
            "preprocess": FakePreprocessController(),
        }

    def get_controller(self, controller_type: str) -> Observable:
        return self.controllers[controller_type]


@pytest.fixture
def compatibility_study() -> FakeInfoPanelStudy:
    return FakeInfoPanelStudy()


@pytest.fixture
def service(compatibility_study):
    return InfoPanelService(compatibility_study)


def test_service_initialization(service, compatibility_study):
    assert service.study == compatibility_study
    assert service._observes_controller_events is True
    assert service.dataset_bridge.observable is compatibility_study.get_controller(
        "dataset"
    )
    assert service.dataset_bridge.event_name == "data_changed"
    assert service.preprocess_bridge.observable is compatibility_study.get_controller(
        "preprocess"
    )
    assert service.preprocess_bridge.event_name == "preprocess_changed"


def test_service_can_delegate_observer_refresh_to_main_window_coordinator(
    compatibility_study,
):
    """MainWindow can own event refresh without duplicate InfoPanelService bridges."""
    service = InfoPanelService(compatibility_study, observe_controller_events=False)

    assert service.study == compatibility_study
    assert service._observes_controller_events is False
    assert not hasattr(service, "dataset_bridge")
    assert not hasattr(service, "preprocess_bridge")


def test_real_study_info_service_does_not_subscribe_direct_controller_bridges():
    study = Study()

    def fail_controller_lookup(_name: str):
        raise AssertionError("real Study controller bridge is not allowed")

    cast(Any, study).get_controller = fail_controller_lookup

    service = InfoPanelService(study)

    assert not hasattr(service, "dataset_bridge")
    assert not hasattr(service, "preprocess_bridge")


def test_register_and_notify(service, compatibility_study):
    """Test registering a panel and notifying it."""
    panel_mock = MagicMock()

    # 1. Register
    service.register(panel_mock)
    assert panel_mock in service._listeners

    # Register should trigger an initial update
    assert panel_mock.update_info.called

    # 2. Notify
    # Setup mock data return
    dataset_ctrl = compatibility_study.get_controller("dataset")
    dataset_ctrl.loaded_data_list = ["loaded_data"]

    preprocess_ctrl = compatibility_study.get_controller("preprocess")
    preprocess_ctrl.preprocessed_data_list = ["prep_data"]

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

        def get_controller(self, controller_type: str) -> Observable:
            return {
                "dataset": self.dataset,
                "preprocess": self.preprocess,
            }[controller_type]

    study = StudyLike()
    service = InfoPanelService(study)
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


def test_real_study_query_failure_does_not_fallback_to_controller_lists():
    study = Study()
    service = InfoPanelService(study)
    study.get_controller("dataset").get_loaded_data_list = MagicMock(
        side_effect=AssertionError("stale loaded list should not be read"),
    )
    study.get_controller("preprocess").get_preprocessed_data_list = MagicMock(
        side_effect=AssertionError("stale preprocessed list should not be read"),
    )
    panel = MagicMock()

    with patch(
        "XBrainLab.ui.components.info_panel_service.execute_application_command",
        MagicMock(return_value=SimpleNamespace(ok=False, message="query failed")),
    ) as execute_command:
        service.register(panel)

    execute_command.assert_called_once()
    assert execute_command.call_args.kwargs == {"refresh": False}
    panel.update_info.assert_called_once_with(
        loaded_data_list=[],
        preprocessed_data_list=[],
    )
    study.get_controller("dataset").get_loaded_data_list.assert_not_called()
    study.get_controller("preprocess").get_preprocessed_data_list.assert_not_called()


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


@pytest.mark.parametrize(
    "relative_path",
    [
        "XBrainLab/ui/components/info_panel_service.py",
        "XBrainLab/ui/dialogs/dataset/data_splitting_dialog.py",
        "XBrainLab/ui/panels/dataset/sidebar.py",
    ],
)
def test_product_ui_runtime_contracts_do_not_import_unittest_mock(
    relative_path: str,
) -> None:
    repo_root = Path(__file__).resolve().parents[4]

    source = (repo_root / relative_path).read_text(encoding="utf-8")

    assert "unittest.mock" not in source
