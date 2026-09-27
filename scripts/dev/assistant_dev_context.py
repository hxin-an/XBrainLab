"""Control non-task run identifiers in DEV model input, never host admission.

This research-only projection inherits normal tool policy and state semantics.
Actual publications/captures remain recorded by the ordinary research observers;
the host still sees the original generation used for freshness checks.
"""

from __future__ import annotations

import re

from XBrainLab.llm.agent.assembler import ContextAssembler

PROJECTION_ID = "dev-state-card-nuisance-v1"
_SUBJECT_REF = re.compile(r"\[SUBJECT_REF:[0-9a-f]{12}\]")


class DevContextAssembler(ContextAssembler):
    """Pure model-facing projection; owns no readiness or execution policy."""

    @staticmethod
    def _state_card_payload(publication, **kwargs):
        payload = ContextAssembler._state_card_payload(publication, **kwargs)
        # This number is meaningful only to the host's original publication.
        payload.pop("backend_generation", None)
        progress = payload.get("progress")
        if isinstance(progress, str):
            aliases: dict[str, str] = {}

            def alias(match):
                original = match.group(0)
                if original not in aliases:
                    aliases[original] = f"[SUBJECT_REF:{len(aliases) + 1:012x}]"
                return aliases[original]

            payload["progress"] = _SUBJECT_REF.sub(alias, progress)
        return payload
