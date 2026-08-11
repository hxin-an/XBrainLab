from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any, cast
from unittest.mock import MagicMock, patch

import mne
import numpy as np

from XBrainLab.backend.application import (
    ApplyInterpretationCommand,
    PreviewInterpretationCommand,
    QueryStateCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
    get_application_service,
    resource_guard,
)
from XBrainLab.backend.application.resource_guard import ResourceCheckResult
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.study import Study
from XBrainLab.ui.interaction_outcome import InteractionStatus
from XBrainLab.ui.main_window import MainWindow


def _switch_and_wait_for_panel(window: MainWindow, index: int, qtbot) -> Any:
    """Observe public navigation completion without assuming synchronous first-open."""
    ready_panels: list[Any] = []
    window.switch_page(index, on_ready=ready_panels.append)
    qtbot.waitUntil(lambda: len(ready_panels) == 1, timeout=5_000)
    return ready_panels[0]


def test_real_gdf_epoching_does_not_block_on_success_modal(qtbot, monkeypatch):
    monkeypatch.setenv("MNE_DONTWRITE_HOME", "true")
    study = Study()
    window = MainWindow(study)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    service = get_application_service(study)

    paths = [
        "tests/fixtures/data/A01T.gdf",
        "tests/fixtures/data/A02T.gdf",
        "tests/fixtures/data/A03T.gdf",
    ]
    commands = (
        ScanSourceCommand(source_path=paths[0], source_hint="file"),
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": paths,
                "label_carrier": "embedded_events",
                "class_map": {
                    event_name: event_name
                    for event_name in ("769", "770", "771", "772")
                },
                "internal_event_selection": {
                    "label_event_codes": ["769", "770", "771", "772"],
                    "class_map": {
                        event_name: event_name
                        for event_name in ("769", "770", "771", "772")
                    },
                },
            },
        ),
        ValidateInterpretationCommand(),
        ApplyInterpretationCommand(confirmed=True),
    )
    for command in commands:
        result = service.execute(command)
        assert result.ok, result.message
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 10**12,
                "total_bytes": 2 * 10**12,
                "used_bytes": 10**12,
            }
        ),
    )

    preprocess_panel = _switch_and_wait_for_panel(window, 1, qtbot)
    query_result = service.execute(
        QueryStateCommand(query="data_lists"),
    )
    assert query_result.ok, query_result.message
    data_rows = query_result.diagnostics.get("preprocessed_rows") or []
    available_events = {
        str(event_name)
        for row in data_rows
        for event_name in row.get("event", {}).get("labels", [])
    }
    selected_events = sorted(
        {
            event_name
            for event_name in available_events
            if event_name in {"769", "770", "771", "772"}
        }
    )
    assert selected_events == ["769", "770", "771", "772"]

    class FakeEpochingDialog:
        def __init__(self, _parent, **kwargs):
            assert isinstance(kwargs["epoch_context"], dict)

        def exec(self):
            return True

        def get_params(self):
            return ((-0.2, 0.0), selected_events, -0.2, 1.0)

        def get_confirmation_receipt(self):
            return None

    start = perf_counter()
    with (
        patch(
            "XBrainLab.ui.panels.preprocess.sidebar.EpochingDialog",
            FakeEpochingDialog,
        ),
        patch(
            "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.information",
        ) as success_dialog,
        patch(
            "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.question",
        ) as resource_dialog,
        patch(
            "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.critical",
        ) as error_dialog,
    ):
        preprocess_panel.sidebar.open_epoching()
        elapsed = perf_counter() - start

        def _epoch_exists() -> bool:
            state_result = service.execute(QueryStateCommand(query="state"))
            assert state_result.ok, state_result.message
            return bool(state_result.diagnostics["state"]["epoch"]["exists"])

        qtbot.waitUntil(_epoch_exists, timeout=10_000)
        epoch_status_bar = cast(Any, window.statusBar())
        assert epoch_status_bar is not None
        qtbot.waitUntil(
            lambda: "EEG epochs created" in epoch_status_bar.currentMessage(),
            timeout=2_000,
        )

    assert elapsed < 10.0
    state_result = service.execute(QueryStateCommand(query="state"))
    assert state_result.ok, state_result.message
    assert state_result.diagnostics["state"]["epoch"]["exists"] is True
    success_dialog.assert_not_called()
    resource_dialog.assert_not_called()
    error_dialog.assert_not_called()
    status_bar = cast(Any, window.statusBar())
    assert status_bar is not None
    assert "EEG epochs created" in status_bar.currentMessage()

    window.close()


def test_epoch_ram_block_is_shown_without_copy_or_materialization(
    qtbot,
    monkeypatch,
    tmp_path: Path,
):
    mne_raw = mne.io.RawArray(
        np.zeros((2, 1_000), dtype=np.float64),
        mne.create_info(["C3", "C4"], sfreq=100.0, ch_types="eeg"),
        verbose=False,
    )
    events = np.array(
        [[200, 0, 1], [400, 0, 2], [600, 0, 1], [800, 0, 2]],
        dtype=int,
    )
    mne_raw.set_annotations(
        mne.annotations_from_events(
            events,
            sfreq=100.0,
            event_desc={1: "left", 2: "right"},
        ),
    )
    fif_path = tmp_path / "ram-blocked-raw.fif"
    mne_raw.save(fif_path, overwrite=True, verbose=False)
    study = Study()
    service = get_application_service(study)
    commands = (
        ScanSourceCommand(source_path=str(fif_path), source_hint="file"),
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(fif_path)],
                "label_carrier": "embedded_events",
                "class_map": {"left": "left", "right": "right"},
                "internal_event_selection": {
                    "label_event_codes": ["left", "right"],
                    "class_map": {"left": "left", "right": "right"},
                },
            },
        ),
        ValidateInterpretationCommand(),
        ApplyInterpretationCommand(confirmed=True),
    )
    for command in commands:
        result = service.execute(command)
        assert result.ok, result.message
    loaded_state = service.execute(QueryStateCommand(query="state"))
    assert loaded_state.ok, loaded_state.message
    assert loaded_state.diagnostics["state"]["raw"]["count"] == 1
    window = MainWindow(study)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    preprocess_panel = _switch_and_wait_for_panel(window, 1, qtbot)

    class FakeEpochingDialog:
        def __init__(self, _parent, **kwargs):
            assert isinstance(kwargs["epoch_context"], dict)

        def exec(self):
            return True

        def get_params(self):
            return (None, ["left", "right"], -0.2, 1.0)

        def get_confirmation_receipt(self):
            return None

    blocking = ResourceCheckResult(
        required_memory_bytes=10_000,
        available_memory_bytes=1_000,
        total_memory_bytes=2_000,
        used_memory_bytes=1_000,
        risk_level=resource_guard.RISK_BLOCKING,
        message="EEG epoch data is too large for available RAM.",
    )
    copy_spy = MagicMock(side_effect=AssertionError("Raw.copy must not run"))
    monkeypatch.setattr(Raw, "copy", copy_spy)

    with (
        patch(
            "XBrainLab.ui.panels.preprocess.sidebar.EpochingDialog",
            FakeEpochingDialog,
        ),
        patch.object(
            resource_guard.ResourceChecker,
            "check_epoch_materialization_safe",
            return_value=blocking,
        ),
        patch(
            "XBrainLab.backend.preprocessor.time_epoch.mne.Epochs",
        ) as epoch_constructor,
        patch(
            "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.critical",
        ) as critical,
    ):
        outcome = preprocess_panel.sidebar.open_epoching()
        assert outcome.status is InteractionStatus.ACCEPTED
        qtbot.waitUntil(lambda: critical.call_count == 1, timeout=5_000)

    assert "too large for available RAM" in critical.call_args.args[2]
    copy_spy.assert_not_called()
    epoch_constructor.assert_not_called()
    state_result = service.execute(QueryStateCommand(query="state"))
    assert state_result.ok, state_result.message
    state = state_result.diagnostics["state"]
    assert state["raw"]["count"] == 1
    assert state["preprocessed"]["count"] == 1
    assert state["epoch"]["exists"] is False
    assert state["active_dataset"]["is_locked"] is False

    window.close()
