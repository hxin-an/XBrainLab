# Agent 架構與評測系統實作計畫

- **狀態**: 規劃中
- **日期**: 2026-02-03
- **相關 ADR**: 005, 006, 007, 008

---

## 總覽

本計畫整合 ROADMAP 願景與 ADR 架構決策，建立可執行的開發里程碑。

**最新調整 (2026-02-04)**：基於測試優先策略，M3 提前執行。

| 里程碑 | 主題 | 優先級 | 預估 | 狀態 |
|--------|------|--------|------|------|
| **M0** | **UI 穩定性與重構** | **Done** | **Completed** | **✅** |
| **M3** | **測試基礎建設 + 多模型** | **P1** | **3-5 天** | **▶️ In Progress** |
| M1 | ReAct 核心架構 | P2 | 3-5 天 | Pending M3 |
| M2 | 統一狀態管理 | P2 | 3-5 天 | Pending M1 |
| M4 | 評測框架 (MLflow) | P3 | 3-5 天 | |
| M5 | 消融實驗 | P3 | 5-7 天 | |

---

## ✅ M0：UI 穩定性與重構 (Completed)

**來源**：ROADMAP Track A

### 0.1 ChatPanel 重構
- [ ] 將 `MessageBubble` 邏輯抽離
- [ ] Logic Decoupling：UI 僅負責渲染
- **檔案**: `XBrainLab/ui/panels/chat/`

### 0.2 程式碼規範
- [ ] 全面補齊 Type Hints（可分批處理）
- [ ] 統一 Exception 處理

### 0.3 New Conversation 功能
- [x] 一鍵清除 Context Window
- [x] 重置 Agent 狀態

> **完成確認**：UI Refinements (Bubble, Buttons, Float) 已於 2026-02-04 驗收。

---

## M1：ReAct 核心架構

**來源**：ADR-006

### 1.1 工具結果回傳
- [ ] Tool Result 加入 messages
- [ ] 定義標準格式（success, data, error）
- **檔案**: `XBrainLab/backend/agent/react_agent.py`

### 1.2 UI 輸入鎖定
- [ ] 執行中禁止輸入
- [ ] 顯示狀態指示器
- **檔案**: `XBrainLab/ui/panels/chat/chat_panel.py`

### 1.3 執行模式選擇器
- [ ] Single/Multi Action 下拉選單
- [ ] MAX_SUCCESSFUL_TOOLS（1 或 5）

### 1.4 迴圈控制
- [ ] MAX_ITERATIONS = 10 硬上限
- [ ] 成功次數計數器

---

## M2：統一狀態管理

**來源**：ADR-005

### 2.1 StateManager 核心
- [ ] 建立 `StateManager` 單例
- [ ] Stage 枚舉定義
- **檔案**: `XBrainLab/backend/services/state_manager.py`（新建）

### 2.2 工具可用性控制
- [ ] `get_available_tools()` 方法
- [ ] Agent Prompt 動態更新

### 2.3 清除與回溯工具
- [ ] `reset_preprocessing()`
- [ ] `clear_dataset()`

---

## M3：測試基礎建設 + 多模型支援

**來源**：ADR-007 + 混合架構需求

### 3.1 Interactive Debug Mode
- [ ] CLI `--tool-debug script.json`
- [ ] Enter 執行下一個動作
- **檔案**: `run.py`, `XBrainLab/ui/panels/chat/chat_panel.py`

### 3.2 Debug 腳本
- [ ] JSON Schema 定義
- [ ] 範例腳本 `scripts/debug_filter.json`

### 3.3 Headless UI Testing
- [ ] pytest + QtTest 設定
- [ ] `create_test_app()` fixture
- **檔案**: `tests/conftest.py`, `tests/test_ui_integration.py`

### 3.4 多模型架構
- [ ] 定義 `LLMProvider` 抽象介面
- [ ] 實作 GPT-4, Claude, Gemini 適配器
- [ ] CLI `--model gpt-4` / `--model claude-3`
- [ ] 評測時可指定模型
- **檔案**: `XBrainLab/backend/agent/providers/`（新建）

### 3.5 真實工具鏈修復（依賴 3.1-3.3）
- [ ] 使用 Interactive Debug 逐步驗證工具
- [ ] Saliency Tool 可呼叫執行
- [ ] 複雜參數正確傳遞
- [ ] 撰寫 Headless Test 防止回歸

---

## M4：評測框架

**來源**：ADR-008

### 4.1 Benchmark Dataset
- [ ] 測試案例 JSON Schema
- [ ] 初始測試集 50+ cases
- **檔案**: `benchmarks/tool_call_v1.json`

### 4.2 ToolCallEvaluator
- [ ] `evaluate()` 方法
- [ ] fuzzy_compare 數值容忍度
- **檔案**: `XBrainLab/eval/evaluator.py`

### 4.3 MLflow 整合
- [ ] Parameters / Metrics / Artifacts 追蹤
- **檔案**: `XBrainLab/eval/mlflow_tracker.py`

### 4.4 CLI 介面
- [ ] `python -m xbrainlab.eval --model gpt-4`
- **檔案**: `XBrainLab/eval/__main__.py`

---

## M5：消融實驗

**來源**：ADR-008

### 5.1 RAG 消融
- [ ] RAG ON/OFF 測試集
- [ ] Retrieval Precision 計算
- **檔案**: `benchmarks/rag_ablation.json`

### 5.2 Memory 消融
- [ ] Happy Path / Confused Path / No Memory
- [ ] Accuracy by Path Type
- **檔案**: `benchmarks/memory_ablation.json`

### 5.3 其他組件（待設計）
- Stage Lock 效果
- Verification 攔截率
- Tool Definition 品質

---

## 依賴關係

## 依賴關係

```
M0 (UI 穩定) ✅ ─┐
                 ├──→ M3 (測試 + 多模型) ▶️ ──→ M1 (ReAct) ──→ M2 (狀態) ──→ M4 (評測)
                 │
                 └──→ (Headless Testing 保障 M1/M2 品質)
```

---

## 時程總計

| 階段 | 里程碑 | 預估 |
|------|--------|------|
| Phase 1 | M0 + M1 + M2 | 2 週 |
| Phase 2 | M3 + M4 | 2 週 |
| Phase 3 | M5 | 1 週 |

**總計 Stage 1 完成**：約 5 週
