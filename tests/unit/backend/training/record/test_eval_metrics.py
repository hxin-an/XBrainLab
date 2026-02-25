import unittest

import numpy as np

from XBrainLab.backend.training.record.eval import EvalRecord


class TestEvalMetrics(unittest.TestCase):
    def setUp(self):
        # Create dummy data for 3 classes
        # Class 0: 3 samples
        # Class 1: 3 samples
        # Class 2: 4 samples
        self.label = np.array([0, 0, 0, 1, 1, 1, 2, 2, 2, 2])

        # Predictions:
        # Class 0: 2 correct, 1 wrong (predicted as 1)
        # Class 1: 2 correct, 1 wrong (predicted as 2)
        # Class 2: 3 correct, 1 wrong (predicted as 0)

        # Output probabilities (mocked, we just need argmax to match predictions)
        # Preds: [0, 0, 1, 1, 1, 2, 2, 2, 2, 0]
        self.output = np.zeros((10, 3))
        preds = [0, 0, 1, 1, 1, 2, 2, 2, 2, 0]
        for i, p in enumerate(preds):
            self.output[i, p] = 1.0

        # Dummy gradients (not used for metrics)
        self.dummy_grad = {}

        self.record = EvalRecord(
            label=self.label,
            output=self.output,
            gradient=self.dummy_grad,
            gradient_input=self.dummy_grad,
            smoothgrad=self.dummy_grad,
            smoothgrad_sq=self.dummy_grad,
            vargrad=self.dummy_grad,
        )

    def test_per_class_metrics(self):
        metrics = self.record.get_per_class_metrics()

        # Expected values calculation:
        # Class 0: TP=2, FP=1 (sample 9), FN=1 (sample 2)
        # Precision = TP / (TP + FP) = 2 / 3 = 0.666...
        # Recall = TP / (TP + FN) = 2 / 3 = 0.666...
        # F1 = 2 * P * R / (P + R) = 0.666...

        # Class 1: TP=2, FP=1 (sample 2), FN=1 (sample 5)
        # Precision = 2 / 3
        # Recall = 2 / 3

        # Class 2: TP=3, FP=1 (sample 5), FN=1 (sample 9)
        # Precision = 3 / 4 = 0.75
        # Recall = 3 / 4 = 0.75

        # Verify Class 0
        self.assertAlmostEqual(metrics[0]["precision"], 2 / 3)
        self.assertAlmostEqual(metrics[0]["recall"], 2 / 3)
        self.assertEqual(metrics[0]["support"], 3)

        # Verify Class 2
        self.assertEqual(metrics[2]["precision"], 0.75)
        self.assertEqual(metrics[2]["recall"], 0.75)
        self.assertEqual(metrics[2]["support"], 4)

        # Verify Macro Avg
        # Precision Avg = (2/3 + 2/3 + 0.75) / 3 = (1.333 + 0.75) / 3 =
        # 2.0833 / 3 = 0.6944...
        expected_macro_p = (2 / 3 + 2 / 3 + 0.75) / 3
        self.assertAlmostEqual(metrics["macro_avg"]["precision"], expected_macro_p)
        self.assertEqual(metrics["macro_avg"]["support"], 10)
