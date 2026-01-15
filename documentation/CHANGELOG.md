# 變更紀錄 (Changelog)

所有對本專案的重要變更都將記錄於此文件中。

## [Unreleased]
### Added
- **Data Strategy (OOD Testing)**:
    - **External Validation Set**: 建立 `external_validation_set.json` (原 Senior Benchmark)，包含 175 個未見過的測試案例 (Basic + Multi-step)。
    - **Clean RAG Split**: 確立 `gold_set.json` 作為 RAG 教學資料，`external_validation_set.json` 作為評測資料的防止洩漏策略。
- **Documentation**:
    - 更新 `KNOWN_ISSUES.md` 標註外部驗證集揭露的工具功能缺失 (Optimizer, Checkpoints)。
    - 更新 `ROADMAP.md` 整合 RAG 與 Multi-Agent 規劃。

### Changed
- **Content Cleanup**:
    - 移除臨時轉換腳本 `convert_senior_benchmark.py` 與原始 CSV 檔案。
    - 刪除冗餘的 `rag_knowledge_content_plan.md`，內容合併至 Roadmap。

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

