import contextlib
from typing import Any, cast

import pyvista as pv
from matplotlib import colormaps

from XBrainLab.backend.application.saliency_render import SaliencyRenderData
from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.visualization.saliency_3d_engine import Saliency3DEngine
from XBrainLab.ui.core.utils import CheckboxObj  # Moved here
from XBrainLab.ui.styles.theme import Theme

bgcolor = Theme.BACKGROUND_MID
mesh_scale_scalar = 0.8

CHECKBOX_KWARGS = {
    "size": 20,
    "border_size": 5,
    "color_on": Theme.CHECKBOX_ON,
    "color_off": bgcolor,
}
CHECKBOX_TEXT_KWARGS = {"color": Theme.TEXT_PRIMARY, "shadow": True, "font_size": 8}


class Saliency3D:
    def __init__(
        self,
        render_data: SaliencyRenderData,
        selected_event_name,
        *,
        method="Gradient",
        absolute=False,
        plotter=None,
        prepared_engine: Saliency3DEngine | None = None,
        prepared_channel_count: int | None = None,
    ):
        # set parameters
        self.selected_event_name = selected_event_name
        self.save = False
        self.showChannel = True
        self.showHead = True
        self.cmap = colormaps["coolwarm"]
        self.init_error = ""

        # Initialize Backend Engine
        self.engine: Saliency3DEngine | None = prepared_engine
        if prepared_engine is not None:
            self.channel_count = int(prepared_channel_count or 0)
        else:
            try:
                self.engine, self.channel_count = self.prepare_engine(
                    render_data,
                    selected_event_name,
                    method=method,
                    absolute=absolute,
                )
            except Exception as exc:
                logger.exception("Failed to initialize Saliency3D engine")
                self.init_error = str(exc)
                self.engine = None
                self.channel_count = 0

        if self.engine is not None:
            self.cmap = colormaps[getattr(self.engine, "cmap_name", "coolwarm")]

        self.param = {
            "sample_index": 0,
            "save": self.save,
        }

        # set plotter
        if plotter:
            self.plotter = plotter
            self.plotter.clear()
        else:
            self.plotter = pv.Plotter(window_size=[750, 750])

        self.plotter.background_color = bgcolor

        self.channelActor: list[pv.Actor] = []
        self.headActor = None

        if self.engine:
            self._setup_scene()
            self._init_actors()

        # checkbox instances
        self.channelBox = CheckboxObj(self.showChannel, lambda s: self.update())
        self.headBox = CheckboxObj(self.showHead, lambda s: self.update())

        if self.engine:
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
            render_data,
            selected_event_name,
            method=method,
            absolute=absolute,
        )
        return engine, int(channel_count)

    def _setup_scene(self):
        # Access engine meshes
        # Note: PyVista meshes are mutable, so we can add them directly
        # But we need them to be stored in "self" for update logic?
        # Actually update logic acts on self.engine.saliency_cap
        pass

    def _init_actors(self):
        # Create channel spheres
        if not self.engine or self.engine.pos_on_3d is None:
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
        if not self.engine:
            return

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
                actor.SetVisibility(self.channelBox.ctrl)

        if self.headBox.ctrl:
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
        if not self.engine:
            # Return empty plotter if init failed?
            return self.plotter

        self.plotter.clear_camera_widgets()
        self.plotter.add_camera_orientation_widget()

        self.channelActor = [self.plotter.add_mesh(ch, color="w") for ch in self.chs]

        # Initialize scalars should be done by engine.update_scalars call in __init__?
        # self.engine.saliency_cap["scalars"] = ...
        # Yes, we called self.update() in __init__

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

        return self.plotter

    def _set_time_seconds(self, time_seconds: float) -> None:
        """Convert a slider time in seconds to one explicit saliency sample."""
        if self.engine is None:
            return
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
