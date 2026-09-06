from threading import Event, Thread
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
import torch

from XBrainLab.backend.controller.training_controller import (
    TrainingController,
)
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import TrainingEvaluation, TrainingOption
from XBrainLab.backend.training_state_contract import (
    TrainingLifecycleEvent,
    TrainingOutcomeState,
    TrainingRunIdentity,
    TrainingStateToken,
    TrainingTerminalOutcome,
)


class TestTrainingController:
    @pytest.fixture
    def mock_study(self):
        return MagicMock(spec=Study)

    @pytest.fixture
    def controller(self, mock_study):
        return TrainingController(mock_study)

    def test_monitor_publishes_update_then_terminal_notification(
        self, controller, mock_study
    ):
        mock_study.is_training.side_effect = [True, False]
        events = []
        controller.subscribe("training_updated", lambda: events.append("updated"))
        controller.subscribe("training_stopped", lambda: events.append("stopped"))
        handoff = controller._training_state._reserve_terminal_handoff()

        controller._training_state._monitor_loop(handoff.generation)

        assert events == ["updated", "stopped"]
        assert controller.wait_for_terminal_notification(handoff.generation, timeout=0)

    def test_rejects_live_previous_monitor(self, controller):
        existing = MagicMock()
        existing.is_alive.return_value = True
        controller._training_state._monitor_thread = existing
        handoff = controller._training_state._reserve_terminal_handoff()

        with pytest.raises(RuntimeError, match="previous training monitor"):
            controller._training_state._start_monitoring(handoff.generation)

        assert controller._training_state._monitor_thread is existing

    def test_start_training_not_running(self, controller, mock_study):
        mock_study.is_training.return_value = False

        mock_callback = MagicMock()
        controller.subscribe("training_started", mock_callback)

        with patch("threading.Thread") as MockThread:
            thread_instance = MockThread.return_value
            generation = controller.start_training()

            mock_study.generate_plan.assert_called_once_with(
                force_update=True, append=True
            )
            mock_study.train.assert_called_once_with(interact=True)
            mock_callback.assert_called_once()

            # Verify monitoring started
            MockThread.assert_called_once()
            thread_instance.start.assert_called_once()
            assert generation == 1

    def test_interactive_start_publishes_typed_generation_without_ordering_threads(
        self,
        controller,
        mock_study,
    ):
        """UI consumers receive identity they can reconcile across Qt threads."""
        mock_study.is_training.return_value = False
        run = TrainingRunIdentity(trainer_id="trainer-1", run_id=1)
        trainer = MagicMock()
        trainer.get_state_snapshot_token.return_value = TrainingStateToken(
            generation=7,
            stable=True,
        )
        trainer.get_terminal_outcome.return_value = TrainingTerminalOutcome(
            state=TrainingOutcomeState.RUNNING,
            run=run,
        )
        mock_study.trainer = trainer
        lifecycle: list[str] = []
        typed_events: list[TrainingLifecycleEvent] = []
        controller.subscribe(
            "training_started",
            lambda: lifecycle.append("started"),
        )
        controller.subscribe("training_started_state", typed_events.append)
        mock_study.train.side_effect = lambda **_kwargs: lifecycle.append("train")

        with patch.object(
            controller._training_state,
            "_start_monitoring",
            side_effect=lambda _generation: lifecycle.append("monitor"),
        ):
            controller.start_training(interactive=True)

        assert lifecycle == ["train", "started", "monitor"]
        assert typed_events == [
            TrainingLifecycleEvent(
                token=TrainingStateToken(generation=7, stable=True),
                outcome=TrainingTerminalOutcome(
                    state=TrainingOutcomeState.RUNNING,
                    run=run,
                ),
            )
        ]

    def test_start_training_sync_honors_command_options(self, controller, mock_study):
        mock_study.is_training.return_value = False

        started_callback = MagicMock()
        stopped_callback = MagicMock()
        controller.subscribe("training_started", started_callback)
        controller.subscribe("training_stopped", stopped_callback)

        with patch("threading.Thread") as MockThread:
            controller.start_training(append=False, interactive=False)

        mock_study.generate_plan.assert_called_once_with(
            force_update=True,
            append=False,
        )
        mock_study.train.assert_called_once_with(interact=False)
        started_callback.assert_called_once()
        stopped_callback.assert_called_once()
        MockThread.assert_not_called()

    def test_start_training_already_running(self, controller, mock_study):
        mock_study.is_training.return_value = True
        mock_callback = MagicMock()
        controller.subscribe("training_started", mock_callback)
        existing = controller._training_state._reserve_terminal_handoff()

        with pytest.raises(RuntimeError, match="already running"):
            controller.start_training()

        mock_study.generate_plan.assert_not_called()
        mock_callback.assert_not_called()
        assert not controller.wait_for_terminal_notification(
            existing.generation,
            timeout=0.0,
        )

    def test_monitor_failure_wakes_exact_terminal_handoff_waiter(
        self,
        controller,
        mock_study,
    ):
        mock_study.is_training.side_effect = RuntimeError("monitor read failed")
        handoff = controller._training_state._reserve_terminal_handoff()
        waiting = Event()
        results: list[bool] = []

        def wait_for_handoff() -> None:
            waiting.set()
            results.append(
                controller.wait_for_terminal_notification(
                    handoff.generation,
                    timeout=5.0,
                )
            )

        waiter = Thread(target=wait_for_handoff, name="terminal-handoff-waiter")
        waiter.start()
        assert waiting.wait(timeout=1.0)

        controller._training_state._monitor_loop(handoff.generation)
        waiter.join(timeout=1.0)

        assert not waiter.is_alive()
        assert results == [False]

    def test_shutdown_wakes_pending_terminal_handoff_waiter(
        self,
        controller,
    ):
        handoff = controller._training_state._reserve_terminal_handoff()
        waiting = Event()
        results: list[bool] = []

        def wait_for_handoff() -> None:
            waiting.set()
            results.append(
                controller.wait_for_terminal_notification(
                    handoff.generation,
                    timeout=5.0,
                )
            )

        waiter = Thread(target=wait_for_handoff, name="shutdown-handoff-waiter")
        waiter.start()
        assert waiting.wait(timeout=1.0)

        controller.shutdown()
        waiter.join(timeout=1.0)

        assert not waiter.is_alive()
        assert results == [False]

    def test_terminal_handoffs_are_owned_by_exact_generation(
        self,
        controller,
    ):
        first = controller._training_state._reserve_terminal_handoff()
        controller._training_state._publish_training_stopped(first.generation)
        second = controller._training_state._reserve_terminal_handoff()

        assert controller.wait_for_terminal_notification(
            first.generation,
            timeout=0.0,
        )
        assert not controller.wait_for_terminal_notification(
            second.generation,
            timeout=0.0,
        )

    def test_restart_wait_releases_monitor_before_reporting_safe(
        self,
        controller,
        mock_study,
    ):
        mock_study.is_training.return_value = False
        callback_entered = Event()
        release_callback = Event()
        handoff = controller._training_state._reserve_terminal_handoff()

        def publish_terminal() -> None:
            callback_entered.set()
            assert release_callback.wait(timeout=5.0)

        controller.subscribe("training_stopped", publish_terminal)
        monitor = Thread(
            target=controller._training_state._monitor_loop,
            args=(handoff.generation,),
            name="training-monitor-under-test",
        )
        controller._training_state._monitor_thread = monitor
        monitor.start()
        assert callback_entered.wait(timeout=1.0)

        safe: list[bool] = []
        waiter = Thread(
            target=lambda: safe.append(controller.wait_until_restart_safe(timeout=5.0)),
            name="training-restart-waiter",
        )
        waiter.start()
        assert waiter.is_alive()

        release_callback.set()
        waiter.join(timeout=1.0)
        monitor.join(timeout=1.0)

        assert safe == [True]
        assert not waiter.is_alive()
        assert not monitor.is_alive()
        assert controller._training_state._monitor_thread is None

    def test_stop_training(self, controller, mock_study):
        mock_study.is_training.return_value = True

        controller.stop_training()

        mock_study.stop_training.assert_called_once()
        # Notification is now emitted only by _monitor_loop, not stop_training()
        # to avoid duplicate "training_stopped" events

    def test_clear_history_running(self, controller, mock_study):
        mock_study.is_training.return_value = True
        with pytest.raises(RuntimeError):
            controller.clear_history()

    def test_clear_history_success(self, controller, mock_study):
        mock_study.is_training.return_value = False
        mock_trainer = MagicMock()
        mock_study.trainer = mock_trainer

        # Setup observer
        mock_callback = MagicMock()
        controller.subscribe("history_cleared", mock_callback)

        controller.clear_history()

        mock_trainer.clear_history.assert_called_once()
        mock_callback.assert_called_once()

    def test_get_formatted_history(self, controller, mock_study):
        mock_trainer = MagicMock()
        mock_study.trainer = mock_trainer

        # Mock Plan and Record
        plan_holder = MagicMock()
        plan_holder.model_holder.target_model.__name__ = "ModelA"
        plan_holder.get_training_repeat.return_value = 1

        record = MagicMock()
        record.repeat = 1

        plan_holder.get_plans.return_value = [record]
        mock_trainer.get_training_plan_holders.return_value = [plan_holder]
        mock_trainer.is_running.return_value = True
        mock_trainer.current_idx = 0

        history = controller.get_formatted_history()

        assert len(history) == 1
        assert history[0]["model_name"] == "ModelA"
        assert history[0]["group_name"] == "Group 1"
        assert history[0]["run_name"] == "1"
        assert history[0]["is_active"] is True
        assert history[0]["is_current_run"] is True

    def test_validate_ready_success(self, controller, mock_study):
        mock_study.datasets = [1, 2]
        mock_study.model_holder = "model"
        mock_study.training_option = "option"
        assert controller.validate_ready() is True

    def test_validate_ready_fail(self, controller, mock_study):
        mock_study.datasets = []
        mock_study.model_holder = "model"
        mock_study.training_option = "option"
        assert controller.validate_ready() is False

    def test_set_model_holder_notifies_config_changed(self, controller, mock_study):
        cb = MagicMock()
        controller.subscribe("config_changed", cb)
        holder = MagicMock()

        controller.set_model_holder(holder)

        mock_study.set_model_holder.assert_called_once_with(holder)
        cb.assert_called_once()

    def test_set_training_option_notifies_config_changed(self, controller, mock_study):
        cb = MagicMock()
        controller.subscribe("config_changed", cb)
        option = MagicMock()

        controller.set_training_option(option)

        mock_study.set_training_option.assert_called_once_with(option)
        cb.assert_called_once()

    def test_invalid_mutated_option_does_not_replace_state_or_notify(self):
        study = Study()
        controller = TrainingController(study)
        existing = TrainingOption(
            "test",
            torch.optim.Adam,
            {},
            True,
            None,
            10,
            32,
            0.001,
            0,
            TrainingEvaluation.VAL_ACC,
            1,
        )
        invalid = TrainingOption(
            "test",
            torch.optim.Adam,
            {},
            True,
            None,
            10,
            32,
            0.001,
            0,
            TrainingEvaluation.VAL_ACC,
            1,
        )
        cast(Any, invalid).epoch = 2.5
        study.set_training_option(existing)
        callback = MagicMock()
        controller.subscribe("config_changed", callback)

        with pytest.raises(ValueError):
            controller.set_training_option(invalid)

        published = study.training_option
        assert published is not None
        assert published.epoch == existing.epoch
        callback.assert_not_called()

    def test_apply_configuration_notifies_once(self, controller, mock_study):
        cb = MagicMock()
        controller.subscribe("config_changed", cb)
        holder = MagicMock()
        option = MagicMock()

        controller.apply_configuration(
            model_holder=holder,
            training_option=option,
            update_model=True,
            update_option=True,
        )

        mock_study.apply_training_configuration.assert_called_once_with(
            model_holder=holder,
            training_option=option,
            update_model=True,
            update_option=True,
        )
        cb.assert_called_once()

    def test_apply_data_splitting_notifies_config_changed(
        self,
        controller,
        mock_study,
    ):
        cb = MagicMock()
        controller.subscribe("config_changed", cb)
        generator = MagicMock()

        controller.apply_data_splitting(generator)

        generator.apply.assert_called_once_with(mock_study)
        cb.assert_called_once()
