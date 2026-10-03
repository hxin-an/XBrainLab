"""Run explicitly selected, byte-frozen DEV renderers on the current engine.

The archived files are research source, not user-supplied templates. Their
original commit and byte digest are pinned here; default callers keep the
existing selected-system renderer. No backend policy or model is selected here.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from types import ModuleType

from scripts.dev.assistant_dev_context import (
    DevContextAssembler,
    validate_dev_prompt_model,
)

FROZEN_PROFILES = {
    1: (
        "d9182f1922b9e80bc4fee647ef0d3657b274f915",  # pragma: allowlist secret
        "f1a6e1986e9e5e3cdaf64406534733b9e8b320fafaac7407bb5cab133e471602",  # pragma: allowlist secret
    ),
    2: (
        "d2e679c2269c2edcd56698a0cdf30b5b332237b5",  # pragma: allowlist secret
        "30e6a6fb5ce29bbc6a752a2316c9a364f4a44d3afeac419415c4669ff1e9f194",  # pragma: allowlist secret
    ),
    3: (
        "e6d10a9f11221d3dd0ba320088bb191c65b709ac",  # pragma: allowlist secret
        "1d3b9b550a699895a6a9fead37dfd6af9bd758e484e90793741e96d4dbfa3896",  # pragma: allowlist secret
    ),
    4: (
        "7811057170307b4f93e33e6248750cb1b6e51beb",  # pragma: allowlist secret
        "174e456c4e18a07c745b487dd536f3ce7b95133af870bb9adf78ece910ccbd5e",  # pragma: allowlist secret
    ),
    5: (
        "51dd709bc8f4aefb17f0c625e8135e69bcfe901b",  # pragma: allowlist secret
        "dc5f1d5b69fcfe2d8a8a8f7b29c3e8911d18c6aa8a0bdcc372b64a35418accef",  # pragma: allowlist secret
    ),
}


class _CatalogAblation:
    """Expand definitions only; keep the original state-selected illustrations."""

    tool_filter_enabled = True
    _illustration_names = None

    def _format_tools(self, allowed_names, *, unavailable_actions=None):
        if self.tool_filter_enabled:
            return super()._format_tools(
                allowed_names, unavailable_actions=unavailable_actions
            )
        from XBrainLab.llm.tools.application_surface import AGENT_ACTION_CONTRACTS

        previous = self._illustration_names
        self._illustration_names = allowed_names
        try:
            catalog = super()._format_tools(
                sorted(AGENT_ACTION_CONTRACTS.model_tool_names()),
                unavailable_actions=unavailable_actions,
            )
        finally:
            self._illustration_names = previous
        return catalog.replace(
            "Callable action contract:", "Action contract definition:"
        ).replace(
            "These entries are informational status, not callable action contracts.",
            "These actions remain unavailable even when their definitions appear above.",
        )

    def _output_illustrations(self, allowed_names):
        return super()._output_illustrations(
            allowed_names
            if self._illustration_names is None
            else self._illustration_names
        )


@lru_cache(maxsize=5)
def _frozen_class(candidate_index):
    path = (
        Path(__file__).with_name("frozen_dev_contexts")
        / f"round_{candidate_index:02}.py.txt"
    )
    source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != FROZEN_PROFILES[candidate_index][1]:
        raise ValueError(f"Frozen candidate {candidate_index} source digest mismatch")
    module = ModuleType(f"xbrainlab_frozen_dev_round_{candidate_index}")
    # Execute only these verified repository bytes, never an arbitrary path,
    # external template, or a timestamp-matched bytecode cache.
    exec(compile(source, str(path), "exec"), module.__dict__)  # noqa: S102
    return type(
        f"FrozenRound{candidate_index}Context",
        (_CatalogAblation, module.DevContextAssembler),
        {},
    )


def build_dev_context(
    registry,
    study,
    *,
    model_id,
    application_runtime=None,
    tool_filter_enabled=True,
    candidate_index=None,
    prompt_profile=None,
):
    """Use historical presentation only with the explicit frozen-round opt-in."""
    validate_dev_prompt_model(model_id)
    if type(tool_filter_enabled) is not bool:
        raise ValueError("Tool catalog filter must be boolean")
    if prompt_profile is None:
        return DevContextAssembler(
            registry,
            study,
            model_id=model_id,
            application_runtime=application_runtime,
            tool_filter_enabled=tool_filter_enabled,
        )
    if prompt_profile != "frozen-dev-round":
        raise ValueError(f"Unsupported prompt profile: {prompt_profile!r}")
    if type(candidate_index) is not int or candidate_index not in FROZEN_PROFILES:
        raise ValueError("Frozen candidate index must be an integer from 1 through 5")
    kwargs = {"application_runtime": application_runtime}
    if candidate_index != 1:
        kwargs["model_id"] = model_id
    assembler = _frozen_class(candidate_index)(registry, study, **kwargs)
    assembler.prompt_profile = prompt_profile
    assembler.candidate_index = candidate_index
    assembler.tool_filter_enabled = tool_filter_enabled
    if not tool_filter_enabled:
        assembler._TOOL_BLOCK_TEMPLATE = assembler._TOOL_BLOCK_TEMPLATE.replace(
            "{availability_note}",
            "Catalog definitions do not grant availability. Unavailable Action "
            "Reference and backend state still determine whether an action is enabled.",
        )
    return assembler
