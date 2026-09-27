import contextlib
from typing import Any, cast

import pyvista as pv
from matplotlib import colormaps

from XBrainLab.backend.application.saliency_render import SaliencyRenderData
from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.visualization.saliency_3d_engine import Saliency3DEngine
from XBrainLab.ui.styles.theme import Theme

bgcolor = Theme.BACKGROUND_MID
mesh_scale_scalar = 0.8


class Saliency3D:
    def __init__(
        self,
        *,
        plotter,
        prepared_engine: Saliency3DEngine,
        prepared_channel_count: int,
    ):
        """Install a background-prepared engine in the view-owned Qt plotter."""
        self.show_electrodes = True
        self.show_head = True
        self.engine = prepared_engine
        self.channel_count = prepared_channel_count
        self.cmap = colormaps[self.engine.cmap_name]
        self.param = {"sample_index": 0}
        self.plotter = plotter
        self.plotter.clear()
        self.plotter.background_color = bgcolor

        self.channelActor: list[pv.Actor] = []
        self.headActor = None
        self._orientation_widget: Any | None = None

        self._init_actors()
        self.update()

    @staticmethod
    def prepare_engine(
        render_data: SaliencyRenderData,
        selected_event_name,
        *,
        method="Gradient",
        absolute=False,
    ) -> tuple[Saliency3DEngine, int]:
        engine = Saliency3DEngine(mesh_scale_scalar=mesh_scale_scalar)
        channel_count = engine.process_data(
            render_data,
            selected_event_name,
            method=method,
            absolute=absolute,
        )
        return engine, int(channel_count)

    def _init_actors(self):
        # Create channel spheres
        if self.engine.pos_on_3d is None:
            self.chs = []
            return
        self.chs = [
            pv.Sphere(
                radius=0.003,
                center=self.engine.pos_on_3d[i, :] * mesh_scale_scalar,
            )
            for i in range(self.channel_count)
        ]

    def __call__(self, key, value):
        self.param[key] = value
        self.update()

    def update(self):
        # Update scalars via engine
        scalars = self.engine.update_scalars(self.param["sample_index"])

        if scalars is not None:
            try:
                # Update scalars in-place
                if self.engine.saliency_cap is not None:
                    self.engine.saliency_cap["scalars"] = scalars
                # Force render
                self.plotter.render()
                # Only update if scalar bar exists (avoids error during init call)
                if (
                    hasattr(self.plotter, "scalar_bars")
                    and "saliency" in self.plotter.scalar_bars
                ):
                    self.plotter.update_scalar_bar_range(
                        self.engine.scalar_bar_range,
                        "saliency",
                    )
            except Exception:
                logger.exception("Error updating 3D visualization")
                # Fixed bare except (Phase 2.1.1)

        if self.channelActor != []:
            for actor in self.channelActor:
                actor.SetVisibility(self.show_electrodes)

        if self.show_head:
            if self.headActor is None:
                self.headActor = self.plotter.add_mesh(
                    self.engine.head_scaled,
                    opacity=0.3,
                    color=Theme.TEXT_PRIMARY,
                )
        else:
            if self.headActor is not None:
                self.plotter.remove_actor(self.headActor)
            self.headActor = None

    def get_3d_head_plot(self):
        self.channelActor = [self.plotter.add_mesh(ch, color="w") for ch in self.chs]

        self.plotter.add_mesh(
            self.engine.saliency_cap,
            opacity=0.8,
            scalars="scalars",  # Named "scalars" in engine
            cmap=self.cmap,
            show_scalar_bar=False,
        )
        cast(Any, self.plotter).add_scalar_bar(
            "saliency",
            interactive=False,
            vertical=False,
            color=Theme.TEXT_PRIMARY,
            position_x=0.1,
            width=0.8,
        )
        self.plotter.update_scalar_bar_range(self.engine.scalar_bar_range, "saliency")
        self.plotter.add_mesh(self.engine.brain_scaled, color=Theme.BRAIN_MESH)
        self._center_scene_camera()
        self._install_orientation_widget()

        return self.plotter

    def _install_orientation_widget(self) -> None:
        """Install the full camera widget only after the live scene is ready."""
        self.plotter.clear_camera_widgets()
        renderer = getattr(self.plotter, "renderer", None)
        if renderer is None:
            self._orientation_widget = None
            return
        self._orientation_widget = self.plotter.add_camera_orientation_widget(
            animate=False,
        )
        self.refresh_orientation_widget()

    def refresh_orientation_widget(self) -> None:
        """Rebuild the VTK-owned corner overlay after the Qt layout settles."""
        orientation_widget = self._orientation_widget
        if orientation_widget is None:
            return
        renderer = getattr(self.plotter, "renderer", None)
        if renderer is None:
            return

        orientation_representation = orientation_widget.GetRepresentation()
        orientation_representation.AnchorToUpperRight()
        orientation_representation.SetSize(112, 112)
        orientation_representation.SetPadding(16, 16)
        orientation_widget.SquareResize()
        orientation_representation.BuildRepresentation()
        orientation_widget.ProcessEventsOff()
        orientation_widget.KeyPressActivationOff()
        render = getattr(self.plotter, "render", None)
        if callable(render):
            render()

    def _set_time_seconds(self, time_seconds: float) -> None:
        """Convert a slider time in seconds to one explicit saliency sample."""
        sample_index = self.engine.sample_index_for_time(float(time_seconds))
        self("sample_index", sample_index)

    def _center_scene_camera(self) -> None:
        """Center the 3-D saliency model after all actors are in the scene."""
        reset_camera = getattr(self.plotter, "reset_camera", None)
        if callable(reset_camera):
            with contextlib.suppress(Exception):
                reset_camera()
        with contextlib.suppress(Exception):
            self.plotter.camera_position = "xy"
        camera = getattr(self.plotter, "camera", None)
        zoom = getattr(camera, "zoom", None)
        if callable(zoom):
            with contextlib.suppress(Exception):
                zoom(0.9)
        render = getattr(self.plotter, "render", None)
        if callable(render):
            with contextlib.suppress(Exception):
                render()
