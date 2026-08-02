"""Base visualizer module for generating matplotlib figures from evaluation records."""

import contextlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

import numpy as np
from matplotlib import pyplot as plt
from matplotlib.figure import Figure

from XBrainLab.backend.application.saliency_render import SaliencyRenderData

from ..dataset import Epochs
from ..training.record import EvalRecord
from ..training.saliency_provenance import SaliencyArtifactContext


@dataclass(frozen=True)
class SaliencyClassIdentity:
    """One unambiguous class binding between EEG metadata and saliency data."""

    saliency_key: object
    class_index: int
    event_code: object | None
    display_name: str


def _identity_token(value: object) -> tuple[str, object]:
    """Return a comparison token without conflating unrelated text values."""
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        return ("integer", int(value))
    if isinstance(value, str):
        stripped = value.strip()
        with contextlib.suppress(ValueError):
            return ("integer", int(stripped))
        return ("text", stripped)
    return ("typed", (type(value).__qualname__, repr(value)))


def _unique_items_by_token(
    items: Sequence[tuple[object, object]],
    *,
    value_index: int,
) -> dict[tuple[str, object], tuple[object, object]]:
    indexed: dict[tuple[str, object], tuple[object, object]] = {}
    duplicates: set[tuple[str, object]] = set()
    for item in items:
        token = _identity_token(item[value_index])
        if token in indexed:
            duplicates.add(token)
        else:
            indexed[token] = item
    for token in duplicates:
        indexed.pop(token, None)
    return indexed


def resolve_saliency_class_identities(
    saliency_store,
    label_items: Sequence[tuple[object, object]],
    *,
    expected_class_count: int | None = None,
) -> list[SaliencyClassIdentity]:
    """Resolve saliency classes using one explicit key schema.

    A complete ``0..N-1`` key set is treated as normalized model class indices.
    Ordered EEG labels may then be paired only when their count is exactly ``N``.
    Any other key set must match EEG event codes or class names one-to-one.  The
    resolver intentionally rejects partial and duplicate matches rather than
    guessing from a candidate order.
    """
    if isinstance(saliency_store, Mapping):
        saliency_keys = list(saliency_store)
    else:
        try:
            saliency_keys = list(range(len(saliency_store)))
        except TypeError:
            saliency_keys = []

    if expected_class_count is not None and len(saliency_keys) != expected_class_count:
        raise ValueError(
            f"Saliency expected {expected_class_count} classes but found "
            f"{len(saliency_keys)}."
        )

    key_by_token: dict[tuple[str, object], object] = {}
    for key in saliency_keys:
        token = _identity_token(key)
        if token in key_by_token:
            raise ValueError(
                "Saliency class keys are ambiguous after normalization: "
                f"{key_by_token[token]!r} and {key!r}."
            )
        key_by_token[token] = key

    labels = list(label_items)
    normalized_tokens = {_identity_token(index) for index in range(len(saliency_keys))}
    is_normalized_store = set(key_by_token) == normalized_tokens
    labels_by_code = _unique_items_by_token(labels, value_index=0)
    labels_by_name = _unique_items_by_token(labels, value_index=1)

    if is_normalized_store:
        exact_code_match = all(
            _identity_token(index) in labels_by_code
            for index in range(len(saliency_keys))
        )
        if exact_code_match:
            ordered_labels = [
                labels_by_code[_identity_token(index)]
                for index in range(len(saliency_keys))
            ]
        elif len(labels) == len(saliency_keys):
            ordered_labels = labels
        else:
            ordered_labels = [(None, str(index)) for index in range(len(saliency_keys))]

        identities = [
            SaliencyClassIdentity(
                saliency_key=key_by_token[_identity_token(class_index)],
                class_index=class_index,
                event_code=event_code,
                display_name=str(display_name),
            )
            for class_index, (event_code, display_name) in enumerate(ordered_labels)
        ]
    else:
        matches_by_code = all(token in labels_by_code for token in key_by_token)
        matches_by_name = all(token in labels_by_name for token in key_by_token)
        if labels and not matches_by_code and not matches_by_name:
            available = ", ".join(map(str, saliency_keys)) or "none"
            raise ValueError(
                "Cannot establish a one-to-one class identity for saliency keys "
                f"{available}."
            )

        identities = []
        for class_index, key in enumerate(saliency_keys):
            token = _identity_token(key)
            if matches_by_code:
                event_code, display_name = labels_by_code[token]
            elif matches_by_name:
                event_code, display_name = labels_by_name[token]
            else:
                event_code, display_name = key, key
            identities.append(
                SaliencyClassIdentity(
                    saliency_key=key,
                    class_index=class_index,
                    event_code=event_code,
                    display_name=str(display_name),
                )
            )

    display_tokens = [_identity_token(item.display_name) for item in identities]
    if len(display_tokens) != len(set(display_tokens)):
        raise ValueError("Resolved saliency class names are not unique.")
    return identities


class Visualizer:
    """Base class for visualizer that generate figures from evaluation record

    Attributes:
        eval_record: evaluation record
        epoch_data: original epoch data for providing dataset information
        figsize: figure size
        dpi: figure dpi
        fig: figure to plot on. If None, a new figure will be created

    """

    MIN_LABEL_NUMBER_FOR_MULTI_ROW = 2

    def __init__(
        self,
        eval_record: EvalRecord | SaliencyRenderData,
        epoch_data: Epochs | None = None,
        figsize: tuple = (6.4, 4.8),
        dpi: int = 100,
        fig: Figure | None = None,
    ):
        """Initialise the visualizer.

        Args:
            eval_record: Evaluation record containing model outputs and gradients.
            epoch_data: Original epoch data providing dataset information.
            figsize: Width and height of the figure in inches.
            dpi: Dots per inch for the figure.
            fig: Existing matplotlib ``Figure`` to draw on.  If ``None``, a new
                figure is created on each call to :meth:`get_plt`.

        """
        self.render_data: SaliencyRenderData | None
        self.eval_record: EvalRecord | SaliencyRenderData
        self.epoch_data: Epochs | SaliencyRenderData
        if isinstance(eval_record, SaliencyRenderData):
            self.render_data = eval_record
            self.eval_record = eval_record
            self.epoch_data = eval_record
        else:
            if epoch_data is None:
                raise TypeError("epoch_data is required for an EvalRecord visualizer")
            self.render_data = None
            self.eval_record = eval_record
            self.epoch_data = epoch_data
        self.figsize = figsize
        self.dpi = dpi
        self.fig = fig

    def _get_plt(self, *args, **kwargs):
        """Subclass hook that performs the actual plotting.

        Raises:
            NotImplementedError: Always; subclasses must override this method.

        """
        raise NotImplementedError

    def get_plt(self, *args, **kwargs):
        """Create (or clear) the figure and delegate to :meth:`_get_plt`.

        Args:
            *args: Positional arguments forwarded to :meth:`_get_plt`.
            **kwargs: Keyword arguments forwarded to :meth:`_get_plt`.

        Returns:
            matplotlib.figure.Figure: The rendered figure.

        """
        created_figure = self.fig is None
        if self.fig is None:
            self.fig = Figure(figsize=self.figsize, dpi=self.dpi)
        try:
            self.fig.clf()
            return self._get_plt(*args, **kwargs)
        except Exception:
            if created_figure and self.fig is not None:
                plt.close(self.fig)
                self.fig = None
            raise

    def get_saliency(self, saliency_name: str, label_index: int) -> np.ndarray:
        """Return the saliency (gradient-based) array for a given class.

        Args:
            saliency_name: Name of the saliency method.  Supported values are
                ``"Gradient"``, ``"Gradient * Input"``, ``"SmoothGrad"``,
                ``"SmoothGrad_Squared"``, and ``"VarGrad"``.
            label_index: Index of the target class label.

        Returns:
            np.ndarray: Saliency array computed by the requested method.

        Raises:
            NotImplementedError: If *saliency_name* is not a recognised method.
            ValueError: If *saliency_name* is ``None``.

        """
        self._validated_saliency_context()
        saliency_store = self._saliency_store(saliency_name)
        resolved_key = self._resolve_saliency_key(
            saliency_store,
            label_index,
            label_index,
            label_index,
        )
        if resolved_key is None:
            available = self._available_saliency_keys(saliency_store)
            raise KeyError(
                f"Cannot map label {label_index!r} to saliency results. "
                f"Available saliency keys: {available}.",
            )
        return saliency_store[resolved_key]

    def iter_saliency_by_label(
        self,
        saliency_name: str,
    ) -> list[tuple[object, str, np.ndarray]]:
        """Return available saliency arrays paired with display labels.

        Training results may be keyed by model class indices (``0..n-1``),
        original event codes (for example ``769``), or stringified keys after
        loading older records.  The visualizers should display what exists
        instead of assuming a zero-based range from the epoch label count.
        """
        saliency_store = self._saliency_store(saliency_name)
        context = self._validated_saliency_context()
        label_map = getattr(self.epoch_data, "label_map", {}) or {}
        label_items = (
            list(self.render_data.class_map)
            if self.render_data is not None
            else list(context.class_map)
            if context is not None
            else list(label_map.items())
            if isinstance(label_map, dict)
            else []
        )
        expected_class_count = self._expected_class_count()
        identities = resolve_saliency_class_identities(
            saliency_store,
            label_items,
            expected_class_count=expected_class_count,
        )
        mapped: list[tuple[object, str, np.ndarray]] = []
        missing_labels: list[str] = []
        for identity in identities:
            saliency = saliency_store[identity.saliency_key]
            if not self._has_saliency_data(saliency):
                missing_labels.append(identity.display_name)
                continue
            mapped.append((identity.saliency_key, identity.display_name, saliency))
        if missing_labels:
            missing = ", ".join(missing_labels)
            raise ValueError(
                f"{saliency_name} is missing saliency for class(es): {missing}. "
                "Recompute saliency using an evaluation split that contains "
                "every trained class."
            )
        return mapped

    def _validated_saliency_context(self) -> SaliencyArtifactContext | None:
        """Validate scientific identity before interpreting saliency axes.

        Artifact producers bind identity before publication. Renderers only
        validate that immutable identity; they never assign meaning from the
        dataset that happens to be active. Minimal fake objects remain usable
        by old unit tests only when no persisted context is involved.
        """
        if self.render_data is not None:
            return None
        eval_record = cast(EvalRecord, self.eval_record)
        epoch_data = cast(Epochs, self.epoch_data)
        status = eval_record.saliency_context_status
        if (
            isinstance(epoch_data, Epochs)
            or eval_record.saliency_context is not None
            or status == "legacy_missing"
        ):
            return eval_record.validate_saliency_context(epoch_data)
        return None

    def _expected_class_count(self) -> int | None:
        if self.render_data is not None:
            return self.render_data.expected_class_count
        output = np.asarray(getattr(self.eval_record, "output", np.array([])))
        if output.ndim != 2 or output.shape[1] <= 0:
            return None
        return int(output.shape[1])

    def _saliency_store(self, saliency_name: str):
        if saliency_name is None:
            raise ValueError("Saliency name not provided")
        if self.render_data is not None:
            if saliency_name != self.render_data.method:
                raise ValueError(
                    f"Render publication contains {self.render_data.method}, "
                    f"not {saliency_name}."
                )
            return self.render_data.saliency_by_class
        eval_record = cast(EvalRecord, self.eval_record)
        if saliency_name == "Gradient":
            return eval_record.gradient
        if saliency_name == "Gradient * Input":
            return eval_record.gradient_input
        if saliency_name == "SmoothGrad":
            return eval_record.smoothgrad
        if saliency_name == "SmoothGrad_Squared":
            return eval_record.smoothgrad_sq
        if saliency_name == "VarGrad":
            return eval_record.vargrad
        raise NotImplementedError

    @staticmethod
    def _resolve_saliency_key(
        saliency_store,
        label_key: object,
        label_name: object,
        order_index: int,
    ) -> object | None:
        candidates: list[object] = [label_key, label_name]
        for value in (label_key, label_name):
            if not isinstance(value, (str, bytes, int, np.integer)):
                continue
            with contextlib.suppress(TypeError, ValueError):
                candidates.append(int(value))
        candidates.append(order_index)

        if isinstance(saliency_store, Mapping):
            for candidate in candidates:
                if candidate in saliency_store:
                    return candidate
                for available_key in saliency_store:
                    if str(available_key) == str(candidate):
                        return available_key
            return None

        try:
            store_len = len(saliency_store)
        except TypeError:
            return None
        for candidate in candidates:
            if (
                isinstance(candidate, (int, np.integer))
                and 0 <= int(candidate) < store_len
            ):
                return int(candidate)
        return None

    @staticmethod
    def _has_saliency_data(saliency) -> bool:
        try:
            return len(saliency) > 0
        except TypeError:
            return False

    @staticmethod
    def _iter_saliency_keys(saliency_store) -> list[object]:
        if isinstance(saliency_store, Mapping):
            return list(saliency_store.keys())
        try:
            return list(range(len(saliency_store)))
        except TypeError:
            return []

    @staticmethod
    def _available_saliency_keys(saliency_store) -> str:
        keys = Visualizer._iter_saliency_keys(saliency_store)
        if not keys:
            return "none"
        return ", ".join(map(str, keys))
