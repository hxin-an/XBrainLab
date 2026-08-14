from __future__ import annotations

import time
from pathlib import Path
from typing import Any, cast

import pytest

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    PreprocessCommand,
    PreprocessOperation,
    PreviewInterpretationCommand,
    SaliencyCommand,
    SaveDatasetSplitCommand,
    ScanSourceCommand,
    TrainCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.backend.training.record.eval import EvalRecord
from XBrainLab.backend.training_state_contract import PostTrainingSaliencyPhase
from XBrainLab.ui.main_window import MainWindow

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "data"
GDF_PATH = FIXTURE_ROOT / "A01T.gdf"
LABEL_PATH = FIXTURE_ROOT / "label" / "A01T.mat"


def _class_value_decisions() -> dict[str, dict[str, object]]:
    return {
        "1": {
            "role": "stimulus",
            "keep_event": True,
            "use_as_class": True,
            "class_name": "left hand",
        },
        "2": {
            "role": "stimulus",
            "keep_event": True,
            "use_as_class": True,
            "class_name": "right hand",
        },
        "3": {
            "role": "stimulus",
            "keep_event": True,
            "use_as_class": True,
            "class_name": "feet",
        },
        "4": {
            "role": "stimulus",
            "keep_event": True,
            "use_as_class": True,
            "class_name": "tongue",
        },
    }


def _render_evidence(widget: Any) -> dict[str, Any]:
    fig = getattr(widget, "fig", None)
    axes = list(getattr(fig, "axes", []) or [])
    plot_axes = [axis for axis in axes if axis.get_title()]
    auxiliary_axes = [axis for axis in axes if axis not in plot_axes]
    image_count = sum(
        len(getattr(axis, "images", []) or [])
        + len(getattr(axis, "collections", []) or [])
        for axis in axes
    )
    error_label = getattr(widget, "error_label", None)
    canvas = getattr(widget, "canvas", None)
    return {
        "error_visible": bool(error_label and error_label.isVisible()),
        "error_text": str(error_label.text()) if error_label else "",
        "axes_count": len(axes),
        "image_count": image_count,
        "canvas_visible": bool(canvas and canvas.isVisible()),
        "titles": [axis.get_title() for axis in plot_axes],
        "x_labels": [axis.get_xlabel() for axis in plot_axes if axis.get_xlabel()],
        "y_labels": [axis.get_ylabel() for axis in plot_axes if axis.get_ylabel()],
        "auxiliary_y_labels": [
            axis.get_ylabel() for axis in auxiliary_axes if axis.get_ylabel()
        ],
        "color_limits": [
            tuple(image.get_clim())
            for axis in plot_axes
            for image in list(getattr(axis, "images", []) or [])
        ],
    }


@pytest.mark.skipif(
    not GDF_PATH.exists() or not LABEL_PATH.exists(),
    reason="Graz label-mapping fixtures are not available.",
)
def test_data_import_label_mapping_renders_saliency_maps(qtbot, tmp_path) -> None:
    """Wizard-applied external labels must survive through saliency rendering."""

    service = ApplicationService()
    scan_result = service.execute(
        ScanSourceCommand(
            source_path=str(GDF_PATH),
            label_sources=[str(LABEL_PATH)],
        ),
    )
    assert scan_result.ok is True

    choices = {
        "selected_eeg_files": [str(GDF_PATH)],
        "label_carrier_choices": {
            str(LABEL_PATH): {
                "label_field": "classlabel",
                "placement_method": "eeg_event",
                "target_event_codes": ["768"],
                "value_decisions": _class_value_decisions(),
            }
        },
    }
    commands = [
        PreviewInterpretationCommand(choices=choices),
        ValidateInterpretationCommand(),
        ApplyInterpretationCommand(confirmed=True),
        PreprocessCommand(operation=PreprocessOperation.NORMALIZE, method="z-score"),
        CreateEpochCommand(
            t_min=0.0,
            t_max=1.2,
            baseline=None,
            event_ids=["left hand", "right hand", "feet", "tongue"],
        ),
        SaveDatasetSplitCommand(
            test_ratio=0.2,
            val_ratio=0.2,
            split_strategy="trial",
            training_mode="individual",
        ),
        ConfigureTrainingCommand(model_name="EEGNet"),
        ConfigureTrainingCommand(
            epoch=1,
            batch_size=64,
            learning_rate=0.001,
            device="cpu",
            output_dir=str(tmp_path / "training-output"),
        ),
        TrainCommand(confirmed=True, interactive=False),
    ]
    for command in commands:
        result = service.execute(command)
        assert result.ok is True, result.message

    holder = service.study.trainer.get_training_plan_holders()[0]
    eval_record = holder.get_plans()[0].get_eval_record()
    assert eval_record.gradient == {}

    saliency_result = service.execute(SaliencyCommand(method="Gradient"))
    assert saliency_result.ok is True, saliency_result.message
    assert saliency_result.diagnostics["action"] == "schedule"
    assert service.wait_for_background_tasks(timeout=30.0)

    eval_record = holder.get_plans()[0].get_eval_record()
    assert sorted(eval_record.gradient) == [0, 1, 2, 3]
    assert all(len(value) > 0 for value in eval_record.gradient.values())

    window = MainWindow(service.study)
    qtbot.addWidget(window)
    window.resize(1220, 900)
    window.show()
    ready_panels = []
    window.switch_page(4, on_ready=ready_panels.append)
    qtbot.waitUntil(lambda: len(ready_panels) == 1, timeout=5_000)

    panel = cast(Any, ready_panels[0])
    assert panel.plan_combo.currentText().startswith("Fold 1")
    assert panel.run_combo.currentText() == "Run 1"

    expected_class_names = {"left hand", "right hand", "feet", "tongue"}
    for tab_name in ("Saliency Map", "Spectrogram"):
        tab_index = next(
            index
            for index in range(panel.tabs.count())
            if panel.tabs.tabText(index) == tab_name
        )
        panel.tabs.setCurrentIndex(tab_index)
        panel.method_combo.setCurrentText("Gradient")
        panel.on_update()
        for _ in range(30):
            qtbot.wait(20)
            time.sleep(0.005)

        evidence = _render_evidence(panel.tabs.currentWidget())
        assert evidence["error_visible"] is False, evidence["error_text"]
        assert evidence["canvas_visible"] is True
        assert evidence["image_count"] > 0
        assert set(evidence["titles"]) == expected_class_names
        assert len(evidence["color_limits"]) == 4
        assert len(set(evidence["color_limits"])) == 1
        if tab_name == "Saliency Map":
            assert set(evidence["x_labels"]) == {"Time (s)"}
            assert set(evidence["y_labels"]) == {"Channel"}
        else:
            assert set(evidence["x_labels"]) == {"Time (s)"}
            assert set(evidence["y_labels"]) == {"Frequency (Hz)"}
            assert len(evidence["auxiliary_y_labels"]) == 1
            assert evidence["auxiliary_y_labels"][0].startswith("Attribution magnitude")

    context = eval_record.saliency_context
    assert context is not None
    assert {name for _key, name in context.class_map} == expected_class_names
    assert context.channel_names == tuple(service.study.epoch_data.get_channel_names())
    identity_artifact = tmp_path / "saliency-identity-round-trip"
    identity_artifact.mkdir()
    eval_record.export(str(identity_artifact))
    reloaded = EvalRecord.load(str(identity_artifact))
    assert reloaded is not None
    assert reloaded.saliency_context == context

    window.close()


@pytest.mark.skipif(
    not GDF_PATH.exists() or not LABEL_PATH.exists(),
    reason="Graz label-mapping fixtures are not available.",
)
def test_training_is_metric_only_until_explicit_saliency_command(
    tmp_path,
) -> None:
    """Training publishes metrics without computing saliency on its own."""

    service = ApplicationService()
    scan_result = service.execute(
        ScanSourceCommand(
            source_path=str(GDF_PATH),
            label_sources=[str(LABEL_PATH)],
        ),
    )
    assert scan_result.ok is True

    choices = {
        "selected_eeg_files": [str(GDF_PATH)],
        "label_carrier_choices": {
            str(LABEL_PATH): {
                "label_field": "classlabel",
                "placement_method": "eeg_event",
                "target_event_codes": ["768"],
                "value_decisions": _class_value_decisions(),
            }
        },
    }
    commands = [
        PreviewInterpretationCommand(choices=choices),
        ValidateInterpretationCommand(),
        ApplyInterpretationCommand(confirmed=True),
        PreprocessCommand(operation=PreprocessOperation.NORMALIZE, method="z-score"),
        CreateEpochCommand(
            t_min=0.0,
            t_max=1.2,
            baseline=None,
            event_ids=["left hand", "right hand", "feet", "tongue"],
        ),
        SaveDatasetSplitCommand(
            test_ratio=0.2,
            val_ratio=0.2,
            split_strategy="trial",
            training_mode="individual",
        ),
        ConfigureTrainingCommand(model_name="EEGNet"),
        ConfigureTrainingCommand(
            epoch=1,
            batch_size=64,
            learning_rate=0.001,
            device="cpu",
            output_dir=str(tmp_path / "training-output"),
        ),
        TrainCommand(confirmed=True, interactive=False),
    ]
    for command in commands:
        result = service.execute(command)
        assert result.ok is True, result.message

    holder = service.study.trainer.get_training_plan_holders()[0]
    eval_record = holder.get_plans()[0].get_eval_record()
    assert eval_record is not None
    assert eval_record.gradient == {}
    assert eval_record.gradient_input == {}
    assert eval_record.smoothgrad == {}
    publication = service.get_view_publication()
    assert publication.state.visualization.post_training_saliency.phase is (
        PostTrainingSaliencyPhase.IDLE
    )
    assert publication.state.visualization.saliency_available is False
    assert all(
        not method.complete
        for run in publication.state.visualization.saliency_coverage
        for method in run.methods
    )

    saliency = service.execute(
        SaliencyCommand(
            method="SmoothGrad",
            params={"nt_samples": 1, "nt_samples_batch_size": 1, "stdevs": 1.0},
        ),
    )

    assert saliency.ok is True, saliency.message
    assert saliency.diagnostics["action"] == "schedule"
    assert service.wait_for_background_tasks(timeout=30.0)
    assert service.get_state().visualization.saliency_available is True
    eval_record = holder.get_plans()[0].get_eval_record()
    assert eval_record.gradient == {}
    assert eval_record.gradient_input == {}
    assert sorted(eval_record.smoothgrad) == [0, 1, 2, 3]
    assert all(len(value) > 0 for value in eval_record.smoothgrad.values())
