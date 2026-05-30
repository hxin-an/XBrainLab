from __future__ import annotations

import inspect

import scripts.dev.capture_data_import_wizard_steps as capture_script


def test_data_import_capture_script_only_targets_canonical_step_folder():
    source = inspect.getsource(capture_script.main)

    assert "review-import-states" not in source
    assert "bids-preset" not in source
    assert "REVIEW_STATES_DIR" not in vars(capture_script)
    assert "BIDS_PRESET_DIR" not in vars(capture_script)
