"""Resource-admission regressions for local Granite model materialization."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.backend.application.errors import (
    PreconditionError,
)
from XBrainLab.backend.application.resource_guard import (
    ResourceChecker,
)
from XBrainLab.llm.core.backends.local import LocalBackend
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.model_catalog import (
    BYTES_PER_GB,
    PRIMARY_LOCAL_MODEL_ID,
    local_model_spec,
)


def _runtime_modules(
    *,
    model: object | None = None,
) -> tuple[MagicMock, MagicMock, MagicMock, MagicMock]:
    torch_module = MagicMock()
    torch_module.cuda.is_available.return_value = True
    torch_module.zeros.return_value = object()

    tokenizer_loader = MagicMock(return_value=MagicMock())
    loaded_model = model or MagicMock()
    if isinstance(loaded_model, MagicMock):
        loaded_model.to.return_value = loaded_model
    model_loader = MagicMock(return_value=loaded_model)
    transformers_module = MagicMock(
        AutoTokenizer=MagicMock(from_pretrained=tokenizer_loader),
        AutoModelForCausalLM=MagicMock(from_pretrained=model_loader),
        BitsAndBytesConfig=MagicMock(),
    )
    return torch_module, transformers_module, tokenizer_loader, model_loader


def _ram_status(
    *,
    available_bytes: int | None,
) -> dict[str, int | None]:
    total = None if available_bytes is None else available_bytes * 2
    used = None if available_bytes is None else total - available_bytes
    return {
        "available_bytes": available_bytes,
        "total_bytes": total,
        "used_bytes": used,
    }


def _gpu_status(
    *,
    available_bytes: int | None,
    gpu_index: int,
) -> dict[str, object]:
    total = None if available_bytes is None else available_bytes * 2
    used = None if available_bytes is None else total - available_bytes
    return {
        "gpu_name": "Test GPU",
        "available_bytes": available_bytes,
        "total_bytes": total,
        "used_bytes": used,
        "allocated_bytes": 0,
        "reserved_bytes": 0,
        "gpu_index": gpu_index,
        "device_count": 4,
        "reason": None if available_bytes is not None else "gpu_memory_query_failed",
        "query_error_type": None,
    }


def test_blocking_ram_admission_runs_before_any_from_pretrained(
    monkeypatch,
) -> None:
    config = LLMConfig(device="cpu")
    backend = LocalBackend(config)
    torch_module, transformers_module, tokenizer_loader, model_loader = (
        _runtime_modules()
    )
    monkeypatch.setattr(
        ResourceChecker,
        "get_system_ram_status",
        staticmethod(lambda: _ram_status(available_bytes=BYTES_PER_GB)),
    )

    with (
        patch.dict(
            "sys.modules",
            {"torch": torch_module, "transformers": transformers_module},
        ),
        pytest.raises(PreconditionError) as raised,
    ):
        backend.load()

    assert raised.value.recoverable is True
    assert raised.value.diagnostics["resource_preflight"]["risk_level"] == "blocking"
    tokenizer_loader.assert_not_called()
    model_loader.assert_not_called()
    assert backend.is_loaded is False


def test_safe_ram_admission_materializes_exact_granite(
    monkeypatch,
) -> None:
    config = LLMConfig(device="cpu")
    backend = LocalBackend(config)
    torch_module, transformers_module, tokenizer_loader, model_loader = (
        _runtime_modules()
    )
    monkeypatch.setattr(
        ResourceChecker,
        "get_system_ram_status",
        staticmethod(lambda: _ram_status(available_bytes=20 * BYTES_PER_GB)),
    )

    with patch.dict(
        "sys.modules",
        {"torch": torch_module, "transformers": transformers_module},
    ):
        backend.load()

    assert config.model_name == PRIMARY_LOCAL_MODEL_ID
    tokenizer_loader.assert_called_once()
    model_loader.assert_called_once()
    assert backend.is_loaded is True


def test_blocking_vram_admission_is_not_misclassified_as_cuda_oom(
    monkeypatch,
) -> None:
    config = LLMConfig(
        device="cuda:1",
        local_runtime_notice_acknowledged=True,
    )
    backend = LocalBackend(config)
    torch_module, transformers_module, tokenizer_loader, model_loader = (
        _runtime_modules()
    )
    monkeypatch.setattr(
        ResourceChecker,
        "get_gpu_vram_status",
        staticmethod(
            lambda gpu_index=None: _gpu_status(
                available_bytes=BYTES_PER_GB,
                gpu_index=1 if gpu_index is None else gpu_index,
            )
        ),
    )

    with (
        patch.dict(
            "sys.modules",
            {"torch": torch_module, "transformers": transformers_module},
        ),
        patch(
            "XBrainLab.llm.core.backends.local.release_cuda_cache",
        ) as release_cache,
        pytest.raises(PreconditionError) as raised,
    ):
        backend.load()

    assert "resource_preflight" in raised.value.diagnostics
    assert "code" not in raised.value.diagnostics
    release_cache.assert_not_called()
    tokenizer_loader.assert_not_called()
    model_loader.assert_not_called()


def test_unknown_ram_query_fails_closed_recoverably_before_load(
    monkeypatch,
) -> None:
    config = LLMConfig(device="cpu", local_runtime_notice_acknowledged=False)
    backend = LocalBackend(config)
    torch_module, transformers_module, tokenizer_loader, model_loader = (
        _runtime_modules()
    )
    monkeypatch.setattr(
        ResourceChecker,
        "get_system_ram_status",
        staticmethod(lambda: _ram_status(available_bytes=None)),
    )

    with (
        patch.dict(
            "sys.modules",
            {"torch": torch_module, "transformers": transformers_module},
        ),
        pytest.raises(PreconditionError) as raised,
    ):
        backend.load()

    assert raised.value.recoverable is True
    assert (
        raised.value.diagnostics["code"] == "local_model_load_resource_risk_unconfirmed"
    )
    assert raised.value.diagnostics["retryable"] is True
    preflight = raised.value.diagnostics["resource_preflight"]
    assert preflight["risk_level"] == "unknown"
    assert preflight["requires_confirmation"] is True
    assert "Retry" in raised.value.message
    tokenizer_loader.assert_not_called()
    model_loader.assert_not_called()


@pytest.mark.parametrize(
    ("available_bytes", "expected_risk"),
    [
        (None, "unknown"),
        (10 * BYTES_PER_GB, "warning"),
    ],
)
def test_persisted_runtime_notice_does_not_confirm_current_memory_risk(
    monkeypatch,
    available_bytes: int | None,
    expected_risk: str,
) -> None:
    config = LLMConfig(device="cpu", local_runtime_notice_acknowledged=True)
    backend = LocalBackend(config)
    torch_module, transformers_module, tokenizer_loader, model_loader = (
        _runtime_modules()
    )
    monkeypatch.setattr(
        ResourceChecker,
        "get_system_ram_status",
        staticmethod(lambda: _ram_status(available_bytes=available_bytes)),
    )

    with (
        patch.dict(
            "sys.modules",
            {"torch": torch_module, "transformers": transformers_module},
        ),
        pytest.raises(PreconditionError) as raised,
    ):
        backend.load()

    assert raised.value.recoverable is True
    assert (
        raised.value.diagnostics["code"] == "local_model_load_resource_risk_unconfirmed"
    )
    assert raised.value.diagnostics["resource_preflight"]["risk_level"] == expected_risk
    tokenizer_loader.assert_not_called()
    model_loader.assert_not_called()
    assert backend.is_loaded is False


def test_resource_risk_is_rechecked_for_every_activation(
    monkeypatch,
) -> None:
    config = LLMConfig(device="cpu", local_runtime_notice_acknowledged=True)
    torch_module, transformers_module, tokenizer_loader, model_loader = (
        _runtime_modules()
    )
    query_count = 0

    def _query_ram() -> dict[str, int | None]:
        nonlocal query_count
        query_count += 1
        return _ram_status(available_bytes=10 * BYTES_PER_GB)

    monkeypatch.setattr(
        ResourceChecker,
        "get_system_ram_status",
        staticmethod(_query_ram),
    )

    with patch.dict(
        "sys.modules",
        {"torch": torch_module, "transformers": transformers_module},
    ):
        for _activation in range(2):
            with pytest.raises(PreconditionError) as raised:
                LocalBackend(config).load()
            assert (
                raised.value.diagnostics["resource_preflight"]["risk_level"]
                == "warning"
            )

    assert query_count == 2
    tokenizer_loader.assert_not_called()
    model_loader.assert_not_called()


def test_cuda_admission_queries_the_selected_device(
    monkeypatch,
) -> None:
    config = LLMConfig(device="cuda:2")
    backend = LocalBackend(config)
    loaded_model = MagicMock()
    loaded_model.to.return_value = loaded_model
    torch_module, transformers_module, _, _ = _runtime_modules(model=loaded_model)
    queried_devices: list[int | None] = []

    def _gpu_query(gpu_index: int | None = None) -> dict[str, object]:
        queried_devices.append(gpu_index)
        return _gpu_status(
            available_bytes=20 * BYTES_PER_GB,
            gpu_index=2 if gpu_index is None else gpu_index,
        )

    monkeypatch.setattr(
        ResourceChecker,
        "get_gpu_vram_status",
        staticmethod(_gpu_query),
    )

    with patch.dict(
        "sys.modules",
        {"torch": torch_module, "transformers": transformers_module},
    ):
        backend.load()

    assert queried_devices == [2]
    torch_module.zeros.assert_called_once_with(1, device="cuda:2")
    loaded_model.to.assert_called_once_with("cuda:2")


def test_cuda_oom_releases_partial_load_and_raises_recoverable_failure(
    monkeypatch,
) -> None:
    config = LLMConfig(
        device="cuda:0",
        local_runtime_notice_acknowledged=True,
    )
    backend = LocalBackend(config)
    loaded_model = MagicMock()
    loaded_model.to.side_effect = RuntimeError("CUDA out of memory")
    torch_module, transformers_module, tokenizer_loader, model_loader = (
        _runtime_modules(model=loaded_model)
    )
    monkeypatch.setattr(
        ResourceChecker,
        "get_gpu_vram_status",
        staticmethod(
            lambda gpu_index=None: _gpu_status(
                available_bytes=20 * BYTES_PER_GB,
                gpu_index=0 if gpu_index is None else gpu_index,
            )
        ),
    )

    with (
        patch.dict(
            "sys.modules",
            {"torch": torch_module, "transformers": transformers_module},
        ),
        patch(
            "XBrainLab.llm.core.backends.local.release_cuda_cache",
        ) as release_cache,
        patch("XBrainLab.llm.core.backends.local.gc.collect") as collect,
        pytest.raises(PreconditionError) as raised,
    ):
        backend.load()

    assert raised.value.recoverable is True
    assert raised.value.diagnostics["code"] == "local_model_load_cuda_oom"
    assert "GPU memory" in raised.value.message
    tokenizer_loader.assert_called_once()
    model_loader.assert_called_once()
    assert backend.model is None
    assert backend.tokenizer is None
    assert backend.is_loaded is False
    collect.assert_called_once()
    release_cache.assert_called_once()


def test_catalog_estimate_drives_selected_device_admission() -> None:
    spec = local_model_spec(PRIMARY_LOCAL_MODEL_ID)

    assert spec is not None
    assert spec.estimated_vram_gb * BYTES_PER_GB == 8 * BYTES_PER_GB
