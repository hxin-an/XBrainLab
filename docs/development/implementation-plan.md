# Agent 架構與評測系統實作計畫

- **狀態**: 持續更新
- **日期**: 2026-02-03（最後更新: 2026-02-25）
- **相關 ADR**: 005, 006, 007, 008

---

## 總覽

本計畫整合 ROADMAP 願景與 ADR 架構決策，建立可執行的開發里程碑。

| 里程碑 | 主題 | 狀態 |
|--------|------|------|
| **M0** | UI 穩定性與重構 | **✅ Done** |
| **M3** | 測試基礎建設 + 多模型 | **✅ Done** |
| **M1** | ReAct 核心架構 | **✅ Mostly Done** |
| M2 | 統一狀態管理 | ❌ Not Started |
| M4 | 評測框架 (MLflow) | 🔄 Partial |
| M5 | 消融實驗 | ❌ Not Started |

---

## ✅ M0：UI 穩定性與重構 (Completed)

**來源**：ROADMAP Track A

### 0.1 ChatPanel 重構
- [x] 將 `MessageBubble` 邏輯抽離
- [x] Logic Decoupling：UI 僅負責渲染

### 0.2 程式碼規範
- [x] 全面補齊 Type Hints
- [x] 統一 Exception 處理

### 0.3 New Conversation 功能
- [x] 一鍵清除 Context Window
- [x] 重置 Agent 狀態

---

## ✅ M1：ReAct 核心架構 (Mostly Done)

**來源**：ADR-006

### 1.1 工具結果回傳
- [x] Tool Result 加入 messages
- [x] 定義標準格式（success, data, error）

### 1.2 UI 輸入鎖定
- [x] 執行中禁止輸入
- [x] 顯示狀態指示器

### 1.3 執行模式選擇器
- [ ] Single/Multi Action 下拉選單
- [ ] MAX_SUCCESSFUL_TOOLS（1 或 5）

### 1.4 迴圈控制
- [x] MAX_ITERATIONS 硬上限 (`_max_loop_breaks = 3`)
- [x] 失敗次數計數器 (`_max_tool_failures = 3`)

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

## ✅ M3：測試基礎建設 + 多模型支援 (Done)

**來源**：ADR-007 + 混合架構需求

### 3.1 Interactive Debug Mode
- [x] CLI `--tool-debug script.json`
- [x] Enter 執行下一個動作

### 3.2 Debug 腳本
- [x] JSON Schema 定義
- [x] 範例腳本 `scripts/agent/debug/` (all_tools, debug_filter, debug_ui_switch)

### 3.3 Headless UI Testing
- [x] pytest + QtTest 設定
- [x] `create_test_app()` fixture

### 3.4 多模型架構
- [x] 定義 `BaseBackend` 抽象介面
- [x] 實作 LocalBackend, OpenAIBackend, GeminiBackend
- [ ] CLI `--model` 參數選擇

### 3.5 真實工具鏈
- [x] 19/19 Real Tools 已完成
- [x] `verify_real_tools.py` 整合驗證
- [x] `verify_all_tools_headless.py` Headless 驗證

---

## 🔄 M4：評測框架 (Partial)

**來源**：ADR-008

### 4.1 Benchmark Dataset
- [x] 測試案例 JSON Schema
- [x] OOD 測試集 175 cases (`external_validation_set.json`)

### 4.2 Benchmark 腳本
- [x] `simple_bench.py` 自動評分
- [x] `audit_dataset.py` 品質審計

### 4.3 MLflow 整合
- [ ] Parameters / Metrics / Artifacts 追蹤

### 4.4 CLI 介面
- [ ] 統一 CLI entry point

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

```
M0 (UI 穩定) ✅ ──→ M3 (測試 + 多模型) ✅ ──→ M1 (ReAct) ✅
                                                    │
                                               M2 (狀態) ❌ ──→ M4 (評測) 🔄 ──→ M5 (消融) ❌
```

---

## 剩餘工作

| 里程碑 | 待完成項目 |
|--------|-----------|
| M1 | Single/Multi Action 模式選擇器 |
| M2 | StateManager 單例（ADR-005 尚未實作） |
| M4 | MLflow 整合、統一 CLI |
| M5 | RAG / Memory 消融實驗設計 |
