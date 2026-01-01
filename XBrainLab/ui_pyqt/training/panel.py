from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QGroupBox, 
    QGridLayout, QMessageBox, QFrame, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QTextEdit
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
        
        # 2. Training Summary (Compact, no frame)
        self.summary_text = QLabel("Model: -- | Batch: -- | LR: --")
        self.summary_text.setStyleSheet("""
            QLabel {
                background-color: #1e1e1e;
                color: #999999;
                border-radius: 4px;
                padding: 8px;
                font-family: monospace;
                font-size: 10pt;
            }
        """)
        self.summary_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.summary_text.setFixedHeight(40) # Fixed small height
        layout.addWidget(self.summary_text, stretch=0)
        
    def update_data(self, epochs, values):
        # Update Plot
        self.ax.clear()
        self.ax.plot(epochs, values, marker='o', linestyle='-', color=self.color, label=self.metric_name)
        self.ax.set_title(f"{self.metric_name} vs Epoch")
        self.ax.set_xlabel("Epoch")
        self.ax.set_ylabel(self.metric_name)
        self.ax.grid(True, linestyle='--', alpha=0.6)
        self.ax.legend()
        self.canvas.draw()
        
    def clear(self):
        # Clear plot
        self.ax.clear()
        self.ax.set_title(f"{self.metric_name} vs Epoch")
        self.ax.set_xlabel("Epoch")
        self.ax.set_ylabel(self.metric_name)
        self.ax.grid(True, linestyle='--', alpha=0.3, color='#666666')
        self.canvas.draw()
        self.summary_text.setText("Model: -- | Batch: -- | LR: --")
        
        # Clear history data
        if hasattr(self, 'epochs'): self.epochs = []
        if hasattr(self, 'train_vals'): self.train_vals = []
        if hasattr(self, 'val_vals'): self.val_vals = []

    def update_plot(self, epoch, train_val, val_val):
        # We need to store history to plot lines. 
        # Since this method is called once per epoch with single values, 
        # we need to accumulate them or pass the full history.
        # TrainingPanel passes single values.
        # So MetricTab needs to maintain state or TrainingPanel should pass lists.
        # Let's make MetricTab maintain state for simplicity here, 
        # OR better, TrainingPanel should pass the full list from Trainer.
        # But Trainer might not expose it easily in the update callback.
        # Let's append to internal lists.
        
        if not hasattr(self, 'epochs'): self.epochs = []
        if not hasattr(self, 'train_vals'): self.train_vals = []
        if not hasattr(self, 'val_vals'): self.val_vals = []
        
        self.epochs.append(epoch)
        self.train_vals.append(train_val)
        self.val_vals.append(val_val)
        
        self.ax.clear()
        self.ax.plot(self.epochs, self.train_vals, marker='.', linestyle='-', color=self.color, label=f"Train {self.metric_name}")
        self.ax.plot(self.epochs, self.val_vals, marker='.', linestyle='--', color='#cccccc', label=f"Val {self.metric_name}")
        
        self.ax.set_title(f"{self.metric_name} vs Epoch")
        self.ax.set_xlabel("Epoch")
        self.ax.set_ylabel(self.metric_name)
        self.ax.grid(True, linestyle='--', alpha=0.3, color='#666666')
        self.ax.legend()
        self.canvas.draw()

    def set_summary(self, text):
        self.summary_text.setText(text)

class TrainingPanel(QWidget):
    """
    Panel for managing the training process.
    """
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.study = main_window.study
        
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
        
        # Info Row (Model, Best Acc)
        info_layout = QHBoxLayout()
        self.model_label = QLabel("Model: None")
        self.model_label.setStyleSheet("color: #cccccc; font-weight: bold;")
        info_layout.addWidget(self.model_label)
        
        info_layout.addStretch()
        
        self.acc_label = QLabel("Best Acc: N/A")
        self.acc_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        info_layout.addWidget(self.acc_label)
        
        history_layout.addLayout(info_layout)
        
        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #3e3e42;
                background-color: #2d2d2d;
                border-radius: 8px;
                color: #cccccc;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #007acc;
                border-radius: 7px;
            }
        """)
        history_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #808080; font-size: 11px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        history_layout.addWidget(self.status_label)
        
        # History List
        from PyQt6.QtWidgets import QListWidget
        self.history_list = QListWidget()
        self.history_list.setStyleSheet("""
            QListWidget {
                background-color: #1e1e1e;
                border: 1px solid #333;
                color: #cccccc;
                border-radius: 4px;
            }
            QListWidget::item {
                padding: 4px;
                border-bottom: 1px solid #2d2d2d;
            }
        """)
        history_layout.addWidget(self.history_list)
        
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
        
        # 1. Dynamic Tips (Always visible)
        self.tips_group = QGroupBox("GETTING STARTED")
        # Explicitly set transparent background to avoid black box
        self.tips_group.setStyleSheet("QGroupBox { background-color: transparent; border: none; margin-top: 10px; } QGroupBox::title { color: #808080; }")
        
        tips_layout = QVBoxLayout(self.tips_group)
        tips_layout.setContentsMargins(0, 10, 0, 0)
        tips_label = QLabel(
            "<div style='line-height: 1.2; color: #999999;'>"
            "<div style='margin-bottom: 6px;'><b style='color: #cccccc;'>1. Select Plan</b><br>Choose model & parameters</div>"
            "<div style='margin-bottom: 6px;'><b style='color: #cccccc;'>2. Start Training</b><br>Begin model training</div>"
            "<div><b style='color: #cccccc;'>3. Monitor</b><br>Watch accuracy & loss</div>"
            "</div>"
        )
        tips_label.setWordWrap(True)
        tips_label.setStyleSheet("background-color: transparent; border: none;") # Explicitly transparent
        tips_layout.addWidget(tips_label)
        right_layout.addWidget(self.tips_group)
        
        right_layout.addSpacing(10)
        
        # Group 1: Configuration
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
        
        self.btn_test_setting = QPushButton("Test Only Setting")
        self.btn_test_setting.clicked.connect(self.test_only_setting)
        config_layout.addWidget(self.btn_test_setting)
        
        right_layout.addWidget(config_group)
        right_layout.addSpacing(20) # Add breathing room
        
        # Group 2: Execution (Status removed from here)
        exec_group = QGroupBox("EXECUTION")
        exec_layout = QVBoxLayout(exec_group)
        exec_layout.setContentsMargins(0, 10, 0, 0)
        
        self.btn_gen_plan = QPushButton("Generate Plan")
        self.btn_gen_plan.clicked.connect(self.generate_plan)
        exec_layout.addWidget(self.btn_gen_plan)
        
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
                background-color: #4a1818; 
                color: #ff9999;
                border: 1px solid #802020;
            }
            QPushButton:hover {
                background-color: #602020;
            }
        """)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_training)
        exec_layout.addWidget(self.btn_stop)
        
        right_layout.addWidget(exec_group)
        right_layout.addStretch()
        
        main_layout.addWidget(right_panel, stretch=0)

    # --- Event Handlers (Placeholders) ---
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
            QMessageBox.information(self, "Success", "Data splitting configuration saved.")

    def select_model(self):
        win = ModelSelectionWindow(self)
        if win.exec():
            self.study.set_model_holder(win.get_result())
            # ModelHolder doesn't have model_name, use get_model_desc_str() or target_model.__name__
            model_name = self.study.model_holder.target_model.__name__
            QMessageBox.information(self, "Success", f"Model selected: {model_name}")

    def training_setting(self):
        win = TrainingSettingWindow(self)
        if win.exec():
            self.study.set_training_option(win.get_result())
            QMessageBox.information(self, "Success", "Training settings saved.")

    def test_only_setting(self):
        win = TestOnlySettingWindow(self)
        if win.exec():
            self.study.set_training_option(win.get_result())
            QMessageBox.information(self, "Success", "Test settings saved.")

    def generate_plan(self):
        try:
            self.study.generate_plan()
            QMessageBox.information(self, "Success", "Training plan generated successfully.")
            self.log_text.append("Training plan generated.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to generate plan: {e}")

    def start_training(self):
        if not self.study.trainer or not self.study.trainer.get_training_plan_holders():
            QMessageBox.warning(self, "No Plan", "Please generate a training plan first.")
            return
            
        # Check if dataset is empty or invalid
        holders = self.study.trainer.get_training_plan_holders()
        for holder in holders:
            dataset = holder.get_dataset()
            if dataset.get_train_len() == 0:
                QMessageBox.critical(
                    self, 
                    "Training Error", 
                    f"Dataset '{dataset.get_name()}' has 0 training samples.\n"
                    "Please check your Data Splitting settings or ensure you have enough data."
                )
                return
            
        # Initialize History
        self.history_list.clear()
        model_name = self.study.model_holder.target_model.__name__ if self.study.model_holder else "Unknown"
        self.model_label.setText(f"Model: {model_name}")
        self.acc_label.setText("Best Acc: N/A")
        self.progress_bar.setValue(0)
        self.status_label.setText("Starting...")
        self.training_completed_shown = False  # Reset flag for new training
        
        # Disable buttons
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.btn_gen_plan.setEnabled(False)
        
        # Clear plots
        self.tab_acc.clear()
        self.tab_loss.clear()
        self.log_text.clear()
        
        # Start Training directly via Trainer
        try:
            if not self.study.trainer.is_running():
                self.study.trainer.run(interact=True)
                self.timer.start(100) # Start polling
        except Exception as e:
             QMessageBox.critical(self, "Error", f"Failed to start training: {e}")
             self.training_finished()

    def stop_training(self):
        if self.study.trainer.is_running():
            self.study.trainer.set_interrupt()
            self.status_label.setText("Stopping...")

    def update_loop(self):
        # Poll trainer status
        trainer = self.study.trainer
        
        # Update Log/Status if available
        # Note: Trainer might not expose real-time logs easily unless we redirect stdout or check internal buffer.
        # For now, let's assume we can get the last status.
        self.status_label.setText(trainer.get_progress_text())
        
        # Check if finished
        if not trainer.is_running():
            self.timer.stop()
            self.training_finished()
            return

        # Update Plots/Progress if possible
        # We need access to current plan's metrics.
        # Trainer -> TrainingPlanHolder -> TrainingPlan -> metrics
        # This might be tricky to get in real-time if not exposed.
        # But TrainingManagerWindow did:
        # values = get_table_values(plan) -> plan.get_training_evaluation()
        
        # Let's try to update the first plan's metrics for visualization
        holders = trainer.get_training_plan_holders()
        if holders:
            plan = holders[0] # Visualize first plan
            status = plan.get_training_status()
            epoch = plan.get_training_epoch()
            
            # get_training_evaluation returns: (lr, loss, acc, auc, val_loss, val_acc, val_auc)
            metrics = plan.get_training_evaluation()
            if metrics:
                # Convert all metrics to float to ensure type safety
                lr, loss, acc, auc, val_loss, val_acc, val_auc = metrics
                # Helper to safely convert to float
                def safe_float(val):
                    if val == '-' or val is None:
                        return 0.0
                    try:
                        return float(val)
                    except ValueError:
                        return 0.0

                lr = safe_float(lr)
                loss = safe_float(loss)
                acc = safe_float(acc)
                auc = safe_float(auc)
                val_loss = safe_float(val_loss)
                val_acc = safe_float(val_acc)
                val_auc = safe_float(val_auc)
                
                # Update Plots
                self.tab_acc.update_plot(int(epoch), acc, val_acc)
                self.tab_loss.update_plot(int(epoch), loss, val_loss)
                
                # Update Progress Bar
                max_epochs = 100
                if self.study.training_option:
                    max_epochs = int(self.study.training_option.epoch)
                if max_epochs > 0:
                    self.progress_bar.setValue(int((int(epoch) / max_epochs) * 100))
              # update status
            lr, train_loss, train_acc, train_auc, val_loss, val_acc, val_auc = \
                plan.get_training_evaluation()
            
            # Get best accuracy from plan directly
            best_acc = plan.get_best_performance()
            if best_acc is not None:
                 self.best_acc = best_acc
                 self.acc_label.setText(f"Best Acc: {self.best_acc:.2f}%")

            self.status_label.setText(plan.get_training_status())
            # The progress bar should show percentage, not epoch number directly
            # Assuming plan.get_training_epoch() returns current epoch and max_epochs is available
            if self.study.training_option:
                max_epochs = int(self.study.training_option.epoch)
                if max_epochs > 0:
                    self.progress_bar.setValue(int((plan.get_training_epoch() / max_epochs) * 100))
            else:
                self.progress_bar.setValue(0) # Or some default if option not set
            self.log_text.append(plan.get_epoch_progress_text()) # Assuming this is the intended label for progress text

    def training_finished(self):
        self.status_label.setText("Training Completed")
        self.progress_bar.setValue(100)
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_gen_plan.setEnabled(True)
        if self.timer.isActive():
            self.timer.stop()
        
        # Only show message once
        if not self.training_completed_shown:
            self.training_completed_shown = True
            QMessageBox.information(self, "Done", "Training process finished.")
