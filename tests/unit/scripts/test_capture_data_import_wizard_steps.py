from __future__ import annotations

import inspect

import scripts.dev.capture_data_import_wizard_steps as capture_script


def test_data_import_capture_script_only_targets_canonical_step_folder():
    source = inspect.getsource(capture_script.main)

    assert "review-import-states" not in source
    assert "bids-preset" not in source
    assert "REVIEW_STATES_DIR" not in vars(capture_script)
    assert "BIDS_PRESET_DIR" not in vars(capture_script)


def test_review_import_capture_has_no_unresolved_primary_decision(qtbot):
    dialog = capture_script._review_import_dialog()
    qtbot.addWidget(dialog)
    dialog.show()
    dialog._go_to_step(dialog._step_titles.index("Review and Import"))

    assert dialog.apply_button.isEnabled()
    assert not dialog.review_actions_panel.isVisibleTo(dialog)
    assert dialog.review_tree.topLevelItemCount() > 0
    report_steps = {
        dialog.review_tree.topLevelItem(index).text(0)
        for index in range(dialog.review_tree.topLevelItemCount())
    }
    assert "Match Labels" not in report_steps


def test_capture_step_navigation_resets_hidden_horizontal_scroll(qtbot):
    dialog = capture_script._review_import_dialog()
    qtbot.addWidget(dialog)
    dialog.resize(capture_script.WINDOW_SIZE)
    dialog.show()
    qtbot.waitExposed(dialog)

    horizontal = dialog.scroll_area.horizontalScrollBar()
    horizontal.setValue(horizontal.maximum())
    dialog._go_to_step(dialog._step_titles.index("Review and Import"))
    qtbot.wait(1)

    assert horizontal.value() == horizontal.minimum()
    capture_script._assert_step_navigation_visible(
        dialog,
        capture_script.OUTPUT_DIR / "test-review.png",
    )
