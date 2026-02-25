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

若您參與 AI Agent 模組的開發，請遵循以下規範：

#### 2.1 工具開發
- **Docstring 即 Prompt**：Agent 依賴 Docstring 理解工具，必須精確且符合 Google Style。
- **Tool Definition**：參考 `documentation/agent/tool_definitions.md` 格式。
- **BackendFacade**：Agent 只能透過 `BackendFacade` 呼叫功能，禁止直接操作 Controller。

#### 2.2 開發流程

```
1. 定義工具 Docstring
       ↓
2. 新增 Benchmark 測試案例
       ↓
3. 使用 Interactive Debug 驗證
       ↓
4. 撰寫 Headless UI Test
       ↓
5. 執行評測確認準確率
```

#### 2.3 相關文件
- [ADR-006: ReAct 架構](./decisions/ADR-006-agent-react-architecture.md)
- [ADR-007: 測試策略](./decisions/ADR-007-tool-call-testing-strategy.md)
- [ADR-008: 評測框架](./decisions/ADR-008-tool-call-evaluation-framework.md)

---

## 測試驅動開發 (Test-Driven Development)

本專案採用 **TDD** 原則，確保程式碼品質與可維護性。

### 1. TDD 流程

```
Red → Green → Refactor

1. 先寫失敗的測試 (Red)
2. 寫最少程式碼讓測試通過 (Green)
3. 重構程式碼 (Refactor)
4. 重複
```

### 2. 測試類型

| 類型 | 目錄 | 用途 |
|------|------|------|
| **Unit Tests** | `tests/unit/` | 單一函數/類別測試 |
| **Integration Tests** | `tests/integration/` | 模組間整合測試 |
| **Regression Tests** | `tests/regression/` | Bug 回歸測試 |

### 3. 測試指令

```bash
# 執行所有測試
poe test

# 只執行單元測試
pytest tests/unit/

# 執行 UI 整合測試
pytest tests/ui/

# Agent 準確率評測
poe benchmark-llm

# Interactive Debug Mode
python run.py --tool-debug scripts/agent/debug/debug_filter.json
```

### 4. 覆蓋率要求

| 模組 | 最低覆蓋率 |
|------|------------|
| Backend Controllers | 80% |
| Agent Tools | 70% |
| UI Panels | 50% |

### 5. Agent 工具測試

新增或修改 Agent Tool 時，**必須**：

1. **更新 Benchmark Dataset**：
   ```bash
   # 新增測試案例到
   scripts/agent/benchmarks/data/external_validation_set.json
   ```

2. **使用 Debug Mode 驗證**：
   ```bash
   python run.py --tool-debug scripts/your_tool_test.json
   # 按 Enter 逐步執行，肉眼確認 UI 正確
   ```

3. **撰寫 Headless Test**：
   ```python
   # tests/ui/test_your_tool.py
   def test_your_tool_updates_ui(test_app):
       result = test_app.controller.execute_tool("your_tool", {...})
       assert result.success
       assert test_app.panel.expected_state()
   ```

4. **執行評測確認準確率**：
   ```bash
   poe benchmark-llm
   # 確認新工具準確率 > 90%
   ```

---

## Git 規範 (Workflow)

我們嚴格執行 **Conventional Commits**。建議安裝 `commitizen`：

```bash
cz commit
```

| 類型 | 說明 |
|------|------|
| `feat` | 新增功能 |
| `fix` | 修復 Bug |
| `refactor` | 重構 |
| `docs` | 文件更新 |
| `test` | 測試相關 |
| `chore` | 建置/工具變動 |

---

## 提交檢查清單 (PR Checklist)

- [ ] 執行過 `poe check` 且全數通過
- [ ] 新功能有對應的單元測試
- [ ] 若修改了 Agent Tool：
  - [ ] 更新 Benchmark Dataset
  - [ ] 使用 Debug Mode 驗證
  - [ ] 撰寫 Headless UI Test
- [ ] 若有架構更動，已通過 `tests/architecture_compliance.py`
- [ ] Commit Message 符合規範
