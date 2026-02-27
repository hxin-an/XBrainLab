# ADR-006：Agent ReAct 架構與驗證策略

- **狀態**: 部分實作 (Partially Implemented)
- **日期**: 2026-02-02（更新: 2026-02-25）
- **作者**: XBrainLab 團隊

> **實作狀況**: ContextAssembler + VerificationLayer 已實作，但信心度檢查尚未完全啟用（見 KNOWN_ISSUES.md）。

---

## 背景

目前 Agent 架構存在以下問題：

1. **工具執行結果未回傳**：Tool Call 執行後，結果未納入 LLM 下一輪思考
2. **執行順序混亂**：Tool Call 執行中，使用者可繼續發送訊息，導致衝突
3. **缺乏驗證機制**：錯誤的 Tool Call 直接執行，無法攔截

---

## 決策

實作標準 **ReAct (Reasoning + Acting) 架構**，並加入 **Adaptive Verification Strategy**。

---

## 設計概覽

### 1. ReAct 迴圈

```
使用者發送訊息
       ↓
   Agent 思考 (Think)
       ↓
   決定行動 (Act) ──→ 無 Tool Call → 輸出回應 → 結束
       ↓
   執行 Tool Call
       ↓
   觀察結果 (Observe)
       ↓
   結果回傳給 Agent
       ↓
   Agent 再次思考 → [迴圈繼續或輸出最終回應]
```

### 2. 工具結果回傳

```python
messages = [system_prompt, user_message]

while True:
    response = llm.chat(messages)

    if response.has_tool_call:
        tool_result = execute_tool(response.tool_call)

        # 關鍵：結果加入對話歷史
        messages.append({
            "role": "tool",
            "tool_call_id": response.tool_call.id,
            "content": json.dumps(tool_result)
        })
    else:
        return response.content  # 最終回應
```

### 3. UI 鎖定機制

| 狀態 | 輸入框 | 說明 |
|------|--------|------|
| 閒置 | ✅ 可輸入 | 正常狀態 |
| Tool Call 執行中 | ❌ 鎖定 | 顯示「執行中...」狀態 |
| 等待 LLM 回應 | ❌ 鎖定 | 顯示「思考中...」狀態 |

### 4. 執行模式選擇器

在 ChatPanel 提供 UI 選單，讓使用者選擇執行模式：

```
┌─────────────────┐
│ 執行模式 ▼      │
├─────────────────┤
│ ○ 單步執行      │  ← 每次最多一個動作
│ ● 自動流程      │  ← 允許連續執行多個動作
└─────────────────┘
```

| 模式 | 行為 | 適用情境 |
|------|------|----------|
| **單步執行** | 每次最多 1 個成功 Tool Call | 學習中、需要細緻控制 |
| **自動流程** | 允許連續執行多個 Tool Call | 熟悉流程、「幫我跑完」 |

### 5. 迴圈控制（雙重限制）

為避免 Agent 過度執行，採用雙重限制：

| 限制 | 說明 | 建議值 |
|------|------|--------|
| **硬上限** | 無論成功失敗，最多迴圈 N 次 | 10 次 |
| **成功上限** | 成功執行的 Real Tool Call 次數 | Single=1, Multi=5 |

```python
MAX_ITERATIONS = 10
MAX_SUCCESSFUL_TOOLS = 1 if mode == "single" else 5

iterations = 0
successful_tools = 0

while iterations < MAX_ITERATIONS:
    iterations += 1
    response = llm.chat(messages)

    if not response.has_tool_call:
        break  # LLM 決定結束

    result = execute_tool(response.tool_call)
    messages.append({"role": "tool", "content": result})

    if result.success:
        successful_tools += 1
        if successful_tools >= MAX_SUCCESSFUL_TOOLS:
            # 達到成功上限，生成總結回應
            return llm.summarize(messages)

# 達到硬上限或正常結束
return final_response
```

---

## 驗證策略 (Adaptive Verification)

### 核心邏輯

根據模型能力自動選擇驗證方式：

```python
class VerificationStrategy:
    # 支援 Confidence 輸出的模型清單
    CONFIDENCE_MODELS = ["gpt-4", "gpt-4o", "claude-3"]

    def should_verify(self, model: str, tool_call: ToolCall) -> bool:
        # 破壞性操作：永遠驗證
        if tool_call.is_destructive:
            return True

        # 模型支援 Confidence
        if model in self.CONFIDENCE_MODELS:
            return tool_call.confidence < 0.8

        # 模型不支援：全部走 Self-Verification
        return True

    def verify(self, user_message: str, tool_call: ToolCall) -> VerifyResult:
        prompt = f"""
        使用者要求：{user_message}
        你打算執行：{tool_call}

        這個 Tool Call 正確嗎？請回答 YES 或 NO，並說明原因。
        """
        return llm.chat(prompt)
```

### 驗證流程

```
使用者訊息
     ↓
Agent 生成 Tool Call
     ↓
VerificationStrategy.should_verify()
     ↓
 ┌───┴───┐
 │       │
 不需驗證   需要驗證
 │       │
 ↓       ↓
執行     Self-Verification
 │       │
 │    ┌──┴──┐
 │    │     │
 │   正確   錯誤
 │    │     │
 │    ↓     ↓
 └──→執行  Agent 重新生成
```

### 破壞性操作定義

以下操作標記為 `is_destructive = True`：

- `clear_dataset`
- `reset_preprocessing`
- `rollback_to_stage`

---

## 自動化支援多模型

### 模型能力探測

```python
class ModelCapabilities:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._detect_capabilities()

    def _detect_capabilities(self):
        # 根據模型名稱或 API 回應判斷能力
        self.supports_confidence = self.model_name in [
            "gpt-4", "gpt-4o", "claude-3-opus", "claude-3.5-sonnet"
        ]
        self.supports_tool_call = True  # 假設所有模型支援
        self.supports_streaming = True
```

### 配置介面

未來可在 GUI 中提供：
- 模型選擇下拉選單
- 驗證策略開關（自動 / 強制驗證 / 關閉驗證）

---

## 實作階段

### Phase 1：ReAct 核心迴圈
- [ ] 實作 Tool Result 回傳機制
- [ ] 實作 ReAct 迴圈（Think → Act → Observe）
- [ ] UI 輸入鎖定（Tool 執行中）

### Phase 2：驗證策略
- [ ] 實作 `VerificationStrategy` 類別
- [ ] 定義破壞性操作清單
- [ ] 實作 Self-Verification Prompt

### Phase 3：多模型支援
- [ ] 實作 `ModelCapabilities` 探測
- [ ] 維護 `CONFIDENCE_MODELS` 清單
- [ ] GUI 驗證策略配置

---

## 影響評估

### 正面影響
- **準確性提升**：LLM 可根據工具結果調整行為
- **順序保證**：不會發生「前面沒做完就做後面」
- **錯誤攔截**：驗證機制可攔截明顯錯誤
- **模型彈性**：自動適應不同模型能力

### 負面影響
- **延遲增加**：驗證需額外 LLM 呼叫
- **複雜度**：新增驗證層邏輯

---

## 待釐清事項

以下項目需進一步討論與設計：

### 計數方式
- 「成功上限」應以「單一工具呼叫」還是「單一 LLM 回應（可能包含多個工具）」計算？
- 建議：以「LLM 回應」為單位，一次回應的所有工具都成功 = 1 次成功

### Long-Running Tools
- 長時間執行的工具（如訓練模型）如何處理？
- 是否需區分「即時工具」與「背景任務」？
- 執行中狀態如何回報？使用者能取消嗎？

### Self-Verification 問題
- 驗證成本：不支援 Confidence 的模型需全部驗證，延遲加倍
- 驗證準確度：自我驗證是否真的能攔截錯誤？
- 使用者選項：是否需要「關閉驗證」選項？

### Streaming 衝突
- Streaming 開啟時，工具呼叫如何處理？
- 是否先禁用 Streaming 或等待完整回應？

### 並行 Tool Call
- LLM 一次回傳多個 Tool Call 時如何處理？
- 建議：先順序執行，未來再考慮並行

### 使用者中斷
- Agent 執行中，使用者想停止怎麼辦？
- 需要 Cancel 按鈕嗎？中斷後狀態如何清理？
