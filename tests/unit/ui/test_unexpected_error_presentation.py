"""Public UI behavior for unexpected training and Data Import failures."""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from XBrainLab.backend.application import ErrorType, ReloadInterpretationRecipeCommand
from XBrainLab.backend.application.view_publication import (
    InterpretationReviewIdentity,
)
from XBrainLab.ui.interaction_outcome import InteractionStatus
from XBrainLab.ui.panels.dataset import actions
from XBrainLab.ui.panels.dataset.actions import DatasetActionHandler
from XBrainLab.ui.panels.training import sidebar as training_sidebar
from XBrainLab.ui.panels.training.sidebar import TrainingSidebar

_SENTINEL = "SENTINEL_SECRET at /private/eeg/subject-01.edf"
_TRAINING_MESSAGE = (
    "XBrainLab could not start training because of an unexpected problem. "
    "Review the training settings and try again."
)
_IMPORT_MESSAGE = (
    "XBrainLab could not continue the data import because of an unexpected problem. "
    "Reopen the source and try again."
)
_REVIEW_MESSAGE = (
    "The current Data Import review could not be opened safely. "
    "Start a new import review and try again."
)
_RECIPE_MESSAGE = (
    "XBrainLab could not reload the import recipe. "
    "Check that the recipe is still available, then try again."
)
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _training_widget(qtbot) -> TrainingSidebar:
    panel = MagicMock()
    panel.controller = MagicMock()
    panel.main_window = None
    widget = TrainingSidebar(panel, parent=None)
    qtbot.addWidget(widget)
    return widget


def _assert_logged_exception(caplog, *, sentinel: str = _SENTINEL) -> None:
    records = [
        record
        for record in caplog.records
        if record.name == "XBrainLab"
        and sentinel
        in " ".join(
            (
                record.getMessage(),
                str(record.exc_info[1]) if record.exc_info is not None else "",
            )
        )
    ]
    assert records
    assert any(record.exc_info is not None for record in records)


def test_training_start_unexpected_exception_is_private_and_actionable(
    qtbot,
    monkeypatch,
    caplog,
) -> None:
    sidebar = _training_widget(qtbot)
    critical = MagicMock()
    monkeypatch.setattr(training_sidebar.QMessageBox, "critical", critical)
    monkeypatch.setattr(
        training_sidebar,
        "get_command_capability",
        MagicMock(side_effect=RuntimeError(_SENTINEL)),
    )

    with caplog.at_level(logging.ERROR, logger="XBrainLab"):
        outcome = sidebar.start_training_ui_action()

    assert outcome is None
    critical.assert_called_once()
    assert critical.call_args.args[1:] == (
        "Training could not start",
        _TRAINING_MESSAGE,
    )
    assert _SENTINEL not in critical.call_args.args[2]
    _assert_logged_exception(caplog)


def test_training_start_async_exception_is_private_and_logged(
    qtbot,
    monkeypatch,
    caplog,
) -> None:
    sidebar = _training_widget(qtbot)
    critical = MagicMock()
    monkeypatch.setattr(training_sidebar.QMessageBox, "critical", critical)
    monkeypatch.setattr(
        training_sidebar,
        "get_command_capability",
        lambda *_args: SimpleNamespace(enabled=True, reasons=[]),
    )

    def dispatch(_context, _command, *, on_error, **_kwargs) -> bool:
        on_error(
            (
                RuntimeError,
                RuntimeError(_SENTINEL),
                f"Traceback (worker):\nRuntimeError: {_SENTINEL}",
            )
        )
        return True

    monkeypatch.setattr(
        training_sidebar,
        "execute_application_command_async",
        dispatch,
    )

    with caplog.at_level(logging.ERROR, logger="XBrainLab"):
        outcome = sidebar.start_training_ui_action()

    assert outcome is None
    critical.assert_called_once()
    assert critical.call_args.args[1:] == (
        "Training could not start",
        _TRAINING_MESSAGE,
    )
    assert _SENTINEL not in critical.call_args.args[2]
    _assert_logged_exception(caplog)


def test_data_import_unexpected_exception_keeps_failed_outcome_without_leaking(
    monkeypatch,
    caplog,
) -> None:
    panel = MagicMock()
    panel.controller.is_locked.return_value = False
    handler = DatasetActionHandler(panel)
    critical = MagicMock()
    monkeypatch.setattr(actions.QMessageBox, "critical", critical)
    monkeypatch.setattr(
        actions.QFileDialog,
        "getOpenFileNames",
        lambda *_args: (["/selected/source.edf"], ""),
    )
    monkeypatch.setattr(
        handler,
        "_run_data_interpretation_import",
        MagicMock(side_effect=RuntimeError(_SENTINEL)),
    )

    with caplog.at_level(logging.ERROR, logger="XBrainLab"):
        outcome = handler.import_data()

    assert outcome.status is InteractionStatus.FAILED
    assert outcome.message == _IMPORT_MESSAGE
    critical.assert_called_once()
    assert critical.call_args.args[1:] == (
        "Data import could not continue",
        _IMPORT_MESSAGE,
    )
    assert _SENTINEL not in critical.call_args.args[2]
    _assert_logged_exception(caplog)


def test_data_import_review_payload_failure_is_private_and_stays_failed(
    monkeypatch,
    caplog,
) -> None:
    class BrokenReview(dict):
        def __getitem__(self, _key):
            raise ValueError(_SENTINEL)

    handler = DatasetActionHandler(MagicMock())
    critical = MagicMock()
    monkeypatch.setattr(actions.QMessageBox, "critical", critical)
    monkeypatch.setattr(
        handler,
        "_read_interpretation_review",
        lambda _identity: actions._PublishedInterpretationReview(
            payload=BrokenReview(),
            identity=InterpretationReviewIdentity(
                publication_generation=1,
                scan_id="scan-1",
                candidate_id="candidate-1",
            ),
        ),
    )

    with caplog.at_level(logging.ERROR, logger="XBrainLab"):
        outcome = handler.review_current_import()

    assert outcome.status is InteractionStatus.FAILED
    assert outcome.message == _REVIEW_MESSAGE
    critical.assert_called_once()
    assert critical.call_args.args[1:] == (
        "Import review unavailable",
        _REVIEW_MESSAGE,
    )
    assert _SENTINEL not in critical.call_args.args[2]
    _assert_logged_exception(caplog)


def test_recipe_reload_worker_failure_is_private_and_logged(
    monkeypatch,
    caplog,
) -> None:
    panel = MagicMock()
    handler = DatasetActionHandler(panel)
    critical = MagicMock()
    monkeypatch.setattr(actions.QMessageBox, "critical", critical)
    monkeypatch.setattr(
        actions,
        "get_command_capability",
        lambda *_args: SimpleNamespace(enabled=True, reasons=[]),
    )
    monkeypatch.setattr(
        actions.QFileDialog,
        "getOpenFileName",
        lambda *_args: ("/selected/import-recipe.json", ""),
    )

    def dispatch(_panel, command, *, on_error, **_kwargs) -> bool:
        assert isinstance(command, ReloadInterpretationRecipeCommand)
        on_error(
            (
                RuntimeError,
                RuntimeError(_SENTINEL),
                f"Traceback (worker):\nRuntimeError: {_SENTINEL}",
            )
        )
        return True

    monkeypatch.setattr(actions, "execute_application_command_async", dispatch)

    with caplog.at_level(logging.ERROR, logger="XBrainLab"):
        outcome = handler.reload_interpretation_recipe()

    assert outcome is None
    critical.assert_called_once()
    assert critical.call_args.args[1:] == (
        "Recipe reload failed",
        _RECIPE_MESSAGE,
    )
    assert _SENTINEL not in critical.call_args.args[2]
    _assert_logged_exception(caplog)


def test_structured_training_failure_keeps_backend_recovery_message(
    qtbot,
    monkeypatch,
) -> None:
    sidebar = _training_widget(qtbot)
    critical = MagicMock()
    monkeypatch.setattr(training_sidebar.QMessageBox, "critical", critical)
    recovery_message = "Reduce the batch size to 16, then start training again."
    result = SimpleNamespace(
        failed=True,
        diagnostics={},
        error_type=ErrorType.TRAINING,
        message=recovery_message,
    )

    sidebar._handle_start_training_result(result, unknown_retried=False)

    critical.assert_called_once()
    assert recovery_message in critical.call_args.args[2]


@pytest.mark.parametrize(
    "relative_path",
    (
        "XBrainLab/ui/panels/training/sidebar.py",
        "XBrainLab/ui/panels/dataset/actions.py",
    ),
)
def test_catch_all_exception_alias_never_reaches_message_box(
    relative_path: str,
) -> None:
    tree = ast.parse((_REPO_ROOT / relative_path).read_text(encoding="utf-8"))
    leaks: list[int] = []

    for handler in (
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler)
        and isinstance(node.type, ast.Name)
        and node.type.id == "Exception"
        and handler_alias(node) is not None
    ):
        alias = handler_alias(handler)
        for call in (node for node in ast.walk(handler) if isinstance(node, ast.Call)):
            if not _is_message_box_call(call):
                continue
            if any(
                isinstance(node, ast.Name) and node.id == alias
                for node in ast.walk(call)
            ):
                leaks.append(call.lineno)

    assert leaks == []


def handler_alias(handler: ast.ExceptHandler) -> str | None:
    return handler.name if isinstance(handler.name, str) else None


def _is_message_box_call(call: ast.Call) -> bool:
    function = call.func
    return (
        isinstance(function, ast.Attribute)
        and function.attr in {"critical", "warning", "information"}
        and isinstance(function.value, ast.Name)
        and function.value.id == "QMessageBox"
    )
