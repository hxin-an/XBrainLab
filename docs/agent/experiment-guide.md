# Agent Experiment Guide

**最後更新**: 2026-02-28

本文件記錄 XBrainLab Agent 系統的完整實驗流程、驗證方法與
執行步驟，方便後續研究者復現與延伸。

---

## 目錄

1. [實驗總覽](#1-實驗總覽)
2. [系統需求](#2-系統需求)
3. [資料管理](#3-資料管理)
4. [實驗一：RAG 檢索品質](#4-實驗一rag-檢索品質)
5. [實驗二：Tool-Call 準確率 (Stage-Aware)](#5-實驗二tool-call-準確率-stage-aware)
6. [實驗三：架構正確性驗證](#6-實驗三架構正確性驗證)
7. [結果解讀](#7-結果解讀)
8. [常見問題](#8-常見問題)

---

## 1. 實驗總覽

Agent 系統的驗證分為三層：

| 實驗 | 測試目標 | 需要 LLM API | 腳本 |
|------|---------|-------------|------|
| RAG 檢索品質 | 語意搜尋能否找到正確的範例 | 否 (CPU) | `rag_experiment.py` |
| Tool-Call 準確率 | LLM 在**階段過濾**下能否選對工具 | 是 | `simple_bench.py` |
| 架構正確性 | Pipeline 階段閘門、多輪執行 | 否 | `validate_architecture.py` |

### 管道架構 (Pipeline Architecture)

```
EMPTY → DATA_LOADED → PREPROCESSED → DATASET_READY ⇄ TRAINED
             (3 tools)   (13 tools)    (14 tools)     (6 tools)    (6 tools)
```

每個階段只對 LLM 暴露該階段的工具。跨階段操作透過
**Multi-mode** 多輪 LLM 呼叫完成（每輪重建 System Prompt）。

### Stage-Aware Benchmark 設計理念

舊版 benchmark 一次顯示全部 19 個工具，不驗證架構的
階段過濾機制。**Stage-Aware** 模式：

- 根據第一個預期工具推斷初始階段
- 同階段的連續工具合併為一個 Round（一次 LLM 呼叫）
- 跨階段時模擬狀態轉換，開啟新 Round 並重建 Prompt
- 完全匹配 Production 的多輪行為

---

## 2. 系統需求

```
Python 3.11+
Poetry (dependency management)
GEMINI_API_KEY in .env (for benchmark)
```

安裝：
```bash
cd XBrainLab
poetry install
```

API Key 設定（在 `.env` 檔案中）：
```
GEMINI_API_KEY=your-key-here
GEMINI_MODEL_NAME=gemini-2.0-flash   # 可選，預設 gemini-2.0-flash
```

---

## 3. 資料管理

詳見 [data-management.md](data-management.md)。

### 資料結構

```
XBrainLab/llm/rag/data/
  gold_set.json     ← MASTER (210 examples: 19 tools x 10 + 20 complex)

scripts/agent/benchmarks/data/
  train.json        ← 60% (126 examples) — 用於 RAG 索引
  test.json         ← 20% (42 examples)  — 用於評估
  val.json          ← 20% (42 examples)  — 用於調參
  manifest.json     ← MD5 校驗碼 + 元資料
```

### 資料流水線

```bash
# 1. 編輯 gold_set.json（主資料集）

# 2. 重新分割
poetry run python scripts/agent/benchmarks/split_dataset.py

# 3. 驗證完整性
poetry run python scripts/agent/benchmarks/validate_gold_set.py

# 4. 執行實驗
```

### 注意事項

- **不要直接編輯 train/test/val.json** — 永遠從 gold_set.json 分割
- **修改 gold_set 後必須重新 split** — `manifest.json` 會檢測過期
- 分割比用 stratified sampling（按 category），seed=42 確保可復現

---

## 4. 實驗一：RAG 檢索品質

### 目的

測試 RAG 系統能否根據使用者查詢找到語意相關的範例。
**不需要 LLM API**，純 CPU 上用 sentence-transformers 執行。

### 執行

```bash
# 預設：test set, top-3
poetry run python scripts/agent/benchmarks/rag_experiment.py

# 自訂設定
poetry run python scripts/agent/benchmarks/rag_experiment.py --eval-set val --k 5
```

### 參數

| 參數 | 預設 | 說明 |
|------|------|------|
| `--eval-set` | test | 評估集：`test` 或 `val` |
| `--k` | 3 | 檢索 top-k 文件數量 |

### 指標

| 指標 | 定義 |
|------|------|
| Tool Recall@k | top-k 結果中是否有相同 tool_name |
| Category Recall@k | top-k 結果中是否有相同 category |
| Exact Match@1 | top-1 結果的 tool_name + category 完全相同 |
| MRR | Mean Reciprocal Rank（第一個正確匹配的倒數排名） |

### 輸出

報告存放於 `output/benchmarks/`：
- `rag_retrieval_TIMESTAMP.md` — Markdown 報告
- `rag_retrieval_TIMESTAMP.json` — 結構化 JSON

### 預期基線

| 指標 | 基線值 |
|------|--------|
| Tool Recall@3 | ≥ 95% |
| MRR | ≥ 0.85 |

---

## 5. 實驗二：Tool-Call 準確率 (Stage-Aware)

### 目的

測試 LLM 在**真實的階段過濾工具集**下，能否根據使用者查詢
選出正確的工具名稱與參數。

### 執行

```bash
# 預設：stage-aware 模式
poetry run python scripts/agent/benchmarks/simple_bench.py \
    --model gemini --dataset test.json --delay 1 --timeout 60

# Legacy 模式（全部 19 工具可見，不驗證架構）
poetry run python scripts/agent/benchmarks/simple_bench.py \
    --model gemini --mode all-visible --delay 1

# 本地模型
poetry run python scripts/agent/benchmarks/simple_bench.py \
    --model qwen --timeout 120
```

### 參數

| 參數 | 預設 | 說明 |
|------|------|------|
| `--model` | (必填) | `gemini`, `qwen`, `gemma`, `phi`, `mistral` |
| `--mode` | `stage-aware` | `stage-aware`: 階段過濾; `all-visible`: 全部 19 工具 |
| `--dataset` | `test.json` | 評估資料集檔名 |
| `--delay` | 0 | API 呼叫間隔（秒），避免限速 |
| `--timeout` | 30 | 單次推理超時（秒） |

### Stage-Aware 評估流程

```
1. 讀取 test case
2. 從第一個預期工具推斷初始 Pipeline Stage
3. 將預期工具序列依 stage 邊界分割為 Rounds
4. 每個 Round：
   a. 設定 assembler 為該 round 的 stage（只顯示對應工具集）
   b. RAG 注入（一次/case，與 production 相同）
   c. LLM 推理 → 解析回應 → 比對預期工具
   d. 模擬工具執行結果加入 conversation history
   e. 模擬狀態轉換到下一 stage
5. 所有 round 通過 → PASS；任一步失敗 → FAIL
```

### 兩種模式的差異

| 面向 | stage-aware | all-visible |
|------|------------|-------------|
| 工具可見性 | 階段過濾 (3–14 tools) | 全部 19 tools |
| 跨階段驗證 | 多輪模擬 + 狀態轉換 | 單次（全部可見） |
| 架構驗證 | ✅ 驗證真實 Pipeline 行為 | ❌ 旁路階段邏輯 |
| LLM 呼叫數 | ~N rounds/case | 1/case |
| 適用場景 | 架構回歸測試 | 快速工具選擇能力評估 |

### 輸出

報告存放於 `output/benchmarks/`：
- `report_{model}_{mode}_TIMESTAMP.md` — Markdown 報告（含失敗分析）
- `data_{model}_{mode}_TIMESTAMP.csv` — 逐筆 CSV（可匯入 Excel）

### 預期基線 (Gemini 2.0 Flash)

| 模式 | 準確率 | LLM Calls |
|------|--------|-----------|
| stage-aware | ≥ 93% | ~43 (42 cases + cross-stage rounds) |
| all-visible | ≥ 93% | 42 |

---

## 6. 實驗三：架構正確性驗證

### 目的

驗證 Pipeline 架構的正確性，不需 LLM API，純靜態分析。

### 執行

```bash
poetry run python scripts/agent/benchmarks/validate_architecture.py
```

### 驗證內容（6 段）

| Section | 驗證項目 |
|---------|---------|
| 1 | Stage → Tool 映射是否指向已註冊工具 |
| 2 | 各階段的工具新增/移除/累計 |
| 3 | 執行時期閘門追蹤（模擬 `_execute_tool_no_loop`） |
| 4 | Prompt 層工具可見性（LLM 在某階段看不到哪些工具） |
| 5 | Multi-mode 多輪執行追蹤（模擬完整 5 步 pipeline） |
| 6 | Benchmark vs Production 差異表 |

### 預期結果

```
FINAL RESULT: 0 issue(s) found
```

如果有任何 issue，表示架構修改破壞了跨階段相容性。

---

## 7. 結果解讀

### 常見失敗類型

| 失敗類型 | 原因 | 改善方向 |
|----------|------|---------|
| Tool Mismatch | LLM 選錯工具 | 改善 system prompt 或增加 RAG 範例 |
| Param Mismatch | 參數值不同 | 可能是合理歧義（如 training_mode） |
| No JSON Output | LLM 回覆純文字 | 檢查 system prompt 的 JSON 格式指引 |
| JSON Parse Error | 格式不完整 | 可能需增加 timeout 或換模型 |

### 如何對比實驗

1. 固定 seed（split_dataset.py seed=42）
2. 使用相同 eval set（預設 test.json）
3. 記錄 model name + mode + timestamp
4. 比較同 mode 下的 accuracy 變化

### 新增工具後的驗證流程

```bash
# 1. 更新 gold_set.json（新增工具的 10 個範例）
# 2. 更新 pipeline_state.py（新增工具到對應 stage）
# 3. 重新分割
poetry run python scripts/agent/benchmarks/split_dataset.py
# 4. 驗證
poetry run python scripts/agent/benchmarks/validate_gold_set.py
poetry run python scripts/agent/benchmarks/validate_architecture.py
# 5. 跑 benchmark
poetry run python scripts/agent/benchmarks/simple_bench.py --model gemini --delay 1
```

---

## 8. 常見問題

### Q: stage-aware 和 all-visible 哪個才是「正確的」benchmark?

**stage-aware** 是正確的架構驗證。它測試的是：「在 production 的
階段過濾環境下，LLM 能否選對工具？」。`all-visible` 只測試工具
選擇能力，不驗證階段邏輯。

### Q: 跨階段的 complex case 怎麼評估？

例如 "Load data and set montage"（EMPTY → DATA_LOADED）：

1. **Round 1**: Stage=EMPTY (3 tools) → LLM 選 `load_data` → 模擬成功
2. **Round 2**: Stage=DATA_LOADED (13 tools) → LLM 從 history 看到
   之前的請求 → 選 `set_montage`

每個 round 都重建 system prompt，與 production multi-mode 行為一致。

### Q: 為什麼 RAG 用 train.json 而不是 gold_set.json?

避免 Data Leakage。如果用完整 gold_set 做 RAG 索引，test set 的
查詢可能直接匹配到自己的範例，導致準確率虛高。

### Q: 如何新增本地模型？

在 `simple_bench.py` 的 `MODEL_CONFIGS` 中新增：

```python
"my_model": {
    "model_name": "org/model-name",
    "inference_mode": "local",
},
```

然後：`poetry run python simple_bench.py --model my_model --timeout 120`

### Q: manifest.json 報告 stale 怎麽辦？

表示 gold_set.json 修改後未重新分割。執行：

```bash
poetry run python scripts/agent/benchmarks/split_dataset.py
poetry run python scripts/agent/benchmarks/validate_gold_set.py
```
