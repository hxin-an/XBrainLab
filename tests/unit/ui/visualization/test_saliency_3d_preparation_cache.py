from __future__ import annotations

import gc
import weakref
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
from PyQt6.QtWidgets import QWidget

from XBrainLab.backend.application.saliency_render import (
    SaliencyPlanIdentity,
    SaliencyRenderData,
    SaliencyRenderPublication,
    SaliencyRenderRequest,
    SaliencyRunIdentity,
)
from XBrainLab.backend.application.state import (
    SaliencyClassCoverageSnapshot,
    SaliencyMethodCoverageSnapshot,
)
from XBrainLab.ui.panels.visualization.saliency_views import plot_3d_view
from XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view import (
    Saliency3DPlotWidget,
)


class _Signal:
    def __init__(self) -> None:
        self._callbacks = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def disconnect(self, callback=None) -> None:
        if callback is None:
            self._callbacks.clear()
            return
        self._callbacks.remove(callback)

    def emit(self, *args) -> None:
        for callback in tuple(self._callbacks):
            callback(*args)


class _ImmediateWorker:
    def __init__(self, fn, *args, **kwargs) -> None:
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = SimpleNamespace(
            result=_Signal(),
            error=_Signal(),
            finished=_Signal(),
        )

    def run(self) -> None:
        self.signals.result.emit(self.fn(*self.args, **self.kwargs))
        self.signals.finished.emit()


class _ImmediatePool:
    def __init__(self) -> None:
        self.workers: list[_ImmediateWorker] = []

    def start(self, worker: _ImmediateWorker) -> None:
        self.workers.append(worker)
        try:
            worker.run()
        finally:
            self.workers.remove(worker)

    def clear(self) -> None:
        pass


def _publication(
    *,
    normalize: bool = False,
    generation: int = 7,
) -> SaliencyRenderPublication:
    request = SaliencyRenderRequest(
        publication_generation=generation,
        run=SaliencyRunIdentity(
            plan=SaliencyPlanIdentity(plan_index=0),
            run_index=0,
        ),
        method="Gradient",
        normalize=normalize,
    )
    data = SaliencyRenderData(
        method="Gradient",
        saliency_by_class={
            0: np.ones((1, 2, 4)),
            1: np.full((1, 2, 4), 2.0),
        },
        class_map=((0, "left"), (1, "right")),
        event_ids={"left": 0, "right": 1},
        channel_names=("C3", "C4"),
        channel_positions=((0.0, 0.0, 0.1), (0.1, 0.0, 0.1)),
        sfreq=128.0,
        tmin=0.0,
        normalized=normalize,
    )
    return SaliencyRenderPublication(
        request=request,
        generation=generation,
        training_generation=3,
        data=data,
    )


@pytest.fixture
def widget(qtbot, monkeypatch) -> Saliency3DPlotWidget:
    monkeypatch.setattr(plot_3d_view, "Worker", _ImmediateWorker)
    monkeypatch.setattr(
        Saliency3DPlotWidget,
        "_interactive_3d_runtime_available",
        staticmethod(lambda: (True, "")),
    )
    instance = Saliency3DPlotWidget(parent=None)
    qtbot.addWidget(instance)
    pool = _ImmediatePool()
    monkeypatch.setattr(instance._worker_pool_owner, "_thread_pool", pool)
    plotter = QWidget(instance.plot_container)
    instance.plot_layout.addWidget(plotter)
    instance.plotter_widget = plotter
    instance._do_3d_plot_if_alive = MagicMock()
    instance.set_saliency_coverage(
        SaliencyMethodCoverageSnapshot(
            method="Gradient",
            available=True,
            complete=True,
            classes=[
                SaliencyClassCoverageSnapshot(
                    class_index=0,
                    display_name="left",
                    available=True,
                ),
                SaliencyClassCoverageSnapshot(
                    class_index=1,
                    display_name="right",
                    available=True,
                ),
            ],
        )
    )
    return instance


def _select_class(widget: Saliency3DPlotWidget, name: str) -> None:
    index = widget.class_combo.findText(name)
    widget._requested_class_key = widget.class_combo.itemData(index)
    widget._selector_syncing = True
    widget.class_combo.setCurrentIndex(index)
    widget._selector_syncing = False


def test_prepared_engine_cache_reuses_exact_toggle_requests(
    widget: Saliency3DPlotWidget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = _publication()
    normalized = _publication(normalize=True)
    prepared: list[tuple[object, int]] = []

    def prepare_engine(*_args, **_kwargs):
        result = (object(), 2)
        prepared.append(result)
        return result

    monkeypatch.setattr(
        plot_3d_view.Saliency3D,
        "prepare_engine",
        staticmethod(prepare_engine),
    )

    widget.update_plot(raw, False)
    widget.update_plot(raw, True)
    widget.update_plot(raw, False)
    _select_class(widget, "right")
    widget.update_plot(raw, False)
    _select_class(widget, "left")
    widget.update_plot(raw, False)
    widget.update_plot(normalized, False)
    widget.update_plot(raw, False)

    assert len(prepared) == 4
    assert widget._do_3d_plot_if_alive.call_count == 7

    equal_but_not_exact = replace(raw)
    widget.update_plot(equal_but_not_exact, False)

    assert len(prepared) == 5


def test_prepared_engine_cache_does_not_own_full_publication_payloads(
    widget: Saliency3DPlotWidget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_count = 0

    def prepare_engine(render_data, *_args, **_kwargs):
        nonlocal prepare_count
        prepare_count += 1
        prepared_saliency = np.asarray(render_data.saliency_by_class[0]).mean(axis=0)
        return SimpleNamespace(saliency=prepared_saliency), 2

    monkeypatch.setattr(
        plot_3d_view.Saliency3D,
        "prepare_engine",
        staticmethod(prepare_engine),
    )

    publication_refs = []
    data_refs = []
    payload_refs = []
    for generation in range(1, widget._MAX_PREPARED_ENGINE_CACHE_ENTRIES + 1):
        publication = _publication(generation=generation)
        publication_refs.append(weakref.ref(publication))
        data_refs.append(weakref.ref(publication.data))
        payload_refs.append(weakref.ref(publication.data.saliency_by_class[0]))
        widget.update_plot(publication, False)
        widget._do_3d_plot_if_alive.reset_mock()

    del publication
    gc.collect()

    assert all(reference() is None for reference in publication_refs[:-1])
    assert all(reference() is None for reference in data_refs[:-1])
    assert all(reference() is None for reference in payload_refs[:-1])

    current_publication = publication_refs[-1]()
    assert current_publication is not None
    widget.update_plot(current_publication, False)
    assert prepare_count == widget._MAX_PREPARED_ENGINE_CACHE_ENTRIES


def test_prepared_engine_cache_is_bounded_and_cleared_by_lifecycle(
    widget: Saliency3DPlotWidget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_count = 0

    def prepare_engine(*_args, **_kwargs):
        nonlocal prepare_count
        prepare_count += 1
        return object(), 2

    monkeypatch.setattr(
        plot_3d_view.Saliency3D,
        "prepare_engine",
        staticmethod(prepare_engine),
    )

    publications = [
        _publication(generation=index + 1)
        for index in range(widget._MAX_PREPARED_ENGINE_CACHE_ENTRIES + 2)
    ]
    for publication in publications:
        widget.update_plot(publication, False)

    assert len(widget._prepared_engine_cache) == (
        widget._MAX_PREPARED_ENGINE_CACHE_ENTRIES
    )

    widget.invalidate_render_publication()
    assert not widget._prepared_engine_cache

    widget.update_plot(publications[-1], False)
    assert prepare_count == len(publications) + 1
    assert widget._prepared_engine_cache

    widget.begin_render_shutdown()
    assert not widget._prepared_engine_cache


def test_stale_prepared_engine_result_is_not_cached_or_rendered(
    widget: Saliency3DPlotWidget,
) -> None:
    publication = _publication(generation=31)
    request_id = widget._invalidate_async_requests()
    widget._current_publication_generation = publication.generation
    worker = object()
    widget._engine_worker = worker
    cache_key = widget._prepared_engine_cache_key(
        publication,
        "left",
        absolute=False,
    )

    widget._invalidate_async_requests()
    widget._current_publication_generation = publication.generation + 1
    widget._on_3d_engine_ready(
        worker,
        request_id,
        (object(), 2),
        publication.data,
        "left",
        method="Gradient",
        absolute=False,
        publication_generation=publication.generation,
        publication=publication,
        prepared_cache_key=cache_key,
    )

    assert not widget._prepared_engine_cache
    widget._do_3d_plot_if_alive.assert_not_called()
    widget._engine_worker = None
