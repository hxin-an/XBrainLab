"""Persisted CPU predictions reach Evaluation through the real service and worker.

Synthetic FIF data proves result routing and presentation, not scientific accuracy.
No catalog, render publisher, application port, or worker callback is substituted.
"""

from pathlib import Path

import mne
import numpy as np

from XBrainLab.backend.application import (
    ApplyInterpretationCommand,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    EvaluationCrossFoldIdentity,
    EvaluationPlanIdentity,
    EvaluationRunIdentity,
    NewSessionCommand,
    PreviewInterpretationCommand,
    SaveDatasetSplitCommand,
    ScanSourceCommand,
    TrainCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.backend.application.owned_work import OwnedWorkKind, OwnedWorkPhase
from XBrainLab.backend.application.runtime import get_application_service
from XBrainLab.backend.study import Study
from XBrainLab.backend.training.record import EvalRecord
from XBrainLab.ui.main_window import MainWindow
from XBrainLab.ui.panels.evaluation.panel import EvaluationPanel


def _write_tiny_fif(path: Path) -> None:
    sfreq = 128
    raw = mne.io.RawArray(
        np.random.default_rng(1729).normal(size=(4, sfreq * 26)) * 1e-6,
        mne.create_info(["C3", "C4", "Cz", "Pz"], sfreq, ch_types="eeg"),
        verbose=False,
    )
    raw.set_annotations(
        mne.Annotations(
            onset=list(range(1, 25, 2)),
            duration=[0.0] * 12,
            description=["left hand", "right hand"] * 6,
        )
    )
    raw.save(path, overwrite=True, verbose=False)


def _assert_result_values(panel, labels, outputs, *, percentages=False) -> None:
    """Compare actual artists/cells against independently counted predictions."""
    predictions = outputs.argmax(axis=1)
    confusion = np.array(
        [
            [
                np.count_nonzero((labels == truth) & (predictions == guess))
                for guess in range(2)
            ]
            for truth in range(2)
        ]
    )
    support = confusion.sum(axis=1)
    expected_image = (
        np.divide(
            confusion,
            support[:, None],
            out=np.zeros((2, 2), dtype=float),
            where=support[:, None] != 0,
        )
        if percentages
        else confusion
    )
    axis = panel.matrix_widget.fig.axes[0]
    np.testing.assert_allclose(axis.images[0].get_array(), expected_image)
    assert [text.get_text() for text in axis.texts] == [
        f"{value:.1%}" if percentages else str(int(value))
        for value in expected_image.flat
    ]
    assert [" ".join(label.get_text().split()) for label in axis.get_xticklabels()] == [
        "left hand",
        "right hand",
    ]
    table = panel.metrics_table
    assert table.rowCount() == 3
    expected_metrics = []
    for index, name in enumerate(("left hand", "right hand")):
        true_positive = int(confusion[index, index])
        predicted_count = int(confusion[:, index].sum())
        actual_count = int(support[index])
        precision = true_positive / predicted_count if predicted_count else 0.0
        recall = true_positive / actual_count if actual_count else 0.0
        f1 = (
            2 * true_positive / (predicted_count + actual_count)
            if predicted_count + actual_count
            else 0.0
        )
        expected_metrics.append((precision, recall, f1))
        assert [table.item(index, column).text() for column in range(5)] == [
            name,
            f"{precision:.4f}",
            f"{recall:.4f}",
            f"{f1:.4f}",
            str(actual_count),
        ]
    macro = np.mean(expected_metrics, axis=0)
    assert [table.item(2, column).text() for column in range(5)] == [
        "Macro Avg",
        *(f"{value:.4f}" for value in macro),
        str(len(labels)),
    ]
    assert len(panel.bar_chart.ax.containers) == 3
    assert [label.get_text() for label in panel.bar_chart.ax.get_xticklabels()] == [
        "left hand",
        "right hand",
    ]
    for metric_index, container in enumerate(panel.bar_chart.ax.containers):
        np.testing.assert_allclose(
            [patch.get_height() for patch in container],
            np.asarray(expected_metrics)[:, metric_index],
        )


def test_persisted_runs_splits_and_folds_render_then_reset_without_stale_results(
    qtbot, tmp_path
):
    source = tmp_path / "evaluation_raw.fif"
    _write_tiny_fif(source)
    study = Study()
    service = get_application_service(study)
    host = MainWindow(study)
    qtbot.addWidget(host)
    panel = None
    host.resize(1280, 920)
    host.show()
    try:
        commands = (
            ScanSourceCommand(source_path=str(source), source_hint="file"),
            PreviewInterpretationCommand(choices={"label_carrier": "embedded_events"}),
            ValidateInterpretationCommand(),
            ApplyInterpretationCommand(confirmed=True),
            CreateEpochCommand(
                t_min=0.0, t_max=1.3, event_ids=["left hand", "right hand"]
            ),
            SaveDatasetSplitCommand(
                split_config={
                    "train_type": "Full Data",
                    "is_cross_validation": True,
                    "val_splitters": [],
                    "test_splitters": [
                        {
                            "split_type": "By Trial",
                            "split_unit": "K Fold",
                            "value": "2",
                            "is_option": True,
                        }
                    ],
                }
            ),
            ConfigureTrainingCommand(
                model_name="EEGNet",
                epoch=1,
                batch_size=2,
                repeat=2,
                learning_rate=0.001,
                device="cpu",
                seed=1729,
                output_dir=str(tmp_path / "trained"),
                evaluation_option="Last Epoch",
            ),
            TrainCommand(confirmed=True, interactive=True),
        )
        for command in commands:
            result = service.execute(command)
            assert result.ok, result.message
        qtbot.waitUntil(
            lambda: service.get_state().training.finished_run_count == 4
            and not service.get_state().training.is_running,
            timeout=20000,
        )
        qtbot.waitUntil(
            lambda: service.wait_for_background_tasks(timeout=0.0), timeout=20000
        )
        plans = service.training_runtime.training_plan_holders()
        assert len(plans) == 2
        saved = {}
        for plan_index, plan in enumerate(plans):
            for run_index, record in enumerate(plan.get_plans()):
                for split in ("test", "training"):
                    persisted = EvalRecord.load(
                        record.target_path,
                        artifact_basename="eval"
                        if split == "test"
                        else f"eval-{split}",
                    )
                    assert persisted is not None
                    assert persisted.evaluation_split == split
                    saved[plan_index, run_index, split] = persisted

        host.switch_page(3)
        qtbot.waitUntil(lambda: 3 in host._loaded_panel_indices, timeout=5000)
        panel = host.evaluation_panel
        assert isinstance(panel, EvaluationPanel)

        def wait_for_selection(selection, split):
            qtbot.waitUntil(
                lambda: panel._evaluation_render is not None
                and panel._evaluation_render.request.selection == selection
                and panel._evaluation_render.data.evaluation_split == split
                and panel.evaluation_background_work_idle(),
                timeout=5000,
            )
            rendered = panel._evaluation_render
            assert (
                service.get_owned_operation(rendered.operation_id).phase
                is OwnedWorkPhase.COMPLETED
            )
            assert service.get_active_owned_operation(OwnedWorkKind.EVALUATION) is None
            return rendered

        panel.update_panel()
        first = EvaluationRunIdentity(EvaluationPlanIdentity(0), 0)
        wait_for_selection(first, "test")
        assert [
            panel.run_combo.itemText(i) for i in range(panel.run_combo.count())
        ] == ["Run 1", "Run 2", "Summary"]
        assert {
            panel.split_combo.itemData(i) for i in range(panel.split_combo.count())
        } == {"test", "training"}
        for run_index, split in ((0, "test"), (1, "test"), (1, "training")):
            identity = EvaluationRunIdentity(EvaluationPlanIdentity(0), run_index)
            panel.run_combo.setCurrentIndex(
                next(
                    index
                    for index in range(panel.run_combo.count())
                    if panel.run_combo.itemData(index) == identity
                )
            )
            panel.split_combo.setCurrentIndex(panel.split_combo.findData(split))
            rendered = wait_for_selection(identity, split)
            expected = saved[0, run_index, split]
            np.testing.assert_array_equal(rendered.data.labels, expected.label)
            np.testing.assert_array_equal(rendered.data.outputs, expected.output)
            _assert_result_values(panel, expected.label, expected.output)

        panel.chk_percentage.setChecked(True)
        _assert_result_values(panel, expected.label, expected.output, percentages=True)
        panel.chk_percentage.setChecked(False)
        _assert_result_values(panel, expected.label, expected.output)

        panel.run_combo.setCurrentIndex(panel.run_combo.findText("Summary"))
        wait_for_selection(EvaluationPlanIdentity(0), "training")
        _assert_result_values(
            panel,
            np.concatenate([saved[0, i, "training"].label for i in range(2)]),
            np.concatenate([saved[0, i, "training"].output for i in range(2)]),
        )

        panel.model_combo.setCurrentIndex(panel.model_combo.findText("All Folds"))
        panel.run_combo.setCurrentIndex(1)
        cross_fold = panel.run_combo.currentData()
        assert isinstance(cross_fold, EvaluationCrossFoldIdentity)
        assert cross_fold.run_index == 1
        rendered = wait_for_selection(cross_fold, "test")
        labels = np.concatenate([saved[i, 1, "test"].label for i in range(2)])
        outputs = np.concatenate([saved[i, 1, "test"].output for i in range(2)])
        assert len(labels) == 12
        np.testing.assert_array_equal(rendered.data.labels, labels)
        np.testing.assert_array_equal(rendered.data.outputs, outputs)
        _assert_result_values(panel, labels, outputs)

        # Corrupt only the selected prediction input. Real publisher validation,
        # registry failure, worker delivery and error presentation still execute.
        selected_record = (
            plans[0].get_plans()[0].get_evaluation_record_for_split("test")
        )
        original_outputs = selected_record.output
        invalid_outputs = original_outputs.copy()
        invalid_outputs[0, 0] = np.nan
        selected_record.output = invalid_outputs
        try:
            panel.model_combo.setCurrentIndex(0)
            panel.run_combo.setCurrentIndex(0)
            panel.split_combo.setCurrentIndex(panel.split_combo.findData("test"))
            failed_operation = panel._evaluation_render_active_operation_id
            assert failed_operation is not None
            qtbot.waitUntil(panel.evaluation_background_work_idle, timeout=5000)
            assert (
                service.get_owned_operation(failed_operation).phase
                is OwnedWorkPhase.FAILED
            )
            assert panel._evaluation_render is None
            assert panel.metrics_table.rowCount() == 0
            assert panel.no_data_label.text() == (
                "The Evaluation result could not be loaded. Refresh Evaluation and try again."
            )
            assert service.get_active_owned_operation(OwnedWorkKind.EVALUATION) is None
        finally:
            selected_record.output = original_outputs
        panel.update_views()
        recovered = wait_for_selection(first, "test")
        assert recovered.operation_id != failed_operation
        _assert_result_values(
            panel, saved[0, 0, "test"].label, saved[0, 0, "test"].output
        )

        reset = service.execute(NewSessionCommand(confirmed=True))
        assert reset.ok, reset.message
        qtbot.waitUntil(
            lambda: panel.model_combo.count() == 0
            and panel.evaluation_background_work_idle(),
            timeout=5000,
        )
        assert panel._evaluation_render is None
        assert panel.metrics_table.rowCount() == 0
        assert panel.run_combo.count() == 0
        assert not panel.chk_percentage.isEnabled()
        assert panel.plot_stack.currentIndex() == 1
        assert service.get_active_owned_operation(OwnedWorkKind.EVALUATION) is None
    finally:
        host.close()
        qtbot.waitUntil(lambda: not host.isVisible(), timeout=20000)
        if panel is not None:
            assert panel.evaluation_background_work_idle()
        assert service.is_closed
