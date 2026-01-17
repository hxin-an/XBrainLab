import threading
from unittest.mock import patch

import pytest

from XBrainLab.backend.training import Trainer, TrainingPlanHolder


class FakePlan:
    def __init__(self, i):
        self.i = i

    def get_name(self):
        return str(self.i)


class FakeTrainingPlanHolder(TrainingPlanHolder):
    def __init__(self, i):
        self.i = i
        self.train_record_list = [FakePlan("test")]

    def get_name(self):
        return "Fake" + str(self.i)


@pytest.fixture
def training_plan_holders():
    result = [FakeTrainingPlanHolder(i) for i in range(2)]
    return result


def test_trainer(training_plan_holders):
    trainer = Trainer(training_plan_holders)
    assert trainer.get_training_plan_holders() == training_plan_holders
    assert trainer.get_progress_text() == "Pending"
    holder = training_plan_holders[-1]

    with (
        patch.object(holder, "set_interrupt") as interrupt_mock,
        patch.object(holder, "clear_interrupt") as clear_interrupt_mock,
    ):

        def interrupt():
            assert trainer.get_progress_text() == "Interrupting"

        interrupt_mock.side_effect = interrupt

        trainer.set_interrupt()
        interrupt_mock.assert_called_once()
        assert trainer.interrupt
        assert trainer.get_progress_text() == "Interrupting"

        trainer.clear_interrupt()
        clear_interrupt_mock.assert_called_once()
        assert trainer.interrupt is False
        assert trainer.get_progress_text() == "Pending"


def test_trainer_custom_progress_text(training_plan_holders):
    trainer = Trainer(training_plan_holders)
    trainer.progress_text = "Custom"
    assert trainer.get_progress_text() == "Custom"


@pytest.mark.parametrize("interact", [True, False])
def test_trainer_run(training_plan_holders, interact):
    trainer = Trainer(training_plan_holders)

    with patch.object(trainer, "job") as job_mock:

        def job():
            if interact:
                assert trainer.is_running()
                assert not isinstance(threading.current_thread(), threading._MainThread)
                call_count = job_mock.call_count
                trainer.run()
                assert job_mock.call_count == call_count
                with pytest.raises(RuntimeError):
                    trainer.clean()
                trainer.clean(force_update=True)
            else:
                assert isinstance(threading.current_thread(), threading._MainThread)

        job_mock.side_effect = job
        trainer.run(interact=interact)
        job_mock.assert_called_once()
        assert trainer.is_running() is False


def test_trainer_job(training_plan_holders):
    trainer = Trainer(training_plan_holders)
    counter = 0

    def train():
        nonlocal counter
        assert trainer.get_progress_text() == "Now training: Fake" + str(counter)
        counter += 1

    # We need to patch 'train' on EACH holder instance.
    # Since training_plan_holders is a list of instances, we can patch them
    # individually.
    # But patch.object works on the object.

    patches = [
        patch.object(holder, "train", side_effect=train)
        for holder in training_plan_holders
    ]

    # Start all patches
    mocks = [p.start() for p in patches]

    try:
        trainer.job()
        for m in mocks:
            m.assert_called_once()
        assert trainer.get_progress_text() == "Pending"
        assert trainer.is_running() is False
    finally:
        for p in patches:
            p.stop()


def test_trainer_interrupt(training_plan_holders):
    trainer = Trainer(training_plan_holders)
    holder = training_plan_holders[0]

    with patch.object(holder, "train") as train_mock:
        trainer.set_interrupt()
        trainer.job()
        train_mock.assert_not_called()


@pytest.mark.parametrize(
    "plan_name, real_plan_name, error_stage",
    [
        ["Fake", "test", 1],
        ["Fake0", "test", 0],
        ["Fake1", "test", 0],
        ["Fake1", "tests", 2],
    ],
)
def test_trainer_get_plan(
    training_plan_holders, plan_name, real_plan_name, error_stage
):
    trainer = Trainer(training_plan_holders)
    if error_stage == 0:
        trainer.get_real_training_plan(plan_name, real_plan_name)
    else:
        error = ".*training plan.*" if error_stage == 1 else ".*real plan.*"
        with pytest.raises(ValueError, match=error):
            trainer.get_real_training_plan(plan_name, real_plan_name)
