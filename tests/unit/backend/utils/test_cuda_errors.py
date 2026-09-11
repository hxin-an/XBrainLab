from types import SimpleNamespace

import pytest
from torch import OutOfMemoryError

from XBrainLab.backend.utils.cuda_errors import is_cuda_oom_error, release_cuda_cache


def test_is_cuda_oom_error_recognizes_typed_and_message_failures():
    assert is_cuda_oom_error(OutOfMemoryError("unrelated detail"))
    assert is_cuda_oom_error(RuntimeError("CUDA out of memory while allocating"))
    assert not is_cuda_oom_error(RuntimeError("CUDA driver is unavailable"))


def test_release_cuda_cache_only_releases_when_available():
    calls: list[str] = []

    available = SimpleNamespace(
        cuda=SimpleNamespace(
            is_available=lambda: True,
            empty_cache=lambda: calls.append("released"),
        )
    )
    unavailable = SimpleNamespace(
        cuda=SimpleNamespace(
            is_available=lambda: False,
            empty_cache=lambda: calls.append("unexpected"),
        )
    )

    release_cuda_cache(available)
    release_cuda_cache(unavailable)

    assert calls == ["released"]


@pytest.mark.parametrize(
    "cuda",
    (
        SimpleNamespace(
            is_available=lambda: (_ for _ in ()).throw(RuntimeError("probe"))
        ),
        SimpleNamespace(
            is_available=lambda: True,
            empty_cache=lambda: (_ for _ in ()).throw(RuntimeError("release")),
        ),
    ),
)
def test_release_cuda_cache_swallows_external_cuda_failures(cuda):
    release_cuda_cache(SimpleNamespace(cuda=cuda))
