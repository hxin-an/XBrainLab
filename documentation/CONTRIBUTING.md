# 貢獻指南 (Contributing Guide)

歡迎參與 XBrainLab 的開發！請遵循以下規範以確保程式碼品質與專案的一致性。

## 環境設定 (Environment Setup)

我們使用 **Poetry** 進行套件管理，並使用 **Pre-commit** 進行程式碼檢查。

1.  **安裝相依套件**：
    ```bash
    poetry install
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

## 測試 (Testing)

在提交 PR 之前，請確保所有測試皆通過：

```bash
poetry run pytest
```
