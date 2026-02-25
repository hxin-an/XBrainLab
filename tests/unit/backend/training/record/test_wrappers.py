"""Unit tests for training/record/wrappers — ProxyRecord and PooledRecordWrapper."""

from unittest.mock import MagicMock

import numpy as np

from XBrainLab.backend.training.record.eval import EvalRecord
from XBrainLab.backend.training.record.wrappers import PooledRecordWrapper, ProxyRecord


class TestProxyRecord:
    def test_creates_eval_record(self):
        labels = np.array([0, 1, 2])
        outputs = np.array([[0.1, 0.9], [0.8, 0.2], [0.3, 0.7]])
        proxy = ProxyRecord(labels, outputs)
        assert isinstance(proxy.eval_record, EvalRecord)

    def test_confusion_figure_returns_none(self):
        proxy = ProxyRecord(np.array([0]), np.array([[1.0]]))
        assert proxy.get_confusion_figure() is None
        assert proxy.get_confusion_figure(fig=MagicMock()) is None

    def test_eval_record_has_empty_saliency(self):
        proxy = ProxyRecord(np.array([0]), np.array([[1.0]]))
        er = proxy.eval_record
        assert er.gradient == {}
        assert er.gradient_input == {}
        assert er.smoothgrad == {}
        assert er.smoothgrad_sq == {}
        assert er.vargrad == {}


class TestPooledRecordWrapper:
    def test_wraps_original(self):
        original = MagicMock()
        original.dataset = MagicMock()
        labels = np.array([0, 1])
        outputs = np.array([[0.5, 0.5], [0.3, 0.7]])

        wrapper = PooledRecordWrapper(original, labels, outputs)
        assert wrapper.original is original
        assert wrapper.dataset is original.dataset
        assert isinstance(wrapper.eval_record, EvalRecord)

    def test_confusion_figure_delegates_to_original_class(self):
        # Use a real-ish mock with get_confusion_figure on the class
        class FakeRecord:
            dataset = MagicMock()

            def get_confusion_figure(self, fig=None, show_percentage=False):
                return "fake_figure"

        original = FakeRecord()
        labels = np.array([0, 1])
        outputs = np.array([[0.5, 0.5], [0.3, 0.7]])

        wrapper = PooledRecordWrapper(original, labels, outputs)
        result = wrapper.get_confusion_figure()
        assert result == "fake_figure"
