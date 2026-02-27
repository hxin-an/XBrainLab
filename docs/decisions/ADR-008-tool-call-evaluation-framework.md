# ADR-008：Tool Call 準確率評測框架

- **狀態**: 部分實作 (Partially Implemented)
- **日期**: 2026-02-02（更新: 2026-02-25）
- **作者**: XBrainLab 團隊

> **實作狀況**: `simple_bench.py` Benchmark 腳本已實作，`external_validation_set.json` (175 題) 已建立，但 MLflow 尚未整合。

---

## 背景

碩論研究需要一套可重複、有歷史紀錄的 Tool Call 準確率評測系統，以：

1. 量化 Agent 的工具呼叫準確率
2. 比較不同模型/配置的表現
3. 追蹤版本迭代的效能變化
4. 分析各部件的準確率瓶頸

---

## 設計概覽

### 評測流程

```
┌─────────────────────────────────────────────────┐
│  Benchmark Dataset (固定測試集)                 │
│  ┌─────────────────────────────────────────┐   │
│  │ test_001: "幫我套用 0.5-50Hz 濾波"        │   │
│  │ expected: apply_filter(low=0.5, high=50) │   │
│  └─────────────────────────────────────────┘   │
└─────────────┬───────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────┐
│  Agent Under Test                               │
│  (Model: X, Config: Y)                          │
└─────────────┬───────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────┐
│  Evaluator (比對 expected vs actual)            │
└─────────────┬───────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────┐
│  Results Store (歷史紀錄)                       │
│  results/2026-02-02_gpt4_v1.2.json             │
└─────────────────────────────────────────────────┘
```

---

## 1. Benchmark Dataset

### 結構

```json
{
  "version": "1.0",
  "created": "2026-02-02",
  "cases": [
    {
      "id": "filter_basic_001",
      "category": "preprocessing",
      "tool": "apply_filter",
      "difficulty": "easy",
      "input": "幫我套用 0.5 到 50 Hz 的帶通濾波",
      "expected": {
        "tool": "apply_filter",
        "params": {"low": 0.5, "high": 50}
      }
    },
    {
      "id": "epoch_complex_002",
      "category": "preprocessing",
      "tool": "create_epochs",
      "difficulty": "medium",
      "input": "把資料切成 epoch，從事件前 0.2 秒到事件後 0.8 秒",
      "expected": {
        "tool": "create_epochs",
        "params": {"tmin": -0.2, "tmax": 0.8}
      }
    }
  ]
}
```

### 分類維度

| 維度 | 分類 |
|------|------|
| **Category** | preprocessing, training, evaluation, data_loading |
| **Tool** | apply_filter, create_epochs, split_data, ... |
| **Difficulty** | easy, medium, hard |

---

## 2. Evaluator

### 準確率指標

```python
class ToolCallEvaluator:
    def evaluate(self, expected: ToolCall, actual: ToolCall) -> EvalResult:
        return EvalResult(
            tool_match = (expected.tool == actual.tool),
            param_match = self.compare_params(expected.params, actual.params),
            exact_match = (expected == actual)
        )

    def compare_params(self, expected: dict, actual: dict) -> ParamResult:
        """逐一比對參數"""
        results = {}
        for key, exp_val in expected.items():
            act_val = actual.get(key)
            results[key] = self.fuzzy_compare(exp_val, act_val)
        return ParamResult(results)

    def fuzzy_compare(self, expected, actual, tolerance=0.01):
        """數值容忍度比對"""
        if isinstance(expected, (int, float)):
            return abs(expected - actual) < tolerance
        return expected == actual
```

### 指標定義

| 指標 | 定義 |
|------|------|
| **Tool Accuracy** | 正確選擇工具的比例 |
| **Param Accuracy** | 參數完全正確的比例 |
| **Exact Match** | 工具 + 參數都正確的比例 |
| **Partial Match** | 工具正確但參數部分錯誤 |

---

## 3. Results Store

### 儲存結構

```
results/
├── 2026-02-02_gpt4_v1.2.json
├── 2026-02-02_claude3_v1.2.json
├── 2026-02-03_gpt4_v1.3.json
└── summary.csv
```

### 單次結果格式

```json
{
  "run_id": "2026-02-02_gpt4_v1.2",
  "timestamp": "2026-02-02T23:00:00",
  "config": {
    "model": "gpt-4",
    "version": "1.2",
    "temperature": 0.0
  },
  "summary": {
    "total_cases": 100,
    "tool_accuracy": 0.95,
    "param_accuracy": 0.88,
    "exact_match": 0.85
  },
  "by_category": {
    "preprocessing": {"tool_acc": 0.96, "exact_match": 0.87},
    "training": {"tool_acc": 0.90, "exact_match": 0.80}
  },
  "by_tool": {
    "apply_filter": {"accuracy": 0.92, "common_errors": ["low/high 顛倒"]},
    "create_epochs": {"accuracy": 0.85, "common_errors": ["tmin 符號錯誤"]}
  },
  "details": [
    {"case_id": "filter_basic_001", "tool_match": true, "param_match": true},
    {"case_id": "epoch_complex_002", "tool_match": true, "param_match": false}
  ]
}
```

---

## 4. CLI 介面

```bash
# 執行完整評測
python -m xbrainlab.eval --model gpt-4 --output results/

# 只測特定類別
python -m xbrainlab.eval --model gpt-4 --category preprocessing

# 比較兩次結果
python -m xbrainlab.eval compare results/run1.json results/run2.json

# 產生報告
python -m xbrainlab.eval report results/ --output report.html
```

---

## 5. 報告與視覺化

### 總覽儀表板

```
┌─────────────────────────────────────────────────┐
│  Tool Call Accuracy Report                      │
│  Model: GPT-4 | Date: 2026-02-02               │
├─────────────────────────────────────────────────┤
│  Overall                                        │
│  ████████████████████░░░░  85% Exact Match     │
│  ██████████████████████░░  92% Tool Correct    │
├─────────────────────────────────────────────────┤
│  By Category                                    │
│  preprocessing  ████████████████████  95%      │
│  training       ████████████████░░░░  80%      │
│  evaluation     ██████████████████░░  88%      │
├─────────────────────────────────────────────────┤
│  Trend (Last 5 Runs)                           │
│  v1.0: 75% → v1.1: 80% → v1.2: 85% ↑          │
└─────────────────────────────────────────────────┘
```

---

## 實作階段

### Phase 1：核心框架
- [ ] 定義 Benchmark Dataset Schema
- [ ] 實作 `ToolCallEvaluator` 類別
- [ ] 實作 Results Store

### Phase 2：CLI 與自動化
- [ ] CLI 介面 `xbrainlab.eval`
- [ ] 整合 CI/CD 自動評測

### Phase 3：分析與報告
- [ ] 歷史趨勢分析
- [ ] HTML/PDF 報告產生
- [ ] 錯誤模式分析

---

## 6. 實驗管理工具：MLflow 整合

使用 **MLflow** 管理實驗結果。

### 優點
- 視覺化儀表板
- 參數/指標自動追蹤
- 實驗比較功能

### 6.1 Parameters（實驗配置）

```python
# 模型配置
mlflow.log_param("model", "gpt-4")
mlflow.log_param("model_version", "2024-01-01")
mlflow.log_param("temperature", 0.0)

# 組件開關
mlflow.log_param("rag_enabled", True)
mlflow.log_param("rag_top_k", 5)
mlflow.log_param("memory_enabled", True)
mlflow.log_param("memory_window", 10)
mlflow.log_param("verification_enabled", True)
mlflow.log_param("execution_mode", "single")  # single/multi

# 測試集配置
mlflow.log_param("benchmark_version", "v1.0")
mlflow.log_param("test_cases_count", 100)
```

### 6.2 Metrics（評估指標）

```python
# 整體指標
mlflow.log_metric("tool_accuracy", 0.92)
mlflow.log_metric("param_accuracy", 0.85)
mlflow.log_metric("exact_match", 0.80)

# 分類指標（依 Category）
mlflow.log_metric("cat_preprocessing_acc", 0.95)
mlflow.log_metric("cat_training_acc", 0.88)
mlflow.log_metric("cat_evaluation_acc", 0.90)

# 工具指標（依 Tool）
mlflow.log_metric("tool_apply_filter_acc", 0.93)
mlflow.log_metric("tool_create_epochs_acc", 0.87)

# RAG 指標（若啟用）
mlflow.log_metric("retrieval_precision", 0.78)
mlflow.log_metric("context_relevance", 0.82)

# 效能指標
mlflow.log_metric("avg_latency_ms", 1250)
mlflow.log_metric("total_tokens_used", 45000)
```

### 6.3 Artifacts（附件檔案）

```python
mlflow.log_artifact("results_detail.json")   # 詳細結果
mlflow.log_artifact("error_analysis.json")   # 錯誤分析
mlflow.log_artifact("benchmark_v1.0.json")   # 測試集快照
mlflow.log_artifact("system_prompt.txt")     # 系統 Prompt 版本
```

### 6.4 運行命名策略

```python
run_name = f"{model}_{config_hash}_{timestamp}"
# 例如：gpt4_rag_on_mem_on_20260202
```

### 6.5 追蹤維度總結

| 類別 | 追蹤項目 | 用途 |
|------|----------|------|
| 模型配置 | model, temperature | 比較不同模型 |
| 組件開關 | rag_enabled, memory_enabled | 消融實驗 |
| 整體準確率 | tool_accuracy, exact_match | 主要指標 |
| 分類準確率 | cat_*_acc | 找出弱點類別 |
| 工具準確率 | tool_*_acc | 找出問題工具 |
| RAG 品質 | retrieval_precision | 驗證 RAG 價值 |
| 效能 | latency, tokens | 成本分析 |

### 6.6 啟動 MLflow UI

```bash
mlflow ui --port 5000
# 瀏覽器開啟 http://localhost:5000
```

---

## 7. 組件消融實驗設計

### 7.1 RAG 消融實驗

| 實驗組 | 配置 | 衡量指標 |
|--------|------|----------|
| **Baseline (No RAG)** | `rag_enabled=False` | Tool Accuracy |
| **With RAG** | `rag_enabled=True` | Tool Accuracy |
| **RAG Retrieval Quality** | 人工標註 | Retrieval Precision@K |

#### 測試集設計

```json
{
  "id": "rag_test_001",
  "input": "幫我跑 EEGNet 模型",
  "expected_retrieval": ["eegnet_example.md", "training_guide.md"],
  "expected_tool": "select_model"
}
```

#### 評估指標

- **Retrieval Precision**：檢索結果中相關文件的比例
- **Context Relevance**：檢索內容是否包含正確答案的線索
- **Accuracy Delta**：with RAG vs without RAG 的準確率差異

---

### 7.2 Memory 消融實驗

| 實驗組 | 對話歷史 | 測試集 |
|--------|----------|--------|
| **No Memory** | 無歷史 | 標準測試集 |
| **Happy Path** | 線性正常流程歷史 | 順序操作測試集 |
| **Confused Path** | 混亂/矛盾歷史 | 干擾測試集 |

#### 測試集設計

**Happy Path 範例**：
```json
{
  "history": [
    {"user": "載入資料 sample.fif", "tool": "load_data"},
    {"user": "套用 0.5-50Hz 濾波", "tool": "apply_filter"}
  ],
  "current": "接著做 epoching",
  "expected": "create_epochs"
}
```

**Confused Path 範例**：
```json
{
  "history": [
    {"user": "載入資料 sample.fif", "tool": "load_data"},
    {"user": "等等，先取消", "tool": null},
    {"user": "還是載入好了", "tool": null},
    {"user": "套用濾波...不對，先看看資料", "tool": null}
  ],
  "current": "好，現在套用 0.5-50Hz",
  "expected": "apply_filter"
}
```

#### 評估指標

- **Accuracy by Path Type**：各路徑類型的準確率
- **Memory Robustness**：混亂歷史下的準確率衰減程度

---

### 7.3 Stage Boundary Testing（跨階段測試）

測試 Agent 是否正確識別階段衝突，並建議先決步驟。

| 測試類型 | 說明 |
|----------|------|
| **Out-of-Stage Request** | 給不屬於當前階段的指令 |
| **Prerequisite Suggestion** | 是否正確建議需先完成什麼 |

#### 測試集設計

```json
{
  "id": "stage_boundary_001",
  "current_stage": "IDLE",
  "input": "幫我訓練 EEGNet 模型",
  "expected_behavior": "suggest_prerequisite",
  "expected_tool": null,
  "expected_message_contains": ["載入資料", "load", "先"]
}
```

#### 評估指標

- **Stage Awareness Rate**：Agent 正確識別階段衝突的比例
- **Prerequisite Suggestion Rate**：Agent 正確建議先決步驟的比例
- **False Positive Rate**：誤判可用操作為不可用的比例

---

### 7.4 其他組件（待設計）

以下組件的實驗設計需進一步討論：

- **Verification**：Self-Verification 的攔截率與誤判率
- **Tool Definition**：工具描述品質對準確率的影響
- **Prompt Engineering**：不同 System Prompt 的效果比較

---

## 待釐清事項

- Benchmark Dataset 的測試案例數量與覆蓋範圍
- 多輪對話（Multi-Turn）的準確率如何計算
- 是否需要評估「工具執行結果」而非只是「工具選擇」
- 其他組件消融實驗的具體設計
