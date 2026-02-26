"""Unit tests for XBrainLab package __init__."""

import XBrainLab


class TestPackageInit:
    """Package exposes __version__ and Study."""

    def test_version_is_string(self):
        assert isinstance(XBrainLab.__version__, str)

    def test_version_nonempty(self):
        assert len(XBrainLab.__version__) > 0

    def test_study_exported(self):
        assert callable(XBrainLab.Study)

    def test_all_contains_expected(self):
        assert "Study" in XBrainLab.__all__
        assert "__version__" in XBrainLab.__all__
