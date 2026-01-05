from PyQt6.QtWidgets import QGroupBox, QGridLayout, QLabel, QWidget, QVBoxLayout, QSizePolicy
from PyQt6.QtCore import Qt
from XBrainLab.backend.load_data import DataType

class AggregateInfoPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Aggregate Information", parent)
        self.main_window = None
        if parent and hasattr(parent, 'study'):
            self.main_window = parent
             
        self.init_ui()

    def init_ui(self):
        # Use VBox with Form or Grid, aligned to top
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        info_layout = QGridLayout()
        info_layout.setVerticalSpacing(5) # Tighter spacing
        
        self.labels = {}
        keys = [
            "Type", "Total Files", "Subjects", "Sessions", "Total Epochs", "Total Events",
            "Channel", "Sample rate", "tmin (sec)", "duration (sec)", 
            "Highpass", "Lowpass", "Classes"
        ]
        
        for i, key in enumerate(keys):
            info_layout.addWidget(QLabel(key), i, 0)
            val_label = QLabel("-")
            val_label.setAlignment(Qt.AlignmentFlag.AlignRight) # Align values right
            info_layout.addWidget(val_label, i, 1)
            self.labels[key] = val_label

        main_layout.addLayout(info_layout)
        self.setFixedWidth(250) # Fixed width for the dock content
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum) # Don't expand vertically

    def set_main_window(self, main_window):
        self.main_window = main_window
        self.update_info()

    def update_info(self):
        if not self.main_window or not hasattr(self.main_window, 'study'):
            return

        # Determine which list to use: Preprocessed if available, else Loaded
        # Actually, user wants to see current state.
        # If we are in Preprocess panel, we might want to see preprocessed data stats.
        # But usually Aggregate Info shows the "Current Data" stats.
        
        study = self.main_window.study
        
        # Check active tab to decide which list to show
        # Tab 0: Dataset -> loaded_data_list
        # Tab 1: Preprocess -> preprocessed_data_list (if available)
        # Others: Default to preprocessed if available
        
        use_loaded = True
        if hasattr(self.main_window, 'stack'):
            current_index = self.main_window.stack.currentIndex()
            if current_index != 0 and study.preprocessed_data_list:
                use_loaded = False
        
        data_list = study.loaded_data_list if use_loaded else study.preprocessed_data_list
        
        if not data_list:
            self.reset_labels()
            return

        subject_set = set()
        session_set = set()
        classes_set = set()

        total_epochs = 0
        total_events = 0
        
        first_data = data_list[0]
        
        for data in data_list:
            subject_set.add(data.get_subject_name())
            session_set.add(data.get_session_name())
            try:
                _, event_id = data.get_event_list()
                if event_id:
                    classes_set.update(event_id)
            except:
                pass

            total_epochs += data.get_epochs_length()
            
            # Calculate Total Events
            try:
                if data.is_raw():
                    events, _ = data.get_event_list()
                    if events is not None:
                        total_events += len(events)
                else:
                    # For epochs, total events is same as total epochs usually, 
                    # but let's be consistent with dataset.py logic
                    total_events += data.get_epochs_length()
            except:
                pass
            
        tmin = "None"
        duration = "None"
        
        if not first_data.is_raw():
            tmin = str(first_data.get_tmin())
            try:
                dur_val = int(first_data.get_epoch_duration() * 100 / first_data.get_sfreq()) / 100
                duration = str(dur_val)
            except:
                duration = "?"

        highpass, lowpass = first_data.get_filter_range()
        text_type = DataType.RAW.value if first_data.is_raw() else DataType.EPOCH.value

        self.labels["Type"].setText(str(text_type))
        self.labels["Total Files"].setText(str(len(data_list)))
        self.labels["Subjects"].setText(str(len(subject_set)))
        self.labels["Sessions"].setText(str(len(session_set)))
        self.labels["Total Epochs"].setText(str(total_epochs))
        self.labels["Total Events"].setText(str(total_events))
        self.labels["Channel"].setText(str(first_data.get_nchan()))
        self.labels["Sample rate"].setText(str(first_data.get_sfreq()))
        self.labels["tmin (sec)"].setText(tmin)
        self.labels["duration (sec)"].setText(duration)
        self.labels["Highpass"].setText(f"{highpass:.2f}")
        self.labels["Lowpass"].setText(f"{lowpass:.2f}")
        self.labels["Classes"].setText(str(len(classes_set)))

    def reset_labels(self):
        for label in self.labels.values():
            label.setText("-")
