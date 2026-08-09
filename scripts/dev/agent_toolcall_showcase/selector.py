"""Deterministic and exact-Granite proposal selectors for the showcase."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from XBrainLab.llm.agent.parser import CommandParser, ToolEnvelopeParseResult

from .cases import ShowcaseCase


@dataclass(frozen=True, slots=True)
class Selection:
    """One selector output and the product parser's classification."""

    owner: str
    raw_output: str
    parsed: ToolEnvelopeParseResult
    duration_ms: float
    error: str | None = None


class ProposalSelector(Protocol):
    """Select one proposed action from an assembled product prompt."""

    mode: str

    def select(
        self,
        case: ShowcaseCase,
        messages: list[dict[str, Any]],
        *,
        source_path: str,
    ) -> Selection: ...

    def metadata(self) -> dict[str, Any]: ...

    def close(self) -> None: ...


class DeterministicSelector:
    """Emit the case's strict action envelope without simulating execution."""

    mode = "deterministic"

    def select(
        self,
        case: ShowcaseCase,
        messages: list[dict[str, Any]],
        *,
        source_path: str,
    ) -> Selection:
        del messages
        started = time.monotonic()
        raw_output = json.dumps(
            {
                "tool_name": case.tool_name,
                "parameters": case.rendered_params(source_path),
            },
            ensure_ascii=True,
            separators=(",", ":"),
        )
        return Selection(
            owner="deterministic_case_selector",
            raw_output=raw_output,
            parsed=CommandParser.parse_product(raw_output),
            duration_ms=(time.monotonic() - started) * 1000,
        )

    def metadata(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "selector_id": "deterministic_case_selector",
            "selector_version": 1,
            "model_owned": False,
            "description": (
                "Built-in strict envelopes exercise product admission, verification, "
                "confirmation, execution, and presentation deterministically."
            ),
        }

    def close(self) -> None:
        return None


class GraniteSelector:
    """Use the exact product Granite model and runtime for proposal generation."""

    mode = "real_granite"

    def __init__(self, *, model_cache_dir: Path | None = None) -> None:
        # A diagnostic must not trigger a model download. The product runtime will
        # fail visibly when the pinned snapshot is unavailable in this cache.
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"

        from XBrainLab.llm.core.config import LLMConfig
        from XBrainLab.llm.core.engine import LLMEngine
        from XBrainLab.llm.core.model_catalog import (
            default_local_model_id,
            local_model_spec,
        )

        model_id = default_local_model_id()
        config_kwargs: dict[str, Any] = {
            "model_name": model_id,
            "do_sample": False,
            "temperature": 0.0,
            "max_new_tokens": 256,
            "timeout": 60,
        }
        if model_cache_dir is not None:
            config_kwargs["cache_dir"] = str(model_cache_dir.resolve())
        self._config = LLMConfig(**config_kwargs)
        self._engine = LLMEngine(self._config)
        self._engine.load_model()
        spec = local_model_spec(model_id)
        self._metadata = {
            "mode": self.mode,
            "selector_id": "ibm_granite_product_runtime",
            "selector_version": 1,
            "model_owned": True,
            "model_id": model_id,
            "revision": spec.revision if spec is not None else None,
            "device": self._config.device,
            "offline": True,
            "silent_fallback": False,
        }

    def select(
        self,
        case: ShowcaseCase,
        messages: list[dict[str, Any]],
        *,
        source_path: str,
    ) -> Selection:
        del case, source_path
        from XBrainLab.llm.core.generation import GenerationProfile

        started = time.monotonic()
        try:
            raw_output = "".join(
                self._engine.generate_stream(
                    messages,
                    profile=GenerationProfile.STRUCTURED_DECISION,
                )
            ).strip()
            error = None
        except Exception as exc:  # Product parser still receives no invented action.
            raw_output = ""
            error = f"{type(exc).__name__}: {exc}"
        return Selection(
            owner="ibm_granite_product_runtime",
            raw_output=raw_output,
            parsed=CommandParser.parse_product(raw_output),
            duration_ms=(time.monotonic() - started) * 1000,
            error=error,
        )

    def metadata(self) -> dict[str, Any]:
        return dict(self._metadata)

    def close(self) -> None:
        self._engine.close()
