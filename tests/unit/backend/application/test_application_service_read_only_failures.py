"""Read-only ApplicationService failure state-truth regressions."""

from __future__ import annotations

import pytest

from XBrainLab.backend.application.commands import (
    Command,
    EvaluateCommand,
    PreviewLabelImportCommand,
    SaliencyCommand,
    TrainCommand,
    VisualizeCommand,
)
from XBrainLab.backend.application.results import ChangedState, ErrorType
from XBrainLab.backend.application.service import ApplicationService
from XBrainLab.backend.study import Study


def test_visualize_then_saliency_failures_preserve_publication_error_truth() -> None:
    service = ApplicationService(Study())
    initial = service.get_view_publication()

    visualize = service.execute(VisualizeCommand())
    after_visualize = service.get_view_publication()
    saliency = service.execute(SaliencyCommand())
    after_saliency = service.get_view_publication()

    assert visualize.failed is True
    assert visualize.error_type is ErrorType.PRECONDITION
    assert saliency.failed is True
    assert saliency.error_type is ErrorType.PRECONDITION
    assert visualize.state == initial.state
    assert saliency.state == initial.state
    assert visualize.state is not initial.state
    assert saliency.state is not initial.state
    assert visualize.changed_state == ChangedState()
    assert saliency.changed_state == ChangedState()
    assert visualize.diagnostics["read_only_query"] is True
    assert saliency.diagnostics["read_only_query"] is True
    assert visualize.diagnostics["state_preserved"] is True
    assert saliency.diagnostics["state_preserved"] is True
    assert after_visualize == initial
    assert after_saliency == initial


def test_mutating_failure_records_error_while_later_queries_preserve_it() -> None:
    service = ApplicationService(Study())

    train = service.execute(TrainCommand())
    after_train = service.get_view_publication()
    visualize = service.execute(VisualizeCommand())
    saliency = service.execute(SaliencyCommand())
    after_queries = service.get_view_publication()

    assert train.failed is True
    assert train.error_type is ErrorType.PRECONDITION
    assert train.state.last_error is not None
    assert train.state.last_error.message == train.message
    assert train.changed_state.error_changed is True
    assert after_train.state.last_error == train.state.last_error
    assert visualize.state.last_error == train.state.last_error
    assert saliency.state.last_error == train.state.last_error
    assert after_queries == after_train


def test_configuring_saliency_failure_still_records_application_error() -> None:
    service = ApplicationService(Study())

    result = service.execute(SaliencyCommand(method="Gradient"))
    publication = service.get_view_publication()

    assert result.failed is True
    assert result.error_type is ErrorType.PRECONDITION
    assert result.state.last_error is not None
    assert result.state.last_error.message == result.message
    assert result.changed_state.error_changed is True
    assert publication.state.last_error == result.state.last_error


@pytest.mark.parametrize(
    "command",
    [SaliencyCommand(method=""), SaliencyCommand(params={})],
)
def test_empty_saliency_payloads_are_read_only_queries(
    command: SaliencyCommand,
) -> None:
    service = ApplicationService(Study())
    initial = service.get_view_publication()

    result = service.execute(command)
    after = service.get_view_publication()

    assert result.failed is True
    assert result.diagnostics["read_only_query"] is True
    assert result.diagnostics["state_preserved"] is True
    assert after == initial


@pytest.mark.parametrize(
    "command",
    [
        EvaluateCommand(),
        PreviewLabelImportCommand(label_paths=[]),
    ],
    ids=["evaluate", "preview-label-import"],
)
def test_other_read_only_failures_preserve_publication_truth(command: Command) -> None:
    service = ApplicationService(Study())
    initial = service.get_view_publication()

    result = service.execute(command)
    after = service.get_view_publication()

    assert result.failed is True
    assert result.error_type is ErrorType.PRECONDITION
    assert result.state == initial.state
    assert result.changed_state == ChangedState()
    assert result.diagnostics["read_only_query"] is True
    assert result.diagnostics["state_preserved"] is True
    assert after == initial
