from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    GenerateDatasetCommand,
    PreprocessCommand,
    PreprocessOperation,
    PreviewInterpretationCommand,
    SaliencyCommand,
    ScanSourceCommand,
    TrainCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.ui.main_window import MainWindow

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "data"
GDF_PATH = FIXTURE_ROOT / "A01T.gdf"
LABEL_PATH = FIXTURE_ROOT / "label" / "A01T.mat"


def _render_evidence(widget: Any) -> dict[str, Any]:
    fig = getattr(widget, "fig", None)
    axes = list(getattr(fig, "axes", []) or [])
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
                "class_map": {
                    "1": "left hand",
                    "2": "right hand",
                    "3": "feet",
                    "4": "tongue",
                },
            }
        },
        "class_map": {
            "1": "left hand",
            "2": "right hand",
            "3": "feet",
            "4": "tongue",
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
        GenerateDatasetCommand(
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
        SaliencyCommand(
            method="Gradient",
            params={"nt_samples": 1, "nt_samples_batch_size": 1, "stdevs": 1.0},
        ),
    ]
    for command in commands:
        result = service.execute(command)
        assert result.ok is True, result.message

    holder = service.study.trainer.get_training_plan_holders()[0]
    eval_record = holder.get_plans()[0].get_eval_record()
    assert sorted(eval_record.gradient) == [0, 1, 2, 3]
    assert all(len(value) > 0 for value in eval_record.gradient.values())

    window = MainWindow(service.study)
    qtbot.addWidget(window)
    window.resize(1220, 900)
    window.show()
    window.switch_page(4)
    qtbot.wait(50)

    panel = window.visualization_panel
    assert panel.plan_combo.currentText().startswith("Fold 1")
    assert panel.run_combo.currentText() == "Run 1"

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

    window.close()


@pytest.mark.skipif(
    not GDF_PATH.exists() or not LABEL_PATH.exists(),
    reason="Graz label-mapping fixtures are not available.",
)
def test_post_training_saliency_configuration_recomputes_metric_only_run(
    tmp_path,
) -> None:
    """Training stays fast by default, then saliency can be computed on demand."""

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
                "class_map": {
                    "1": "left hand",
                    "2": "right hand",
                    "3": "feet",
                    "4": "tongue",
                },
            }
        },
        "class_map": {
            "1": "left hand",
            "2": "right hand",
            "3": "feet",
            "4": "tongue",
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
        GenerateDatasetCommand(
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
    assert service.get_state().visualization.saliency_available is False

    saliency = service.execute(
        SaliencyCommand(
            method="Gradient",
            params={"nt_samples": 1, "nt_samples_batch_size": 1, "stdevs": 1.0},
        ),
    )

    assert saliency.ok is True, saliency.message
    assert saliency.diagnostics["saliency_available"] is True
    assert service.get_state().visualization.saliency_available is True
    eval_record = holder.get_plans()[0].get_eval_record()
    assert sorted(eval_record.gradient) == [0, 1, 2, 3]
    assert all(len(value) > 0 for value in eval_record.gradient.values())
