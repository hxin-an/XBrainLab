from PyQt6.QtWidgets import QDialog, QVBoxLayout, QWidget, QSizePolicy
from PyQt6.QtCore import Qt
import matplotlib
matplotlib.use('QtAgg')
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import matplotlib.pyplot as plt

class SinglePlotWindow(QDialog):
    PLOT_COUNTER = 0
    def __init__(self, parent, figsize=None, dpi=None, title='Plot'):
        super().__init__(parent)
        self.setWindowTitle(title)
        
        if figsize is None:
            figsize = (6.4, 4.8)
        if dpi is None:
            dpi = 100
            
        self.figsize = figsize
        self.dpi = dpi
        
        self.layout = QVBoxLayout(self)
        self.figure_canvas = None
        self.plot_number = None
        
        self.init_figure()
        
        # Resize logic (approximate)
        width = int(figsize[0] * dpi)
        height = int(figsize[1] * dpi)
        self.resize(width + 50, height + 100) # Add padding for toolbar/margins

    def active_figure(self):
        plt.figure(self.plot_number)

    def init_figure(self):
        self.plot_number = f'SinglePlotWindow-{SinglePlotWindow.PLOT_COUNTER}'
        SinglePlotWindow.PLOT_COUNTER += 1
        
        figure = plt.figure(num=self.plot_number, figsize=self.figsize, dpi=self.dpi)
        self.set_figure(figure, self.figsize, self.dpi)
        self.active_figure()

    def get_figure_params(self):
        # self.init_figure() # Original called this, but it might reset?
        # Let's check if we need to re-init
        if not plt.fignum_exists(self.plot_number):
             self.init_figure()
        return self.fig_param

    def clear_figure(self):
        plt.clf()
        self.redraw()

    def show_drawing(self):
        self.clear_figure()
        plt.text(.5, .5, 'Drawing.', ha='center', va='center')
        self.redraw()

    def empty_data_figure(self):
        self.clear_figure()
        plt.text(.5, .5, 'No data is available.', ha='center', va='center')
        self.redraw()

    def set_figure(self, figure, figsize, dpi):
        if self.figure_canvas:
            self.layout.removeWidget(self.figure_canvas)
            self.figure_canvas.setParent(None)
            self.figure_canvas.deleteLater()
            if hasattr(self, 'toolbar'):
                self.layout.removeWidget(self.toolbar)
                self.toolbar.setParent(None)
                self.toolbar.deleteLater()

        self.figure_canvas = FigureCanvasQTAgg(figure)
        self.figure_canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.figure_canvas.updateGeometry()
        
        self.toolbar = NavigationToolbar(self.figure_canvas, self)
        
        self.layout.addWidget(self.toolbar)
        self.layout.addWidget(self.figure_canvas)
        
        self.fig_param = {'fig': figure, 'figsize': figsize, 'dpi': dpi}

    def redraw(self):
        if self.figure_canvas:
            self.fig_param['fig'].tight_layout()
            self.figure_canvas.draw()
