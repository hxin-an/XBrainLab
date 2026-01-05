from PyQt6.QtWidgets import QMessageBox
from .plot_abs_plot_figure import PlotABSFigureWindow

class PlotTopoABSFigureWindow(PlotABSFigureWindow):
    def check_data(self):
        super().check_data()
        # In PyQt we might not want to raise exceptions in check_data if it crashes the app,
        # but let's follow the logic.
        if self.trainers:
            epoch_data = self.trainers[0].get_dataset().get_epoch_data()
            positions = epoch_data.get_montage_position()

            if positions is None:
                QMessageBox.warning(self, "Error", "No valid montage position is set.")
                # We might want to close or disable here
