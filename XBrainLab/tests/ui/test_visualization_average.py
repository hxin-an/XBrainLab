import unittest
from unittest.mock import MagicMock
import numpy as np
from XBrainLab.backend.training.record.eval import EvalRecord

# Mock SaliencyMapWidget's get_averaged_record method
# We can just copy the method here for testing since it's identical across widgets
def get_averaged_record(trainer):
    plans = trainer.get_plans()
    records = [p.get_eval_record() for p in plans if p.get_eval_record() is not None]
    
    if not records:
        return None
        
    base = records[0]
    
    def avg_dict(attr_name):
        result = {}
        keys = getattr(base, attr_name).keys()
        for k in keys:
            arrays = [getattr(r, attr_name)[k] for r in records]
            result[k] = np.mean(np.stack(arrays), axis=0)
        return result

    avg_gradient = avg_dict('gradient')
    avg_gradient_input = avg_dict('gradient_input')
    avg_smoothgrad = avg_dict('smoothgrad')
    avg_smoothgrad_sq = avg_dict('smoothgrad_sq')
    avg_vargrad = avg_dict('vargrad')
    
    return EvalRecord(
        label=base.label,
        output=base.output,
        gradient=avg_gradient,
        gradient_input=avg_gradient_input,
        smoothgrad=avg_smoothgrad,
        smoothgrad_sq=avg_smoothgrad_sq,
        vargrad=avg_vargrad
    )

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

        # Mock trainer
        trainer = MagicMock()
        trainer.get_plans.return_value = [plan1, plan2]

        # Run averaging
        avg_rec = get_averaged_record(trainer)

        # Verify
        self.assertIsNotNone(avg_rec)
        
        # Check gradient average: (1+3)/2 = 2, (2+4)/2 = 3
        np.testing.assert_array_equal(avg_rec.gradient[0], np.array([[2.0, 2.0]]))
        np.testing.assert_array_equal(avg_rec.gradient[1], np.array([[3.0, 3.0]]))
        
        print("Averaging test passed!")

if __name__ == '__main__':
    unittest.main()
