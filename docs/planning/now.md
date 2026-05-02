# Now

最後更新：`2026-05-02`

這份文件只放短期工作焦點。

## 目前位置

目前位置是：

```text
後端 Application Service contract baseline -> UI / Agent command surface 第一批統一完成
-> local LLM primary/fallback runtime smoke 通過 -> desktop launcher startup smoke 通過
-> chat product blocker 修復 -> 第一批 UI execution service adapter / agent direct CommandResult path
-> product click-through smoke / synthetic pipeline walkthrough 已新增
```

## 重要狀態修正

2026-05-02 人工檢查曾發現 AI Assistant 有明顯產品阻塞，並已在本輪補 targeted fix：

- chat UI 當時仍像 debug dock，尚未達到產品級對話介面。
- 使用者送出 `hello` 後當時只看到 user bubble，沒有 assistant 回覆。
- 這代表舊的 automated product gate 沒有覆蓋「一般文字輸入 -> 可見 assistant 回覆 / 可見錯誤」這條最基本 product flow；本輪已補。
- deterministic tool-call eval、local runtime health check、launcher startup smoke 不能代表 chat 產品流程已可用。

後端狀態需要分開判斷：

- `ApplicationService / Command API` backend baseline 已驗證，可作為後續 UI / Agent migration 的基礎。
- 第一批 UI execution 已接 service-backed command adapter：dataset import、reset、preprocess、
  epoching、training start / stop。仍不是完整 service-first，因為 label import、smart parse、
  channel selection、split/model/training dialogs、evaluation / visualization query actions
  還有 controller direct-call path。
- Agent tool surface 已開始使用 backend capability policy 和 typed adapter；mapped workflow
  tools 可直接消費 `CommandResult`，但 `load_data`、`set_montage`、`switch_panel` 等仍保留
  legacy real-tool / UI request path。

## 產品線盤點

### A. Backend

- `ApplicationService` command contract、state snapshot、capability policy 仍是目前最可信的
  backend core。
- `BackendFacade` 保留 headless / assistant compatibility surface，核心 workflow 已包
  ApplicationService，不應再塞新 business logic。
- reset / destructive command policy 已存在；UI confirmation walkthrough 仍要補。
- `evaluate` / `visualize` / `saliency` / `new_session` 仍是 disabled future placeholder，
  文件和 UI / agent 不能把它們寫成完成。

### B. UI

- MainWindow / panel startup smoke 仍可用，但這不代表 assistant 互動可用。
- UI readiness 第一批已共用 ApplicationService capability policy；第一批 high-value action
  execution 已透過 `ApplicationService.execute()`，剩餘 dialog / query actions 仍有 direct
  controller legacy path。
- ChatPanel 本輪已完成 product redesign：header、status chips、empty state、bubble、composer、
  visible error feedback。
- `tests/integration/ui/test_product_walkthrough.py` 已覆蓋 assistant click-through layout 與
  synthetic EEG button-driven pipeline walkthrough。
- 真 Windows launcher 打開 assistant 後的 click-through 仍未完成。

### C. Agent

- normal no-tool response、tool-call response、empty response、worker error、local unavailable
  現在都有 targeted tests。
- tool result 保留 structured payload；tool-only success 會有可見 summary。
- mapped workflow tools 可直接回 `ToolCommandResult.from_command_result(...)`；legacy path
  保留給需要 directory expansion、UI request 或 read-only routing 的 tools。
- deterministic eval 只代表 scripted baseline，不代表 local LLM 真實能力。

### D. Local LLM Runtime

- Phi primary / fallback cache、preflight、prompt smoke、structured-output smoke 已通過。
- local ready 不能再被誤讀為 UI chat flow 一定可用；本輪已把這個邊界寫進 validation。
- 真 local model 在 ChatPanel 中的 full response walkthrough 仍要 resource-safe smoke。

### E. Launcher / Packaging

- Windows launcher / Desktop shortcut 已產出，`xvfb` startup smoke 顯示 `MainWindow initialized`。
- 這仍不是人工 click-through。需要驗收 Desktop launcher -> MainWindow -> assistant -> visible
  response / visible failure。

### F. Tests / Validation

- 先前 dashboard / deterministic eval 漏掉 no-response bug。
- 新增 product-flow tests 覆蓋 normal chat response、empty response、worker error、local unavailable、
  UI structure。
- 新 validation rule：不能只用 dashboard PASS 或 deterministic eval 宣稱 assistant 可用。

已完成：

- `docs/legacy/` 刪除。
- `docs/active/` 刪除。
- root `ROADMAP.md` 刪除。
- canonical docs 重新分層。
- fast dashboard clean evidence 已記錄。
- backend / UI / data pipeline / agent / validation 架構文件已有第一輪 source 對照。
- 後端第一個重構主線已開工：
  - 新增 `XBrainLab/backend/application/`
  - `BackendFacade` 核心 workflow 改走 `ApplicationService`
  - 新增 state snapshot、capability policy、command result、error boundary
- 第二輪 contract 收斂已完成：
  - `evaluate` / `visualize` / `saliency` / `new_session` 有明確 future placeholder contract，
    policy 不再宣稱可執行。
  - `set_montage` 在 service contract 中不再假成功，仍留在 `BackendFacade` legacy path。
  - `reset_session` 會清掉 active backend session 的資料與訓練設定狀態。
  - low-mock workflow tests 已覆蓋 load -> epoch -> dataset -> training readiness -> reset。
- 第一批 UI / Agent command surface unification 已完成：
  - preprocess capability 改成要求 raw data；create epoch 才要求 preprocessed data。
  - UI dataset import / preprocess / epoching / start training readiness 讀
    ApplicationService capability policy。
  - Agent prompt tool list 和 execution guard 讀同一套 capability policy。
  - Agent tool output 寫回 structured JSON payload。
  - Agent real tools 透過 typed result adapter 區分 success / failed /
    blocked，不再把 `"Error: ..."` legacy 字串誤當成功。
  - Chat panel 補 retry / clear / compact backend diagnostics。

## 現在要做

1. 已完成 targeted 修復：一般輸入如 `hello` 透過 product-flow test 驗證會產生可見
   assistant 回覆；local runtime 失敗、empty response、worker error 會產生可見訊息，不能
   silent failure。
2. 已完成 ChatPanel 第一輪產品化重設計：空狀態、header、status chips、model/runtime/backend
   diagnostics、bubble、composer 都已重做。
3. 已完成第一批 UI execution command adapter 與 agent direct CommandResult path。
4. 已新增 product click-through / synthetic pipeline walkthrough tests。
5. 現在進行 truth docs / validation closure；接著回到剩餘 UI action migration、
   launcher click-through、query command contract。

## Product Delivery Milestone TODO

這份 checklist 是目前 autopilot 的恢復點。若對話上下文被壓縮，下一個 agent
應先從這裡恢復，不要只根據聊天記憶判斷進度。

### Milestone A - Confirm Current Progress

狀態：完成；不是重做，而是從目前 dirty worktree 繼續收斂。

- [x] 讀取 `git status --short`。
- [x] 讀取 `git diff --stat`。
- [x] 重新確認 `docs/current.md`、本文件、roadmap、validation、agent docs。
- [x] 判斷目前已完成到 backend baseline、UI/agent command readiness、local runtime
  preflight/launcher 初步實作。
- [x] 最終收尾前重新列出仍髒的 worktree 大類。

### Milestone B - Backend Product Core

狀態：工程 baseline 通過，可支撐目前 UI / Agent migration；query command 仍是本輪產品收斂缺口。

- [x] `ApplicationService` / `Command API` / `CapabilityPolicy` /
  `CommandResult` contract 對齊。
- [x] exposed command 要嘛可執行，要嘛明確回傳 unsupported / future result。
- [x] state snapshot 覆蓋 raw / preprocessed / epoch / dataset / training /
  evaluation / visualization / `last_error`。
- [x] capability policy 覆蓋 load / preprocess / epoch / dataset / train /
  reset destructive confirmation。
- [x] `BackendFacade` 保留舊 API，但核心 workflow 包 `ApplicationService`。
- [x] low-mock backend workflow tests 通過。
- [ ] 本輪剩餘：`evaluate` / `visualize` / `saliency` 仍需從 future placeholder
  推進成 service-backed query command。

### Milestone C - UI / Agent Command Surface Unification

狀態：第一批高價值 workflow 通過，可支撐 local runtime / launcher；UI execution 也已有
第一批 service-backed command adapter。legacy controller path 仍需逐步遷移。agent tool
result 已收斂成 typed adapter，mapped tools 可直接回 `CommandResult` payload。

- [x] UI readiness for load / preprocess / create epoch / generate dataset /
  train / reset 讀同一套 `ApplicationService` capability policy。
- [x] Agent prompt tool list 和 execution guard 讀同一套 capability policy。
- [x] blocked command reason 對齊 backend capability reason。
- [x] Agent tool output 保留 structured JSON payload。
- [x] `BackendFacade` 仍相容 headless tests。
- [x] 本輪完成：dataset import、reset、preprocess、epoching、training start / stop execution
  改成 service command adapter，mock / legacy caller 保留 controller fallback。
- [ ] 剩餘：label import、smart parse、channel selection、split/model/training setting dialogs、
  evaluation / visualization query actions 仍需 service command adapter。
- [x] Agent real tools 從舊 facade string result 收斂到 typed
  `CommandResult` / equivalent result adapter。
- [x] Agent mapped workflow tools 可直接執行 ApplicationService command 並回 structured
  `CommandResult` payload；`load_data` / `set_montage` / `switch_panel` 等 legacy/request path
  仍保留。

### Milestone D - UI Chat / Agent Panel Stabilization

狀態：targeted 修復完成，broader UI / LLM gate 通過。工程 baseline 曾通過，但人工檢查發現
chat UI 品質不足，且一般輸入 `hello` 沒有 assistant 回覆；本輪已補 visible-response
contract、ChatPanel product redesign 和 regression tests。

- [x] chat panel 可 send / stop / retry / clear。
- [x] loading / error / compact backend diagnostics 可見。
- [x] local runtime unavailable 不讓 UI 直接閃退，會顯示狀態。
- [x] UI tests、dialog acceptance smoke、agent manager smoke 通過。
- [x] UI -> agent -> backend blocked-command deterministic tool flow 可測。
- [x] normal text input product flow：使用者輸入 `hello` 後，必須看到 assistant 回覆或可理解錯誤。
- [x] empty model response 必須顯示 fallback/error bubble，不能只結束 processing。
- [x] worker error / local unavailable 必須在 UI 中可見。
- [x] chat panel 視覺與互動重新設計到產品級，不再像 debug dock。
- [ ] 真 local model loading timeout 必須在 UI 中可見並驗收。
- [ ] 真 local model load / failure / fallback 下的 UI smoke。
- [ ] 桌面 launcher 啟動後開 chat panel 的 product smoke。

### Milestone E - Agent Tool System Alignment

狀態：agent command guard 與 typed result adapter 已完成；剩下 product walkthrough 和 UI state refresh 驗收。

- [x] Agent prompt tool list 讀 `ApplicationService` capability policy。
- [x] Tool call 前用 ApplicationService guard 檢查 blocked reason。
- [x] Tool output 寫入 conversation history 時保留 structured JSON payload。
- [x] empty state 不能 train 的 blocked reason 由 backend policy 產生。
- [x] Agent real tools 改為消費 typed `CommandResult` 或等價 adapter。
- [ ] Tool call 後用 state snapshot 更新 UI / agent diagnostics。
- [ ] reset / new session confirmation boundary 的 product UI flow 還要驗收。

### Milestone F - Local LLM Runtime

狀態：完成 product baseline；primary / fallback 都已下載並通過 smoke。

- [x] 盤點目前 local runtime：`torch` / `transformers` 可用；`accelerate` /
  `bitsandbytes` 不作預設硬需求，4-bit 是 optional path。
- [x] 盤點硬體與磁碟：RTX 5070 Ti 16GB VRAM；`D:` 仍有足夠空間。
- [x] 上網確認 2026-05 適合 RTX 5070 Ti 16GB 的非中國 primary / fallback model。
- [x] 排除中國公司或中國來源模型，例如 Qwen、DeepSeek、Yi、GLM、Baichuan、InternLM、MiniCPM。
- [x] 選型：primary `microsoft/Phi-4-mini-instruct`，fallback
  `microsoft/Phi-3.5-mini-instruct`。
- [x] 下載前估算 primary：約 7.69GB，BF16 safetensors，VRAM 約 9GB，cache
  `XBrainLab/llm/core/models`。
- [x] 建立下載前 preflight，不讓單一模型超過 10GB、不讓總 cache 超過 20GB。
- [x] 使用者已授權刪除 Qwen cache；`models--Qwen--Qwen2.5-7B-Instruct` 和 lock 已刪。
- [x] primary model 已下載並通過 health check。
- [x] fallback model 已下載並通過 health check，總 cache 約 `15.34GB`，低於 20GB 上限。
- [x] 建立 health check：cache exists / packages / GPU / minimal prompt /
  structured-output or prompt-protocol smoke。
- [x] 建立 fallback：primary 不可用且 fallback cache ready 時使用 fallback；UI 顯示原因。
- [x] 更新 `docs/architecture/agent.md`、`docs/architecture/validation.md` 或
  `docs/validation/README.md` 的 local runtime 邊界。

### Milestone G - Desktop Launcher / Packaging

狀態：完成低風險 launcher baseline；已補 automated product click-through smoke，真 Windows
launcher 人工 walkthrough 仍待驗收。

- [x] 盤點 `run.py`、Poetry entry point、existing scripts、Windows launcher 選項。
- [x] 產出低風險 WSL Windows launcher：
  `scripts/launchers/xbrainlab_wsl_launcher.cmd`。
- [x] 產出 PowerShell launcher：
  `scripts/launchers/xbrainlab_wsl_launcher.ps1`。
- [x] 複製可點擊 launcher 到 Windows Desktop：
  `/mnt/c/Users/Administrator/Desktop/XBrainLab.cmd`。
- [x] launcher 進入正確 repo / env，啟動 UI，寫錯誤 log 到
  `%LOCALAPPDATA%\\XBrainLab\\logs`。
- [x] missing local LLM 不可導致 app startup 閃退：startup 不載入 model；chat panel 會顯示 runtime reason。
- [x] 更新 `docs/operations.md`。
- [x] launcher smoke / startup log check：`xvfb-run` startup 顯示 `MainWindow initialized`。

### Milestone H - End-to-End Product Stabilization

狀態：targeted product-flow tests 已補，broader UI / LLM gate 已重跑；startup/local runtime
基線通過；automated assistant click-through 和 synthetic pipeline walkthrough 已新增。完整真
launcher / local model walkthrough 仍未完成。先前 automated final gate 漏掉 `hello` 無回覆
問題，因此不能再只靠 dashboard / deterministic eval 判斷。

- [x] desktop launcher / run.py startup -> MainWindow smoke 可展示。
- [x] local LLM 狀態可見於 chat panel diagnostics。
- [x] empty state 要求 train 時，agent 依 capability policy 拒絕並說明缺 dataset / config（unit 覆蓋）。
- [x] UI -> agent debug tool -> backend blocked command flow 會顯示 shared blocked reason。
- [ ] backend command 成功 / failed / blocked reason 的真 launcher 互動式 walkthrough。
- [x] normal chat input -> assistant visible response / visible failure 的 deterministic UI product-flow test。
- [x] assistant header/status/bubble/composer click-through layout smoke。
- [x] synthetic EEG button-driven pipeline walkthrough：Dataset import -> Preprocess filter ->
  Epoch -> Training config dry-run -> Evaluation result-ready state。
- [ ] normal chat input -> assistant visible response / visible failure 的真 launcher walkthrough。
- [ ] destructive reset / new session 有 confirmation boundary。
- [x] backend / UI / agent / local runtime automated gate 已補上 normal chat response targeted gate
  並重跑 UI / LLM suites。

### Milestone I - Tool-Call Eval / Thesis Evidence

狀態：deterministic baseline 已建立並跑通；local LLM primary / fallback 真實 eval runner 尚未開始。

- [x] 研究 BFCL / trajectory evaluation / function-calling eval / local structured-output 限制。
- [x] 實作 deterministic mock-agent baseline evaluator。
- [x] 至少 20 個 XBrainLab 專用 eval cases。
- [x] 產出 machine-readable JSON 與 human-readable Markdown report。
- [ ] 若 local LLM 穩定，再跑 primary / fallback model。
- [x] 更新 `docs/validation/README.md` 與 implementation log。

### Milestone J - Final Validation / Documentation Closure

狀態：舊 automated final gate 不再足夠；chat product blocker targeted 修復後，broader UI /
LLM / docs gate 已通過，但仍需人工 launcher click-through 後才能宣稱完整桌面交付。

- [x] 跑 backend unit / backend integration / pipeline integration。
- [x] 跑 UI unit / dialog smoke。
- [x] 跑 LLM unit / local health / prompt smoke。
- [x] 跑 mkdocs strict 與 `git diff --check`。
- [x] 更新 worklog / implementation log / architecture docs / planning docs。
- [x] 清楚列出仍髒的 worktree 大類與 release 前風險。

## 當前執行邊界

目前不是只做後端 baseline，也不是只做文件整理。下一輪可以一路推進
backend、UI、agent、local LLM 和 desktop launcher，但要維持工程順序：

1. 先讓 `ApplicationService / Command API` 成為可靠 backend core。
2. 再統一 UI 和 agent 使用 backend 的 command surface。
3. 再修穩 UI chat / agent panel 與 local LLM runtime。
4. 再做 desktop launcher / product stabilization。
5. 產品主線穩定後，才開始 tool-call eval / thesis evidence。

允許做：

- UI action execution 從 controller direct-call 遷移到 service-backed adapter。
- agent real tools 從 facade 舊字串回傳遷移到 typed `CommandResult` formatter。
- local LLM model selection、preflight、health check、fallback 和 UI 狀態整合。
- desktop launcher / shortcut / startup smoke。
- 低風險移除或隔離 API / Gemini code path；高風險時先文件化 removal plan。

仍要避免：

- 不做無測試支撐的大爆改。
- 不把 UI / agent 各自接成第二套 backend workflow。
- 不在產品主線未穩定前提前做 tool-call eval。
- 不下載超過容量邊界的模型；單模型原則 10GB 內，總 cache 原則 20GB 內。
- 不使用中國公司或中國來源模型；Qwen、DeepSeek、Yi、GLM、Baichuan、InternLM、MiniCPM 等模型不列入選型。
- 不把 CHANGELOG 或 records 當 current truth。

## Product Delivery Done Definition

Milestone 是最低交付門檻，不是工作上限。下一輪完成定義應以「成品是否可用」
判斷，而不是只看清單是否勾完。

下一輪至少要交付：

- UI 和 agent 對 load / preprocess / epoch / dataset / train / reset 使用同一套
  `ApplicationService` capability policy 與 blocked reason。
- 至少一批 UI action execution 改成 service-backed command adapter，而不只是 read-only readiness。
- agent real tools 能消費 typed `CommandResult` 或等價 structured result。
- local LLM runtime 有 model selection、cache preflight、health check、prompt smoke 和 failure fallback。
- 有可點擊啟動的 desktop launcher / shortcut 或明確可用的 Windows launcher。
- backend -> UI -> agent -> local runtime 至少有一條可展示 product flow。
- chat 一般文字輸入必須有可見 assistant 回覆；模型空回覆、worker error、local unavailable
  都必須在 UI 顯示成可理解狀態，不能 silent failure。
- 完成後更新 worklog、implementation log、backend/UI/agent/validation/planning 文件。
- 跑完相關 backend、UI、agent、local runtime、MkDocs、diff whitespace 驗證。

如果上述最低項目完成後仍有明顯閃退、狀態不同步、錯誤無法理解、文件失真或測試無法支撐，
agent 應繼續修，不應宣稱完成。
