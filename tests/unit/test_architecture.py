import pytest

from XBrainLab.backend.study import Study


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
