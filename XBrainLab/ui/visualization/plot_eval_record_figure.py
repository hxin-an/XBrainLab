from ..widget import PlotFigureWindow


class PlotEvalRecordFigureWindow(PlotFigureWindow):
    def _create_figure(self):
        if not self.plan_to_plot:
            return None
        eval_record = self.plan_to_plot.get_eval_record()
        if not eval_record:
            return None

        if not self.trainer:
            return None
        dataset = self.trainer.get_dataset()
        if not dataset:
            return None
        epoch_data = dataset.get_epoch_data()

        plot_visualizer = self.plot_type.value(
            eval_record, epoch_data, **self.get_figure_params()
        )

        figure = plot_visualizer.get_plt(method=self.saliency_combo.currentText())
        return figure
