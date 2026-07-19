from unittest.mock import patch

import pytest

from XBrainLab.backend.application import QueryStateCommand
from XBrainLab.backend.application.results import (
    ChangedState,
    CommandResult,
    ErrorType,
)
from XBrainLab.ui.panels.preprocess.data_query import (
    PreprocessRenderDataUnavailableError,
    query_preprocess_render_lists,
)


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


def test_query_preprocess_render_lists_strict_mode_rejects_missing_runtime() -> None:
    context = object()

    with (
        patch(
            "XBrainLab.ui.panels.preprocess.data_query.execute_application_command",
            return_value=None,
        ),
        pytest.raises(
            PreprocessRenderDataUnavailableError,
            match="application state could not be read",
        ),
    ):
        query_preprocess_render_lists(context, require_available=True)


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


def test_query_preprocess_render_lists_strict_mode_surfaces_query_failure() -> None:
    context = object()
    result = CommandResult.failure_result(
        "query_state",
        "Query failed.",
        state={},
        changed_state=ChangedState(error_changed=True),
        error_type=ErrorType.PRECONDITION,
        recoverable=True,
        error_message="Published preprocess objects are stale.",
    )

    with (
        patch(
            "XBrainLab.ui.panels.preprocess.data_query.execute_application_command",
            return_value=result,
        ),
        pytest.raises(
            PreprocessRenderDataUnavailableError,
            match="Published preprocess objects are stale",
        ),
    ):
        query_preprocess_render_lists(context, require_available=True)


def test_query_preprocess_render_lists_strict_mode_rejects_incomplete_payload() -> None:
    context = object()
    result = CommandResult.success_result(
        "query_state",
        "Incomplete data lists.",
        state={},
        changed_state=ChangedState(),
        diagnostics={"preprocessed_data_list": []},
    )

    with (
        patch(
            "XBrainLab.ui.panels.preprocess.data_query.execute_application_command",
            return_value=result,
        ),
        pytest.raises(
            PreprocessRenderDataUnavailableError,
            match="did not publish both data lists",
        ),
    ):
        query_preprocess_render_lists(context, require_available=True)
