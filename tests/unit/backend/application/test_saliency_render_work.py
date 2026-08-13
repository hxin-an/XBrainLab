from __future__ import annotations

import threading
from collections.abc import Iterator, Mapping
from typing import Any

import numpy as np

from XBrainLab.backend.application.owned_work import (
    OwnedOperationCancelledError,
    OwnedWorkKind,
    OwnedWorkPhase,
    OwnedWorkRegistry,
    owned_work_checkpoint,
)
from XBrainLab.backend.application.saliency_render import (
    SaliencyCrossFoldClass,
    SaliencyPlanIdentity,
    SaliencyRenderData,
    SaliencyRenderPublication,
    SaliencyRenderRequest,
    SaliencyRunIdentity,
    _pool_cross_fold_saliency,
    normalized_saliency_render_publication,
)
from XBrainLab.backend.application.saliency_render_work import (
    SaliencyRenderWorkController,
)


def _request(*, generation: int = 3) -> SaliencyRenderRequest:
    return SaliencyRenderRequest(
        publication_generation=generation,
        run=SaliencyRunIdentity(
            plan=SaliencyPlanIdentity(plan_index=0),
            run_index=0,
        ),
        method="Gradient",
    )


def _publication(request: SaliencyRenderRequest) -> SaliencyRenderPublication:
    return SaliencyRenderPublication(
        request=request,
        generation=request.publication_generation,
        training_generation=2,
        data=SaliencyRenderData(
            method=request.method,
            saliency_by_class={0: np.ones((1, 2, 3), dtype=np.float32)},
            class_map=((0, "Left"),),
            event_ids={"Left": 769},
            channel_names=("C3", "C4"),
            channel_positions=(),
            sfreq=128.0,
            tmin=-0.2,
        ),
    )


def test_saliency_render_stays_owned_until_native_commit() -> None:
    registry = OwnedWorkRegistry()
    controller = SaliencyRenderWorkController(
        registry=registry,
        publish=_publication,
    )
    request = _request()
    scheduled = controller.begin(request)

    publication = controller.prepare(scheduled.operation_id, request)

    running = registry.snapshot(scheduled.operation_id)
    assert scheduled.kind is OwnedWorkKind.RENDER
    assert running.phase is OwnedWorkPhase.RUNNING
    assert running.stage == "Rendering saliency canvas"
    assert publication.operation_id == scheduled.operation_id

    assert controller.enter_commit(scheduled.operation_id) is True
    controller.finish(scheduled.operation_id, "completed")
    assert registry.snapshot(scheduled.operation_id).phase is OwnedWorkPhase.COMPLETED


def test_saliency_render_cancel_before_commit_rejects_canvas_and_retry_succeeds() -> (
    None
):
    registry = OwnedWorkRegistry()
    controller = SaliencyRenderWorkController(
        registry=registry,
        publish=_publication,
    )
    request = _request()
    scheduled = controller.begin(request)
    controller.prepare(scheduled.operation_id, request)

    assert controller.cancel(scheduled.operation_id) is True
    assert controller.enter_commit(scheduled.operation_id) is False
    controller.finish(scheduled.operation_id, "completed")
    assert registry.snapshot(scheduled.operation_id).phase is OwnedWorkPhase.CANCELLED

    retry_request = _request(generation=4)
    retry = controller.begin(retry_request)
    controller.prepare(retry.operation_id, retry_request)
    assert controller.enter_commit(retry.operation_id) is True
    controller.finish(retry.operation_id, "completed")
    assert registry.snapshot(retry.operation_id).phase is OwnedWorkPhase.COMPLETED


def test_saliency_render_cancel_after_commit_is_not_admitted() -> None:
    registry = OwnedWorkRegistry()
    controller = SaliencyRenderWorkController(
        registry=registry,
        publish=_publication,
    )
    request = _request()
    scheduled = controller.begin(request)
    controller.prepare(scheduled.operation_id, request)

    assert controller.enter_commit(scheduled.operation_id) is True
    assert controller.cancel(scheduled.operation_id) is False
    controller.finish(scheduled.operation_id, "completed")

    assert registry.snapshot(scheduled.operation_id).phase is OwnedWorkPhase.COMPLETED


def test_saliency_render_cancel_during_normalization_terminalizes_and_retries(
    monkeypatch,
) -> None:
    registry = OwnedWorkRegistry()
    controller = SaliencyRenderWorkController(
        registry=registry,
        publish=_publication,
    )
    entered = threading.Event()
    release = threading.Event()

    def blocked_normalize(publication):
        entered.set()
        assert release.wait(timeout=2.0)
        owned_work_checkpoint("Normalizing blocked saliency class")
        return publication

    monkeypatch.setattr(
        "XBrainLab.backend.application.saliency_render_work."
        "normalized_saliency_render_publication",
        blocked_normalize,
    )
    request = _request()
    scheduled = controller.begin(request)
    failures: list[BaseException] = []

    def prepare() -> None:
        try:
            controller.prepare_variants(
                scheduled.operation_id,
                request,
                include_normalized=True,
            )
        except BaseException as exc:
            failures.append(exc)

    worker = threading.Thread(target=prepare)
    worker.start()
    assert entered.wait(timeout=2.0)
    assert controller.cancel(scheduled.operation_id) is True
    release.set()
    worker.join(timeout=2.0)

    assert not worker.is_alive()
    assert len(failures) == 1
    assert isinstance(failures[0], OwnedOperationCancelledError)
    assert registry.snapshot(scheduled.operation_id).phase is OwnedWorkPhase.CANCELLED

    monkeypatch.setattr(
        "XBrainLab.backend.application.saliency_render_work."
        "normalized_saliency_render_publication",
        normalized_saliency_render_publication,
    )
    retry_request = _request(generation=4)
    retry = controller.begin(retry_request)
    raw, normalized = controller.prepare_variants(
        retry.operation_id,
        retry_request,
        include_normalized=True,
    )
    assert raw.operation_id == retry.operation_id
    assert normalized is not None
    assert normalized.request.normalize is True


def test_cross_fold_pool_cancel_after_store_read_discards_partial_result() -> None:
    registry = OwnedWorkRegistry()
    scheduled = registry.begin(OwnedWorkKind.RENDER, cancellable=True)
    registry.start(scheduled.operation_id)
    entered = threading.Event()
    release = threading.Event()

    class _BlockingStore(Mapping[object, Any]):
        def __getitem__(self, key: object) -> Any:
            assert key == 0
            entered.set()
            assert release.wait(timeout=2.0)
            return np.full((1, 1, 2), 2.0)

        def __iter__(self) -> Iterator[object]:
            return iter((0,))

        def __len__(self) -> int:
            return 1

    results: list[dict[object, np.ndarray]] = []
    failures: list[BaseException] = []

    def pool() -> None:
        try:
            with registry.bind(scheduled.operation_id):
                results.append(
                    _pool_cross_fold_saliency(
                        (
                            {0: np.ones((1, 1, 2))},
                            _BlockingStore(),
                        ),
                        (
                            SaliencyCrossFoldClass(
                                class_index=0,
                                display_name="Left",
                                event_code=769,
                                store_key=0,
                            ),
                        ),
                        normalize=False,
                    )
                )
        except BaseException as exc:
            failures.append(exc)

    worker = threading.Thread(target=pool)
    worker.start()
    assert entered.wait(timeout=2.0)
    assert registry.cancel(scheduled.operation_id) is True
    release.set()
    worker.join(timeout=2.0)

    assert not worker.is_alive()
    assert results == []
    assert len(failures) == 1
    assert isinstance(failures[0], OwnedOperationCancelledError)
    assert registry.snapshot(scheduled.operation_id).phase is OwnedWorkPhase.CANCELLED

    retry = registry.begin(OwnedWorkKind.RENDER, cancellable=True)
    registry.start(retry.operation_id)
    with registry.bind(retry.operation_id):
        pooled = _pool_cross_fold_saliency(
            (
                {0: np.ones((1, 1, 2))},
                {0: np.full((1, 1, 2), 2.0)},
            ),
            (
                SaliencyCrossFoldClass(
                    class_index=0,
                    display_name="Left",
                    event_code=769,
                    store_key=0,
                ),
            ),
            normalize=False,
        )
    registry.complete(retry.operation_id)
    np.testing.assert_array_equal(pooled[0][:, 0, 0], [1.0, 2.0])
    assert registry.snapshot(retry.operation_id).phase is OwnedWorkPhase.COMPLETED


def test_single_fold_class_copy_observes_cancel_after_array_copy() -> None:
    registry = OwnedWorkRegistry()
    scheduled = registry.begin(OwnedWorkKind.RENDER, cancellable=True)
    registry.start(scheduled.operation_id)
    entered = threading.Event()
    release = threading.Event()

    class _BlockingArray:
        def __array__(self, dtype=None, copy=None) -> np.ndarray:
            del copy
            entered.set()
            assert release.wait(timeout=2.0)
            return np.ones((1, 2, 3), dtype=dtype or np.float32)

    publications: list[SaliencyRenderData] = []
    failures: list[BaseException] = []

    def copy_single_fold() -> None:
        try:
            with registry.bind(scheduled.operation_id):
                publications.append(
                    SaliencyRenderData(
                        method="Gradient",
                        saliency_by_class={0: _BlockingArray()},
                        class_map=((0, "Left"),),
                        event_ids={"Left": 769},
                        channel_names=("C3", "C4"),
                        channel_positions=(),
                        sfreq=128.0,
                        tmin=-0.2,
                    )
                )
        except BaseException as exc:
            failures.append(exc)

    worker = threading.Thread(target=copy_single_fold)
    worker.start()
    assert entered.wait(timeout=2.0)
    assert registry.cancel(scheduled.operation_id) is True
    release.set()
    worker.join(timeout=2.0)

    assert not worker.is_alive()
    assert publications == []
    assert len(failures) == 1
    assert isinstance(failures[0], OwnedOperationCancelledError)
    assert registry.snapshot(scheduled.operation_id).phase is OwnedWorkPhase.CANCELLED
