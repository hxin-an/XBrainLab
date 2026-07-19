"""Fail-closed integrity manifests for persisted saliency payload arrays."""

from __future__ import annotations

import math
import platform
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from importlib.metadata import PackageNotFoundError, version
from typing import Final, NoReturn, cast

import numpy as np
import torch

from XBrainLab import __version__ as xbrainlab_version

from .saliency_provenance import (
    SaliencyArtifactContext,
    SaliencyContextError,
    canonicalize_saliency_identity,
    describe_saliency_array,
    fingerprint_saliency_identity,
)

SALIENCY_ARTIFACT_MANIFEST_SCHEMA_VERSION: Final = 1
SALIENCY_PAYLOAD_IDENTITY_SCHEMA_VERSION: Final = 1
SALIENCY_RUNTIME_CONTRACT_SCHEMA_VERSION: Final = 1

SALIENCY_METHOD_STORE_NAMES: Final[dict[str, str]] = {
    "Gradient": "gradient",
    "Gradient * Input": "gradient_input",
    "SmoothGrad": "smoothgrad",
    "SmoothGrad_Squared": "smoothgrad_sq",
    "VarGrad": "vargrad",
}
_SALIENCY_METHOD_ORDER: Final = tuple(SALIENCY_METHOD_STORE_NAMES)
_NOISE_METHODS: Final = frozenset({"SmoothGrad", "SmoothGrad_Squared", "VarGrad"})
_NOISE_DEFAULTS: Final[dict[str, object]] = {
    "nt_samples": 5,
    "nt_samples_batch_size": None,
    "stdevs": 1.0,
}
_MANIFEST_KEYS: Final = frozenset(
    {
        "schema_version",
        "payload_identity_schema_version",
        "hash_algorithm",
        "logical_order",
        "context_fingerprint",
        "producer_fingerprint",
        "runtime_contract",
        "methods",
        "method_parameters",
        "noise_seeds",
        "entries",
        "manifest_sha256",
    }
)


class SaliencyIntegrityReason(str, Enum):
    """Machine-readable reasons why saliency must not be published."""

    MISSING_MANIFEST = "missing_manifest"
    UNSUPPORTED_SCHEMA = "unsupported_schema"
    MALFORMED_MANIFEST = "malformed_manifest"
    MANIFEST_TAMPERED = "manifest_tampered"
    PAYLOAD_MUTATION = "payload_mutation"
    METHOD_MISMATCH = "method_mismatch"
    PARAMETER_MISMATCH = "parameter_mismatch"
    TARGET_MISMATCH = "target_mismatch"
    NOISE_SEED_MISMATCH = "noise_seed_mismatch"
    PRODUCER_MISMATCH = "producer_mismatch"
    RUNTIME_CONTRACT_MISMATCH = "runtime_contract_mismatch"
    PARTIAL_COVERAGE = "partial_coverage"
    NON_FINITE_PAYLOAD = "non_finite_payload"
    UNSUPPORTED_DTYPE = "unsupported_dtype"
    AMBIGUOUS_IDENTITY = "ambiguous_identity"


@dataclass(frozen=True, slots=True)
class SaliencyIntegrityDiagnostic:
    """One bounded diagnostic attached to an integrity failure."""

    field: str
    message: str
    method: str | None = None
    class_index: int | None = None
    expected: object | None = None
    actual: object | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "field": self.field,
            "message": self.message,
        }
        if self.method is not None:
            payload["method"] = self.method
        if self.class_index is not None:
            payload["class_index"] = self.class_index
        if self.expected is not None:
            payload["expected"] = self.expected
        if self.actual is not None:
            payload["actual"] = self.actual
        return payload


class SaliencyArtifactIntegrityError(SaliencyContextError):
    """Typed integrity failure that keeps metrics readable and saliency closed."""

    def __init__(
        self,
        reason: SaliencyIntegrityReason,
        message: str,
        *,
        diagnostics: tuple[SaliencyIntegrityDiagnostic, ...] = (),
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.diagnostics = diagnostics


def _fail(
    reason: SaliencyIntegrityReason,
    message: str,
    *,
    diagnostics: tuple[SaliencyIntegrityDiagnostic, ...] = (),
) -> NoReturn:
    raise SaliencyArtifactIntegrityError(
        reason,
        message,
        diagnostics=diagnostics,
    )


def _package_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "unavailable"


def current_saliency_runtime_contract() -> dict[str, object]:
    """Capture the producer and library contract included in every entry hash."""
    return {
        "schema_version": SALIENCY_RUNTIME_CONTRACT_SCHEMA_VERSION,
        "producer": (
            "XBrainLab.backend.training.evaluator.Evaluator.evaluate_with_saliency"
        ),
        "python_version": platform.python_version(),
        "xbrainlab_version": str(xbrainlab_version),
        "numpy_version": str(np.__version__),
        "torch_version": str(torch.__version__),
        "captum_version": _package_version("captum"),
    }


def normalize_saliency_method_parameters(
    method: str,
    parameters: object,
) -> dict[str, object]:
    """Return the exact effective parameter contract for one method."""
    if method not in SALIENCY_METHOD_STORE_NAMES:
        _fail(
            SaliencyIntegrityReason.METHOD_MISMATCH,
            f"Unsupported saliency method {method!r}.",
        )
    if parameters is None:
        raw: Mapping[object, object] = {}
    elif type(parameters) is dict:
        raw = parameters
    else:
        _fail(
            SaliencyIntegrityReason.PARAMETER_MISMATCH,
            f"Saliency parameters for {method} must be a mapping.",
        )

    try:
        canonicalize_saliency_identity(raw)
    except SaliencyContextError as exc:
        reason = (
            SaliencyIntegrityReason.AMBIGUOUS_IDENTITY
            if "ambiguous mapping keys" in str(exc).lower()
            else SaliencyIntegrityReason.PARAMETER_MISMATCH
        )
        _fail(reason, str(exc))

    if any(not isinstance(key, str) for key in raw):
        _fail(
            SaliencyIntegrityReason.PARAMETER_MISMATCH,
            f"Saliency parameter names for {method} must be strings.",
        )
    raw_dict = cast(dict[str, object], raw)
    if method not in _NOISE_METHODS:
        if raw_dict:
            _fail(
                SaliencyIntegrityReason.PARAMETER_MISMATCH,
                f"{method} does not accept noise-tunnel parameters.",
            )
        return {}

    unknown = set(raw_dict) - set(_NOISE_DEFAULTS)
    if unknown:
        _fail(
            SaliencyIntegrityReason.PARAMETER_MISMATCH,
            f"Unsupported {method} parameter(s): {', '.join(sorted(unknown))}.",
        )
    normalized = {**_NOISE_DEFAULTS, **raw_dict}
    nt_samples = normalized["nt_samples"]
    batch_size = normalized["nt_samples_batch_size"]
    stdevs = normalized["stdevs"]
    if isinstance(nt_samples, bool) or not isinstance(nt_samples, int):
        _fail(
            SaliencyIntegrityReason.PARAMETER_MISMATCH,
            f"{method} nt_samples must be a positive integer.",
        )
    if nt_samples <= 0:
        _fail(
            SaliencyIntegrityReason.PARAMETER_MISMATCH,
            f"{method} nt_samples must be a positive integer.",
        )
    if batch_size is not None and (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or batch_size <= 0
    ):
        _fail(
            SaliencyIntegrityReason.PARAMETER_MISMATCH,
            f"{method} nt_samples_batch_size must be positive or null.",
        )
    if isinstance(stdevs, bool) or not isinstance(stdevs, (int, float)):
        _fail(
            SaliencyIntegrityReason.PARAMETER_MISMATCH,
            f"{method} stdevs must be a finite non-negative number.",
        )
    normalized_stdevs = float(stdevs)
    if not math.isfinite(normalized_stdevs) or normalized_stdevs < 0:
        _fail(
            SaliencyIntegrityReason.PARAMETER_MISMATCH,
            f"{method} stdevs must be a finite non-negative number.",
        )
    return {
        "nt_samples": nt_samples,
        "nt_samples_batch_size": batch_size,
        "stdevs": normalized_stdevs,
    }


def _active_method_stores(
    stores: Mapping[str, object],
) -> dict[str, Mapping[object, object]]:
    active: dict[str, Mapping[object, object]] = {}
    for method in _SALIENCY_METHOD_ORDER:
        value = stores.get(method, {})
        if type(value) is not dict:
            _fail(
                SaliencyIntegrityReason.PARTIAL_COVERAGE,
                f"{method} saliency payload must be a class-indexed mapping.",
            )
        if value:
            active[method] = value
    return active


def _normalized_contracts(
    methods: tuple[str, ...],
    method_parameters: object,
    noise_seeds: object,
) -> tuple[dict[str, dict[str, object]], dict[str, int]]:
    if type(method_parameters) is not dict:
        _fail(
            SaliencyIntegrityReason.PARAMETER_MISMATCH,
            "Saliency method parameters are missing or malformed.",
        )
    if type(noise_seeds) is not dict:
        _fail(
            SaliencyIntegrityReason.NOISE_SEED_MISMATCH,
            "Saliency noise seed contract is missing or malformed.",
        )
    if any(not isinstance(key, str) for key in method_parameters):
        _fail(
            SaliencyIntegrityReason.PARAMETER_MISMATCH,
            "Saliency method parameter keys must be strings.",
        )
    if any(not isinstance(key, str) for key in noise_seeds):
        _fail(
            SaliencyIntegrityReason.NOISE_SEED_MISMATCH,
            "Saliency noise seed keys must be strings.",
        )
    parameters_dict = cast(dict[str, object], method_parameters)
    seeds_dict = cast(dict[str, object], noise_seeds)
    if set(parameters_dict) != set(methods):
        _fail(
            SaliencyIntegrityReason.PARAMETER_MISMATCH,
            "Saliency method parameter coverage does not match payload methods.",
        )
    expected_noise_methods = set(methods) & _NOISE_METHODS
    if set(seeds_dict) != expected_noise_methods:
        _fail(
            SaliencyIntegrityReason.NOISE_SEED_MISMATCH,
            "Saliency noise seed coverage does not match noise methods.",
        )

    normalized_parameters = {
        method: normalize_saliency_method_parameters(
            method,
            parameters_dict[method],
        )
        for method in methods
    }
    normalized_seeds: dict[str, int] = {}
    for method in methods:
        if method not in _NOISE_METHODS:
            continue
        seed = seeds_dict[method]
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**64:
            _fail(
                SaliencyIntegrityReason.NOISE_SEED_MISMATCH,
                f"{method} noise seed must be an unsigned 64-bit integer.",
            )
        normalized_seeds[method] = seed
    return normalized_parameters, normalized_seeds


def _class_payloads(
    method: str,
    store: Mapping[object, object],
    context: SaliencyArtifactContext,
) -> tuple[tuple[int, object, str, object], ...]:
    expected_indices = set(range(len(context.class_map)))
    normalized_store: dict[int, object] = {}
    for raw_key, value in store.items():
        if isinstance(raw_key, bool) or not isinstance(raw_key, (int, np.integer)):
            _fail(
                SaliencyIntegrityReason.TARGET_MISMATCH,
                f"{method} class keys must be zero-based integer targets.",
            )
        class_index = int(raw_key)
        if class_index in normalized_store:
            _fail(
                SaliencyIntegrityReason.AMBIGUOUS_IDENTITY,
                f"{method} contains ambiguous normalized class keys.",
            )
        normalized_store[class_index] = value
    if set(normalized_store) != expected_indices:
        missing = sorted(expected_indices - set(normalized_store))
        extra = sorted(set(normalized_store) - expected_indices)
        _fail(
            SaliencyIntegrityReason.PARTIAL_COVERAGE,
            f"{method} saliency does not cover every trained class.",
            diagnostics=(
                SaliencyIntegrityDiagnostic(
                    field="class_coverage",
                    message="Class coverage is incomplete or contains extra targets.",
                    method=method,
                    expected=sorted(expected_indices),
                    actual=sorted(normalized_store),
                ),
                SaliencyIntegrityDiagnostic(
                    field="missing_classes",
                    message="Missing class indices.",
                    method=method,
                    actual=missing,
                ),
                SaliencyIntegrityDiagnostic(
                    field="extra_classes",
                    message="Unexpected class indices.",
                    method=method,
                    actual=extra,
                ),
            ),
        )
    return tuple(
        (
            class_index,
            context.class_map[class_index][0],
            context.class_map[class_index][1],
            normalized_store[class_index],
        )
        for class_index in sorted(normalized_store)
    )


def _describe_payload(
    value: object,
    *,
    method: str,
    class_index: int,
) -> dict[str, object]:
    try:
        descriptor = describe_saliency_array(value, require_finite_float=True)
    except SaliencyContextError as exc:
        message = str(exc)
        lowered = message.lower()
        if "finite" in lowered:
            reason = SaliencyIntegrityReason.NON_FINITE_PAYLOAD
        elif "dtype" in lowered or "arrays or torch tensors" in lowered:
            reason = SaliencyIntegrityReason.UNSUPPORTED_DTYPE
        else:
            reason = SaliencyIntegrityReason.MALFORMED_MANIFEST
        _fail(
            reason,
            message,
            diagnostics=(
                SaliencyIntegrityDiagnostic(
                    field="payload",
                    message=message,
                    method=method,
                    class_index=class_index,
                ),
            ),
        )
    element_count = descriptor["element_count"]
    if type(element_count) is not int:
        _fail(
            SaliencyIntegrityReason.MALFORMED_MANIFEST,
            f"{method} saliency array descriptor is malformed.",
        )
    if element_count <= 0:
        _fail(
            SaliencyIntegrityReason.PARTIAL_COVERAGE,
            f"{method} saliency for class {class_index} is empty.",
        )
    return descriptor


def _manifest_core(manifest: Mapping[str, object]) -> dict[str, object]:
    return {key: manifest[key] for key in _MANIFEST_KEYS if key != "manifest_sha256"}


def build_saliency_artifact_manifest(
    stores: Mapping[str, object],
    *,
    context: SaliencyArtifactContext,
    method_parameters: object,
    noise_seeds: object,
    runtime_contract: object | None = None,
) -> dict[str, object]:
    """Build a complete manifest without materializing full attribution arrays."""
    if not isinstance(context, SaliencyArtifactContext):
        _fail(
            SaliencyIntegrityReason.PRODUCER_MISMATCH,
            "Saliency identity context is required for artifact integrity.",
        )
    active_stores = _active_method_stores(stores)
    methods = tuple(active_stores)
    if not methods:
        _fail(
            SaliencyIntegrityReason.PARTIAL_COVERAGE,
            "A saliency manifest requires at least one attribution method.",
        )
    parameters, seeds = _normalized_contracts(
        methods,
        method_parameters,
        noise_seeds,
    )
    runtime = (
        current_saliency_runtime_contract()
        if runtime_contract is None
        else runtime_contract
    )
    if type(runtime) is not dict:
        _fail(
            SaliencyIntegrityReason.RUNTIME_CONTRACT_MISMATCH,
            "Saliency runtime contract is missing or malformed.",
        )
    runtime_dict = cast(dict[str, object], runtime)
    if runtime_dict.get("schema_version") != SALIENCY_RUNTIME_CONTRACT_SCHEMA_VERSION:
        _fail(
            SaliencyIntegrityReason.RUNTIME_CONTRACT_MISMATCH,
            "Saliency runtime contract uses an unsupported schema version.",
        )
    try:
        canonical_runtime = canonicalize_saliency_identity(runtime_dict)
    except SaliencyContextError as exc:
        _fail(SaliencyIntegrityReason.RUNTIME_CONTRACT_MISMATCH, str(exc))
    if not isinstance(canonical_runtime, dict):
        _fail(
            SaliencyIntegrityReason.RUNTIME_CONTRACT_MISMATCH,
            "Saliency runtime contract is missing or malformed.",
        )

    producer_contract = {
        "context_fingerprint": context.context_fingerprint,
        "producer_fingerprint": context.producer_identity.fingerprint,
    }
    entries: list[dict[str, object]] = []
    for method, store in active_stores.items():
        for class_index, class_key, class_name, payload in _class_payloads(
            method,
            store,
            context,
        ):
            target = {
                "class_index": class_index,
                "class_key": canonicalize_saliency_identity(class_key),
                "class_name": class_name,
            }
            array = _describe_payload(
                payload,
                method=method,
                class_index=class_index,
            )
            identity_payload = {
                "schema_version": SALIENCY_PAYLOAD_IDENTITY_SCHEMA_VERSION,
                "method": method,
                "parameters": parameters[method],
                "target": target,
                "noise_seed": seeds.get(method),
                "producer_contract": producer_contract,
                "runtime_contract": canonical_runtime,
                "array": array,
            }
            entries.append(
                {
                    **identity_payload,
                    "identity_sha256": fingerprint_saliency_identity(identity_payload),
                }
            )

    manifest: dict[str, object] = {
        "schema_version": SALIENCY_ARTIFACT_MANIFEST_SCHEMA_VERSION,
        "payload_identity_schema_version": (SALIENCY_PAYLOAD_IDENTITY_SCHEMA_VERSION),
        "hash_algorithm": "sha256",
        "logical_order": "C",
        **producer_contract,
        "runtime_contract": canonical_runtime,
        "methods": list(methods),
        "method_parameters": parameters,
        "noise_seeds": seeds,
        "entries": entries,
    }
    manifest["manifest_sha256"] = fingerprint_saliency_identity(manifest)
    return manifest


def _validate_manifest_envelope(manifest: object) -> dict[str, object]:
    if manifest is None:
        _fail(
            SaliencyIntegrityReason.MISSING_MANIFEST,
            "This saliency artifact does not contain an integrity manifest.",
        )
    if type(manifest) is not dict:
        _fail(
            SaliencyIntegrityReason.MALFORMED_MANIFEST,
            "Saliency integrity manifest is malformed.",
        )
    manifest_dict = cast(dict[str, object], manifest)
    if set(manifest_dict) != _MANIFEST_KEYS:
        _fail(
            SaliencyIntegrityReason.MALFORMED_MANIFEST,
            "Saliency integrity manifest fields are incomplete or unsupported.",
        )
    version_value = manifest_dict.get("schema_version")
    identity_version = manifest_dict.get("payload_identity_schema_version")
    if (
        isinstance(version_value, bool)
        or version_value != SALIENCY_ARTIFACT_MANIFEST_SCHEMA_VERSION
        or isinstance(identity_version, bool)
        or identity_version != SALIENCY_PAYLOAD_IDENTITY_SCHEMA_VERSION
    ):
        _fail(
            SaliencyIntegrityReason.UNSUPPORTED_SCHEMA,
            "This saliency artifact uses an unsupported integrity schema.",
        )
    if (
        manifest_dict.get("hash_algorithm") != "sha256"
        or manifest_dict.get("logical_order") != "C"
    ):
        _fail(
            SaliencyIntegrityReason.UNSUPPORTED_SCHEMA,
            "This saliency artifact uses an unsupported hashing contract.",
        )
    return manifest_dict


def _entry_map(
    entries: object,
) -> dict[tuple[object, object], Mapping[str, object]]:
    if type(entries) is not list:
        _fail(
            SaliencyIntegrityReason.MALFORMED_MANIFEST,
            "Saliency manifest entries are malformed.",
        )
    result: dict[tuple[object, object], Mapping[str, object]] = {}
    entries_list = cast(list[object], entries)
    for entry in entries_list:
        if type(entry) is not dict:
            _fail(
                SaliencyIntegrityReason.MALFORMED_MANIFEST,
                "Saliency manifest entries are malformed.",
            )
        entry_dict = cast(dict[str, object], entry)
        if entry_dict.get("schema_version") != SALIENCY_PAYLOAD_IDENTITY_SCHEMA_VERSION:
            _fail(
                SaliencyIntegrityReason.UNSUPPORTED_SCHEMA,
                "Saliency payload identity uses an unsupported schema version.",
            )
        target = entry_dict.get("target")
        if type(target) is not dict:
            _fail(
                SaliencyIntegrityReason.TARGET_MISMATCH,
                "Saliency manifest target identity is malformed.",
            )
        target_dict = cast(dict[str, object], target)
        key = (entry_dict.get("method"), target_dict.get("class_index"))
        if key in result:
            _fail(
                SaliencyIntegrityReason.AMBIGUOUS_IDENTITY,
                "Saliency manifest contains duplicate method/class identities.",
            )
        result[key] = entry_dict
    return result


def _entry_content_hash(entry: Mapping[str, object]) -> object:
    array = entry.get("array")
    return array.get("content_sha256") if type(array) is dict else None


def _verified_identity_fingerprint(
    value: object,
    *,
    reason: SaliencyIntegrityReason,
    message: str,
) -> str:
    try:
        return fingerprint_saliency_identity(value)
    except SaliencyContextError as exc:
        _fail(reason, f"{message}: {exc}")


def verify_saliency_artifact_manifest(
    manifest: object,
    stores: Mapping[str, object],
    *,
    context: SaliencyArtifactContext,
    method_parameters: object,
    noise_seeds: object,
) -> dict[str, object]:
    """Re-hash every payload and verify a persisted manifest fail closed."""
    expected = _validate_manifest_envelope(manifest)
    if expected.get("context_fingerprint") != context.context_fingerprint:
        _fail(
            SaliencyIntegrityReason.TARGET_MISMATCH,
            "Saliency manifest does not match its EEG identity context.",
        )
    if expected.get("producer_fingerprint") != context.producer_identity.fingerprint:
        _fail(
            SaliencyIntegrityReason.PRODUCER_MISMATCH,
            "Saliency manifest does not match its producer identity.",
        )

    expected_parameters = expected.get("method_parameters")
    if _verified_identity_fingerprint(
        expected_parameters,
        reason=SaliencyIntegrityReason.PARAMETER_MISMATCH,
        message="Saliency manifest parameters are malformed",
    ) != _verified_identity_fingerprint(
        method_parameters,
        reason=SaliencyIntegrityReason.PARAMETER_MISMATCH,
        message="Saliency artifact parameters are malformed",
    ):
        _fail(
            SaliencyIntegrityReason.PARAMETER_MISMATCH,
            "Saliency method parameters do not match the integrity manifest.",
        )
    expected_seeds = expected.get("noise_seeds")
    if _verified_identity_fingerprint(
        expected_seeds,
        reason=SaliencyIntegrityReason.NOISE_SEED_MISMATCH,
        message="Saliency manifest noise seeds are malformed",
    ) != _verified_identity_fingerprint(
        noise_seeds,
        reason=SaliencyIntegrityReason.NOISE_SEED_MISMATCH,
        message="Saliency artifact noise seeds are malformed",
    ):
        _fail(
            SaliencyIntegrityReason.NOISE_SEED_MISMATCH,
            "Saliency noise seeds do not match the integrity manifest.",
        )

    runtime_contract = expected.get("runtime_contract")
    try:
        actual = build_saliency_artifact_manifest(
            stores,
            context=context,
            method_parameters=method_parameters,
            noise_seeds=noise_seeds,
            runtime_contract=runtime_contract,
        )
    except SaliencyArtifactIntegrityError:
        raise
    except SaliencyContextError as exc:
        _fail(SaliencyIntegrityReason.MALFORMED_MANIFEST, str(exc))

    if expected.get("methods") != actual["methods"]:
        _fail(
            SaliencyIntegrityReason.METHOD_MISMATCH,
            "Saliency payload methods do not match the integrity manifest.",
        )
    expected_entries = _entry_map(expected.get("entries"))
    actual_entries = _entry_map(actual["entries"])
    if set(expected_entries) != set(actual_entries):
        _fail(
            SaliencyIntegrityReason.PARTIAL_COVERAGE,
            "Saliency method/class coverage does not match the integrity manifest.",
        )

    expected_hash_locations = {
        _entry_content_hash(entry): key for key, entry in expected_entries.items()
    }
    for key, expected_entry in expected_entries.items():
        actual_entry = actual_entries[key]
        if expected_entry.get("target") != actual_entry.get("target"):
            _fail(
                SaliencyIntegrityReason.TARGET_MISMATCH,
                "Saliency target identity does not match the integrity manifest.",
            )
        expected_content = _entry_content_hash(expected_entry)
        actual_content = _entry_content_hash(actual_entry)
        if expected_content != actual_content:
            moved_from = expected_hash_locations.get(actual_content)
            reason = (
                SaliencyIntegrityReason.METHOD_MISMATCH
                if moved_from is not None and moved_from[0] != key[0]
                else SaliencyIntegrityReason.PAYLOAD_MUTATION
            )
            method = key[0] if isinstance(key[0], str) else None
            class_index = key[1] if isinstance(key[1], int) else None
            _fail(
                reason,
                "Saliency payload content does not match its method/class identity.",
                diagnostics=(
                    SaliencyIntegrityDiagnostic(
                        field="content_sha256",
                        message="Exact logical C-order payload hash mismatch.",
                        method=method,
                        class_index=class_index,
                        expected=expected_content,
                        actual=actual_content,
                    ),
                ),
            )
        if expected_entry.get("array") != actual_entry.get("array"):
            _fail(
                SaliencyIntegrityReason.PAYLOAD_MUTATION,
                "Saliency payload shape or dtype does not match its manifest.",
            )
        if expected_entry.get("identity_sha256") != actual_entry.get("identity_sha256"):
            _fail(
                SaliencyIntegrityReason.MANIFEST_TAMPERED,
                "Saliency payload identity hash failed verification.",
            )

    expected_manifest_sha = expected.get("manifest_sha256")
    computed_manifest_sha = _verified_identity_fingerprint(
        _manifest_core(expected),
        reason=SaliencyIntegrityReason.MALFORMED_MANIFEST,
        message="Saliency manifest contains unsupported metadata",
    )
    if expected_manifest_sha != computed_manifest_sha:
        _fail(
            SaliencyIntegrityReason.MANIFEST_TAMPERED,
            "Saliency integrity manifest hash failed verification.",
        )
    if expected_manifest_sha != actual["manifest_sha256"]:
        _fail(
            SaliencyIntegrityReason.RUNTIME_CONTRACT_MISMATCH,
            "Saliency producer/runtime contract does not match the payload identities.",
        )
    return dict(expected)


__all__ = [
    "SALIENCY_ARTIFACT_MANIFEST_SCHEMA_VERSION",
    "SALIENCY_METHOD_STORE_NAMES",
    "SALIENCY_PAYLOAD_IDENTITY_SCHEMA_VERSION",
    "SALIENCY_RUNTIME_CONTRACT_SCHEMA_VERSION",
    "SaliencyArtifactIntegrityError",
    "SaliencyIntegrityDiagnostic",
    "SaliencyIntegrityReason",
    "build_saliency_artifact_manifest",
    "current_saliency_runtime_contract",
    "normalize_saliency_method_parameters",
    "verify_saliency_artifact_manifest",
]
