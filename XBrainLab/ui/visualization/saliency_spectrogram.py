from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox
)
from PyQt6.QtCore import Qt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from XBrainLab.backend.visualization import VisualizerType, supported_saliency_methods

class SaliencySpectrogramWidget(QWidget):
    def __init__(self, parent, trainers):
        super().__init__(parent)
        self.trainers = trainers
        self.trainer_map = {t.get_name(): t for t in trainers}
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Controls
        ctrl_layout = QHBoxLayout()
        
        # Plan Selector
        lbl_plan = QLabel("Plan:")
        lbl_plan.setStyleSheet("color: #cccccc;")
        ctrl_layout.addWidget(lbl_plan)
        
        self.plan_combo = QComboBox()
        self.plan_combo.addItem("Select a plan")
        
        # Re-build map with friendly names
        self.friendly_map = {}
        for i, trainer in enumerate(self.trainers):
            model_name = trainer.model_holder.target_model.__name__
            friendly_name = f"Group {i+1} ({model_name})"
            self.friendly_map[friendly_name] = trainer
            self.plan_combo.addItem(friendly_name)
            
        self.plan_combo.setStyleSheet("""
            QComboBox {
                background-color: #3e3e42;
                color: #cccccc;
                border: 1px solid #555;
                padding: 5px;
            }
            QComboBox::drop-down {
                border: 0px;
            }
        """)
        self.plan_combo.currentTextChanged.connect(self.on_plan_changed)
        ctrl_layout.addWidget(self.plan_combo)
        
        ctrl_layout.addSpacing(20)
        
        # Run Selector
        lbl_run = QLabel("Run:")
        lbl_run.setStyleSheet("color: #cccccc;")
        ctrl_layout.addWidget(lbl_run)
        
        self.run_combo = QComboBox()
        self.run_combo.setStyleSheet(self.plan_combo.styleSheet())
        self.run_combo.currentTextChanged.connect(self.on_update)
        ctrl_layout.addWidget(self.run_combo)
        
        ctrl_layout.addSpacing(20)
        
        # Saliency Method Selector
        lbl_method = QLabel("Method:")
        lbl_method.setStyleSheet("color: #cccccc;")
        ctrl_layout.addWidget(lbl_method)
        
        self.saliency_combo = QComboBox()
        self.saliency_combo.addItem('Gradient')
        self.saliency_combo.addItem('Gradient * Input')
        self.saliency_combo.addItems(supported_saliency_methods)
        self.saliency_combo.setStyleSheet(self.plan_combo.styleSheet())
        self.saliency_combo.currentTextChanged.connect(self.on_update)
        ctrl_layout.addWidget(self.saliency_combo)
        
        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)
        
        # Plot Area
        self.plot_container = QWidget()
        self.plot_layout = QVBoxLayout(self.plot_container)
        self.plot_layout.setContentsMargins(0, 0, 0, 0)
        
        # Initial Placeholder
        self.fig = Figure(figsize=(5, 4), dpi=100)
        self.fig.patch.set_facecolor('#2d2d2d')
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor('#2d2d2d')
        self.ax.text(0.5, 0.5, "Select a plan to view Spectrogram", 
                     color='#666666', ha='center', va='center')
        self.ax.axis('off')
        
        self.plot_layout.addWidget(self.canvas)
        layout.addWidget(self.plot_container, stretch=1)

    def on_plan_changed(self, text):
        """Update Run combo when Plan changes."""
        self.run_combo.blockSignals(True)
        self.run_combo.clear()
        
        if text in self.friendly_map:
            trainer = self.friendly_map[text]
            # Add runs
            for i in range(trainer.option.repeat_num):
                self.run_combo.addItem(f"Run {i+1}")
            # Add Average
            self.run_combo.addItem("Average")
            
        self.run_combo.blockSignals(False)
        self.on_update()

    def on_update(self):
        plan_name = self.plan_combo.currentText()
        run_name = self.run_combo.currentText()
        method_name = self.saliency_combo.currentText()
        
        if plan_name not in self.friendly_map:
            return
        if not run_name:
            return
            
        trainer = self.friendly_map[plan_name]
        
        target_plan = None
        eval_record = None
        
        if run_name == "Average":
            # Compute Average
            eval_record = self.get_averaged_record(trainer)
            if not eval_record:
                self.show_error("No finished runs to average.")
                return
            target_plan = trainer.get_plans()[0]
        else:
            # Parse "Run X"
            try:
                run_idx = int(run_name.split(" ")[1]) - 1
                plans = trainer.get_plans()
                if 0 <= run_idx < len(plans):
                    target_plan = plans[run_idx]
                    eval_record = target_plan.get_eval_record()
            except:
                pass
        
        if not eval_record:
            self.show_error("Selected run has no evaluation record.")
            return
        
        self.plot_saliency(target_plan, trainer, method_name, eval_record)

    def get_averaged_record(self, trainer):
        """Compute average EvalRecord from all finished runs."""
        import numpy as np
        from XBrainLab.backend.training.record.eval import EvalRecord
        
        plans = trainer.get_plans()
        records = [p.get_eval_record() for p in plans if p.get_eval_record() is not None]
        
        if not records:
            return None
            
        base = records[0]
        
        def avg_dict(attr_name):
            result = {}
            keys = getattr(base, attr_name).keys()
            for k in keys:
                arrays = [getattr(r, attr_name)[k] for r in records]
                result[k] = np.mean(np.stack(arrays), axis=0)
            return result

        avg_gradient = avg_dict('gradient')
        avg_gradient_input = avg_dict('gradient_input')
        avg_smoothgrad = avg_dict('smoothgrad')
        avg_smoothgrad_sq = avg_dict('smoothgrad_sq')
        avg_vargrad = avg_dict('vargrad')
        
        return EvalRecord(
            label=base.label,
            output=base.output,
            gradient=avg_gradient,
            gradient_input=avg_gradient_input,
            smoothgrad=avg_smoothgrad,
            smoothgrad_sq=avg_smoothgrad_sq,
            vargrad=avg_vargrad
        )

    def show_error(self, message):
        for i in reversed(range(self.plot_layout.count())): 
            self.plot_layout.itemAt(i).widget().setParent(None)
        lbl = QLabel(message)
        lbl.setStyleSheet("color: #ef5350; font-size: 14px; font-weight: bold;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plot_layout.addWidget(lbl)

    def plot_saliency(self, plan, trainer, method, eval_record=None):
        try:
            # Clear previous
            for i in reversed(range(self.plot_layout.count())): 
                self.plot_layout.itemAt(i).widget().setParent(None)
            
            # Get Data
            if eval_record is None:
                eval_record = plan.get_eval_record()
                
            if not eval_record:
                raise ValueError("No evaluation record found.")
                
            epoch_data = trainer.get_dataset().get_epoch_data()
            
            # Instantiate Visualizer
            visualizer = VisualizerType.SaliencySpectrogramMap.value(
                eval_record, epoch_data
            )
            
            # Get Figure
            self.fig = visualizer.get_plt(method=method)
            
            if self.fig:
                # Apply Dark Theme
                self.fig.patch.set_facecolor('#2d2d2d')
                for ax in self.fig.axes:
                    ax.set_facecolor('#2d2d2d')
                    ax.tick_params(colors='#cccccc')
                    for spine in ax.spines.values():
                        spine.set_color('#555555')
                    ax.xaxis.label.set_color('#cccccc')
                    ax.yaxis.label.set_color('#cccccc')
                    ax.title.set_color('#cccccc')
                
                # Re-create canvas
                self.canvas = FigureCanvas(self.fig)
                self.plot_layout.addWidget(self.canvas)
            else:
                self.show_error("No data available.")
                
        except Exception as e:
            print(f"Error plotting spectrogram: {e}")
            self.show_error(f"Error: {e}")
