"""Public UI behavior for unexpected product failures."""

from __future__ import annotations

import ast
import logging
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QMainWindow

from XBrainLab.backend.application import ErrorType, ReloadInterpretationRecipeCommand
from XBrainLab.backend.application.view_publication import (
    InterpretationReviewIdentity,
)
from XBrainLab.ui.components import user_error_presentation
from XBrainLab.ui.components.user_error_presentation import (
    UnexpectedErrorContext,
    present_unexpected_error,
)
from XBrainLab.ui.interaction_outcome import InteractionStatus
from XBrainLab.ui.panels.dataset import actions
from XBrainLab.ui.panels.dataset.actions import DatasetActionHandler
from XBrainLab.ui.panels.dataset.data_interpretation_action_coordinator import (
    _PublishedInterpretationReview,
)
from XBrainLab.ui.panels.preprocess import sidebar as preprocess_sidebar
from XBrainLab.ui.panels.preprocess.sidebar import PreprocessSidebar
from XBrainLab.ui.panels.training import sidebar as training_sidebar
from XBrainLab.ui.panels.training.sidebar import TrainingSidebar

_SENTINEL_TOKEN = "SEC07_PRIVATE_TOKEN"  # noqa: S105 - redaction test sentinel
_PRIVATE_SENTINEL_PATH = "/private/eeg/subject-01.edf"
_SENTINEL = f"token={_SENTINEL_TOKEN}; source={_PRIVATE_SENTINEL_PATH}"
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
_PREPROCESS_MESSAGE = (
    "XBrainLab could not apply preprocessing because of an unexpected problem. "
    "Review the preprocessing settings and try again."
)


def _record_shared_alert(target: MagicMock):
    """Preserve concise legacy assertions while checking shared alert metadata."""

    def present(parent, *, severity, title, message):
        target(parent, title, message)
        target.severity = severity

    return present


_RESET_PREPROCESS_MESSAGE = (
    "XBrainLab could not reset preprocessing because of an unexpected problem. "
    "Review the current workflow state and try again."
)
_TRAINING_SETTINGS_MESSAGE = (
    "XBrainLab could not apply the training settings because of an unexpected "
    "problem. Review the training configuration and try again."
)
_SALIENCY_SETTINGS_MESSAGE = (
    "XBrainLab could not apply the saliency settings because of an unexpected "
    "problem. Review the selected methods and parameters, then try again."
)
_MONTAGE_SETUP_MESSAGE = (
    "XBrainLab could not apply the montage setup because of an unexpected problem. "
    "Reopen the channel mapping and try again."
)
_DATASET_APPLY_MESSAGE = (
    "XBrainLab could not apply the loaded EEG data because of an unexpected problem. "
    "Reopen the data source and try again."
)
_REPO_ROOT = Path(__file__).resolve().parents[3]
_UI_ROOT = _REPO_ROOT / "XBrainLab" / "ui"


def _training_widget(qtbot) -> TrainingSidebar:
    panel = MagicMock()
    panel.controller = MagicMock()
    panel.main_window = None
    widget = TrainingSidebar(panel, parent=None)
    qtbot.addWidget(widget)
    return widget


def _preprocess_widget(qtbot) -> PreprocessSidebar:
    panel = MagicMock()
    panel.controller = MagicMock()
    panel.dataset_controller = MagicMock()
    panel.main_window = QMainWindow()
    qtbot.addWidget(panel.main_window)
    widget = PreprocessSidebar(panel)
    qtbot.addWidget(widget)
    return widget


def _assert_logged_exception(caplog, *, sentinel: str = _SENTINEL) -> None:
    records = [
        record
        for record in caplog.records
        if record.name == "XBrainLab" and record.levelno >= logging.ERROR
    ]
    assert records
    serialized = "\n".join(record.getMessage() for record in records)
    assert sentinel not in serialized
    assert _SENTINEL_TOKEN not in serialized
    assert _PRIVATE_SENTINEL_PATH not in serialized
    assert "subject-01" not in serialized
    assert all(record.exc_info is None for record in records)


@contextmanager
def _capture_public_xbrainlab_logs(caplog):
    product_logger = logging.getLogger("XBrainLab")
    product_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR, logger="XBrainLab"):
            yield
    finally:
        product_logger.removeHandler(caplog.handler)


def test_training_start_unexpected_exception_is_private_and_actionable(
    qtbot,
    monkeypatch,
    caplog,
) -> None:
    sidebar = _training_widget(qtbot)
    critical = MagicMock()
    monkeypatch.setattr(
        user_error_presentation, "show_alert", _record_shared_alert(critical)
    )
    monkeypatch.setattr(
        training_sidebar,
        "get_command_capability",
        MagicMock(side_effect=RuntimeError(_SENTINEL)),
    )

    with _capture_public_xbrainlab_logs(caplog):
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
    monkeypatch.setattr(
        user_error_presentation, "show_alert", _record_shared_alert(critical)
    )
    monkeypatch.setattr(
        training_sidebar,
        "get_command_capability",
        lambda *_args, **_kwargs: SimpleNamespace(enabled=True, reasons=[]),
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

    with _capture_public_xbrainlab_logs(caplog):
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
    from XBrainLab.ui.dialogs.dataset.eeg_source_chooser_dialog import (
        EegSourceSelection,
    )

    class _AcceptedChooser:
        def __init__(self, _parent, *, start_directory=""):
            assert isinstance(start_directory, str)

        def exec(self):
            return True

        def get_result(self):
            return EegSourceSelection(
                kind="files",
                paths=("/selected/source.edf",),
            )

    panel = MagicMock()
    panel.controller.is_locked.return_value = False
    handler = DatasetActionHandler(panel)
    handler._data_interpretation._source_chooser_dialog_class = lambda: (
        _AcceptedChooser
    )
    critical = MagicMock()
    monkeypatch.setattr(
        user_error_presentation, "show_alert", _record_shared_alert(critical)
    )
    monkeypatch.setattr(
        handler._data_interpretation,
        "_run_data_interpretation_import",
        MagicMock(side_effect=RuntimeError(_SENTINEL)),
    )

    with _capture_public_xbrainlab_logs(caplog):
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
    monkeypatch.setattr(
        user_error_presentation, "show_alert", _record_shared_alert(critical)
    )
    monkeypatch.setattr(
        handler._data_interpretation,
        "_read_interpretation_review",
        lambda _identity: _PublishedInterpretationReview(
            payload=BrokenReview(),
            identity=InterpretationReviewIdentity(
                publication_generation=1,
                scan_id="scan-1",
                candidate_id="candidate-1",
            ),
        ),
    )

    with _capture_public_xbrainlab_logs(caplog):
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
    monkeypatch.setattr(
        user_error_presentation, "show_alert", _record_shared_alert(critical)
    )
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

    with _capture_public_xbrainlab_logs(caplog):
        outcome = handler.reload_interpretation_recipe()

    assert outcome is None
    critical.assert_called_once()
    assert critical.call_args.args[1:] == (
        "Recipe reload failed",
        _RECIPE_MESSAGE,
    )
    assert _SENTINEL not in critical.call_args.args[2]
    _assert_logged_exception(caplog)


def test_preprocess_async_exception_is_private_and_logged(
    qtbot,
    monkeypatch,
    caplog,
) -> None:
    sidebar = _preprocess_widget(qtbot)
    critical = MagicMock()
    monkeypatch.setattr(
        user_error_presentation, "show_alert", _record_shared_alert(critical)
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
        preprocess_sidebar,
        "execute_application_command_async",
        dispatch,
    )

    with _capture_public_xbrainlab_logs(caplog):
        outcome = sidebar._execute_preprocess_command(
            MagicMock(),
            blocked_title="Filtering Blocked",
            failure_prefix="Filtering failed",
            on_success=MagicMock(),
        )

    assert outcome.status is InteractionStatus.ACCEPTED
    critical.assert_called_once_with(
        sidebar,
        "Preprocessing could not be applied",
        _PREPROCESS_MESSAGE,
    )
    assert _SENTINEL not in critical.call_args.args[2]
    _assert_logged_exception(caplog)


def test_preprocess_sync_exception_is_private_and_returns_stable_outcome(
    qtbot,
    monkeypatch,
    caplog,
) -> None:
    sidebar = _preprocess_widget(qtbot)
    critical = MagicMock()
    monkeypatch.setattr(
        user_error_presentation, "show_alert", _record_shared_alert(critical)
    )
    monkeypatch.setattr(
        preprocess_sidebar,
        "execute_application_command_async",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        preprocess_sidebar,
        "has_real_application_context",
        lambda _context: False,
    )
    monkeypatch.setattr(
        preprocess_sidebar,
        "execute_application_command",
        MagicMock(side_effect=RuntimeError(_SENTINEL)),
    )

    with _capture_public_xbrainlab_logs(caplog):
        outcome = sidebar._execute_preprocess_command(
            MagicMock(),
            blocked_title="Filtering Blocked",
            failure_prefix="Filtering failed",
            on_success=MagicMock(),
        )

    assert outcome.status is InteractionStatus.FAILED
    assert outcome.message == _PREPROCESS_MESSAGE
    critical.assert_called_once_with(
        sidebar,
        "Preprocessing could not be applied",
        _PREPROCESS_MESSAGE,
    )
    assert _SENTINEL not in outcome.message
    _assert_logged_exception(caplog)


def test_reset_preprocess_sync_exception_is_private(
    qtbot,
    monkeypatch,
    caplog,
) -> None:
    sidebar = _preprocess_widget(qtbot)
    critical = MagicMock()
    monkeypatch.setattr(
        user_error_presentation, "show_alert", _record_shared_alert(critical)
    )
    monkeypatch.setattr(
        preprocess_sidebar,
        "get_application_view_publication",
        lambda _context: None,
    )
    monkeypatch.setattr(
        preprocess_sidebar,
        "has_real_application_context",
        lambda _context: False,
    )
    monkeypatch.setattr(
        preprocess_sidebar,
        "get_command_capability",
        lambda *_args: SimpleNamespace(
            enabled=True,
            confirmation_required=True,
            requires_confirmation=True,
        ),
    )
    monkeypatch.setattr(
        preprocess_sidebar,
        "ask_confirmation",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        preprocess_sidebar,
        "execute_application_command",
        MagicMock(side_effect=RuntimeError(_SENTINEL)),
    )

    with _capture_public_xbrainlab_logs(caplog):
        sidebar.reset_preprocess()

    critical.assert_called_once_with(
        sidebar,
        "Preprocessing could not be reset",
        _RESET_PREPROCESS_MESSAGE,
    )
    assert _SENTINEL not in critical.call_args.args[2]
    _assert_logged_exception(caplog)


class _HostileTuple(tuple):
    def __bool__(self):
        raise RuntimeError("tuple truthiness must not run")

    def __getitem__(self, _index):
        raise RuntimeError("tuple indexing must not run")

    def __iter__(self):
        raise RuntimeError("tuple iteration must not run")

    def __len__(self):
        raise RuntimeError("tuple length must not run")


class _HostileText:
    def __str__(self) -> str:
        raise RuntimeError("text rendering must not run")


class _HostileString(str):
    def __str__(self) -> str:
        raise RuntimeError("string subclass rendering must not run")


class _HostileException(RuntimeError):
    def __str__(self) -> str:
        raise RuntimeError("exception rendering must not run")


class _HostileNameMeta(type):
    def __getattribute__(self, name: str):
        if name == "__name__":
            raise RuntimeError("type name rendering must not run")
        return super().__getattribute__(name)


class _HostileErrorType(metaclass=_HostileNameMeta):
    pass


@pytest.mark.parametrize(
    "error_info",
    (
        pytest.param(
            _HostileTuple(
                (
                    RuntimeError,
                    RuntimeError(_SENTINEL),
                    f"Traceback: {_SENTINEL}",
                )
            ),
            id="tuple-subclass",
        ),
        pytest.param(
            (_HostileErrorType, _HostileText(), _HostileText()),
            id="non-exception-and-hostile-name",
        ),
        pytest.param(
            (
                RuntimeError,
                _HostileException(_SENTINEL),
                _HostileString(f"Traceback: {_SENTINEL}"),
            ),
            id="hostile-exception-and-string-subclass",
        ),
    ),
)
def test_worker_error_presentation_fails_closed_for_hostile_payloads(
    error_info,
    caplog,
) -> None:
    with (
        _capture_public_xbrainlab_logs(caplog),
        patch("XBrainLab.ui.components.user_error_presentation.show_alert") as alert,
    ):
        message = present_unexpected_error(
            None,
            UnexpectedErrorContext.PREPROCESS_EXECUTION,
            error_info=error_info,
        )

    assert message == _PREPROCESS_MESSAGE
    assert alert.call_args.kwargs["message"] == _PREPROCESS_MESSAGE
    _assert_logged_exception(caplog)


def test_worker_logging_failure_does_not_hide_stable_message(monkeypatch) -> None:
    monkeypatch.setattr(
        user_error_presentation.logger,
        "error",
        MagicMock(side_effect=RuntimeError("logger failed")),
    )

    with patch("XBrainLab.ui.components.user_error_presentation.show_alert") as alert:
        message = present_unexpected_error(
            None,
            UnexpectedErrorContext.PREPROCESS_EXECUTION,
            error_info=(RuntimeError, RuntimeError(_SENTINEL), _SENTINEL),
        )

    assert message == _PREPROCESS_MESSAGE
    assert alert.call_args.kwargs["message"] == _PREPROCESS_MESSAGE


def test_training_settings_unexpected_exception_uses_stable_warning(
    qtbot,
    monkeypatch,
    caplog,
) -> None:
    from XBrainLab.ui.dialogs.training import (
        device_setting_dialog,
        training_setting_dialog,
    )

    monkeypatch.setattr(
        training_setting_dialog,
        "get_optimizer_classes",
        dict,
    )
    monkeypatch.setattr(device_setting_dialog, "get_device_count", lambda: 0)
    controller = MagicMock()
    controller.get_training_option.return_value = None
    dialog = training_setting_dialog.TrainingSettingDialog(None, controller)
    qtbot.addWidget(dialog)
    warning = MagicMock()
    monkeypatch.setattr(
        user_error_presentation, "show_alert", _record_shared_alert(warning)
    )
    monkeypatch.setattr(
        training_setting_dialog,
        "TrainingOption",
        MagicMock(side_effect=RuntimeError(_SENTINEL)),
    )

    with _capture_public_xbrainlab_logs(caplog):
        dialog.accept()

    warning.assert_called_once_with(
        dialog,
        "Training settings could not be applied",
        _TRAINING_SETTINGS_MESSAGE,
    )
    assert _SENTINEL not in warning.call_args.args[2]
    _assert_logged_exception(caplog)


def test_saliency_settings_unexpected_exception_uses_stable_warning(
    qtbot,
    monkeypatch,
    caplog,
) -> None:
    from XBrainLab.ui.dialogs.visualization import saliency_setting_dialog

    dialog = saliency_setting_dialog.SaliencySettingDialog(None)
    qtbot.addWidget(dialog)
    warning = MagicMock()
    monkeypatch.setattr(
        user_error_presentation, "show_alert", _record_shared_alert(warning)
    )
    monkeypatch.setattr(
        dialog,
        "_editor_value",
        MagicMock(side_effect=RuntimeError(_SENTINEL)),
    )

    with _capture_public_xbrainlab_logs(caplog):
        dialog.accept()

    warning.assert_called_once_with(
        dialog,
        "Saliency settings could not be applied",
        _SALIENCY_SETTINGS_MESSAGE,
    )
    assert _SENTINEL not in warning.call_args.args[2]
    _assert_logged_exception(caplog)


def test_visualization_sidebar_montage_exception_returns_stable_outcome(
    qtbot,
    monkeypatch,
    caplog,
) -> None:
    from XBrainLab.backend.application import CommandName
    from XBrainLab.ui.panels.visualization import control_sidebar

    panel = MagicMock()
    panel.controller = MagicMock()
    panel.main_window = QMainWindow()
    qtbot.addWidget(panel.main_window)
    sidebar = control_sidebar.ControlSidebar(panel)
    qtbot.addWidget(sidebar)
    review_context = SimpleNamespace(
        capability=SimpleNamespace(enabled=True),
        publication_generation=17,
    )
    query_result = SimpleNamespace(
        failed=False,
        diagnostics={"state": {"epoch": {"channel_names": ["C3"]}}},
    )
    monkeypatch.setattr(
        control_sidebar,
        "get_command_review_context",
        lambda _context, command_name: (
            review_context if command_name is CommandName.APPLY_MONTAGE else None
        ),
    )
    monkeypatch.setattr(
        control_sidebar,
        "execute_application_command",
        lambda *_args, **_kwargs: query_result,
    )
    montage_dialog = MagicMock()
    montage_dialog.exec.return_value = True
    montage_dialog.get_result.return_value = (["C3"], [[0.0, 0.0, 0.0]])
    monkeypatch.setattr(
        control_sidebar,
        "PickMontageDialog",
        lambda *_args, **_kwargs: montage_dialog,
    )
    monkeypatch.setattr(
        control_sidebar,
        "normalize_montage_positions",
        MagicMock(side_effect=RuntimeError(_SENTINEL)),
    )
    critical = MagicMock()
    monkeypatch.setattr(
        user_error_presentation, "show_alert", _record_shared_alert(critical)
    )

    with _capture_public_xbrainlab_logs(caplog):
        outcome = sidebar.set_montage()

    assert outcome.status is InteractionStatus.FAILED
    assert outcome.message == _MONTAGE_SETUP_MESSAGE
    critical.assert_called_once_with(
        sidebar,
        "Montage setup could not be applied",
        _MONTAGE_SETUP_MESSAGE,
    )
    _assert_logged_exception(caplog)


def test_dataset_panel_loader_exception_uses_stable_message(
    qtbot,
    monkeypatch,
    caplog,
) -> None:
    from XBrainLab.ui.panels.dataset import panel as dataset_panel

    window = QMainWindow()
    qtbot.addWidget(window)
    window.study = MagicMock()
    panel = dataset_panel.DatasetPanel(controller=MagicMock(), parent=window)
    qtbot.addWidget(panel)
    monkeypatch.setattr(
        panel,
        "_compatibility_apply_loader",
        MagicMock(side_effect=RuntimeError(_SENTINEL)),
    )
    critical = MagicMock()
    monkeypatch.setattr(
        user_error_presentation, "show_alert", _record_shared_alert(critical)
    )

    with _capture_public_xbrainlab_logs(caplog):
        panel.apply_loader(MagicMock())

    critical.assert_called_once_with(
        panel,
        "Dataset could not be updated",
        _DATASET_APPLY_MESSAGE,
    )
    assert _SENTINEL not in critical.call_args.args[2]
    _assert_logged_exception(caplog)


def test_structured_training_failure_keeps_backend_recovery_message(
    qtbot,
    monkeypatch,
) -> None:
    sidebar = _training_widget(qtbot)
    critical = MagicMock()
    monkeypatch.setattr(training_sidebar, "show_error", critical)
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


def test_catch_all_exception_values_never_reach_ui_product_sinks() -> None:
    leaks: list[str] = []

    for path in sorted(_UI_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        relative_path = path.relative_to(_REPO_ROOT).as_posix()
        for handler in (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ExceptHandler)
            and _is_catch_all_handler(node)
            and handler_alias(node) is not None
        ):
            tainted_names = _exception_derived_names(handler)
            for call in (
                node for node in ast.walk(handler) if isinstance(node, ast.Call)
            ):
                if not _is_user_error_sink(call):
                    continue
                if _references_any_name(call, tainted_names):
                    leaks.append(f"{relative_path}:{call.lineno}:{_call_name(call)}")

    assert leaks == []


def test_worker_callback_error_values_never_reach_ui_product_sinks() -> None:
    leaks: list[str] = []

    for path in sorted(_UI_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        relative_path = path.relative_to(_REPO_ROOT).as_posix()
        for function in (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ):
            parameter_names = {
                argument.arg
                for argument in (
                    *function.args.posonlyargs,
                    *function.args.args,
                    *function.args.kwonlyargs,
                )
                if argument.arg in {"error", "error_info", "worker_error"}
            }
            if not parameter_names:
                continue
            tainted_names = _derived_names(function, parameter_names)
            for call in (
                node for node in ast.walk(function) if isinstance(node, ast.Call)
            ):
                if not _is_user_error_sink(call):
                    continue
                if _references_any_name(call, tainted_names):
                    leaks.append(f"{relative_path}:{call.lineno}:{_call_name(call)}")

    assert leaks == []


def handler_alias(handler: ast.ExceptHandler) -> str | None:
    return handler.name if isinstance(handler.name, str) else None


def _is_catch_all_handler(handler: ast.ExceptHandler) -> bool:
    caught = handler.type
    if caught is None:
        return True
    if isinstance(caught, ast.Name):
        return caught.id in {"BaseException", "Exception"}
    if isinstance(caught, ast.Tuple):
        return any(
            isinstance(element, ast.Name)
            and element.id in {"BaseException", "Exception"}
            for element in caught.elts
        )
    return False


def _exception_derived_names(handler: ast.ExceptHandler) -> set[str]:
    alias = handler_alias(handler)
    if alias is None:
        return set()
    return _derived_names(handler, {alias})


def _derived_names(node: ast.AST, roots: set[str]) -> set[str]:
    tainted_names = set(roots)
    assignments = [
        candidate
        for candidate in ast.walk(node)
        if isinstance(candidate, (ast.Assign, ast.AnnAssign, ast.NamedExpr))
    ]

    changed = True
    while changed:
        changed = False
        for assignment in assignments:
            value = assignment.value
            if not _references_any_name(value, tainted_names):
                continue
            targets = (
                assignment.targets
                if isinstance(assignment, ast.Assign)
                else [assignment.target]
            )
            for target in targets:
                for name in (
                    node.id for node in ast.walk(target) if isinstance(node, ast.Name)
                ):
                    if name not in tainted_names:
                        tainted_names.add(name)
                        changed = True
    return tainted_names


def _references_any_name(node: ast.AST, names: set[str]) -> bool:
    return any(
        isinstance(candidate, ast.Name) and candidate.id in names
        for candidate in ast.walk(node)
    )


def _is_message_box_call(call: ast.Call) -> bool:
    function = call.func
    return (
        isinstance(function, ast.Attribute)
        and function.attr in {"critical", "warning", "information"}
        and isinstance(function.value, ast.Name)
        and function.value.id == "QMessageBox"
    )


def _is_user_error_sink(call: ast.Call) -> bool:
    if _is_message_box_call(call):
        return True
    function = call.func
    if isinstance(function, ast.Name):
        return function.id == "show_status_message"
    return isinstance(function, ast.Attribute) and function.attr in {
        "_show_status",
        "showMessage",
    }


def _call_name(call: ast.Call) -> str:
    function = call.func
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        return function.attr
    return "<call>"
