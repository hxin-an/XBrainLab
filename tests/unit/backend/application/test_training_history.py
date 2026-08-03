from unittest.mock import MagicMock

import numpy as np

from XBrainLab.backend.application.training_history import (
    project_training_history_rows,
)
from XBrainLab.backend.training.record.eval import EvalRecord


def test_failed_training_history_row_detaches_its_failure_detail() -> None:
    plan = MagicMock()
    plan.error = (
        "CUDA out of memory during training. "
        "Try reducing batch size, input length, or model size."
    )
    plan.get_training_status.return_value = plan.error
    plan.option.epoch = 1
    record = MagicMock()
    record.get_epoch.return_value = 0
    record.is_finished.return_value = False
    record.train = {}
    record.val = {}

    rows = project_training_history_rows(
        [
            {
                "plan": plan,
                "record": record,
                "plan_index": 0,
                "run_index": 0,
                "group_name": "Group 1",
                "run_name": "1",
                "model_name": "EEGNet",
                "is_active": False,
                "is_current_run": False,
            }
        ]
    )

    assert rows[0]["status"] == "Failed"
    assert rows[0]["status_detail"] == plan.error
    assert "plan" not in rows[0]
    assert "record" not in rows[0]


def test_completed_training_history_row_does_not_publish_stale_failure_detail() -> None:
    plan = MagicMock()
    plan.error = "stale implementation detail"
    plan.get_training_status.return_value = "Done"
    plan.option.epoch = 1
    record = MagicMock()
    record.get_epoch.return_value = 1
    record.is_finished.return_value = True
    record.train = {}
    record.val = {}

    rows = project_training_history_rows(
        [
            {
                "plan": plan,
                "record": record,
                "plan_index": 0,
                "run_index": 0,
                "group_name": "Group 1",
                "run_name": "1",
                "model_name": "EEGNet",
                "is_active": False,
                "is_current_run": False,
            }
        ]
    )

    assert rows[0]["status"] == "Completed"
    assert rows[0]["status_detail"] is None


def test_completed_training_history_row_publishes_detached_final_test_accuracy() -> (
    None
):
    plan = MagicMock()
    plan.get_training_status.return_value = "Done"
    plan.option.epoch = 1
    record = MagicMock()
    record.get_epoch.return_value = 1
    record.is_finished.return_value = True
    record.train = {}
    record.val = {}
    record.evaluation_records = {
        "test": EvalRecord(
            label=np.asarray([0, 1]),
            output=np.asarray([[0.9, 0.1], [0.2, 0.8]]),
            gradient={},
            gradient_input={},
            smoothgrad={},
            smoothgrad_sq={},
            vargrad={},
            evaluation_split="test",
        )
    }

    rows = project_training_history_rows(
        [
            {
                "plan": plan,
                "record": record,
                "plan_index": 0,
                "run_index": 0,
                "group_name": "Group 1",
                "run_name": "1",
                "model_name": "EEGNet",
                "is_active": False,
                "is_current_run": False,
            }
        ]
    )

    assert rows[0]["metrics"]["test"]["accuracy"] == [100.0]
    assert "record" not in rows[0]
