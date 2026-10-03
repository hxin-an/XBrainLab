"""Archived candidates retain their complete input on the reliable runner."""

import hashlib
import importlib.machinery
import importlib.util
from pathlib import Path

import pytest

from scripts.dev.assistant_dev_context import DEV_PROMPT_MODEL_IDS, DevContextAssembler
from scripts.dev.assistant_dev_profiles import FROZEN_PROFILES, build_dev_context
from XBrainLab.backend.application import get_application_service
from XBrainLab.backend.study import Study
from XBrainLab.llm.tools import get_all_tools
from XBrainLab.llm.tools.tool_registry import ToolRegistry


def registry():
    result = ToolRegistry()
    for tool in get_all_tools():
        result.register(tool)
    return result


def archived_class(candidate):
    """Load the sealed original directly, without the runtime factory adapter."""
    path = (
        Path(__file__).resolve().parents[3]
        / "scripts/dev/frozen_dev_contexts"
        / f"round_{candidate:02}.py.txt"
    )
    assert (
        hashlib.sha256(path.read_bytes()).hexdigest() == FROZEN_PROFILES[candidate][1]
    )
    loader = importlib.machinery.SourceFileLoader(
        f"original_round_{candidate}", str(path)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.DevContextAssembler


@pytest.fixture
def live_study():
    study = Study()
    service = get_application_service(study)
    try:
        yield study, service
    finally:
        service.close()


@pytest.mark.parametrize("model_id", DEV_PROMPT_MODEL_IDS)
def test_default_keeps_selected_profile_even_with_candidate_metadata(
    live_study, model_id
):
    study, service = live_study
    kwargs = {"model_id": model_id, "application_runtime": service}
    original = DevContextAssembler(registry(), study, **kwargs)
    migrated = build_dev_context(registry(), study, candidate_index=1, **kwargs)
    history = [{"role": "user", "content": "Open Import EEG Data."}]
    assert original.get_messages(history) == migrated.get_messages(history)


@pytest.mark.parametrize("candidate", range(1, 6))
@pytest.mark.parametrize("model_id", DEV_PROMPT_MODEL_IDS)
def test_all_frozen_candidates_preserve_normal_and_recovery_inputs(
    live_study, candidate, model_id
):
    study, service = live_study
    original_kwargs = {"application_runtime": service}
    if candidate != 1:
        original_kwargs["model_id"] = model_id
    original = archived_class(candidate)(registry(), study, **original_kwargs)
    migrated = build_dev_context(
        registry(),
        study,
        model_id=model_id,
        application_runtime=service,
        candidate_index=candidate,
        prompt_profile="frozen-dev-round",
    )
    history = [{"role": "user", "content": "Open Import EEG Data."}]
    for assembler in (original, migrated):
        assembler.add_context("A reference is not authorization for this request.")
    for recovery in (False, True):
        assert original.get_messages(
            history, format_recovery=recovery
        ) == migrated.get_messages(history, format_recovery=recovery)
        assert original.latest_tool_publication == migrated.latest_tool_publication
        assert original.rag_allowed_tool_names() == migrated.rag_allowed_tool_names()


@pytest.mark.parametrize("candidate", range(1, 6))
@pytest.mark.parametrize("model_id", DEV_PROMPT_MODEL_IDS)
def test_frozen_catalog_ablation_preserves_permission_rag_state_and_examples(
    live_study, candidate, model_id
):
    study, service = live_study
    full, off = [
        build_dev_context(
            registry(),
            study,
            model_id=model_id,
            application_runtime=service,
            candidate_index=candidate,
            prompt_profile="frozen-dev-round",
            tool_filter_enabled=enabled,
        )
        for enabled in (True, False)
    ]
    history = [{"role": "user", "content": "Open Import EEG Data."}]
    normal, expanded = [assembler.get_messages(history) for assembler in (full, off)]
    assert normal[1:] == expanded[1:]
    assert full.latest_tool_publication == off.latest_tool_publication
    assert full.rag_allowed_tool_names() == off.rag_allowed_tool_names()
    assert full._decision_instructions() == off._decision_instructions()
    assert "apply_bandpass_filter" not in off.latest_tool_publication.tool_names
    assert off.latest_tool_publication.blocked_reason("apply_bandpass_filter")
    assert "Catalog definitions do not grant availability." in expanded[0]["content"]
    assert "Callable action contract:" not in expanded[0]["content"]
    assert (
        '"name": "apply_bandpass_filter"' in expanded[0]["content"]
        or "Action: apply_bandpass_filter" in expanded[0]["content"]
    )
    if "Complete output illustrations:" in normal[0]["content"]:

        def illustration_block(content):
            return (
                content.split("Complete output illustrations:", 1)[1]
                .split("Only the listed workflow actions", 1)[0]
                .split("Catalog definitions do not grant", 1)[0]
            )

        assert illustration_block(normal[0]["content"]) == illustration_block(
            expanded[0]["content"]
        )


@pytest.mark.parametrize("candidate", [None, True, 0, 6, "1", 1.0])
def test_frozen_candidate_identity_fails_closed(candidate):
    with pytest.raises(ValueError, match="candidate"):
        build_dev_context(
            registry(),
            None,
            model_id=DEV_PROMPT_MODEL_IDS[0],
            candidate_index=candidate,
            prompt_profile="frozen-dev-round",
        )


def test_unknown_profile_and_nonboolean_ablation_fail_closed():
    with pytest.raises(ValueError, match="profile"):
        build_dev_context(
            registry(), None, model_id=DEV_PROMPT_MODEL_IDS[0], prompt_profile="unknown"
        )
    with pytest.raises(ValueError, match="boolean"):
        build_dev_context(
            registry(),
            None,
            model_id=DEV_PROMPT_MODEL_IDS[0],
            candidate_index=1,
            prompt_profile="frozen-dev-round",
            tool_filter_enabled=1,
        )


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize(
    ("model_id", "candidate"),
    [
        ("ibm-granite/granite-4.0-micro", 2),
        ("ibm-granite/granite-3.3-2b-instruct", 5),
        ("microsoft/Phi-4-mini-instruct", 5),
        ("meta-llama/Llama-3.2-3B-Instruct", 3),
        ("google/gemma-3-4b-it", 4),
    ],
)
def test_prior_selected_candidates_and_catalog_ablations_stay_identical(
    live_study, model_id, candidate, enabled
):
    study, service = live_study
    kwargs = {
        "model_id": model_id,
        "application_runtime": service,
        "tool_filter_enabled": enabled,
    }
    previous = DevContextAssembler(registry(), study, **kwargs)
    explicit = build_dev_context(
        registry(),
        study,
        **kwargs,
        candidate_index=candidate,
        prompt_profile="frozen-dev-round",
    )
    history = [{"role": "user", "content": "Open import."}]
    assert previous.get_messages(history) == explicit.get_messages(history)


def test_modified_archive_is_rejected_before_execution(monkeypatch):
    from scripts.dev.assistant_dev_profiles import _frozen_class

    _frozen_class.cache_clear()
    monkeypatch.setattr(
        Path, "read_bytes", lambda path: b"raise AssertionError('executed')"
    )
    try:
        with pytest.raises(ValueError, match="source digest mismatch"):
            build_dev_context(
                registry(),
                None,
                model_id=DEV_PROMPT_MODEL_IDS[0],
                candidate_index=1,
                prompt_profile="frozen-dev-round",
            )
    finally:
        _frozen_class.cache_clear()
