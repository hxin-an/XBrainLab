from ..widget import PlotFigureWindow

class PlotEvalRecordFigureWindow(PlotFigureWindow):
    def _create_figure(self):
        eval_record = self.plan_to_plot.get_eval_record()
        if not eval_record:
            return None

        epoch_data = self.trainer.get_dataset().get_epoch_data()
        
        plot_visualizer = self.plot_type.value(
            eval_record, epoch_data, **self.get_figure_params()
        )
        
        figure = plot_visualizer.get_plt(method=self.saliency_combo.currentText())
        return figure
