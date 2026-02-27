# Agent 架構與評測系統實作計畫

- **狀態**: 持續更新
- **日期**: 2026-02-03（最後更新: 2026-02-27）
- **相關 ADR**: 005, 006, 007, 008

---

## 總覽

本計畫整合 ROADMAP 願景與 ADR 架構決策，建立可執行的開發里程碑。

| 里程碑 | 主題 | 狀態 |
|--------|------|------|
| **M0** | UI 穩定性與重構 | **✅ Done** |
| **M1** | ReAct 核心架構 | **✅ Done** |
| **M2** | Pipeline Stage 狀態管理 | **✅ Done** |
| **M3** | 測試基礎建設 + 多模型 | **✅ Done** |
| M4 | 評測框架 | 🔄 Partial |
| M5 | 消融實驗 | ❌ Not Started |

> **里程碑編號為歷史順序**，實際開發有交錯。M2 在 v0.5.3–v0.5.5 中完成。

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

## ✅ M1：ReAct 核心架構 (Done)

**來源**：ADR-006

### 1.1 工具結果回傳
- [x] Tool Result 加入 messages
- [x] 定義標準格式（success, data, error）

### 1.2 UI 輸入鎖定
- [x] 執行中禁止輸入（`is_processing` flag → 按鈕 ■/➤ 切換）
- [x] 顯示狀態指示器（`status_update` signal → StatusBar）

### 1.3 執行模式
- [x] 目前採用 **Safe Mode**：每批 tool call 成功後停止，等待用戶輸入
- [x] 失敗時自動重試（`_max_tool_failures = 3`）
- ~~[ ] Single/Multi Action 下拉選單~~ → **已取消**：Safe Mode 在實務中已足夠，
  Multi-Action 模式（agent 自動連續執行多步）風險過高，不符合 HITL 設計原則。

### 1.4 迴圈控制
- [x] MAX_ITERATIONS 硬上限（`_max_loop_breaks = 3`）
- [x] 失敗次數計數器（`_max_tool_failures = 3`）
- [x] 重複呼叫偵測（`_recent_tool_calls` deque + `_detect_loop()`）

### 1.5 HITL（Human-in-the-Loop）
- [x] `requires_confirmation` 屬性 → 危險操作前彈出確認
- [x] `_pending_confirmation` 3-tuple 暫存 → 等用戶回應後繼續
- [x] `on_user_confirmed()` 恢復剩餘 commands

### 1.6 Observability
- [x] `AgentMetricsTracker`：Token 計數、Latency、Tool 執行追蹤
- [x] `TurnMetrics` dataclass：per-turn 結構化日誌
- [x] `conversation_id` 關聯多輪對話

---

## ✅ M2：Pipeline Stage 狀態管理 (Done)

**來源**：ADR-005

> ⚠️ **設計變更**：ADR-005 原設計為 `StateManager` 單例類別，實際採用了**無狀態
> 函式 + 配置表**的輕量替代方案（`pipeline_state.py`），避免引入 Singleton 反模式。

### 2.1 Stage 定義
- [x] `PipelineStage` 枚舉（EMPTY → DATA_LOADED → PREPROCESSED → DATASET_READY ⇄ TRAINED）
- [x] `compute_pipeline_stage(study)` — 從 Study 物件即時推導 stage，無需手動 advance
- **檔案**: `XBrainLab/llm/pipeline_state.py`

### 2.2 工具可用性控制（Stage Gate）
- [x] `STAGE_CONFIG` 映射：每個 stage 定義允許的 tool 清單
- [x] `ContextAssembler._get_stage_config()` → 動態過濾 tool definitions
- [x] `LLMController._execute_tool_no_loop()` → 執行前二次檢查 stage 允許

### 2.3 Per-Stage System Prompt
- [x] 每個 stage 有專用 system prompt（指引 Agent 在當前階段該做什麼、不該做什麼）
- [x] 225 個單元測試驗證 stage 計算與配置完整性

### 2.4 清除與回溯
- [x] `clear_dataset` tool 已實作（`RealClearDatasetTool`）→ 清除所有資料回到 EMPTY
- ~~[ ] `reset_preprocessing()`~~ → **已取消**：目前 `clear_dataset` 已足夠，
  細粒度的 undo 需要 Command Pattern 支撐，ROI 不高。

### 2.5 Confidence 估算
- [x] `estimate_confidence()` 基於關鍵字匹配估算 tool call 信心度
- [x] 整合至 `_process_tool_calls()` + `VerificationLayer`

---

## ✅ M3：測試基礎建設 + 多模型支援 (Done)

**來源**：ADR-007 + 混合架構需求

### 3.1 Interactive Debug Mode
- [x] CLI `--tool-debug script.json`
- [x] Enter 執行下一個動作
- [x] `ToolExecutor` + `ToolDebugMode` 完整實作

### 3.2 Debug 腳本
- [x] JSON Schema 定義
- [x] 範例腳本 `scripts/agent/debug/` (all_tools, debug_filter, debug_ui_switch)

### 3.3 Headless UI Testing
- [x] pytest + QtTest 設定
- [x] `create_test_app()` fixture
- [x] 3978 tests passing, ~90% coverage

### 3.4 多模型架構
- [x] `BaseBackend` 抽象介面 (`llm/core/backends/base.py`)
- [x] `LocalBackend`, `OpenAIBackend`, `GeminiBackend` 實作
- [x] `LLMEngine.switch_backend()` 動態切換
- [x] Config sync：`AgentWorker` 每次 generate 前從 `settings.json` 重載

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
- [x] Gold set 50 cases → RAG Few-Shot 範例（不用於評分）

### 4.2 Benchmark 腳本
- [x] `simple_bench.py` 自動評分
- [x] `audit_dataset.py` 品質審計
- [x] 分類準確率報告 + 失敗案例分析

### 4.3 多模型 Benchmark
- [ ] 在 `external_validation_set.json` (175 題) 測試不同模型：
  - Gemma-2B (CPU), Qwen2.5-7B (預設), Phi-3.5-mini, Llama-3.1-8B
  - Gemini-2.0-Flash, Gemini-2.5-Flash (API 免費層)
- [ ] 記錄 Pass Rate、推論時間、VRAM 使用量
- [ ] 建立「模型選擇指南」文件

### 4.4 MLflow / 實驗追蹤
- [ ] Parameters / Metrics / Artifacts 追蹤
- **評估**: MLflow 是否仍為最佳選擇？若實驗規模較小，
  可考慮輕量替代（JSON log + 簡易比較腳本）

### 4.5 CLI 介面
- [ ] `--model` 參數允許指定推論模型
- [ ] `--benchmark` 一鍵啟動評測

---

## M5：消融實驗

**來源**：ADR-008

> **前置條件**：M4.3 多模型 Benchmark 完成後方有意義。

### 5.1 RAG 消融
- [ ] RAG ON/OFF 對比
- [ ] Retrieval Precision (Hit Rate, MRR) 計算
- **檔案**: `benchmarks/rag_ablation.json`

### 5.2 Stage Gate 消融
- [ ] Stage Lock ON/OFF 對比（允許所有 tool vs 限制）
- [ ] 量化 Stage Gate 對錯誤工具呼叫的攔截率

### 5.3 Verification 消融
- [ ] Verification ON/OFF 對比
- [ ] 量化 Validator 攔截的無效參數比例

### 5.4 Memory 消融
- [ ] Happy Path / Confused Path / No Memory
- [ ] Accuracy by Path Type
- **檔案**: `benchmarks/memory_ablation.json`

---

## 依賴關係

```
M0 (UI 穩定) ✅ ──→ M1 (ReAct) ✅ ──→ M2 (Stage Gate) ✅
                                            │
M3 (測試 + 多模型) ✅ ─────────────→ M4 (評測) 🔄 ──→ M5 (消融) ❌
```

---

## 剩餘工作摘要

| 優先級 | 項目 | 里程碑 | 估算 |
|--------|------|--------|------|
| **高** | 多模型 Benchmark（各模型 Pass Rate 實測） | M4.3 | 1-2 天 |
| **高** | CLI `--model` 參數 | M4.5 | 半天 |
| 中 | MLflow 或輕量追蹤整合 | M4.4 | 1 天 |
| 中 | RAG 消融實驗 | M5.1 | 1 天 |
| 中 | Stage Gate / Verification 消融 | M5.2-5.3 | 1 天 |
| 低 | Memory 消融實驗 | M5.4 | 1 天 |

**品質基線**（2026-02-27）：Ruff 0 | 3978 tests | ~90% coverage | Pre-commit ✅
