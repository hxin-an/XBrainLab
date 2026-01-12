from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QListWidget, QGroupBox, QGridLayout, QDialog, QFormLayout, 
    QDoubleSpinBox, QDialogButtonBox, QMessageBox, QFrame
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QListWidget, QGroupBox, QGridLayout, QDialog, QFormLayout, 
    QDoubleSpinBox, QDialogButtonBox, QMessageBox, QTabWidget, QSpinBox,
    QCheckBox, QLineEdit, QScrollArea, QSlider, QComboBox, QRadioButton, QButtonGroup
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np
from scipy.signal import welch
from XBrainLab.backend import preprocessor as Preprocessor
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.dashboard_panel.info import AggregateInfoPanel
from XBrainLab.ui.dashboard_panel.info import AggregateInfoPanel

class ResampleDialog(QDialog):
    def __init__(self, parent, preprocessed_data_list):
        super().__init__(parent)
        self.setWindowTitle("Resample")
        self.resize(300, 100)
        self.preprocessor = Preprocessor.Resample(preprocessed_data_list)
        self.return_data = None
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.sfreq_spin = QDoubleSpinBox()
        self.sfreq_spin.setRange(1, 10000)
        self.sfreq_spin.setValue(250.0)
        form.addRow("Sampling Rate (Hz):", self.sfreq_spin)
        layout.addLayout(form)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def accept(self):
        try:
            self.return_data = self.preprocessor.data_preprocess(self.sfreq_spin.value())
            super().accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def get_result(self):
        return self.return_data

class EpochingDialog(QDialog):
    def __init__(self, parent, preprocessed_data_list):
        super().__init__(parent)
        self.setWindowTitle("Time Epoching")
        self.resize(400, 500)
        self.preprocessor = Preprocessor.TimeEpoch(preprocessed_data_list)
        self.data_list = preprocessed_data_list
        self.return_data = None
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 1. Event Selection
        event_group = QGroupBox("Select Events")
        event_layout = QVBoxLayout()
        self.event_list = QListWidget()
        self.event_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        
        # Collect all unique events
        events = set()
        for data in self.data_list:
            try:
                # Use get_event_list which prioritizes imported/resampled events
                evs, ev_ids = data.get_event_list()
                if ev_ids:
                    events.update(ev_ids.keys())
            except:
                pass
        
        for ev in sorted(list(events)):
            self.event_list.addItem(ev)
            
        event_layout.addWidget(self.event_list)
        event_group.setLayout(event_layout)
        layout.addWidget(event_group)
        
        # 2. Parameters
        param_group = QGroupBox("Epoch Parameters")
        form = QFormLayout()
        
        self.tmin_spin = QDoubleSpinBox()
        self.tmin_spin.setRange(-10, 10)
        self.tmin_spin.setValue(-0.2)
        self.tmin_spin.setSingleStep(0.1)
        self.tmin_spin.valueChanged.connect(self.update_duration_info)
        
        self.tmax_spin = QDoubleSpinBox()
        self.tmax_spin.setRange(-10, 10)
        self.tmax_spin.setValue(1.0)
        self.tmax_spin.setSingleStep(0.1)
        self.tmax_spin.valueChanged.connect(self.update_duration_info)
        
        form.addRow("Start (s):", self.tmin_spin)
        form.addRow("End (s):", self.tmax_spin)
        
        # Duration info label
        self.duration_label = QLabel()
        self.duration_label.setStyleSheet("color: gray; font-style: italic;")
        form.addRow("Duration:", self.duration_label)
        
        # Warning label (must be created before update_duration_info is called)
        self.warning_label = QLabel()
        self.warning_label.setStyleSheet("color: orange; font-weight: bold;")
        self.warning_label.setWordWrap(True)
        form.addRow(self.warning_label)
        
        # Now update duration info (which uses warning_label)
        self.update_duration_info()
        
        # Baseline
        self.baseline_check = QCheckBox("Apply Baseline Correction")
        self.baseline_check.setChecked(True)
        self.baseline_check.toggled.connect(self.toggle_baseline)
        
        self.b_min_spin = QDoubleSpinBox()
        self.b_min_spin.setRange(-10, 10)
        self.b_min_spin.setValue(-0.2)
        
        self.b_max_spin = QDoubleSpinBox()
        self.b_max_spin.setRange(-10, 10)
        self.b_max_spin.setValue(0.0)
        
        form.addRow(self.baseline_check)
        form.addRow("Baseline Min (s):", self.b_min_spin)
        form.addRow("Baseline Max (s):", self.b_max_spin)
        
        param_group.setLayout(form)
        layout.addWidget(param_group)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def toggle_baseline(self, checked):
        self.b_min_spin.setEnabled(checked)
        self.b_max_spin.setEnabled(checked)
    
    def update_duration_info(self):
        """Update duration information and show warning if duration is too short."""
        tmin = self.tmin_spin.value()
        tmax = self.tmax_spin.value()
        duration = tmax - tmin
        
        self.duration_label.setText(f"{duration:.2f}s ({tmax} - ({tmin}))")
        
        # Check if duration might be too short for models
        # Most models need at least 1.0-1.2s at typical sampling rates
        if duration < 1.0:
            self.warning_label.setText(
                "Warning: Epoch duration < 1.0s may be too short for some models (EEGNet, SCCNet, ShallowConvNet). "
                "Consider using at least 1.2s to avoid errors during training plan generation."
            )
            self.warning_label.show()
        elif duration < 1.2:
            self.warning_label.setText(
                "Note: Epoch duration < 1.2s may cause issues with high sampling rates (>250Hz)."
            )
            self.warning_label.show()
        else:
            self.warning_label.hide()


    def accept(self):
        selected_items = self.event_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select at least one event.")
            return
            
        selected_events = [item.text() for item in selected_items]
        tmin = self.tmin_spin.value()
        tmax = self.tmax_spin.value()
        
        baseline = None
        if self.baseline_check.isChecked():
            baseline = (self.b_min_spin.value(), self.b_max_spin.value())
            
        try:
            self.return_data = self.preprocessor.data_preprocess(
                baseline, selected_events, tmin, tmax
            )
            super().accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def get_result(self):
        return self.return_data

class FilteringDialog(QDialog):
    def __init__(self, parent, preprocessed_data_list):
        super().__init__(parent)
        self.setWindowTitle("Filtering")
        self.resize(300, 250)
        
        # Initialize backend preprocessor
        self.preprocessor = Preprocessor.Filtering(preprocessed_data_list)
        self.return_data = None
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        
        # Bandpass Filter
        self.bandpass_check = QCheckBox("Apply Bandpass Filter")
        self.bandpass_check.setChecked(True)
        self.bandpass_check.toggled.connect(self.toggle_bandpass)
        form_layout.addRow(self.bandpass_check)

        self.l_freq_spin = QDoubleSpinBox()
        self.l_freq_spin.setRange(0, 1000)
        self.l_freq_spin.setDecimals(2)
        self.l_freq_spin.setValue(1.0) # Default
        
        self.h_freq_spin = QDoubleSpinBox()
        self.h_freq_spin.setRange(0, 1000)
        self.h_freq_spin.setDecimals(2)
        self.h_freq_spin.setValue(40.0) # Default
        
        form_layout.addRow("Lower pass-band (Hz):", self.l_freq_spin)
        form_layout.addRow("Upper pass-band (Hz):", self.h_freq_spin)
        

        
        # Notch Filter
        self.notch_check = QCheckBox("Apply Notch Filter")
        self.notch_check.toggled.connect(self.toggle_notch)
        form_layout.addRow(self.notch_check)
        
        self.notch_spin = QDoubleSpinBox()
        self.notch_spin.setRange(0, 1000)
        self.notch_spin.setValue(50.0) # Default 50Hz
        self.notch_spin.setEnabled(False)
        form_layout.addRow("Notch Frequency (Hz):", self.notch_spin)
        
        layout.addLayout(form_layout)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def toggle_notch(self, checked):
        self.notch_spin.setEnabled(checked)

    def toggle_bandpass(self, checked):
        self.l_freq_spin.setEnabled(checked)
        self.h_freq_spin.setEnabled(checked)

    def accept(self):
        l_freq = None
        h_freq = None
        
        if self.bandpass_check.isChecked():
            l_freq = self.l_freq_spin.value()
            h_freq = self.h_freq_spin.value()
            
            # Validate
            if l_freq >= h_freq and h_freq > 0:
                 QMessageBox.warning(self, "Invalid Input", "Lower freq must be less than Upper freq.")
                 return
        
        notch_freqs = None
        if self.notch_check.isChecked():
            notch_freqs = self.notch_spin.value()
            
        if l_freq is None and h_freq is None and notch_freqs is None:
             QMessageBox.warning(self, "Warning", "Please select at least one filter (Bandpass or Notch).")
             return



        try:
            self.return_data = self.preprocessor.data_preprocess(l_freq, h_freq, notch_freqs=notch_freqs)
            super().accept()
        except Exception as e:
            logger.error(f"Filtering failed: {e}")
            QMessageBox.critical(self, "Error", f"Filtering failed: {e}")

    def get_result(self):
        return self.return_data



class RereferenceDialog(QDialog):
    def __init__(self, parent, preprocessed_data_list):
        super().__init__(parent)
        self.setWindowTitle("Re-reference")
        self.resize(400, 300)
        self.preprocessor = Preprocessor.Rereference(preprocessed_data_list)
        self.return_data = None
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        self.avg_check = QCheckBox("Use Average Reference")
        self.avg_check.setChecked(True)
        self.avg_check.toggled.connect(self.toggle_avg)
        layout.addWidget(self.avg_check)
        
        self.chan_group = QGroupBox("Select Reference Channels")
        self.chan_group.setEnabled(False)
        chan_layout = QVBoxLayout()
        self.chan_list = QListWidget()
        self.chan_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        
        # Populate channels from first data
        if self.preprocessor.get_preprocessed_data_list():
            first_data = self.preprocessor.get_preprocessed_data_list()[0]
            self.chan_list.addItems(first_data.get_mne().ch_names)
            
        chan_layout.addWidget(self.chan_list)
        self.chan_group.setLayout(chan_layout)
        layout.addWidget(self.chan_group)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def toggle_avg(self, checked):
        self.chan_group.setEnabled(not checked)
        
    def accept(self):
        try:
            if self.avg_check.isChecked():
                ref = 'average'
            else:
                selected = self.chan_list.selectedItems()
                if not selected:
                    QMessageBox.warning(self, "Warning", "Please select at least one channel or use average reference.")
                    return
                ref = [item.text() for item in selected]
                
            self.return_data = self.preprocessor.data_preprocess(ref_channels=ref)
            super().accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def get_result(self):
        return self.return_data

class NormalizeDialog(QDialog):
    def __init__(self, parent, preprocessed_data_list):
        super().__init__(parent)
        self.setWindowTitle("Normalize")
        self.resize(300, 150)
        self.preprocessor = Preprocessor.Normalize(preprocessed_data_list)
        self.return_data = None
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        self.method_group = QGroupBox("Normalization Method")
        method_layout = QVBoxLayout()
        
        self.zscore_radio = QRadioButton("Z-Score (Standardization)")
        self.zscore_radio.setChecked(True)
        self.minmax_radio = QRadioButton("Min-Max Scaling")
        
        method_layout.addWidget(self.zscore_radio)
        method_layout.addWidget(self.minmax_radio)
        self.method_group.setLayout(method_layout)
        layout.addWidget(self.method_group)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def accept(self):
        try:
            method = "z score" if self.zscore_radio.isChecked() else "minmax"
            self.return_data = self.preprocessor.data_preprocess(norm=method)
            super().accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def get_result(self):
        return self.return_data

class PreprocessPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.plot_timer = QTimer()
        self.plot_timer.setSingleShot(True)
        self.plot_timer.timeout.connect(self.plot_sample_data)
        self.init_ui()
        
    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # --- Right Side: Operations (Styled like DatasetPanel) ---
        right_panel = QWidget()
        right_panel.setFixedWidth(260)
        right_panel.setObjectName("RightPanel")
        right_panel.setStyleSheet("""
            #RightPanel { 
                background-color: #252526; 
                border-left: 1px solid #3e3e42; 
            }
            /* Minimal Group Style */
            QGroupBox {
                background-color: transparent;
                border: none;
                margin-top: 15px;
                font-weight: bold;
                color: #808080;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 0px;
                padding: 0 0px;
                color: #808080;
            }
            /* Flat, Minimal Buttons */
            /* Flat, Minimal Buttons */
            QPushButton {
                background-color: #3e3e42; /* Lighter gray (VS Code style) */
                border: none;
                border-radius: 4px;
                padding: 8px 12px;
                color: #ffffff; /* White text */
                font-weight: normal;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #4e4e52;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #007acc;
            }
        """)
        
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 20, 10, 20)
        
        # 0. Logo Removed
        
        # 1. Aggregate Info (Replaces Getting Started)
        self.info_panel = AggregateInfoPanel(self.main_window)
        # Style it to match the panel look (transparent background if needed, but AggregateInfoPanel is a GroupBox)
        # We might need to adjust its style slightly or let it inherit.
        # AggregateInfoPanel sets its own title "Aggregate Information".
        
        # Remove the default border/background from AggregateInfoPanel to match our minimal style
        self.info_panel.setStyleSheet("""
            QGroupBox {
                background-color: transparent;
                border: none;
                margin-top: 15px;
                font-weight: bold;
                color: #808080;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 0px;
                padding: 0 0px;
                color: #808080;
            }
            QLabel {
                color: #cccccc;
                font-weight: normal;
            }
        """)
        
        right_layout.addWidget(self.info_panel, stretch=1)
        
        # Add separator line with spacing to center it
        right_layout.addSpacing(10)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #3e3e42; border: none;")
        line.setFixedHeight(1)
        right_layout.addWidget(line)
        right_layout.addSpacing(10)
        
        right_layout.addSpacing(10)
        # right_layout.addStretch() # Removed to align buttons up
        
        ops_group = QGroupBox("OPERATIONS")
        ops_layout = QVBoxLayout(ops_group)
        ops_layout.setContentsMargins(0, 10, 0, 0)
        
        self.btn_filter = QPushButton("Filtering")
        self.btn_filter.clicked.connect(self.open_filtering)
        
        self.btn_resample = QPushButton("Resample")
        self.btn_resample.clicked.connect(self.open_resample)
        
        self.btn_rereference = QPushButton("Re-reference")
        self.btn_rereference.clicked.connect(self.open_rereference)
        
        self.btn_normalize = QPushButton("Normalize")
        self.btn_normalize.clicked.connect(self.open_normalize)
        
        ops_layout.addWidget(self.btn_filter)
        ops_layout.addWidget(self.btn_resample)
        ops_layout.addWidget(self.btn_rereference)
        ops_layout.addWidget(self.btn_normalize)
        
        right_layout.addWidget(ops_group)
        
        # Execution Group
        exec_group = QGroupBox("EXECUTION")
        exec_layout = QVBoxLayout(exec_group)
        exec_layout.setContentsMargins(0, 10, 0, 0)
        
        # Epoching Button (Moved here, Green)
        self.btn_epoch = QPushButton("Epoching")
        self.btn_epoch.setStyleSheet("""
            QPushButton {
                background-color: #1b5e20; 
                color: #a5d6a7;
                border: 1px solid #2e7d32;
            }
            QPushButton:hover {
                background-color: #2e7d32;
                color: white;
            }
        """)
        self.btn_epoch.clicked.connect(self.open_epoching)
        exec_layout.addWidget(self.btn_epoch)

        # Reset Button (Styled distinctively but consistent shape)
        self.btn_reset = QPushButton("Reset All Preprocessing")
        self.btn_reset.setStyleSheet("""
            QPushButton {
                background-color: #4a1818; 
                color: #ff9999;
                border: 1px solid #802020;
            }
            QPushButton:hover {
                background-color: #602020;
            }
        """)
        self.btn_reset.clicked.connect(self.reset_preprocess)
        exec_layout.addWidget(self.btn_reset)
        
        right_layout.addWidget(exec_group)
        
        right_layout.addStretch() # Push everything to top
        
        # --- Right Side: Plot & History ---
        # --- Right Side: Plot & History ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(0)
        
        # Plot Group
        plot_group = QGroupBox("SIGNAL PREVIEW")
        plot_layout = QVBoxLayout()
        plot_layout.setContentsMargins(10, 20, 10, 10)
        
        # Tabs for Time/Freq
        self.plot_tabs = QTabWidget()
        
        # Tab 1: Time Domain
        self.tab_time = QWidget()
        time_layout = QVBoxLayout(self.tab_time)
        self.fig_time = Figure(figsize=(5, 3), dpi=100)
        self.fig_time.patch.set_facecolor('#2d2d2d')
        self.canvas_time = FigureCanvas(self.fig_time)
        self.ax_time = self.fig_time.add_subplot(111)
        self.ax_time.set_facecolor('#2d2d2d')
        # Style axes
        self.ax_time.spines['bottom'].set_color('#cccccc')
        self.ax_time.spines['top'].set_color('#cccccc') 
        self.ax_time.spines['right'].set_color('#cccccc')
        self.ax_time.spines['left'].set_color('#cccccc')
        self.ax_time.tick_params(axis='x', colors='#cccccc')
        self.ax_time.tick_params(axis='y', colors='#cccccc')
        self.ax_time.yaxis.label.set_color('#cccccc')
        self.ax_time.xaxis.label.set_color('#cccccc')
        self.ax_time.title.set_color('#cccccc')
        
        # Add Title and Labels with Units
        self.ax_time.set_title("Time Domain Signal")
        self.ax_time.set_xlabel("Time (s)")
        self.ax_time.set_ylabel("Amplitude (uV)")
        
        self.fig_time.tight_layout()
        time_layout.addWidget(self.canvas_time)
        self.plot_tabs.addTab(self.tab_time, "Time Domain")
        
        # Tab 2: Frequency Domain (PSD)
        self.tab_freq = QWidget()
        freq_layout = QVBoxLayout(self.tab_freq)
        self.fig_freq = Figure(figsize=(5, 3), dpi=100)
        self.fig_freq.patch.set_facecolor('#2d2d2d')
        self.canvas_freq = FigureCanvas(self.fig_freq)
        self.ax_freq = self.fig_freq.add_subplot(111)
        self.ax_freq.set_facecolor('#2d2d2d')
        # Style axes
        self.ax_freq.spines['bottom'].set_color('#cccccc')
        self.ax_freq.spines['top'].set_color('#cccccc') 
        self.ax_freq.spines['right'].set_color('#cccccc')
        self.ax_freq.spines['left'].set_color('#cccccc')
        self.ax_freq.tick_params(axis='x', colors='#cccccc')
        self.ax_freq.tick_params(axis='y', colors='#cccccc')
        self.ax_freq.yaxis.label.set_color('#cccccc')
        self.ax_freq.xaxis.label.set_color('#cccccc')
        self.ax_freq.title.set_color('#cccccc')
        
        # Add Title and Labels with Units
        self.ax_freq.set_title("Power Spectral Density")
        self.ax_freq.set_xlabel("Frequency (Hz)")
        self.ax_freq.set_ylabel("Power (uV²/Hz)")
        
        self.fig_freq.tight_layout()
        freq_layout.addWidget(self.canvas_freq)
        self.plot_tabs.addTab(self.tab_freq, "Frequency (PSD)")
        
        plot_layout.addWidget(self.plot_tabs)

        # Controls
        ctrl_layout = QHBoxLayout()
        ctrl_layout.addWidget(QLabel("Channel:"))
        self.chan_combo = QComboBox()
        self.chan_combo.setMinimumWidth(100)
        self.chan_combo.currentIndexChanged.connect(self.update_plot_only)
        ctrl_layout.addWidget(self.chan_combo)
        
        ctrl_layout.addSpacing(20)
        ctrl_layout.addWidget(QLabel("Y-Scale (uV):"))
        self.yscale_spin = QDoubleSpinBox()
        self.yscale_spin.setRange(0, 5000)
        self.yscale_spin.setValue(0) # 0 = Auto
        self.yscale_spin.setSpecialValueText("Auto")
        self.yscale_spin.setSingleStep(10)
        self.yscale_spin.valueChanged.connect(self.update_plot_only)
        ctrl_layout.addWidget(self.yscale_spin)
        
        ctrl_layout.addStretch()
        ctrl_layout.addStretch()
        plot_layout.addLayout(ctrl_layout)
        
        # Time Navigation
        time_nav_layout = QHBoxLayout()
        time_nav_layout.addWidget(QLabel("Time / Epoch:"))
        
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setRange(0, 100) # Placeholder
        self.time_slider.valueChanged.connect(self.on_time_slider_changed)
        time_nav_layout.addWidget(self.time_slider)
        
        self.time_spin = QDoubleSpinBox()
        self.time_spin.setRange(0, 10000)
        self.time_spin.setSingleStep(1.0)
        self.time_spin.valueChanged.connect(self.on_time_spin_changed)
        time_nav_layout.addWidget(self.time_spin)
        
        plot_layout.addLayout(time_nav_layout)
        plot_group.setLayout(plot_layout)
        
        # History Group
        hist_group = QGroupBox("PREPROCESSING HISTORY")
        hist_layout = QVBoxLayout(hist_group)
        hist_layout.setContentsMargins(10, 20, 10, 10)
        self.history_list = QListWidget()
        hist_layout.addWidget(self.history_list)
        # hist_group.setLayout(hist_layout) # Already passed to constructor
        
        right_layout.addWidget(plot_group, stretch=2)
        right_layout.addWidget(hist_group, stretch=1)
        
        # Add widgets to main layout (Plot on Left, Ops on Right)
        main_layout.addWidget(right_widget, stretch=1)
        main_layout.addWidget(right_panel, stretch=0)

    def on_time_slider_changed(self, value):
        self.time_spin.blockSignals(True)
        self.time_spin.setValue(value / 10.0) # Slider is int, spin is float (0.1s step)
        self.time_spin.blockSignals(False)
        self.plot_timer.start(50) # Debounce: Wait 50ms before plotting

    def on_time_spin_changed(self, value):
        self.time_slider.blockSignals(True)
        self.time_slider.setValue(int(value * 10))
        self.time_slider.blockSignals(False)
        self.plot_timer.start(50) # Debounce

    def update_panel(self):
        if not self.main_window or not hasattr(self.main_window, 'study'):
            return
            
        # Update History List
        if hasattr(self, 'info_panel'):
            self.info_panel.update_info()
            
        self.history_list.clear()
        data_list = self.main_window.study.preprocessed_data_list
        
        is_epoched = False
        if data_list:
            # Assuming all files have same history, take first one
            first_data = data_list[0]
            
            # Update History
            history = first_data.get_preprocess_history()
            if history:
                for step in history:
                    self.history_list.addItem(str(step))
            else:
                self.history_list.addItem("No preprocessing applied.")
                
            # Check if data is epoched
            is_epoched = not first_data.is_raw()
            
            # 2. Update Preprocessing Buttons State
        # Unified Style: Keep buttons enabled but show warning if locked
        if hasattr(self, 'btn_filter'):
            # self.btn_filter.setEnabled(not is_epoched)
            if is_epoched:
                self.btn_filter.setToolTip("Preprocessing is locked (Data Epoched). Click to see details.")
            else:
                self.btn_filter.setToolTip("Apply bandpass/notch filters")

        if hasattr(self, 'btn_resample'):
            # self.btn_resample.setEnabled(not is_epoched)
            if is_epoched:
                self.btn_resample.setToolTip("Preprocessing is locked (Data Epoched). Click to see details.")
            else:
                self.btn_resample.setToolTip("Change sampling rate")



        if hasattr(self, 'btn_rereference'):
            # self.btn_rereference.setEnabled(not is_epoched)
            if is_epoched:
                self.btn_rereference.setToolTip("Preprocessing is locked (Data Epoched). Click to see details.")
            else:
                self.btn_rereference.setToolTip("Change reference")

        if hasattr(self, 'btn_normalize'):
            if is_epoched:
                self.btn_normalize.setToolTip("Preprocessing is locked (Data Epoched). Click to see details.")
            else:
                self.btn_normalize.setToolTip("Apply Z-Score or Min-Max normalization")
                
        if hasattr(self, 'btn_epoch'):
            # self.btn_epoch.setEnabled(not is_epoched)
            if is_epoched:
                self.btn_epoch.setText("Epoched (Locked)")
                self.btn_epoch.setToolTip("Preprocessing is locked (Data Epoched). Click to see details.")
                # Skip Plotting for Epoched Data (as requested)
                self.history_list.addItem("Preprocessing Locked (Epoched).")
                self.ax_time.clear()
                self.ax_time.text(0.5, 0.5, "Data is Epoched\nPreprocessing Locked", ha='center', va='center', color='#cccccc')
                self.canvas_time.draw()
                self.ax_freq.clear()
                self.ax_freq.text(0.5, 0.5, "Data is Epoched", ha='center', va='center', color='#cccccc')
                self.canvas_freq.draw()
                return
            else:
                self.btn_epoch.setText("Epoching")
                
            # Update Plot
            if data_list:
                # Update channel list
                ch_names = first_data.get_mne().ch_names
                self.chan_combo.blockSignals(True)
                self.chan_combo.clear()
                self.chan_combo.addItems(ch_names)
                self.chan_combo.blockSignals(False)
                
                # Update time range
                duration = first_data.get_epochs_length() if not first_data.is_raw() else (first_data.get_mne().times[-1])
                self.time_spin.setRange(0, duration)
                self.time_slider.setRange(0, int(duration * 10))
                
                self.plot_sample_data()
        else:
            self.history_list.addItem("No data loaded.")
            self.ax_time.clear()
            self.ax_time.text(0.5, 0.5, "No Data", ha='center', va='center', color='#cccccc')
            self.canvas_time.draw()
            self.ax_freq.clear()
            self.ax_freq.text(0.5, 0.5, "No Data", ha='center', va='center', color='#cccccc')
            self.canvas_freq.draw()

    def update_plot_only(self):
        self.plot_sample_data()

    def plot_sample_data(self):
        self.ax_time.clear()
        self.ax_freq.clear()
        
        if not self.main_window or not hasattr(self.main_window, 'study'):
            return
            
        data_list = self.main_window.study.preprocessed_data_list
        orig_list = self.main_window.study.loaded_data_list
        
        if not data_list:
            return

        try:
            # Use first file
            raw_obj = data_list[0]
            orig_obj = orig_list[0] if orig_list else None
            
            chan_idx = self.chan_combo.currentIndex()
            if chan_idx < 0: return # No channel selected
            chan_name = self.chan_combo.currentText()
            
            sfreq = raw_obj.get_sfreq()
            
            # --- Helper to get data ---
            def get_chan_data(obj, ch_idx, start_time=0, duration=5):
                is_raw = obj.is_raw()
                obj_sfreq = obj.get_sfreq()
                data = obj.get_mne().get_data()
                if data is None: return None, None
                
                if is_raw:
                    start_sample = int(start_time * obj_sfreq)
                    n_samples = int(duration * obj_sfreq)
                    end_sample = start_sample + n_samples
                    
                    # Check bounds
                    if start_sample >= data.shape[1]:
                        return None, None
                    if end_sample > data.shape[1]:
                        end_sample = data.shape[1]
                        
                    y = data[ch_idx, start_sample:end_sample]
                    x = np.arange(start_sample, end_sample) / obj_sfreq
                    return x, y
                else:
                    if data.ndim == 3:
                        # For epochs, start_time is the epoch index
                        epoch_idx = int(start_time)
                        if epoch_idx < 0: epoch_idx = 0
                        if epoch_idx >= data.shape[0]: epoch_idx = data.shape[0] - 1
                        
                        y = data[epoch_idx, ch_idx, :] 
                        x = obj.get_mne().times
                        return x, y
                return None, None

            # Get Current Data
            start_t = self.time_spin.value()
            x_curr, y_curr = get_chan_data(raw_obj, chan_idx, start_time=start_t)
            
            # Get Original Data (if available and compatible)
            x_orig, y_orig = None, None
            if orig_obj:
                # Try to match time
                x_orig, y_orig = get_chan_data(orig_obj, chan_idx, start_time=start_t)
            
            # --- Time Domain Plot ---
            if y_curr is not None:
                # Scale to uV
                y_curr_uv = y_curr * 1e6
                y_orig_uv = y_orig * 1e6 if y_orig is not None else None
                
                # x is already time array
                
                if y_orig_uv is not None:
                    self.ax_time.plot(x_orig, y_orig_uv, color='gray', alpha=0.5, label='Original')
                
                self.ax_time.plot(x_curr, y_curr_uv, color='#2196F3', linewidth=1, label='Current')
                if raw_obj.is_raw():
                    self.ax_time.set_title(f"{chan_name} (Time)", color='#cccccc')
                else:
                    self.ax_time.set_title(f"{chan_name} (Epoch {int(start_t)})", color='#cccccc')
                self.ax_time.set_xlabel("Time (s)", color='#cccccc')
                self.ax_time.set_ylabel("Amplitude (uV)", color='#cccccc') # Updated unit
                legend = self.ax_time.legend(loc='upper right', fontsize='small', facecolor='#2d2d2d', edgecolor='#cccccc')
                for text in legend.get_texts():
                    text.set_color("#cccccc")
                
                self.ax_time.tick_params(axis='x', colors='#cccccc')
                self.ax_time.tick_params(axis='y', colors='#cccccc')
                for spine in self.ax_time.spines.values():
                    spine.set_color('#cccccc')

                self.ax_time.grid(True, linestyle='--', alpha=0.5)
                
                # Apply Y-Scale
                y_scale = self.yscale_spin.value()
                if y_scale > 0:
                    self.ax_time.set_ylim(-y_scale, y_scale)
                    
                # --- Plot Events ---
                if raw_obj.is_raw():
                    try:
                        events, event_id_map = raw_obj.get_event_list()
                        if len(events) > 0:
                            # Create reverse map for labels
                            id_to_name = {v: k for k, v in event_id_map.items()}
                            
                            # Define time window
                            t_start_view = x_curr[0]
                            t_end_view = x_curr[-1]
                            
                            for ev in events:
                                ev_sample = ev[0]
                                ev_time = ev_sample / sfreq
                                ev_id = ev[2]
                                
                                if t_start_view <= ev_time <= t_end_view:
                                    self.ax_time.axvline(x=ev_time, color='#ff9800', linestyle='--', alpha=0.8)
                                    label = id_to_name.get(ev_id, str(ev_id))
                                    # Place text near top, slightly offset to avoid blocking line
                                    y_lim = self.ax_time.get_ylim()
                                    y_pos = y_lim[1] - (y_lim[1] - y_lim[0]) * 0.05
                                    # Offset x slightly
                                    x_offset = (t_end_view - t_start_view) * 0.01 
                                    self.ax_time.text(ev_time + x_offset, y_pos, label, color='#ff9800', ha='left', va='bottom', fontsize='small', rotation=0)
                    except Exception as e:
                        logger.warning(f"Failed to plot events: {e}")
            
            # --- Frequency Domain (PSD) Plot ---
            if y_curr is not None:
                # Calculate PSD (using uV data)
                def calc_psd(sig):
                    f, Pxx = welch(sig, fs=sfreq, nperseg=min(len(sig), 256*4))
                    return f, Pxx
                
                f_curr, p_curr = calc_psd(y_curr_uv)
                
                if y_orig_uv is not None:
                    f_orig, p_orig = calc_psd(y_orig_uv)
                    self.ax_freq.plot(f_orig, 10 * np.log10(p_orig), color='gray', alpha=0.5, label='Original')
                
                self.ax_freq.plot(f_curr, 10 * np.log10(p_curr), color='#2196F3', linewidth=1, label='Current')
                self.ax_freq.set_title(f"{chan_name} (PSD)", color='#cccccc')
                self.ax_freq.set_xlabel("Frequency (Hz)", color='#cccccc')
                self.ax_freq.set_ylabel("Power (dB/Hz)", color='#cccccc') # PSD of uV is uV^2/Hz, log is dB
                legend = self.ax_freq.legend(loc='upper right', fontsize='small', facecolor='#2d2d2d', edgecolor='#cccccc')
                for text in legend.get_texts():
                    text.set_color("#cccccc")
                
                self.ax_freq.tick_params(axis='x', colors='#cccccc')
                self.ax_freq.tick_params(axis='y', colors='#cccccc')
                for spine in self.ax_freq.spines.values():
                    spine.set_color('#cccccc')

                self.ax_freq.grid(True, linestyle='--', alpha=0.5)
                
            self.canvas_time.draw()
            self.canvas_freq.draw()
            
        except Exception as e:
            logger.error(f"Plotting failed: {e}")
            self.ax_time.text(0.5, 0.5, "Plot Error", ha='center', va='center', color='#cccccc')
            self.canvas_time.draw()

    def check_lock(self):
        if self.main_window and hasattr(self.main_window, 'study') and self.main_window.study.epoch_data:
            QMessageBox.warning(self, "Action Blocked", 
                                "Preprocessing is locked because data has been Epoched.\n"
                                "Please 'Reset All Preprocessing' to make changes.")
            return True
        return False

    def open_filtering(self):
        if self.check_lock(): return
        if not self.main_window or not hasattr(self.main_window, 'study') or not self.main_window.study.preprocessed_data_list:
            QMessageBox.warning(self, "Warning", "No data loaded.")
            return
            
        dialog = FilteringDialog(self, self.main_window.study.preprocessed_data_list)
        if dialog.exec():
            result = dialog.get_result()
            if result:
                self.main_window.study.set_preprocessed_data_list(result)
                # self.main_window.study.preprocess(Preprocessor.Filtering, l_freq=None, h_freq=None) # Log only?
                # Actually study.preprocess calls the preprocessor. 
                # Here we already ran it in dialog.
                # We should probably refactor to let study run it, but current pattern is dialog runs it.
                # Just update UI.
                self.update_panel()
                if self.main_window:
                    self.main_window.refresh_panels()
                QMessageBox.information(self, "Success", "Filtering applied.")

    def open_resample(self):
        if self.check_lock(): return
        if not self.main_window or not hasattr(self.main_window, 'study') or not self.main_window.study.preprocessed_data_list:
            QMessageBox.warning(self, "Warning", "No data loaded.")
            return
            
        dialog = ResampleDialog(self, self.main_window.study.preprocessed_data_list)
        if dialog.exec():
            result = dialog.get_result()
            if result:
                self.main_window.study.set_preprocessed_data_list(result)
                self.update_panel()
                if self.main_window:
                    self.main_window.refresh_panels()
                QMessageBox.information(self, "Success", "Resampling applied.")

    def open_rereference(self):
        if self.check_lock(): return
        if not self.main_window or not hasattr(self.main_window, 'study') or not self.main_window.study.preprocessed_data_list:
            QMessageBox.warning(self, "Warning", "No data loaded.")
            return
            
        dialog = RereferenceDialog(self, self.main_window.study.preprocessed_data_list)
        if dialog.exec():
            result = dialog.get_result()
            if result:
                self.main_window.study.set_preprocessed_data_list(result)
                self.update_panel()
                if self.main_window:
                    self.main_window.refresh_panels()
                QMessageBox.information(self, "Success", "Re-reference applied.")

    def open_normalize(self):
        if self.check_lock(): return
        if not self.main_window or not hasattr(self.main_window, 'study') or not self.main_window.study.preprocessed_data_list:
            QMessageBox.warning(self, "Warning", "No data loaded.")
            return
            
        dialog = NormalizeDialog(self, self.main_window.study.preprocessed_data_list)
        if dialog.exec():
            result = dialog.get_result()
            if result:
                self.main_window.study.set_preprocessed_data_list(result)
                self.update_panel()
                if self.main_window:
                    self.main_window.refresh_panels()
                QMessageBox.information(self, "Success", "Normalization applied.")

    def open_epoching(self):
        if self.check_lock(): return
        if not self.main_window or not hasattr(self.main_window, 'study') or not self.main_window.study.preprocessed_data_list:
            QMessageBox.warning(self, "Warning", "No data loaded.")
            return
            
        dialog = EpochingDialog(self, self.main_window.study.preprocessed_data_list)
        if dialog.exec():
            result = dialog.get_result()
            if result:
                self.main_window.study.set_preprocessed_data_list(result)
                
                # Lock preprocessing after epoching
                self.main_window.study.lock_dataset()
                
                self.update_panel()
                if hasattr(self.main_window, 'update_info_panel'):
                    self.main_window.update_info_panel()
                QMessageBox.information(self, "Success", "Epoching applied.\nPreprocessing is now LOCKED.")



    def open_rereference(self):
        if self.check_lock(): return
        if not self.main_window or not hasattr(self.main_window, 'study') or not self.main_window.study.preprocessed_data_list:
            QMessageBox.warning(self, "Warning", "No data loaded.")
            return
            
        dialog = RereferenceDialog(self, self.main_window.study.preprocessed_data_list)
        if dialog.exec():
            result = dialog.get_result()
            if result:
                self.main_window.study.set_preprocessed_data_list(result)
                self.update_panel()
                if hasattr(self.main_window, 'update_info_panel'):
                    self.main_window.update_info_panel()
                QMessageBox.information(self, "Success", "Re-referencing applied.")

    def reset_preprocess(self):
        if not self.check_data_loaded():
            return
            
        reply = QMessageBox.question(
            self, "Confirm Reset", 
            "Are you sure you want to reset all preprocessing steps?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.main_window.study.reset_preprocess()
                self.update_panel()
                if hasattr(self.main_window, 'update_info_panel'):
                    self.main_window.update_info_panel()
                QMessageBox.information(self, "Success", "Preprocessing reset.")
            except Exception as e:
                logger.error(f"Reset failed: {e}")
                QMessageBox.critical(self, "Error", f"Reset failed: {e}")

    def check_data_loaded(self):
        if not self.main_window or not hasattr(self.main_window, 'study') or not self.main_window.study.preprocessed_data_list:
            QMessageBox.warning(self, "Warning", "No data loaded. Please import data first.")
            return False
        return True
