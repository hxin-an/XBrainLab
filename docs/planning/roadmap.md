# XBrainLab Roadmap

最後更新：`2026-05-06`

這份 roadmap 只回答三件事：

- XBrainLab 要成為什麼產品。
- 目前哪些產品主線還沒完成。
- 哪些想法只是 future work，不能當成現在的 blocker。

細節歷史看 `docs/records/implementation_log.md`；逐 slice 驗證看
`docs/records/worklog.md`；短期施工看 `docs/planning/now.md`。

## North Star

XBrainLab 要成為本地可用的 EEG / BCI 桌面分析工具。

目標使用路徑：

```text
選資料來源
-> 系統解讀資料 / label / event
-> 使用者確認不明確語意
-> preprocessing / epoch / dataset / training
-> evaluation / visualization / saliency
-> assistant 和 MCP 都走同一套 workflow truth
```

完成品不能只靠 backend JSON、mock tests、deterministic eval 或文字報告宣稱完成。

## Product Tracks

### Documentation Truth

**Goal**：文件讓人快速掌握 current truth、目標、短期工作、驗證邊界。

**Now**：canonical 結構已建立，但入口文件仍過長。下一步要做 documentation reset。

**Done When**：

- `current.md` 可在 5-10 分鐘內讀完。
- `roadmap.md` 只保留產品主線與 future directions。
- `now.md` 只保留下一輪焦點。
- `validation/README.md` 只保留 evidence 分層與 artifact index。
- `implementation_log.md` 高層、短；細節只放 `worklog.md`。

### Backend Command Spine

**Goal**：UI、agent、headless、MCP 都走 `ApplicationService / Command API`。

**Now**：command spine 已是主路徑，許多 workflow 已拆到 focused services。仍不能宣稱 fully clean：
UI refresh 還有 observer / manual / command-result 混合模式，controller fallback audit 也未完全關閉。

**Done When**：

- `ApplicationService` 只負責 dispatch、policy gate、result envelope。
- mutating product runtime 不 silent fallback 到 controller mutation。
- command result 的 `changed_state` 可驅動主要 UI refresh。
- legacy `load_data / attach_labels` 只保留 compatibility，不主導新 UI / agent 心智模型。

### Data Interpretation System

**Goal**：Data Interpretation 是唯一新資料入口語言。

**Now**：file / folder / BIDS-style / recipe flow 已有 baseline：scan -> preview -> validate ->
confirm/apply -> save recipe。metadata、class map、event role、label carrier 和 recipe trace
已進 UI / backend / state snapshot。

**Still Missing**：

- mature embedded label editor
- raw trigger selector
- complex GDF / MAT anchor reconciliation
- XDF / LSL stream parser
- full real-data manual certification
- mature recipe diff / review UX

### UI Product Experience

**Goal**：使用者看到的是 EEG workflow 工具，不是 debug panel 或 AI demo。

**Now**：ChatPanel、Data Interpretation wizard、Dataset layout、walkthrough artifacts 已有多輪 polish。
仍缺 Windows human desktop acceptance 和完整 product walkthrough。

**Done When**：

- import / preprocess / train / evaluate / visualize / saliency 可由使用者正常操作。
- visible UI 不顯示 raw tool syntax、schema、traceback、snake_case command。
- narrow / docked / high-DPI / Windows launcher path 都有 evidence。
- automated walkthrough 和 human desktop acceptance 明確分層。

### Agent Runtime And Tool Surface

**Goal**：assistant 是 workflow operator，使用 state snapshot、verification、capability policy、
typed command result。

**Now**：formal `121` case local tool-call benchmark 已有 primary / fallback x3 evidence；
source suite 已增到 `122` cases，但新增中文 missing-input case只跑 fast deterministic gate。

**Done When**：

- Data Interpretation 是 agent primary data-entry path。
- no-call / clarification / blocked / confirmation boundary 可穩定處理。
- tool-call report 能說清楚 case family、metric、failure taxonomy、model comparison 和 claim boundary。
- 不把 tool-call score 擴張成 UI / launcher / product completion claim。

### Automation Adapters / MCP

**Goal**：external agents 可透過 MCP 操作同一套 command surface。

**Now**：stdio MCP、Inspector config / CLI / GUI baseline、local HTTP transport / train job baseline 已存在。
仍不是 full client certification。

**Done When**：

- MCP tools/list、agent tools、headless schema 共用同一套 truth。
- MCP calls 全部走 ApplicationService policy。
- long-running jobs、authorization、persistence / recovery、client certification boundary 清楚。

### Packaging And Release

**Goal**：使用者能從 Windows 桌面啟動並完成代表性 workflow。

**Now**：automated launcher/startup baseline 已存在；真人 Windows click-through、雙螢幕、
DPI、長 local model session 尚未完成。

**Done When**：

- Windows launcher human acceptance passed。
- first-run model/resource boundary 清楚。
- packaging / logs / recovery path 可交接。

## Future Work

這些是未來方向，不是 current commitment，也不是 Goal 1 blocker。
架構健康與 documentation reset 完成後再討論。

### Expert Workflow Mode

給有經驗的腦科學 / EEG 使用者更彈性的 workflow。

- 可以跳步、重跑某段、比較多個 recipe。
- 仍走 Command API / capability policy。
- 第一版不開任意 Python execution。

### Workflow Recipe DSL

用受限 declarative workflow recipe 取代一長串脆弱 tool calls。

- 可由 user 編輯，也可由 assistant 產生草稿。
- 每一步仍要 verification / confirmation。
- 借鑑 programmatic tool calling，但不開放任意 code-space 直接操作 backend。

### Training Model Registry

這裡的 model 是 EEG training model，不是 LLM。

- 例如 EEGNet、DeepConvNet、ShallowConvNet、TCN、Transformer-based EEG model。
- 每個 model 應有 task fit、input requirement、resource profile、explainability support。
- 使用者應保留擴充 model 的權利，但 release / thesis claim 只認列通過 validation profile 的 model。

### Training Model Node Visualization

讓使用者理解 EEGNet 等 training model 的內部結構。

第一版應低資源：

- layer / node graph
- input/output tensor shape
- parameter count
- activation memory estimate
- supported saliency hooks

不應先做 heavy live activation animation 或 training-time introspection。

### Training Model Compatibility Check

在使用者選 model 前檢查目前 dataset 是否適合。

- channel count / sample length / class count
- epoch window
- model input shape
- GPU / memory estimate
- blocked reason 或 recommended adjustment

## Current Priority Order

1. Documentation reset：先讓文件能被人讀。
2. Architecture health：command spine、refresh coordinator、controller fallback audit。
3. Data Interpretation mature wizard。
4. UI / assistant product walkthrough。
5. Release / thesis gate：只在產品路徑穩定後刷新 full local eval。

## Non-Goals

- 不把 future work 當成目前 checklist。
- 不把 deterministic eval 當成 local LLM 真實 tool-call accuracy。
- 不把 EEG training accuracy 當成 thesis 主 evidence。
- 不讓 API / Gemini / remote LLM 回到 product execution path。
- 不用中國公司或中國來源模型。
- 不讓 MCP 或 UI 繞過 ApplicationService。
