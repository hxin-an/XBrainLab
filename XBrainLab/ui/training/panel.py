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
        self.ax.set_ylabel(self.metric_name)
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
        self.ax.set_ylabel(self.metric_name)
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
        self.ax.set_ylabel(self.metric_name)
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
        self.study = main_window.study
        
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
        
        # 0. Logo (Minimal, no frame)
        logo_frame = QFrame()
        logo_frame.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border: none;
            }
        """)
        logo_layout = QVBoxLayout(logo_frame)
        logo_layout.setContentsMargins(0, 0, 0, 10)
        
        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        logo_label.setStyleSheet("border: none; background: transparent;") 
        
        import os
        logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "logo.svg")
        if os.path.exists(logo_path):
            from PyQt6.QtGui import QPixmap
            pixmap = QPixmap(logo_path)
            # Scale pixmap to fit panel width (260 - 20 margin = 240)
            scaled_pixmap = pixmap.scaledToWidth(240, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(scaled_pixmap)
            logo_label.setScaledContents(False)
        else:
            logo_label.setText("XBrainLab")
            logo_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #cccccc; margin-bottom: 5px; border: none;")
            
        logo_layout.addWidget(logo_label)
        right_layout.addWidget(logo_frame)
        
        # 1. Configuration Summary Table (Replaces Getting Started)
        self.summary_group = QGroupBox("CONFIGURATION SUMMARY")
        self.summary_group.setStyleSheet("QGroupBox { border: none; margin-top: 10px; font-weight: bold; color: #808080; } QGroupBox::title { color: #808080; }")
        summary_layout = QVBoxLayout(self.summary_group)
        summary_layout.setContentsMargins(0, 8, 0, 0)
        summary_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.summary_table = QTableWidget()
        self.summary_table.setColumnCount(2)
        self.summary_table.setHorizontalHeaderLabels(["Setting", "Value"])
        self.summary_table.verticalHeader().setVisible(False)
        self.summary_table.horizontalHeader().setVisible(False) # Clean look
        self.summary_table.setShowGrid(False)
        self.summary_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.summary_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.summary_table.setStyleSheet("""
            QTableWidget {
                background-color: transparent;
                border: none;
                color: #cccccc;
            }
            QTableWidget::item {
                padding: 4px;
                border-bottom: 1px solid #3e3e42;
            }
        """)
        self.summary_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.summary_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        
        summary_layout.addWidget(self.summary_table)
        right_layout.addWidget(self.summary_group)
        
        # Add more spacing to separate Summary from Configuration
        right_layout.addSpacing(120)
        
        # Limit height to prevent pushing content too far
        self.summary_table.setMaximumHeight(500)
        
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
        
        # Initialize summary
        self.update_summary()
        
        # Spacer to push Execution group to bottom
        right_layout.addStretch()
        
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
        
        main_layout.addWidget(right_panel, stretch=0)

    # --- Event Handlers ---
    def update_summary(self):
        """Update the configuration summary table based on current study state."""
        self.summary_table.setRowCount(0)
        
        def add_row(setting, value):
            row = self.summary_table.rowCount()
            self.summary_table.insertRow(row)
            self.summary_table.setItem(row, 0, QTableWidgetItem(setting))
            self.summary_table.setItem(row, 1, QTableWidgetItem(value))
            
        # 1. Dataset Splitting
        if self.study.dataset_generator:
            gen = self.study.dataset_generator
            if gen.config:
                # Validation Split Info
                val_splitters = gen.config.val_splitter_list
                for s in val_splitters:
                    if s.is_option:
                        info = f"{s.text}"
                        if s.split_unit:
                            info += f" ({s.split_unit.value}: {s.value_var})"
                        add_row("Val Split", info)
                        
                # Test Split Info
                test_splitters = gen.config.test_splitter_list
                for s in test_splitters:
                    if s.is_option:
                        info = f"{s.text}"
                        if s.split_unit:
                            info += f" ({s.split_unit.value}: {s.value_var})"
                        add_row("Test Split", info)

            if gen.datasets:
                # Show detailed summary for each dataset
                for i, dataset in enumerate(gen.datasets):
                    train_count = sum(dataset.train_mask)
                    val_count = sum(dataset.val_mask)
                    test_count = sum(dataset.test_mask)
                    total = len(dataset.train_mask)
                    
                    prefix = f"Dataset {i+1}" if len(gen.datasets) > 1 else "Data"
                    
                    if total > 0:
                        add_row(f"{prefix} Train", f"{train_count} ({train_count/total*100:.1f}%)")
                        add_row(f"{prefix} Val", f"{val_count} ({val_count/total*100:.1f}%)")
                        add_row(f"{prefix} Test", f"{test_count} ({test_count/total*100:.1f}%)")
                    else:
                        add_row(f"{prefix} Status", "Empty")
        else:
            add_row("Splitting", "Not Set")
            
        # 2. Model
        if self.study.model_holder:
            model_name = self.study.model_holder.target_model.__name__
            add_row("Model", model_name)
        else:
            add_row("Model", "Not Set")
            
        # 3. Training Settings
        if self.study.training_option:
            opt = self.study.training_option
            add_row("Epochs", str(opt.epoch))
            add_row("Batch Size", str(opt.bs))
            add_row("LR", str(opt.lr))
            add_row("Device", opt.get_device_name())
        else:
            add_row("Training", "Not Set")

        # Dynamic Height Adjustment
        self.summary_table.resizeRowsToContents()
        total_height = 0
        # Calculate total height of all rows
        for i in range(self.summary_table.rowCount()):
            total_height += self.summary_table.rowHeight(i)
        
        # Add buffer for borders (header is hidden)
        # If total_height is 0 (empty), set a minimum
        # Cap at 500 to prevent layout shift
        target_height = min(max(total_height + 5, 20), 500)
        self.summary_table.setFixedHeight(target_height)

    def split_data(self):
        if not self.study.loaded_data_list:
            QMessageBox.warning(self, "No Data", "Please load and preprocess data first.")
            return
        
        # Validate epoch_data exists
        if self.study.epoch_data is None:
            QMessageBox.warning(
                self, 
                "No Epoched Data", 
                "Please perform epoching in the Preprocess panel first.\n\n"
                "Dataset splitting requires epoched data to generate training, validation, and test sets."
            )
            return
            
        # Fix: Pass self.study.epoch_data as the second argument
        win = DataSplittingSettingWindow(self, self.study.epoch_data)
        if win.exec():
            generator = win.get_result()
            if generator:
                generator.apply(self.study)
            self.update_summary() # Refresh summary
            QMessageBox.information(self, "Success", "Data splitting configuration saved.")

    def select_model(self):
        win = ModelSelectionWindow(self)
        if win.exec():
            self.study.set_model_holder(win.get_result())
            self.update_summary() # Refresh summary
            # ModelHolder doesn't have model_name, use get_model_desc_str() or target_model.__name__
            model_name = self.study.model_holder.target_model.__name__
            QMessageBox.information(self, "Success", f"Model selected: {model_name}")

    def training_setting(self):
        win = TrainingSettingWindow(self)
        if win.exec():
            self.study.set_training_option(win.get_result())
            self.update_summary() # Refresh summary
            QMessageBox.information(self, "Success", "Training settings saved.")

    def start_training(self):
        # Auto-generate plan if needed or just always regenerate to be safe with current settings
        try:
            # Use append=True to add to existing history instead of clearing it
            self.study.generate_plan(force_update=True, append=True)
            self.log_text.append("New training plan added to queue.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to generate plan: {e}")
            return

        if not self.study.trainer or not self.study.trainer.get_training_plan_holders():
            QMessageBox.warning(self, "No Plan", "Failed to generate training plan.")
            return
            
        # Check if dataset is empty or invalid
        # We only check the newly added plan (last one)
        holders = self.study.trainer.get_training_plan_holders()
        new_holder = holders[-1]
        dataset = new_holder.get_dataset()
        if dataset.get_train_len() == 0:
            QMessageBox.critical(
                self, 
                "Training Error", 
                f"Dataset '{dataset.get_name()}' has 0 training samples.\n"
                "Please check your Data Splitting settings or ensure you have enough data."
            )
            # Remove the invalid plan
            holders.pop()
            return
            
        self.training_completed_shown = False  # Reset flag for new training
        
        # Disable buttons
        # self.btn_start.setEnabled(False) # Allow clicking start again to queue
        self.btn_stop.setEnabled(True)
        
        # Start Training directly via Trainer
        try:
            if not self.study.trainer.is_running():
                self.study.trainer.run(interact=True)
                self.timer.start(100) # Start polling
            else:
                self.log_text.append("Training already running. New plan added to queue.")
        except Exception as e:
             QMessageBox.critical(self, "Error", f"Failed to start training: {e}")
             self.training_finished()

    def stop_training(self):
        if self.study.trainer.is_running():
            self.study.trainer.set_interrupt() 

    def clear_history(self):
        """Clear the training history."""
        if self.study.trainer and self.study.trainer.is_running():
            QMessageBox.warning(self, "Warning", "Cannot clear history while training is running.")
            return
            
        if self.study.trainer:
            self.study.trainer.clear_history()
            
        self.history_table.setRowCount(0)
        self.row_map.clear()
        self.tab_acc.clear()
        self.tab_loss.clear()
        # self.tab_summary.clear() # Removed
        self.log_text.clear()
        self.log_text.append("History cleared.")

    def update_loop(self):
        # Poll trainer status
        trainer = self.study.trainer
        
        # Check if finished
        if not trainer.is_running():
            self.timer.stop()
            self.training_finished()
        
        # Update Plots/Progress
        holders = trainer.get_training_plan_holders()
        
        # Flatten the list of all runs
        target_rows = []
        for i, plan in enumerate(holders):
            group_name = f"Group {i+1}"
            model_name = plan.model_holder.target_model.__name__
            
            is_plan_active = False
            if trainer.is_running() and trainer.current_idx == i:
                is_plan_active = True
                
            runs = plan.get_plans()
            for r_idx, record in enumerate(runs):
                target_rows.append({
                    'plan': plan,
                    'record': record,
                    'group': group_name,
                    'run_name': f"{r_idx + 1}", # 1-based index
                    'model': model_name,
                    'is_plan_active': is_plan_active
                })
                
        # If row count mismatch, adjust
        if self.history_table.rowCount() != len(target_rows):
            self.history_table.setRowCount(len(target_rows))
            
        # Update content
        for row_idx, data in enumerate(target_rows):
            plan = data['plan']
            record = data['record']
            group_name = data['group']
            run_name = data['run_name']
            model_name = data['model']
            is_plan_active = data['is_plan_active']
            
            # Store mapping
            self.row_map[row_idx] = (plan, record)
            
            # Determine status
            epoch = record.get_epoch()
            max_epochs = plan.option.epoch
            
            is_active = False
            if record.is_finished():
                status = "Done"
            elif is_plan_active and plan.get_training_repeat() == record.repeat:
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
            time_str = ""
            if is_active:
                # Show current time or elapsed? User asked for duration/end time?
                # "training history 的 time 那欄還是空的" -> usually implies duration or timestamp
                # Let's show current time for active, and maybe duration for finished?
                # For now, let's show Start Time or Duration if available.
                # Since record doesn't track start/end time explicitly in this snippet,
                # we can use current time for running.
                time_str = datetime.datetime.now().strftime("%H:%M:%S")
            elif record.is_finished():
                 # If we had start/end time, we could show duration.
                 # For now, let's show "Done" or leave it empty if no data.
                 # But user said "Time column is empty".
                 # Let's try to show something meaningful.
                 # Maybe we can add a timestamp to the record in backend?
                 # Or just show current time when it finished?
                 # Without backend changes, we can't show true duration.
                 # But we can show "N/A" or similar.
                 # However, let's check if record has any time info.
                 # It seems not.
                 # Let's just show current time for active, and maybe "-" for others for now,
                 # or implement a simple duration tracker in the panel if possible?
                 # No, panel is recreated.
                 # Let's stick to current time for active.
                 pass
            
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
                    self.tab_acc.clear()
                    self.tab_loss.clear()
                    # self.tab_summary.update_plot(plan) # Removed
                
                current_plot_epoch = 0
                if self.tab_acc.epochs:
                    current_plot_epoch = self.tab_acc.epochs[-1]
                
                if is_active and epoch > current_plot_epoch:
                     self.tab_acc.update_plot(epoch, train_acc, val_acc)
                     self.tab_loss.update_plot(epoch, train_loss, val_loss)
                     # self.tab_summary.update_plot(plan) # Removed
                     
                     # Log
                     timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                     log_msg = (
                        f"[{timestamp}] {group_name} {record.get_name()} Epoch {epoch}: "
                        f"Loss={train_loss:.4f}, Acc={train_acc:.2f}%, "
                        f"Val Loss={val_loss_str}, Val Acc={val_acc_str}"
                     )
                     self.log_text.append(log_msg)

    def on_history_selection_changed(self):
        """Handle row selection to update plots."""
        selected_items = self.history_table.selectedItems()
        if not selected_items:
            return
            
        row = selected_items[0].row()
        if row in self.row_map:
            plan, record = self.row_map[row]
            
            # Update Summary (Removed)
            # self.tab_summary.update_plot(plan)
            
            # Update Current Run Plots (Replay history)
            self.current_plotting_record = record
            self.tab_acc.clear()
            self.tab_loss.clear()
            
            # Replay
            train_accs = record.train['accuracy']
            val_accs = record.val['accuracy']
            train_losses = record.train['loss']
            val_losses = record.val['loss']
            
            # We assume lengths match roughly
            for i in range(len(train_accs)):
                ep = i + 1
                t_acc = train_accs[i]
                v_acc = val_accs[i] if i < len(val_accs) else 0
                t_loss = train_losses[i]
                v_loss = val_losses[i] if i < len(val_losses) else 0
                
                self.tab_acc.update_plot(ep, t_acc, v_acc)
                self.tab_loss.update_plot(ep, t_loss, v_loss)

    def training_finished(self):
        # self.btn_start.setEnabled(True) # Always enabled now
        self.btn_stop.setEnabled(False)
        if self.timer.isActive():
            self.timer.stop()
        
        # Only show message once
        if not self.training_completed_shown:
            self.training_completed_shown = True
            QMessageBox.information(self, "Done", "All training jobs finished.")
