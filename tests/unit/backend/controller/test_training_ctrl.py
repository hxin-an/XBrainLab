"""Coverage tests for TrainingController uncovered lines."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

from XBrainLab.backend.controller.training_controller import TrainingController


def _make_ctrl():
    study = MagicMock()
    study.is_training.return_value = False
    study.trainer = None
    study.loaded_data_list = []
    study.epoch_data = None
    study.datasets = None
    study.model_holder = None
    study.training_option = None
    study.dataset_generator = None
    study.preprocessed_data_list = []
    return TrainingController(study), study


class TestMonitorLoop:
    def test_loop_notifies_stopped_when_not_training(self):
        ctrl, study = _make_ctrl()
        study.is_training.return_value = False
        events = []
        ctrl.subscribe("training_stopped", lambda: events.append("stopped"))
        ctrl._monitor_loop()
        assert "stopped" in events

    def test_loop_breaks_on_shutdown(self):
        ctrl, study = _make_ctrl()
        study.is_training.return_value = True
        ctrl._shutdown_event.set()
        ctrl._monitor_loop()

    def test_loop_emits_updated_then_stops(self):
        ctrl, study = _make_ctrl()
        call_count = [0]

        def side_effect():
            call_count[0] += 1
            return call_count[0] > 1

        study.is_training.side_effect = [True, False]
        ctrl._shutdown_event = MagicMock(spec=threading.Event)
        ctrl._shutdown_event.is_set.return_value = False
        ctrl._shutdown_event.wait.return_value = False
        events = []
        ctrl.subscribe("training_updated", lambda: events.append("updated"))
        ctrl.subscribe("training_stopped", lambda: events.append("stopped"))
        ctrl._monitor_loop()
        assert "updated" in events


class TestStartMonitoring:
    def test_starts_new_thread(self):
        ctrl, _study = _make_ctrl()
        ctrl._start_monitoring()
        assert ctrl._monitor_thread is not None
        ctrl._shutdown_event.set()
        ctrl._monitor_thread.join(timeout=2.0)

    def test_noop_if_alive(self):
        ctrl, _ = _make_ctrl()
        existing = MagicMock()
        existing.is_alive.return_value = True
        ctrl._monitor_thread = existing
        ctrl._start_monitoring()
        assert ctrl._monitor_thread is existing


class TestAccessorsAndConfig:
    def test_get_trainer(self):
        ctrl, study = _make_ctrl()
        study.trainer = "t"
        assert ctrl.get_trainer() == "t"

    def test_has_loaded_data(self):
        ctrl, study = _make_ctrl()
        assert ctrl.has_loaded_data() is False
        study.loaded_data_list = [1]
        assert ctrl.has_loaded_data() is True

    def test_has_epoch_data(self):
        ctrl, study = _make_ctrl()
        assert ctrl.has_epoch_data() is False
        study.epoch_data = "e"
        assert ctrl.has_epoch_data() is True

    def test_get_epoch_data(self):
        ctrl, study = _make_ctrl()
        study.epoch_data = "ep"
        assert ctrl.get_epoch_data() == "ep"

    def test_clean_datasets(self):
        ctrl, study = _make_ctrl()
        ctrl.clean_datasets(force_update=True)
        study.clean_datasets.assert_called_once_with(force_update=True)

    def test_apply_data_splitting(self):
        ctrl, study = _make_ctrl()
        gen = MagicMock()
        ctrl.apply_data_splitting(gen)
        gen.apply.assert_called_once_with(study)

    def test_set_model_holder(self):
        ctrl, study = _make_ctrl()
        ctrl.set_model_holder("mh")
        study.set_model_holder.assert_called_once_with("mh")

    def test_set_training_option(self):
        ctrl, study = _make_ctrl()
        ctrl.set_training_option("to")
        study.set_training_option.assert_called_once_with("to")

    def test_get_training_option(self):
        ctrl, study = _make_ctrl()
        study.training_option = "opt"
        assert ctrl.get_training_option() == "opt"

    def test_get_model_holder(self):
        ctrl, study = _make_ctrl()
        study.model_holder = "mh"
        assert ctrl.get_model_holder() == "mh"

    def test_get_dataset_generator(self):
        ctrl, study = _make_ctrl()
        study.dataset_generator = "dg"
        assert ctrl.get_dataset_generator() == "dg"

    def test_get_loaded_data_list(self):
        ctrl, study = _make_ctrl()
        study.loaded_data_list = ["a"]
        assert ctrl.get_loaded_data_list() == ["a"]

    def test_get_preprocessed_data_list(self):
        ctrl, study = _make_ctrl()
        study.preprocessed_data_list = ["b"]
        assert ctrl.get_preprocessed_data_list() == ["b"]
