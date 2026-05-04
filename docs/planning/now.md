# Now

最後更新：`2026-05-04`

這份文件只放短期施工焦點。

它不是：

- roadmap：產品主線看 `docs/planning/roadmap.md`。
- current truth：目前完整狀態看 `docs/current.md`。
- worklog：流水帳看 `docs/records/worklog.md`。

目前 `now.md` 的用途是：記錄 Goal 1 engineering baseline 的 closure 狀態、剩餘不能宣稱的事，
以及下一輪應優先處理的產品硬化方向。

## 目前位置

文件設計與 Goal 1 baseline 已進入可交接狀態：

- `docs/planning/roadmap.md` 已重寫為成品主線。
- `docs/target/data_interpretation_system.md` 已定義資料解讀終局設計。
- `docs/target/agent.md` 已定義 agent control loop、Verification Layer、Autonomy Policy /
  Decision Boundary 和成熟 tool taxonomy。
- `docs/target/architecture.md` 已把 Data Interpretation command surface、capability policy
  和 autonomy decision 寫成理想架構。
- `docs/validation/thesis_protocol.md` 已校正 thesis 主 evidence：tool-call accuracy，不是
  EEG training accuracy。
- Goal 1 長跑 runbook 已建立：`artifacts/goal/goal-1-product-autopilot.md`。

目前實作狀態要保守判斷：

- `ApplicationService / Command API` baseline 已存在，可作為後續重構骨架。
- Data Interpretation 的 backend command baseline 已新增。
- agent tool surface 已暴露 Data Interpretation tools，並能使用 backend dynamic confirmation
  boundary。
- Dataset panel 的主要資料入口已從 `Import Data` 改為 `Interpret Data Source`，並走
  scan -> preview -> validate -> confirm/apply；preview dialog 現在提供 apply 後保存 recipe
  的選項，並透過 `SaveInterpretationRecipeCommand` 寫入 recipe。舊 label import 入口已改成
  `Add Labels to Loaded Data`，定位為 service-backed compatibility path；label import 成功後
  會寫入 applied interpretation 的 label carrier / class map / selected event / recipe trace，
  UI 也可提示保存更新後 recipe。
- headless / MCP-ready automation adapter 已新增：
  `backend.application.automation` 產生 command schema / MCP-shaped tool specs，並把 JSON
  payload 轉回 typed `ApplicationService` command。
- stdio MCP server baseline 已新增：
  `XBrainLab.mcp.server` / `scripts/dev/run_mcp_server.py` 支援 MCP `initialize`、
  `tools/list`、`tools/call`，並在同一個 `ApplicationService` session 中執行工具。
- deterministic engineering eval 已擴到 `54` cases，包含 `15` 個 multi-turn cases 和
  `34 / 54` negative / blocked / confirmation / missing-input / recovery cases。
- 真 local LLM tool-call runner 已新增，使用同一份 `54` cases / scorer 接 primary /
  fallback 模型 raw output 並各重跑 `3` 次。前一輪 full rerun：
  - primary `microsoft/Phi-4-mini-instruct`：`53 / 54` pass。
  - fallback `microsoft/Phi-3.5-mini-instruct`：`53 / 54` pass。
  這是 engineering evidence，不是 thesis-ready accuracy；case 數仍不足 `100`，且仍有
  bandpass-vs-standard preprocess 語意 failure。
- `VerificationLayer` 已補 registered tool schema / required / type / enum 檢查，controller
  會在 execution 前攔可解析但不可執行的 tool JSON。
- local assistant guardrail slice 已補 placeholder path rejection、requested-intent boundary、
  parser 對 top-level array / OpenAI function-call shape 的支援、以及 standard preprocess /
  dataset split prompt/schema 規則。後續 normalizer slice 已把 command-only JSON、bare tool
  name、latest-turn substitute、query_state、BIDS hint、subject override、placeholder prose path
  和 result interpretation 接到 verifier / ApplicationService 語意。探索性 smoke artifact：
  - primary guardrail smoke：`6 / 6` pass。
  - fallback guardrail smoke：`6 / 6` pass。
  前一輪正式 `54` cases x `3` full rerun：
  - primary `microsoft/Phi-4-mini-instruct`：`53 / 54` pass。
  - fallback `microsoft/Phi-3.5-mini-instruct`：`53 / 54` pass。
  這仍不是 thesis-ready；case 數不足 `100`，且剩餘 bandpass-vs-standard preprocess 語意
  failure。
- 最新 tool-call thesis-candidate slice 已把同一 scorer 擴到 `100` cases，並用 cached
  primary / fallback local models 各重跑 `3` 次：
  - deterministic baseline：`100 / 100` pass。
  - primary `microsoft/Phi-4-mini-instruct`：`100 / 100` pass。
  - fallback `microsoft/Phi-3.5-mini-instruct`：`100 / 100` pass。
  - runtime classification：primary / fallback 都是 `gpu-ready`；cache `15.34 GB`；no download。
  這支撐 thesis-candidate tool-call benchmark evidence；仍不能取代 ChatPanel walkthrough、
  Windows launcher click-through、MCP Inspector / release config 或成熟 import wizard 驗收。
- MCP stdio external-client walkthrough 已新增：
  - `scripts/dev/capture_mcp_stdio_walkthrough.py` 是只依賴 Python standard library 的 client。
  - client 會啟動 prepared XBrainLab runtime 內的 `scripts/dev/run_mcp_server.py`，並保存
    `artifacts/mcp/stdio-walkthrough.json` / `.md`。
  - evidence 覆蓋 `initialize`、`tools/list`、`scan_source`、`preview_interpretation`、
    `validate_interpretation`；tool schema taxonomy 仍來自 ApplicationService automation
    surface。
  - 這支撐 external stdio client path，不代表 MCP Inspector GUI click-through、Windows release
    config、HTTP transport 或 long-running training through MCP 已完成。
- Goal 1 要求的 Data Interpretation baseline 已可走 source -> scan -> preview -> validate ->
  confirm/apply -> recipe，且有 backend non-mocked source -> recipe -> preprocess -> epoch ->
  dataset workflow evidence 和 UI-observable preview / applied artifact。
- 剩餘非 Goal 1 closure blockers：label import 已能寫入 recipe trace，但尚未成為成熟 import
  wizard 內的 label/recipe editor；MCP Inspector / Windows release config 尚未完成、UI replay coverage
  還不是完整真人 walkthrough。
- subject / session / task / run metadata resolution 已可在 preview dialog 呈現並進入 recipe trace；
  更完整的 override UI 仍是下一輪 hardening。

## 下一個 Goal

下一個 goal 應聚焦在產品硬化，而不是重做 Goal 1 baseline：

```text
True local LLM ChatPanel workflow
  + label/recipe wizard hardening
  + MCP Inspector / release config
  + Windows launcher click-through
```

這不是單純讓 deterministic eval 分數漂亮。下一輪要把真 UI、真 local model、可見 blocked
reason、recipe editing 和 external-agent adapter 邊界一起驗證。

MCP 也應納入設計，但 Goal 1 的最低要求是 **MCP-ready command surface**：先確保 command
taxonomy、capability policy、autonomy policy、result schema 足以支撐 MCP server。若 runner
能安全完成 MCP server，可作為 Goal 1 延伸；若無法完成，不能因此延後 Data Interpretation
主線。

## Goal 1 Scope

Goal 1 至少要包含：

1. **Data Interpretation command surface**
   - `scan_source`
   - `preview_interpretation`
   - `validate_interpretation`
   - `apply_interpretation`
   - `save_interpretation_recipe`
   - `reload_interpretation_recipe`

2. **Data Interpretation lifecycle**
   - `ScanResult`
   - `InterpretationCandidate`
   - `InterpretationPreview`
   - `ValidationDecision`
   - `AppliedInterpretation`
   - `ImportRecipe`

3. **Metadata resolution**
   - subject / session / task / run preview。
   - filename / folder / BIDS / header metadata source。
   - user confirmation / override。
   - recipe 保存 metadata rule 與 override。

4. **Validation decisions**
   - `safe`
   - `needs_confirmation`
   - `blocked`
   - BIDS metadata 的 `warning` / `limited` / `blocked`

5. **Autonomy policy / decision boundary**
   - command-specific autonomy policy。
   - `allow_auto`、`confirm`、`ask_user`、`stop`、`repair`、`block`。
   - `continue_allowed_after_success`。
   - decision boundary taxonomy：semantic、high-impact、long-running、destructive、
     missing-input、resource-lock、blocked。

6. **Agent tool taxonomy migration**
   - Discovery / Query。
   - Data Interpretation。
   - Metadata Resolution。
   - Data Transform。
   - Experiment Setup。
   - Execution。
   - Lifecycle / Destructive。
   - UI Routing。

7. **UI import entry redesign**
   - 使用者給 file / folder / BIDS root / recipe。
   - UI 顯示 scan / preview / validation / confirmation。（preview dialog 已完成第一版。）
   - 不再以 `Imported` / `Labels attached` 作為資料可信主語言。（主 import entry 已改；
     label import messaging 仍待收斂。）
   - 使用者已允許為新 Data Interpretation / load data 機制修改資料入口 UI；不能因為 UI
     會大改就只做 backend 或把新流程塞回舊 import 外殼。

8. **Agent alignment**
   - Context Assembler 暴露 Data Interpretation tools。（agent surface slice 已完成。）
   - Verification Layer 檢查 capability policy、Data Interpretation decision 和 autonomy policy。
     （目前已檢查 backend capability / dynamic confirmation boundary；deterministic eval cases
     已納入 Data Interpretation decision / blocked / confirmation / recovery。）
   - visible response 不暴露 raw schema、snake_case command、traceback 或 debug payload。

9. **Evaluation baseline**
   - deterministic / engineering tool-call cases 覆蓋 Data Interpretation、metadata resolution、
     autonomy boundary、blocked、confirmation、missing parameter、recipe reload。
     （目前 deterministic baseline 已擴為 `100 / 100` pass。）
   - local LLM runner 使用同一份 cases 接 primary / fallback raw output，各重跑 `3` 次；
     目前 primary `100 / 100` pass、fallback `100 / 100` pass，可作為 thesis-candidate
     tool-call benchmark evidence，但仍不能替代 UI / launcher / ChatPanel 產品驗收。
   - scripted replay 要分 backend replay 和 UI-observable replay；不能只看文字報告就宣稱 UI 行為正確。
   - 正式 local LLM thesis eval 可以晚一點，但 scorer schema 與 case shape 不能再用舊
     `load_data / attach_labels` 作為主設計。

10. **MCP-ready automation surface**
    - CLI / headless runner 保留給 CI、eval、batch 和 artifact generation。
      （`scripts/dev/run_application_command.py` 已新增。）
    - MCP server 作為 external agent adapter，使用同一套 command taxonomy。
      （目前已有 stdio MCP server baseline：`scripts/dev/run_mcp_server.py`。）
    - MCP client 不應需要安裝 XBrainLab 的 EEG / PyQt / PyTorch 依賴；MCP server 跑在 prepared
      XBrainLab runtime。
    - MCP calls 不能繞過 ApplicationService、capability policy 或 autonomy policy。

## Goal 1 Done Definition

Goal 1 不能只做文件或小 patch。至少要達到：

- UI、agent、headless path 都能走同一套 Data Interpretation command surface。
- 資料入口 UI 已反映新 Data Interpretation 心智模型；不是舊 `Import Data` / `Import Label`
  外殼加 backend adapter。
- 舊 `load_data / attach_labels` 不能再是新 UI / agent 的主要心智模型；若保留，只能是
  legacy adapter 或底層 compatibility path。
- subject / session / task / run metadata 會在資料解讀 preview 中顯示，且能保存進 recipe。
- Data Interpretation validation 會產生 `safe`、`needs_confirmation`、`blocked`。
- command result 或 verification result 能表達 autonomy decision / decision boundary。
- agent 可以規劃完整 workflow，但每一步都一個 command 一個 command 地 verify / execute /
  refresh state。
- decision boundary 會強制停下來問使用者，不依賴 LLM 自己「夠聰明」。
- 至少一條 non-mocked synthetic workflow 走過：

```text
source_path
  -> scan
  -> preview metadata / label-event interpretation
  -> validate
  -> confirm / apply
  -> recipe
  -> preprocess
  -> epoch
  -> dataset
```

- tests / artifacts 能證明上述行為，不只靠人工讀程式碼。
  （backend integration test 已覆蓋；UI-observable artifact 已覆蓋 Data Interpretation preview /
  applied dataset panel。）
- scripted replay 至少能產生 backend report；涉及 UI 的 replay 必須有 transcript、visible state、
  screenshot 或 UI artifact，不能只看 backend JSON。
- command / result schema 已足以包成 MCP tools，且 MCP 設計不會變成第三套 workflow truth。
- 文件同步更新 `target/`、`architecture/`、`validation/`、`records/`。

## Goal 前必做

啟動 goal 前先做：

1. 跑一次文件一致性檢查。
   - 確認 `target/architecture.md`、`target/data_interpretation_system.md`、`target/agent.md`、
     `validation/thesis_protocol.md`、`planning/roadmap.md`、本文件不互相矛盾。

2. 建立 docs checkpoint。
   - 目前文件變更很多；goal runner 開工前應先有一個清楚 checkpoint。
   - 不要把 `.vscode/settings.json` 或 root `settings.json` 的本機變更混入 checkpoint。

3. 確認 goal runbook。
   - 目前 runbook 位於 `artifacts/goal/goal-1-product-autopilot.md`。
   - runner 不應頻繁回報，應改用 `records/worklog.md` 和
     `records/implementation_log.md` 留狀態。
   - runner 必須遵守 commit discipline；每個可驗收切片完成後 commit。

4. 設定驗收 gate。
   - 不只跑 dashboard。
   - 需要 backend command tests、agent tool / verifier tests、UI import walkthrough、
     non-mocked synthetic workflow、UI-observable scripted replay、mkdocs strict。

## Validation Gates

Goal runner 回報完成前至少要跑：

```bash
git diff --check
poetry run mkdocs build --strict
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
```

還需要依實作範圍跑 targeted tests，例如：

```bash
poetry run pytest --capture=sys tests/unit/backend/application -q
poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q
poetry run pytest --capture=sys tests/integration/backend tests/integration/io/test_io_integration.py -q
```

若改 UI / import flow，還要跑相關 UI tests / walkthrough。若改 launcher / local runtime，還要跑
Windows launcher 或 local model resource-safe smoke。

若新增 MCP server，還要至少驗證：

```bash
poetry run pytest --capture=sys tests/unit/mcp tests/integration/mcp -q
```

實際 test path 可依實作調整，但不能只靠手動 MCP 呼叫宣稱完成。

## 不能宣稱

- 不能宣稱 Data Interpretation System 已完成，除非 source path 到 recipe 的流程真的可用。
- 不能宣稱 agent 已達理想架構，除非它已遷移到新 tool taxonomy 並受 autonomy policy 約束。
- 不能把 prompt smoke 當成真 local LLM ChatPanel walkthrough。
- 不能把 deterministic eval 當成 local LLM 真實 tool-call accuracy；目前 primary / fallback
  真模型 `100` case runner 已有 `100 / 100` x `3` evidence，但這只支撐 tool-call
  thesis-candidate benchmark，不代表 ChatPanel / launcher / import wizard 產品驗收完成。
- 不能把 backend scripted replay 的文字報告當成 UI 行為正確；UI replay 要有人眼可審查 artifact。
- 不能把 mock-heavy tests 當成真實 workflow evidence。
- 不能把 dashboard PASS 當成產品完成或 thesis claim 成立。
- 不能讓 API / Gemini / remote LLM 回到 product execution path。
- 不能使用中國公司或中國來源模型。
- 不能讓 MCP 直接操作 controller 或繞過 ApplicationService / autonomy policy。

## 下一步

現在最應該做的是：

```text
1. 建立 docs checkpoint
2. 啟動 Codex goal
3. 由 reviewer 依 runbook 驗收，不達標就打回 goal 繼續
```
