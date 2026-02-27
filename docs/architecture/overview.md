# Architecture Overview

XBrainLab follows a layered architecture:

```
┌─────────────────────────────────────────┐
│              UI Layer (PyQt6)           │
│  Panels → Dialogs → Controllers        │
├─────────────────────────────────────────┤
│           AI Agent Layer                │
│  AgentController → Tools → Verifier    │
├─────────────────────────────────────────┤
│          Backend Layer                  │
│  Study → DataManager + TrainingManager  │
│  → Trainer → TrainingPlanHolder         │
└─────────────────────────────────────────┘
```

## Key Components

### Study (Facade)
Central state container delegating to `DataManager` and `TrainingManager`.
See [Study API](../api/backend/study.md).

### DataManager
Manages the data lifecycle: loading, preprocessing, epoching, dataset splitting.
See [DataManager API](../api/backend/data_manager.md).

### TrainingManager
Manages training lifecycle: model config, plan generation, execution, cleanup.
See [TrainingManager API](../api/backend/training_manager.md).

### AgentController
LLM-powered agent that interprets user intent and calls tools.
See [Controller API](../api/agent/controller.md).

For detailed architecture documentation, see:

- [Backend Architecture](backend.md)
- [UI Architecture](ui.md)
- [Agent Architecture](agent.md)
