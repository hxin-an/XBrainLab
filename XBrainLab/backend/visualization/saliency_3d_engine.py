"""Thread-agnostic 3-D saliency visualisation engine using PyVista."""

import os
import threading
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar, cast

import numpy as np
import pyvista as pv

from XBrainLab.backend.application.saliency_render import SaliencyRenderData
from XBrainLab.backend.dataset import Epochs
from XBrainLab.backend.training.record.eval import EvalRecord
from XBrainLab.backend.training.saliency_provenance import SaliencyArtifactContext
from XBrainLab.backend.utils.logger import logger

from .base import SaliencyClassIdentity, resolve_saliency_class_identities
from .saliency_semantics import saliency_color_scale


@dataclass(frozen=True)
class _StaticMeshAssets:
    head_mesh: pv.PolyData
    brain_mesh: pv.PolyData
    head_scaled: pv.PolyData
    brain_scaled: pv.PolyData


@dataclass(frozen=True)
class _InterpolationWeights:
    nearest_indices: np.ndarray
    weights: np.ndarray


def inverse_dist_weighted_sum(dist, val):
    """Compute an inverse-distance weighted sum of values.

    Args:
        dist: Array of distances from the query point to each source.
        val: Array of scalar values at each source.

    Returns:
        float: Weighted sum where closer sources contribute more.

    """
    weight = 1 / (dist + 1e-8)
    weight = weight / weight.sum()
    return (weight * val).sum()


def channel_convex_hull(ch_pos: np.ndarray) -> pv.PolyData:
    """Build a triangulated surface mesh from channel positions.

    Uses Delaunay 2-D triangulation on a point cloud to create a surface
    suitable for scalp-level EEG visualisation.

    Args:
        ch_pos: ``(N, 3)`` array of 3-D channel positions.

    Returns:
        pyvista.PolyData: Triangulated surface mesh.

    """
    cloud = pv.PolyData(ch_pos)
    # Delaunay 2D is better for surface reconstruction of EEG cap (manifold)
    # Delaunay 3D tries to make a volume, which fails for scalp points.
    surf = cloud.delaunay_2d()
    return cast(pv.PolyData, surf)


class Saliency3DEngine:
    """Backend engine for 3-D saliency visualisation.

    Handles mesh loading, electrode-to-mesh mapping, saliency interpolation,
    and PyVista actor management.

    Attributes:
        mesh_scale_scalar: Uniform scaling factor applied to meshes.
        head_mesh: Loaded head ``PolyData`` mesh, or ``None``.
        brain_mesh: Loaded brain ``PolyData`` mesh, or ``None``.
        saliency_cap: Triangulated cap mesh derived from channel positions.
        pos_on_3d: ``(N, 3)`` array of electrode positions in 3-D model space.
        saliency: ``(channels, time)`` saliency matrix for the current event.
        model_error: User-facing reason if required local meshes are unavailable.

    """

    _MAX_MESH_CACHE_ENTRIES: ClassVar[int] = 1
    _mesh_cache_lock: ClassVar[threading.RLock] = threading.RLock()
    _mesh_cache: ClassVar[OrderedDict[tuple[object, ...], _StaticMeshAssets]] = (
        OrderedDict()
    )
    _MAX_INTERPOLATION_CACHE_ENTRIES: ClassVar[int] = 4
    _interpolation_cache_lock: ClassVar[threading.RLock] = threading.RLock()
    _interpolation_cache: ClassVar[
        OrderedDict[tuple[object, ...], _InterpolationWeights]
    ] = OrderedDict()

    def __init__(self, mesh_scale_scalar=0.8):
        """Initialise the engine and load the required local mesh assets.

        Args:
            mesh_scale_scalar: Uniform scaling factor applied to all meshes.

        """
        self.mesh_scale_scalar = mesh_scale_scalar
        self.head_mesh = None
        self.brain_mesh = None
        self.head_scaled = None
        self.brain_scaled = None
        self.saliency_cap = None

        self.pos_on_3d = None
        self.saliency = None
        self.time_axis_seconds = np.array([], dtype=float)
        self.model_error = ""
        self._prepared_interpolation_key: tuple[object, ...] | None = None
        self._prepared_interpolation: _InterpolationWeights | None = None
        self._prepared_interpolation_neighbor_count: int | None = None

        self._load_models()

    def _load_models(self):
        """Locate local 3-D model files without performing network downloads."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        model_dir = os.path.join(current_dir, "3Dmodel")

        fn_ply = ["brain.ply", "head.ply"]

        missing_files = []
        for fn in fn_ply:
            file_path = os.path.join(model_dir, fn)
            if not os.path.exists(file_path) or os.path.getsize(file_path) < 1024:
                missing_files.append((fn, file_path))

        if missing_files:
            missing_list = [f[0] for f in missing_files]
            self.model_error = (
                "3D head model assets are not installed: "
                + ", ".join(missing_list)
                + ". Install the local 3Dmodel assets before opening 3D saliency."
            )
            logger.warning(self.model_error)
            return
        self._init_meshes(model_dir)

    def _init_meshes(self, model_dir):
        """Read head and brain PLY meshes from *model_dir*.

        Args:
            model_dir: Directory containing ``head.ply`` and ``brain.ply``.

        """
        head_path = os.path.join(model_dir, "head.ply")
        brain_path = os.path.join(model_dir, "brain.ply")

        try:
            cache_key = self._mesh_cache_key(head_path, brain_path)
            assets = self._cached_mesh_assets(
                cache_key=cache_key,
                head_path=head_path,
                brain_path=brain_path,
            )
            self.head_mesh = assets.head_mesh
            self.brain_mesh = assets.brain_mesh
            self.head_scaled = assets.head_scaled
            self.brain_scaled = assets.brain_scaled
        except Exception as e:
            logger.error("Failed to load meshes: %s", e)

    def _mesh_cache_key(
        self,
        head_path: str,
        brain_path: str,
    ) -> tuple[object, ...]:
        return (
            *self._asset_signature(head_path),
            *self._asset_signature(brain_path),
            float(self.mesh_scale_scalar),
        )

    @staticmethod
    def _asset_signature(path: str) -> tuple[object, ...]:
        resolved = os.path.realpath(path)
        metadata = os.stat(resolved)
        return (
            resolved,
            int(metadata.st_size),
            int(metadata.st_mtime_ns),
        )

    def _cached_mesh_assets(
        self,
        *,
        cache_key: tuple[object, ...],
        head_path: str,
        brain_path: str,
    ) -> _StaticMeshAssets:
        with self._mesh_cache_lock:
            cached = self._mesh_cache.get(cache_key)
            if cached is not None:
                self._mesh_cache.move_to_end(cache_key)
                return cached

            head_mesh = cast(pv.PolyData, pv.read(head_path))
            if head_mesh is None or not hasattr(head_mesh, "bounds"):
                raise ValueError("Invalid head model.")
            brain_mesh = cast(pv.PolyData, pv.read(brain_path))
            if brain_mesh is None or not hasattr(brain_mesh, "bounds"):
                raise ValueError("Invalid brain model.")
            scaling = np.ones(3) * self.mesh_scale_scalar
            head_scaled = cast(
                pv.PolyData,
                head_mesh.copy().scale(scaling, inplace=False),
            )
            brain_scaled = cast(
                pv.PolyData,
                brain_mesh.copy().scale(scaling * 0.001, inplace=False).triangulate(),
            )
            assets = _StaticMeshAssets(
                head_mesh=head_mesh,
                brain_mesh=brain_mesh,
                head_scaled=head_scaled,
                brain_scaled=brain_scaled,
            )
            self._mesh_cache[cache_key] = assets
            while len(self._mesh_cache) > self._MAX_MESH_CACHE_ENTRIES:
                self._mesh_cache.popitem(last=False)
            logger.info("3D Models loaded successfully.")
            return assets

    @classmethod
    def _clear_mesh_cache(cls) -> None:
        """Release process-local static mesh references (used by lifecycle tests)."""
        with cls._mesh_cache_lock:
            cls._mesh_cache.clear()

    @classmethod
    def _clear_interpolation_cache(cls) -> None:
        """Release process-local interpolation arrays (used by lifecycle tests)."""
        with cls._interpolation_cache_lock:
            cls._interpolation_cache.clear()

    def process_data(
        self,
        eval_record,
        epoch_data,
        selected_event_name,
        *,
        method="Gradient",
        absolute=False,
    ):
        """Process epoch data and evaluation record for 3-D visualisation.

        Computes saliency values, maps channels onto the 3-D head model,
        builds scaled meshes, and prepares the interpolation cap.

        Args:
            eval_record: Evaluation record containing saliency data.
            epoch_data: Epoch data providing channel names, montage positions
                and event IDs.
            selected_event_name: Name of the event class to visualise.
            method: Saliency method to render.
            absolute: Whether to render absolute saliency magnitudes.

        Returns:
            int: Number of channels in the saliency matrix.

        Raises:
            ValueError: If no montage positions are available or no channels
                could be mapped.
            RuntimeError: If the head or brain mesh has not been loaded.

        """
        render_data = (
            eval_record if isinstance(eval_record, SaliencyRenderData) else None
        )
        if render_data is not None:
            epoch_data = render_data
        context: SaliencyArtifactContext | None = None
        context_status = getattr(
            eval_record,
            "saliency_context_status",
            "runtime_unbound",
        )
        context_value = getattr(eval_record, "saliency_context", None)
        validate_context = getattr(eval_record, "validate_saliency_context", None)
        if (
            isinstance(eval_record, EvalRecord)
            and callable(validate_context)
            and (
                isinstance(epoch_data, Epochs)
                or context_value is not None
                or context_status == "legacy_missing"
            )
        ):
            context = cast(SaliencyArtifactContext, validate_context(epoch_data))
        # Training records usually store saliency by class index, while EEG files
        # often keep original event codes such as 769/770. Resolve both shapes.
        saliency_store = self._saliency_store(eval_record, method)
        label_key = self._resolve_saliency_label_key(
            saliency_store,
            epoch_data,
            selected_event_name,
            class_items=(
                render_data.class_map
                if render_data is not None
                else context.class_map
                if context is not None
                else None
            ),
        )
        saliency_raw = np.asarray(saliency_store[label_key])
        if not self._has_saliency_data(saliency_raw):
            raise KeyError(
                "No saliency samples are available for EEG event "
                f"{selected_event_name!r}. Select another trained class or "
                "regenerate saliency after training.",
            )
        if absolute:
            saliency_raw = np.abs(saliency_raw)
        # Preserve the previous float64 accumulator without first duplicating
        # the complete epoch tensor as float64.
        saliency = saliency_raw.mean(axis=0, dtype=np.float64)

        ch_pos = epoch_data.get_montage_position()
        electrode = epoch_data.get_channel_names()

        if ch_pos is None or len(ch_pos) == 0:
            raise ValueError("No montage positions found. Please set a montage first.")
        if saliency.ndim != 2:
            raise ValueError(
                "3D saliency must resolve to a channels-by-time matrix; "
                f"received shape {saliency.shape}."
            )
        identity_counts = {
            "EEG channel names": len(electrode),
            "montage positions": len(ch_pos),
            "saliency channels": int(saliency.shape[0]),
        }
        if len(set(identity_counts.values())) != 1:
            details = ", ".join(
                f"{name}={count}" for name, count in identity_counts.items()
            )
            raise ValueError(
                "3D channel identity mismatch: "
                f"{details}. Set a matching montage or recompute saliency."
            )

        time_axis_seconds = self._build_time_axis_seconds(
            epoch_data,
            sample_count=int(saliency.shape[1]),
        )

        self.saliency = saliency
        self.time_axis_seconds = time_axis_seconds
        self.cmap_name, color_min, color_max = saliency_color_scale(
            method,
            self.saliency,
            absolute=absolute,
            normalized=bool(getattr(epoch_data, "normalized", False)),
        )
        self.scalar_bar_range = [color_min, color_max]

        # get electrode pos in 3d
        pos_on_3d = []
        # trans Cz to [0, 0, 0]
        # Note: These values are tuned for the specific head model
        if self.model_error:
            raise RuntimeError(self.model_error)
        if self.head_mesh is None:
            raise RuntimeError("Head mesh not loaded")

        trans = np.asarray(
            [
                -0.0004,
                0.00917,
                self.head_mesh.bounds[5] - 0.10024,
            ],
            dtype=float,
        )

        for position in ch_pos:
            center = self._translated_channel_position(position, trans)
            if center[1] > 0:
                center[2] += 0.007
            pos_on_3d.append(center)

        if not pos_on_3d:
            raise ValueError("Failed to map any channels to 3D positions.")

        self.pos_on_3d = np.asarray(pos_on_3d)

        if self.head_mesh is None or self.brain_mesh is None:
            raise RuntimeError("Meshes not loaded")
        self._ensure_scaled_meshes()
        self.saliency_cap = cast(
            pv.PolyData,
            channel_convex_hull(self.pos_on_3d).scale(
                np.ones(3) * self.mesh_scale_scalar,
                inplace=False,
            ),
        )

        self.scalar_buffer = np.zeros(self.saliency_cap.n_points)
        self._prepared_interpolation_key = None
        self._prepared_interpolation = None
        self._prepared_interpolation_neighbor_count = None
        self._prepare_interpolation_weights(neighbor=3)

        return self.saliency.shape[0]  # Number of channels

    def _ensure_scaled_meshes(self) -> None:
        """Prepare static meshes when tests or callers inject uncached assets."""
        scaling = np.ones(3) * self.mesh_scale_scalar
        if self.head_scaled is None:
            if self.head_mesh is None:
                raise RuntimeError("Head mesh not loaded")
            self.head_scaled = self.head_mesh.copy().scale(scaling, inplace=False)
        if self.brain_scaled is None:
            if self.brain_mesh is None:
                raise RuntimeError("Brain mesh not loaded")
            self.brain_scaled = (
                self.brain_mesh.copy()
                .scale(scaling * 0.001, inplace=False)
                .triangulate()
            )

    @staticmethod
    def _build_time_axis_seconds(epoch_data, *, sample_count: int) -> np.ndarray:
        """Build the epoch-relative seconds axis represented by saliency samples."""
        if sample_count < 1:
            raise ValueError("3D saliency requires at least one time sample.")
        model_args = epoch_data.get_model_args()
        sfreq = float(model_args["sfreq"])
        if not np.isfinite(sfreq) or sfreq <= 0:
            raise ValueError(
                "Sampling frequency must be finite and positive for 3D saliency."
            )
        epoch_start = float(getattr(epoch_data, "tmin", 0.0))
        if not np.isfinite(epoch_start):
            raise ValueError("Epoch start time must be finite for 3D saliency.")
        return epoch_start + np.arange(sample_count, dtype=float) / sfreq

    @property
    def time_range_seconds(self) -> tuple[float, float]:
        """Return the first and last epoch-relative times represented by saliency."""
        if self.time_axis_seconds.size == 0:
            raise RuntimeError("3D saliency time axis is not initialized.")
        return (
            float(self.time_axis_seconds[0]),
            float(self.time_axis_seconds[-1]),
        )

    @property
    def initial_time_seconds(self) -> float:
        """Return the initial slider value in epoch-relative seconds."""
        return self.time_range_seconds[0]

    def sample_index_for_time(self, time_seconds: float) -> int:
        """Return the nearest sample index, clamped to the represented epoch."""
        if self.time_axis_seconds.size == 0:
            raise RuntimeError("3D saliency time axis is not initialized.")
        requested_time = float(time_seconds)
        if not np.isfinite(requested_time):
            raise ValueError("3D saliency time must be finite.")

        insertion_index = int(
            np.searchsorted(self.time_axis_seconds, requested_time, side="left")
        )
        if insertion_index <= 0:
            return 0
        if insertion_index >= self.time_axis_seconds.size:
            return int(self.time_axis_seconds.size - 1)

        before_index = insertion_index - 1
        before_distance = requested_time - self.time_axis_seconds[before_index]
        after_distance = self.time_axis_seconds[insertion_index] - requested_time
        if before_distance <= after_distance:
            return before_index
        return insertion_index

    @staticmethod
    def _translated_channel_position(position, translation):
        """Return a numeric channel position after applying 3-D translation."""
        return np.asarray(position, dtype=float) + np.asarray(translation, dtype=float)

    @staticmethod
    def _resolve_saliency_label_key(
        saliency_store,
        epoch_data,
        selected_event_name,
        *,
        class_items=None,
    ):
        """Map an EEG event name/code to the saliency key used by training results."""
        event_id = getattr(epoch_data, "event_id", {}) or {}
        event_value = event_id.get(selected_event_name)
        label_items = (
            list(class_items)
            if class_items is not None
            else [(value, name) for name, value in event_id.items()]
        )
        identities = resolve_saliency_class_identities(saliency_store, label_items)
        matches = [
            identity
            for identity in identities
            if Saliency3DEngine._identity_matches_selection(
                identity,
                selected_event_name,
                event_value,
            )
        ]
        if len(matches) > 1:
            raise KeyError(
                f"Selected class {selected_event_name!r} maps to multiple saliency "
                "classes. Recompute saliency with normalized class metadata."
            )
        if matches:
            resolved_key = matches[0].saliency_key
            if Saliency3DEngine._has_saliency_data(saliency_store[resolved_key]):
                return resolved_key
            raise KeyError(
                f"No saliency for selected class {selected_event_name!r}. "
                "Recompute saliency using an evaluation split that contains "
                "this class."
            )

        available = ", ".join(map(str, Saliency3DEngine._saliency_keys(saliency_store)))
        raise KeyError(
            "Cannot map EEG event "
            f"{selected_event_name!r} "
            f"(event code {event_value!r}) to saliency results. "
            f"Available saliency keys: {available}."
        )

    @staticmethod
    def _identity_matches_selection(
        identity: SaliencyClassIdentity,
        selected_event_name: object,
        selected_event_code: object,
    ) -> bool:
        if identity.display_name == str(selected_event_name):
            return True
        if selected_event_code is not None:
            return str(identity.event_code) == str(selected_event_code)
        return str(identity.saliency_key) == str(selected_event_name)

    @staticmethod
    def _saliency_keys(saliency_store) -> list[object]:
        if isinstance(saliency_store, Mapping):
            return list(saliency_store)
        try:
            return list(range(len(saliency_store)))
        except TypeError:
            return []

    @staticmethod
    def _has_saliency_data(value) -> bool:
        try:
            return len(value) > 0
        except TypeError:
            return False

    @staticmethod
    def _saliency_store(eval_record, method):
        """Return saliency data for the selected 3-D method."""
        if isinstance(eval_record, SaliencyRenderData):
            if method != eval_record.method:
                raise ValueError(
                    f"Render publication contains {eval_record.method}, not {method}."
                )
            return eval_record.saliency_by_class
        if method == "Gradient":
            store = getattr(eval_record, "gradient", None)
        elif method == "Gradient * Input":
            store = getattr(eval_record, "gradient_input", None)
        elif method == "SmoothGrad":
            store = getattr(eval_record, "smoothgrad", None)
        elif method == "SmoothGrad_Squared":
            store = getattr(eval_record, "smoothgrad_sq", None)
        elif method == "VarGrad":
            store = getattr(eval_record, "vargrad", None)
        else:
            raise ValueError(f"Unknown saliency method: {method}")
        if store is None:
            raise KeyError(f"No {method} saliency is available for this evaluation.")
        return store

    def update_scalars(self, sample_index, neighbor=3):
        """Update scalar values on the saliency cap for a given time point.

        Reuses the prepared *neighbor* nearest channels and inverse-distance
        weights for each cap vertex, then applies the selected time sample.

        Args:
            sample_index: Zero-based sample index into the saliency matrix.
            neighbor: Number of nearest channels to use for interpolation.

        Returns:
            np.ndarray | None: Interpolated scalar array with one value per
                cap-mesh vertex, or ``None`` if data is not yet available.

        """
        if self.saliency is None or self.saliency_cap is None or self.pos_on_3d is None:
            return None

        t_idx = min(max(int(sample_index), 0), self.saliency.shape[1] - 1)

        current_saliency = self.saliency[:, t_idx]

        neighbor_count = min(
            max(int(neighbor), 1),
            int(self.pos_on_3d.shape[0]),
        )
        interpolation = self._prepared_interpolation
        if (
            interpolation is None
            or self._prepared_interpolation_neighbor_count != neighbor_count
        ):
            interpolation = self._prepare_interpolation_weights(neighbor=neighbor)
        nearest_values = current_saliency[interpolation.nearest_indices]
        return (interpolation.weights * nearest_values).sum(axis=1)

    def _prepare_interpolation_weights(self, *, neighbor: int) -> _InterpolationWeights:
        """Prepare immutable geometry weights before the engine reaches the UI."""
        if self.saliency_cap is None or self.pos_on_3d is None:
            raise RuntimeError("3D saliency geometry is not initialized.")

        points = np.ascontiguousarray(np.asarray(self.saliency_cap.points, dtype=float))
        scaled_channels = np.ascontiguousarray(
            np.asarray(self.pos_on_3d, dtype=float) * self.mesh_scale_scalar
        )
        if points.ndim != 2 or points.shape[1] != 3:
            raise ValueError("3D saliency cap points must have shape (N, 3).")
        if scaled_channels.ndim != 2 or scaled_channels.shape[1] != 3:
            raise ValueError("3D channel positions must have shape (N, 3).")
        if points.shape[0] == 0 or scaled_channels.shape[0] == 0:
            raise ValueError("3D interpolation requires cap and channel positions.")

        neighbor_count = min(max(int(neighbor), 1), scaled_channels.shape[0])
        cache_key = self._interpolation_cache_key(
            points,
            scaled_channels,
            neighbor_count=neighbor_count,
        )
        if (
            self._prepared_interpolation_key == cache_key
            and self._prepared_interpolation is not None
        ):
            return self._prepared_interpolation

        with self._interpolation_cache_lock:
            prepared = self._interpolation_cache.get(cache_key)
            if prepared is None:
                distances = np.linalg.norm(
                    points[:, None, :] - scaled_channels[None, :, :],
                    axis=2,
                )
                nearest_indices = np.argpartition(
                    distances,
                    neighbor_count - 1,
                    axis=1,
                )[:, :neighbor_count].copy()
                nearest_distances = np.take_along_axis(
                    distances,
                    nearest_indices,
                    axis=1,
                )
                weights = 1 / (nearest_distances + 1e-8)
                weights = weights / weights.sum(axis=1, keepdims=True)
                nearest_indices.setflags(write=False)
                weights.setflags(write=False)
                prepared = _InterpolationWeights(
                    nearest_indices=nearest_indices,
                    weights=weights,
                )
                self._interpolation_cache[cache_key] = prepared
                while (
                    len(self._interpolation_cache)
                    > self._MAX_INTERPOLATION_CACHE_ENTRIES
                ):
                    self._interpolation_cache.popitem(last=False)
            else:
                self._interpolation_cache.move_to_end(cache_key)

        self._prepared_interpolation_key = cache_key
        self._prepared_interpolation = prepared
        self._prepared_interpolation_neighbor_count = neighbor_count
        return prepared

    @staticmethod
    def _interpolation_cache_key(
        points: np.ndarray,
        scaled_channels: np.ndarray,
        *,
        neighbor_count: int,
    ) -> tuple[object, ...]:
        """Return an exact geometry key without retaining mutable array aliases."""
        return (
            points.shape,
            points.dtype.str,
            points.tobytes(order="C"),
            scaled_channels.shape,
            scaled_channels.dtype.str,
            scaled_channels.tobytes(order="C"),
            neighbor_count,
        )
