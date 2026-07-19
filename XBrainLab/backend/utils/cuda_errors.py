"""CUDA memory error helpers shared by backend services and training loops."""

from __future__ import annotations

from typing import Any

from XBrainLab.backend.utils.logger import logger


def is_cuda_oom_error(exc: BaseException) -> bool:
    """Return whether an exception represents CUDA memory exhaustion."""
    exception_type = type(exc)
    if exception_type.__name__ == "OutOfMemoryError" and exception_type.__module__ in {
        "torch",
        "torch.cuda",
    }:
        return True
    message = str(exc).lower()
    return any(
        token in message
        for token in (
            "cuda out of memory",
            "cublas_status_alloc_failed",
            "cudnn_status_alloc_failed",
            "cuda error: out of memory",
            "cuda error: memory allocation",
            "hip out of memory",
        )
    )


def release_cuda_cache(torch_module: Any) -> None:
    """Release cached CUDA memory when CUDA is available."""
    try:
        if torch_module.cuda.is_available():
            torch_module.cuda.empty_cache()
    except Exception:
        logger.debug("CUDA cache release failed", exc_info=True)
