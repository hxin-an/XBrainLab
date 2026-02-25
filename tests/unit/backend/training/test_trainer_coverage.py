"""Extended tests for Trainer covering job exceptions, clear_history, clean.

Covers: job() exception path, clear_history RuntimeError, clean(force_update),
run() idempotency guard.
"""

import threading
from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.backend.training import Trainer, TrainingPlanHolder

# ---------------------------------------------------------------------------
# Fake plan holders
# ---------------------------------------------------------------------------


class FakeTrainingPlanHolder(TrainingPlanHolder):
    def __init__(self, name="FakePlan"):
        self._name = name
        self.train_record_list = [MagicMock()]
        self._interrupt = threading.Event()
        self.error = None

    def get_name(self):
        return self._name


@pytest.fixture
def holders():
    return [FakeTrainingPlanHolder(f"Plan{i}") for i in range(3)]


# ---------------------------------------------------------------------------
# job() exception handling
# ---------------------------------------------------------------------------


class TestJobException:
    def test_job_exception_sets_error_progress(self, holders):
        """When a plan's train() raises, progress_text prefixed with 'Error:'."""
        trainer = Trainer(holders)

        with patch.object(holders[0], "train", side_effect=RuntimeError("boom")):
            trainer.job()

        assert trainer.progress_text.startswith("Error:")
        assert "boom" in trainer.progress_text
        assert trainer.job_thread is None

    def test_job_exception_preserves_error_in_finally(self, holders):
        """Error progress text should NOT be overwritten in finally block."""
        trainer = Trainer(holders)

        with patch.object(holders[0], "train", side_effect=ValueError("bad")):
            trainer.job()

        assert trainer.progress_text.startswith("Error:")


# ---------------------------------------------------------------------------
# clear_history
# ---------------------------------------------------------------------------


class TestClearHistory:
    def test_clear_history_when_idle(self, holders):
        trainer = Trainer(holders)
        assert len(trainer.training_plan_holders) == 3
        trainer.clear_history()
        assert len(trainer.training_plan_holders) == 0
        assert trainer.current_idx == 0

    def test_clear_history_while_running_raises(self, holders):
        trainer = Trainer(holders)
        # Simulate running
        trainer.job_thread = MagicMock()
        trainer.job_thread.is_alive.return_value = True

        with pytest.raises(RuntimeError, match="Cannot clear"):
            trainer.clear_history()


# ---------------------------------------------------------------------------
# clean
# ---------------------------------------------------------------------------


class TestClean:
    def test_clean_force_sets_interrupt(self, holders):
        trainer = Trainer(holders)
        trainer.clean(force_update=True)
        assert trainer.interrupt is True

    def test_clean_no_force_while_running_raises(self, holders):
        trainer = Trainer(holders)
        trainer.job_thread = MagicMock()
        trainer.job_thread.is_alive.return_value = True

        with pytest.raises(RuntimeError, match="still in progress"):
            trainer.clean(force_update=False)

    def test_clean_no_force_when_idle_ok(self, holders):
        trainer = Trainer(holders)
        # Should not raise
        trainer.clean(force_update=False)


# ---------------------------------------------------------------------------
# add_plan / add_training_plan_holders
# ---------------------------------------------------------------------------


class TestAddPlans:
    def test_add_plan(self, holders):
        trainer = Trainer(holders[:1])
        new_plan = FakeTrainingPlanHolder("NewPlan")
        trainer.add_plan(new_plan)
        assert len(trainer.training_plan_holders) == 2
        assert trainer.training_plan_holders[-1] is new_plan

    def test_add_training_plan_holders(self, holders):
        trainer = Trainer(holders[:1])
        trainer.add_training_plan_holders(holders[1:])
        assert len(trainer.training_plan_holders) == 3


# ---------------------------------------------------------------------------
# run idempotency
# ---------------------------------------------------------------------------


class TestRunIdempotency:
    def test_run_while_already_running_is_noop(self, holders):
        trainer = Trainer(holders)
        # Simulate running
        trainer.job_thread = MagicMock()
        trainer.job_thread.is_alive.return_value = True

        with patch.object(trainer, "job") as mock_job:
            trainer.run(interact=False)
            mock_job.assert_not_called()

    def test_run_sync(self, holders):
        trainer = Trainer(holders)
        with patch.object(trainer, "job") as mock_job:
            trainer.run(interact=False)
            mock_job.assert_called_once()

    def test_run_threaded(self, holders):
        trainer = Trainer(holders)
        event = threading.Event()

        def fake_job():
            event.set()

        with patch.object(trainer, "job", side_effect=fake_job):
            trainer.run(interact=True)
            event.wait(timeout=5)
            assert event.is_set()
