import unittest
from unittest.mock import MagicMock

import numpy as np

from XBrainLab.backend.controller.visualization_controller import (
    VisualizationController,
)
from XBrainLab.backend.training.record.eval import EvalRecord


class TestAveraging(unittest.TestCase):
    def test_average_logic(self):
        # Create mock records
        rec1 = MagicMock(spec=EvalRecord)
        rec1.label = np.array([0, 1])
        rec1.output = np.array([[0.1, 0.9], [0.8, 0.2]])
        rec1.gradient = {0: np.array([[1.0, 1.0]]), 1: np.array([[2.0, 2.0]])}
        rec1.gradient_input = {0: np.array([[1.0]]), 1: np.array([[2.0]])}
        rec1.smoothgrad = {0: np.array([[1.0]]), 1: np.array([[2.0]])}
        rec1.smoothgrad_sq = {0: np.array([[1.0]]), 1: np.array([[2.0]])}
        rec1.vargrad = {0: np.array([[1.0]]), 1: np.array([[2.0]])}

        rec2 = MagicMock(spec=EvalRecord)
        rec2.label = np.array([0, 1])
        rec2.output = np.array([[0.2, 0.8], [0.7, 0.3]])
        rec2.gradient = {0: np.array([[3.0, 3.0]]), 1: np.array([[4.0, 4.0]])}
        rec2.gradient_input = {0: np.array([[3.0]]), 1: np.array([[4.0]])}
        rec2.smoothgrad = {0: np.array([[3.0]]), 1: np.array([[4.0]])}
        rec2.smoothgrad_sq = {0: np.array([[3.0]]), 1: np.array([[4.0]])}
        rec2.vargrad = {0: np.array([[3.0]]), 1: np.array([[4.0]])}

        # Mock plans
        plan1 = MagicMock()
        plan1.get_eval_record.return_value = rec1
        plan2 = MagicMock()
        plan2.get_eval_record.return_value = rec2

        # Mock trainer_holder
        trainer_holder = MagicMock()
        trainer_holder.get_plans.return_value = [plan1, plan2]

        # Use real controller method (mock Study to avoid init side-effects)
        mock_study = MagicMock()
        controller = VisualizationController(mock_study)

        # Run averaging via the real method
        avg_rec = controller.get_averaged_record(trainer_holder)

        # Verify
        self.assertIsNotNone(avg_rec)

        # Check gradient average: (1+3)/2 = 2, (2+4)/2 = 3
        np.testing.assert_array_equal(avg_rec.gradient[0], np.array([[2.0, 2.0]]))
        np.testing.assert_array_equal(avg_rec.gradient[1], np.array([[3.0, 3.0]]))
