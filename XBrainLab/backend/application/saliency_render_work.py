"""Unified owned-work lifecycle for saliency publication and native rendering."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import replace

from XBrainLab.backend.utils.public_diagnostics import public_exception_message

from .owned_work import (
    OwnedOperationCancelledError,
    OwnedOperationSnapshot,
    OwnedWorkKind,
    OwnedWorkRegistry,
    owned_work_checkpoint,
)
from .saliency_render import (
    SaliencyRenderPublication,
    SaliencyRenderRequest,
    normalized_saliency_render_publication,
)


def _request_identity(request: SaliencyRenderRequest) -> str:
    payload = {
        "generation": request.publication_generation,
        "run": request.run.to_dict(),
        "run_type": type(request.run).__name__,
        "method": request.method,
        "normalize": request.normalize,
        "view": request.view,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return f"saliency_render:{digest}"


class SaliencyRenderWorkController:
    """Keep one RENDER operation alive through the native canvas commit."""

    def __init__(
        self,
        *,
        registry: OwnedWorkRegistry,
        publish: Callable[[SaliencyRenderRequest], SaliencyRenderPublication],
    ) -> None:
        self._registry = registry
        self._publish = publish

    def begin(self, request: SaliencyRenderRequest) -> OwnedOperationSnapshot:
        if not isinstance(request, SaliencyRenderRequest):
            raise TypeError("request must be a SaliencyRenderRequest")
        return self._registry.begin(
            OwnedWorkKind.RENDER,
            cancellable=True,
            stage="Queued saliency render",
            command_identity=_request_identity(request),
        )

    def prepare(
        self,
        operation_id: str,
        request: SaliencyRenderRequest,
    ) -> SaliencyRenderPublication:
        """Publish detached data while retaining ownership for native rendering."""
        normalized = str(operation_id or "").strip()
        self._registry.claim_start(
            normalized,
            kind=OwnedWorkKind.RENDER,
            command_identity=_request_identity(request),
        )
        try:
            with self._registry.bind(normalized):
                owned_work_checkpoint("Preparing saliency render data")
                publication = self._publish(request)
                self._validate_publication(publication, request)
                owned_work_checkpoint("Rendering saliency canvas")
                return replace(publication, operation_id=normalized)
        except OwnedOperationCancelledError:
            raise
        except BaseException as exc:
            self._registry.fail(normalized, message=public_exception_message(exc))
            raise

    def prepare_variants(
        self,
        operation_id: str,
        request: SaliencyRenderRequest,
        *,
        include_normalized: bool,
    ) -> tuple[SaliencyRenderPublication, SaliencyRenderPublication | None]:
        """Prepare raw and optional normalized data inside one owned operation."""
        normalized_id = str(operation_id or "").strip()
        self._registry.claim_start(
            normalized_id,
            kind=OwnedWorkKind.RENDER,
            command_identity=_request_identity(request),
        )
        raw_request = replace(request, normalize=False)
        try:
            with self._registry.bind(normalized_id):
                owned_work_checkpoint("Preparing saliency render data")
                raw_publication = self._publish(raw_request)
                self._validate_publication(raw_publication, raw_request)
                raw_publication = replace(
                    raw_publication,
                    operation_id=normalized_id,
                )
                normalized_publication = None
                if include_normalized:
                    owned_work_checkpoint("Normalizing saliency render data")
                    normalized_publication = normalized_saliency_render_publication(
                        raw_publication
                    )
                    owned_work_checkpoint("Saliency normalization ready")
                owned_work_checkpoint("Rendering saliency canvas")
                return raw_publication, normalized_publication
        except OwnedOperationCancelledError:
            raise
        except BaseException as exc:
            self._registry.fail(normalized_id, message=public_exception_message(exc))
            raise

    def finish(self, operation_id: str, phase: str, *, message: str = "") -> None:
        """Publish the native generation's exact terminal outcome."""
        normalized = str(operation_id or "").strip()
        snapshot = self._registry.snapshot(normalized)
        if snapshot.phase.terminal:
            return
        if snapshot.cancel_requested:
            self._registry.finish_cancelled(normalized)
        elif phase == "completed":
            self._registry.complete(normalized)
        elif phase == "cancelled":
            self._registry.finish_cancelled(normalized)
        elif phase == "failed":
            self._registry.fail(normalized, message=message or "Render failed")
        else:
            raise ValueError("render terminal phase is invalid")

    def enter_commit(self, operation_id: str) -> bool:
        """Atomically admit a native canvas commit or terminalize cancellation."""
        normalized = str(operation_id or "").strip()
        try:
            self._registry.enter_commit(
                normalized,
                "Committing saliency canvas",
            )
        except OwnedOperationCancelledError:
            self._registry.finish_cancelled(normalized)
            return False
        return True

    def cancel(self, operation_id: str) -> bool:
        return self._registry.cancel(str(operation_id))

    def snapshot(self, operation_id: str) -> OwnedOperationSnapshot:
        return self._registry.snapshot(str(operation_id))

    @staticmethod
    def _validate_publication(
        publication: object,
        request: SaliencyRenderRequest,
    ) -> None:
        if (
            not isinstance(publication, SaliencyRenderPublication)
            or publication.request != request
            or publication.generation != request.publication_generation
        ):
            raise TypeError("Saliency render publication identity is invalid")


__all__ = ["SaliencyRenderWorkController"]
