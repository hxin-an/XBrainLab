"""Detached dataset-splitting publications for UI tests."""

from __future__ import annotations

from collections.abc import Callable

from XBrainLab.backend.application.dataset_split_preview import (
    DatasetSplitChoice,
    DatasetSplitContext,
    DatasetSplitPreviewPublication,
    DatasetSplitPreviewRequest,
    DatasetSplitPreviewRow,
)

TEST_PUBLICATION_GENERATION = 7


def split_context(
    *,
    epoch_available: bool = True,
    subject_count: int = 2,
    session_count: int = 1,
    label_count: int = 2,
    trial_count: int = 100,
) -> DatasetSplitContext:
    """Return one compact, detached context for dialog tests."""
    if not epoch_available:
        return DatasetSplitContext(epoch_available=False)
    return DatasetSplitContext(
        epoch_available=True,
        subject_count=subject_count,
        session_count=session_count,
        label_count=label_count,
        trial_count=trial_count,
        subject_choices=tuple(
            DatasetSplitChoice(value=f"S{index + 1:02d}", label=f"S{index + 1:02d}")
            for index in range(subject_count)
        ),
        session_choices=tuple(
            DatasetSplitChoice(
                value=f"session-{index + 1}",
                label=f"session-{index + 1}",
            )
            for index in range(session_count)
        ),
    )


def successful_preview(
    request: DatasetSplitPreviewRequest,
) -> DatasetSplitPreviewPublication:
    """Return one successful detached preview publication."""
    return DatasetSplitPreviewPublication(
        request=request,
        generation=request.publication_generation,
        rows=(
            DatasetSplitPreviewRow(
                name="Fold_0",
                train_count=80,
                validation_count=10,
                test_count=10,
            ),
        ),
    )


def dialog_context_kwargs(
    *,
    context: DatasetSplitContext | None = None,
    preview_provider: Callable[
        [DatasetSplitPreviewRequest],
        DatasetSplitPreviewPublication,
    ] = successful_preview,
) -> dict[str, object]:
    """Return keyword arguments shared by both split-dialog steps."""
    return {
        "split_context": context or split_context(),
        "publication_generation": TEST_PUBLICATION_GENERATION,
        "preview_provider": preview_provider,
        "preview_canceller": lambda _request_id: True,
    }
