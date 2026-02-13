# XBrainLab Testing Strategy

This directory contains documentation and guidelines for testing XBrainLab.

## Test Directory Structure

The tests are organized into three main categories within the `tests/` directory at the project root:

### 1. Unit Tests (`tests/unit/`)
Tests individual components in isolation, mocking external dependencies.
- **backend/**: Tests for Facade, Controllers, and Data Processing logic.
- **llm/**: Tests for Agent logic, Prompt Manager, and Tools (Mocked).
- **ui/**: Tests for UI components (Panels, Widgets) in isolation.

### 2. Integration Tests (`tests/integration/`)
Tests the interaction between multiple components (e.g., Controller + Backend + UI). These tests ensure that the system works correctly as a whole.

**Categorization:**

| Directory | Purpose | Examples |
|-----------|---------|----------|
| `pipeline/` | **End-to-End Pipelines**<br>Tests complete workflows from data loading to results. | `test_real_data_pipeline.py`<br>`test_e2e_training.py` |
| `ui/` | **UI Interaction**<br>Tests UI updates, panel switching, and widget behavior. | `test_ui_integration.py`<br>`test_refresh_panels.py` |
| `training/` | **Model Training**<br>Tests the training loop, progress reporting, and model saving. | `test_training_integration.py` |
| `io/` | **Input/Output**<br>Tests file loading, saving, and metadata handling. | `test_io_integration.py` |

### 3. Regression Tests (`tests/regression/`)
Tests specifically designed to reproduce and prevent the recurrence of known bugs.
- Each file should be named after the issue it reproduces (e.g., `reproduce_issue_123.py` or `test_epoch_duration_bug.py`).
- These tests serve as a guarantee that fixed bugs stay fixed.

## Running Tests

```bash
# Run all tests
poetry run pytest

# Run only unit tests
poetry run pytest tests/unit

# Run only integration tests
poetry run pytest tests/integration

# Run regression tests
poetry run pytest tests/regression
```
