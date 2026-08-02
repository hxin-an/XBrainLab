"""Tests for TrainingManager extracted from Study."""

from threading import Event, Thread
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
import torch

from XBrainLab.backend.exceptions import (
    StaleSaliencyUpdateError,
    StaleTrainingPipelineMutationError,
)
from XBrainLab.backend.training import (
    ModelHolder,
    TestOnlyOption,
    Trainer,
    TrainingEvaluation,
    TrainingOption,
    TrainingPlanHolder,
)
from XBrainLab.backend.training_manager import (
    PostTrainingSaliencyTarget,
    TrainingManager,
)
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyStatus,
    TrainingOutcomeState,
    TrainingRunIdentity,
    TrainingStateToken,
    TrainingTerminalOutcome,
)


class _StablePipelineTrainer:
    def __init__(
        self,
        *,
        identity: str = "pipeline-trainer",
        generation: int = 3,
        run_id: int = 1,
        outcome_state: TrainingOutcomeState = TrainingOutcomeState.COMPLETED,
    ) -> None:
        self.identity = identity
        self.generation = generation
        self.run_id = run_id
        self.outcome_state = outcome_state
        self.clean_calls: list[bool] = []
        self.wait_calls: list[float | None] = []

    def get_state_snapshot_identity(self) -> str:
        return self.identity

    def get_state_snapshot_token(self) -> TrainingStateToken:
        return TrainingStateToken(generation=self.generation, stable=True)

    def get_terminal_outcome(self) -> TrainingTerminalOutcome:
        return TrainingTerminalOutcome(
            state=self.outcome_state,
            run=(
                TrainingRunIdentity(
                    trainer_id=self.identity,
                    run_id=self.run_id,
                )
                if self.outcome_state
                not in {
                    TrainingOutcomeState.NOT_STARTED,
                    TrainingOutcomeState.UNKNOWN,
                }
                else None
            ),
        )

    def is_running(self) -> bool:
        return False

    def wait_for_completion(self, timeout: float | None = None) -> bool:
        self.wait_calls.append(timeout)
        return True

    def clean(self, *, force_update: bool) -> None:
        self.clean_calls.append(force_update)


def _valid_training_option() -> TrainingOption:
    return TrainingOption(
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


class TestTrainingManagerInit:
    def test_defaults(self):
        tm = TrainingManager()
        assert tm.model_holder is None
        assert tm.training_option is None
        assert tm.trainer is None
        assert tm.saliency_params is None


class TestTrainingPipelineMutationBoundary:
    def test_compare_and_retire_preserves_one_stable_boundary(self) -> None:
        manager = TrainingManager()
        trainer = _StablePipelineTrainer()
        manager.trainer = cast(Any, trainer)
        boundary = manager.capture_pipeline_mutation_boundary()

        retired = manager.retire_trainer_if_current(boundary)

        assert retired is True
        assert manager.trainer is None
        assert trainer.clean_calls == [False]
        assert manager.get_post_training_saliency_status() == (
            PostTrainingSaliencyStatus.idle(generation=1)
        )

    def test_compare_and_retire_rejects_changed_saliency_generation(self) -> None:
        manager = TrainingManager()
        trainer = _StablePipelineTrainer()
        manager.trainer = cast(Any, trainer)
        boundary = manager.capture_pipeline_mutation_boundary()
        manager._post_training_saliency_status = PostTrainingSaliencyStatus.idle(
            generation=9,
        )

        with pytest.raises(StaleTrainingPipelineMutationError):
            manager.retire_trainer_if_current(boundary)

        assert manager.trainer is trainer
        assert trainer.clean_calls == []

    def test_compare_and_retire_rejects_replaced_trainer_identity(self) -> None:
        manager = TrainingManager()
        original = _StablePipelineTrainer(identity="original-trainer")
        replacement = _StablePipelineTrainer(identity="replacement-trainer")
        manager.trainer = cast(Any, original)
        boundary = manager.capture_pipeline_mutation_boundary()
        manager.trainer = cast(Any, replacement)

        with pytest.raises(StaleTrainingPipelineMutationError):
            manager.retire_trainer_if_current(boundary)

        assert manager.trainer is replacement
        assert original.clean_calls == []
        assert replacement.clean_calls == []

    @pytest.mark.parametrize("changed_field", ["generation", "terminal_run"])
    def test_compare_and_retire_rejects_changed_trainer_state(
        self,
        changed_field: str,
    ) -> None:
        manager = TrainingManager()
        trainer = _StablePipelineTrainer()
        manager.trainer = cast(Any, trainer)
        boundary = manager.capture_pipeline_mutation_boundary()
        if changed_field == "generation":
            trainer.generation += 1
        else:
            trainer.run_id += 1

        with pytest.raises(StaleTrainingPipelineMutationError):
            manager.retire_trainer_if_current(boundary)

        assert manager.trainer is trainer
        assert trainer.clean_calls == []

    def test_compare_and_retire_rejects_new_saliency_cleanup_owner(self) -> None:
        manager = TrainingManager()
        trainer = _StablePipelineTrainer()
        manager.trainer = cast(Any, trainer)
        boundary = manager.capture_pipeline_mutation_boundary()
        manager._saliency_job_cleanup_complete = Event()

        with pytest.raises(StaleTrainingPipelineMutationError):
            manager.retire_trainer_if_current(boundary)

        assert manager.trainer is trainer
        assert trainer.clean_calls == []

    def test_compare_and_retire_rejects_unknown_trainer_outcome(self) -> None:
        manager = TrainingManager()
        trainer = _StablePipelineTrainer(
            outcome_state=TrainingOutcomeState.UNKNOWN,
        )
        manager.trainer = cast(Any, trainer)
        boundary = manager.capture_pipeline_mutation_boundary()

        with pytest.raises(StaleTrainingPipelineMutationError):
            manager.retire_trainer_if_current(boundary)

        assert manager.trainer is trainer
        assert trainer.clean_calls == []

    def test_compare_and_retire_accepts_not_started_trainer(self) -> None:
        manager = TrainingManager()
        trainer = _StablePipelineTrainer(
            outcome_state=TrainingOutcomeState.NOT_STARTED,
        )
        manager.trainer = cast(Any, trainer)
        boundary = manager.capture_pipeline_mutation_boundary()

        assert manager.retire_trainer_if_current(boundary) is True
        assert manager.trainer is None
        assert trainer.clean_calls == [False]

    def test_pipeline_replacement_fences_plan_generation_after_data_publication(
        self,
    ) -> None:
        publication_complete = Event()
        cleanup_started = Event()
        release_cleanup = Event()

        class _BlockingCleanupTrainer(_StablePipelineTrainer):
            def clean(self, *, force_update: bool) -> None:
                self.clean_calls.append(force_update)
                cleanup_started.set()
                assert release_cleanup.wait(timeout=2.0)

        manager = TrainingManager()
        trainer = _BlockingCleanupTrainer(
            outcome_state=TrainingOutcomeState.NOT_STARTED,
        )
        manager.trainer = cast(Any, trainer)
        boundary = manager.capture_pipeline_mutation_boundary()
        errors: list[BaseException] = []

        def commit() -> None:
            try:
                manager.commit_pipeline_replacement(
                    boundary,
                    publish=publication_complete.set,
                )
            except BaseException as exc:
                errors.append(exc)

        worker = Thread(target=commit, daemon=True)
        worker.start()
        assert publication_complete.wait(timeout=1.0)
        assert cleanup_started.wait(timeout=1.0)

        with pytest.raises(
            RuntimeError,
            match="Another training lifecycle operation",
        ):
            manager.generate_plan([object()])

        release_cleanup.set()
        worker.join(timeout=1.0)

        assert not worker.is_alive()
        assert errors == []
        assert manager.trainer is None

    def test_pipeline_publication_failure_releases_lease_and_preserves_trainer(
        self,
    ) -> None:
        manager = TrainingManager()
        trainer = _StablePipelineTrainer(
            outcome_state=TrainingOutcomeState.NOT_STARTED,
        )
        manager.trainer = cast(Any, trainer)
        boundary = manager.capture_pipeline_mutation_boundary()

        def fail_publication() -> None:
            raise RuntimeError("dataset publication failed")

        with pytest.raises(RuntimeError, match="dataset publication failed"):
            manager.commit_pipeline_replacement(
                boundary,
                publish=fail_publication,
            )

        assert manager.trainer is trainer
        assert trainer.clean_calls == []
        assert manager._training_operation_owner is None

    def test_terminal_worker_handle_counts_as_active_saliency_work(self) -> None:
        manager = TrainingManager()
        manager._saliency_job_thread = cast(Any, object())

        boundary = manager.capture_pipeline_mutation_boundary()

        assert manager.has_active_saliency_work() is True
        assert boundary.saliency_work_active is True


class TestTrainingCompletionIdentity:
    def test_wait_rejects_a_different_trainer_before_blocking(self) -> None:
        manager = TrainingManager()
        trainer = _StablePipelineTrainer(identity="trainer-a")
        manager.trainer = cast(Any, trainer)

        completed = manager.wait_for_training_completion(
            timeout=0.1,
            expected_trainer_identity="trainer-b",
        )

        assert completed is False
        assert trainer.wait_calls == []

    def test_wait_rejects_a_trainer_replaced_during_completion(self) -> None:
        wait_started = Event()
        release_wait = Event()

        class _BlockingTrainer(_StablePipelineTrainer):
            def wait_for_completion(self, timeout: float | None = None) -> bool:
                self.wait_calls.append(timeout)
                wait_started.set()
                return release_wait.wait(timeout=1.0)

        manager = TrainingManager()
        original = _BlockingTrainer(identity="trainer-a")
        replacement = _StablePipelineTrainer(identity="trainer-b")
        manager.trainer = cast(Any, original)
        results: list[bool] = []
        waiter = Thread(
            target=lambda: results.append(
                manager.wait_for_training_completion(
                    timeout=1.0,
                    expected_trainer_identity="trainer-a",
                )
            )
        )

        waiter.start()
        assert wait_started.wait(timeout=1.0)
        with manager._training_pipeline_lock:
            manager.trainer = cast(Any, replacement)
        release_wait.set()
        waiter.join(timeout=1.0)

        assert waiter.is_alive() is False
        assert results == [False]
        assert original.wait_calls == [1.0]


class TestSetTrainingOption:
    def test_sets_valid_option(self):
        tm = TrainingManager()
        option = _valid_training_option()
        tm.set_training_option(option)
        published = tm.training_option
        assert published is not None
        assert published is not option
        assert published.epoch == option.epoch

    def test_rejects_invalid_type(self):
        tm = TrainingManager()
        with pytest.raises(TypeError):
            tm.set_training_option(cast(Any, "not_an_option"))

    @pytest.mark.parametrize(
        ("field", "invalid_value"),
        [
            ("lr", float("nan")),
            ("epoch", 1.5),
            ("bs", 31.5),
            ("checkpoint_epoch", 2.5),
            ("repeat_num", 1.5),
            ("optim", None),
            ("output_dir", 123),
            ("evaluation_option", "mystery"),
        ],
    )
    def test_revalidates_mutated_option_before_replacing_existing_state(
        self,
        field,
        invalid_value,
    ):
        tm = TrainingManager()
        existing = _valid_training_option()
        candidate = _valid_training_option()
        tm.set_training_option(existing)
        setattr(candidate, field, invalid_value)

        with pytest.raises(ValueError):
            tm.set_training_option(candidate)

        published = tm.training_option
        assert published is not None
        assert published.epoch == existing.epoch

    def test_rejects_mutated_test_only_option_before_replacing_state(self):
        tm = TrainingManager()
        existing = _valid_training_option()
        candidate = TestOnlyOption("./output", True, 0, 20)
        cast(Any, candidate).repeat_num = 1.5
        tm.set_training_option(existing)

        with pytest.raises(ValueError):
            tm.set_training_option(candidate)

        published = tm.training_option
        assert published is not None
        assert published.epoch == existing.epoch

    def test_published_option_is_isolated_from_caller_mutation(self):
        tm = TrainingManager()
        option = _valid_training_option()

        tm.set_training_option(option)
        cast(Any, option).epoch = 1.5

        published = tm.training_option
        assert published is not option
        assert published is not None
        assert published.epoch == 10

    def test_returned_option_cannot_mutate_manager_state(self):
        tm = TrainingManager()
        tm.set_training_option(_valid_training_option())

        published = tm.training_option
        assert published is not None
        cast(Any, published).epoch = 1.5

        reread = tm.training_option
        assert reread is not None
        assert reread.epoch == 10


class TestSetModelHolder:
    def test_sets_valid_holder(self):
        tm = TrainingManager()
        holder = ModelHolder(int, {})
        tm.set_model_holder(holder)
        published = tm.model_holder
        assert published is not holder
        assert published is not None
        assert published.target_model is holder.target_model

    def test_published_holder_is_isolated_from_caller_mutation(self):
        tm = TrainingManager()
        params = {"dropout": 0.25}
        holder = ModelHolder(int, params)

        tm.set_model_holder(holder)
        params["dropout"] = 0.9

        published = tm.model_holder
        assert published is not holder
        assert published is not None
        assert published.model_params_map == {"dropout": 0.25}

    def test_returned_holder_cannot_mutate_manager_state(self):
        tm = TrainingManager()
        tm.set_model_holder(ModelHolder(int, {"nested": {"depth": 2}}))

        published = tm.model_holder
        assert published is not None
        published.target_model = str
        returned_params = published.model_params_map
        returned_params["nested"]["depth"] = 9

        reread = tm.model_holder
        assert reread is not None
        assert reread.target_model is int
        assert reread.model_params_map == {"nested": {"depth": 2}}

    def test_rejects_invalid_type(self):
        tm = TrainingManager()
        with pytest.raises(TypeError):
            tm.set_model_holder(cast(Any, "not_a_holder"))


class TestApplyConfiguration:
    def test_applies_model_and_option_together(self):
        tm = TrainingManager()
        holder = ModelHolder(int, {})
        option = _valid_training_option()

        tm.apply_configuration(
            model_holder=holder,
            training_option=option,
            update_model=True,
            update_option=True,
        )

        published_holder = tm.model_holder
        assert published_holder is not holder
        assert published_holder is not None
        assert published_holder.target_model is holder.target_model
        published = tm.training_option
        assert published is not None
        assert published is not option
        assert published.epoch == option.epoch

    def test_validation_failure_leaves_existing_configuration_unchanged(self):
        tm = TrainingManager()
        existing_holder = ModelHolder(str, {})
        existing_option = _valid_training_option()
        tm.model_holder = existing_holder
        tm.training_option = existing_option

        with pytest.raises(TypeError):
            tm.apply_configuration(
                model_holder=ModelHolder(int, {}),
                training_option=cast(Any, "not-an-option"),
                update_model=True,
                update_option=True,
            )

        published_holder = tm.model_holder
        assert published_holder is not None
        assert published_holder.target_model is existing_holder.target_model
        published = tm.training_option
        assert published is not None
        assert published.epoch == existing_option.epoch

    def test_mutated_option_failure_keeps_atomic_configuration_unchanged(self):
        tm = TrainingManager()
        existing_holder = ModelHolder(str, {})
        existing_option = _valid_training_option()
        invalid_option = _valid_training_option()
        invalid_option.lr = float("nan")
        tm.model_holder = existing_holder
        tm.training_option = existing_option

        with pytest.raises(ValueError):
            tm.apply_configuration(
                model_holder=ModelHolder(int, {}),
                training_option=invalid_option,
                update_model=True,
                update_option=True,
            )

        published_holder = tm.model_holder
        assert published_holder is not None
        assert published_holder.target_model is existing_holder.target_model
        published = tm.training_option
        assert published is not None
        assert published.epoch == existing_option.epoch


class TestGeneratePlan:
    def test_no_datasets_raises(self):
        tm = TrainingManager()
        tm.set_training_option(_valid_training_option())
        tm.set_model_holder(ModelHolder(int, {}))
        with pytest.raises(ValueError, match="No valid dataset"):
            tm.generate_plan(datasets=[])

    def test_invalid_replacement_does_not_clean_existing_trainer(self):
        tm = TrainingManager()
        existing_trainer = MagicMock()
        tm.trainer = existing_trainer
        tm.set_training_option(_valid_training_option())
        tm.set_model_holder(ModelHolder(int, {}))

        with pytest.raises(ValueError, match="No valid dataset"):
            tm.generate_plan(datasets=[], force_update=True)

        assert tm.trainer is existing_trainer
        existing_trainer.clean.assert_not_called()

    def test_no_training_option_raises(self):
        tm = TrainingManager()
        tm.set_model_holder(ModelHolder(int, {}))
        with pytest.raises(ValueError, match="training option"):
            tm.generate_plan(datasets=[MagicMock()])

    def test_no_model_holder_raises(self):
        tm = TrainingManager()
        tm.set_training_option(_valid_training_option())
        with pytest.raises(ValueError, match="model holder"):
            tm.generate_plan(datasets=[MagicMock()])

    @patch("XBrainLab.backend.training.Trainer")
    @patch("XBrainLab.backend.training.TrainingPlanHolder")
    def test_creates_trainer(self, mock_tph, mock_trainer):
        tm = TrainingManager()
        tm.set_training_option(_valid_training_option())
        tm.set_model_holder(ModelHolder(int, {}))
        datasets = [MagicMock(), MagicMock()]

        tm.generate_plan(datasets=datasets)

        assert mock_tph.call_count == 2
        mock_trainer.assert_called_once()
        assert tm.trainer == mock_trainer.return_value

    @patch("XBrainLab.backend.training.TrainingPlanHolder")
    def test_append_to_existing(self, mock_tph):
        tm = TrainingManager()
        tm.set_training_option(_valid_training_option())
        tm.set_model_holder(ModelHolder(int, {}))
        existing_trainer = MagicMock()
        tm.trainer = existing_trainer
        datasets = [MagicMock()]

        tm.generate_plan(datasets=datasets, append=True)

        existing_trainer.add_training_plan_holders.assert_called_once()

    def test_plan_construction_publishes_operation_without_holding_lock(
        self,
    ) -> None:
        construction_started = Event()
        release_construction = Event()
        errors: list[BaseException] = []
        tm = TrainingManager()
        tm.set_training_option(_valid_training_option())
        tm.set_model_holder(ModelHolder(int, {}))
        existing_trainer = MagicMock()
        tm.trainer = existing_trainer

        def construct_plan(*_args):
            construction_started.set()
            assert release_construction.wait(timeout=2.0)
            return MagicMock()

        def generate() -> None:
            try:
                tm.generate_plan(datasets=[MagicMock()], append=True)
            except BaseException as exc:
                errors.append(exc)

        worker = Thread(target=generate, daemon=True)
        with patch(
            "XBrainLab.backend.training.TrainingPlanHolder",
            side_effect=construct_plan,
        ):
            worker.start()
            assert construction_started.wait(timeout=1.0)
            acquired = tm._training_pipeline_lock.acquire(timeout=0.25)
            if acquired:
                tm._training_pipeline_lock.release()
            boundary = tm.capture_pipeline_mutation_boundary()
            release_construction.set()
            worker.join(timeout=1.0)

        assert acquired
        assert boundary.training_work_active is True
        assert not worker.is_alive()
        assert errors == []
        existing_trainer.add_training_plan_holders.assert_called_once()

    @patch(
        "XBrainLab.backend.training.TrainingPlanHolder",
        side_effect=RuntimeError("plan construction failed"),
    )
    def test_plan_construction_failure_releases_operation_lease(
        self,
        _mock_plan_holder,
    ) -> None:
        manager = TrainingManager()
        manager.set_training_option(_valid_training_option())
        manager.set_model_holder(ModelHolder(int, {}))
        existing_trainer = MagicMock()
        manager.trainer = existing_trainer

        with pytest.raises(RuntimeError, match="plan construction failed"):
            manager.generate_plan(
                datasets=[MagicMock()],
                force_update=True,
            )

        assert manager.trainer is existing_trainer
        assert manager._training_operation_owner is None

    @patch("XBrainLab.backend.training.TrainingPlanHolder")
    def test_append_publication_failure_releases_operation_lease(
        self,
        mock_plan_holder,
    ) -> None:
        manager = TrainingManager()
        manager.set_training_option(_valid_training_option())
        manager.set_model_holder(ModelHolder(int, {}))
        existing_trainer = MagicMock()
        existing_trainer.add_training_plan_holders.side_effect = RuntimeError(
            "append failed",
        )
        manager.trainer = existing_trainer
        mock_plan_holder.return_value = MagicMock()

        with pytest.raises(RuntimeError, match="append failed"):
            manager.generate_plan(
                datasets=[MagicMock()],
                append=True,
            )

        assert manager.trainer is existing_trainer
        assert manager._training_operation_owner is None


class TestTrain:
    def test_no_trainer_raises(self):
        tm = TrainingManager()
        with pytest.raises(ValueError, match="No valid trainer"):
            tm.train()

    def test_calls_run(self):
        tm = TrainingManager()
        tm.trainer = MagicMock()
        tm.train(interact=True)
        tm.trainer.run.assert_called_once_with(interact=True)

    def test_synchronous_training_does_not_block_stop_admission(self) -> None:
        run_started = Event()
        release_run = Event()
        stop_called = Event()

        class _BlockingTrainer:
            def run(self, *, interact: bool) -> None:
                run_started.set()
                if not interact:
                    assert release_run.wait(timeout=2.0)

            def wait_for_completion(self, *, timeout: float | None = None) -> bool:
                return release_run.wait(timeout=timeout)

            def stop(self, *, wait_timeout: float | None = None) -> bool:
                del wait_timeout
                stop_called.set()
                release_run.set()
                return True

        manager = TrainingManager()
        manager.trainer = cast(Any, _BlockingTrainer())
        errors: list[BaseException] = []
        stop_results: list[bool] = []

        def train() -> None:
            try:
                manager.train(interact=False)
            except BaseException as exc:
                errors.append(exc)

        def stop() -> None:
            try:
                stop_results.append(manager.stop_training(wait_timeout=0.25))
            except BaseException as exc:
                errors.append(exc)

        training = Thread(
            target=train,
            daemon=True,
        )
        stopping = Thread(
            target=stop,
            daemon=True,
        )

        training.start()
        assert run_started.wait(timeout=1.0)
        stopping.start()
        stop_admitted_while_run_active = stop_called.wait(timeout=0.25)
        release_run.set()
        training.join(timeout=1.0)
        stopping.join(timeout=1.0)

        assert stop_admitted_while_run_active
        assert not training.is_alive()
        assert not stopping.is_alive()
        assert errors == []
        assert stop_results == [True]

    def test_stop_during_training_admission_is_honored_after_saliency_cleanup(
        self,
    ) -> None:
        cancellation_started = Event()
        release_cancellation = Event()
        run_started = Event()
        stop_after_run = Event()

        class _AdmissionTrainer:
            def run(self, *, interact: bool) -> None:
                assert interact is True
                run_started.set()

            def stop(self, *, wait_timeout: float | None = None) -> bool:
                del wait_timeout
                if run_started.is_set():
                    stop_after_run.set()
                return True

        manager = TrainingManager()
        manager.trainer = cast(Any, _AdmissionTrainer())
        errors: list[BaseException] = []
        stop_results: list[bool] = []

        def block_saliency_cleanup(*, wait: bool) -> None:
            assert wait is True
            cancellation_started.set()
            assert release_cancellation.wait(timeout=2.0)

        manager._cancel_post_training_saliency = block_saliency_cleanup  # type: ignore[method-assign]

        def train() -> None:
            try:
                manager.train(interact=True)
            except BaseException as exc:
                errors.append(exc)

        def stop() -> None:
            try:
                stop_results.append(manager.stop_training(wait_timeout=1.0))
            except BaseException as exc:
                errors.append(exc)

        training = Thread(
            target=train,
            daemon=True,
        )
        stopping = Thread(
            target=stop,
            daemon=True,
        )

        training.start()
        assert cancellation_started.wait(timeout=1.0)
        stopping.start()
        release_cancellation.set()
        training.join(timeout=1.0)
        stopping.join(timeout=1.0)

        assert not training.is_alive()
        assert not stopping.is_alive()
        assert run_started.is_set()
        assert stop_after_run.is_set()
        assert errors == []
        assert stop_results == [True]


class TestStopTraining:
    def test_no_trainer_raises(self):
        tm = TrainingManager()
        with pytest.raises(ValueError, match="No valid trainer"):
            tm.stop_training()

    def test_sets_interrupt(self):
        tm = TrainingManager()
        tm.trainer = MagicMock()
        tm.trainer.stop.return_value = True
        assert tm.stop_training(wait_timeout=0.25) is True
        tm.trainer.stop.assert_called_once_with(wait_timeout=0.25)


class TestIsTraining:
    def test_no_trainer_returns_false(self):
        tm = TrainingManager()
        assert tm.is_training() is False

    def test_delegates_to_trainer(self):
        tm = TrainingManager()
        tm.trainer = MagicMock()
        tm.trainer.is_running.return_value = True
        assert tm.is_training() is True


class TestExportOutputCsv:
    def test_no_trainer_raises(self):
        tm = TrainingManager()
        with pytest.raises(ValueError, match="No valid training plan"):
            tm.export_output_csv("out.csv", "p", "rp")

    def test_no_record_raises(self):
        tm = TrainingManager()
        tm.trainer = MagicMock()
        plan = MagicMock()
        plan.get_eval_record.return_value = None
        tm.trainer.get_real_training_plan.return_value = plan
        with pytest.raises(ValueError, match="No evaluation record"):
            tm.export_output_csv("out.csv", "p", "rp")

    def test_exports(self):
        tm = TrainingManager()
        tm.trainer = MagicMock()
        record = MagicMock()
        plan = MagicMock()
        plan.get_eval_record.return_value = record
        tm.trainer.get_real_training_plan.return_value = plan
        tm.export_output_csv("out.csv", "p", "rp")
        record.export_csv.assert_called_once_with("out.csv")


class TestSaliencyParams:
    def test_get_none_default(self):
        tm = TrainingManager()
        assert tm.get_saliency_params() is None

    def test_set_and_get(self):
        tm = TrainingManager()
        params = {"SmoothGrad": {"n_samples": 50}}
        tm.set_saliency_params(params)
        assert tm.get_saliency_params() == params

    def test_propagates_to_existing_plans(self):
        tm = TrainingManager()
        plan_holder = object.__new__(TrainingPlanHolder)
        plan_holder.train_record_list = []
        plan_holder._state_tracker = None
        plan_holder.saliency_params = {}
        tm.trainer = Trainer([plan_holder])
        params = {"SmoothGrad": {"n_samples": 50}}

        tm.set_saliency_params(params)

        assert plan_holder.saliency_params == params

    def test_manual_saliency_computation_does_not_hold_pipeline_lock(self) -> None:
        compute_started = Event()
        release_compute = Event()

        class _Holder:
            def prepare_saliency_update(self, _params):
                compute_started.set()
                assert release_compute.wait(timeout=2.0)
                return MagicMock()

        class _Trainer:
            def get_training_plan_holders(self):
                return [_Holder()]

        manager = TrainingManager()
        manager.trainer = cast(Any, _Trainer())
        worker = Thread(
            target=manager.set_saliency_params,
            args=({"SmoothGrad": {"n_samples": 5}},),
            daemon=True,
        )

        with patch(
            "XBrainLab.backend.training.training_plan."
            "publish_prepared_saliency_updates",
        ):
            worker.start()
            assert compute_started.wait(timeout=1.0)
            acquired = manager._training_pipeline_lock.acquire(timeout=0.25)
            if acquired:
                manager._training_pipeline_lock.release()
            release_compute.set()
            worker.join(timeout=1.0)

        assert acquired
        assert not worker.is_alive()

    def test_manual_saliency_discards_result_after_trainer_replacement(self) -> None:
        compute_started = Event()
        release_compute = Event()
        errors: list[BaseException] = []

        class _Holder:
            def prepare_saliency_update(self, _params):
                compute_started.set()
                assert release_compute.wait(timeout=2.0)
                return MagicMock()

        class _Trainer:
            def get_training_plan_holders(self):
                return [_Holder()]

        manager = TrainingManager()
        original = _Trainer()
        replacement = _Trainer()
        manager.trainer = cast(Any, original)

        def compute() -> None:
            try:
                manager.set_saliency_params({"SmoothGrad": {"n_samples": 5}})
            except BaseException as exc:
                errors.append(exc)

        worker = Thread(target=compute, daemon=True)
        with patch(
            "XBrainLab.backend.training.training_plan."
            "publish_prepared_saliency_updates",
        ) as publish:
            worker.start()
            assert compute_started.wait(timeout=1.0)
            with manager._training_pipeline_lock:
                manager.trainer = cast(Any, replacement)
            release_compute.set()
            worker.join(timeout=1.0)

        assert not worker.is_alive()
        assert len(errors) == 1
        assert isinstance(errors[0], StaleSaliencyUpdateError)
        assert manager.trainer is replacement
        assert manager.saliency_params is None
        assert manager._training_operation_owner is None
        publish.assert_not_called()

    def test_manual_saliency_releases_lease_when_plan_snapshot_fails(self) -> None:
        manager = TrainingManager()
        trainer = MagicMock()
        trainer.get_training_plan_holders.side_effect = RuntimeError(
            "plan snapshot failed"
        )
        manager.trainer = trainer

        with pytest.raises(RuntimeError, match="plan snapshot failed"):
            manager.set_saliency_params({"SmoothGrad": {"n_samples": 5}})

        assert manager._training_operation_owner is None

    def test_automatic_saliency_admission_is_blocked_by_training_operation(
        self,
    ) -> None:
        manager = TrainingManager()
        trainer = _StablePipelineTrainer()
        manager.trainer = cast(Any, trainer)
        run = trainer.get_terminal_outcome().run
        assert run is not None
        target = PostTrainingSaliencyTarget(
            run=run,
            finished_runs_before=0,
            finished_runs_after=1,
            append=True,
        )

        with manager._training_pipeline_lock, manager._saliency_job_lock:
            lease = manager._begin_training_operation_locked(
                kind="cleanup",
                trainer=trainer,
            )
            admitted = manager._admit_post_training_saliency_request_locked(
                target=target,
                trainer=trainer,
                training_generation=trainer.generation,
                request_generation=1,
                cancellation_epoch=manager._saliency_cancellation_epoch,
            )
            manager._finish_training_operation_locked(lease)

        assert admitted is None
        assert manager._saliency_request_owner is None


class TestCleanTrainer:
    def test_force_update_true(self):
        tm = TrainingManager()
        tm.trainer = MagicMock()
        tm.clean_trainer(force_update=True)
        assert tm.trainer is None

    def test_force_update_does_not_interrupt_inactive_trainer(self):
        tm = TrainingManager()
        trainer = MagicMock()
        trainer.is_running.return_value = False
        tm.trainer = trainer

        tm.clean_trainer(force_update=True)

        trainer.clean.assert_called_once_with(force_update=False)
        assert tm.trainer is None

    def test_force_update_keeps_trainer_when_cleanup_fails(self):
        tm = TrainingManager()
        trainer = MagicMock()
        trainer.clean.side_effect = RuntimeError("Training did not stop")
        tm.trainer = trainer

        with pytest.raises(RuntimeError, match="did not stop"):
            tm.clean_trainer(force_update=True)

        assert tm.trainer is trainer
        assert tm._training_operation_owner is None

    def test_saliency_cancellation_failure_releases_cleanup_lease(self) -> None:
        manager = TrainingManager()
        trainer = MagicMock()
        manager.trainer = trainer
        manager._cancel_post_training_saliency = MagicMock(
            side_effect=RuntimeError("saliency cancellation failed"),
        )

        with pytest.raises(RuntimeError, match="saliency cancellation failed"):
            manager.clean_trainer(force_update=True)

        assert manager.trainer is trainer
        assert manager._training_operation_owner is None
        trainer.clean.assert_not_called()

    def test_cleanup_wait_does_not_hold_pipeline_lock(self) -> None:
        clean_started = Event()
        release_clean = Event()

        class _Trainer:
            def is_running(self) -> bool:
                return False

            def clean(self, *, force_update: bool) -> None:
                assert force_update is False
                clean_started.set()
                assert release_clean.wait(timeout=2.0)

        manager = TrainingManager()
        manager.trainer = cast(Any, _Trainer())
        worker = Thread(target=manager.clean_trainer, daemon=True)

        worker.start()
        assert clean_started.wait(timeout=1.0)
        acquired = manager._training_pipeline_lock.acquire(timeout=0.25)
        if acquired:
            manager._training_pipeline_lock.release()
        active_boundary = manager.capture_pipeline_mutation_boundary()
        publication_attempted = Event()
        with pytest.raises(StaleTrainingPipelineMutationError):
            manager.commit_pipeline_replacement(
                active_boundary,
                publish=publication_attempted.set,
            )
        release_clean.set()
        worker.join(timeout=1.0)

        assert acquired
        assert active_boundary.training_work_active is True
        assert publication_attempted.is_set() is False
        assert not worker.is_alive()
        assert manager.trainer is None
        assert manager._training_operation_owner is None

    def test_force_update_false_with_trainer_raises(self):
        tm = TrainingManager()
        tm.trainer = MagicMock()
        with (
            patch.object(tm, "_cancel_post_training_saliency") as cancel,
            pytest.raises(ValueError, match="already been done"),
        ):
            tm.clean_trainer(force_update=False)

        cancel.assert_not_called()

    def test_force_update_false_no_trainer_ok(self):
        tm = TrainingManager()
        tm.clean_trainer(force_update=False)
        assert tm.trainer is None


class TestHasTrainer:
    def test_false_when_none(self):
        tm = TrainingManager()
        assert tm.has_trainer() is False

    def test_true_when_set(self):
        tm = TrainingManager()
        tm.trainer = MagicMock()
        assert tm.has_trainer() is True
