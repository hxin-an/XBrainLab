"""3-D saliency visualisation engine using PyVista and Qt threading."""

import contextlib
import os

import numpy as np
import pyvista as pv
from PyQt6.QtCore import QObject, pyqtSignal

from XBrainLab.backend.utils.logger import logger


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


def channel_convex_hull(ch_pos):
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
    return surf


class Saliency3DEngine(QObject):
    """Backend engine for 3-D saliency visualisation.

    Handles mesh loading, electrode-to-mesh mapping, saliency interpolation,
    and PyVista actor management.

    Attributes:
        model_loaded: Signal emitted once both head and brain meshes are
            loaded and ready.
        mesh_scale_scalar: Uniform scaling factor applied to meshes.
        head_mesh: Loaded head ``PolyData`` mesh, or ``None``.
        brain_mesh: Loaded brain ``PolyData`` mesh, or ``None``.
        saliency_cap: Triangulated cap mesh derived from channel positions.
        pos_on_3d: ``(N, 3)`` array of electrode positions in 3-D model space.
        saliency: ``(channels, time)`` saliency matrix for the current event.
        model_error: User-facing reason if required local meshes are unavailable.

    """

    model_loaded = pyqtSignal()

    def __init__(self, mesh_scale_scalar=0.8):
        """Initialise the engine and begin asynchronous model loading.

        Args:
            mesh_scale_scalar: Uniform scaling factor applied to all meshes.

        """
        super().__init__()
        self.mesh_scale_scalar = mesh_scale_scalar
        self.head_mesh = None
        self.brain_mesh = None
        self.saliency_cap = None

        self.pos_on_3d = None
        self.saliency = None
        self.model_error = ""

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
            self.head_mesh = pv.read(head_path)
            if self.head_mesh is None or not hasattr(self.head_mesh, "bounds"):
                logger.error("Invalid head model.")
                return

            self.brain_mesh = pv.read(brain_path)
            logger.info("3D Models loaded successfully.")
            self.model_loaded.emit()
        except Exception as e:
            logger.error("Failed to load meshes: %s", e)

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
        # Training records usually store saliency by class index, while EEG files
        # often keep original event codes such as 769/770. Resolve both shapes.
        saliency_store = self._saliency_store(eval_record, method)
        label_key = self._resolve_saliency_label_key(
            saliency_store,
            epoch_data,
            selected_event_name,
        )
        saliency_raw = np.asarray(saliency_store[label_key], dtype=float)
        if absolute:
            saliency_raw = np.abs(saliency_raw)
        self.saliency = saliency_raw.mean(axis=0)
        self.scalar_bar_range = [
            float(self.saliency.min()),
            float(self.saliency.max()),
        ]

        # get channel pos
        ch_pos = epoch_data.get_montage_position()
        electrode = epoch_data.get_channel_names()

        if ch_pos is None or len(ch_pos) == 0:
            raise ValueError("No montage positions found. Please set a montage first.")

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

        for idx, _ele in enumerate(electrode):
            if idx >= len(ch_pos):
                continue

            center = self._translated_channel_position(ch_pos[idx], trans)
            if center[1] > 0:
                center[2] += 0.007
            pos_on_3d.append(center)

        if not pos_on_3d:
            raise ValueError("Failed to map any channels to 3D positions.")

        self.pos_on_3d = np.asarray(pos_on_3d)

        # Prepare Meshes
        scaling = np.ones(3) * self.mesh_scale_scalar

        # We clone to avoid mutating cached original meshes repeatedly
        # if this is called multiple times.
        # Or just scale once? The original code scaled inplace.
        # Let's clone for safety if reusable.
        if self.head_mesh is None or self.brain_mesh is None:
            raise RuntimeError("Meshes not loaded")

        self.head_scaled = self.head_mesh.copy().scale(scaling, inplace=False)
        self.brain_scaled = (
            self.brain_mesh.copy().scale(scaling * 0.001, inplace=False).triangulate()
        )
        self.saliency_cap = channel_convex_hull(self.pos_on_3d).scale(
            scaling,
            inplace=False,
        )

        self.scalar_buffer = np.zeros(self.saliency_cap.n_points)

        return self.saliency.shape[0]  # Number of channels

    @staticmethod
    def _translated_channel_position(position, translation):
        """Return a numeric channel position after applying 3-D translation."""
        return np.asarray(position, dtype=float) + np.asarray(translation, dtype=float)

    @staticmethod
    def _resolve_saliency_label_key(saliency_store, epoch_data, selected_event_name):
        """Map an EEG event name/code to the saliency key used by training results."""
        event_id = getattr(epoch_data, "event_id", {}) or {}
        event_names = list(event_id.keys())
        event_value = event_id.get(selected_event_name)
        try:
            event_order_index = event_names.index(selected_event_name)
        except ValueError:
            event_order_index = None

        candidates = [event_value, selected_event_name]
        with contextlib.suppress(TypeError, ValueError):
            candidates.append(int(selected_event_name))
        if event_order_index is not None:
            candidates.append(event_order_index)

        if isinstance(saliency_store, dict):
            for candidate in candidates:
                if candidate is None:
                    continue
                if candidate in saliency_store:
                    return candidate
                for key in saliency_store:
                    if str(key) == str(candidate):
                        return key
            if len(saliency_store) == 1:
                return next(iter(saliency_store))
            available = ", ".join(map(str, saliency_store.keys()))
        else:
            try:
                gradient_len = len(saliency_store)
            except TypeError:
                gradient_len = 0
            for candidate in candidates:
                if (
                    isinstance(candidate, (int, np.integer))
                    and 0 <= int(candidate) < gradient_len
                ):
                    return candidate
            available = f"0..{max(gradient_len - 1, 0)}"

        raise KeyError(
            "Cannot map EEG event "
            f"{selected_event_name!r} "
            f"(event code {event_value!r}) to saliency results. "
            f"Available saliency keys: {available}."
        )

    @staticmethod
    def _saliency_store(eval_record, method):
        """Return saliency data for the selected 3-D method."""
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

    def update_scalars(self, timestamp, neighbor=3):
        """Update scalar values on the saliency cap for a given time point.

        For each vertex of the cap mesh the *neighbor* nearest channels are
        found and their saliency values are combined using inverse-distance
        weighting.

        Args:
            timestamp: Time-step index into the saliency matrix.
            neighbor: Number of nearest channels to use for interpolation.

        Returns:
            np.ndarray | None: Interpolated scalar array with one value per
                cap-mesh vertex, or ``None`` if data is not yet available.

        """
        if self.saliency is None or self.saliency_cap is None or self.pos_on_3d is None:
            return None

        t_idx = int(timestamp)
        # Clamp t_idx
        if t_idx >= self.saliency.shape[1]:
            t_idx = self.saliency.shape[1] - 1

        current_saliency = self.saliency[:, t_idx]

        points = self.saliency_cap.points
        # For each point on the cap mesh, find k-nearest channels and interpolate.
        # Uses a simple distance matrix approach for vectorized computation.

        scaled_channels = self.pos_on_3d * self.mesh_scale_scalar
        neighbor_count = min(max(int(neighbor), 1), scaled_channels.shape[0])
        distances = np.linalg.norm(
            points[:, None, :] - scaled_channels[None, :, :],
            axis=2,
        )
        nearest_indices = np.argpartition(
            distances,
            neighbor_count - 1,
            axis=1,
        )[:, :neighbor_count]
        nearest_distances = np.take_along_axis(distances, nearest_indices, axis=1)
        nearest_values = current_saliency[nearest_indices]
        weights = 1 / (nearest_distances + 1e-8)
        weights = weights / weights.sum(axis=1, keepdims=True)
        return (weights * nearest_values).sum(axis=1)
