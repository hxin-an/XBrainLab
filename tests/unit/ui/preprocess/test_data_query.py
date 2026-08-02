from types import SimpleNamespace
from unittest.mock import patch

import pytest

from XBrainLab.backend.application import QueryStateCommand
from XBrainLab.backend.application.errors import PreconditionError
from XBrainLab.backend.application.preprocess_render import (
    PreprocessRenderData,
    PreprocessRenderPublication,
    PreprocessRenderRequest,
    PreprocessSignalState,
)
from XBrainLab.backend.application.results import (
    ChangedState,
    CommandResult,
    ErrorType,
)
from XBrainLab.ui.panels.preprocess.data_query import (
    PreprocessRenderDataUnavailableError,
    query_preprocess_data_rows,
    query_preprocess_render,
)


def _no_data_publication(
    request: PreprocessRenderRequest,
) -> PreprocessRenderPublication:
    return PreprocessRenderPublication(
        request=request,
        generation=request.publication_generation,
        data=PreprocessRenderData(state=PreprocessSignalState.NO_DATA),
    )


def test_query_preprocess_render_uses_exact_view_generation() -> None:
    context = object()
    captured: list[PreprocessRenderRequest] = []

    def publish(_context, request):
        captured.append(request)
        return _no_data_publication(request)

    with (
        patch(
            "XBrainLab.ui.panels.preprocess.data_query.get_application_view_publication",
            return_value=SimpleNamespace(generation=7, usable=True),
        ),
        patch(
            "XBrainLab.ui.panels.preprocess.data_query.get_preprocess_render_publication",
            side_effect=publish,
        ),
    ):
        publication = query_preprocess_render(
            context,
            channel_index=2,
            start_seconds=3.5,
        )

    assert publication is not None
    assert captured == [
        PreprocessRenderRequest(
            publication_generation=7,
            channel_index=2,
            start_seconds=3.5,
        )
    ]


def test_query_preprocess_render_preserves_missing_runtime_boundary() -> None:
    with (
        patch(
            "XBrainLab.ui.panels.preprocess.data_query.get_application_view_publication",
            return_value=None,
        ),
        patch(
            "XBrainLab.ui.panels.preprocess.data_query.get_preprocess_render_publication"
        ) as publish,
    ):
        assert (
            query_preprocess_render(
                object(),
                channel_index=0,
                start_seconds=0.0,
            )
            is None
        )

    publish.assert_not_called()


def test_query_preprocess_render_surfaces_safe_application_failure() -> None:
    with (
        patch(
            "XBrainLab.ui.panels.preprocess.data_query.get_application_view_publication",
            return_value=SimpleNamespace(generation=7, usable=True),
        ),
        patch(
            "XBrainLab.ui.panels.preprocess.data_query.get_preprocess_render_publication",
            side_effect=PreconditionError("Signal preview is busy."),
        ),
        pytest.raises(
            PreprocessRenderDataUnavailableError,
            match="Signal preview is busy",
        ),
    ):
        query_preprocess_render(
            object(),
            channel_index=0,
            start_seconds=0.0,
        )


def test_query_preprocess_data_rows_uses_detached_application_query() -> None:
    current = {"sampling_frequency": 128.0, "channels": ["C3"]}
    original = {"sampling_frequency": 256.0, "channels": ["C3"]}
    result = CommandResult.success_result(
        "query_state",
        "Data rows ready.",
        state={},
        changed_state=ChangedState(),
        diagnostics={
            "preprocessed_rows": [current],
            "raw_rows": [original],
        },
    )

    with patch(
        "XBrainLab.ui.panels.preprocess.data_query.execute_application_command",
        return_value=result,
    ) as execute:
        rows = query_preprocess_data_rows(object())

    assert rows == ([current], [original])
    assert rows is not None
    assert rows[0][0] is not current
    command = execute.call_args.args[1]
    assert isinstance(command, QueryStateCommand)
    assert command.query == "data_lists"
    assert execute.call_args.kwargs["refresh"] is False


def test_query_preprocess_data_rows_failed_query_returns_empty_rows() -> None:
    result = CommandResult.failure_result(
        "query_state",
        "Query failed.",
        state={},
        changed_state=ChangedState(error_changed=True),
        error_type=ErrorType.PREPROCESSING,
        recoverable=True,
    )

    with patch(
        "XBrainLab.ui.panels.preprocess.data_query.execute_application_command",
        return_value=result,
    ):
        assert query_preprocess_data_rows(object()) == ([], [])
