# XBrainLab UI Architecture

This document describes the architecture of the XBrainLab User Interface, built with PyQt6.

## Overview

The UI follows a modular design where the `MainWindow` acts as the central container, managing navigation between different functional panels. Each panel is a self-contained widget responsible for a specific stage of the EEG analysis workflow.

## Core Components

### MainWindow (`ui_pyqt/main_window.py`)
- **Responsibility**: Application entry point, layout management, navigation, and global services (AI Agent, Logging).
- **Structure**:
    - **Top Bar**: Navigation buttons (Dataset, Preprocess, Training, Evaluation, Visualization) and global actions (AI Assistant, Data Info).
    - **Central Widget**: A `QStackedWidget` that holds the main panels.
    - **Dock Widgets**: Collapsible panels for the AI Assistant (`ChatPanel`) and Data Info (`AggregateInfoPanel`).
- **Key Methods**:
    - `init_panels()`: Initializes and adds all panels to the stack.
    - `switch_page(index)`: Handles navigation logic.

### Panels
Each panel inherits from `QWidget` (or `QFrame`) and implements a specific workflow.

1.  **DatasetPanel** (`ui_pyqt/dashboard_panel/dataset.py`)
    - **Purpose**: Data loading, management, and basic visualization.
    - **Features**: File tree view, channel selection, data info display.

2.  **PreprocessPanel** (`ui_pyqt/dashboard_panel/preprocess.py`)
    - **Purpose**: Signal processing operations.
    - **Features**: Filtering, resampling, epoching, ICA, etc.
    - **Design**: Uses a "History" list to track operations and allows undo/redo (conceptually).

3.  **TrainingPanel** (`ui_pyqt/training/panel.py`)
    - **Purpose**: Model configuration and training.
    - **Features**:
        - **Model Selection**: Choose model architecture and parameters.
        - **Training Configuration**: Set hyperparameters (epochs, batch size, lr).
        - **Data Splitting**: Configure train/val/test splits via `DataSplittingSettingWindow`.
        - **Execution**: Start/Stop training and view real-time metrics (Loss/Accuracy).

4.  **EvaluationPanel** (`ui_pyqt/evaluation/panel.py`)
    - **Purpose**: Model evaluation and result analysis.
    - **Features**: Confusion matrices, classification reports, and performance metrics.

5.  **VisualizationPanel** (`ui_pyqt/visualization/panel.py`)
    - **Purpose**: Advanced data visualization.
    - **Features**: 2D/3D Topomaps, raw signal inspection.

### Dialogs
Reusable dialogs for user input.
- `ImportLabelDialog`: For batch importing labels.
- `EpochingDialog`: For configuring epoching parameters.
- `DataSplittingSettingWindow`: For complex data splitting configuration.

## Testing Strategy

The UI is tested using `pytest-qt`, which allows for headless simulation of user interactions.

### Test Location
Tests are located in `XBrainLab/ui_pyqt/tests/`.

### Key Test Files
- `test_main_window.py`: Tests application launch and navigation.
- `test_training_panel.py`: Tests training configuration, data splitting, and execution logic.
- `test_dialogs.py`: Tests individual dialogs (Epoching, Import Label, etc.).
- `test_panels.py`: General initialization tests for all panels.
- `test_workflow.py`: Integration tests simulating a full user workflow.

## Design Principles
- **Separation of Concerns**: UI logic is separated from business logic (handled by `Study`, `Trainer`, `Preprocessor` classes).
- **Modularity**: Panels are independent and can be developed/tested in isolation.
- **Responsibility**: The UI is responsible for *gathering* user input and *displaying* results, while the backend performs the actual computation.
