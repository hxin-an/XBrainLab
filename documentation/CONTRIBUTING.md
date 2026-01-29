# 貢獻指南 (Contributing Guide)

歡迎參與 XBrainLab 的開發。本指南旨在協助開發者快速建立標準化的開發環境，即便是初次接觸 Python 專案的研究人員也能順利上手。

## 開發環境建置 (Environment Setup)

為確保研究結果的可重現性與程式碼品質，本專案採用以下現代化工具進行依賴管理與品質控管：

| 工具 | 用途 | 說明 |
| :--- | :--- | :--- |
| **Poetry** | 依賴管理 | 用於解決套件版本衝突，並自動建立隔離的虛擬環境 (Virtual Environment)，確保實驗環境的一致性。 |
| **Pre-commit** | 自動化檢查 | 在提交 (Commit) 前自動執行品質檢查腳本，防止格式錯誤或明顯的 Bug 進入版本庫。 |
| **Ruff** | 靜態分析 | 高效的 Python Linter，用於檢查程式碼風格 (PEP 8) 與潛在錯誤。 |
| **Result** | 自動化任務 | 專案專用的任務執行器，簡化測試與驗證指令。 |

### 1. 環境安裝 (Installation)

1.  **安裝 Poetry**:
    請參考 [Poetry 官方文件](https://python-poetry.org/docs/#installation) 進行安裝。

2.  **複製專案 (Clone Repository)**:
    ```bash
    git clone https://github.com/your-repo/XBrainLab.git
    cd XBrainLab
    ```

3.  **安裝依賴 (Install Dependencies)**:
    此指令將讀取 `pyproject.toml` 並安裝所有必要的開發與執行套件。
    ```bash
    poetry install --with gui,llm,dev,test
    ```

4.  **啟動虛擬環境 (Activate Shell)**:
    進入專案專屬的隔離環境 (注意：Poetry 2.0+ 已移除 `shell` 指令，請使用以下方式)：
    ```bash
    source $(poetry env info --path)/bin/activate
    ```

5.  **設定 Git Hooks**:
    安裝 Pre-commit hook，確保每次提交都符合專案規範。
    ```bash
    pre-commit install
    ```

### 2. 常用開發指令 (Common Commands)

本專案使用 `poe` 封裝常用的開發指令，定義於 `pyproject.toml` 中：

*   **執行完整檢查** (提交前建議執行):
    ```bash
    poe check
    ```
*   **自動修復程式碼風格**:
    ```bash
    poe lint-fix
    ```
*   **執行 Agent 驗證測試**:
    ```bash
    poe benchmark-llm
    ```

---

## 程式碼規範 (Coding Standards)

為維護專案的長期可維護性，請嚴格遵守以下規範：

### 1. Python 風格
本專案全面自動化程式碼風格檢查，請確保您的開發環境已設定好以下工具：
*   **Linting/Formatting**: 統一使用 **Ruff** 進行代碼排版與靜態檢查。若 `poe check` 報告錯誤，可嘗試 `poe lint-fix` 進行自動修復。
*   **Type Hinting (型別提示)**:
    *   為提升代碼的可讀性與安全性，**強烈建議**在函式簽名中使用型別提示 (Type Hints)。
    *   *Correct*: `def add(a: int, b: int) -> int:`
    *   *Incorrect*: `def add(a, b):`

### 2. Agent 開發規範 (Agent Development)
若您參與 AI Agent 模組的開發，請注意以下事項，這直接影響 LLM 的推論能力：
*   **Docstring 即 Prompt**:
    *   Agent 依賴函式的文檔字串 (Docstring) 來理解工具用途與參數格式。
    *   Docstring 必須精確、清晰，並符合 Google Style 或 NumPy Style。
*   **維護黃金測試集 (Gold Set)**:
    *   引入新工具時，**必須**同步更新 `XBrainLab/llm/rag/data/gold_set.json`，提供 Few-Shot Examples，以確保模型能正確學習工具的使用情境。

---
### 3. 架構原則
*   **BackendFacade**: Agent 只能透過 `BackendFacade` 呼叫核心功能，禁止直接操作 Controller。
*   **Observer Pattern**: UI 元件應訂閱 Backend 的訊號 (Signal)，而非主動輪詢 (Polling)。

## Git 規範 (Workflow)

我們嚴格執行 **Conventional Commits**。建議安裝 `commitizen`：

```bash
# 推薦使用 cz 來 commit，它會協助你格式化訊息
cz commit
```

*   `feat`: 新增功能
*   `fix`: 修復 Bug
*   `refactor`: 重構 (無功能變動)
*   `docs`: 文件更新
*   `test`: 測試相關
*   `chore`: 建置/工具變動

## 提交檢查清單 (PR Checklist)
- [ ] 執行過 `poe check` 且全數通過 (包含 Coverage > 50%)。
- [ ] 若修改了 Agent Tool，已更新 `gold_set.json`。
- [ ] 若有架構更動，已通過 `tests/architecture_compliance.py`。
- [ ] Commit Message 符合規範。
