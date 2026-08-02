"""ApplicationService ownership of dataset-splitting publications."""

from __future__ import annotations

from unittest.mock import Mock

from XBrainLab.backend.application.dataset_split_preview import (
    DatasetSplitContextRequest,
)
from XBrainLab.backend.application.service import ApplicationService
from XBrainLab.backend.study import Study


def test_application_service_publishes_detached_missing_epoch_context() -> None:
    service = ApplicationService(Study())
    publication = service.get_view_publication()

    result = service.get_dataset_split_context(
        DatasetSplitContextRequest(
            publication_generation=publication.generation,
        )
    )

    assert result.generation == publication.generation
    assert result.context.epoch_available is False
    assert not hasattr(result.context, "epoch_data")


def test_shutdown_fence_cancels_active_dataset_split_previews() -> None:
    service = ApplicationService(Study())
    cancel_all = Mock()
    service.dataset_split_preview.cancel_all = cancel_all

    service.request_shutdown_fence()

    cancel_all.assert_called_once_with()
