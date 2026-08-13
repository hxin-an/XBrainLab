"""Unified owned-work lifecycle for detached Evaluation publications."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import replace

from XBrainLab.backend.utils.public_diagnostics import public_exception_message

from .evaluation_render import EvaluationRenderPublication, EvaluationRenderRequest
from .owned_work import (
    OwnedOperationCancelledError,
    OwnedOperationSnapshot,
    OwnedWorkKind,
    OwnedWorkRegistry,
    owned_work_checkpoint,
    owned_work_commit_boundary,
)

_EVALUATION_RENDER_COMMAND = "evaluation_render"


def _request_command_identity(request: EvaluationRenderRequest) -> str:
    selection = request.selection
    payload = {
        "generation": request.publication_generation,
        "selection": selection.to_dict(),
        "selection_type": type(selection).__name__,
        "split": request.split,
    }
    digest = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return f"{_EVALUATION_RENDER_COMMAND}:{digest}"


class EvaluationWorkController:
    """Run Evaluation reads inside the application's single work registry."""

    def __init__(
        self,
        *,
        registry: OwnedWorkRegistry,
        render: Callable[[EvaluationRenderRequest], EvaluationRenderPublication],
    ) -> None:
        if not isinstance(registry, OwnedWorkRegistry):
            raise TypeError("registry must be an OwnedWorkRegistry")
        if not callable(render):
            raise TypeError("render must be callable")
        self._registry = registry
        self._render = render

    def begin(self, request: EvaluationRenderRequest) -> OwnedOperationSnapshot:
        """Reserve one request-bound operation before its worker is scheduled."""
        if not isinstance(request, EvaluationRenderRequest):
            raise TypeError("request must be an EvaluationRenderRequest")
        return self._registry.begin(
            OwnedWorkKind.EVALUATION,
            cancellable=True,
            stage="Queued evaluation render",
            command_identity=_request_command_identity(request),
        )

    def run(
        self,
        operation_id: str,
        request: EvaluationRenderRequest,
    ) -> EvaluationRenderPublication:
        """Claim, render, verify, and terminate one exact operation identity."""
        if not isinstance(request, EvaluationRenderRequest):
            raise TypeError("request must be an EvaluationRenderRequest")
        normalized_operation_id = str(operation_id or "").strip()
        if not normalized_operation_id:
            raise ValueError("operation_id must be non-empty")
        self._registry.claim_start(
            normalized_operation_id,
            kind=OwnedWorkKind.EVALUATION,
            command_identity=_request_command_identity(request),
        )
        try:
            with self._registry.bind(normalized_operation_id):
                owned_work_checkpoint("Preparing evaluation render")
                publication = self._render(request)
                owned_work_checkpoint("Verifying evaluation render")
                self._validate_publication(publication, request)
                owned_work_commit_boundary("Finalizing evaluation render")
                publication = replace(
                    publication,
                    operation_id=normalized_operation_id,
                )
        except OwnedOperationCancelledError:
            raise
        except BaseException as exc:
            self._registry.fail(
                normalized_operation_id,
                message=public_exception_message(exc),
            )
            raise
        else:
            self._registry.complete(normalized_operation_id)
            return publication

    def cancel(self, operation_id: str) -> bool:
        """Request cancellation without entering the application command lock."""
        return self._registry.cancel(str(operation_id))

    def snapshot(self, operation_id: str) -> OwnedOperationSnapshot:
        """Return immutable progress from the application's shared registry."""
        return self._registry.snapshot(str(operation_id))

    @staticmethod
    def _validate_publication(
        publication: object,
        request: EvaluationRenderRequest,
    ) -> None:
        if (
            not isinstance(publication, EvaluationRenderPublication)
            or publication.request != request
            or publication.generation != request.publication_generation
            or publication.operation_id is not None
            or not publication.producer_identities
            or not publication.split_specification_fingerprint
            or publication.split_epoch_revision is None
        ):
            raise TypeError(
                "Evaluation render returned an invalid publication identity"
            )


__all__ = ["EvaluationWorkController"]
