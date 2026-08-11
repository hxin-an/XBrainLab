from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from time import monotonic, sleep
from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np
import pytest

from XBrainLab.backend.application.saliency_render import SaliencyRenderData
from XBrainLab.backend.visualization import (
    saliency_spectrogram_map as spectrogram_module,
)
from XBrainLab.backend.visualization.saliency_semantics import (
    SALIENCY_RED_BLUE_CMAP,
    saliency_color_scale,
)
from XBrainLab.backend.visualization.saliency_spectrogram_map import (
    SaliencySpectrogramMapViz,
)


def _render_data() -> SaliencyRenderData:
    rng = np.random.default_rng(17)
    arrays = {
        class_index: rng.standard_normal((4, 4, 64), dtype=np.float32)
        for class_index in range(2)
    }
    return SaliencyRenderData(
        method="Gradient",
        saliency_by_class=arrays,
        class_map=((0, "left"), (1, "right")),
        event_ids={"left": 0, "right": 1},
        channel_names=("C3", "C4", "Cz", "Pz"),
        channel_positions=(
            (-0.04, 0.0, 0.08),
            (0.04, 0.0, 0.08),
            (0.0, 0.03, 0.09),
            (0.0, -0.04, 0.07),
        ),
        sfreq=128.0,
        tmin=-0.2,
    )


def _empty_prepared() -> spectrogram_module._PreparedSpectrogram:
    return spectrogram_module._PreparedSpectrogram(classes=(), diagnostics=())


def _wait_for_cache_waiters(
    cache: spectrogram_module.SaliencySpectrogramPreparationCache,
    *,
    key: object,
    count: int,
) -> None:
    deadline = monotonic() + 1.0
    while monotonic() < deadline:
        with cache._lock:
            flight = cache._in_flight.get(key)
            if flight is not None and flight.waiter_count >= count:
                return
        sleep(0.001)
    raise AssertionError(f"Expected {count} cache waiters for {key!r}")


def test_normalized_signed_and_nonnegative_views_use_fixed_shared_limits() -> None:
    signed = saliency_color_scale(
        "Gradient",
        [np.array([-0.2, 0.7])],
        absolute=False,
        normalized=True,
    )
    nonnegative = saliency_color_scale(
        "Gradient",
        [np.array([0.2, 0.7])],
        absolute=True,
        normalized=True,
    )

    assert signed == (SALIENCY_RED_BLUE_CMAP, -1.0, 1.0)
    assert nonnegative == ("Reds", 0.0, 1.0)


def test_normalized_spectrogram_uses_one_zero_to_one_scale() -> None:
    norm, label, details = SaliencySpectrogramMapViz._build_shared_display_scale(
        [np.array([[0.05, 0.8]]), np.array([[0.2, 1.0]])],
        normalized=True,
    )

    assert norm.vmin == pytest.approx(0.0)
    assert norm.vmax == pytest.approx(1.0)
    assert label == "Normalized attribution magnitude"
    assert details["scale"] == "normalized"


def test_spectrogram_normalize_toggle_reuses_stft_and_preserves_dtype() -> None:
    raw_data = _render_data()
    preparation_cache = spectrogram_module.SaliencySpectrogramPreparationCache()
    preparation_key = (7, "run-1", raw_data.method)
    original_stft = spectrogram_module.signal.stft
    stft_inputs: list[np.ndarray] = []

    def recording_stft(values, *args, **kwargs):
        stft_inputs.append(np.asarray(values))
        return original_stft(values, *args, **kwargs)

    figures = []
    with patch(
        "XBrainLab.backend.visualization.saliency_spectrogram_map.signal.stft",
        side_effect=recording_stft,
    ):
        figures.extend(
            [
                SaliencySpectrogramMapViz(raw_data).get_plt(
                    method=raw_data.method,
                    display_normalized=normalized,
                    preparation_cache=preparation_cache,
                    preparation_key=preparation_key,
                )
                for normalized in (False, True, False)
            ]
        )

    try:
        assert len(stft_inputs) == len(raw_data.saliency_by_class)
        raw_images = [
            axis.images[0].get_array() for axis in figures[0].axes if axis.images
        ]
        normalized_images = [
            axis.images[0].get_array() for axis in figures[1].axes if axis.images
        ]
        warm_raw_images = [
            axis.images[0].get_array() for axis in figures[2].axes if axis.images
        ]
        source_scale = max(
            float(np.max(np.abs(values), initial=0.0))
            for values in raw_data.saliency_by_class.values()
        )
        for raw, normalized, warm_raw in zip(
            raw_images,
            normalized_images,
            warm_raw_images,
            strict=True,
        ):
            np.testing.assert_array_equal(raw, warm_raw)
            np.testing.assert_allclose(normalized, raw / source_scale, rtol=1e-6)
            assert raw.dtype == normalized.dtype == np.float32
    finally:
        for figure in figures:
            plt.close(figure)


def test_spectrogram_normalized_first_toggle_still_reuses_one_raw_stft() -> None:
    raw_data = _render_data()
    cache = spectrogram_module.SaliencySpectrogramPreparationCache()
    original_stft = spectrogram_module.signal.stft
    stft_calls = 0

    def recording_stft(values, *args, **kwargs):
        nonlocal stft_calls
        stft_calls += 1
        return original_stft(values, *args, **kwargs)

    figures = []
    with patch(
        "XBrainLab.backend.visualization.saliency_spectrogram_map.signal.stft",
        side_effect=recording_stft,
    ):
        figures.extend(
            [
                SaliencySpectrogramMapViz(raw_data).get_plt(
                    method=raw_data.method,
                    display_normalized=normalized,
                    preparation_cache=cache,
                    preparation_key=(7, "run-1", raw_data.method),
                )
                for normalized in (True, False, True)
            ]
        )

    try:
        assert stft_calls == len(raw_data.saliency_by_class)
    finally:
        for figure in figures:
            plt.close(figure)


def test_spectrogram_cache_clear_does_not_wait_for_active_preparation() -> None:
    cache = spectrogram_module.SaliencySpectrogramPreparationCache()
    started = threading.Event()
    release = threading.Event()
    prepared = spectrogram_module._PreparedSpectrogram(classes=(), diagnostics=())

    def prepare():
        started.set()
        assert release.wait(timeout=2.0)
        return prepared

    worker = threading.Thread(
        target=lambda: cache.get_or_prepare(
            key="run-1",
            normalized=False,
            raw_sources=(np.ones((1,), dtype=np.float32),),
            prepare=prepare,
        ),
        daemon=True,
    )
    worker.start()
    assert started.wait(timeout=1.0)

    cache.clear()
    assert worker.is_alive()
    release.set()
    worker.join(timeout=2.0)

    assert not worker.is_alive()
    assert not cache._entries


def test_spectrogram_cache_single_flights_concurrent_same_key_preparation() -> None:
    cache = spectrogram_module.SaliencySpectrogramPreparationCache()
    prepared = _empty_prepared()
    prepare_started = threading.Event()
    release_prepare = threading.Event()
    prepare_calls = 0
    calls_lock = threading.Lock()

    def prepare() -> spectrogram_module._PreparedSpectrogram:
        nonlocal prepare_calls
        with calls_lock:
            prepare_calls += 1
        prepare_started.set()
        assert release_prepare.wait(timeout=2.0)
        return prepared

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [
            executor.submit(
                cache.get_or_prepare,
                key="run-1",
                normalized=False,
                raw_sources=(np.ones((1,), dtype=np.float32),),
                prepare=prepare,
            )
            for _ in range(6)
        ]
        assert prepare_started.wait(timeout=1.0)
        try:
            _wait_for_cache_waiters(cache, key="run-1", count=5)
            assert prepare_calls == 1
        finally:
            release_prepare.set()
        results = [future.result(timeout=2.0) for future in futures]

    assert all(result is prepared for result in results)


def test_spectrogram_cache_failure_reaches_waiters_and_allows_retry() -> None:
    cache = spectrogram_module.SaliencySpectrogramPreparationCache()
    prepare_started = threading.Event()
    release_failure = threading.Event()
    prepare_calls = 0
    calls_lock = threading.Lock()

    def fail_prepare() -> spectrogram_module._PreparedSpectrogram:
        nonlocal prepare_calls
        with calls_lock:
            prepare_calls += 1
        prepare_started.set()
        assert release_failure.wait(timeout=2.0)
        raise RuntimeError("STFT failed")

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(
                cache.get_or_prepare,
                key="run-1",
                normalized=False,
                raw_sources=(np.ones((1,), dtype=np.float32),),
                prepare=fail_prepare,
            )
            for _ in range(4)
        ]
        assert prepare_started.wait(timeout=1.0)
        try:
            _wait_for_cache_waiters(cache, key="run-1", count=3)
            assert prepare_calls == 1
        finally:
            release_failure.set()
        for future in futures:
            with pytest.raises(RuntimeError, match="STFT failed"):
                future.result(timeout=2.0)

    assert prepare_calls == 1
    retried = _empty_prepared()
    result = cache.get_or_prepare(
        key="run-1",
        normalized=False,
        raw_sources=(np.ones((1,), dtype=np.float32),),
        prepare=lambda: retried,
    )

    assert result is retried
    assert tuple(cache._entries) == ("run-1",)
    assert not cache._in_flight


def test_spectrogram_cache_clear_wakes_waiters_into_new_generation() -> None:
    cache = spectrogram_module.SaliencySpectrogramPreparationCache()
    stale = _empty_prepared()
    current = _empty_prepared()
    stale_prepare_started = threading.Event()
    release_stale_prepare = threading.Event()
    current_prepare_started = threading.Event()

    def prepare_stale() -> spectrogram_module._PreparedSpectrogram:
        stale_prepare_started.set()
        assert release_stale_prepare.wait(timeout=2.0)
        return stale

    def prepare_current() -> spectrogram_module._PreparedSpectrogram:
        current_prepare_started.set()
        return current

    with ThreadPoolExecutor(max_workers=2) as executor:
        stale_future = executor.submit(
            cache.get_or_prepare,
            key="run-1",
            normalized=False,
            raw_sources=(np.ones((1,), dtype=np.float32),),
            prepare=prepare_stale,
        )
        assert stale_prepare_started.wait(timeout=1.0)
        current_future = executor.submit(
            cache.get_or_prepare,
            key="run-1",
            normalized=False,
            raw_sources=(np.ones((1,), dtype=np.float32),),
            prepare=prepare_current,
        )
        _wait_for_cache_waiters(cache, key="run-1", count=1)

        cache.clear()
        try:
            assert current_prepare_started.wait(timeout=1.0)
            assert current_future.result(timeout=1.0) is current
            assert cache._entries["run-1"].raw is current
        finally:
            release_stale_prepare.set()
        assert stale_future.result(timeout=2.0) is stale

    assert cache._entries["run-1"].raw is current


def test_spectrogram_cache_evicts_least_recently_used_third_lineage() -> None:
    cache = spectrogram_module.SaliencySpectrogramPreparationCache(max_lineages=2)
    prepared = {key: _empty_prepared() for key in ("first", "second", "third")}
    raw_sources = (np.ones((1,), dtype=np.float32),)

    for key in ("first", "second"):
        assert (
            cache.get_or_prepare(
                key=key,
                normalized=False,
                raw_sources=raw_sources,
                prepare=lambda key=key: prepared[key],
            )
            is prepared[key]
        )
    assert (
        cache.get_or_prepare(
            key="first",
            normalized=False,
            raw_sources=raw_sources,
            prepare=lambda: pytest.fail("first lineage should be cached"),
        )
        is prepared["first"]
    )
    assert (
        cache.get_or_prepare(
            key="third",
            normalized=False,
            raw_sources=raw_sources,
            prepare=lambda: prepared["third"],
        )
        is prepared["third"]
    )

    assert tuple(cache._entries) == ("first", "third")
    assert len(cache._entries) == 2


def test_spectrogram_cache_does_not_retain_failed_lineages() -> None:
    cache = spectrogram_module.SaliencySpectrogramPreparationCache(max_lineages=2)

    for index in range(5):
        with pytest.raises(RuntimeError, match="failed"):
            cache.get_or_prepare(
                key=index,
                normalized=False,
                raw_sources=(np.ones((1,), dtype=np.float32),),
                prepare=lambda: (_ for _ in ()).throw(RuntimeError("failed")),
            )

    assert not cache._entries


def test_spectrogram_preparation_cache_does_not_cross_render_lineages() -> None:
    data = _render_data()
    preparation_cache = spectrogram_module.SaliencySpectrogramPreparationCache()
    original_stft = spectrogram_module.signal.stft
    stft_calls = 0

    def recording_stft(values, *args, **kwargs):
        nonlocal stft_calls
        stft_calls += 1
        return original_stft(values, *args, **kwargs)

    figures = []
    with patch(
        "XBrainLab.backend.visualization.saliency_spectrogram_map.signal.stft",
        side_effect=recording_stft,
    ):
        figures.extend(
            [
                SaliencySpectrogramMapViz(data).get_plt(
                    method=data.method,
                    preparation_cache=preparation_cache,
                    preparation_key=(generation, "run-1", data.method),
                )
                for generation in (7, 8)
            ]
        )

    try:
        assert stft_calls == 2 * len(data.saliency_by_class)
    finally:
        for figure in figures:
            plt.close(figure)
