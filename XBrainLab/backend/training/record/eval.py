"""Evaluation records and persistence for model metrics and saliency artifacts."""

from __future__ import annotations

import copy
import os
from collections.abc import Mapping
from typing import Any, cast

import numpy as np
from sklearn.metrics import roc_auc_score

from ...utils.filesystem_identity import (
    FilesystemIdentityError,
    StableDirectoryIdentity,
)
from ...utils.logger import logger
from ..saliency_artifact_integrity import (
    SALIENCY_METHOD_STORE_NAMES,
    SaliencyArtifactIntegrityError,
    SaliencyIntegrityDiagnostic,
    SaliencyIntegrityReason,
    build_saliency_artifact_manifest,
    verify_saliency_artifact_manifest,
)
from ..saliency_provenance import (
    SALIENCY_CONTEXT_SCHEMA_VERSION,  # noqa: F401 - compatibility re-export
    SALIENCY_PRODUCER_SCHEMA_VERSION,  # noqa: F401 - compatibility re-export
    SaliencyArtifactContext,
    SaliencyContextError,
    SaliencyProducerIdentity,
    canonicalize_saliency_identity,  # noqa: F401 - compatibility re-export
    describe_saliency_array,  # noqa: F401 - compatibility re-export
    fingerprint_saliency_epoch_data,  # noqa: F401 - compatibility re-export
    fingerprint_saliency_identity,  # noqa: F401 - compatibility re-export
    fingerprint_saliency_model_state,  # noqa: F401 - compatibility re-export
    fingerprint_saliency_split_mask,  # noqa: F401 - compatibility re-export
)
from .artifact_store import (
    EVALUATION_RECORD_ARTIFACT_TYPE,
    SALIENCY_EXPORT_ARTIFACT_TYPE,
    ArtifactStoreError,
    UnsupportedArtifactError,
    read_json_npz_artifact,
    write_json_npz_artifact,
)

EVAL_ARTIFACT_SCHEMA_VERSION = 4
EVAL_ARTIFACT_BASENAMES = frozenset(
    {"eval", "eval-training", "eval-validation", "eval-test"}
)
SALIENCY_EXPORT_ARTIFACT_SCHEMA_VERSION = 3

_SEALED_RESULT_FIELDS = frozenset(
    {
        "label",
        "output",
        *SALIENCY_METHOD_STORE_NAMES.values(),
        "evaluation_split",
        "saliency_context",
        "saliency_method_parameters",
        "saliency_noise_seeds",
        "saliency_integrity_manifest",
    }
)


def _freeze_array(value: object) -> np.ndarray:
    """Detach an array into bytes that cannot be made writable again."""
    array = np.asarray(value)
    if array.dtype.hasobject:
        raise SaliencyContextError("Saliency snapshots cannot contain object arrays.")
    return np.ndarray(
        shape=array.shape, dtype=array.dtype, buffer=array.tobytes(order="C")
    )


def _readonly_array_view(canonical: np.ndarray) -> np.ndarray:
    """Return an isolated header over immutable bytes, without a payload copy."""
    return np.ndarray(
        shape=canonical.shape,
        dtype=canonical.dtype,
        buffer=canonical.base,
    )


def _has_items(value: Any) -> bool:
    try:
        return len(value) > 0
    except TypeError:
        return False


def _decode_eval_artifact(
    payload: dict[str, object],
    arrays: dict[str, np.ndarray],
) -> dict[str, object]:
    label_array = payload.get("label_array")
    output_array = payload.get("output_array")
    raw_stores = payload.get("saliency_stores")
    if not isinstance(label_array, str) or label_array not in arrays:
        raise ArtifactStoreError(
            "Evaluation artifact label array reference is invalid."
        )
    if not isinstance(output_array, str) or output_array not in arrays:
        raise ArtifactStoreError(
            "Evaluation artifact output array reference is invalid."
        )
    if type(raw_stores) is not dict or set(raw_stores) != set(
        SALIENCY_METHOD_STORE_NAMES.values()
    ):
        raise ArtifactStoreError(
            "Evaluation artifact saliency store index is malformed."
        )
    consumed_arrays = {label_array, output_array}
    reconstructed_stores: dict[str, dict[int, np.ndarray]] = {}
    for attribute in SALIENCY_METHOD_STORE_NAMES.values():
        raw_entries = raw_stores[attribute]
        if not isinstance(raw_entries, list):
            raise ArtifactStoreError(
                f"Evaluation saliency store {attribute!r} is malformed."
            )
        reconstructed: dict[int, np.ndarray] = {}
        for entry in raw_entries:
            if type(entry) is not dict or set(entry) != {
                "class_index",
                "array",
            }:
                raise ArtifactStoreError(
                    f"Evaluation saliency store {attribute!r} is malformed."
                )
            class_index = entry["class_index"]
            array_name = entry["array"]
            if (
                isinstance(class_index, bool)
                or not isinstance(class_index, int)
                or class_index in reconstructed
                or not isinstance(array_name, str)
                or array_name not in arrays
                or array_name in consumed_arrays
            ):
                raise ArtifactStoreError(
                    f"Evaluation saliency store {attribute!r} is malformed."
                )
            reconstructed[class_index] = arrays[array_name]
            consumed_arrays.add(array_name)
        reconstructed_stores[attribute] = reconstructed
    if consumed_arrays != set(arrays):
        raise ArtifactStoreError(
            "Evaluation artifact contains unreferenced numeric arrays."
        )
    return {
        **payload,
        "label": arrays[label_array],
        "output": arrays[output_array],
        **reconstructed_stores,
    }


def calculate_confusion(output: np.ndarray, label: np.ndarray) -> np.ndarray:
    """Calculate the confusion matrix from model outputs and ground truth labels.

    Args:
        output: Model output array of shape ``(n, num_classes)``.
        label: Ground truth label array of shape ``(n,)``.

    Returns:
        A confusion matrix of shape ``(num_classes, num_classes)`` where
        entry ``[i][j]`` is the count of samples with true label ``i``
        predicted as label ``j``.

    """
    class_num = output.shape[1] if output.ndim > 1 else len(np.unique(label))
    confusion = np.zeros((class_num, class_num), dtype=np.uint32)
    output = output.argmax(axis=1)
    for ground_truth in range(class_num):
        for predict in range(class_num):
            confusion[ground_truth][predict] = (
                output[label == ground_truth] == predict
            ).sum()
    return confusion


class EvalRecord:
    """Record class for storing and exporting model evaluation results.

    Stores ground truth labels, model outputs, and saliency maps from
    multiple attribution methods, organized by class index.

    Attributes:
        label: Ground truth label array of shape ``(n,)``.
        output: Model output array of shape ``(n, num_classes)``.
        gradient: Dictionary mapping class indices to gradient arrays.
        gradient_input: Dictionary mapping class indices to gradient*input arrays.
        smoothgrad: Dictionary mapping class indices to SmoothGrad arrays.
        smoothgrad_sq: Dictionary mapping class indices to SmoothGrad² arrays.
        vargrad: Dictionary mapping class indices to VarGrad arrays.

    """

    _label: np.ndarray
    _output: np.ndarray
    _gradient: dict
    _gradient_input: dict
    _smoothgrad: dict
    _smoothgrad_sq: dict
    _vargrad: dict

    def __setattr__(self, name: str, value: object) -> None:
        if name in _SEALED_RESULT_FIELDS and getattr(
            self, "_saliency_result_sealed", False
        ):
            raise AttributeError("Completed saliency results are immutable.")
        object.__setattr__(self, name, value)

    def _set_store(self, name: str, value: object) -> None:
        if getattr(self, "_saliency_result_sealed", False):
            raise AttributeError("Completed saliency results are immutable.")
        object.__setattr__(self, f"_{name}", value)

    def _store_view(self, name: str) -> Mapping[object, np.ndarray] | dict:
        store = getattr(self, f"_{name}")
        if not getattr(self, "_saliency_result_sealed", False):
            return store
        return {key: _readonly_array_view(value) for key, value in store.items()}

    def _set_metadata(self, name: str, value: object) -> None:
        if getattr(self, "_saliency_result_sealed", False):
            raise AttributeError("Completed saliency results are immutable.")
        object.__setattr__(self, f"_{name}", copy.deepcopy(value))

    def _metadata_view(self, name: str) -> object:
        value = getattr(self, f"_{name}")
        return copy.deepcopy(value) if self._saliency_result_sealed else value

    @property
    def label(self) -> np.ndarray:
        value = self._label
        return _readonly_array_view(value) if self._saliency_result_sealed else value

    @label.setter
    def label(self, value: np.ndarray) -> None:
        self._set_store("label", value)

    @property
    def output(self) -> np.ndarray:
        value = self._output
        return _readonly_array_view(value) if self._saliency_result_sealed else value

    @output.setter
    def output(self, value: np.ndarray) -> None:
        self._set_store("output", value)

    @property
    def gradient(self) -> Mapping[object, np.ndarray] | dict:
        return self._store_view("gradient")

    @gradient.setter
    def gradient(self, value: dict) -> None:
        self._set_store("gradient", value)

    @property
    def gradient_input(self) -> Mapping[object, np.ndarray] | dict:
        return self._store_view("gradient_input")

    @gradient_input.setter
    def gradient_input(self, value: dict) -> None:
        self._set_store("gradient_input", value)

    @property
    def smoothgrad(self) -> Mapping[object, np.ndarray] | dict:
        return self._store_view("smoothgrad")

    @smoothgrad.setter
    def smoothgrad(self, value: dict) -> None:
        self._set_store("smoothgrad", value)

    @property
    def smoothgrad_sq(self) -> Mapping[object, np.ndarray] | dict:
        return self._store_view("smoothgrad_sq")

    @smoothgrad_sq.setter
    def smoothgrad_sq(self, value: dict) -> None:
        self._set_store("smoothgrad_sq", value)

    @property
    def vargrad(self) -> Mapping[object, np.ndarray] | dict:
        return self._store_view("vargrad")

    @vargrad.setter
    def vargrad(self, value: dict) -> None:
        self._set_store("vargrad", value)

    @property
    def saliency_method_parameters(self) -> Mapping[str, object]:
        return cast(
            Mapping[str, object], self._metadata_view("saliency_method_parameters")
        )

    @saliency_method_parameters.setter
    def saliency_method_parameters(self, value: Mapping[str, object]) -> None:
        self._set_metadata("saliency_method_parameters", value)

    @property
    def saliency_noise_seeds(self) -> Mapping[str, object]:
        return cast(Mapping[str, object], self._metadata_view("saliency_noise_seeds"))

    @saliency_noise_seeds.setter
    def saliency_noise_seeds(self, value: Mapping[str, object]) -> None:
        self._set_metadata("saliency_noise_seeds", value)

    @property
    def saliency_integrity_manifest(self) -> Mapping[str, object] | None:
        return cast(
            Mapping[str, object] | None,
            self._metadata_view("saliency_integrity_manifest"),
        )

    @saliency_integrity_manifest.setter
    def saliency_integrity_manifest(self, value: Mapping[str, object] | None) -> None:
        self._set_metadata("saliency_integrity_manifest", value)

    def __init__(
        self,
        label: np.ndarray,
        output: np.ndarray,
        gradient: dict,
        gradient_input: dict,
        smoothgrad: dict,
        smoothgrad_sq: dict,
        vargrad: dict,
        evaluation_split: str = "unknown",
        *,
        saliency_context: SaliencyArtifactContext | dict[str, Any] | None = None,
        saliency_method_parameters: Mapping[str, object] | None = None,
        saliency_noise_seeds: Mapping[str, object] | None = None,
        saliency_integrity_manifest: Mapping[str, object] | None = None,
        _from_artifact: bool = False,
    ) -> None:
        """Initialize the evaluation record.

        Args:
            label: Ground truth label array of shape ``(n,)``.
            output: Model output array of shape ``(n, num_classes)``.
            gradient: Per-class gradient saliency maps.
            gradient_input: Per-class gradient*input saliency maps.
            smoothgrad: Per-class SmoothGrad saliency maps.
            smoothgrad_sq: Per-class SmoothGrad² saliency maps.
            vargrad: Per-class VarGrad saliency maps.
            evaluation_split: Data split used for this final evaluation.
            saliency_context: Immutable EEG identity used when interpreting
                class-indexed and channel-indexed saliency arrays.
            saliency_method_parameters: Exact effective parameters by method.
            saliency_noise_seeds: Noise-tunnel seed by stochastic method.
            saliency_integrity_manifest: Serialized payload integrity manifest.

        """
        self._saliency_result_sealed = False
        self.label = label
        self.output = output
        self.gradient = gradient
        self.gradient_input = gradient_input
        self.smoothgrad = smoothgrad
        self.smoothgrad_sq = smoothgrad_sq
        self.vargrad = vargrad
        self.evaluation_split = str(evaluation_split or "unknown")
        if isinstance(saliency_context, dict):
            saliency_context = SaliencyArtifactContext.from_payload(saliency_context)
        self.saliency_context = saliency_context
        self._loaded_from_artifact = False
        self._saliency_context_error: str | None = None
        self._saliency_context_missing = False
        self._saliency_integrity_error: SaliencyArtifactIntegrityError | None = None
        self.saliency_method_parameters = copy.deepcopy(
            dict(saliency_method_parameters or {})
        )
        self.saliency_noise_seeds = copy.deepcopy(dict(saliency_noise_seeds or {}))
        self.saliency_integrity_manifest = (
            copy.deepcopy(dict(saliency_integrity_manifest))
            if saliency_integrity_manifest is not None
            else None
        )
        if self.has_saliency_data() and not self.saliency_method_parameters:
            self.saliency_method_parameters = {
                method: {}
                for method, store in self._saliency_stores().items()
                if _has_items(store)
            }
        if (
            not _from_artifact
            and self.has_saliency_data()
            and self.saliency_context is not None
        ):
            self._seal_saliency_integrity()

    @property
    def saliency_context_status(self) -> str:
        """Return the explicit compatibility state for saliency identity."""
        if self._saliency_context_error is not None:
            if self._saliency_context_missing:
                return "legacy_missing"
            return "incompatible"
        if self.saliency_context is not None:
            return "verified"
        if not self.has_saliency_data():
            return "not_applicable"
        if self._loaded_from_artifact:
            return "legacy_missing"
        return "runtime_unbound"

    @property
    def saliency_recompute_reason(self) -> str | None:
        """Return an actionable reason when persisted saliency is unusable."""
        return self._saliency_context_error

    @property
    def saliency_integrity_reason(self) -> SaliencyIntegrityReason | None:
        """Return the typed artifact-integrity reason, when validation failed."""
        if self._saliency_integrity_error is None:
            return None
        return self._saliency_integrity_error.reason

    @property
    def saliency_integrity_diagnostics(
        self,
    ) -> tuple[SaliencyIntegrityDiagnostic, ...]:
        """Return bounded method/class diagnostics for an integrity failure."""
        if self._saliency_integrity_error is None:
            return ()
        return self._saliency_integrity_error.diagnostics

    def has_saliency_data(self) -> bool:
        """Return whether any attribution method contains class results."""
        return any(
            _has_items(store)
            for store in (
                self.gradient,
                self.gradient_input,
                self.smoothgrad,
                self.smoothgrad_sq,
                self.vargrad,
            )
        )

    def bind_saliency_context(
        self,
        epoch_data: Any,
        *,
        producer_identity: SaliencyProducerIdentity | None = None,
    ) -> SaliencyArtifactContext:
        """Bind a fresh runtime saliency record to one immutable EEG context.

        Persisted legacy records are never rebound because doing so would assign
        old class/channel indices using whichever dataset happens to be active.
        """
        if self.saliency_context is None and self._loaded_from_artifact:
            raise SaliencyContextError(
                "This legacy saliency artifact does not contain identity context. "
                "Recompute saliency for the current dataset."
            )
        current = self._build_saliency_context(
            epoch_data,
            producer_identity=producer_identity,
        )
        if self.saliency_context is None:
            self.saliency_context = current
            self._saliency_context_error = None
            self._seal_saliency_integrity()
            return current
        return self._validate_saliency_context(current)

    def validate_saliency_context(
        self,
        epoch_data: Any,
        *,
        producer_identity: SaliencyProducerIdentity | None = None,
    ) -> SaliencyArtifactContext:
        """Validate an existing artifact identity without mutating the record."""
        self._raise_saliency_context_error()
        if self.saliency_context is None:
            if self._loaded_from_artifact:
                raise SaliencyContextError(
                    "This legacy saliency artifact does not contain identity "
                    "context. Recompute saliency for the current dataset."
                )
            raise SaliencyContextError(
                "Saliency identity context is not bound. Recompute saliency "
                "before rendering."
            )
        return self._validate_saliency_context(
            self._build_saliency_context(
                epoch_data,
                producer_identity=producer_identity,
            )
        )

    def _build_saliency_context(
        self,
        epoch_data: Any,
        *,
        producer_identity: SaliencyProducerIdentity | None,
    ) -> SaliencyArtifactContext:
        """Build the current EEG identity using the trained output contract."""
        expected_class_count = None
        outputs = np.asarray(self.output)
        if outputs.ndim == 2 and outputs.shape[1] > 0:
            expected_class_count = int(outputs.shape[1])
        if producer_identity is None:
            if self.saliency_context is None:
                raise SaliencyContextError(
                    "Saliency producer provenance is unavailable. Recompute "
                    "saliency for the current dataset."
                )
            producer_identity = self.saliency_context.producer_identity
        return SaliencyArtifactContext.from_epoch_data(
            epoch_data,
            class_count=expected_class_count,
            producer_identity=producer_identity,
        )

    def _validate_saliency_context(
        self,
        current: SaliencyArtifactContext,
    ) -> SaliencyArtifactContext:
        """Compare one current identity with the immutable artifact identity."""
        self._raise_saliency_context_error()
        if self.saliency_context is None:
            raise SaliencyContextError("Saliency identity context is not bound.")
        differences = self.saliency_context.mismatch_details(current)
        if differences:
            raise SaliencyContextError(
                "Saliency artifact does not match the current EEG "
                f"{', '.join(differences)}. Recompute saliency before rendering."
            )
        if not self._saliency_result_sealed:
            self._verify_saliency_integrity()
        return self.saliency_context

    def validate_saliency_producer_identity(
        self,
        producer_identity: SaliencyProducerIdentity,
    ) -> SaliencyProducerIdentity:
        """Validate dataset/split/run/model provenance without EEG array access."""
        self._raise_saliency_context_error()
        if self.saliency_context is None:
            raise SaliencyContextError(
                "Saliency producer provenance is missing. Recompute saliency."
            )
        differences = self.saliency_context.producer_identity.mismatch_details(
            producer_identity
        )
        if differences:
            raise SaliencyContextError(
                "Saliency artifact does not match the current "
                f"{', '.join(differences)}. Recompute saliency before rendering."
            )
        if not self._saliency_result_sealed:
            self._verify_saliency_integrity()
        return self.saliency_context.producer_identity

    def validate_sealed_saliency_render_snapshot(
        self,
        epoch_data: Any,
        *,
        producer_identity: SaliencyProducerIdentity,
    ) -> SaliencyArtifactContext:
        """Validate live model/split and EEG axes without hashing sealed payloads."""
        self._raise_saliency_context_error()
        if not self._saliency_result_sealed or self.saliency_context is None:
            raise SaliencyContextError(
                "Saliency result is not sealed. Recompute saliency."
            )
        outputs = np.asarray(self.output)
        class_count = int(outputs.shape[1]) if outputs.ndim == 2 else None
        current = SaliencyArtifactContext.from_epoch_data(
            epoch_data,
            class_count=class_count,
            producer_identity=producer_identity,
            sealed_epoch_data_fingerprint=self.saliency_context.epoch_data_fingerprint,
        )
        return self._validate_saliency_context(current)

    def mark_saliency_context_incompatible(self, reason: str) -> None:
        """Fail closed while preserving non-saliency evaluation metrics."""
        normalized = str(reason).strip()
        if not normalized:
            normalized = "Saliency provenance is incompatible."
        if "recompute saliency" not in normalized.lower():
            normalized = f"{normalized} Recompute saliency for the current run."
        self._saliency_context_error = normalized

    def mark_saliency_integrity_incompatible(
        self,
        error: SaliencyArtifactIntegrityError,
    ) -> None:
        """Preserve metrics while retaining a typed fail-closed saliency error."""
        self.mark_saliency_context_incompatible(str(error))
        self._saliency_integrity_error = SaliencyArtifactIntegrityError(
            error.reason,
            self._saliency_context_error or str(error),
            diagnostics=error.diagnostics,
        )

    def _raise_saliency_context_error(self) -> None:
        if self._saliency_integrity_error is not None:
            raise self._saliency_integrity_error
        if self._saliency_context_error is not None:
            raise SaliencyContextError(self._saliency_context_error)

    def _saliency_stores(self) -> dict[str, Mapping[object, object]]:
        return {
            method: cast(Mapping[object, object], getattr(self, attribute))
            for method, attribute in SALIENCY_METHOD_STORE_NAMES.items()
        }

    def _seal_saliency_integrity(self) -> dict[str, object]:
        if self.saliency_context is None:
            raise SaliencyContextError(
                "Saliency integrity cannot be sealed without identity context."
            )
        detached_stores = {
            method: {key: _freeze_array(value) for key, value in store.items()}
            for method, store in self._saliency_stores().items()
        }
        manifest = build_saliency_artifact_manifest(
            detached_stores,
            context=self.saliency_context,
            method_parameters=self.saliency_method_parameters,
            noise_seeds=self.saliency_noise_seeds,
        )
        parameters = manifest["method_parameters"]
        seeds = manifest["noise_seeds"]
        if not isinstance(parameters, dict) or not isinstance(seeds, dict):
            raise SaliencyArtifactIntegrityError(
                SaliencyIntegrityReason.MALFORMED_MANIFEST,
                "Generated saliency manifest contract is malformed.",
            )
        self._freeze_verified_saliency_result(detached_stores, manifest)
        return manifest

    def _freeze_verified_saliency_result(
        self,
        detached_stores: Mapping[str, Mapping[object, np.ndarray]] | None = None,
        manifest: Mapping[str, object] | None = None,
    ) -> None:
        """Seal a fully verified result without exposing mutable array headers."""
        stores = detached_stores or {
            method: {key: _freeze_array(value) for key, value in store.items()}
            for method, store in self._saliency_stores().items()
        }
        frozen_label = _freeze_array(self._label)
        frozen_output = _freeze_array(self._output)
        parameters = (
            manifest.get("method_parameters")
            if manifest is not None
            else self.saliency_method_parameters
        )
        seeds = (
            manifest.get("noise_seeds")
            if manifest is not None
            else self.saliency_noise_seeds
        )
        frozen_manifest = (
            manifest if manifest is not None else self.saliency_integrity_manifest
        )
        for method, attribute in SALIENCY_METHOD_STORE_NAMES.items():
            object.__setattr__(self, f"_{attribute}", dict(stores[method]))
        object.__setattr__(self, "_label", frozen_label)
        object.__setattr__(self, "_output", frozen_output)
        object.__setattr__(
            self, "_saliency_method_parameters", copy.deepcopy(parameters)
        )
        object.__setattr__(self, "_saliency_noise_seeds", copy.deepcopy(seeds))
        object.__setattr__(
            self, "_saliency_integrity_manifest", copy.deepcopy(frozen_manifest)
        )
        object.__setattr__(self, "_saliency_integrity_error", None)
        object.__setattr__(self, "_saliency_result_sealed", True)

    def _verify_saliency_integrity(self) -> dict[str, object] | None:
        if not self.has_saliency_data():
            return None
        if self.saliency_context is None:
            raise SaliencyArtifactIntegrityError(
                SaliencyIntegrityReason.PRODUCER_MISMATCH,
                "Saliency integrity cannot be verified without identity context.",
            )
        manifest = verify_saliency_artifact_manifest(
            self.saliency_integrity_manifest,
            self._saliency_stores(),
            context=self.saliency_context,
            method_parameters=self.saliency_method_parameters,
            noise_seeds=self.saliency_noise_seeds,
        )
        self.saliency_integrity_manifest = manifest
        return manifest

    def _require_persistable_saliency_context(self) -> None:
        self._raise_saliency_context_error()
        if self.has_saliency_data() and self.saliency_context is None:
            raise SaliencyContextError(
                "Saliency cannot be persisted without class, channel, and EEG epoch "
                "identity context. Bind the evaluation record to its EEG epoch "
                "data first."
            )
        if self.has_saliency_data():
            if self.saliency_integrity_manifest is None:
                self._seal_saliency_integrity()
            elif not self._saliency_result_sealed:
                self._verify_saliency_integrity()

    def export(
        self,
        target_path: str,
        *,
        artifact_basename: str = "eval",
        directory_identity: StableDirectoryIdentity | None = None,
    ) -> None:
        """Export the evaluation record as JSON metadata and numeric NPZ arrays.

        Args:
            target_path: Directory where ``eval`` and ``eval.npz`` are saved.

        """
        if artifact_basename not in EVAL_ARTIFACT_BASENAMES:
            raise ValueError("Unsupported evaluation artifact basename")
        self._require_persistable_saliency_context()
        arrays: dict[str, object] = {
            "label": self.label,
            "output": self.output,
        }
        saliency_stores: dict[str, list[dict[str, object]]] = {}
        for attribute in SALIENCY_METHOD_STORE_NAMES.values():
            store = getattr(self, attribute)
            if type(store) is not dict:
                raise ArtifactStoreError(
                    f"Evaluation saliency store {attribute!r} must be a plain mapping."
                )
            entries: list[dict[str, object]] = []
            for index, (class_index, values) in enumerate(store.items()):
                array_name = f"saliency.{attribute}.{index}"
                arrays[array_name] = values
                entries.append(
                    {
                        "class_index": class_index,
                        "array": array_name,
                    }
                )
            saliency_stores[attribute] = entries
        payload = {
            "artifact_schema_version": EVAL_ARTIFACT_SCHEMA_VERSION,
            "label_array": "label",
            "output_array": "output",
            "saliency_stores": saliency_stores,
            "evaluation_split": self.evaluation_split,
            "saliency_context": (
                self.saliency_context.to_payload()
                if self.saliency_context is not None
                else None
            ),
            "saliency_method_parameters": copy.deepcopy(
                self.saliency_method_parameters
            ),
            "saliency_noise_seeds": copy.deepcopy(self.saliency_noise_seeds),
            "saliency_integrity_manifest": copy.deepcopy(
                self.saliency_integrity_manifest
            ),
        }
        write_json_npz_artifact(
            os.path.join(target_path, artifact_basename),
            artifact_type=EVALUATION_RECORD_ARTIFACT_TYPE,
            payload=payload,
            arrays=arrays,
            arrays_filename=f"{artifact_basename}.npz",
            directory_identity=directory_identity,
        )

    @classmethod
    def load(
        cls,
        target_path: str,
        *,
        artifact_basename: str = "eval",
        expected_producer_identity: SaliencyProducerIdentity | None = None,
        directory_identity: StableDirectoryIdentity | None = None,
    ) -> EvalRecord | None:
        """Load an evaluation record from the safe JSON/NPZ artifact store.

        Args:
            target_path: Directory path containing the ``'eval'`` file.

        Returns:
            An :class:`EvalRecord` instance, or ``None`` if the file does not
            exist or cannot be loaded.

        """
        if artifact_basename not in EVAL_ARTIFACT_BASENAMES:
            raise ValueError("Unsupported evaluation artifact basename")
        path = os.path.join(target_path, artifact_basename)
        if not os.path.exists(path):
            return None

        try:
            payload, arrays = read_json_npz_artifact(
                path,
                expected_artifact_type=EVALUATION_RECORD_ARTIFACT_TYPE,
                directory_identity=directory_identity,
            )
            data = _decode_eval_artifact(payload, arrays)
            saliency_stores = {
                attribute: (value if type(value) is dict else {})
                for attribute in SALIENCY_METHOD_STORE_NAMES.values()
                for value in (data.get(attribute, {}),)
            }
            malformed_stores = tuple(
                attribute
                for attribute in SALIENCY_METHOD_STORE_NAMES.values()
                if type(data.get(attribute, {})) is not dict
            )
            integrity_stores = {
                method: saliency_stores[attribute]
                for method, attribute in SALIENCY_METHOD_STORE_NAMES.items()
            }
            has_saliency = bool(malformed_stores) or any(
                bool(value) for value in saliency_stores.values()
            )
            raw_artifact_version = data.get("artifact_schema_version", 0)
            artifact_version = (
                raw_artifact_version if type(raw_artifact_version) is int else 0
            )
            context_payload = data.get("saliency_context")
            method_parameters = data.get("saliency_method_parameters", {})
            noise_seeds = data.get("saliency_noise_seeds", {})
            integrity_manifest = data.get("saliency_integrity_manifest")
            context: SaliencyArtifactContext | None = None
            context_error: str | None = None
            integrity_error: SaliencyArtifactIntegrityError | None = None
            if malformed_stores:
                integrity_error = SaliencyArtifactIntegrityError(
                    SaliencyIntegrityReason.PARTIAL_COVERAGE,
                    "Saliency class stores must be plain mappings: "
                    f"{', '.join(malformed_stores)}.",
                )
            if context_payload is None:
                if has_saliency:
                    context_error = (
                        "This legacy saliency artifact does not contain producer "
                        "identity context."
                    )
            else:
                try:
                    context = SaliencyArtifactContext.from_payload(context_payload)
                except SaliencyContextError as exc:
                    context_error = str(exc)
                    if artifact_version < EVAL_ARTIFACT_SCHEMA_VERSION:
                        context_error = (
                            "This legacy saliency identity schema is unsupported: "
                            f"{context_error}"
                        )
            if integrity_error is not None:
                pass
            elif has_saliency and context_error is not None:
                integrity_error = SaliencyArtifactIntegrityError(
                    SaliencyIntegrityReason.PRODUCER_MISMATCH,
                    context_error,
                )
            elif has_saliency and artifact_version != EVAL_ARTIFACT_SCHEMA_VERSION:
                integrity_error = SaliencyArtifactIntegrityError(
                    SaliencyIntegrityReason.UNSUPPORTED_SCHEMA,
                    "This legacy saliency artifact schema version "
                    f"{artifact_version} does not contain the required payload "
                    "integrity manifest.",
                )
            elif has_saliency and context is not None:
                try:
                    verify_saliency_artifact_manifest(
                        integrity_manifest,
                        integrity_stores,
                        context=context,
                        method_parameters=method_parameters,
                        noise_seeds=noise_seeds,
                    )
                except SaliencyArtifactIntegrityError as exc:
                    integrity_error = exc
                except SaliencyContextError as exc:
                    integrity_error = SaliencyArtifactIntegrityError(
                        SaliencyIntegrityReason.MALFORMED_MANIFEST,
                        str(exc),
                    )
            record = cls(
                label=cast(np.ndarray, data["label"]),
                output=cast(np.ndarray, data["output"]),
                gradient=saliency_stores["gradient"],
                gradient_input=saliency_stores["gradient_input"],
                smoothgrad=saliency_stores["smoothgrad"],
                smoothgrad_sq=saliency_stores["smoothgrad_sq"],
                vargrad=saliency_stores["vargrad"],
                evaluation_split=str(data.get("evaluation_split", "unknown")),
                saliency_context=context,
                saliency_method_parameters=(
                    method_parameters if type(method_parameters) is dict else None
                ),
                saliency_noise_seeds=(
                    noise_seeds if type(noise_seeds) is dict else None
                ),
                saliency_integrity_manifest=(
                    integrity_manifest if type(integrity_manifest) is dict else None
                ),
                _from_artifact=True,
            )
        except (FilesystemIdentityError, UnsupportedArtifactError):
            raise
        except Exception as e:
            logger.error("Failed to load EvalRecord: %s", e, exc_info=True)
            return None
        else:
            record._loaded_from_artifact = True
            if context_error is not None:
                record.mark_saliency_context_incompatible(context_error)
                record._saliency_context_missing = context_payload is None
            if integrity_error is not None:
                record.mark_saliency_integrity_incompatible(integrity_error)
                if context_payload is None:
                    record._saliency_context_missing = True
            if (
                expected_producer_identity is not None
                and has_saliency
                and integrity_error is None
                and context is not None
            ):
                differences = context.producer_identity.mismatch_details(
                    expected_producer_identity
                )
                if differences:
                    record.mark_saliency_integrity_incompatible(
                        SaliencyArtifactIntegrityError(
                            SaliencyIntegrityReason.PRODUCER_MISMATCH,
                            "Saliency artifact does not match the current "
                            f"{', '.join(differences)}.",
                        )
                    )
            if (
                has_saliency
                and context is not None
                and integrity_error is None
                and record._saliency_context_error is None
            ):
                record._freeze_verified_saliency_result()
            return record

    def export_csv(self, target_path: str) -> None:
        """Export evaluation results as a CSV file.

        The CSV contains model outputs, ground truth labels, and predicted labels.

        Args:
            target_path: Full file path for the CSV output.

        """
        data = np.c_[self.output, self.label, self.output.argmax(axis=1)]
        index_header_str = ",".join([str(i) for i in range(self.output.shape[1])])
        header = f"{index_header_str},ground_truth,predict"
        np.savetxt(
            target_path,
            data,
            delimiter=",",
            newline="\n",
            header=header,
            comments="",
        )

    def export_saliency(self, method: str, target_path: str | None = None) -> dict:
        """Build and optionally save an identity-bearing saliency artifact.

        Args:
            method: Saliency method name. One of ``'Gradient'``,
                ``'Gradient * Input'``, ``'SmoothGrad'``,
                ``'SmoothGrad_Squared'``, or ``'VarGrad'``.
            target_path: Optional JSON manifest path. Its numeric arrays are
                saved in a sibling path ending in ``.npz``.

        Returns:
            A versioned artifact envelope containing the requested saliency and
            its immutable EEG identity context.

        """
        if method == "Gradient":
            saliency = self.gradient
        elif method == "Gradient * Input":
            saliency = self.gradient_input
        elif method == "SmoothGrad":
            saliency = self.smoothgrad
        elif method == "SmoothGrad_Squared":
            saliency = self.smoothgrad_sq
        elif method == "VarGrad":
            saliency = self.vargrad
        else:
            raise ValueError(f"Unknown saliency method: {method}")
        self._require_persistable_saliency_context()
        if self.saliency_context is None:
            raise SaliencyContextError("Saliency identity context is not bound.")
        method_parameters = {
            method: copy.deepcopy(self.saliency_method_parameters[method])
        }
        noise_seeds = (
            {method: self.saliency_noise_seeds[method]}
            if method in self.saliency_noise_seeds
            else {}
        )
        manifest = build_saliency_artifact_manifest(
            {method: saliency},
            context=self.saliency_context,
            method_parameters=method_parameters,
            noise_seeds=noise_seeds,
        )
        artifact = {
            "artifact_schema_version": SALIENCY_EXPORT_ARTIFACT_SCHEMA_VERSION,
            "method": method,
            "saliency": saliency,
            "saliency_context": self.saliency_context.to_payload()
            if self.saliency_context is not None
            else None,
            "saliency_method_parameters": copy.deepcopy(method_parameters),
            "saliency_noise_seeds": copy.deepcopy(noise_seeds),
            "saliency_integrity_manifest": copy.deepcopy(manifest),
        }
        if target_path:
            arrays: dict[str, object] = {}
            saliency_entries: list[dict[str, object]] = []
            for index, (class_index, values) in enumerate(saliency.items()):
                array_name = f"saliency.{index}"
                arrays[array_name] = values
                saliency_entries.append(
                    {
                        "class_index": class_index,
                        "array": array_name,
                    }
                )
            write_json_npz_artifact(
                target_path,
                artifact_type=SALIENCY_EXPORT_ARTIFACT_TYPE,
                payload={
                    key: value for key, value in artifact.items() if key != "saliency"
                }
                | {"saliency_arrays": saliency_entries},
                arrays=arrays,
            )
        return artifact

    def get_acc(self) -> float:
        """Compute the classification accuracy.

        Returns:
            Accuracy as a float between 0 and 1.

        """
        if len(self.label) == 0:
            return 0.0
        return sum(self.output.argmax(axis=1) == self.label) / len(self.label)

    def get_auc(self) -> float | None:
        """Compute the AUC (Area Under the ROC Curve) score.

        Handles both binary and multi-class scenarios using one-vs-rest.

        Returns:
            AUC score as a float, or ``None`` when it is undefined.

        """
        if len(self.label) == 0 or len(self.output) == 0:
            return None
        labels = np.asarray(self.label)
        outputs = np.asarray(self.output)
        if outputs.ndim != 2 or outputs.shape[0] != labels.shape[0]:
            return None
        unique_labels = np.unique(labels)
        if unique_labels.size < 2 or outputs.shape[1] < 2:
            return None
        shifted_outputs = outputs - np.max(outputs, axis=1, keepdims=True)
        exponentials = np.exp(shifted_outputs)
        probabilities = exponentials / np.sum(exponentials, axis=1, keepdims=True)
        if probabilities.shape[1] > 2 and unique_labels.size != probabilities.shape[1]:
            return None
        try:
            if probabilities.shape[1] <= 2:
                auc = roc_auc_score(labels, probabilities[:, -1])
            else:
                auc = roc_auc_score(labels, probabilities, multi_class="ovr")
        except ValueError as exc:
            logger.warning("Evaluation AUC is undefined: %s", exc)
            return None
        return None if np.isnan(auc) else float(auc)

    def get_kappa(self) -> float:
        """Compute Cohen's Kappa coefficient.

        Returns:
            The Kappa statistic as a float.

        """
        confusion = calculate_confusion(self.output, self.label)
        class_num = len(confusion)
        p0 = np.diagonal(confusion).sum() / confusion.sum()
        pe = sum(
            [confusion[:, i].sum() * confusion[i].sum() for i in range(class_num)],
        ) / (confusion.sum() * confusion.sum())
        if pe >= 1.0:
            return 0.0
        return (p0 - pe) / (1 - pe)

    def get_per_class_metrics(self) -> dict:
        """Get per-class precision, recall, f1-score, and support.

        Returns:
            Dictionary where keys are class indices and values are dicts containing:
            'precision', 'recall', 'f1-score', 'support'

        """
        if len(self.label) == 0:
            raise ValueError(
                "Found empty input array (e.g., `y_true` or `y_pred`) while a "
                "minimum of 1 sample is required."
            )
        class_num = self.output.shape[1]
        confusion = calculate_confusion(self.output, self.label)

        metrics: dict[int | str, dict[str, float | int]] = {}
        precision_scores: list[float] = []
        recall_scores: list[float] = []
        f1_scores: list[float] = []
        total_support = 0
        for class_index in range(class_num):
            true_positive = int(confusion[class_index, class_index])
            predicted_count = int(confusion[:, class_index].sum())
            support = int(confusion[class_index].sum())
            precision = true_positive / predicted_count if predicted_count else 0.0
            recall = true_positive / support if support else 0.0
            f1_denominator = predicted_count + support
            f1_score = 2.0 * true_positive / f1_denominator if f1_denominator else 0.0
            metrics[class_index] = {
                "precision": precision,
                "recall": recall,
                "f1-score": f1_score,
                "support": support,
            }
            precision_scores.append(precision)
            recall_scores.append(recall)
            f1_scores.append(f1_score)
            total_support += support

        # Calculate macro average
        metrics["macro_avg"] = {
            "precision": float(np.mean(precision_scores)),
            "recall": float(np.mean(recall_scores)),
            "f1-score": float(np.mean(f1_scores)),
            "support": total_support,
        }

        return metrics

    def get_gradient(self, label_index: int) -> np.ndarray:
        """Return gradient saliency maps for the specified class.

        Args:
            label_index: Class index to retrieve saliency maps for.

        Returns:
            Numpy array of gradient saliency maps for the given class.

        """
        return self._saliency_for_class(
            self.gradient,
            label_index,
            method="Gradient",
        )

    def get_gradient_input(self, label_index: int) -> np.ndarray:
        """Return gradient*input saliency maps for the specified class.

        Args:
            label_index: Class index to retrieve saliency maps for.

        Returns:
            Numpy array of gradient*input saliency maps for the given class.

        """
        return self._saliency_for_class(
            self.gradient_input,
            label_index,
            method="Gradient * Input",
        )

    def get_smoothgrad(self, label_index: int) -> np.ndarray:
        """Return SmoothGrad saliency maps for the specified class.

        Args:
            label_index: Class index to retrieve saliency maps for.

        Returns:
            Numpy array of SmoothGrad saliency maps for the given class.

        """
        return self._saliency_for_class(
            self.smoothgrad,
            label_index,
            method="SmoothGrad",
        )

    def get_smoothgrad_sq(self, label_index: int) -> np.ndarray:
        """Return SmoothGrad² saliency maps for the specified class.

        Args:
            label_index: Class index to retrieve saliency maps for.

        Returns:
            Numpy array of SmoothGrad² saliency maps for the given class.

        """
        return self._saliency_for_class(
            self.smoothgrad_sq,
            label_index,
            method="SmoothGrad Squared",
        )

    def get_vargrad(self, label_index: int) -> np.ndarray:
        """Return VarGrad saliency maps for the specified class.

        Args:
            label_index: Class index to retrieve saliency maps for.

        Returns:
            Numpy array of VarGrad saliency maps for the given class.

        """
        return self._saliency_for_class(
            self.vargrad,
            label_index,
            method="VarGrad",
        )

    def _saliency_for_class(
        self,
        store: Mapping[object, np.ndarray],
        label_index: int,
        *,
        method: str,
    ) -> np.ndarray:
        """Return one class result without leaking persistence ``KeyError``."""
        self._raise_saliency_context_error()
        if not self._saliency_result_sealed:
            self._verify_saliency_integrity()
        try:
            value = store[label_index]
        except KeyError as exc:
            raise SaliencyContextError(
                f"{method} saliency is unavailable for class {label_index}. "
                "Recompute saliency for the current run."
            ) from exc
        return value
