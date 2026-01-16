from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QGroupBox, 
    QGridLayout, QMessageBox, QFrame, QTabWidget, QTreeWidget, QTreeWidgetItem,
    QHeaderView, QProgressBar, QTextEdit, QTableWidget, QTableWidgetItem
)
from PyQt6.QtCore import Qt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from .training_setting import TrainingSettingWindow
from .test_only_setting import TestOnlySettingWindow
from .model_selection import ModelSelectionWindow
from .training_manager import TrainingManagerWindow
from ..dataset.data_splitting_setting import DataSplittingSettingWindow
from XBrainLab.ui.dashboard_panel.info import AggregateInfoPanel
from XBrainLab.backend.controller.training_controller import TrainingController

class MetricTab(QWidget):
    """
    A tab containing a plot and a table for a specific metric (e.g., Accuracy, Loss).
    """
    def __init__(self, metric_name, color="#4CAF50"):
        super().__init__()
        self.metric_name = metric_name
        self.color = color
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        
        # 1. Plot
        self.fig = Figure(figsize=(5, 3), dpi=100)
        self.fig.patch.set_facecolor('#2d2d2d') # Dark background
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor('#2d2d2d') # Dark axes
        
        # Style axes
        self.ax.spines['bottom'].set_color('#cccccc')
        self.ax.spines['top'].set_color('#cccccc') 
        self.ax.spines['right'].set_color('#cccccc')
        self.ax.spines['left'].set_color('#cccccc')
        self.ax.tick_params(axis='x', colors='#cccccc')
        self.ax.tick_params(axis='y', colors='#cccccc')
        self.ax.yaxis.label.set_color('#cccccc')
        self.ax.xaxis.label.set_color('#cccccc')
        self.ax.title.set_color('#cccccc')
        
        self.ax.set_title(f"{self.metric_name} vs Epoch")
        self.ax.set_xlabel("Epoch")
        
        # Add Units
        ylabel = self.metric_name
        if "Accuracy" in self.metric_name:
            ylabel += " (%)"
        self.ax.set_ylabel(ylabel)
        
        self.ax.grid(True, linestyle='--', alpha=0.3, color='#666666') # Subtle grid
        self.fig.tight_layout()
        layout.addWidget(self.canvas, stretch=1)
        
        # 2. Training Summary (Removed as per redesign)
        # self.summary_text = QLabel("Model: -- | Batch: -- | LR: --")
        # ... removed ...
        
        self.epochs = []
        self.train_vals = []
        self.val_vals = []
        
    def update_plot(self, epoch, train_val, val_val):
        self.epochs.append(epoch)
        self.train_vals.append(train_val)
        self.val_vals.append(val_val)
        
        self.ax.clear()
        
        # Re-apply styling (ax.clear removes it)
        self.ax.set_facecolor('#2d2d2d')
        self.ax.spines['bottom'].set_color('#cccccc')
        self.ax.spines['top'].set_color('#cccccc') 
        self.ax.spines['right'].set_color('#cccccc')
        self.ax.spines['left'].set_color('#cccccc')
        self.ax.tick_params(axis='x', colors='#cccccc')
        self.ax.tick_params(axis='y', colors='#cccccc')
        self.ax.yaxis.label.set_color('#cccccc')
        self.ax.xaxis.label.set_color('#cccccc')
        self.ax.title.set_color('#cccccc')
        
        # Plot Lines
        self.ax.plot(self.epochs, self.train_vals, marker='o', markersize=4, linestyle='-', color=self.color, label=f"Train {self.metric_name}")
        # Improved Validation Line: Dashed, lighter color, smaller dot marker
        self.ax.plot(self.epochs, self.val_vals, marker='o', markersize=4, linestyle='--', color='#aaaaaa', label=f"Val {self.metric_name}")
        
        self.ax.set_title(f"{self.metric_name} vs Epoch")
        self.ax.set_xlabel("Epoch")
        
        # Add Units
        ylabel = self.metric_name
        if "Accuracy" in self.metric_name:
            ylabel += " (%)"
        self.ax.set_ylabel(ylabel)
        
        self.ax.grid(True, linestyle='--', alpha=0.3, color='#666666')
        
        # Legend styling
        legend = self.ax.legend(facecolor='#2d2d2d', edgecolor='#cccccc')
        for text in legend.get_texts():
            text.set_color('#cccccc')
            
        self.canvas.draw()
        
    def clear(self):
        # Clear plot
        self.ax.clear()
        self.ax.set_title(f"{self.metric_name} vs Epoch")
        self.ax.set_xlabel("Epoch")
        
        # Add Units
        ylabel = self.metric_name
        if "Accuracy" in self.metric_name:
            ylabel += " (%)"
        self.ax.set_ylabel(ylabel)
        
        self.ax.grid(True, linestyle='--', alpha=0.3, color='#666666')
        self.canvas.draw()
        
        # Clear history data
        if hasattr(self, 'epochs'): self.epochs = []
        if hasattr(self, 'train_vals'): self.train_vals = []
        if hasattr(self, 'val_vals'): self.val_vals = []

    # set_summary removed

    # set_summary removed

class TrainingPanel(QWidget):
    """
    Panel for managing the training process.
    """
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        # self.study = main_window.study # Decoupled
        self.controller = TrainingController(main_window.study)
        
        self.current_plotting_record = None # Initialize here to avoid AttributeError
        self.plan_items = {} # Map id(plan) -> QTreeWidgetItem
        self.run_items = {}  # Map id(record) -> QTreeWidgetItem
        
        self.init_ui()
        
        # Timer for polling training status
        from PyQt6.QtCore import QTimer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_loop)
        self.training_completed_shown = False  # Track if completion message was shown
        
    def init_ui(self):
        # Main Layout: Horizontal (Left: Content, Right: Controls)
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0) # Full width
        main_layout.setSpacing(0)
        
        # --- Left Column: Training Status (Main Content) ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(20, 20, 20, 20)
        left_layout.setSpacing(0)
        
        # Training Plots Group
        plots_group = QGroupBox("TRAINING PLOTS")
        plots_layout = QVBoxLayout(plots_group)
        plots_layout.setContentsMargins(10, 20, 10, 10)
        
        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabWidget::pane { border: 0; }") # Clean look
        
        # Tab 1: Accuracy
        self.tab_acc = MetricTab("Accuracy", color="#4CAF50")
        self.tabs.addTab(self.tab_acc, "Accuracy")
        
        # Tab 2: Loss
        self.tab_loss = MetricTab("Loss", color="#ef5350")
        self.tabs.addTab(self.tab_loss, "Loss")
        
        # Tab 3: Log
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setPlaceholderText("Training logs will appear here...")
        self.log_text.setStyleSheet("background-color: #1e1e1e; border: 1px solid #333; color: #aaa; font-family: monospace;")
        self.tabs.addTab(self.log_text, "Log")
        
        plots_layout.addWidget(self.tabs)
        left_layout.addWidget(plots_group, stretch=2)
        
        # Training History Group
        history_group = QGroupBox("TRAINING HISTORY")
        history_layout = QVBoxLayout(history_group)
        history_layout.setContentsMargins(10, 20, 10, 10)
        
        # History Table
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(11)
        self.history_table.setHorizontalHeaderLabels([
            "Group", "Run", "Model", "Status", "Progress", 
            "Train Loss", "Train Acc", "Val Loss", "Val Acc", "LR", "Time"
        ])
        
        # Style the table
        self.history_table.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e1e;
                border: 1px solid #333;
                color: #cccccc;
                font-size: 13px;
                gridline-color: #333;
            }
            QHeaderView::section {
                background-color: #2d2d2d;
                color: #cccccc;
                padding: 6px;
                border: 1px solid #333;
                font-weight: bold;
            }
            QTableWidget::item {
                padding: 4px;
                border-bottom: 1px solid #2a2a2a;
            }
            QTableWidget::item:selected {
                background-color: #007acc;
                color: #ffffff;
            }
        """)
        
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        # Column widths
        header = self.history_table.horizontalHeader()
        for i in range(11):
             header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
             
        self.history_table.setColumnWidth(0, 80)  # Group
        self.history_table.setColumnWidth(1, 80)  # Run
        self.history_table.setColumnWidth(2, 150) # Model
        self.history_table.setColumnWidth(3, 100) # Status
        self.history_table.setColumnWidth(4, 80)  # Progress
        # Metrics
        for i in range(5, 11):
            self.history_table.setColumnWidth(i, 80)
            
        header.setStretchLastSection(True)
        
        # Connect selection
        self.history_table.itemSelectionChanged.connect(self.on_history_selection_changed)
        
        history_layout.addWidget(self.history_table)
        
        # Internal map to track rows: row_index -> (plan, run)
        self.row_map = {} 
        
        left_layout.addWidget(history_group, stretch=1)
        main_layout.addWidget(left_widget, stretch=1)
        
        # --- Right Side: Sidebar (Styled like Dataset/Preprocess) ---
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
            QPushButton {
                background-color: #3e3e42; 
                border: none;
                border-radius: 4px;
                padding: 8px 12px;
                color: #ffffff;
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
        
        # 1. Aggregate Information (New)
        self.info_panel = AggregateInfoPanel(self.main_window)
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

        
        # Group 1: Configuration Buttons
        config_group = QGroupBox("CONFIGURATION")
        config_layout = QVBoxLayout(config_group)
        config_layout.setContentsMargins(0, 10, 0, 0)
        
        self.btn_split = QPushButton("Dataset Splitting")
        self.btn_split.clicked.connect(self.split_data)
        config_layout.addWidget(self.btn_split)
        
        self.btn_model = QPushButton("Model Selection")
        self.btn_model.clicked.connect(self.select_model)
        config_layout.addWidget(self.btn_model)
        
        self.btn_setting = QPushButton("Training Setting")
        self.btn_setting.clicked.connect(self.training_setting)
        config_layout.addWidget(self.btn_setting)
        
        right_layout.addWidget(config_group)
        right_layout.addSpacing(20)
        
        
        # Spacer to push Execution group to bottom
        # right_layout.addStretch()
        
        # Group 2: Execution
        exec_group = QGroupBox("EXECUTION")
        exec_layout = QVBoxLayout(exec_group)
        exec_layout.setContentsMargins(0, 10, 0, 0)
        
        self.btn_start = QPushButton("Start Training")
        self.btn_start.setStyleSheet("""
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
        self.btn_start.clicked.connect(self.start_training)
        self.btn_start.setEnabled(False) # Locked until configured
        exec_layout.addWidget(self.btn_start)
        
        self.btn_stop = QPushButton("Stop Training")
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background-color: #bf360c; 
                color: #ffccbc;
                border: 1px solid #d84315;
            }
            QPushButton:hover {
                background-color: #d84315;
                color: white;
            }
        """)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_training)
        exec_layout.addWidget(self.btn_stop)
        
        self.btn_clear = QPushButton("Clear History")
        self.btn_clear.setStyleSheet("""
            QPushButton {
                background-color: #4a1818; 
                color: #ff9999;
                border: 1px solid #802020;
            }
            QPushButton:hover {
                background-color: #602020;
            }
        """)
        self.btn_clear.clicked.connect(self.clear_history)
        exec_layout.addWidget(self.btn_clear)
        
        right_layout.addWidget(exec_group)
        
        right_layout.addStretch() # Push everything to top
        
        main_layout.addWidget(right_panel, stretch=0)
        
        # Initial check
        self.check_ready_to_train()

    # --- Event Handlers ---

    def split_data(self):
        if not self.controller.has_loaded_data():
            QMessageBox.warning(self, "No Data", "Please load and preprocess data first.")
            return
        
        # Validate epoch_data exists
        if not self.controller.has_epoch_data():
            QMessageBox.warning(
                self, 
                "No Epoched Data", 
                "Please perform epoching in the Preprocess panel first.\n\n"
                "Dataset splitting requires epoched data to generate training, validation, and test sets."
            )
            return

        # Check if training is running
        if self.controller.is_training():
            QMessageBox.warning(self, "Training Running", "Cannot change data splitting while training is running.")
            return

        win = DataSplittingSettingWindow(self, self.controller.get_epoch_data())
        if win.exec():
            # Check if reset is needed
            if self.controller.has_datasets() or (self.controller.get_trainer() is not None):
                reply = QMessageBox.question(
                    self, 
                    "Reset Training Data", 
                    "Applying new data splitting will clear existing datasets and training history.\n\n"
                    "Do you want to continue?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return
                # Force clean
                self.controller.clean_datasets(force_update=True)

            generator = win.get_result()
            if generator:
                self.controller.apply_data_splitting(generator)
            QMessageBox.information(self, "Success", "Data splitting configuration saved.")
            self.check_ready_to_train()

    def select_model(self):
        # Check if training is running
        if self.controller.is_training():
            QMessageBox.warning(self, "Training Running", "Cannot change model while training is running.")
            return

        win = ModelSelectionWindow(self)
        if win.exec():
            holder = win.get_result()
            self.controller.set_model_holder(holder)
            # ModelHolder doesn't have model_name, use get_model_desc_str() or target_model.__name__
            model_name = holder.target_model.__name__
            QMessageBox.information(self, "Success", f"Model selected: {model_name}")
            self.check_ready_to_train()

    def training_setting(self):
        # Check if training is running
        if self.controller.is_training():
            QMessageBox.warning(self, "Training Running", "Cannot change training settings while training is running.")
            return

        win = TrainingSettingWindow(self)
        if win.exec():
            self.controller.set_training_option(win.get_result())
            QMessageBox.information(self, "Success", "Training settings saved.")
            self.check_ready_to_train()

    def start_training(self):
        """Start training using the controller."""
        try:
            if not self.controller.is_training():
                # This will generate plan and start training
                self.controller.start_training()
                
                # Check if started successfully
                if self.controller.is_training():
                    self.timer.start(100) # Start polling
                    self.log_text.append("Training started.")
                else:
                    self.log_text.append("Failed to start training.")
            else:
                 self.log_text.append("Training is already running.")
            
            self.training_completed_shown = False
            self.btn_stop.setEnabled(True)
            self.check_ready_to_train()

        except Exception as e:
             QMessageBox.critical(self, "Error", f"Failed to start training: {e}")
             self.training_finished()

    def stop_training(self):
        if self.controller.is_training():
            self.controller.stop_training() 

    def clear_history(self):
        """Clear the training history."""
        try:
            if self.controller.is_training():
                QMessageBox.warning(self, "Warning", "Cannot clear history while training is running.")
                return
            
            self.controller.clear_history()
        except Exception as e:
             QMessageBox.warning(self, "Warning", f"Error clearing history: {e}")
             return
            
        self.history_table.setRowCount(0)
        self.row_map.clear()
        self.tab_acc.clear()
        self.tab_loss.clear()
        # self.tab_summary.clear() # Removed
        self.log_text.clear()
        self.log_text.append("History cleared.")

    def update_loop(self):
        # Poll trainer status
        if not self.controller.is_training():
            self.timer.stop()
            self.training_finished()
        
        # Update Plots/Progress
        # Use Controller to get flattened history
        target_rows = self.controller.get_formatted_history()
                
        # If row count mismatch, adjust
        if self.history_table.rowCount() != len(target_rows):
            self.history_table.setRowCount(len(target_rows))
            
        # Update content
        for row_idx, data in enumerate(target_rows):
            plan = data['plan']
            record = data['record']
            group_name = data['group_name']
            run_name = data['run_name']
            model_name = data['model_name']
            is_plan_active = data['is_active']
            is_current_run = data.get('is_current_run', False)
            
            # Store mapping
            self.row_map[row_idx] = (plan, record)
            
            # Determine status
            epoch = record.get_epoch()
            max_epochs = plan.option.epoch
            
            is_active = False
            if record.is_finished():
                status = "Done"
            elif is_current_run:
                status = "Running"
                is_active = True
            elif record.epoch == 0:
                status = "Pending"
            else:
                status = "Stopped"
            
            # Helper to set item text safely
            def set_item(col, text):
                item = self.history_table.item(row_idx, col)
                if not item:
                    item = QTableWidgetItem()
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.history_table.setItem(row_idx, col, item)
                if item.text() != text:
                    item.setText(text)
            
            set_item(0, group_name)
            set_item(1, run_name)
            set_item(2, model_name)
            set_item(3, status)
            set_item(4, f"{epoch}/{max_epochs}")
            
            # Metrics
            def get_last(key, source):
                if len(source[key]) > 0:
                    val = source[key][-1]
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        return 0.0
                return 0.0

            from XBrainLab.backend.training.record.train import RecordKey, TrainRecordKey
            
            train_loss = get_last(TrainRecordKey.LOSS, record.train)
            train_acc = get_last(TrainRecordKey.ACC, record.train)
            val_loss = get_last(RecordKey.LOSS, record.val)
            val_acc = get_last(RecordKey.ACC, record.val)
            lr = get_last(TrainRecordKey.LR, record.train)
            
            val_loss_str = f"{val_loss:.4f}" if val_loss != 0 else "N/A"
            val_acc_str = f"{val_acc:.2f}%" if val_acc != 0 else "N/A"
            
            set_item(5, f"{train_loss:.4f}")
            set_item(6, f"{train_acc:.2f}%")
            set_item(7, val_loss_str)
            set_item(8, val_acc_str)
            set_item(9, f"{lr:.6f}")
            
            import datetime
            import time
            time_str = "-"
            
            start_ts = getattr(record, 'start_timestamp', None)
            end_ts = getattr(record, 'end_timestamp', None)
            
            if start_ts:
                if end_ts:
                    duration = end_ts - start_ts
                else:
                    duration = time.time() - start_ts
                
                # Format duration as HH:MM:SS
                m, s = divmod(int(duration), 60)
                h, m = divmod(m, 60)
                time_str = f"{h:02d}:{m:02d}:{s:02d}"
            
            set_item(10, time_str)

            # Update plots logic
            selected_items = self.history_table.selectedItems()
            user_selected_row = -1
            if selected_items:
                user_selected_row = selected_items[0].row()
            
            should_plot = False
            if user_selected_row != -1:
                if user_selected_row == row_idx:
                    should_plot = True
            elif is_active:
                should_plot = True
                
            if should_plot:
                if self.current_plotting_record != record:
                    self.current_plotting_record = record
                    self.refresh_plot(record)
                
                current_plot_epoch = 0
                if self.tab_acc.epochs:
                    current_plot_epoch = self.tab_acc.epochs[-1]
                
                if is_active and epoch > current_plot_epoch:
                     self.tab_acc.update_plot(epoch, train_acc, val_acc)
                     self.tab_loss.update_plot(epoch, train_loss, val_loss)
                     
                     # Log
                     timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                     log_msg = (
                        f"[{timestamp}] {group_name} {record.get_name()} Epoch {epoch}: "
                        f"Loss={train_loss:.4f}, Acc={train_acc:.2f}%, "
                        f"Val Loss={val_loss_str}, Val Acc={val_acc_str}"
                     )
                     self.log_text.append(log_msg)

    def on_history_selection_changed(self):
        """Handle history table selection change."""
        selected_items = self.history_table.selectedItems()
        if not selected_items:
            return
            
        row = selected_items[0].row()
        if row in self.row_map:
            plan, record = self.row_map[row]
            self.current_plotting_record = record
            self.refresh_plot(record)

    def refresh_plot(self, record):
        """Refresh the plots with the full history of the given record."""
        self.tab_acc.clear()
        self.tab_loss.clear()
        
        # Re-populate data
        from XBrainLab.backend.training.record.train import RecordKey, TrainRecordKey
        
        epochs = len(record.train[TrainRecordKey.ACC])
        for i in range(epochs):
            epoch = i + 1
            
            def get_val(key, source, idx):
                if idx < len(source[key]):
                    val = source[key][idx]
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        return 0.0
                return 0.0

            train_acc = get_val(TrainRecordKey.ACC, record.train, i)
            val_acc = get_val(RecordKey.ACC, record.val, i)
            train_loss = get_val(TrainRecordKey.LOSS, record.train, i)
            val_loss = get_val(RecordKey.LOSS, record.val, i)
            
            self.tab_acc.update_plot(epoch, train_acc, val_acc)
            self.tab_loss.update_plot(epoch, train_loss, val_loss)

    def training_finished(self):
        self.check_ready_to_train() # Re-enable start button if ready
        self.btn_stop.setEnabled(False)
        if self.timer.isActive():
            self.timer.stop()
        
        # Only show message once
        if not self.training_completed_shown:
            self.training_completed_shown = True
            QMessageBox.information(self, "Done", "All training jobs finished.")

    def update_info(self):
        """Update the Aggregate Info Panel."""
        if hasattr(self, 'info_panel'):
            self.info_panel.update_info()

    def update_panel(self):
        """Update panel content when switched to."""
        self.update_info()
        self.check_ready_to_train()
        
    def check_ready_to_train(self):
        """Check if all configurations are set and enable/disable start button."""
        ready = self.controller.validate_ready()
        self.btn_start.setEnabled(ready)
        
        if not ready:
            missing = self.controller.get_missing_requirements()
            self.btn_start.setToolTip(f"Please configure: {', '.join(missing)}")
        else:
            self.btn_start.setToolTip("Start Training")
