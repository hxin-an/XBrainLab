# 貢獻指南 (Contributing Guide)

歡迎參與 XBrainLab 的開發！請遵循以下規範以確保程式碼品質與專案的一致性。

## 環境設定 (Environment Setup)

我們使用 **Poetry** 進行套件管理，並使用 **Pre-commit** 進行程式碼檢查。

1.  **安裝相依套件**：
    ```bash
    poetry install --with gui,llm
    ```
2.  **啟動虛擬環境**：
    ```bash
    poetry shell
    ```
3.  **安裝 Pre-commit Hooks**：
    ```bash
    pre-commit install
    ```

## 程式碼風格 (Coding Style)

*   **Python**: 遵循 PEP 8 規範。
    *   使用 `Ruff` 進行 Linting。
    *   使用 `Black` 進行 Formatting。
*   **命名規則**：
    *   變數/函式：`snake_case` (如 `load_data`, `process_signal`)
    *   類別：`PascalCase` (如 `DatasetGenerator`, `MainWindow`)
    *   常數：`UPPER_CASE` (如 `DEFAULT_SAMPLE_RATE`)

## 架構規範 (Architecture Guidelines)

為確保系統的可維護性，請嚴格遵守以下原則：

1.  **前後端分離**：
    *   **UI 層** (`XBrainLab/ui`) 僅負責顯示與使用者互動，**嚴禁**直接呼叫後端核心邏輯或實例化後端類別。
    *   所有 UI 與後端的溝通應透過 **Controller** 或 **Signal/Slot** 機制進行。
2.  **資源管理**：
    *   在處理大型數據 (Tensor/Numpy Array) 時，請注意記憶體釋放 (如使用 `.detach()`, `del`)。
    *   避免在迴圈中進行不必要的數據複製。

## 文件規範 (Documentation Guidelines)

*   **專業語氣**：所有文件應保持專業、客觀。
*   **禁止 Emoji**：文件中**嚴禁使用 Emoji**，以維持專業形象。
*   **語言**：主要使用繁體中文，關鍵術語可保留英文。

## Git 規範 (Git Workflow)

### Commit Message
我們使用 **Conventional Commits** 規範 Commit Message：

*   `feat`: 新增功能 (Features)
*   `fix`: 修復 Bug (Bug Fixes)
*   `docs`: 文件修改 (Documentation)
*   `style`: 格式調整 (不影響程式碼運作)
*   `refactor`: 重構 (既不是新增功能也不是修復 Bug)
*   `test`: 增加或修改測試
*   `chore`: 建置過程或輔助工具的變動

**範例**：
```bash
git commit -m "feat: add ICA artifact removal support"
git commit -m "fix: resolve crash when loading empty dataset"
```

### 分支命名 (Branch Naming)
請使用以下格式命名分支：
`type/description`

*   `feat/add-login-page`
*   `fix/resolve-memory-leak`
*   `docs/update-readme`
*   `refactor/cleanup-backend`

## 測試規範 (Testing Guidelines)

我們致力於建立高覆蓋率且穩定的測試體系。請遵循以下準則：

### 1. 測試結構 (Structure)
所有測試應位於專案根目錄的 `tests/` 資料夾中，並鏡像源碼結構：
*   `XBrainLab/backend/foo.py` -> `tests/backend/test_foo.py`
*   `XBrainLab/ui/bar.py` -> `tests/ui/test_bar.py`

### 2. 命名規則 (Naming)
*   檔案：`test_*.py`
*   函式：`test_功能名稱_預期行為` (如 `test_load_data_invalid_path_raises_error`)

### 3. UI 測試 (UI Testing)
*   使用 `pytest-qt` 的 `qtbot` fixture 進行互動測試。
*   **必須 Mock 後端**：UI 測試不應依賴真實的後端運算 (如訓練模型)，請使用 `unittest.mock` 模擬後端回傳值。
*   範例：
    ```python
    def test_click_train_button(qtbot, mock_study):
        panel = TrainingPanel(mock_study)
        qtbot.addWidget(panel)
        qtbot.mouseClick(panel.btn_start, Qt.LeftButton)
        mock_study.train.assert_called_once()
    ```

### 4. 整合測試 (Integration Testing)
*   針對關鍵流程 (如 "Import -> Preprocess -> Train") 撰寫 E2E 測試。
*   標記為 `@pytest.mark.slow` 以便區分。

### 5. 執行測試 (Running Tests)

1.  **執行所有測試**：
    ```bash
    poetry run pytest
    ```
2.  **執行 UI 測試**：
    ```bash
    poetry run pytest tests/ui
    ```

**提交 PR 前的檢查清單**：
- [ ] 所有測試皆通過 (`pytest`)。
- [ ] 程式碼風格檢查通過 (`pre-commit`)。
- [ ] 若有新功能，已新增對應的測試。
- [ ] 已更新 `CHANGELOG.md`。
