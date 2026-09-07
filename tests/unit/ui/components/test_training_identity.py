from XBrainLab.ui.product_language import (
    fold_display_label,
    run_display_label,
)


def test_fold_label_hides_internal_zero_based_name() -> None:
    assert fold_display_label(0, "Fold_0") == "Fold 1"
    assert fold_display_label(1, "fold-1") == "Fold 2"


def test_fold_label_preserves_meaningful_descriptor() -> None:
    assert fold_display_label(0, "EEGNet") == "Fold 1 (EEGNet)"


def test_generated_subject_fold_label_is_one_based_without_storage_name_change() -> (
    None
):
    assert fold_display_label(0, "Subject-1_0") == "Fold 1 (Subject-1-1)"


def test_run_label_is_one_based_without_completion_suffix() -> None:
    assert run_display_label(0) == "Run 1"
    assert run_display_label(1) == "Run 2"
