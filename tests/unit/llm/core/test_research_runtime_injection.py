"""Explicit research configuration never changes default product admission."""

from dataclasses import replace
from functools import partial
from unittest.mock import MagicMock

import pytest

from XBrainLab.llm.core.backends.local import LocalBackend
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import LLMEngine
from XBrainLab.llm.core.model_catalog import LOCAL_MODEL_SPECS


def _config():
    return LLMConfig(model_name="research/example", device="cpu")


def _spec(**overrides):
    return replace(LOCAL_MODEL_SPECS[0], repo_id="research/example", **overrides)


def test_default_backend_still_rejects_research_model():
    with pytest.raises(RuntimeError):
        LocalBackend(_config()).load()


@pytest.mark.parametrize(
    "changes",
    [
        {"revision": "main"},
        {"repo_id": "different/model"},
        {"runtime_context_tokens": 0},
        {"preferred_cuda_dtype": "float8"},
        {"estimated_vram_gb": float("nan")},
        {"estimated_vram_gb": float("inf")},
    ],
)
def test_explicit_spec_rejects_invalid_identity_or_runtime(changes):
    with pytest.raises(ValueError):
        LocalBackend(_config(), model_spec=replace(_spec(), **changes))


def test_explicit_spec_detects_config_identity_drift():
    config = _config()
    backend = LocalBackend(config, model_spec=_spec())
    config.model_name = "different/model"
    with pytest.raises(ValueError):
        backend.load()


@pytest.mark.parametrize(
    "quantized,available,admitted",
    [
        (True, 15_738_077_184, True),
        (False, 15_738_077_184, False),
        (True, 9_000_000_000, False),
    ],
)
def test_research_quantization_uses_own_estimate_without_weakening_guard(
    monkeypatch, quantized, available, admitted
):
    import sys

    from XBrainLab.backend.application import resource_guard
    from XBrainLab.backend.application.errors import PreconditionError
    from XBrainLab.llm.core.backends import local

    native, torch = MagicMock(), MagicMock()
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "transformers", native)
    captured = []

    def preflight(*, required_memory_bytes, device):
        captured.append(required_memory_bytes)
        # Real memory-policy decisions; isolate only the hardware measurement.
        return resource_guard.check_model_load_resource_preflight(
            required_memory_bytes=required_memory_bytes, device=device
        )

    monkeypatch.setattr(local, "check_model_load_resource_preflight", preflight)
    torch.cuda.is_available.return_value = True
    torch.cuda.device_count.return_value = 1
    torch.cuda.mem_get_info.return_value = (available, 17_094_475_776)
    config = LLMConfig(
        model_name="research/example", device="cuda", load_in_4bit=quantized
    )
    spec = _spec(
        estimated_vram_gb=12.0,
        estimated_4bit_vram_gb=8.0,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype="bfloat16",
    )
    backend = LocalBackend(config, model_spec=spec)
    if not admitted:
        with pytest.raises(PreconditionError):
            backend.load()
        native.AutoModelForCausalLM.from_pretrained.assert_not_called()
    else:
        backend.load()
        kwargs = native.AutoModelForCausalLM.from_pretrained.call_args.kwargs
        assert kwargs["device_map"] == {"": "cuda"}
        assert kwargs["dtype"] is torch.bfloat16
        native.BitsAndBytesConfig.assert_called_once_with(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=False,
        )
    assert captured == [8_000_000_000 if quantized else 12_000_000_000]


def test_quantized_research_requires_explicit_memory_estimate():
    config = _config()
    config.load_in_4bit = True
    with pytest.raises(ValueError, match="4-bit"):
        LocalBackend(config, model_spec=_spec())


def test_explicit_pin_still_loads_offline_without_remote_code(monkeypatch):
    import sys

    from XBrainLab.backend.application.resource_guard import ResourcePreflightResult
    from XBrainLab.llm.core.backends import local

    native = MagicMock()
    monkeypatch.setitem(sys.modules, "torch", MagicMock())
    monkeypatch.setitem(sys.modules, "transformers", native)
    monkeypatch.setattr(
        local,
        "check_model_load_resource_preflight",
        lambda **kwargs: ResourcePreflightResult(issues=(), diagnostics={}),
    )
    backend = LocalBackend(_config(), model_spec=_spec())
    backend.load()
    for loader in (native.AutoTokenizer, native.AutoModelForCausalLM):
        args, kwargs = loader.from_pretrained.call_args
        assert args == (_spec().repo_id,)
        assert kwargs["revision"] == _spec().revision
        assert kwargs["trust_remote_code"] is False
        assert kwargs["local_files_only"] is True
    assert backend.is_loaded


def test_explicit_spec_preserves_system_but_merges_strict_user_roles():
    backend = LocalBackend(
        _config(),
        model_spec=_spec(supports_consecutive_user_roles=False),
    )
    context = (
        '{"schema":"xbrainlab.untrusted_context.v1","trust":"untrusted","items":[]}'
    )
    assert backend._process_messages_for_template(
        [
            {"role": "system", "content": "policy"},
            {"role": "user", "content": context},
            {"role": "user", "content": "exact request"},
        ]
    ) == [
        {"role": "system", "content": "policy"},
        {"role": "user", "content": context + "\n\nexact request"},
    ]


def test_template_options_are_identical_for_count_and_render():
    backend = LocalBackend(
        _config(),
        model_spec=_spec(),
        template_kwargs=(("date_string", "21 Sep 2026"),),
    )
    tokenizer = MagicMock()
    tokenizer.apply_chat_template.side_effect = [[1, 2], "frozen prompt"]
    assert backend._render_chat_template_with_token_count(tokenizer, []) == (
        "frozen prompt",
        2,
    )
    for call in tokenizer.apply_chat_template.call_args_list:
        assert call.kwargs["date_string"] == "21 Sep 2026"


def test_engine_uses_explicit_backend_without_changing_default_catalog():
    backend = MagicMock()
    backend.unload.return_value = True
    factory = MagicMock(return_value=backend)
    engine = LLMEngine(_config(), backend_factory=factory)
    engine.load_model()
    assert engine.active_backend is backend
    factory.assert_called_once_with(engine.config)
    backend.load.assert_called_once()
    assert engine.close()
    backend.unload.assert_called_once()
    test_default_backend_still_rejects_research_model()


def test_worker_frozen_settings_loader_never_reads_daily_settings(qtbot, monkeypatch):
    from XBrainLab.llm.agent.worker import AgentWorker

    def forbid_daily_read(*args, **kwargs):
        pytest.fail("Research worker read daily settings")

    monkeypatch.setattr(LLMConfig, "load_from_file", forbid_daily_read)
    frozen = _config()
    frozen.max_new_tokens = 123
    worker = AgentWorker(generation_config_loader=lambda: frozen)
    worker.engine = MagicMock(config=_config())
    worker._reload_generation_settings()
    assert worker.engine.config.max_new_tokens == 123
    worker.engine = None
    worker.deleteLater()
    qtbot.wait(0)


class _FiniteResearchBackend:
    """Replace only native model inference in the real process/engine path."""

    def __init__(self, config, *, spec):
        self.config = config
        self.spec = spec

    def load(self):
        assert self.config.model_name == self.spec.repo_id

    def generate_stream(self, messages, *, options):
        del messages
        yield self.spec.revision
        yield str(options.max_new_tokens)

    def unload(self):
        return True


def _research_engine(config, *, spec):
    return LLMEngine(
        config,
        backend_factory=partial(_FiniteResearchBackend, spec=spec),
    )


def test_worker_injection_spawns_real_process_and_closes(qtbot):
    from XBrainLab.llm.agent.runtime_state import AssistantRuntimePhase
    from XBrainLab.llm.agent.worker import AgentWorker
    from XBrainLab.llm.core.generation import GenerationProfile
    from XBrainLab.llm.core.runtime_selection import (
        AssistantRuntimeBackend,
        AssistantRuntimeLaunchSpec,
        AssistantRuntimeSelectionOutcome,
        AssistantRuntimeSettingsSnapshot,
    )

    config = _config()
    spec = _spec()
    worker = AgentWorker(engine_factory=partial(_research_engine, spec=spec))
    launch = AssistantRuntimeLaunchSpec(
        backend=AssistantRuntimeBackend.LOCAL,
        requested_backend_id="local",
        requested_model_id=spec.repo_id,
        model_id=spec.repo_id,
        outcome=AssistantRuntimeSelectionOutcome.EXACT,
        selection_detail="Local runtime ready.",
        settings=AssistantRuntimeSettingsSnapshot.from_config(config),
    )
    snapshots = []
    worker.runtime_snapshot_changed.connect(snapshots.append)
    try:
        worker.initialize_agent(launch)
        qtbot.waitUntil(lambda: worker.runtime_load_thread is None, timeout=60_000)
        assert snapshots[-1].phase is AssistantRuntimePhase.READY
        assert worker.engine is not None
        assert worker.engine.pid is not None
        assert worker.engine.active_backend is worker.engine
        assert list(
            worker.engine.generate_stream(
                [{"role": "user", "content": "probe"}],
                profile=GenerationProfile.INFORMATIONAL_TEXT,
            )
        ) == [spec.revision, str(config.max_new_tokens)]
    finally:
        if worker.engine is not None:
            assert worker.engine.close(wait_timeout=2)
            assert worker.engine.is_alive is False
            assert worker.engine.active_backend is None
        worker.deleteLater()
        qtbot.wait(0)


def test_controller_factory_keeps_real_worker_thread_lifecycle(qtbot):
    from tests.qt_lifecycle import close_controller_and_wait
    from XBrainLab.backend.study import Study
    from XBrainLab.llm.agent.controller import LLMController
    from XBrainLab.llm.agent.worker import AgentWorker

    created = []

    def factory():
        worker = AgentWorker(generation_config_loader=lambda: None)
        created.append(worker)
        return worker

    controller = LLMController(Study(), worker_factory=factory)
    try:
        assert created == [controller.worker]
        assert controller.worker.thread() is controller.worker_thread
        assert controller.worker_thread.isRunning()
    finally:
        close_controller_and_wait(controller, qtbot)
