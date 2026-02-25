import matplotlib.pyplot as plt
import pyvista as pv

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
    def __init__(self, eval_record, epoch_data, selected_event_name, plotter=None):
        # set parameters
        self.selected_event_name = selected_event_name
        self.save = False
        self.showChannel = True
        self.showHead = True
        self.cmap = plt.cm.get_cmap("coolwarm")

        # Initialize Backend Engine
        self.engine: Saliency3DEngine | None = None
        try:
            self.engine = Saliency3DEngine(mesh_scale_scalar=mesh_scale_scalar)
            self.channel_count = self.engine.process_data(
                eval_record,
                epoch_data,
                selected_event_name,
            )
        except Exception:
            logger.exception("Failed to initialize Saliency3D engine")
            # Handle failure gracefully
            self.engine = None
            self.channel_count = 0

        self.param = {
            "timestamp": 1,
            "save": self.save,
        }

        # set plotter
        if plotter:
            self.plotter = plotter
            self.plotter.clear()
        else:
            self.plotter = pv.Plotter(window_size=[750, 750])

        self.plotter.background_color = bgcolor

        self.channelActor = []
        self.headActor = None

        if self.engine:
            self._setup_scene()
            self._init_actors()

        # checkbox instances
        self.channelBox = CheckboxObj(self.showChannel, lambda s: self.update())
        self.headBox = CheckboxObj(self.showHead, lambda s: self.update())

        if self.engine:
            self.update()

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
        scalars = self.engine.update_scalars(self.param["timestamp"] - 1)

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
            self.plotter.remove_actor(self.headActor)
            self.headActor = None

    def get_3d_head_plot(self):
        if not self.engine:
            # Return empty plotter if init failed?
            return self.plotter

        self.plotter.add_camera_orientation_widget()

        saliency_shape_1 = 1
        if self.engine and self.engine.saliency is not None:
            saliency_shape_1 = self.engine.saliency.shape[1]
        self.plotter.add_slider_widget(
            callback=lambda val: self("timestamp", int(val)),
            rng=[1, saliency_shape_1],  # Use engine's saliency shape
            value=1,
            title="Timestamp",
            color="white",
            pointa=(0.025, 0.08),
            pointb=(0.31, 0.08),
            style="modern",
            interaction_event="always",
        )

        self.plotter.add_checkbox_button_widget(
            self.channelBox,
            value=self.showChannel,
            position=(25, 200),
            **CHECKBOX_KWARGS,
        )
        self.plotter.add_text(
            "Show channel",
            position=(60, 197),
            **CHECKBOX_TEXT_KWARGS,
        )

        self.plotter.add_checkbox_button_widget(
            self.headBox,
            value=self.showHead,
            position=(25, 250),
            **CHECKBOX_KWARGS,
        )
        self.plotter.add_text("Show head", position=(60, 247), **CHECKBOX_TEXT_KWARGS)

        self.plotter.camera_position = "xy"
        self.plotter.camera.zoom(0.8)

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
        self.plotter.add_scalar_bar(
            "saliency",
            interactive=False,
            vertical=False,
            color=Theme.TEXT_PRIMARY,
        )
        self.plotter.update_scalar_bar_range(self.engine.scalar_bar_range, "saliency")
        self.plotter.add_mesh(self.engine.brain_scaled, color=Theme.BRAIN_MESH)

        self.plotter.show_bounds(color="white")

        return self.plotter
