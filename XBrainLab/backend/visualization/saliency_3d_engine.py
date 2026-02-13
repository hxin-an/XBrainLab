import os

import numpy as np
import pyvista as pv
import requests
from PyQt6.QtCore import QObject, QThread, pyqtSignal
from scipy.spatial import ConvexHull  # noqa: F401

from XBrainLab.backend.utils.logger import logger


def inverse_dist_weighted_sum(dist, val):
    weight = 1 / (dist + 1e-8)
    weight = weight / weight.sum()
    return (weight * val).sum()


def channel_convex_hull(ch_pos):
    # hull = ConvexHull(ch_pos) # Unused
    # Extract the vertices of the convex hull
    # Extract the vertices of the convex hull
    # vertices = ch_pos[hull.vertices]  # Unused variable F841
    # Create pyvista PolyData from the vertices
    # Note: ConvexHull just gives vertices. We need triangulation for a surface.
    # Note: ConvexHull just gives vertices. We need triangulation for a surface.
    # PyVista has a delaunay_3d or similar, but often PolyData(vertices)
    # delaunay_3d().extract_surface() works.

    # Original logic was simpler or assumed pv.PolyData can fit?
    # Let's inspect original usage:
    # self.saliency_cap = channel_convex_hull(self.pos_on_3d).scale(...)
    # It likely returned a PyVista mesh.

    cloud = pv.PolyData(ch_pos)
    # Delaunay 2D is better for surface reconstruction of EEG cap (manifold)
    # Delaunay 3D tries to make a volume, which fails for scalp points.
    surf = cloud.delaunay_2d()
    return surf


class ModelDownloadThread(QThread):
    download_finished = pyqtSignal(str)  # formatted path or error

    def __init__(self, url, dest_path):
        super().__init__()
        self.url = url
        self.dest_path = dest_path

    def run(self):
        try:
            logger.info(f"Downloading {os.path.basename(self.dest_path)}...")
            with requests.get(self.url, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(self.dest_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            logger.info(f"Downloaded {self.dest_path}")
            self.download_finished.emit(self.dest_path)
        except Exception as e:
            logger.error(f"Download failed: {e}")
            self.download_finished.emit(f"Error: {e}")


# Robustness: Keep separate references to prevent premature QThread destruction
SALIENCY_DOWNLOAD_THREADS = set()


class Saliency3DEngine(QObject):
    """
    Backend engine for Saliency 3D visualization.
    Handles mesh loading, data processing, and PyVista actor management.
    """

    model_loaded = pyqtSignal()

    def __init__(self, mesh_scale_scalar=0.8):
        super().__init__()
        self.mesh_scale_scalar = mesh_scale_scalar
        self.head_mesh = None
        self.brain_mesh = None
        self.saliency_cap = None

        self.pos_on_3d = None
        self.saliency = None

        self.download_threads = []

        # Load models asynchronously
        self._load_models()

    def _load_models(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        model_dir = os.path.join(current_dir, "3Dmodel")

        if not os.path.exists(model_dir):
            os.makedirs(model_dir)

        fn_ply = ["brain.ply", "head.ply"]
        gitrepo_loc = "https://raw.githubusercontent.com/CECNL/XBrainLab/main/XBrainLab/backend/visualization/3Dmodel/"

        missing_files = []
        for fn in fn_ply:
            file_path = os.path.join(model_dir, fn)
            if not os.path.exists(file_path) or os.path.getsize(file_path) < 1024:
                missing_files.append((fn, file_path))

        if missing_files:
            missing_list = [f[0] for f in missing_files]
            msg = f"Missing 3D models: {missing_list}. Starting background download..."
            logger.info(msg)
            for fn, path in missing_files:
                thread = ModelDownloadThread(gitrepo_loc + fn, path)
                thread.download_finished.connect(self._on_download_complete)

                # Robustness: Prevent QThread: Destroyed by keeping global ref
                SALIENCY_DOWNLOAD_THREADS.add(thread)
                # Use QThread's native finished signal (0 args) for cleanup
                # Use QThread's native finished signal (0 args) for cleanup
                # Fix B023: bind thread=thread
                thread.finished.connect(
                    lambda t=thread: SALIENCY_DOWNLOAD_THREADS.discard(t)
                )

                self.download_threads.append(thread)
                thread.start()
        else:
            self._init_meshes(model_dir)

    def _on_download_complete(self, result):
        if "Error" in result:
            logger.error(result)
            return

        # Check if all downloads finished?
        # For simplicity, try to load whenever one finishes, or wait for all.
        # Minimalist approach: Try loading models again.
        current_dir = os.path.dirname(os.path.abspath(__file__))
        model_dir = os.path.join(current_dir, "3Dmodel")

        # Check if bot exist now
        head_path = os.path.join(model_dir, "head.ply")
        brain_path = os.path.join(model_dir, "brain.ply")

        # Ensure sizes valid (SIM102 combined if)
        if (
            os.path.exists(head_path)
            and os.path.exists(brain_path)
            and os.path.getsize(head_path) > 1024
            and os.path.getsize(brain_path) > 1024
        ):
            self._init_meshes(model_dir)

    def _init_meshes(self, model_dir):
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
            logger.error(f"Failed to load meshes: {e}")

    def process_data(self, eval_record, epoch_data, selected_event_name):
        """Process epoch data and eval record to prepare for visualization."""
        # get saliency
        label_index = epoch_data.event_id[selected_event_name]
        saliency_raw = eval_record.gradient[label_index]
        self.saliency = saliency_raw.mean(axis=0)
        self.scalar_bar_range = [self.saliency.min(), self.saliency.max()]

        # self.max_time = self.saliency.shape[-1] # Unused?

        # get channel pos
        ch_pos = epoch_data.get_montage_position()
        electrode = epoch_data.get_channel_names()

        if ch_pos is None or len(ch_pos) == 0:
            raise ValueError("No montage positions found. Please set a montage first.")

        # get electrode pos in 3d
        pos_on_3d = []
        # trans Cz to [0, 0, 0]
        # Note: These values are tuned for the specific head model
        if self.head_mesh is None:
            raise RuntimeError("Head mesh not loaded")

        trans = [
            -0.0004,
            0.00917,
            self.head_mesh.bounds[5] - 0.10024,
        ]

        # Hull was unused variable F841
        # hull = self.head_mesh.copy()

        for ele in electrode:
            # Safety check for index
            if ele not in electrode:
                continue
            idx = electrode.index(ele)
            if idx >= len(ch_pos):
                continue

            center = ch_pos[idx] + trans
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
            scaling, inplace=False
        )

        self.scalar_buffer = np.zeros(self.saliency_cap.n_points)

        return self.saliency.shape[0]  # Number of channels

    def update_scalars(self, timestamp, neighbor=3):
        """
        Update scalar values on the saliency cap based on timestamp.
        Returns the updated scalar array.
        """
        if self.saliency is None or self.saliency_cap is None:
            return None

        t_idx = int(timestamp)
        # Clamp t_idx
        if t_idx >= self.saliency.shape[1]:
            t_idx = self.saliency.shape[1] - 1

        current_saliency = self.saliency[:, t_idx]

        points = self.saliency_cap.points
        # For each point on the cap mesh, find k-nearest channels and interpolate
        # Note: This is computationally expensive to do in Python loop for many points.
        # But keeping original logic for fidelity.

        # Optimization: use KDTree if points are static?
        # For direct port, keep logic but maybe vectorizable?
        # Original logic:
        # for i in range(mesh.n_points):
        #    ... find k nearest chs ...
        #    val = inverse_dist_weighted_sum(...)

        # Let's vectorize simply if possible, or stick to loop for safety.
        # The mesh points count might be small (hundreds?).

        scalars = np.zeros(points.shape[0])

        # Simple distance matrix: Points(N,3) vs Channels(M,3)
        # d[i, j] = dist between point i and channel j
        # Memory heavy if N is huge.

        for i, point in enumerate(points):
            diff = self.pos_on_3d * self.mesh_scale_scalar - point
            # pos_on_3d needs scaling to match mesh?
            # Yes, s.chs uses pos_on_3d * mesh_scale_scalar

            dist_sq = np.sum(diff**2, axis=1)
            dist = np.sqrt(dist_sq)

            # Get k nearest
            idx_sorted = np.argsort(dist)[:neighbor]
            nearest_dist = dist[idx_sorted]
            nearest_vals = current_saliency[idx_sorted]

            scalars[i] = inverse_dist_weighted_sum(nearest_dist, nearest_vals)

        return scalars
