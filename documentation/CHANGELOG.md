# 變更紀錄 (Changelog)

所有對本專案的重要變更都將記錄於此文件中。

## [Unreleased]

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

