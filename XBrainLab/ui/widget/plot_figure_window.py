from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QWidget, QGroupBox
)
from PyQt6.QtCore import QTimer
from .single_plot_window import SinglePlotWindow
from XBrainLab.backend.visualization import supported_saliency_methods
import matplotlib.pyplot as plt

class PlotFigureWindow(SinglePlotWindow):
    def __init__(
        self,
        parent,
        trainers,
        plot_type,
        figsize=None,
        title='Plot',
        plan_name=None,
        real_plan_name=None,
        saliency_name=None
    ):
        super().__init__(parent, figsize, title=title)
        self.trainers = trainers
        self.trainer = None
        self.check_data()
        self.plot_type = plot_type
        self.plan_to_plot = None
        self.current_plot = None
        self.plot_gap = 0
        self.saliency_name = saliency_name
        
        self.trainer_map = {trainer.get_name(): trainer for trainer in trainers}
        self.real_plan_map = {}
        
        self.init_ui()
        
        self.drawCounter = 0
        self.update_progress = -1
        
        # Timer for update loop
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_loop)
        self.timer.start(100)
        
        if plan_name:
            self.plan_combo.setCurrentText(plan_name)
        if real_plan_name:
            self.real_plan_combo.setCurrentText(real_plan_name)
        if saliency_name:
            self.saliency_combo.setCurrentText(saliency_name)

    def check_data(self):
        if not isinstance(self.trainers, list) or len(self.trainers) == 0:
            # In PyQt we might want to show a message box, but init shouldn't block/fail ideally
            pass 

    def init_ui(self):
        # Insert selector frame at the top
        self.selector_group = QGroupBox("Controls")
        selector_layout = QHBoxLayout(self.selector_group)
        
        # Plan
        self.plan_combo = QComboBox()
        self.plan_combo.addItem('Select a plan')
        self.plan_combo.addItems(list(self.trainer_map.keys()))
        self.plan_combo.currentTextChanged.connect(self.on_plan_select)
        selector_layout.addWidget(self.plan_combo)
        
        # Real Plan (Repeat)
        self.real_plan_combo = QComboBox()
        self.real_plan_combo.addItem('Select repeat')
        self.real_plan_combo.currentTextChanged.connect(self.on_real_plan_select)
        selector_layout.addWidget(self.real_plan_combo)
        
        # Saliency
        self.saliency_combo = QComboBox()
        self.saliency_combo.addItem('Select saliency method')
        self.saliency_combo.addItems(['Gradient', 'Gradient * Input', *supported_saliency_methods])
        self.saliency_combo.currentTextChanged.connect(self.on_saliency_method_select)
        selector_layout.addWidget(self.saliency_combo)
        
        # Add to main layout at index 0 (top)
        self.layout.insertWidget(0, self.selector_group)

    def on_plan_select(self, plan_name):
        self.set_selection(False)
        self.plan_to_plot = None
        self.trainer = None
        
        self.real_plan_combo.clear()
        self.real_plan_combo.addItem('Select repeat')
        
        if plan_name not in self.trainer_map:
            return
            
        trainer = self.trainer_map[plan_name]
        self.trainer = trainer
        self.real_plan_map = {plan.get_name(): plan for plan in trainer.get_plans()}
        self.real_plan_combo.addItems(list(self.real_plan_map.keys()))

    def on_real_plan_select(self, plan_name):
        self.set_selection(False)
        self.plan_to_plot = None
        if plan_name not in self.real_plan_map:
            return
        self.plan_to_plot = self.real_plan_map[plan_name]
        # self.add_plot_command() # Scripting not fully ported yet

    def on_saliency_method_select(self, method_name):
        self.set_selection(False)
        if method_name == 'Select saliency method':
            return
        # self.add_plot_command()
        self.recreate_fig()

    def _create_figure(self):
        target_func = getattr(self.plan_to_plot, self.plot_type.value)
        # Ensure figure params are ready
        params = self.get_figure_params()
        figure = target_func(**params)
        return figure

    def update_loop(self):
        if not self.isVisible():
            return
            
        counter = self.drawCounter
        MAX_PLOT_GAP = 20
        
        if self.current_plot != self.plan_to_plot:
            self.current_plot = self.plan_to_plot
            self.active_figure()
            
            if self.plan_to_plot is None:
                self.empty_data_figure()
            else:
                self.plot_gap += 1
                if self.plot_gap < MAX_PLOT_GAP:
                    self.current_plot = True # Keep waiting
                else:
                    self.plot_gap = 0
                    update_progress = self.plan_to_plot.get_epoch()
                    
                    if (update_progress != self.update_progress or self.plan_to_plot.is_finished()):
                        self.update_progress = update_progress
                        self.show_drawing()
                        
                        try:
                            figure = self._create_figure()
                            if figure is None:
                                self.empty_data_figure()
                            else:
                                # Update canvas with new figure
                                # We need to replace the figure in the canvas
                                # SinglePlotWindow.set_figure handles this
                                self.set_figure(figure, self.figsize, self.dpi)
                                self.redraw()
                        except Exception as e:
                            print(f"Plotting error: {e}")
                            self.empty_data_figure()
                            
                    if not self.plan_to_plot.is_finished():
                        self.current_plot = True # Keep updating if running
                    # self.redraw() # Redraw handled above

        if counter == self.drawCounter:
            self.set_selection(allow=True)
            
        # Check for new plans dynamically?
        # Original code did this, maybe we skip for now or implement if needed

    def set_selection(self, allow):
        if not allow:
            self.drawCounter += 1
            self.selector_group.setEnabled(False)
        else:
            self.selector_group.setEnabled(True)

    def recreate_fig(self, *args, current_plot=True):
        self.update_progress = -1
        self.current_plot = current_plot # Force re-check in loop
        self.plot_gap = 100 # Force immediate update
