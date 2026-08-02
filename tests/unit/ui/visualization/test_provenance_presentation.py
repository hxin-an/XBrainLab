from XBrainLab.ui.panels.visualization.panel import explanation_provenance_text


def test_visualization_provenance_is_compact_and_names_eeg_epochs() -> None:
    assert explanation_provenance_text(0) == "True class · Mean over EEG epochs"
    assert explanation_provenance_text(1) == (
        "True class · Mean magnitude over EEG epochs and channels"
    )
    assert explanation_provenance_text(2) == (
        "True class · Mean over EEG epochs and time"
    )
    assert explanation_provenance_text(
        0,
        dataset_label="A01T.gdf +2 files",
        plan_label="Fold 1 (EEGNet)",
        run_label="Run 1",
    ) == (
        "A01T.gdf +2 files · Fold 1 (EEGNet) · Run 1 · "
        "True class · Mean over EEG epochs"
    )
