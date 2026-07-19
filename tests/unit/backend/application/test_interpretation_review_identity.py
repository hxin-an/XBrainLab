"""Publication-bound Data Import review retrieval tests."""

from __future__ import annotations

import pytest

from XBrainLab.backend.application.data_interpretation_candidate import (
    InterpretationCandidate,
)
from XBrainLab.backend.application.data_interpretation_review import (
    InterpretationPreview,
    ValidationDecision,
)
from XBrainLab.backend.application.data_interpretation_scan import ScanResult
from XBrainLab.backend.application.errors import PreconditionError
from XBrainLab.backend.application.service import ApplicationService
from XBrainLab.backend.application.view_publication import (
    InterpretationReviewIdentity,
)
from XBrainLab.backend.study import Study


def _record_review(service: ApplicationService, suffix: str) -> None:
    interpretation = service.interpretation._service()
    state = interpretation.state
    scan = ScanResult(
        scan_id=f"scan-{suffix}",
        source_path=f"/tmp/source-{suffix}",
        source_kind="folder",
        eeg_files=[f"/tmp/source-{suffix}/recording.fif"],
        label_carriers=[],
        format_capabilities=[{"format": "fif", "status": "safe"}],
    )
    candidate = InterpretationCandidate(
        candidate_id=f"candidate-{suffix}",
        scan_id=scan.scan_id,
        source_path=scan.source_path,
        source_kind=scan.source_kind,
        selected_eeg_files=list(scan.eeg_files),
        format_capabilities=list(scan.format_capabilities),
        recipe_trace=[f"scan:{scan.scan_id}"],
    )
    preview = InterpretationPreview(
        preview_id=f"preview-{suffix}",
        candidate_id=candidate.candidate_id,
        summary=f"Review {suffix}",
        file_count=1,
        label_carrier_count=0,
        format_capabilities=list(candidate.format_capabilities),
    )
    decision = ValidationDecision(
        candidate_id=candidate.candidate_id,
        decision="safe",
    )
    state.record_scan(scan)
    state.record_preview(candidate, preview)
    state.record_validation(candidate.candidate_id, decision)
    service.get_state()


def _identity(service: ApplicationService) -> InterpretationReviewIdentity:
    publication = service.get_view_publication()
    interpretation = publication.state.interpretation
    assert interpretation.latest_scan_id is not None
    assert interpretation.latest_candidate_id is not None
    return InterpretationReviewIdentity(
        publication_generation=publication.generation,
        scan_id=interpretation.latest_scan_id,
        candidate_id=interpretation.latest_candidate_id,
    )


def test_review_a_cannot_reopen_after_review_b_is_published() -> None:
    service = ApplicationService(Study())
    _record_review(service, "a")
    identity_a = _identity(service)
    assert (
        service.get_interpretation_review(
            expected_identity=identity_a,
        )["candidate"]["candidate_id"]
        == "candidate-a"
    )

    _record_review(service, "b")
    identity_b = _identity(service)

    with pytest.raises(PreconditionError) as exc_info:
        service.get_interpretation_review(expected_identity=identity_a)

    assert exc_info.value.error_type.value == "precondition"
    assert exc_info.value.diagnostics["stale_interpretation_review"] is True
    assert exc_info.value.diagnostics["expected_candidate_id"] == "candidate-a"
    assert exc_info.value.diagnostics["current_candidate_id"] == "candidate-b"
    review_b = service.get_interpretation_review(expected_identity=identity_b)
    assert review_b["scan_result"]["scan_id"] == "scan-b"
    assert review_b["candidate"]["candidate_id"] == "candidate-b"
