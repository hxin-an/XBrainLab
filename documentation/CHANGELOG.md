# 變更紀錄 (Changelog)

所有對本專案的重要變更都將記錄於此文件中。

## [Unreleased]

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

