"""ApplicationService contract for direct-load one-shot RAM consent."""

from __future__ import annotations

from unittest.mock import MagicMock

from XBrainLab.backend.application import resource_guard
from XBrainLab.backend.application.commands import LoadDataCommand
from XBrainLab.backend.application.results import ErrorType
from XBrainLab.backend.application.service import ApplicationService
from XBrainLab.backend.study import Study


def test_load_data_warning_requires_and_consumes_exact_backend_receipt(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "warning.unknown"
    path.write_bytes(b"0" * 100)
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 2_000_000)
    service = ApplicationService(Study())
    service.dataset.import_files = MagicMock(return_value=(1, []))
    before = service.get_view_publication()

    challenged = service.execute(LoadDataCommand(paths=[str(path)]))
    after_challenge = service.get_view_publication()

    assert challenged.failed is True
    assert challenged.error_type is ErrorType.CONFIRMATION_REQUIRED
    assert challenged.state.last_error is None
    assert after_challenge.generation == before.generation
    assert after_challenge.usable is True
    preflight = challenged.diagnostics["resource_preflight"]
    challenge = preflight["confirmation_challenge"]
    assert challenge["command_name"] == "load_data"
    service.dataset.import_files.assert_not_called()

    accepted = service.execute(
        LoadDataCommand(
            paths=[str(path)],
            resource_preflight_confirmed=True,
            resource_preflight_token=challenge["challenge_id"],
        )
    )

    assert accepted.ok is True
    assert (
        accepted.diagnostics["resource_preflight"]["confirmation_receipt_reused"]
        is True
    )
    service.dataset.import_files.assert_called_once_with([str(path)])

    replayed = service.execute(
        LoadDataCommand(
            paths=[str(path)],
            resource_preflight_confirmed=True,
            resource_preflight_token=challenge["challenge_id"],
        )
    )

    assert replayed.failed is True
    assert replayed.error_type is ErrorType.CONFIRMATION_REQUIRED
    replay_challenge = replayed.diagnostics["resource_preflight"][
        "confirmation_challenge"
    ]
    assert replay_challenge["challenge_id"] != challenge["challenge_id"]
    service.dataset.import_files.assert_called_once_with([str(path)])
