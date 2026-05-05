from unittest.mock import patch

from XBrainLab.backend.application import QueryStateCommand
from XBrainLab.backend.application.results import (
    ChangedState,
    CommandResult,
    ErrorType,
)
from XBrainLab.ui.panels.preprocess.data_query import query_preprocess_render_lists


def test_query_preprocess_render_lists_uses_application_query() -> None:
    current = object()
    original = object()
    context = object()
    result = CommandResult.success_result(
        "query_state",
        "Data lists ready.",
        state={},
        changed_state=ChangedState(),
        diagnostics={
            "preprocessed_data_list": [current],
            "loaded_data_list": [original],
        },
    )

    with patch(
        "XBrainLab.ui.panels.preprocess.data_query.execute_application_command",
        return_value=result,
    ) as execute:
        data_lists = query_preprocess_render_lists(context)

    assert data_lists == ([current], [original])
    execute.assert_called_once()
    command = execute.call_args.args[1]
    assert isinstance(command, QueryStateCommand)
    assert command.query == "data_lists"
    assert command.include_objects is True
    assert execute.call_args.kwargs["refresh"] is False


def test_query_preprocess_render_lists_preserves_legacy_fallback_boundary() -> None:
    context = object()

    with patch(
        "XBrainLab.ui.panels.preprocess.data_query.execute_application_command",
        return_value=None,
    ):
        assert query_preprocess_render_lists(context) is None


def test_query_preprocess_render_lists_failed_query_returns_empty_lists() -> None:
    context = object()
    result = CommandResult.failure_result(
        "query_state",
        "Query failed.",
        state={},
        changed_state=ChangedState(error_changed=True),
        error_type=ErrorType.PRECONDITION,
        recoverable=True,
    )

    with patch(
        "XBrainLab.ui.panels.preprocess.data_query.execute_application_command",
        return_value=result,
    ):
        assert query_preprocess_render_lists(context) == ([], [])
