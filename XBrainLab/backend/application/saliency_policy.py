"""Shared saliency method policy for ApplicationService and UI surfaces."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from XBrainLab.backend.saliency_methods import (
    all_saliency_methods,
    recommended_saliency_methods,
    supported_saliency_methods,
)

DEFAULT_ADVANCED_SALIENCY_PARAMS: dict[str, Any] = {
    "nt_samples": 5,
    "nt_samples_batch_size": None,
    "stdevs": 1.0,
}
ADVANCED_SALIENCY_METHODS = tuple(supported_saliency_methods)
RECOMMENDED_SALIENCY_METHODS = tuple(recommended_saliency_methods)
ALL_SALIENCY_METHODS = tuple(all_saliency_methods)


def baseline_saliency_params() -> dict[str, object]:
    """Return the default fast saliency baseline profile."""
    return {
        "profile": "recommended",
        "methods": list(RECOMMENDED_SALIENCY_METHODS),
    }


def recommended_saliency_params_for_method(method_name: str) -> dict[str, object]:
    """Return a command payload suitable for the selected saliency method."""
    if is_recommended_saliency_method(method_name):
        return baseline_saliency_params()
    if method_name in ADVANCED_SALIENCY_METHODS:
        return {
            "profile": "advanced",
            "methods": [method_name],
            method_name: dict(DEFAULT_ADVANCED_SALIENCY_PARAMS),
        }
    return baseline_saliency_params()


def is_recommended_saliency_method(method_name: str) -> bool:
    """Return whether a method belongs to the automatic baseline profile."""
    return method_name in RECOMMENDED_SALIENCY_METHODS


def selected_saliency_methods_from_params(
    params: Mapping[str, object],
) -> set[str]:
    """Extract selected saliency methods from a configured payload."""
    raw_methods = params.get("_methods") or params.get("methods")
    if isinstance(raw_methods, str):
        return {raw_methods}
    if isinstance(raw_methods, (list, tuple, set)):
        return {str(item) for item in raw_methods}
    return {
        method
        for method in ADVANCED_SALIENCY_METHODS
        if isinstance(params.get(method), dict)
    }


def normalize_saliency_params(
    method: str | None,
    params: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], str | None]:
    """Normalize agent/UI-friendly saliency args to evaluator-required keys."""
    raw = dict(params or {})
    requested_method = str(raw.pop("method", method or "") or "").strip() or None
    profile = str(raw.pop("profile", "") or "").strip().lower()
    explicit_methods = normalize_saliency_methods(raw.pop("methods", None))
    configured_method_keys = [
        key for key in ADVANCED_SALIENCY_METHODS if isinstance(raw.get(key), dict)
    ]
    flat_params: dict[str, Any] = {}
    normalized: dict[str, Any] = {
        key: dict(DEFAULT_ADVANCED_SALIENCY_PARAMS) for key in ADVANCED_SALIENCY_METHODS
    }
    for key, value in raw.items():
        if key in ADVANCED_SALIENCY_METHODS and isinstance(value, dict):
            normalized[key].update(value)
        elif key not in ADVANCED_SALIENCY_METHODS:
            flat_params[key] = value
    if flat_params:
        for key in ADVANCED_SALIENCY_METHODS:
            normalized[key].update(flat_params)

    normalized["_methods"] = select_saliency_methods(
        requested_method=requested_method,
        profile=profile,
        explicit_methods=explicit_methods,
        configured_method_keys=configured_method_keys,
    )
    if profile:
        normalized["_profile"] = profile
    return normalized, requested_method


def normalize_saliency_methods(value: Any) -> list[str]:
    """Return valid saliency methods from a loose string/list payload."""
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        return []

    methods = []
    for item in items:
        method = str(item).strip()
        if method in ALL_SALIENCY_METHODS and method not in methods:
            methods.append(method)
    return methods


def select_saliency_methods(
    *,
    requested_method: str | None,
    profile: str,
    explicit_methods: list[str],
    configured_method_keys: list[str],
) -> list[str]:
    """Resolve the final saliency method set for a command payload."""
    if explicit_methods:
        return explicit_methods
    if profile == "recommended":
        return list(RECOMMENDED_SALIENCY_METHODS)
    if profile == "advanced":
        return configured_method_keys or list(ADVANCED_SALIENCY_METHODS)
    if requested_method in ALL_SALIENCY_METHODS:
        return [requested_method]
    if configured_method_keys:
        return configured_method_keys
    return list(ALL_SALIENCY_METHODS)
