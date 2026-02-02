from unittest.mock import MagicMock

import pytest

from XBrainLab.backend.study import Study
from XBrainLab.backend.utils.observer import Observable
from XBrainLab.ui.core.observer_bridge import QtObserverBridge

try:
    # Check if PyQt6 is installed
    import PyQt6.QtCore  # noqa: F401

    has_pyqt = True
except ImportError:
    has_pyqt = False


class MockController(Observable):
    def __init__(self, study):
        super().__init__()
        self.study = study


class TestStudySingleton:
    def test_get_controller_singleton(self):
        """Test that study.get_controller returns the same instance."""
        study = Study()

        # Test with built-in controllers
        # lazy import should work if paths are correct.

        # Testing DatasetController
        ctrl1 = study.get_controller("dataset")
        ctrl2 = study.get_controller("dataset")
        assert ctrl1 is ctrl2, "get_controller should return the same instance"
        assert ctrl1.study is study

        # Testing PreprocessController
        ctrl3 = study.get_controller("preprocess")
        ctrl4 = study.get_controller("preprocess")
        assert ctrl3 is ctrl4
        assert ctrl3 is not ctrl1

    def test_get_controller_invalid_type(self):
        study = Study()
        with pytest.raises(ValueError, match="Unknown controller type"):
            study.get_controller("invalid_type")


@pytest.mark.skipif(not has_pyqt, reason="PyQt6 not installed")
class TestQtObserverBridge:
    def test_bridge_emission(self):
        """Test that Observer events trigger Qt processing (mocked)."""
        # Setup
        observable = MockController(None)

        # Ideally we'd use a real QObject/Signal, but for unit test we can mock
        # connect_to. Since we can't easily spin a Qt loop in headless unit
        # we will verify the logic of 'update' method.

        bridge = QtObserverBridge(observable, "test_event", None)

        # Connect a mock slot
        mock_slot = MagicMock()
        bridge.triggered.connect(mock_slot)

        # Trigger event
        bridge._on_event("arg1", arg2="val2")

        # Verify slot called
        mock_slot.assert_called_once_with(("arg1",), {"arg2": "val2"})
