from PyQt6.QtWidgets import QCheckBox

from ..widget import PlotFigureWindow


class PlotABSFigureWindow(PlotFigureWindow):
    def __init__(
        self,
        parent,
        trainers,
        plot_type,
        figsize=None,
        title="Plot",
        plan_name=None,
        real_plan_name=None,
        saliency_name=None,
        absolute=None,
    ):
        super().__init__(
            parent,
            trainers,
            plot_type,
            figsize,
            title,
            plan_name,
            real_plan_name,
            saliency_name,
        )

        self.absolute_chk = QCheckBox("absolute value")
        self.absolute_chk.stateChanged.connect(self.absolute_callback)

        if absolute is not None:
            self.absolute_chk.setChecked(absolute)

        # Add to selector group
        self.selector_group.layout().addWidget(self.absolute_chk)

    def absolute_callback(self, state):
        # self.add_plot_command()
        self.recreate_fig()

    def _create_figure(self):
        eval_record = self.plan_to_plot.get_eval_record()
        if not eval_record:
            return None

        epoch_data = self.trainer.get_dataset().get_epoch_data()

        # Instantiate the visualizer class (plot_type is a class or enum value pointing
        # to class)
        # In original code: self.plot_type.value(...)
        # Assuming plot_type is an Enum where value is the class
        plot_visualizer = self.plot_type.value(
            eval_record, epoch_data, **self.get_figure_params()
        )

        figure = plot_visualizer.get_plt(
            method=self.saliency_combo.currentText(),
            absolute=self.absolute_chk.isChecked(),
        )
        return figure
