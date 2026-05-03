# XBrainLab Roadmap

最後更新：`2026-05-04`

這份 roadmap 定義 XBrainLab 走向工程級成品的產品主線。

它不是短期 task list，也不是歷史流水帳：

- 目前真相看 `docs/current.md`。
- 短期施工焦點看 `docs/planning/now.md`。
- 目標態看 `docs/target/`。
- 已做過的重要變更看 `docs/records/implementation_log.md`。

Roadmap 只回答一件事：XBrainLab 要完成成品，還必須打通哪些主線，以及每條主線怎樣才算完成。

## Product North Star

XBrainLab 的目標是成為可直接在本地使用的 EEG / BCI 分析桌面軟體。

使用者理想上只需要：

```text
提供資料位置
  -> 系統可靠解讀資料與 label / event
  -> 使用者確認不明確語意
  -> 軟體可完成 preprocessing / dataset / training / evaluation / visualization / saliency
  -> assistant 能在同一套 workflow truth 上協助操作
  -> external agents 可透過 MCP adapter 操作同一套 workflow truth
  -> 所有重要判斷都有可重跑 evidence
```

這代表 XBrainLab 不是 demo，不是只修到測試過關，也不是把聊天框接到幾個 controller。
完成品必須同時滿足：使用者友善、架構乾淨、資料語意可信、agent tool-call 可驗證、Windows
本地啟動可交付。

## 路線原則

- 對外只看完成品；工程內部可以切片，但不能把切片完成說成產品完成。
- UI、in-app agent、headless runner、MCP server 必須共用同一套 `ApplicationService / Command API`。
- 資料入口的核心不是舊 `load_data / attach_labels`，而是 Data Interpretation System。
- agent 不能靠 prompt 自己猜 backend 能力；可執行 command 必須由 backend capability policy 控制。
- MCP 是 external agent adapter，不是另一套 backend，也不能繞過 autonomy policy。
- 論文主 evidence 是 agent tool-call 準確率，不是 EEG training accuracy。
- local assistant runtime 是產品路線；不使用 API / Gemini 作為產品 execution path。
- 不使用中國公司或中國來源模型。
- dashboard clean 只能代表工程健康，不能代表產品、agent 或論文 claim 已完成。
- 文件、程式、測試、artifact 必須同步；不能留下多套 truth。

## Product Completion Tracks

| Track | 目標 | 目前判斷 | 完成條件 |
| --- | --- | --- | --- |
| Documentation Truth | 文件能讓人掌握目標、現況、決策與驗證證據。 | canonical 結構已建立；仍需隨實作持續對齊。 | `target/`、`architecture/`、`planning/`、`validation/`、`records/` 分工穩定；MkDocs strict 通過；文件不再宣稱未完成能力。 |
| Backend Command Spine | UI / agent / script 都走同一套 workflow command layer。 | `ApplicationService` baseline 已落地，但仍有 legacy / adapter path。 | 核心 workflow 不再靠 UI/controller 私有邏輯；command、state snapshot、capability policy、typed result、confirmation、rollback 都有 non-mocked tests。 |
| Data Interpretation System | 使用者給資料位置，系統建立可預覽、可驗證、可重跑的 `DataInterpretation`。 | 目標設計已完成；實作尚未開始。 | `scan -> interpret -> preview -> validate -> confirm -> apply -> recipe` 成為 UI / agent / headless 的唯一資料入口心智模型。 |
| UI Product Experience | 使用者看到的是 EEG workflow 工具，不是 debug 面板。 | assistant UI 已多輪修正，但仍需真使用者 click-through 驗收。 | import、preprocess、dataset、training、evaluation、visualization、saliency、assistant 都能被正常操作；狀態與錯誤用使用者語言呈現。 |
| Agent Runtime And Tool Surface | assistant 是 workflow operator，透過 state、verification 和 command result 操作軟體。 | controller / verifier / local runtime / capability gate 已存在；tool surface 仍受舊資料入口影響。 | agent tools 遷移到 Data Interpretation + ApplicationService command；State Snapshot、Verification Result、visible response、retry / recovery 都可評分。 |
| Automation Adapters / MCP | CI、eval、batch 和外部 agent 能操作同一套 workflow truth。 | headless/script path 是輔助角色；MCP 尚未建立。 | CLI/headless runner 用於 CI / eval / batch；MCP server 暴露同一套 command taxonomy 給 external agents；client 不需安裝 XBrainLab 的 EEG/PyQt/PyTorch 依賴；所有 MCP calls 仍受 capability / autonomy policy 約束。 |
| Validation And Thesis Evidence | 以可重跑 benchmark 證明 agent tool-call 準確率。 | thesis protocol 已定義；正式 local LLM eval runner 和足量 cases 尚未完成。 | 至少 50 個 engineering cases、100 個 thesis candidate cases；local primary / fallback 重跑；artifact、failure taxonomy、report 可重現。 |
| Packaging And Release | 使用者能從 Windows 桌面啟動並可靠使用。 | launcher baseline 已有；仍不是完整 release packaging。 | Desktop launcher / packaging、local model consent、資源提示、geometry recovery、真 Windows walkthrough、release gate 全部通過。 |

## Roadmap Order

這不是版本承諾，而是比較合理的工程順序：

1. **鎖定文件真相**
   - 確認 target、architecture、roadmap、validation 沒有互相打架。
   - 每次大改後更新 records，避免只靠聊天上下文。

2. **完成 Backend Command Spine**
   - 收斂 ApplicationService command。
   - 盤點並移除 UI / agent 還在直接依賴 controller workflow logic 的路徑。
   - 強化 lifecycle、rollback、confirmation、resource gate。

3. **實作 Data Interpretation System**
   - 建立 `ScanResult`、`InterpretationCandidate`、`InterpretationPreview`、
     `ValidationDecision`、`AppliedInterpretation`、`ImportRecipe`。
   - 覆蓋 BIDS、GDF + external labels、MAT / CSV / TSV labels、EEGLAB、BrainVision、
     XDF / BrainFlow、clinical interval 等主流情境。
   - 所有 recipe reload 都要重新 preview / validate。

4. **重做資料入口 UI**
   - 使用者選 file / folder / BIDS root / recipe。
   - UI 顯示系統找到什麼、如何解讀、哪些需要確認、哪些 blocked。
   - 不再用「Imported / Labels attached」這種不足以判斷可信度的狀態作為主語言。
   - Data Interpretation 會自然牽動 UI；這裡允許重設資料入口 UI，而不是把新流程塞進舊
     import / label 按鈕外殼。

5. **遷移 Agent Tool Surface**
   - 把 agent 的資料入口從 `load_data / attach_labels` 換成 Data Interpretation tools。
   - Context Assembler 只暴露目前 backend policy 允許或需要確認的 command。
   - Verification Layer 同時檢查 schema、confidence、capability policy 和 Data Interpretation decision。

6. **建立 Automation Adapters / MCP**
   - 保留 CLI / headless runner 作為 CI、eval、batch 和 artifact 入口。
   - 新增 MCP server 作為 external agent adapter。
   - MCP tools 使用同一套 Data Interpretation / command taxonomy，不直接操作 controller。
   - MCP client 不需要下載 XBrainLab 的大型科學計算與 UI 依賴；依賴留在 XBrainLab prepared runtime。

7. **建立 Tool-call Evaluation System**
   - 設計 benchmark case schema、scorer、runner、artifact。
   - cases 必須覆蓋 happy path、blocked、missing parameter、ambiguous intent、recovery、
     Data Interpretation confirmation、recipe reload。
   - deterministic baseline 只能證明 scorer；scripted replay 也要能產生 UI-observable evidence；
     正式 evidence 必須跑 local LLM primary / fallback。

8. **完成 Product Walkthrough And Release Gate**
   - Windows launcher 真機 click-through。
   - 真 local model ChatPanel walkthrough。
   - button-driven UI 和 assistant-driven workflow 都要能走完代表性流程。
   - 測試、文件、artifact、launcher / packaging 全部同步後才可稱為可交付。

## Non-goals

- 不把 roadmap 寫成每天要做什麼；短期工作放 `now.md`。
- 不用更多 planning 文件分散 truth。
- 不把舊 `load_data / attach_labels` 當成新產品資料入口。
- 不把 mock-heavy tests 當成真實 workflow evidence。
- 不把 scripted replay 的文字報告當成 UI 行為已驗證；需要 transcript、state、screenshot 或
  UI observable artifact。
- 不把 EEG model accuracy 寫成本論文主 evidence。
- 不下載超過資源邊界的大模型；單模型原則 10GB 內，總 cache 原則 20GB 內，除非使用者明確同意。
- 不讓 API / Gemini / remote LLM 回到產品 execution path。
- 不讓 MCP 成為第三套 workflow truth 或繞過 ApplicationService。

## 成品判定

XBrainLab 只有在下列條件同時成立時，才算進入可交付狀態：

- 使用者可以從 Windows 桌面啟動。
- UI 能完成代表性 EEG workflow。
- assistant 能在同一套 backend truth 上協助操作，而不是暴露 raw tool / debug syntax。
- external agents 能透過 MCP 操作同一套 command surface，而不需要自己安裝 XBrainLab 的完整
  EEG/PyQt/PyTorch stack。
- 資料匯入與 label / event 解讀可預覽、可確認、可保存 recipe、可重跑。
- training / evaluation / visualization / saliency 可以追溯資料 recipe 與 workflow state。
- tool-call eval 有固定 cases、重跑 artifact、score breakdown 和 failure taxonomy。
- 文件與程式碼一致，沒有把未完成能力寫成已完成。
