"""Shared saliency method policy for ApplicationService and UI surfaces."""

from __future__ import annotations

import math
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
# This bounds request amplification independently of runtime telemetry. The
# shape- and device-aware resource admission applies the tighter effective cap.
MIN_SALIENCY_NT_SAMPLES = 1
MAX_SALIENCY_NT_SAMPLES = 1_024
MIN_SALIENCY_NT_SAMPLES_BATCH_SIZE = 1
MAX_SALIENCY_NT_SAMPLES_BATCH_SIZE = MAX_SALIENCY_NT_SAMPLES
ADVANCED_SALIENCY_METHODS = tuple(supported_saliency_methods)
RECOMMENDED_SALIENCY_METHODS = tuple(recommended_saliency_methods)
ALL_SALIENCY_METHODS = tuple(all_saliency_methods)
_SALIENCY_NOISE_PARAM_NAMES = frozenset(DEFAULT_ADVANCED_SALIENCY_PARAMS)
_SALIENCY_TOP_LEVEL_NAMES = frozenset(
    {
        "method",
        "profile",
        "methods",
        *_SALIENCY_NOISE_PARAM_NAMES,
        *ADVANCED_SALIENCY_METHODS,
    }
)


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
    raise ValueError(f"Unsupported saliency method: {method_name}")


def is_recommended_saliency_method(method_name: str) -> bool:
    """Return whether a method belongs to the recommended baseline profile."""
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


def saliency_command_params_from_configured(
    params: Mapping[str, Any],
) -> dict[str, Any]:
    """Convert authoritative stored params back to the public command shape."""
    raw = dict(params)
    if "_methods" not in raw and "_profile" not in raw:
        return raw

    selected_methods = _validated_saliency_methods(raw.get("_methods"))
    command_params: dict[str, Any] = {"methods": selected_methods}
    profile = raw.get("_profile")
    if profile is not None:
        command_params["profile"] = profile
    for method in selected_methods:
        if method not in ADVANCED_SALIENCY_METHODS:
            continue
        method_params = raw.get(method)
        if isinstance(method_params, Mapping):
            command_params[method] = dict(method_params)
    return command_params


def normalize_saliency_params(
    method: str | None,
    params: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], str | None]:
    """Normalize agent/UI-friendly saliency args to evaluator-required keys."""
    raw = dict(params or {})
    unknown_names = sorted(set(raw).difference(_SALIENCY_TOP_LEVEL_NAMES))
    if unknown_names:
        raise ValueError(
            f"Unsupported saliency parameter: {unknown_names[0]}",
        )

    embedded_method = raw.pop("method", None)
    if method is not None and embedded_method is not None and method != embedded_method:
        raise ValueError("Conflicting saliency methods were requested.")
    requested_method = _optional_method(embedded_method if embedded_method else method)
    if requested_method is not None and requested_method not in ALL_SALIENCY_METHODS:
        raise ValueError(f"Unsupported saliency method: {requested_method}")

    profile_value = raw.pop("profile", "")
    if profile_value is not None and not isinstance(profile_value, str):
        raise ValueError("Saliency profile must be a string.")
    profile = str(profile_value or "").strip().lower()
    if profile not in {"", "recommended", "advanced"}:
        raise ValueError(f"Unsupported saliency profile: {profile}")

    explicit_methods = _validated_saliency_methods(raw.pop("methods", None))
    configured_method_keys = [key for key in ADVANCED_SALIENCY_METHODS if key in raw]
    configured_params: dict[str, dict[str, Any]] = {}
    for key in configured_method_keys:
        value = raw.pop(key)
        if not isinstance(value, Mapping):
            raise ValueError(f"Saliency parameters for {key} must be an object.")
        configured_params[key] = _validated_noise_params(value)

    flat_params = {
        key: raw.pop(key) for key in tuple(raw) if key in _SALIENCY_NOISE_PARAM_NAMES
    }
    flat_params = _validated_noise_params(flat_params)
    normalized: dict[str, Any] = {
        key: dict(DEFAULT_ADVANCED_SALIENCY_PARAMS) for key in ADVANCED_SALIENCY_METHODS
    }
    for key, values in configured_params.items():
        normalized[key].update(values)

    selected_methods = select_saliency_methods(
        requested_method=requested_method,
        profile=profile,
        explicit_methods=explicit_methods,
        configured_method_keys=configured_method_keys,
    )
    if requested_method is not None and requested_method not in selected_methods:
        raise ValueError("Saliency method/profile conflict.")
    if profile == "recommended" and selected_methods != list(
        RECOMMENDED_SALIENCY_METHODS
    ):
        raise ValueError("Saliency method/profile conflict.")
    if profile == "advanced" and any(
        method not in ADVANCED_SALIENCY_METHODS for method in selected_methods
    ):
        raise ValueError("Saliency method/profile conflict.")
    if flat_params:
        flat_targets = [
            selected
            for selected in selected_methods
            if selected in ADVANCED_SALIENCY_METHODS
        ]
        if len(flat_targets) != 1 or len(selected_methods) != 1:
            if requested_method in RECOMMENDED_SALIENCY_METHODS:
                raise ValueError(
                    f"{requested_method} does not accept noise parameters.",
                )
            raise ValueError(
                "Noise parameters require exactly one advanced saliency method.",
            )
        normalized[flat_targets[0]].update(flat_params)

    unselected_configurations = set(configured_method_keys).difference(
        selected_methods,
    )
    if unselected_configurations:
        name = sorted(unselected_configurations)[0]
        raise ValueError(
            f"Saliency parameters were provided for unselected method {name}."
        )

    normalized["_methods"] = selected_methods
    if profile:
        normalized["_profile"] = profile
    return normalized, requested_method


def _optional_method(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Saliency method must be a string.")
    return value.strip() or None


def _validated_saliency_methods(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        raise ValueError("Saliency methods must be a string or list of strings.")

    methods: list[str] = []
    for item in items:
        method = _optional_method(item)
        if method is None or method not in ALL_SALIENCY_METHODS:
            raise ValueError(f"Unsupported saliency method: {method or item}")
        if method not in methods:
            methods.append(method)
    if not methods:
        raise ValueError("Select at least one saliency method.")
    return methods


def _validated_noise_params(params: Mapping[str, Any]) -> dict[str, Any]:
    unknown_names = sorted(set(params).difference(_SALIENCY_NOISE_PARAM_NAMES))
    if unknown_names:
        raise ValueError(
            f"Unsupported saliency parameter: {unknown_names[0]}",
        )

    validated: dict[str, Any] = {}
    for key, value in params.items():
        normalized_value = value
        if key == "nt_samples":
            if type(value) is not int or value < MIN_SALIENCY_NT_SAMPLES:
                raise ValueError("nt_samples must be a positive integer.")
            if value > MAX_SALIENCY_NT_SAMPLES:
                raise ValueError(
                    f"nt_samples must not exceed {MAX_SALIENCY_NT_SAMPLES}.",
                )
        elif key == "nt_samples_batch_size":
            if value is not None and (
                type(value) is not int or value < MIN_SALIENCY_NT_SAMPLES_BATCH_SIZE
            ):
                raise ValueError(
                    "nt_samples_batch_size must be a positive integer or null.",
                )
            if value is not None and value > MAX_SALIENCY_NT_SAMPLES_BATCH_SIZE:
                raise ValueError(
                    "nt_samples_batch_size must not exceed "
                    f"{MAX_SALIENCY_NT_SAMPLES_BATCH_SIZE}.",
                )
        elif key == "stdevs":
            if (
                type(value) not in {int, float}
                or not math.isfinite(float(value))
                or value < 0
            ):
                raise ValueError("stdevs must be a finite non-negative number.")
            normalized_value = float(value)
        validated[key] = normalized_value
    return validated


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
