"""Host-owned provenance attached to public training configuration commands."""

from __future__ import annotations

from dataclasses import dataclass, fields

from .commands import ConfigureTrainingCommand
from .resource_guard import TrainingResourcePreviewReceipt
from .training_recommendation import TrainingRecommendationField


@dataclass(frozen=True)
class _HostConfigureTrainingCommand(ConfigureTrainingCommand):
    edited_fields: frozenset[TrainingRecommendationField] = frozenset()
    resource_preview_receipt: TrainingResourcePreviewReceipt | None = None

    @property
    def edited_recommendation_fields(
        self,
    ) -> frozenset[TrainingRecommendationField]:
        return self.edited_fields


def attach_training_submission_provenance(
    command: ConfigureTrainingCommand,
    edited_fields: frozenset[TrainingRecommendationField],
    *,
    resource_preview_receipt: TrainingResourcePreviewReceipt | None = None,
) -> ConfigureTrainingCommand:
    """Return an internal command carrying fields derived by a trusted host."""
    if not isinstance(command, ConfigureTrainingCommand):
        raise TypeError("command must be a ConfigureTrainingCommand")
    normalized = frozenset(
        field
        if isinstance(field, TrainingRecommendationField)
        else TrainingRecommendationField(str(field))
        for field in edited_fields
    )
    values = {
        field.name: getattr(command, field.name)
        for field in fields(ConfigureTrainingCommand)
    }
    return _HostConfigureTrainingCommand(
        **values,
        edited_fields=normalized,
        resource_preview_receipt=resource_preview_receipt,
    )


def training_submission_edited_fields(
    command: ConfigureTrainingCommand,
) -> frozenset[TrainingRecommendationField]:
    """Read trusted provenance; ordinary public commands have none."""
    if not isinstance(command, _HostConfigureTrainingCommand):
        return frozenset()
    return command.edited_fields


def training_submission_resource_preview_receipt(
    command: ConfigureTrainingCommand,
) -> TrainingResourcePreviewReceipt | None:
    """Read a preview receipt attached by the trusted desktop host."""
    if not isinstance(command, _HostConfigureTrainingCommand):
        return None
    return command.resource_preview_receipt
