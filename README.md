# XBrainLab

XBrainLab is a comprehensive platform for EEG analysis and machine learning, featuring a robust backend for data processing and training, and an LLM-powered Agent interface.

## Recent Updates (v0.3.7)

### Real Tool Implementation
We have implemented a full suite of "Real Tools" that allow the LLM Agent to directly interact with the backend to perform end-to-end tasks:

*   **Data Management**: Loading GDF files, attaching labels, splitting datasets.
*   **Preprocessing**: Filtering (Bandpass, Notch), Epoching, and artifacts removal.
*   **Training**: Configuring and running training tasks on EEGNet, SCCNet, etc.
*   **UI Control**: Switching interface panels.

### Verification
To verify the functionality of these tools, we provide a manual verification script:

```bash
poetry run python scripts/verify_real_tools.py
```

This script executes a complete workflow (Load -> Preprocess -> Split -> Train) and saves the execution log to `output/verification_log.txt`.

## Testing
We maintain high test coverage. Partial unit tests for the backend and comprehensive unit tests for the LLM Tools can be run via:

```bash
poetry run pytest tests/unit/llm/tools/real/test_real_tools.py
```
