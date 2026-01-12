import matplotlib.pyplot as plt
import numpy as np
import pyvista as pv
#from pyvista.plotting import _vtk
from scipy.spatial import ConvexHull
import os
import requests


bgcolor = '#2d2d2d'#'#F8F5F1'#lightslategray'
mesh_scale_scalar = 0.8

checkboxKwargs = {
    'size' : 20, 
    'border_size' : 5,
    'color_on' : '#456071',
    'color_off' : bgcolor,
}
checkboxTextKwargs = {
    'color' : 'white',
    'shadow' : True,
    'font_size' : 8
}

class Saliency3D:
    def __init__(self, eval_record, epoch_data, selected_event_name, plotter=None):
        # set parameters
        self.selected_event_name = selected_event_name
        self.save = False
        self.showChannel = True
        self.showHead = True
        self.cmap = plt.cm.get_cmap("jet")
        self.neighbor = 3

        # load 3d model
        # Use absolute path relative to this file's location or package structure
        # This file is in XBrainLab/ui/visualization/
        # Models are in XBrainLab/backend/visualization/3Dmodel/
        
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Go up two levels to XBrainLab root, then into backend
        project_root = os.path.dirname(os.path.dirname(current_dir))
        model_dir = os.path.join(project_root, 'backend', 'visualization', '3Dmodel')
        
        if not os.path.exists(model_dir):
            os.makedirs(model_dir)
            fn_ply = ['brain.ply','head.ply']
            gitrepo_loc = 'https://raw.githubusercontent.com/CECNL/XBrainLab/main/XBrainLab.backend.visualization/3Dmodel/'
            for fn in fn_ply:
                try:
                    req = requests.get(gitrepo_loc+fn)
                    with open(os.path.join(model_dir, fn), 'wb') as handle:
                        handle.write(req.content)
                except Exception as e:
                    print(f"Failed to download {fn}: {e}")

        head_path = os.path.join(model_dir, 'head.ply')
        brain_path = os.path.join(model_dir, 'brain.ply')
        
        if os.path.exists(head_path):
            mesh_head = pv.read(head_path)
        else:
            raise FileNotFoundError(f"Head model not found at {head_path}")
            
        if os.path.exists(brain_path):
            mesh_brain = pv.read(brain_path)
        else:
            raise FileNotFoundError(f"Brain model not found at {brain_path}")

        # get saliency
        labelIndex = epoch_data.event_id[self.selected_event_name]
        self.saliency = eval_record.gradient[labelIndex]
        self.saliency = self.saliency.mean(axis=0)
        self.scalar_bar_range = [self.saliency.min(), self.saliency.max()]

        self.max_time = self.saliency.shape[-1]

        # get channel pos
        ch_pos = epoch_data.get_montage_position() # close plt
        electrode = epoch_data.get_channel_names()

        # get electrode pos in 3d
        pos_on_3d = []
        trans = [-0.0004, 0.00917, mesh_head.bounds[5] - 0.10024]  # trans Cz to [0, 0, 0]
        for ele in electrode:
            center = ch_pos[electrode.index(ele)] + trans
            if center[1] > 0:
                center[2] += 0.007
            pos_on_3d.append(center)
        self.pos_on_3d = np.asarray(pos_on_3d)

        self.chs = [
            pv.Sphere(radius=0.003, center=self.pos_on_3d[i, :] * mesh_scale_scalar)
            for i in range(self.saliency.shape[0])
        ]

        # set plotter
        if plotter:
            self.plotter = plotter
            self.plotter.clear() # Clear existing actors
        else:
            self.plotter = pv.Plotter(window_size=[750, 750])
            
        self.plotter.background_color = bgcolor

        scaling = np.ones(3) * mesh_scale_scalar 
        self.head = mesh_head.scale(scaling, inplace=True)
        self.brain = mesh_brain.scale(scaling * 0.001, inplace=True).triangulate()
        self.saliency_cap = ChannelConvexHull(self.pos_on_3d).scale(scaling, inplace=True)

        self.scalar = np.zeros(self.saliency_cap.n_points)
        self.channelActor = []
        self.headActor = None
        self.param = {
            'timestamp': 1,
            'save': self.save,
        }
        # checkbox instances & widget containers
        # Pass callback to trigger update immediately when clicked
        self.channelBox = CheckboxObj(self.showChannel, lambda s: self.update())
        self.headBox = CheckboxObj(self.showHead, lambda s: self.update())

        self.update()

    def __call__(self, key, value):
        self.param[key] = value
        self.update()

    def update(self):
        for i in range(self.saliency_cap.n_points):
            dist = [np.linalg.norm(self.saliency_cap.points[i] - ch) for ch in self.pos_on_3d]
            dist_idx = np.argsort(dist)[:self.neighbor] # id of #neighbor cloest points
            dist = np.array([dist[idx] for idx in dist_idx])
            self.scalar[i] = InverseDistWeightedSum(
                dist, self.saliency[dist_idx, self.param['timestamp'] - 1]
            )
        try:
            # Update scalars in-place to avoid deprecation warning
            self.saliency_cap['scalars'] = self.scalar
            self.plotter.render()
            self.plotter.update_scalar_bar_range(self.scalar_bar_range, '')
        except Exception:
            pass

        if self.channelActor != []:
            for actor in self.channelActor:
                actor.SetVisibility(self.channelBox.ctrl)

        if self.headBox.ctrl:
            if self.headActor is None:
                self.headActor = self.plotter.add_mesh(
                    self.head, opacity=0.3, color='w'
                )
        else:
            self.plotter.remove_actor(self.headActor)
            self.headActor = None

    def get3dHeadPlot(self):
        self.plotter.add_camera_orientation_widget()
        
        self.plotter.add_slider_widget(
            callback=lambda val: self('timestamp', int(val)),
            rng=[1, self.max_time], value=1,
            title="Timestamp",
            color='white',
            pointa=(0.025, 0.08),  # left bottom
            pointb=(0.31, 0.08),  # right bottom
            style='modern',
            interaction_event = 'always'
        )

        self.plotter.add_checkbox_button_widget(
            self.channelBox,
            value=self.showChannel,
            position=(25, 200),
            **checkboxKwargs
        )
        self.plotter.add_text(
            'Show channel', position=(60, 197), **checkboxTextKwargs
        )

        self.plotter.add_checkbox_button_widget(
            self.headBox,
            value=self.showHead,
            position=(25, 250),
            **checkboxKwargs
        )
        self.plotter.add_text(
            'Show head', position=(60, 247), **checkboxTextKwargs
        )

        self.plotter.camera_position = 'xy'
        self.plotter.camera.zoom(0.8)

        self.channelActor = [self.plotter.add_mesh(ch, color='w') for ch in self.chs]
        
        # Initialize scalars in the mesh
        self.saliency_cap['scalars'] = self.scalar
        
        self.plotter.add_mesh(
            self.saliency_cap, opacity=0.8,
            scalars='scalars', cmap=self.cmap, show_scalar_bar=False
        )
        self.plotter.add_scalar_bar('', interactive=False, vertical=False, color='white')
        self.plotter.update_scalar_bar_range(self.scalar_bar_range, '')
        self.plotter.add_mesh(self.brain, color='#FDEBD0')

        self.plotter.show_bounds(color='white')

        return self.plotter

class CheckboxObj:
    def __init__(self, init_val, callback=None):
        self.ctrl = init_val
        self.callback = callback

    def __call__(self, state):
        self.ctrl = state
        if self.callback:
            self.callback(state)

def InverseDistWeightedSum(dist, val):
    assert len(dist) == len(val)
    dist = dist + 1e-12
    return np.sum(val/dist)/(np.sum([1/d for d in dist]))

def ChannelConvexHull(ch_pos):
    # faster than pyvista delaunay? :
    # https://gist.github.com/flutefreak7/bd621a9a836c8224e92305980ed829b9
    hull = ConvexHull(ch_pos)
    faces = np.hstack(
        (np.ones((len(hull.simplices), 1))*3, hull.simplices)
    ).astype(np.int32)
    poly = pv.PolyData(hull.points, faces.ravel())
    return poly
    # cloud = pv.PolyData(ch_pos)
    # return cloud.delaunay_3d()
