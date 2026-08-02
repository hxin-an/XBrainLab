from unittest.mock import MagicMock

from XBrainLab.backend.application.training_history import (
    project_training_history_rows,
)


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
