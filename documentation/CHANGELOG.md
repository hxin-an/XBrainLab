# 變更紀錄 (Changelog)

所有對本專案的重要變更都將記錄於此文件中。



## [0.4.6] - 2026-01-18
### Added
- **Backend Architecture (P2)**:
    - Decoupled `DatasetController` from PyQt6: Now uses a pure Python `Observable` pattern for event notification.
    - Enables "Headless" backend execution (critical for LLM Agent).
    - Moved `LabelImportService` to `backend/services/` to enforce layering.
    - Added `BackendFacade`: A unified, high-level API for the Agent to access backend functions without UI.
    - **Agent Tooling Refactor**:
        - Standardized all `llm/tools/real/*.py` (Dataset, Preprocess, Training) to use `BackendFacade`.
        - Moved complex logic (Enum mapping, Channel Matching, Model Resolution) from Tools to Facade.
        - **Why?**: To ensure the backend logic is reusable ("Headless SDK") and allow lightweight Agent Tools that only handle Interface/HIT logic.
        - **Training Control**: Added `optimizer` (Adam/SGD) and `save_checkpoints_every` support to `RealConfigureTrainingTool`.
- **Architecture Verification (P1)**:
    - Added `tests/architecture_compliance.py` to strictly enforce decoupling rules for Dialogs.
    - Verified all `QDialog` subclasses adhere to `parent.study` prohibition.
### Verified
- **UI/Backend Interaction**: Confirmed legacy files (`import_label.py`, `smart_parser.py`) and Controllers (`TrainingController`) follow Pull/Push patterns.

## [0.4.5] - 2026-01-18
### Added
- **Structured Logging System (P1)**:
    - Implemented central logging configuration (`logger.py`) with rotation.
    - Replaced `print` statements with `logger` calls across UI visualization and backend training modules.
### Fixed
- **Bare Except Clauses (P0)**:
    - Removed bare `except:` usage in `PreprocessController` (and verified global absence).
### Refactored
- **Circular Dependencies**:
    - Extracted `RecordKey` and `TrainRecordKey` from `train.py` to `key.py` to resolve circular imports in `eval.py`.

## [0.4.4] - 2026-01-18
### Fixed
- **Critical Stability Fixes**:
    - `PreprocessController`: 修復裸 `except:` 子句，改為具體異常捕獲並添加日誌記錄，防止系統異常被意外吞噬。
- **Urgent Decoupling (P0)**:
    - `AggregateInfoPanel`: 移除直接訪問 `main_window.study` 的耦合代碼。重構 `update_info` 方法以接受參數，並更新了所有 5 個主要 Panel (`Dataset`, `Preprocess`, `Training`, `Visualization`, `Evaluation`) 以顯式傳遞數據。
- **Documentation**:
    - 更新 `KNOWN_ISSUES.md` 包含詳細的架構耦合分析與代碼質量報告。
    - 重寫 `ROADMAP.md` Track A，確立以穩定性與解耦為核心的開發階段。
### Refactored
- **TrainingPanel Decoupling (P1)**:
    - **TrainingController**: Expanded to serve as the unified data access and logic layer for `TrainingPanel`.
    - **Dialogs**: Refactored `TrainingSettingWindow`, `DatasetSplittingSettingWindow`, and `ModelSelectionWindow` to interact via `TrainingController` instead of accessing `Study` directly.
    - **Cleanup**: Removed all direct `self.study` references from `TrainingPanel` to enforce strict architectural boundaries.
    - **Testing**: Added comprehensive unit tests for `TrainingPanel` and its dialogs, with `TrainingController` fully mocked.

## [0.4.3] - 2026-01-18
### Fixed
- **Type Safety (Mypy)**：全面修復靜態類型檢查錯誤，達成 **0 errors** 目標：
    - **None 安全性**: 為 `QHeaderView`、`QWidget`、`QTreeWidgetItem` 等 Qt 物件訪問添加 None 檢查。
    - **類型推斷**: 修復 `preprocess.py` 中複雜控制流的類型聯合問題 (`str | list[str]`)。
    - **LSP 合規性**: 更新 LLM Tools (`dataset_real.py`) 使參數可選，符合 Liskov 替換原則。
    - **可選導入**: 為 OpenAI/Gemini 等可選依賴添加類型抑制註解。
    - **數組類型**: 解決 `plot_3d_head.py` 中 ndarray 與 list 的類型不匹配。
    - **涵蓋範圍**: 修復 139 個源文件中的所有類型錯誤，包括 UI 組件、LLM 工具、後端邏輯等模組。

## [0.4.2] - 2026-01-17
### Added
- **代碼品質工具**: 引入 `detect-secrets` 來防止機密洩漏，並建立了 `.secrets.baseline` 基準檔案以處理現有的誤報。

### Fixed
- **Linting 錯誤修復**: 全面修復了 `ruff` 和 `pre-commit` 檢測到的代碼風格與質量問題：
    - **RUF043**: 將測試檔案中包含正則表達式 (Regex) 的字串統一改為 Python 原始字串 (`r"..."`)，避免轉義字符問題。
    - **PLC0415**: 將原本位於函數內部的 `import` 語句移至檔案頂部，符合 PEP 8 標準。
    - **RUF059**: 將未使用的解包變數（如 `_events`, `_remaining_mask`）加上底線前綴，明確表示忽略。
    - **B905**: 為 `zip()` 函數添加了 `strict=False` 參數，明確指定在長度不一致時的行為（保持向後兼容）。
- **CI/CD 穩定性**: 解決了所有 `pre-commit` hook 的報錯，確保代碼提交流程暢通。

### Removed
- 移除了開發過程中產生的臨時調試腳本與日誌檔案 (`lint_fix_plan.txt`, `pytest_log.txt`, `debug_list_gemini_models.py` 等)。

## [0.4.1] - 2026-01-17
### Refactored
- **Frontend-Backend Separation**:
    - **Controllers**: Implemented strict separation between UI and Backend logic using `DatasetController`, `TrainingController`, and `VisualizationController`.
    - **Signals**: Refactored `DatasetController` to use `pyqtSignal` for UI synchronization (`dataChanged`, `datasetLocked`, `importFinished`).
    - **Cleanup**: Removed legacy UI code that directly manipulated backend state, significantly reducing coupling.

### Fixed
- **Critical Logic Bugs**:
    - **Infinite Loop**: Fixed a bug in `training_plan.py` where `train_record.epoch` was not incremented, causing training to hang indefinitely.
    - **Loader Registration**: Fixed "Unsupported format" error for `.gdf` files by ensuring `raw_data_loader.py` is imported and loaders are registered on startup.
- **Regressions**:
    - Fixed `AssertionError` in `test_training_plan.py` caused by duplicate `export_checkpoint` calls.
    - Fixed `ImportError` in `ui/widget/__init__.py` (missing newline) and removed unused variables in integration tests.

### Optimized
- **Integration Tests**:
    - **GPU Acceleration**: Updated `test_pipeline_integration.py` to support "Scenario 3" (Real Logic on GPU).
    - **Performance**: Reduced test execution time from ~10m to ~8s by using GPU acceleration and reduced synthetic dataset size (4 trials) while maintaining full logical verification (Data->Model->Saliency).

## [0.4.0] - 2026-01-16
### Added
- **Hybrid Inference Engine**: Support for switching between Local (GPU), OpenAI, and Gemini backends.
- **Gemini API Support**: Native integration using `google-genai` SDK (v2).
- **OpenAI API Support**: Compatible with GPT-4o, DeepSeek, and vLLM.
- **Verification Scripts**: Added `scripts/verify_api_llm.py` and `scripts/verify_gemini_llm.py`.
- **Utility Scripts**: Added `scripts/list_gemini_models.py` to fetch available models.
- **Poe Tasks**: Added `verify-api`, `verify-gemini`, and `list-models` commands.
- **Configuration**: Added `.env` support with `python-dotenv` for secure API key management.

### Changed
- Refactored `LLMEngine` to use a Strategy Pattern (`LocalBackend`, `APIBackend`, `GeminiBackend`).
- Migrated from deprecated `google-generativeai` to `google-genai`.
- Updated `README.md` with new `inference_mode` configuration guide.

## [0.3.9] - 2026-01-16
### Added
- **Human-in-the-loop (HIL) - Montage Verification**:
    - Implemented interactive confirmation flow for `RealSetMontageTool`.
    - **Logic**: If channel matching is imperfect (or completely fails), the tool returns a `Request: Verify Montage...` command.
    - **Controller**: `LLMController` detects this request, emits `request_user_interaction` signal, and pauses the Agent loop.
    - **UI**: `MainWindow` intercepts the signal and opens `PickMontageWindow` (Montage Picker Dialog) with pre-filled mappings.
    - **Collaboration**: User manually corrects/confirms the mapping, and the Agent resumes execution automatically.

## [0.3.8] - 2026-01-16
### Refactored
- **DatasetController**:
    - Inherit `QObject` and emit signals (`dataChanged`, `datasetLocked`, `importFinished`) to enable UI synchronization when backend state changes.
    - Updated `import_files`, `apply_channel_selection`, `reset_preprocess` to emit signals.
### Added
- **RealSetMontageTool**:
    - Implemented channel mapping logic (Exact/Clean match) using `mne_helper.get_montage_positions`.
    - Enables Agent to set montage for visualization.
- **Tests**:
    - Added `test_set_montage` to `tests/unit/llm/tools/real/test_real_tools.py`.
    - Updated preprocessing unit tests to match new backend signatures.

## [0.3.7] - 2026-01-16
### Added
- Implemented "Real" backend interaction tools for LLM Agent:
    - `dataset_real.py`: Load Data, List Files, Clear Dataset, Attach Labels, Get Info, Generate Dataset.
    - `preprocess_real.py`: Bandpass, Notch, Resample, Normalize, Rereference, Channel Selection, Epoching.
    - `training_real.py`: Set Model (EEGNet, SCCNet, etc.), Configure, Start Training.
    - `ui_control_real.py`: UI Switch Panel control.
- Added comprehensive unit tests for all Real Tools in `tests/unit/llm/tools/real/test_real_tools.py`.
- Added manual verification script `scripts/verify_real_tools.py` for end-to-end backend pipeline testing.

## [0.3.6] - 2026-01-16
### Fixed
- **Data Loading**:
    - 修復 `.gdf` 等格式無法讀取的 "Unsupported format" 錯誤。
    - 原因：`DatasetController` 未正確引入 `raw_data_loader` 導致 Loader 未註冊。
- **Tests**:
    - 修復 `TestTrainingPanel` 中因代碼重構導致的過時斷言錯誤 (`AttributeError`, `AssertionError`)。
    - 更新測試邏輯以驗證 `Study` 物件的狀態變更，而非舊的 `Controller` 呼叫。

### Added
- **Documentation**:
    - 新增 `documentation/test/ui/ui_testing_strategy.md`：說明 UI 測試策略 (Mocking, PyQtBot) 與最佳實踐。

## [0.3.5] - 2026-01-16
### Fixed
- **Known Issues Resolved**:
    - **Backend Parameters**: `configure_training` 現在完整支援 `optimizer` (Adam/SGD/AdamW) 與 `save_checkpoints_every` 參數。相關變更同步至 `TrainingOption`、Tool Definitions 與 Mock/Real Implementations。
    - **Memory Leaks**:
        - **VRAM**: `train_one_epoch` 結束後自動呼叫 `torch.cuda.empty_cache()`。
        - **RAM**: `Dataset` 新增索引存取 helper，並在文件與代碼中警告 `get_training_data` 的複製風險。
        - **Agent**: `LLMController` 實作 Sliding Window 機制 (Max 20 Turns)，防止記憶體無限增長。
    - **Silent Failures**: `AggregateInfoPanel` 與 `VisualizationPanel` 移除裸露的 `try...except: pass`，改為 `logger.warning` 記錄異常。
    - **Dependencies**:
        - 移除 `requirements.txt` 中衝突的 `nvidia-*` 套件。
        - 修正 `pyproject.toml` 中的 Torch 版本至 `2.2.0` (與 Changelog 一致)。
        - 重建 `requirements.txt` 以匹配 `pyproject.toml`。

### Added
- **Real Tool Implementation**:
    - 新增 `XBrainLab/llm/tools/real/training_real.py`，實作真正控制後端的訓練工具。
    - 更新 `XBrainLab/llm/tools/__init__.py` 支援 `mode='real'`。

## [0.3.4] - 2026-01-16
### Fixed
- **VTK Dependency Conflict**:
    - 修復 VTK 9.5.2 與 PyVista 不相容問題，降級至 VTK 9.3.1。
    - 解決 `ImportError: cannot import name 'vtkCompositePolyDataMapper2'` 錯誤。
- **Training Panel KeyError**:
    - 修復 `TrainingPanel.update_loop()` 中的字典鍵名不一致問題：
        - `'group'` → `'group_name'`
        - `'model'` → `'model_name'`
        - `'is_plan_active'` → `'is_active'`
    - 修復 `is_current_run` 未定義錯誤。
    - 移除重複的循環代碼和重複的 `set_item(0, group_name)` 調用。

## [0.3.3] - 2026-01-15
### Changed (High Risk)
- **Dependency Architecture Refactoring**:
    - **Break Change**: `pyproject.toml` 依賴結構重組為 `gui`, `llm` 分組。
    - **Impact**: 改變了預設安裝行為。
    - **Risk**: 僅驗證 Headless/Remote 環境 (`--without gui`) 可行性，**GUI 環境 (Full Install) 尚未進行完整的手動回歸測試**。
- **Test Configuration Workaround**:
    - **Critical Change**: 修改 `tests/conftest.py` 強制全域預載入 `torch`。
    - **Reason**: 解決 Headless 環境下 Qt 與 Torch (OpenMP/CUDA) 衝突導致的 SIGABRT (IOT instruction) 崩潰。
    - **Risk**: 此變更影響所有測試執行，掩蓋了潛在的 Import Order 問題，可能與生產環境行為不一致。

### Refactored
- **Prompt Architecture**:
    - **New Component**: 引入 `PromptManager` 類別，取代硬編碼的 Prompt 生成邏輯。
    - **Logic Decoupling**: 將 System Prompt, Tool Definitions, Context Injection, History Sliding Window 邏輯從 `LLMController` 中剝離。
    - **Deleted**: 移除過時的 `prompts.py` 模組。
    - **Coverage**: 新增 `tests/unit/llm/test_prompt_manager.py` 確保邏輯正確性。

### Fixed
- **Testing**:
    - 修復 `test-remote` 指令執行錯誤。
    - **Workaround**: 在 Headless 模式下跳過 `tests/unit/llm/test_controller.py`，因其無法在無顯卡環境下同時初始化 Qt 與 Torch。

## [0.3.2] - 2026-01-15
### Added
- **Controller Pattern**:
    - 新增 `TrainingController`：封裝訓練流程控制與狀態查詢。
    - 新增 `VisualizationController`：集中管理視覺化設定與數據檢索。
- **Cognitive Benchmark**:
    - 新增 `tests/llm_benchmark/gold_set.json`：Agent 認知能力測試黃金集。
    - 新增 `poetry run benchmark-llm`：自動化基準測試腳本。
### Refactored
- **UI Decoupling**:
    - 重構 `TrainingPanel` 與 `VisualizationPanel`，移除對 `Study` 的直接依賴。
    - 移除過舊的 `ui_pyqt` 目錄。


## [0.3.1] - 2026-01-15
### Fixed
- **Resource Management**:
    - 修復 VRAM 洩漏：在 `training_plan.py` 中增加 tensor `.detach().cpu()` 處理。
    - 優化 RAM 使用：實作 `SharedMemoryDataset` 以參照方式存取資料，避免大量 NumPy Copy。
- **Stability**:
    - 消除 `training_plan.py` 中的靜默失敗 (Silent Failures)，增加異常日誌記錄。
    - 鎖定 `torch==2.2.0` 相依版本以確保環境一致性。

## [0.3.0] - 2026-01-15
### Changed
- **Unit Test Infrastructure**:
    - 全面整併測試檔案至 `tests/unit/`，移除源碼目錄中的散落測試。
    - 引入 `scripts/run_tests.py` 與 Poetry 測試指令 (`test-backend`, `test-ui`, `test-llm`, `test-remote`)。
    - 配置 `MPLBACKEND=Agg` 支援 Headless 環境測試。
- **Test Integrity**:
    - 修復 `test_montage_picker_redesign.py` Segmentation Fault 問題 (移除全域 `QApplication`)。
    - 達成 Backend 單元測試 100% 通過率 (2020 個測試案例)。

### Fixed
- **Dependencies**: 補齊 `captum`, `pyvistaqt` 缺失相依套件。

## [0.2.0] - 2026-01-14
### Added
- **Agent Tool System Refactoring**:
    - 採用 `definitions/` (Base), `mock/` (Impl), `real/` (Placeholder) 分層架構。
    - 實作 Factory Pattern (`get_all_tools`) 支援 Mock/Real 模式切換。
- **New Tools**:
    - `SwitchPanelTool`: 支援 `view_mode` 參數，可精確導航至特定 Tab (如 `saliency_map`, `metrics`)。
    - `SetMontageTool`: 新增設定 Montage 功能，補足視覺化前置需求。
- **Documentation**:
    - 更新 `agent_architecture.md` 與 `code_structure.md` 反映新架構。
    - 更新 `tool_definitions.md` 與 `ROADMAP.md`。
- **Tests**:
    - 建立 `llm_test_cases.md`。
    - 實作完整的單元測試 (`test_parser`, `test_prompts`, `test_tools`, `test_controller`)。

### Fixed
- **Agent Memory Leak**: 實作 Sliding Window 機制。
- **UI Blocking**: 將 Agent 執行邏輯移至 `QThread`。
- **Dependency Issues**: 解決 `captum` 缺失導致的測試失敗。

### Added
- 建立文件目錄結構與基礎文件 (`README.md`, `CONTRIBUTING.md` 等)。
