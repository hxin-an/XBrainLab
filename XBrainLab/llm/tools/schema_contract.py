"""Prompt-facing tool schema helpers for local tool-call planning."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from XBrainLab.llm.tools.base import BaseTool

LEGACY_COMPATIBILITY_TOOLS: dict[str, str] = {
    "load_data": (
        "Legacy compatibility path for direct file loading. Prefer "
        "scan_source -> preview_interpretation -> validate_interpretation -> "
        "apply_interpretation for new data entry workflows."
    ),
    "attach_labels": (
        "Legacy compatibility path for already-loaded data. Prefer Data "
        "Interpretation preview choices for label/event metadata."
    ),
}

TOOL_TAXONOMY: dict[str, str] = {
    "list_files": "Discovery",
    "scan_source": "Data Interpretation",
    "preview_interpretation": "Data Interpretation",
    "validate_interpretation": "Data Interpretation",
    "apply_interpretation": "Data Interpretation",
    "save_interpretation_recipe": "Data Interpretation",
    "reload_interpretation_recipe": "Data Interpretation",
    "load_data": "Legacy Compatibility",
    "attach_labels": "Legacy Compatibility",
    "apply_standard_preprocess": "Data Transform",
    "apply_bandpass_filter": "Data Transform",
    "apply_notch_filter": "Data Transform",
    "resample_data": "Data Transform",
    "normalize_data": "Data Transform",
    "set_reference": "Data Transform",
    "select_channels": "Data Transform",
    "set_montage": "Metadata Resolution",
    "epoch_data": "Experiment Setup",
    "generate_dataset": "Experiment Setup",
    "set_model": "Experiment Setup",
    "configure_training": "Experiment Setup",
    "start_training": "Execution",
    "evaluate": "Execution",
    "visualize": "Execution",
    "saliency": "Execution",
    "clear_dataset": "Lifecycle",
    "query_state": "Lifecycle",
    "get_dataset_info": "Lifecycle",
    "switch_panel": "UI Routing",
}


def tool_contract_for_llm(tool: BaseTool) -> dict[str, Any]:
    """Return a compact, schema-constrained tool definition for the LLM."""
    payload: dict[str, Any] = {
        "name": tool.name,
        "taxonomy": TOOL_TAXONOMY.get(tool.name, "Workflow"),
        "description": tool.description,
        "parameters": strict_prompt_parameters(tool.parameters),
    }
    if tool.name in LEGACY_COMPATIBILITY_TOOLS:
        payload["legacy_compatibility"] = True
        payload["routing_note"] = LEGACY_COMPATIBILITY_TOOLS[tool.name]
    return payload


def strict_prompt_parameters(schema: dict[str, Any]) -> dict[str, Any]:
    """Normalize a JSON-like tool schema for prompt-visible tool contracts.

    The runtime verifier still validates the actual arguments. This helper
    makes the schema shown to local models explicit about object boundaries so
    the prompt resembles structured-output/function-call contracts.
    """
    normalized = deepcopy(schema)
    _normalize_object_schema(normalized)
    return normalized


def _normalize_object_schema(schema: dict[str, Any]) -> None:
    if schema.get("type") != "object":
        return

    properties = schema.get("properties")
    if isinstance(properties, dict):
        schema.setdefault("additionalProperties", False)
        for property_schema in properties.values():
            if isinstance(property_schema, dict):
                _normalize_object_schema(property_schema)
                _normalize_array_schema(property_schema)
    else:
        schema.setdefault("properties", {})
        schema.setdefault("additionalProperties", False)


def _normalize_array_schema(schema: dict[str, Any]) -> None:
    if schema.get("type") != "array":
        return
    items = schema.get("items")
    if isinstance(items, dict):
        _normalize_object_schema(items)
        _normalize_array_schema(items)
