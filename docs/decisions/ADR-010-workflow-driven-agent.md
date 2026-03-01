# ADR-010: Workflow-Driven Agent 執行模式與 Complete 概念替換

**日期**: 2026-03-01
**狀態**: 規劃中 (Planned)
**決策者**: 核心開發團隊

## 背景 (Context)

目前 `LLMController` 中定義了兩種執行模式：
- `single` (單步模式)：執行一次工具後即返回控制權給使用者。
- `multi` (多步模式)：依賴 LLM 自行決定是否繼續呼叫下一個工具，並使用盲目的啟發式防護 (`_max_successful_tools`，預設為 5) 來強制停止。

**痛點分析**：
1. **語義不符**：使用者在要求 AI 連續執行時，心理預期是「完成 (Complete) 一個大任務」，而不是單純的「執行很多步 (Multi)」。
2. **不可預測性 (Lack of Predictability)**：`multi` 模式本質上是一個難以預測的 Open-ended ReAct 迴圈。在神經科學與資料處裡領域中，無法確定 LLM 到了第 N 步是真的做完任務，還是卡在無意義的重試中。
3. **安全風險**：依賴 LLM 的內部邏輯來決定流程終點，會降低系統對專家用戶的透明度與可信度。

## 決策 (Decision)

1. **命名與概念替換**：廢除 `multi` 模式的命名，改為 **`complete` (完整 / 全自動) 模式**，使語義符合使用者「一次搞定」的期望。
2. **架構轉型：Workflow-Driven Agent (工作流驅動)**：
   - 放棄讓 LLM 在一個開放迴圈中漫無目的地一步步摸索。
   - 轉向 **工作流驅動 (Workflow-Driven) 或 狀態機 (State Machine)** 的設計。任務的執行應該是有明確起點、步驟與終點的。

### 潛在的實作方向 (待後續收斂)
為實現 `complete` 模式，未來將從以下兩種方案中選擇或混合使用：
- **作法 A：LLM 作為編排者 (Dynamic Planner)**
  使用者輸入需求後，LLM 首先輸出一份前置規劃 (例如 JSON 格式的 Workflow Plan `[Task1, Task2, ...]`)。系統讓使用者確認後，LLM 或狀態機再依序、確定性地將這份清單執行完畢。
- **作法 B：靜態工作流 (Static Workflow) 結合 LLM 參數提取**
  系統內建幾套標準處理流程（例如：Standard Preprocess = Load -> Filter -> Epoch）。使用者選擇流程後，LLM 僅負責從自然語言中萃取參數（如頻率），後續執行完全由系統的狀態機接管。

## 影響與後果 (Consequences)

### 正面影響 (Pros)
- **提升穩定性與可信度**：流程從黑盒子變成白盒子，每一步都可預測，不會發生 LLM 暴走執行未知工具的情況。
- **大幅降低 Token 消耗與延遲**：不需要在每做完一步後就把巨大的歷史記錄再次餵給 LLM 進行下一次「思考」，只需按照 Workflow 執行。
- **增強分層提示 (Hierarchical Prompting)**：當系統知道目前正在 Workflow 的哪個階段，就能只將該階段相關的工具 (例如只給 Preprocess 相關的 Tools) 丟給 LLM，顯著提升小型模型（如 Qwen 7B）的準確率。

### 負面影響與挑戰 (Cons)
- **工程複雜度增加**：需要實作一個新的 `WorkflowManager` 或排程層來取代現在簡單的 `while/if` 迴圈邏輯。
- **靈活性折衷**：對於極度開放、連開發者都沒想到的使用情境，純靜態 Workflow 可能無法覆蓋，需依賴 LLM 的動態規劃能力來彌補。
