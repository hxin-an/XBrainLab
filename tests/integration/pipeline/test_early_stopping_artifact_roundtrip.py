"""Real optimizer, selected weights, final metrics and safe artifact evidence."""

from pathlib import Path
from unittest.mock import patch

import mne
import numpy as np
import pytest
import torch

from XBrainLab.backend.application.training_history import project_training_history_rows
from XBrainLab.backend.dataset import Dataset, DataSplittingConfig, Epochs, TrainingType
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.training.model_holder import ModelHolder
from XBrainLab.backend.training.option import TrainingEvaluation, TrainingOption
from XBrainLab.backend.training.record import RecordKey, TrainRecord
from XBrainLab.backend.training.record.artifact_store import load_model_state_dict
from XBrainLab.backend.training.trainer import Trainer
from XBrainLab.backend.training.training_plan import TrainingPlanHolder
from XBrainLab.backend.training_manager import TrainingManager
from XBrainLab.backend.training_state_contract import TrainingOutcomeState


class TinyLinear(torch.nn.Module):
    def __init__(self, **_kwargs):
        super().__init__()
        self.linear = torch.nn.Linear(1, 2, bias=False)
        torch.nn.init.zeros_(self.linear.weight)

    def forward(self, inputs):
        return self.linear(inputs.flatten(start_dim=1))


@pytest.fixture
def training_manager():
    manager = TrainingManager()
    yield manager
    manager.clean_trainer()


@pytest.fixture
def tiny_training(tmp_path):
    # Opposing validation examples make validation loss strictly worse as the
    # training loss improves, without mocking metrics or the epoch runner.
    labels = np.tile([0, 1], 6)
    signals = (2 * labels - 1).astype(float).reshape(-1, 1, 1)
    signals[4:8] *= -1
    events = np.column_stack((np.arange(12), np.zeros(12, dtype=int), labels))
    epoch_data = Epochs(
        [
            Raw(
                "tiny-early-stop.fif",
                mne.EpochsArray(
                    signals,
                    mne.create_info(["Cz"], sfreq=1, ch_types="eeg"),
                    events=events,
                    event_id={"left": 0, "right": 1},
                    verbose=False,
                ),
            )
        ]
    )
    dataset = Dataset(epoch_data, DataSplittingConfig(TrainingType.FULL, False, [], []))
    dataset.set_name("early-stop-oracle")
    dataset.train_mask[:4] = True
    dataset.val_mask[4:8] = True
    dataset.test_mask[8:] = True
    option = TrainingOption(
        output_dir=str(tmp_path),
        optim=torch.optim.SGD,
        optim_params={},
        use_cpu=True,
        gpu_idx=None,
        epoch=8,
        bs=4,
        lr=0.5,
        checkpoint_epoch=1,
        evaluation_option=TrainingEvaluation.VAL_LOSS,
        repeat_num=2,
        seed=17,
        early_stopping_enabled=True,
        early_stopping_patience=1,
        early_stopping_min_delta=0.0,
    )
    model_holder = ModelHolder(TinyLinear, {})
    return dataset, option, model_holder


def test_early_stop_evaluates_nonfinal_best_weights_and_reloads_real_artifacts(
    tiny_training,
):
    dataset, option, model_holder = tiny_training
    holder = TrainingPlanHolder(model_holder, dataset, option, {})
    holder.train()

    assert holder.error is None
    assert holder.is_finished()
    for index, record in enumerate(holder.get_plans()):
        assert record.seed == 17 + index
        assert record.epoch == 2
        assert record.is_finished()
        assert record.early_stopping["stopped_early"] is True
        assert record.early_stopping["best_epoch"] == 1
        assert record.early_stopping["stop_epoch"] == 2
        assert record.val[RecordKey.LOSS][0] < record.val[RecordKey.LOSS][1]
        assert record.train[RecordKey.LOSS][0] > record.train[RecordKey.LOSS][1]

        path = Path(record.target_path)
        selected = load_model_state_dict(path / "best_val_loss_model")
        final = load_model_state_dict(path / "Epoch-2-model")
        torch.testing.assert_close(
            selected["linear.weight"], torch.tensor([[-0.25], [0.25]])
        )
        assert not torch.equal(selected["linear.weight"], final["linear.weight"])
        expected_logits = torch.tensor([[0.25, -0.25], [-0.25, 0.25]]).repeat(2, 1)
        evaluation = record.get_eval_record()
        assert evaluation.evaluation_split == "test"
        np.testing.assert_allclose(
            evaluation.output, expected_logits.numpy(), rtol=1e-6
        )
        np.testing.assert_array_equal(evaluation.label, [0, 1, 0, 1])

        # Bind a new record to the existing directory; all artifact readers and
        # writers remain real. Loading statistics is intentionally not resume.
        with patch.object(TrainRecord, "init_dir"):
            restored = TrainRecord(
                index,
                dataset,
                TinyLinear(),
                option,
                0,
                model_identity=model_holder.catalog_identity,
            )
        restored.target_path = record.target_path
        restored._artifact_io_path = record._artifact_io_path
        restored.load()
        assert restored.seed == record.seed
        assert restored.epoch == record.epoch
        assert restored.early_stopping == record.early_stopping
        assert restored.best_record == record.best_record
        assert restored.train == record.train
        assert restored.val == record.val
        assert restored.is_finished()
        assert set(restored.get_available_evaluation_splits()) == {
            "training",
            "validation",
            "test",
        }
        for split in restored.get_available_evaluation_splits():
            actual = restored.get_evaluation_record_for_split(split)
            original = record.get_evaluation_record_for_split(split)
            np.testing.assert_array_equal(actual.label, original.label)
            np.testing.assert_array_equal(actual.output, original.output)
            assert actual.get_acc() == original.get_acc()


@pytest.mark.parametrize(
    "failure",
    [
        torch.OutOfMemoryError("CUDA out of memory"),
        ValueError("Training model output contains NaN"),
    ],
    ids=["oom", "generic-model-error"],
)
def test_failure_then_fresh_real_training_preserves_failed_history(
    tiny_training, training_manager, failure
):
    dataset, option, model_holder = tiny_training
    manager = training_manager
    manager.apply_configuration(
        model_holder=model_holder,
        training_option=option,
        update_model=True,
        update_option=True,
    )
    manager.generate_plan([dataset])
    failed_holder = manager.get_training_plan_holders_snapshot()[0]
    # Inject allocation/model failure at the real forward seam. Plan,
    # record, optimizer, worker and manager lifecycle remain production code.
    with patch.object(TinyLinear, "forward", side_effect=failure):
        manager.train(interact=True)
        assert manager.wait_for_training_completion(timeout=10)
    failed_outcome = manager.get_training_terminal_outcome()
    assert failed_outcome.state is TrainingOutcomeState.FAILED
    assert str(failure) in failed_outcome.detail
    failed_record = failed_holder.get_plans()[0]
    failed_row = project_training_history_rows(
        [{"plan": failed_holder, "record": failed_record}]
    )[0]
    assert failed_row["status"] == "Failed"
    assert failed_row["status_detail"] == failed_holder.error
    assert all(record.epoch == 0 for record in failed_holder.get_plans())
    assert all(record.eval_record is None for record in failed_holder.get_plans())
    assert all(
        not (Path(record.target_path) / "record").exists()
        for record in failed_holder.get_plans()
    )

    manager.generate_plan([dataset], append=True)
    manager.train(interact=True)
    assert manager.wait_for_training_completion(timeout=10)
    success = manager.get_training_terminal_outcome()
    assert success.state is TrainingOutcomeState.COMPLETED
    assert success.run != failed_outcome.run
    holders = manager.get_training_plan_holders_snapshot()
    assert holders[0] is failed_holder
    assert str(failure) in failed_holder.error
    assert not failed_holder.is_finished()
    assert holders[1].is_finished()
    assert all(
        record.get_eval_record().get_acc() == 1.0 for record in holders[1].get_plans()
    )
    assert all(
        (Path(record.target_path) / "record").is_file()
        for record in holders[1].get_plans()
    )


@pytest.mark.parametrize(
    "failure",
    [torch.OutOfMemoryError("CUDA out of memory"), ValueError("Invalid model output")],
    ids=["oom", "generic"],
)
def test_later_repeat_failure_preserves_completed_history(tiny_training, failure):
    dataset, option, model_holder = tiny_training
    holder = TrainingPlanHolder(model_holder, dataset, option, {})
    first, second = holder.get_plans()

    def fail_forward(_model, _inputs):
        raise failure

    with second.model.register_forward_pre_hook(fail_forward):
        holder.train()
    assert first.is_finished()
    assert not second.is_finished()
    rows = project_training_history_rows(
        [{"plan": holder, "record": record} for record in holder.get_plans()]
    )
    assert rows[0]["status"] == "Completed early"
    assert rows[1]["status"] == "Failed"
    assert rows[1]["status_detail"] == holder.error


@pytest.mark.parametrize("history_source", ["publication", "query"])
def test_training_panel_preserves_real_early_stop_status(
    tiny_training, qtbot, history_source
):
    from dataclasses import replace
    from types import SimpleNamespace

    from XBrainLab.backend.application import (
        ApplicationStateSnapshot,
        ApplicationViewPublication,
        CapabilityPolicy,
    )
    from XBrainLab.backend.application.results import ChangedState, CommandResult
    from XBrainLab.backend.training_state_contract import TrainingTerminalOutcome
    from XBrainLab.ui.panels.training.panel import TrainingPanel

    dataset, option, model_holder = tiny_training
    holder = TrainingPlanHolder(model_holder, dataset, option, {})
    holder.train()
    assert holder.error is None
    rows = project_training_history_rows(
        [{"plan": holder, "record": record} for record in holder.get_plans()]
    )
    assert [row["status"] for row in rows] == ["Completed early"] * 2
    initial = ApplicationStateSnapshot.empty()
    publication = ApplicationViewPublication(
        generation=1,
        revision=1,
        state=replace(
            initial,
            training=replace(
                initial.training,
                terminal_outcome=TrainingTerminalOutcome(
                    TrainingOutcomeState.COMPLETED
                ),
            ),
        ),
        capabilities=CapabilityPolicy({}),
        verified=True,
        stale=False,
        training_history=tuple(rows) if history_source == "publication" else None,
    )
    ports = SimpleNamespace(
        get_view_publication=lambda: publication,
        query_training_history=lambda **_kwargs: CommandResult.success_result(
            "history",
            "history",
            {},
            ChangedState(),
            diagnostics={"payload_type": "training_history", "rows": rows},
        ),
    )
    # Only the publication transport is detached; training, projection, widgets,
    # terminal reconciliation and subsequent progress refresh remain real.
    panel = TrainingPanel(query_port=ports)
    panel._publication_port = ports
    qtbot.addWidget(panel)
    panel.update_panel()
    panel.update_loop(log_epochs=True)

    assert [panel.history_table.item(index, 3).text() for index in range(2)] == [
        "Completed early",
        "Completed early",
    ]
    assert rows[1]["status_detail"] in panel.log_text.toPlainText()
    assert panel.tab_acc.test_vals == rows[1]["metrics"]["test"]["accuracy"]
    panel.close()


@pytest.mark.parametrize("failed_repeat", [0, 1])
def test_final_artifact_failure_does_not_publish_completed_evaluation(
    tiny_training, monkeypatch, failed_repeat
):
    dataset, option, model_holder = tiny_training
    holder = TrainingPlanHolder(model_holder, dataset, option, {})
    trainer = Trainer([holder])
    record = holder.get_plans()[failed_repeat]
    export_checkpoint = record.export_checkpoint

    def fail_final_export():
        if record.eval_record is not None:
            assert not trainer.get_state_snapshot_token().stable
            raise OSError("disk full during final artifact export")
        export_checkpoint()

    monkeypatch.setattr(record, "export_checkpoint", fail_final_export)
    holder.train()

    assert holder.error == "disk full during final artifact export"
    assert trainer.get_state_snapshot_token().stable
    assert not record.is_finished()
    assert record.eval_record is None
    assert record.get_available_evaluation_splits() == []
    rows = project_training_history_rows(
        [{"plan": holder, "record": item} for item in holder.get_plans()]
    )
    assert rows[failed_repeat]["status"] == "Failed"
    assert rows[failed_repeat]["status_detail"] == holder.error
    if failed_repeat:
        assert rows[0]["status"] == "Completed early"
        assert holder.get_plans()[0].get_eval_record().get_acc() == 1.0
        assert (Path(holder.get_plans()[0].target_path) / "eval").is_file()
