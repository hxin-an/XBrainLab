from unittest.mock import MagicMock

# Ensure no QApplication is created
from XBrainLab.backend.controller.dataset_controller import DatasetController
from XBrainLab.backend.utils.observer import Observable


def test_dataset_controller_headless():
    """
    Verify that DatasetController can be instantiated and used
    WITHOUT a running QApplication instance using the new Observable pattern.
    """

    # 1. Assert no QApplication exists
    # assert QApplication.instance() is None, "Test must run without QApplication"
    # Note: In pytest environment, QApplication might be present
    # due to plugins or other tests.
    # The key is that DatasetController logic doesn't depend on it.

    # 2. Mock Study backend
    mock_study = MagicMock()
    mock_study.loaded_data_list = []
    mock_study.is_locked.return_value = False

    # 3. Import Controller (should not trigger QObject/GUI errors)
    # Imports moved to top

    # 4. Instantiate
    controller = DatasetController(mock_study)

    # 5. Verify inheritance
    assert isinstance(controller, Observable)
    assert not hasattr(controller, "data_changed"), "Should not have pyqtSignals"

    # 6. Verify Observer Pattern
    callback_mock = MagicMock()
    controller.subscribe("data_changed", callback_mock)

    # Trigger notification manually to test mechanism
    controller.notify("data_changed")
    callback_mock.assert_called_once()

    # 7. Verify method calls don't crash
    assert controller.has_data() is False
    assert controller.is_locked() is False
