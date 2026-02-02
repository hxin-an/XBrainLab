# UI Architecture 2.0

## Overview
The UI Architecture 2.0 is a comprehensive redesign of the XBrainLab user interface layer, aiming to solve issues of tight coupling, inconsistent state management, and monolithic components.

## Core Principles

### 1. Layered Architecture
Strict separation of concerns:
- **UI Layer (`ui/`)**: Pure presentation. No business logic. No direct backend access.
- **Controller Layer (`backend/controller/`)**: Intermediary. Handles data retrieval, formatting, and user actions.
- **Backend Layer (`backend/`)**: Core application logic and data state (`Study` object).

### 2. Event-Driven Updates (Observer Pattern)
- UI components never manually call `refresh()` on other components.
- UI components subscribe to `Controller` events.
- When backend state changes, `Controller` emits signals.
- `ObserverBridge` translates backend events to Qt signals for thread-safe UI updates.

### 3. Component Composition
- Large panels are broken down into smaller, focused sub-components.
- **BasePanel**: Abstract base class enforcing standard initialization and cleanup.
- **BaseDialog**: Abstract base class for all dialogs.

### 4. Dependency Injection
- Components receive their dependencies (Controllers, Data) explicitly.
- No global state access (e.g., removing `self.main_window.study`).

## Directory Structure

```
ui/
├── __init__.py
├── main_window.py          # Orchestration only (~200 lines target)
├── app.py                  # Application entry point
│
├── core/                   # Core UI infrastructure
│   ├── base_panel.py       # Abstract base for all panels
│   ├── base_dialog.py      # Abstract base for all dialogs
│   ├── observer_bridge.py  # Qt-Backend bridge
│   └── event_bus.py        # Application-wide events
│
├── styles/                 # Centralized theming
│   ├── theme.py            # Color constants
│   ├── stylesheets.py      # Reusable CSS classes
│   └── icons.py            # Icon management
│
├── components/             # Reusable widgets (no business logic)
│   ├── info_panel.py       # Aggregate information display
│   ├── metric_tab.py       # Training metrics chart
│   ├── data_table.py       # Generic data table
│   ├── toolbar.py          # Action button toolbar
│   ├── plot_canvas.py      # Matplotlib integration
│   └── cards/
│       └── card.py
│
├── dialogs/                # All dialogs (one class per file)
│   ├── preprocess/
│   │   ├── filtering_dialog.py
│   │   ├── resampling_dialog.py
│   │   ├── rereference_dialog.py
│   │   ├── normalize_dialog.py
│   │   └── epoching_dialog.py
│   ├── dataset/
│   │   ├── import_label_dialog.py
│   │   ├── event_filter_dialog.py
│   │   ├── label_mapping_dialog.py
│   │   ├── smart_parser_dialog.py
│   │   ├── channel_selection_dialog.py
│   │   └── data_splitting_dialog.py
│   ├── training/
│   │   ├── model_selection_dialog.py
│   │   ├── training_setting_dialog.py
│   │   ├── optimizer_setting_dialog.py
│   │   └── device_setting_dialog.py
│   └── visualization/
│       ├── montage_picker_dialog.py
│       ├── saliency_setting_dialog.py
│       └── export_saliency_dialog.py
│
├── panels/                 # Main application panels
│   ├── dataset/
│   │   ├── panel.py        # Panel composition (~150 lines)
│   │   ├── file_list.py    # File list widget
│   │   └── actions.py      # Action handlers
│   ├── preprocess/
│   │   ├── panel.py
│   │   ├── preview_plot.py
│   │   └── operation_toolbar.py
│   ├── training/
│   │   ├── panel.py
│   │   ├── history_table.py
│   │   ├── sidebar.py
│   │   ├── components.py
│   │   └── progress_display.py
│   ├── evaluation/
│   │   ├── panel.py
│   │   ├── confusion_matrix.py
│   │   ├── metrics_table.py
│   │   └── metrics_chart.py
│   └── visualization/
│       ├── panel.py
│       ├── saliency_views/
│       │   ├── map_view.py
│       │   ├── topomap_view.py
│       │   ├── spectrogram_view.py
│       │   └── plot_3d_view.py
│       └── control_sidebar.py
│
└── chat/                   # AI assistant
    ├── panel.py
    ├── message_bubble.py
    └── styles.py
```

## Migration Status
- [x] **Phase 1: Foundation**: Core infrastructure, styles, and decoupling completed.
- [x] **Phase 2: Dialog Reorganization**: All dialogs moved to `ui/dialogs/` and split into domain-specific folders.
- [x] **Phase 3: Panel Decomposition (Training)**: `TrainingPanel` refactored into `Sidebar`, `HistoryTable`, and `MetricTab`.
- [ ] **Phase 3: Panel Decomposition (Other)**: Preprocess, Dataset, Visualization panels pending.

## Implementation Details

### The Observer Bridge
The `QtObserverBridge` connects Python-native backend observables to PyQt UI slots.

```python
# In Component
self.bridge = QtObserverBridge(controller, "data_changed", self)
self.bridge.connect_to(self.update_view)
```

### Centralized Styling
Styles are defined in `ui/styles/stylesheets.py` to ensure consistency.

```python
self.setStyleSheet(Stylesheets.BTN_PRIMARY)
```
